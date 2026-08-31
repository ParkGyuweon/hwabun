# -*- coding: utf-8 -*-
"""
LLM 에이전트 러너 — PA 페르소나가 실제 사이트를 돌아다닌다
================================================================================

무엇을 하는가
    페르소나 프로필을 LLM 에게 주고, 실제 브라우저로 프론트를 조작하게 한다.
    화면을 텍스트로 읽어 "다음에 뭘 할래" 를 묻고, 답을 받아 클릭·스크롤을 실행한다.

왜 로그를 직접 만들지 않는가
    **브라우저를 조작하면 프론트의 log.ts 가 알아서 로그를 남긴다.**
    우리가 로그를 만들면 gen_behavior_logs.py 와 다를 게 없다. 실제 DOM 을 거쳐야
    이벤트 계약·수집 API·Kafka 까지 한 번에 검증된다.

대상은 PA 100명뿐이다
    PC 9,900명은 gen_behavior_logs.py 가 합성 로그를 만든다. PA 는 그 대상에서
    빼두었으므로(--include-agents 없이는 생성 안 됨) 여기서만 로그가 생긴다.

크레딧을 아끼는 법
    --dry-run   LLM 을 부르지 않고 프롬프트만 출력한다. 문구를 다듬을 때 쓴다 (0 크레딧)
    --cache     같은 화면·같은 페르소나면 저장된 응답을 재사용한다 (2회차부터 0 크레딧)
    실측 기준 gpt-4.1-nano 가 1회 0.6 크레딧. 100명 x 30턴 = 약 1,800 (예산의 1.8%)

준비
    pip install playwright openai
    playwright install chromium
    set GMS_KEY=...            (Windows CMD)
    $env:GMS_KEY="..."          (PowerShell)

실행
    python simulator/agents/agent_runner.py --dry-run --limit 1     # 프롬프트만 확인
    python simulator/agents/agent_runner.py --limit 3 --headed      # 3명, 브라우저 보이게
    python simulator/agents/agent_runner.py --limit 100             # 전원 배치
"""
import argparse
import hashlib
import io
import json
import os
import random
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
PERSONA_FILE = os.path.join(ROOT, "simulator", "personas", "data",
                            "personas_100_agent.json")
CACHE_DIR = os.path.join(BD, ".cache")

GMS_BASE = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
MODEL = "gpt-4.1-nano"          # 실측 5/5 통과. 1회 0.6 크레딧

# 에이전트가 쓸 수 있는 행동. 여기 없는 것을 답하면 그 턴은 버린다.
ACTIONS = ("click_product", "scroll", "add_to_cart", "back_to_list", "leave")

NL = "\n"        # f-string 안에서 줄바꿈을 쓰려면 이름이 필요하다


# ============================================================================
# 1. 페르소나 -> 프로필 문장
# ============================================================================

TONE_KR = {"fair": "밝은", "light": "밝은 편", "medium": "중간",
           "tan": "어두운 편", "deep": "어두운"}
TYPE_KR = {"combination": "복합성", "dry": "건성", "normal": "중성", "oily": "지성"}


def profile_text(p):
    """페르소나 레코드 -> LLM 에게 줄 자기소개

    구매 이력을 그대로 넣는 것이 핵심이다. "이 브랜드를 이미 샀다" 가
    다음 선택의 가장 강한 근거이기 때문이다 (브랜드 lift 6.45x).
    """
    revs = sorted(p["reviews"], key=lambda r: r["submission_time"])
    bought, seen = [], set()
    for r in revs:
        if r["group_id"] in seen:
            continue
        seen.add(r["group_id"])
        mark = "만족" if r["rating"] >= 4 else ("불만" if r["rating"] <= 2 else "보통")
        bought.append(f"{r['brand_name']} {r['product_name']} ({mark})")

    prices = [r.get("price_usd") for r in revs if r.get("price_usd")]
    price_line = ""
    if prices:
        price_line = f"\n- 주로 사는 가격대: ${min(prices):.0f} ~ ${max(prices):.0f}"

    return (f"- 피부 타입: {TYPE_KR.get(p['skin_type'], p['skin_type'])}\n"
            f"- 피부 톤: {TONE_KR.get(p['skin_tone'], p['skin_tone'])}"
            f"{price_line}\n"
            f"- 지금까지 산 것:\n    " + "\n    ".join(bought[-8:]))


SYSTEM_TMPL = """당신은 화장품 쇼핑몰을 둘러보는 실제 사람입니다.

[당신이 누구인가]
{profile}

[어떻게 행동하는가]
- **화면에 당신 취향과 맞는 상품이 보이면 그것을 누르십시오.**
  이미 써보고 만족한 브랜드, 비슷한 가격대면 관심이 갑니다.
- 불만이었던 상품과 비슷한 것은 피하십시오.
- 상세 페이지에서는 scroll 로 아래까지 읽어본 뒤에 판단하십시오.
- 마음에 들면 add_to_cart, 아니면 back_to_list 로 돌아가십시오.
- 한 세션에서 장바구니에 담는 것은 보통 한두 개입니다.
- scroll 은 더 볼 것이 있을 때만 쓰십시오.

[답변 형식]
JSON 만 출력하십시오. 설명이나 코드블록을 붙이지 마십시오.

{{"action": {actions},
 "target": "화면에 실제로 있는 상품명 (해당 없으면 null)",
 "reason": "한 문장"}}"""


# ============================================================================
# 2. 화면 -> 텍스트
# ============================================================================

def read_screen(page):
    """지금 브라우저에 보이는 것을 LLM 이 읽을 수 있는 텍스트로 만든다.

    DOM 전체를 주면 토큰이 폭발하고 모델이 헤맨다. **판단에 필요한 것만** 추린다.
    프론트가 data-product-id / data-position 을 노출해 두어 셀렉터가 안정적이다.
    """
    url = page.url
    if "/product/" in url or page.locator('[data-log-action="add_to_cart"]').count():
        return read_detail(page)
    return read_list(page)


def read_list(page):
    """목록 화면. **지금 화면에 실제로 보이는 카드만** 읽는다.

    스크롤해도 같은 12개를 돌려주면 프롬프트가 안 바뀌어 LLM 이 같은 판단을
    무한 반복한다 (실제로 25턴 내내 scroll 만 한 사고가 있었다).
    """
    pct = page.evaluate(
        "() => Math.round((window.scrollY + window.innerHeight)"
        " / Math.max(document.body.scrollHeight,1) * 100)")
    cards = page.locator(".card[data-product-id]")
    lines, seen = [], set()
    for i in range(cards.count()):
        if len(lines) >= 12:
            break
        c = cards.nth(i)
        try:
            if not c.is_visible():      # 화면 밖 카드는 보이지 않는 것이다
                continue
            pid = c.get_attribute("data-product-id")
            # 프로모션 배너와 그리드가 같은 .card 를 써서 같은 상품이 두 번 잡힌다.
            # 중복을 그대로 주면 LLM 이 "1번과 11번 중 뭐지" 로 헷갈린다
            if pid in seen:
                continue
            seen.add(pid)
            brand = c.locator(".card__brand").inner_text(timeout=1500).strip()
            name = c.locator(".card__name").inner_text(timeout=1500).strip()
            price = c.locator(".card__price").inner_text(timeout=1500).strip()
        except Exception:
            continue
        lines.append(f"{len(lines)+1}. {brand} {name} — {price}")
    body = "\n".join(lines) if lines else "(화면에 상품이 없습니다)"
    tail = "  ← 목록 끝입니다" if pct >= 97 else ""
    return (f"[현재 화면] 상품 목록 (스크롤 {pct}%{tail})\n\n{body}\n\n"
            f"다음에 무엇을 하시겠습니까?"), "list"


def read_detail(page):
    def txt(sel, default=""):
        try:
            return page.locator(sel).first.inner_text(timeout=1500).strip()
        except Exception:
            return default

    name = txt("h1", "(상품명 불명)")
    brand = txt(".detail__brand") or txt(".card__brand")
    price = txt(".detail__price") or txt(".card__price")
    # 지금 화면에 보이는 섹션 — 얼마나 내려왔는지를 알려준다
    secs = []
    for s in ("product_hero", "highlights", "about_product", "ingredients",
              "how_to_use", "similar_products", "reviews"):
        el = page.locator(f'[data-log-section="{s}"]')
        if el.count() and el.first.is_visible():
            secs.append(s)
    pct = page.evaluate(
        "() => Math.round((window.scrollY + window.innerHeight)"
        " / document.body.scrollHeight * 100)")
    return (f"[현재 화면] 상품 상세\n\n"
            f"{brand} {name} — {price}\n"
            f"스크롤 위치: {pct}%\n"
            f"보이는 영역: {', '.join(secs) if secs else '상단'}\n\n"
            f"다음에 무엇을 하시겠습니까?", "detail")


# ============================================================================
# 3. LLM 호출 (캐시)
# ============================================================================

def ask(client, system, user, cache_on, dry):
    """LLM 에게 다음 행동을 묻는다.

    dry=True 면 호출하지 않고 프롬프트만 보여준다 (크레딧 0).
    cache_on 이면 (system+user) 해시로 응답을 저장·재사용한다 (2회차부터 0).
    """
    if dry:
        print("\n" + "─" * 70)
        print(system)
        print("─" * 70)
        print(user)
        print("─" * 70)
        return {"action": "scroll", "target": None, "reason": "(dry-run)"}, 0

    key = hashlib.md5((system + "\x00" + user).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if cache_on and os.path.exists(path):
        return json.load(open(path, encoding="utf-8")), 0

    kw = dict(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        # 200 이면 reason 을 쓰다가 잘려서 JSON 이 통째로 깨진다.
        # 프롬프트가 길어질수록 reason 도 길어지므로 넉넉히 준다
        max_tokens=400,
        temperature=0.9,      # 사람마다 다르게 움직여야 한다. 낮추면 전부 같은 동선이 된다
        # 모델이 문장을 섞어 쓰지 못하게 아예 JSON 만 뱉도록 강제한다
        response_format={"type": "json_object"},
    )
    try:
        r = client.chat.completions.create(**kw)
    except Exception:
        kw.pop("response_format")        # 지원 안 하는 모델이면 없이 재시도
        r = client.chat.completions.create(**kw)
    txt = (r.choices[0].message.content or "").strip()
    finish = r.choices[0].finish_reason
    if txt.startswith("```"):                    # 코드펜스로 감싸는 경우가 있다
        txt = txt.split("```")[1]
        txt = txt[4:] if txt.startswith("json") else txt
        txt = txt.strip()
    try:
        obj = json.loads(txt)
    except Exception:
        # 왜 깨졌는지 안 보이면 고칠 수가 없다. 잘린 것인지 헛소리인지 구분한다
        why = "토큰 잘림" if finish == "length" else "파싱 실패"
        print(f"       [{why}] {txt[:110]}")
        return None, 1
    if obj.get("action") not in ACTIONS:
        print(f"       [모르는 action] {obj.get('action')!r}")
        return None, 1
    if cache_on:
        os.makedirs(CACHE_DIR, exist_ok=True)
        json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return obj, 1


# ============================================================================
# 4. 행동 실행
# ============================================================================

def norm(s):
    """상품명 비교용 정규화. LLM 이 이름을 조금 다르게 쓰는 것을 흡수한다"""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def click_safe(loc, page):
    """겹친 요소 때문에 막히는 클릭을 뚫는다.

    카드에 마우스를 올리면 Quick Look 버튼이 카드 한가운데를 덮는다.
    Playwright 는 기본으로 요소 중앙을 누르므로 그대로 두면 30초를 기다리다
    TimeoutError 로 죽는다. 사람이라면 버튼을 피해 이미지 구석을 누를 것이므로
    좌상단(8,8) 을 먼저 누르고, 그래도 막히면 이벤트를 직접 쏜다.
    """
    for kw in ({"position": {"x": 8, "y": 8}, "timeout": 4000},
               {"timeout": 3000, "force": True}):
        try:
            loc.click(**kw)
            return True
        except Exception:
            pass
    try:
        loc.dispatch_event("click")   # 히트테스트를 건너뛰고 핸들러만 실행
        return True
    except Exception:
        return False


def do_action(page, act, target):
    """LLM 이 고른 행동을 실제 DOM 조작으로 옮긴다. 성공하면 True"""
    a = act

    if a == "scroll":
        page.mouse.wheel(0, random.randint(500, 1200))
        page.wait_for_timeout(random.randint(700, 2500))
        return True

    if a == "back_to_list":
        page.go_back()
        page.wait_for_timeout(1200)
        return True

    if a == "add_to_cart":
        btn = page.locator('[data-log-action="add_to_cart"]')
        if not btn.count():
            return False                         # 목록 화면에서는 담을 수 없다
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(900)
        return True

    if a == "click_product":
        cards = page.locator(".card[data-product-id]")
        want = norm(target)
        for i in range(cards.count()):
            c = cards.nth(i)
            try:
                nm = norm(c.locator(".card__name").inner_text(timeout=1000))
            except Exception:
                continue
            # LLM 이 이름을 줄여 쓰는 경우가 많아 부분 일치까지 허용한다
            if want and (want in nm or nm in want or want[:14] in nm):
                if not click_safe(c.locator(".card__link").first, page):
                    return False
                page.wait_for_timeout(1400)
                return True
        return False                             # 화면에 없는 상품을 지어낸 경우

    return False


# ============================================================================
# 5. 한 명 돌리기
# ============================================================================

def run_one(page, client, persona, max_turns, cache_on, dry, verbose):
    system = SYSTEM_TMPL.format(profile=profile_text(persona),
                                actions=" | ".join(f'"{a}"' for a in ACTIONS))
    calls, done, failed, carted = 0, 0, 0, 0

    history = []          # 최근 행동. 없으면 LLM 이 같은 판단을 무한 반복한다
    visited, cart = [], []   # 이미 본 상품 / 담은 상품
    for turn in range(1, max_turns + 1):
        user, kind = read_screen(page)
        # 본 상품과 담은 상품을 알려주지 않으면 같은 상품만 25턴 내내 반복한다.
        # (실제로 한 페르소나가 BELIF 두 개만 왕복한 사고가 있었다)
        if visited:
            user = (f"[이미 본 상품] {', '.join(visited[-8:])}"
                    f"{NL}같은 상품을 또 누르지 마십시오. 목록에 새 상품이 없으면"
                    f" scroll 로 아래쪽을 확인하십시오." + NL + NL + user)
        if cart:
            user = f"[장바구니] {', '.join(cart)}{NL}{NL}" + user
        if history:
            recent = NL.join(f"  {i}. {h}" for i, h in
                             enumerate(history[-6:], max(1, len(history) - 5)))
            user = f"[지금까지 한 행동]{NL}{recent}{NL}{NL}{user}"
            # 연속으로 스크롤만 하고 있으면 대놓고 지적한다
            if len(history) >= 3 and all(h.startswith("scroll") for h in history[-3:]):
                user = ("[주의] 스크롤을 세 번 연속 했습니다. **이번에는 상품을 하나 고르거나"
                        " 목록 끝이면 leave 하십시오.**" + NL + NL + user)
        obj, used = ask(client, system, user, cache_on, dry)
        calls += used
        if obj is None:
            failed += 1
            if verbose:
                print(f"    {turn:>2}. (응답 형식 깨짐 — 건너뜀)")
            continue
        act, tgt = obj["action"], obj.get("target")

        if act == "leave":
            if verbose:
                print(f"    {turn:>2}. leave — {obj.get('reason')}")
            break

        try:
            okd = do_action(page, act, tgt)
        except Exception as e:            # 셀렉터가 바뀌었거나 화면이 예상 밖일 때
            okd = False
            if verbose:
                print(f"       [조작 실패] {type(e).__name__}: {str(e)[:70]}")
        history.append(f"{act}" + (f" → {tgt}" if tgt else "")
                       + ("" if okd else "  (실패)"))
        if okd and act == "click_product" and tgt:
            short = " ".join(str(tgt).split()[:4])
            if short not in visited:
                visited.append(short)
        if okd and act == "add_to_cart":
            nm = " ".join(str(tgt).split()[:4]) if tgt else (visited[-1] if visited else "?")
            if nm not in cart:
                cart.append(nm)
        done += okd
        failed += (not okd)
        if okd and act == "add_to_cart":
            carted += 1
        if verbose:
            mark = "  " if okd else "! "
            print(f"    {turn:>2}.{mark}{act:<14} {str(tgt)[:30]:<32} {obj.get('reason','')[:40]}")
        if dry:
            break                                # 프롬프트 확인용이므로 한 턴만
    return dict(calls=calls, done=done, failed=failed, carted=carted)


# ============================================================================
# 6. 메인
# ============================================================================

def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173", help="프론트 주소")
    ap.add_argument("--limit", type=int, default=3, help="돌릴 페르소나 수")
    ap.add_argument("--turns", type=int, default=25, help="1인당 최대 턴")
    ap.add_argument("--headed", action="store_true", help="브라우저를 띄워서 본다")
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 프롬프트만 (0 크레딧)")
    ap.add_argument("--cache", action="store_true", help="같은 화면이면 저장된 응답 재사용")
    ap.add_argument("--openai", action="store_true",
                    help="GMS 대신 개인 OpenAI 키를 쓴다 (OPENAI_API_KEY 환경변수)")
    ap.add_argument("--model", default=None, help=f"모델 (기본 {MODEL})")
    ap.add_argument("--out", default=os.path.join(BD, "data", "agent_events.jsonl"),
                    help="가로챈 행동 로그를 적을 파일")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.model:
        MODEL = a.model

    client = None
    if not a.dry_run:
        from openai import OpenAI
        if a.openai:
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                print("OPENAI_API_KEY 환경변수가 없습니다.  set OPENAI_API_KEY=sk-...")
                raise SystemExit(1)
            client = OpenAI(api_key=key)          # 기본 엔드포인트 = api.openai.com
        else:
            key = os.environ.get("GMS_KEY")
            if not key:
                print("GMS_KEY 환경변수가 없습니다.  set GMS_KEY=...")
                raise SystemExit(1)
            client = OpenAI(base_url=GMS_BASE, api_key=key)

    personas = json.load(open(PERSONA_FILE, encoding="utf-8"))[:a.limit]
    print(f"페르소나 {len(personas)}명 · 모델 {MODEL} · 최대 {a.turns}턴"
          + ("  [dry-run]" if a.dry_run else ""))
    print(f"프론트 {a.url}")

    from playwright.sync_api import sync_playwright
    tot = dict(calls=0, done=0, failed=0, carted=0)
    t0 = time.time()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sink = LogSink(a.out)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        for p in personas:
            ctx = browser.new_context()          # 페르소나마다 새 세션
            sink.attach(ctx)                     # 백엔드 없이도 로그를 건진다
            page = ctx.new_page()
            page.goto(a.url, wait_until="networkidle")

            if not switch_persona(page, p["persona_id"]):
                print(f"  {p['persona_id']}  페르소나 전환 실패 — 건너뜀")
                ctx.close()
                continue

            print(f"  {p['persona_id']}  {TYPE_KR.get(p['skin_type'], '')}/"
                  f"{p['skin_tone']}  구매 {p['n_products']}개")
            r = run_one(page, client, p, a.turns, a.cache, a.dry_run, not a.quiet)
            for k in tot:
                tot[k] += r[k]
            page.wait_for_timeout(1200)       # 남은 배치가 flush 될 시간을 준다
            ctx.close()
        browser.close()
    sink.close()

    dt = time.time() - t0
    print()
    print("=" * 60)
    print(f"  실행 {tot['done']}건 / 실패 {tot['failed']}건 / 장바구니 {tot['carted']}건")
    print(f"  LLM 호출 {tot['calls']}회 · {dt:.0f}초")
    if tot["calls"]:
        print(f"  예상 크레딧 약 {tot['calls'] * 0.6:.0f}"
              f"  (100명 환산 {tot['calls'] * 0.6 / max(len(personas),1) * 100:,.0f})")
    top = sorted(sink.kinds.items(), key=lambda x: -x[1])[:8]
    print(f"  수집 로그 {sink.n}건 -> {a.out}")
    if top:
        print("  " + " · ".join(f"{k} {v}" for k, v in top))
    print("=" * 60)


# ============================================================================
# 6. 행동 로그 가로채기
# ============================================================================

class LogSink:
    """프론트가 /api/events 로 보내는 행동 로그를 가로채 파일로 남긴다.

    프론트는 sendBeacon/fetch 로 백엔드에 로그를 보낸다. 백엔드가 안 떠 있으면
    그 요청은 그대로 실패하고 **로그가 통째로 사라진다** — 에이전트를 25턴씩
    돌려놓고 아무것도 못 건지는 사고가 여기서 난다.
    그래서 백엔드에 의존하지 않고 Playwright 가 요청을 가로채 직접 적는다.
    응답은 200 으로 돌려줘야 프론트가 재전송 큐에 쌓지 않는다.
    """

    def __init__(self, path):
        self.path = path
        self.f = io.open(path, "w", encoding="utf-8")
        self.n = 0
        self.kinds = {}

    def attach(self, ctx):
        ctx.route("**/api/events", self._handle)

    def _handle(self, route, request):
        try:
            payload = json.loads(request.post_data or "{}")
            for ev in payload.get("events", []):
                self.f.write(json.dumps(ev, ensure_ascii=False) + NL)
                self.n += 1
                k = ev.get("event_name") or ev.get("action") or "?"
                self.kinds[k] = self.kinds.get(k, 0) + 1
        except Exception:
            pass
        route.fulfill(status=200, content_type="application/json",
                      body='{"ok":true}')

    def close(self):
        self.f.close()


def switch_persona(page, persona_id):
    """드롭다운을 열고 해당 페르소나를 고른다. 이후 모든 로그의 persona_id 가 된다"""
    try:
        page.locator('[data-log-action="persona_switcher_open"]').first.click()
        page.wait_for_timeout(500)
        item = page.get_by_text(persona_id, exact=False).first
        item.click()
        page.wait_for_timeout(900)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
