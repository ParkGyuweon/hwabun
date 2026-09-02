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

    키는 레포 루트 .env 에 둔다 (.gitignore 에 있어 커밋되지 않는다):
        GMS_KEY=...
        OPENAI_API_KEY=...      (--openai 로 개인 키를 쓸 때만)
    환경변수로 줘도 된다 — 환경변수가 .env 보다 우선한다.

실행
    python simulator/agents/agent_runner.py --dry-run --limit 1     # 프롬프트만 확인
    python simulator/agents/agent_runner.py --limit 1 --entry list         --script quick_look,click_product,wishlist_toggle,add_to_cart,back_to_list
                                                                    # 대본 리허설 (0 크레딧)
    python simulator/agents/agent_runner.py --limit 3 --headed      # 3명, 브라우저 보이게
    python simulator/agents/agent_runner.py --limit 100             # 전원 배치
    python simulator/agents/agent_runner.py --limit 100 --post http://localhost:8080

로그에 synthetic 표시를 붙이는 곳
    프론트 로거는 에이전트를 실사용자와 구분하지 못한다(브라우저로 조작하므로).
    그래서 LogSink 가 가로챈 봉투에 actor_type 과 실행 메타데이터 3종을 채운 뒤
    파일로 남기고, --post 를 주면 수집 API 로 대신 보낸다.
    계약이 정한 강제 지점이 Simulator 와 Spark 이라 프론트는 고치지 않는다.
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
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
PERSONA_FILE = os.path.join(ROOT, "simulator", "personas", "data",
                            "personas_100_agent.json")
CACHE_DIR = os.path.join(BD, ".cache")
PRODUCTS_FILE = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")

# ── 카탈로그 커버리지 ─────────────────────────────────────
# 100명이 200개 중 38개만 만졌다(19%). 원인은 취향이 아니라 화면 구조다.
#   * 목록은 25개씩 끊어 보여주고 나머지는 "더 보기" 버튼 뒤에 있다
#   * 100명 전원이 같은 첫 화면에서 시작하니 보이는 후보가 늘 같은 25개다
# 프롬프트로 "더 내려보라" 고 부탁하지 않고 코드로 시작 지점을 흩는다.
DEEP_LINK_P = 0.5       # 이 확률로 상품 상세에서 시작한다 (검색·광고 유입에 해당)
CATEGORY_P = 0.6        # 목록에서 시작할 때 이 확률로 카테고리 탭을 하나 고른다
MAX_MORE_CLICKS = 3     # "더 보기" 한도. 25 -> 최대 100개까지 늘린다

GMS_BASE = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
MODEL = "gpt-4.1-nano"          # 실측 5/5 통과. 1회 0.6 크레딧

# 에이전트가 쓸 수 있는 행동. 여기 없는 것을 답하면 그 턴은 버린다.
ACTIONS = ("click_product", "scroll", "quick_look", "add_to_cart",
           "wishlist_toggle", "remove_from_cart", "back_to_list", "leave")

# 행동을 세 개 더 연 이유
#   5개(click_product/scroll/add_to_cart/back_to_list/leave)만으로는 프론트가 정의한
#   이벤트 36종 중 상당수가 **구조적으로 생성 불가능**했다. 특히 v_u- 의 입력인
#   찜 해제·장바구니 제거가 아예 안 나왔다.
#   quick_look     목록에서 상세로 안 가고 요약만 열어보는 동선 (관심은 있으나 약함)
#   wishlist_toggle 담기 전 단계의 관심. 두 번 누르면 찜 해제 = 부정 신호
#   remove_from_cart 담았다 뺀 것. 조사 7-2 기준 상품 특정 부정 신호 중 가장 명확
#
# 다만 선택지를 늘리면 약한 모델이 그쪽으로 도망쳐 전환이 줄어든다(75턴 add_to_cart
# 0건 사고). 그래서 세 개 모두 **코드가 조건을 만족할 때만** 목록에 올린다.
QUICK_LOOK_MAX = 3      # 1인당 요약 열기 상한. 넘으면 상세로 들어가야 한다
CART_MIN_TO_REMOVE = 2  # 장바구니에 이만큼 있어야 빼는 선택지를 연다 (전환 0 방지)
MIN_DETAILS_BEFORE_LEAVE = 3   # 이만큼은 상세를 보고 나서야 나갈 수 있다

# 매 턴 화면 판정을 찍는다. 왜 그 행동이 열렸는지 못 밝힐 때만 켠다 (--debug-screen)
DEBUG_SCREEN = False

# 목록 화면 주소. 딥링크로 상세에 바로 들어온 사람은 **히스토리에 앞 페이지가 없어**
# go_back() 이 about:blank 로 간다. 그때 돌아갈 곳을 알고 있어야 복구가 된다
LIST_URL = None

# ── synthetic 실행 메타데이터 ────────────────────────────────────────────────
# 에이전트는 실제 브라우저로 프론트를 조작하므로, 아무 표시도 하지 않으면 프론트
# 로거가 실사용자와 똑같이 actor_type='user' 로 남긴다.
#
# 진입 주소에 표시를 붙이면 **프론트 로거가 그것을 읽어 봉투에 싣는다**
# (frontend/src/lib/logger.ts syntheticContextFromUrl). 그래서 평상시 LogSink 의
# 보정은 0 이고, 프론트가 표시를 못 붙인 경우에만 채운다.
# 실측: stamped 0 / already 120.
#
# LogSink 를 남겨 두는 이유는 프론트가 파라미터를 못 읽는 경우(배포 빌드,
# 파라미터 누락)에도 로그를 건지기 위해서다. 계약이 정한 강제 지점도
# Simulator + Spark 다.
# 계약: docs/analytics/log-transport-contract.md §9
#
# 이름은 gen_behavior_logs.py 와 맞춘다 — 두 생성기의 로그가 같은 Mart 에 들어간다.
# 시나리오는 배치와 같은 값을 쓰고, 배치(python_batch)와 에이전트는
# generator_type 으로 가른다 (contracts/dw-schema.md).
DEFAULT_SCENARIO_ID = "normal_day"
# 계약 enum 은 python_batch | agent_llm 이다 (contracts/event-schema.json).
# agent_realtime 은 legacy 로 명시적으로 거절된다 (contracts/tests/test_validate_events.py)
GENERATOR_TYPE = "agent_llm"

# 봉투에 schema_version 이 없을 때만 쓰는 값. 평소에는 프론트가 보낸 값을 그대로 쓴다
SCHEMA_VERSION = "0.2.0-draft"
# 수집 API 한 요청의 최대 건수. 백엔드 EventBatchRequest 의 @Size(max = 100)
POST_BATCH = 100


def default_simulation_run_id(now=None):
    """실행 ID 를 안 주면 시각으로 만든다. 배치 생성기와 같은 형식"""
    ts = now or datetime.now(timezone.utc)
    return f"run_{ts.strftime('%Y%m%dT%H%M%SZ')}"


def entry_url(base, scenario_id, simulation_run_id, product_id=None):
    """프론트 진입 주소에 synthetic 표시를 붙인다.

    프론트 로거는 **개발 서버에서만** 이 파라미터를 인정한다. 배포 화면에서도
    받아주면 주소만 고쳐 아무나 로그 출처를 위장할 수 있기 때문이다.
    (frontend/src/lib/logger.ts syntheticContextFromUrl)

    셋 중 하나라도 빠지면 로거가 user 로 되돌리므로 항상 함께 붙인다.
    """
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({
        "actor": "synthetic",
        "gen": GENERATOR_TYPE,
        "run": simulation_run_id,
        "scenario": scenario_id,
    })
    if product_id:
        # 프론트가 이미 지원하는 진입 경로다 (App.tsx initialProductId).
        # 검색·광고로 상세에 바로 떨어지는 실제 유입에 해당한다
        query["product"] = product_id
    return urlunsplit(parts._replace(query=urlencode(query)))


def load_dotenv(path=None):
    """레포 루트 .env 에서 키를 읽어 환경변수에 얹는다.

    의존성을 늘리지 않으려고 직접 읽는다 (python-dotenv 없이 동작해야 팀원이
    받자마자 돌릴 수 있다). **이미 환경변수에 있으면 덮지 않는다** — CI 나 일회성
    실행에서 준 값이 파일보다 우선이어야 한다.
    """
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:                      # 키가 없다고 러너가 죽으면 안 된다
        print(f"  .env 를 읽지 못했습니다 ({exc}) — 환경변수로 주십시오")


def load_catalog():
    """딥링크로 보낼 상품 ID 목록. 프론트 목록과 같은 200개다"""
    try:
        with io.open(PRODUCTS_FILE, encoding="utf-8") as f:
            return [p["product_id"] for p in json.load(f) if p.get("product_id")]
    except Exception:
        return []


def spread_start(page, rng):
    """목록에서 시작하는 사람의 출발 지점을 흩는다.

    100명 전원이 같은 첫 화면(25개)에서 시작하면 그 25개만 후보가 된다.
    카테고리 탭을 고르고, "더 보기" 로 목록을 늘리고, 시작 스크롤 위치를 옮긴다.
    전부 화면에 실제로 있는 조작이라 로그도 실제 사용자와 같은 모양으로 남는다.

    스크롤은 한 번에 뛰지 않고 여러 번에 나눠 내린다. 한 번에 뛰면 프론트의
    scroll_depth 25/50/75 단계가 통째로 건너뛰어져 로그가 사람 같지 않다.
    """
    tabs = page.locator(".list__tabs button")
    if not tabs.count():
        return None                      # 목록 화면이 아니다 (상세로 바로 들어옴)

    picked = None
    if rng.random() < CATEGORY_P:
        i = rng.randrange(tabs.count())
        try:
            picked = tabs.nth(i).inner_text(timeout=1500).split(NL)[0].strip()
            tabs.nth(i).click(timeout=3000)
            page.wait_for_timeout(700)
        except Exception:
            picked = None

    for _ in range(rng.randint(0, MAX_MORE_CLICKS)):
        more = page.locator(".list__more")
        if not more.count():
            break
        try:
            more.first.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            break

    height = page.evaluate("() => document.body.scrollHeight")
    view = page.evaluate("() => window.innerHeight")
    # 0.75 까지 내렸더니 첫 화면부터 "목록 끝" 이 떠서 곧장 leave 하는 사고가 났다
    # (실측: 9명 중 6명이 2~5턴 만에 종료). 바닥 근처에서 시작하지 않게 한다
    target = int(max(0, height - view) * rng.uniform(0, 0.55))
    while page.evaluate("() => window.scrollY") + 40 < target:
        page.mouse.wheel(0, rng.randint(500, 900))
        page.wait_for_timeout(rng.randint(180, 420))
    return picked

NL = "\n"
PCT_RE = "([0-9]+)[ ]*%"   # "스크롤 62%" 에서 숫자만 뽑는다


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


SYSTEM_TMPL = """당신은 화장품 쇼핑몰에서 실제로 구매를 고민하는 사람입니다.

오늘 목표는 관심 있는 스킨케어 제품을 살펴보고, 마음에 드는 제품이 있으면
장바구니에 담는 것입니다. 반드시 사야 하는 것은 아니지만, 충분히 살펴본
상품은 계속 미루지 말고 담거나 목록으로 돌아가야 합니다.

[당신이 누구인가]
{profile}

[행동 기준]
- 목록에서는 **아직 보지 않은 상품 중** 내 피부 타입, 피부 톤, 구매 이력,
  가격대에 가장 맞는 상품을 하나 고르십시오.
- 이미 본 상품은 다시 누르지 말고 다른 후보를 고르십시오.
- 불만이었던 상품과 비슷한 것은 피하십시오.
- 상세 페이지에서는 처음에는 필요한 정보를 더 읽어볼 수 있습니다.
- 상세 페이지를 충분히 봤다면 계속 스크롤하지 말고 add_to_cart 또는
  back_to_list 중 하나를 고르십시오.
- 마음에 드는 정도가 보통 이상이면 add_to_cart 를 고르십시오.
- 맞지 않거나 이미 충분히 봤다면 back_to_list 를 고르십시오.
- 목록 끝에 도달했고 더 관심 가는 상품이 없으면 leave 를 고르십시오.
- 궁금하지만 상세까지 볼 정도는 아니면 quick_look 으로 요약만 열어보십시오.
- 상세에서 마음에 들지만 지금 사기는 망설여지면 wishlist_toggle 로 찜하십시오.
  이미 찜한 상품이 마음에서 멀어졌으면 다시 눌러 해제하십시오.
- 장바구니에 담아둔 것 중 다시 보니 아닌 것이 있으면 remove_from_cart 로 빼십시오.

[답변 형식]
JSON 만 출력하십시오. 설명이나 코드블록을 붙이지 마십시오.
action 은 **이번 턴에 고를 수 있는 행동**으로 제시된 것 중에서만 고르십시오.

{{"action": {actions},
 "target": "화면에 실제로 있는 상품명 (해당 없으면 null)",
 "reason": "내 프로필과 연결된 구체적인 한 문장"}}"""


# ============================================================================
# 2. 화면 -> 텍스트
# ============================================================================

def screen_is_broken(page):
    """화면이 죽었는가 — 카드도 없고 담기 버튼도 없다.

    빈 화면에서는 어떤 조작도 성공하지 못하므로 에이전트가 남은 턴을 전부 버린다.

    원래 잡으려던 것은 AboutProduct.tsx 가 `highlighted_ingredients` 없는 상품에서
    던지던 크래시였다 (202개 중 78개). **2026-09-02 프론트가 옵셔널 체이닝으로
    고쳐 dev 에 들어갔다.** 그래도 이 판정은 남긴다 — 화면이 비는 이유가 그것
    하나뿐이라는 보장이 없고, 비었는데 계속 조작하면 로그가 조용히 망가진다.
    """
    try:
        return (not page.locator(".card[data-product-id]").count()
                and not page.locator('[data-log-action="add_to_cart"]').count())
    except Exception:
        return False


def recover_screen(page):
    """목록으로 되돌려 세션을 살린다. 돌아갈 곳을 모르면 아무것도 하지 않는다"""
    if not LIST_URL:
        return False
    page.goto(LIST_URL, wait_until="networkidle")
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(900)
    return True


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
    # 바닥이어도 "더 보기" 가 남아 있으면 목록 끝이 아니다. 끝이라고 말하면
    # LLM 이 leave 를 고르고, 26번째 상품부터는 아무도 보지 못한다
    more = page.locator(".list__more").count() > 0
    if pct >= 97:
        tail = "  ← 목록 끝입니다" if not more else "  ← 더 내리면 상품이 더 나옵니다"
    else:
        tail = ""
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

class LocalLLM:
    """로컬 GPU 에 올린 오픈 모델. GMS 크레딧을 쓰지 않는다.

    100명 x 15턴이 약 900 크레딧이라 반복 실행이 부담이다. 러너가 모델에 요구하는
    것은 "허용된 행동 중 하나 + 상품명 + 한 줄 이유" 를 JSON 으로 뱉는 것뿐이라,
    작은 모델로도 되는지 먼저 확인하고 쓴다.

    서버를 따로 띄우지 않고 프로세스 안에서 돌린다. 대신 --workers 로 여러 개를
    띄우면 워커마다 모델을 올려 VRAM 이 그만큼 곱해진다 (8GB 에서는 1개만).
    """

    def __init__(self, model_id, device=None, max_new_tokens=160):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_new_tokens = max_new_tokens
        print(f"로컬 모델 {model_id} 를 {self.device} 에 올립니다...")
        t0 = time.time()
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.float16 if self.device == "cuda" else None)
        self.model.to(self.device).eval()
        print(f"  준비 {time.time() - t0:.1f}초")

    def chat(self, system, user):
        import torch
        prompt = self.tok.apply_chat_template(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        # JSON 만 뱉게 첫 글자를 미리 넣어 준다. 작은 모델은 서두를 붙이는 버릇이 있다
        prompt += '{"action": "'
        ids = self.tok(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(
                **ids, max_new_tokens=self.max_new_tokens, do_sample=True,
                temperature=0.9, top_p=0.9, pad_token_id=self.tok.eos_token_id)
        text = self.tok.decode(out[0][ids["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        return '{"action": "' + text


class ScriptedLLM:
    """정해진 순서를 돌려주는 가짜 LLM. 크레딧 0 으로 배선을 검증한다.

    행동을 새로 열 때 그것이 **실제 DOM 조작과 로그로 이어지는지**는 프롬프트를
    아무리 다듬어도 알 수 없다. 모델을 부르는 대신 순서를 강제해서, 브라우저와
    프론트 로거는 진짜인 채로 나머지 배선을 전부 확인한다.

    target 은 화면에서 고른다 — LLM 이 지어낸 이름을 흉내 내면 매칭 실패까지
    같이 재현돼 무엇을 검증하는지 흐려진다.
    """

    def __init__(self, plan):
        self.plan = list(plan)
        self.i = 0

    def next_action(self, page, acts, here, cart, visited, peeked=()):
        while self.i < len(self.plan):
            act = self.plan[self.i]
            self.i += 1
            if act not in acts:
                print(f"       [대본 {act} 은 이번 턴에 허용되지 않음 — 건너뜀]")
                continue
            target = None
            if act == "click_product":
                target = first_unvisited(page, visited)
                if target is None:
                    continue
            elif act == "quick_look":
                # 요약을 이미 열어본 카드는 다시 고르지 않는다
                target = first_unvisited(page, list(visited) + list(peeked))
                if target is None:
                    continue
            elif act in ("add_to_cart", "wishlist_toggle"):
                target = here
            elif act == "remove_from_cart":
                target = cart[-1] if cart else None
            return {"action": act, "target": target, "reason": "(대본)"}
        return {"action": "leave", "target": None, "reason": "(대본 끝)"}


def parse_action(text):
    """모델 응답에서 JSON 하나를 건진다. 앞뒤에 말을 붙여도 중괄호만 떼어 쓴다"""
    lo, hi = text.find("{"), text.rfind("}")
    if lo < 0 or hi <= lo:
        return None
    try:
        obj = json.loads(text[lo:hi + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and obj.get("action") else None


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


def find_card(page, target):
    """LLM 이 말한 이름과 맞는 목록 카드를 찾는다. 없으면 None

    이름을 줄여 쓰는 경우가 많아 부분 일치까지 허용한다. 못 찾으면 첫 카드로
    대충 누르지 않는다 — 고른 적 없는 클릭이 로그에 남으면 수집 자체를 못 믿는다.
    """
    cards = page.locator(".card[data-product-id]")
    want = norm(target)
    if not want:
        return None
    for i in range(cards.count()):
        card = cards.nth(i)
        try:
            name = norm(card.locator(".card__name").inner_text(timeout=1000))
        except Exception:
            continue
        if want in name or name in want or want[:14] in name:
            return card
    return None


def do_action(page, act, target):
    """LLM 이 고른 행동을 실제 DOM 조작으로 옮긴다. 성공하면 True"""
    a = act

    if a == "scroll":
        # 바닥에 닿았으면 위로 올린다. 아래로만 굴리면 화면이 안 바뀌어
        # "볼 것이 없다" 로 읽히고, 실제로 위쪽에 안 본 상품이 남아 있다
        at_bottom = page.evaluate(
            "() => window.scrollY + window.innerHeight"
            " >= document.body.scrollHeight - 40")
        step = random.randint(500, 1200)
        page.mouse.wheel(0, -step if at_bottom else step)
        page.wait_for_timeout(random.randint(700, 2500))
        # 목록 바닥에 닿았고 "더 보기" 가 보이면 눌러 준다. 사람은 더 볼 게
        # 있으면 누른다. LLM 의 선택지로 두지 않는 이유는, 행동을 하나 더 늘리면
        # 약한 모델이 그쪽으로 도망쳐 상품을 안 고르기 때문이다
        more = page.locator(".list__more")
        if more.count():
            try:
                more.first.scroll_into_view_if_needed(timeout=1500)
                more.first.click(timeout=2500)
                page.wait_for_timeout(600)
            except Exception:
                pass
        return True

    if a == "back_to_list":
        page.go_back()
        page.wait_for_timeout(1200)
        # 딥링크로 상세에 바로 들어온 사람은 **돌아갈 목록이 없다.** go_back() 이
        # about:blank 로 가고, 그 빈 화면을 "다 봤다" 로 읽어 곧장 나간다
        # (실측: 5명 중 3명이 상세를 한 개도 못 열고 종료).
        # 그래서 목록 주소를 미리 기억해 두고 그리로 이동해 복구한다
        if (page.url.startswith("about:")
                or not page.locator(".card[data-product-id]").count()):
            page.goto(LIST_URL or page.url, wait_until="networkidle")
            page.evaluate("() => window.scrollTo(0, 0)")   # 복구는 목록 맨 위에서
            page.wait_for_timeout(900)
        return True

    if a == "add_to_cart":
        btn = page.locator('[data-log-action="add_to_cart"]')
        if not btn.count():
            return False                         # 목록 화면에서는 담을 수 없다
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(900)
        return True

    if a == "quick_look":
        # 카드에 마우스를 올려야 버튼이 뜬다. 사람이 하는 순서 그대로 간다
        card = find_card(page, target)
        if card is None:
            return False
        try:
            card.hover(timeout=2000)
        except Exception:
            pass
        btn = card.locator(".card__quicklook")
        if not btn.count() or not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(random.randint(900, 2200))   # 요약을 읽는 시간
        # 열었으면 닫는다. 닫는 것까지가 한 동선이라 quick_look_close 가 남는다
        close = page.locator('.qlook__close[data-log-action="quick_look_close"]')
        if close.count():
            click_safe(close.first, page)
            page.wait_for_timeout(500)
        return True

    if a == "wishlist_toggle":
        btn = page.locator('[data-log-action="wishlist_toggle"]')
        if not btn.count():
            return False                         # 목록 화면에는 없다
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(600)
        return True

    if a == "remove_from_cart":
        # 장바구니를 열고 -> 빼고 -> 돌아온다. 한 동선이라 코드가 묶어서 실행한다.
        # 사람도 "빼려고" 장바구니를 열지, 열어놓고 고민하지 않는다
        basket = page.locator('[data-log-action="view_cart"]')
        if not basket.count() or not click_safe(basket.first, page):
            return False
        page.wait_for_timeout(1000)
        rows = page.locator('[data-log-action="remove_from_cart"]')
        if not rows.count():
            page.go_back()
            page.wait_for_timeout(800)
            return False
        want = norm(target)
        pick = rows.first
        if want:                                 # 지목한 상품이 있으면 그것을 뺀다
            for i in range(rows.count()):
                row = rows.nth(i)
                try:
                    text = norm(row.locator("xpath=ancestor::li[1]").inner_text(timeout=800))
                except Exception:
                    continue
                if want[:14] and want[:14] in text:
                    pick = row
                    break
        ok = click_safe(pick, page)
        page.wait_for_timeout(700)
        page.go_back()                           # 보던 화면으로 돌아간다
        page.wait_for_timeout(900)
        return ok

    if a == "click_product":
        card = find_card(page, target)
        if card is None:
            return False                         # 화면에 없는 상품을 지어냈다
        if not click_safe(card.locator(".card__link").first, page):
            return False
        page.wait_for_timeout(1400)
        return True

    return False


# ============================================================================
# 5. 한 명 돌리기
# ============================================================================

DETAIL_MAX_SCROLL = 2      # 상세에서 이만큼 내렸으면 결정해야 한다


def first_unvisited(page, visited):
    """목록 화면에서 아직 안 본 상품 이름을 하나 돌려준다. 없으면 None.

    LLM 이 화면에 없는 상품을 지어냈을 때 쓰는 fallback 이다.
    '목록 첫 상품'을 무조건 누르면 그 사람이 고른 적 없는 클릭이 로그에
    남으므로, 최소한 '아직 안 본 상품'이라는 근거는 있어야 한다.
    """
    seen = {norm(v) for v in visited}
    cards = page.locator(".card[data-product-id]")
    for i in range(min(cards.count(), 40)):
        c = cards.nth(i)
        try:
            if not c.is_visible():
                continue
            brand = c.locator(".card__brand").inner_text(timeout=800).strip()
            name = c.locator(".card__name").inner_text(timeout=800).strip()
        except Exception:
            continue
        full = f"{brand} {name}"
        if not any(norm(full) in v or v in norm(full) for v in seen if v):
            return full
    return None


def has_unvisited_in_list(page, visited):
    """목록에 아직 안 본 상품이 남아 있는가.

    **화면에 보이는 카드만 보면 안 된다.** back_to_list 로 돌아오면 스크롤이
    복원되는데, 그 자리에 안 본 카드가 안 보이면 "다 봤다" 로 판정돼 첫 턴부터
    leave 가 열린다 (실측: 5명 중 5명이 2~3턴에 종료). 스크롤하거나 "더 보기" 를
    누르면 닿을 수 있는 것까지 세야 한다.
    """
    if page.locator(".list__more").count():
        return True                              # 아직 안 불러온 상품이 남아 있다
    seen = {norm(v) for v in visited if norm(v)}
    cards = page.locator(".card[data-product-id]")
    if not cards.count():
        # 화면이 비어 있는 것은 "다 봤다" 가 아니라 화면이 이상한 것이다.
        # 여기서 True 를 돌려줘야 leave 가 안 열리고 다음 턴에 복구할 기회가 생긴다
        return True
    for i in range(min(cards.count(), 120)):
        try:
            name = norm(cards.nth(i).locator(".card__name").inner_text(timeout=600))
        except Exception:
            continue
        if name and not any(name in v or v in name for v in seen):
            return True
    return False


def allowed_actions(kind, pct, scroll_run, carted_here, has_more=False,
                    wished_here=False, quick_looks=0, cart_size=0,
                    n_details=0, has_unvisited=True):
    """이번 턴에 실제로 의미가 있는 행동만 남긴다.

    행동 다섯 개를 매 턴 전부 열어주면 약한 모델은 가장 안전한 scroll 로
    도망친다. 실제로 75턴 동안 add_to_cart 가 0건이었다 — 전환이 0이면
    v_u+ 가 비어서 취향 벡터를 만들 수 없다.
    그래서 프롬프트로 부탁하지 않고 코드가 선택지를 좁힌다.
    """
    if kind == "detail":
        acts = ["back_to_list"]
        if not carted_here:
            acts.insert(0, "add_to_cart")     # 담기를 맨 앞에 둔다
        if scroll_run < DETAIL_MAX_SCROLL:    # 다 읽었으면 더는 못 내린다
            acts.append("scroll")
        # 찜은 상품당 한 번만 연다. 계속 열어두면 담기 대신 찜만 반복한다
        if not wished_here:
            acts.append("wishlist_toggle")
        return acts
    # 목록 화면: 끝까지 내려왔고 더 불러올 것도 없으면 scroll 은 무의미하다.
    # 다만 "더 보기" 가 남아 있으면 바닥이어도 내릴 값어치가 있다 (scroll 이
    # 더 보기를 눌러 26번째 상품부터를 화면에 올린다)
    acts = ["click_product"]
    # 목록에서는 스크롤을 늘 연다. 바닥에 닿으면 do_action 이 위로 올리므로
    # "바닥이라 볼 것이 없다" 로 갇히지 않는다. 연속 스크롤은 프롬프트가 지적한다
    acts.append("scroll")
    if quick_looks < QUICK_LOOK_MAX:
        acts.append("quick_look")
    # 담은 것이 하나뿐일 때 빼기를 열면 전환이 0 으로 돌아갈 수 있다
    if cart_size >= CART_MIN_TO_REMOVE:
        acts.append("remove_from_cart")
    # **leave 를 일찍 열지 않는다.** 시작 위치를 흩으면서 목록 아래쪽에서 출발하는
    # 사람이 생겼는데, 화면에 "목록 끝" 이 보이면 첫 턴부터 나가버렸다.
    # 상세를 몇 개는 보고 나서, 그리고 화면에 새 상품이 없을 때만 나갈 수 있다
    if n_details >= MIN_DETAILS_BEFORE_LEAVE or not has_unvisited:
        acts.append("leave")
    return acts


def detail_title(user):
    """상세 화면 프롬프트에서 상품명 줄만 뽑는다"""
    parts = user.split(NL + NL)
    if len(parts) > 1:
        return parts[1].split(" — ")[0].strip()
    return ""


class DecisionLog:
    """LLM 의 판단 근거를 별도 파일로 남긴다.

    왜 이벤트에 안 넣는가 — 이벤트는 계약(36종)이고 property 도 계약이 정한 것만
    쓴다. `reason` 은 거기에 없다. 그렇다고 콘솔에만 찍으면 실행이 끝나는 순간
    사라진다 (8/31 GMS 100명 실행의 근거 문장이 그렇게 사라졌다).

    이벤트 로그와는 `persona_id` + `simulation_run_id` + 시각으로 붙는다.
    정성 검증 축의 근거이고, 발표에서 실제 문장을 인용할 때 쓴다.
    """

    def __init__(self, path, run_id, model):
        self.path = path
        self.run_id = run_id
        self.model = model
        self.n = 0
        self.f = None
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self.f = open(path, "w", encoding="utf-8", newline="\n")

    def write(self, persona_id, turn, screen, allowed, obj, act, tgt, ok):
        if self.f is None:
            return
        self.f.write(json.dumps({
            "simulation_run_id": self.run_id,
            "model": self.model,
            "persona_id": persona_id,
            "turn": turn,
            "decided_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                          .replace("+00:00", "Z"),
            "screen": screen,
            "allowed": allowed,
            # 모델이 뭐라고 했는가
            "llm_action": (obj or {}).get("action"),
            "llm_target": (obj or {}).get("target"),
            "reason": (obj or {}).get("reason"),
            # 코드가 무엇으로 바꿨는가. 둘이 다르면 교정된 턴이다
            "action": act,
            "target": tgt,
            "corrected": bool(obj) and (obj.get("action") != act),
            "succeeded": bool(ok),
        }, ensure_ascii=False) + "\n")
        self.n += 1

    def close(self):
        if self.f is not None:
            self.f.close()


def run_one(page, client, persona, max_turns, cache_on, dry, verbose, script=None,
            decisions=None):
    system = SYSTEM_TMPL.format(profile=profile_text(persona),
                                actions=" | ".join(f'"{a}"' for a in ACTIONS))
    calls, done, failed, carted = 0, 0, 0, 0

    history = []          # 최근 행동. 없으면 LLM 이 같은 판단을 무한 반복한다
    visited, cart = [], []   # 이미 본 상품 / 담은 상품
    wished = set()           # 찜한 상품. 상품당 한 번만 열어준다
    peeked = []              # 요약만 열어본 상품. 같은 카드를 다시 열지 않게 한다
    quick_looks = 0          # 요약 열어본 횟수. 상한을 넘으면 상세로 가야 한다
    scroll_run = 0           # 연속 스크롤 횟수. 상세에서 결정을 강제하는 데 쓴다
    here = ""                # 지금 상세를 보고 있는 상품
    broken = 0
    for turn in range(1, max_turns + 1):
        if screen_is_broken(page):
            # 화면이 죽었다. 목록으로 되돌리고 이 턴은 LLM 을 부르지 않는다
            broken += 1
            if verbose:
                print(f"    {turn:>2}. (화면이 비어 목록으로 복구)")
            if not recover_screen(page) or broken > 3:
                break
            continue
        user, kind = read_screen(page)
        m = re.search(PCT_RE, user)
        pct = int(m.group(1)) if m else 0
        if kind == "detail":
            here = detail_title(user) or here
            # 무엇을 봤는지는 LLM 이 말한 target 이 아니라 화면이 진실이다.
            # target 을 틀리게 쓰거나 빠뜨리면 중복 방지가 통째로 무력해진다
            if here and here not in visited:
                visited.append(here)
        # 이미 담은 상품을 또 담게 두면 같은 전환이 중복으로 쌓인다
        carted_here = any(norm(c) and (norm(c) in norm(here) or norm(here) in norm(c))
                          for c in cart)
        has_more = kind == "list" and page.locator(".list__more").count() > 0
        wished_here = any(norm(w) and (norm(w) in norm(here) or norm(here) in norm(w))
                          for w in wished)
        has_unvisited = kind != "list" or has_unvisited_in_list(page, visited)
        acts = allowed_actions(kind, pct, scroll_run, carted_here, has_more,
                               wished_here=wished_here, quick_looks=quick_looks,
                               cart_size=len(cart), n_details=len(visited),
                               has_unvisited=has_unvisited)
        user = (f"[이번 턴에 고를 수 있는 행동] {' | '.join(acts)}"
                f"{NL}이 중에서만 고르십시오." + NL + NL + user)
        if kind == "detail" and "scroll" not in acts:
            user = ("[결정하십시오] 이 상품을 충분히 봤습니다."
                    " 마음에 들면 add_to_cart, 아니면 back_to_list 입니다."
                    + NL + NL + user)
        # 본 상품과 담은 상품을 알려주지 않으면 같은 상품만 25턴 내내 반복한다.
        # (실제로 한 페르소나가 BELIF 두 개만 왕복한 사고가 있었다)
        if visited:
            user = (f"[이미 본 상품] {', '.join(visited[-8:])}"
                    f"{NL}이미 본 상품은 다시 누르지 말고 다른 상품을 고르십시오."
                    + NL + NL + user)
        if peeked:
            user = (f"[요약만 열어본 상품] {', '.join(peeked[-6:])}{NL}"
                    f"같은 상품을 또 열지 말고, 관심이 남았으면 상세로 들어가십시오."
                    f"{NL}{NL}") + user
        if wished:
            user = (f"[찜한 상품] {', '.join(sorted(wished))}{NL}"
                    f"이미 찜한 상품을 다시 누르면 찜이 해제됩니다.{NL}{NL}") + user
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
        if verbose and DEBUG_SCREEN:
            print(f"       [화면 {kind} · 스크롤 {pct}% · 상세 {len(visited)}개"
                  f" · 새 상품 {'있음' if has_unvisited else '없음'}"
                  f" · 선택지 {'/'.join(acts)}]")
        if script is not None:
            obj, used = script.next_action(page, acts, here, cart, visited, peeked), 0
        elif isinstance(client, LocalLLM):
            obj, used = parse_action(client.chat(system, user)), 0
        else:
            obj, used = ask(client, system, user, cache_on, dry)
        calls += used
        if obj is None:
            failed += 1
            if verbose:
                print(f"    {turn:>2}. (응답 형식 깨짐 — 건너뜀)")
            continue
        act, tgt = obj["action"], obj.get("target")
        if act not in acts:
            # 크레딧을 또 쓰지 않는다. 이번 턴은 허용된 첫 행동으로 대체한다.
            # 다만 click_product 로 교정할 때 target 을 그대로 두면,
            # LLM 이 지어낸 이름이 매칭에 실패해 엉뚱한 상품이 눌릴 수 있다.
            # 그 사람이 고른 적 없는 클릭이 로그에 남는 것은 수집 목적에 반한다
            new_act = acts[0]
            if new_act == "click_product":
                tgt = first_unvisited(page, visited)
                if tgt is None:                  # 누를 만한 새 상품이 없다
                    new_act = "leave" if "leave" in acts else acts[-1]
            elif new_act in ("add_to_cart", "wishlist_toggle"):
                tgt = here or tgt                # 화면이 진실이다
            elif new_act == "remove_from_cart":
                tgt = cart[-1] if cart else None
            else:
                tgt = None
            if verbose:
                print(f"       [허용 밖 {act} -> {new_act}]")
            act = new_act
            if act == "leave":
                if verbose:
                    print(f"    {turn:>2}. leave (목록에 새 상품 없음)")
                break

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
        scroll_run = scroll_run + 1 if act == "scroll" else 0
        history.append(f"{act}" + (f" → {tgt}" if tgt else "")
                       + ("" if okd else "  (실패)"))
        if okd and act == "add_to_cart":
            # 담은 것도 화면 기준. here 는 지금 보고 있는 상세 페이지의 상품이다
            nm = here or (" ".join(str(tgt).split()[:4]) if tgt else "")
            if nm and nm not in cart:
                cart.append(nm)
        if okd and act == "wishlist_toggle":
            # 같은 상품을 다시 누르면 해제다. 상태를 뒤집어 둬야 프롬프트가 맞는다
            nm = here or (str(tgt) if tgt else "")
            if nm:
                wished.discard(nm) if nm in wished else wished.add(nm)
        if okd and act == "quick_look":
            quick_looks += 1
            if tgt and tgt not in peeked:
                peeked.append(str(tgt))
        if okd and act == "remove_from_cart":
            gone = str(tgt) if tgt else (cart[-1] if cart else None)
            if gone in cart:
                cart.remove(gone)
        done += okd
        failed += (not okd)
        if okd and act == "add_to_cart":
            carted += 1
        if decisions is not None:
            decisions.write(persona["persona_id"], turn, kind, acts, obj, act, tgt, okd)
        if verbose:
            mark = "  " if okd else "! "
            print(f"    {turn:>2}.{mark}{act:<14} {str(tgt)[:30]:<32} {(obj.get('reason') or '')[:40]}")
        if dry:
            break                                # 프롬프트 확인용이므로 한 턴만
    return dict(calls=calls, done=done, failed=failed, carted=carted, broken=broken)


# ============================================================================
# 6. 메인
# ============================================================================


def run_parallel(a):
    """자기 자신을 --shard 로 여러 번 띄우고 로그를 합친다.

    Playwright 의 sync API 가 스레드 안전하지 않아 스레드가 아니라 프로세스로
    나눈다. 한 워커가 죽어도 나머지는 계속 돈다.
    """
    import subprocess
    n = min(a.workers, a.limit)
    base, ext = os.path.splitext(a.out)
    parts = [f"{base}.part{i}{ext}" for i in range(n)]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    # **실행 ID 를 부모가 정해 모든 샤드에 물려준다.** 샤드마다 만들면 한 번의
    # 실행이 워커 수만큼의 simulation_run_id 로 쪼개져 실행 단위 집계가 깨진다
    run_id = a.simulation_run_id or default_simulation_run_id()

    argv = [sys.executable, os.path.abspath(__file__),
            "--url", a.url, "--limit", str(a.limit), "--turns", str(a.turns),
            "--model", MODEL,
            "--scenario-id", a.scenario_id, "--simulation-run-id", run_id,
            "--entry", a.entry]
    for flag, on in (("--headed", a.headed), ("--dry-run", a.dry_run),
                     ("--openai", a.openai), ("--cache", a.cache),
                     ("--debug-screen", a.debug_screen)):
        if on:
            argv.append(flag)
    if a.api_base:                  # 자체 모델 서버 주소도 워커에 물려준다
        argv += ["--api-base", a.api_base]
    if a.decisions and a.decisions.lower() == "off":
        argv += ["--decisions", "off"]   # 경로는 샤드별 --out 에서 유도된다
    if a.post:                      # 안 넘기면 워커가 파일로만 쓰고 수집이 안 된다
        argv += ["--post", a.post, "--post-timeout", str(a.post_timeout)]
    if a.script:
        argv += ["--script", a.script]

    print(f"워커 {n}개로 나눠 실행합니다 (Playwright sync API 가 스레드 안전하지"
          f" 않아 프로세스로 분리)")
    print(f"  실행 ID {run_id} — 모든 워커가 같은 값을 씁니다")
    t0 = time.time()
    procs = []
    for i in range(n):
        cmd = argv + ["--shard", str(i), "--shards", str(n),
                      "--out", parts[i], "--quiet"]
        procs.append(subprocess.Popen(cmd))
    codes = [p.wait() for p in procs]
    dead = [i for i, c in enumerate(codes) if c != 0]

    # 로그 합치기 — 워커마다 따로 쓴 파일을 하나로 잇는다
    total = 0
    with io.open(a.out, "w", encoding="utf-8") as out:
        for p in parts:
            if not os.path.exists(p):
                continue
            with io.open(p, encoding="utf-8") as f:
                for line in f:
                    out.write(line)
                    total += 1
            os.remove(p)

    dt = time.time() - t0
    print()
    print("=" * 60)
    print(f"  워커 {n}개 · {dt:.0f}초 ({dt/60:.1f}분)")
    if dead:
        print(f"  실패한 워커 {len(dead)}개: {dead}  <- 그만큼 페르소나가 빠졌습니다")
    print(f"  수집 로그 {total:,}건 -> {a.out}")
    print("=" * 60)


def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173", help="프론트 주소")
    ap.add_argument("--limit", type=int, default=3, help="돌릴 페르소나 수")
    ap.add_argument("--turns", type=int, default=25, help="1인당 최대 턴")
    ap.add_argument("--headed", action="store_true", help="브라우저를 띄워서 본다")
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 프롬프트만 (0 크레딧)")
    ap.add_argument("--cache", action="store_true", help="같은 화면이면 저장된 응답 재사용")
    ap.add_argument("--local-model", default=None, metavar="HF_ID",
                    help="로컬 GPU 의 오픈 모델을 쓴다 (크레딧 0). "
                         "예) HuggingFaceTB/SmolLM2-1.7B-Instruct")
    ap.add_argument("--decisions",
                    help="LLM 판단 근거를 남길 jsonl 경로. 안 주면 --out 옆에"
                         " *_decisions.jsonl 로 만든다. 'off' 면 남기지 않는다")
    ap.add_argument("--api-base",
                    help="OpenAI 호환 자체 모델 서버 주소. 예) http://70.12.130.103:8501/v1"
                         " (GPU 서버에 model_server.py 를 띄워 두고 쓴다. 크레딧 0)")
    ap.add_argument("--openai", action="store_true",
                    help="GMS 대신 개인 OpenAI 키를 쓴다 (OPENAI_API_KEY 환경변수)")
    ap.add_argument("--model", default=None, help=f"모델 (기본 {MODEL})")
    ap.add_argument("--out", default=os.path.join(BD, "data", "agent_events.jsonl"),
                    help="가로챈 행동 로그를 적을 파일")
    ap.add_argument("--workers", type=int, default=1,
                    help="동시에 돌릴 프로세스 수. LLM 대기가 병목이라 그대로 빨라진다")
    ap.add_argument("--shard", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--shards", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--debug-screen", action="store_true",
                    help="매 턴 화면 판정과 선택지를 찍는다 (행동이 왜 열렸는지 볼 때)")
    ap.add_argument("--entry", choices=("auto", "list", "detail"), default="auto",
                    help="시작 화면을 고정한다. 기본 auto 는 페르소나마다 무작위 "
                         "(리허설에서 특정 동선을 재현할 때 쓴다)")
    ap.add_argument("--script", default=None,
                    help="LLM 대신 정해진 행동 순서를 실행한다 (크레딧 0). "
                         "예) click_product,wishlist_toggle,add_to_cart,back_to_list")
    ap.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID,
                    help=f"synthetic 시나리오 ID (기본 {DEFAULT_SCENARIO_ID})")
    ap.add_argument("--simulation-run-id", default=None,
                    help="이번 실행 ID. 안 주면 시각으로 만든다")
    ap.add_argument("--post", default=None, metavar="URL",
                    help="수집 API 베이스 URL. 예) http://localhost:8080"
                         " (안 주면 파일로만 남긴다)")
    ap.add_argument("--post-timeout", type=int, default=40,
                    help="수집 API 응답 대기 초. Kafka 가 없으면 25초쯤 뒤 503 이 온다")
    a = ap.parse_args()

    simulation_run_id = a.simulation_run_id or default_simulation_run_id()
    start_url = entry_url(a.url, a.scenario_id, simulation_run_id)
    # 상세로 딥링크한 사람이 목록으로 돌아갈 때 쓸 주소 (product 파라미터 없음)
    globals()["LIST_URL"] = start_url

    if a.model:
        MODEL = a.model
    if a.debug_screen:
        globals()["DEBUG_SCREEN"] = True

    load_dotenv()

    client = None
    if a.local_model and not a.dry_run and not a.script:
        client = LocalLLM(a.local_model)
    elif a.api_base and not a.dry_run and not a.script:
        # 자체 모델 서버 (model_server.py). GPU 서버에 모델을 올려 두고 여기서는
        # 브라우저만 돌린다 — 노트북 VRAM 이 8GB 라 3B 가 한계인데, 서버가 32GB 면
        # 7B 이상을 쓸 수 있고 노트북 GPU 가 비어 워커도 늘릴 수 있다.
        # 키는 검사하지 않는 서버라 자리만 채운다.
        from openai import OpenAI
        client = OpenAI(base_url=a.api_base, api_key="not-used")
        print(f"모델 서버 {a.api_base} · 모델 {MODEL}")
    elif not a.dry_run and not a.script:
        from openai import OpenAI
        if a.openai:
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                print("OPENAI_API_KEY 가 없습니다. 레포 루트 .env 에 넣거나 환경변수로 주십시오.")
                raise SystemExit(1)
            client = OpenAI(api_key=key)          # 기본 엔드포인트 = api.openai.com
        else:
            key = os.environ.get("GMS_KEY")
            if not key:
                print("GMS_KEY 가 없습니다. 레포 루트 .env 에 'GMS_KEY=...' 를 넣으십시오.")
                raise SystemExit(1)
            client = OpenAI(base_url=GMS_BASE, api_key=key)

    if a.workers > 1 and a.shards == 1:
        run_parallel(a)
        return

    personas = json.load(open(PERSONA_FILE, encoding="utf-8"))[:a.limit]
    catalog = load_catalog()
    if not catalog:
        print(f"상품 목록을 못 읽었습니다 ({PRODUCTS_FILE}) — 전원 목록에서 시작합니다")
    print("PA(LLM 에이전트) — 정성 검증 축입니다. 대표 정량 지표(PC 9,900명)에"
          " 합치지 마십시오 (docs/ai/evaluation-framework.md 5절)")
    if a.shards > 1:
        # 앞에서부터 순서대로 나누지 않고 건너뛰며 나눈다. 페르소나 파일이
        # 정렬돼 있으면 앞쪽 샤드에만 무거운 사람이 몰릴 수 있다
        personas = personas[a.shard::a.shards]
    print(f"페르소나 {len(personas)}명 · 모델 {MODEL} · 최대 {a.turns}턴"
          + ("  [dry-run]" if a.dry_run else ""))
    print(f"프론트 {start_url}")
    print(f"실행 메타데이터 actor_type=synthetic generator_type={GENERATOR_TYPE} "
          f"scenario_id={a.scenario_id} simulation_run_id={simulation_run_id}")
    print(f"수집 API {a.post}" if a.post else "수집 API 전송 없음 (파일로만 남김)")

    dec_path = a.decisions
    if dec_path is None:
        base, ext = os.path.splitext(a.out)
        dec_path = f"{base}_decisions{ext}"
    elif dec_path.lower() == "off":
        dec_path = None
    decisions = DecisionLog(dec_path, simulation_run_id, MODEL)
    if dec_path:
        print(f"판단 근거 {dec_path}")

    from playwright.sync_api import sync_playwright
    tot = dict(calls=0, done=0, failed=0, carted=0, broken=0)
    t0 = time.time()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sink = LogSink(a.out, a.scenario_id, simulation_run_id,
                   post_base=a.post, timeout=a.post_timeout)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        for p in personas:
            ctx = browser.new_context()          # 페르소나마다 새 세션
            sink.attach(ctx)                     # 백엔드 없이도 로그를 건진다
            page = ctx.new_page()

            # 출발 지점은 페르소나마다 다르되 **같은 사람은 늘 같은 곳**에서
            # 시작한다. 실행마다 달라지면 커버리지 변화가 코드 때문인지
            # 운 때문인지 구분할 수 없다
            rng = random.Random(p["persona_id"])
            deep = catalog and rng.random() < DEEP_LINK_P
            if a.entry != "auto":
                deep = a.entry == "detail"
            entry = entry_url(a.url, a.scenario_id, simulation_run_id,
                              product_id=rng.choice(catalog) if deep else None)
            page.goto(entry, wait_until="networkidle")

            # 딥링크로 들어간 상세가 렌더되지 않으면 목록으로 되돌린다.
            # AboutProduct.tsx 크래시는 2026-09-02 고쳐졌다. 이 방어는 이제
            # 대부분 놀지만, 놀고 있다는 것 자체가 확인이라 남긴다
            if deep and not page.locator('[data-log-action="add_to_cart"]').count():
                print(f"  {p['persona_id']}  상세가 렌더되지 않아 목록에서 시작합니다")
                page.goto(LIST_URL, wait_until="networkidle")
                page.wait_for_timeout(800)

            if not switch_persona(page, p["persona_id"]):
                print(f"  {p['persona_id']}  페르소나 전환 실패 — 건너뜀")
                ctx.close()
                continue

            spread_start(page, rng)              # 목록에서 시작하면 자리를 흩는다

            print(f"  {p['persona_id']}  {TYPE_KR.get(p['skin_type'], '')}/"
                  f"{p['skin_tone']}  구매 {p['n_products']}개")
            script = ScriptedLLM(a.script.split(",")) if a.script else None
            r = run_one(page, client, p, a.turns, a.cache, a.dry_run, not a.quiet,
                        decisions=decisions,
                        script=script)
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
    if tot.get("broken"):
        print(f"  ⚠ 화면이 비어 복구한 횟수 {tot['broken']}회"
              f" — AboutProduct.tsx 크래시는 2026-09-02 고쳐졌으므로 다른 원인입니다")
    print(f"  LLM 호출 {tot['calls']}회 · {dt:.0f}초")
    if tot["calls"] and not a.local_model and not a.api_base:
        print(f"  예상 크레딧 약 {tot['calls'] * 0.6:.0f}"
              f"  (100명 환산 {tot['calls'] * 0.6 / max(len(personas),1) * 100:,.0f})")
    top = sorted(sink.kinds.items(), key=lambda x: -x[1])[:8]
    print(f"  수집 로그 {sink.n}건 -> {a.out}")
    if decisions.n:
        print(f"  판단 근거 {decisions.n}건 -> {decisions.path}"
              f"  (교정된 턴 포함. 이벤트와는 persona_id+simulation_run_id 로 붙는다)")
    decisions.close()
    if top:
        print("  " + " · ".join(f"{k} {v}" for k, v in top))

    # 표시가 어디서 붙었는지. 프론트가 스스로 붙이기 시작하면 stamped 가 0 이 된다
    print(f"  actor_type=synthetic  {sink.n}건 "
          f"(러너가 채움 {sink.stamped} · 봉투에 이미 있었음 {sink.already})")
    if sink.dropped:
        print(f"  페르소나 선택 전 이벤트 {sink.dropped}건은 전송 제외 (파일에는 있음)")
    if a.post:
        print(f"  수집 API 전송  성공 {sink.sent}건 / 실패 {sink.send_failed}건")
        if sink.send_failed:
            print("    수집 서버와 Kafka 가 떠 있는지 확인하세요. 파일에는 그대로 남아 있습니다.")
    print("=" * 60)


# ============================================================================
# 6. 행동 로그 가로채기
# ============================================================================

class LogSink:
    """프론트가 /api/events 로 보내는 행동 로그를 가로채 표시를 채우고 내보낸다.

    두 가지를 한다.

    1. **파일로 남긴다.** 프론트는 sendBeacon/fetch 로 백엔드에 로그를 보내는데,
       백엔드가 안 떠 있으면 그 요청은 그대로 실패하고 **로그가 통째로 사라진다** —
       에이전트를 25턴씩 돌려놓고 아무것도 못 건지는 사고가 여기서 난다.
    2. **synthetic 표시를 채운다.** 에이전트는 실제 브라우저로 조작하므로 프론트
       로거가 실사용자와 똑같이 `actor_type='user'` 로 남긴다. 그대로 두면
       `clean_events_job` 이 `user_id` 를 NULL 로, `source` 를 `web` 으로 파생하고
       시뮬레이션 Mart 에서 통째로 빠진다. 게다가 synthetic 필수 properties 검증은
       `actor_type != 'synthetic'` 이면 그냥 통과시켜서 **거절도 안 되고 조용히
       잘못된 데이터**가 된다. 표시는 여기서 채운다. synthetic 필수값은
       contracts/event-schema.json, PA 보강 책임은
       docs/analytics/log-transport-contract.md §9-2를 따른다.

    `--post` 를 주면 채운 로그를 수집 API 로 대신 보낸다. 헤더에도 같은 사실을
    적어 둔다 (`X-Actor-Type`). 지금은 아무도 안 읽지만, 나중에 수집 서버가
    헤더를 보고 직접 찍는 방식(합성 트래픽의 일반적인 처리)으로 올라가도
    러너를 다시 고칠 필요가 없다.
    """

    def __init__(self, path, scenario_id, simulation_run_id, post_base=None,
                 timeout=40):
        self.path = path
        self.f = io.open(path, "w", encoding="utf-8")
        self.n = 0
        self.kinds = {}
        self.scenario_id = scenario_id
        self.simulation_run_id = simulation_run_id
        self.post_base = post_base.rstrip("/") if post_base else None
        self.timeout = timeout
        # 봉투가 어떤 상태로 들어왔는지. 프론트가 스스로 표시를 붙이게 되면
        # already 가 오르고 stamped 는 0 이 된다 — 그때 이 보정을 걷어내면 된다
        self.already = 0
        self.stamped = 0
        self.sent = 0
        self.send_failed = 0
        self.dropped = 0
        self.client = None          # 첫 전송 때 만든다 (백프레셔 상태를 들고 있다)
        self.schema_version = None
        self.queue = None
        self.worker = None
        if self.post_base:
            import queue as _queue
            import threading
            self.queue = _queue.Queue()
            self.worker = threading.Thread(target=self._drain, daemon=True)
            self.worker.start()

    def attach(self, ctx):
        ctx.route("**/api/events", self._handle)

    def _stamp(self, ev):
        """봉투에 synthetic 표시를 채운다. 이미 붙어 있으면 건드리지 않는다"""
        if ev.get("actor_type") == "synthetic":
            self.already += 1
        else:
            ev["actor_type"] = "synthetic"
            self.stamped += 1

        props = ev.get("properties")
        if not isinstance(props, dict):
            props = {}
            ev["properties"] = props
        # 프론트가 넣어준 값이 있으면 존중한다. 우리 값으로 덮으면 프론트가
        # 나중에 제대로 붙였을 때 그 사실을 확인할 방법이 없어진다
        props.setdefault("scenario_id", self.scenario_id)
        props.setdefault("simulation_run_id", self.simulation_run_id)
        props.setdefault("generator_type", GENERATOR_TYPE)
        return ev

    def _handle(self, route, request):
        try:
            payload = json.loads(request.post_data or "{}")
            self.schema_version = payload.get("schema_version") or self.schema_version
            events = [self._stamp(ev) for ev in payload.get("events", [])]
            for ev in events:
                self.f.write(json.dumps(ev, ensure_ascii=False) + NL)
                self.n += 1
                k = ev.get("event_name") or ev.get("action") or "?"
                self.kinds[k] = self.kinds.get(k, 0) + 1

            # 페르소나를 고르기 전(첫 화면 로드)에 발생한 이벤트는 보내지 않는다.
            # synthetic Event 는 persona_id 가 필수라 Spark 가 invalid_properties 로
            # 격리한다. 어느 페르소나의 행동도 아니므로 격리 로그만 늘 뿐이다.
            # 실측: 1인당 2건(첫 화면 scroll_depth). 파일에는 그대로 남긴다
            sendable = [ev for ev in events if ev.get("persona_id")]
            self.dropped += len(events) - len(sendable)
            if self.queue is not None and sendable:
                self.queue.put(sendable)
        except Exception:
            pass
        # 수집 서버 응답과 무관하게 200 을 돌려준다. 실패를 그대로 전하면
        # 프론트가 같은 배치를 재전송해 파일에 중복이 쌓인다. 전송 성패는
        # 우리가 세어서 실행 끝에 보고한다
        route.fulfill(status=200, content_type="application/json",
                      body='{"ok":true}')

    def _drain(self):
        """전송은 별도 스레드에서 한다.

        route 핸들러 안에서 그대로 보내면 브라우저가 응답을 기다리며 멈춘다.
        Kafka 가 안 떠 있으면 수집 서버가 25초쯤 뒤에 503 을 주는데, 그동안
        에이전트의 한 턴이 통째로 정지한다.
        """
        while True:
            events = self.queue.get()
            if events is None:
                self.queue.task_done()
                return
            try:
                self._post(events)
            except Exception:
                self.send_failed += len(events)
            self.queue.task_done()

    def _post(self, events):
        """수집 API 로 보낸다. 백프레셔 처리는 공용 클라이언트가 한다.

        생성기(gen_behavior_logs.py)와 **같은 클라이언트**를 쓴다 — 같은 서버에
        같은 계약으로 보내면서 재시도 정책이 다르면 부하 결과를 해석할 수 없다.
        """
        if self.client is None:
            sys.path.insert(0, os.path.join(ROOT, "simulator"))
            from collector_client import CollectorClient
            self.client = CollectorClient(
                self.post_base, timeout=self.timeout, max_batch=POST_BATCH,
                log=lambda m: print(f"   {m}"))
        before = dict(self.client.stats)
        self.client.send(
            events, schema_version=self.schema_version or SCHEMA_VERSION,
            headers={"X-Actor-Type": "synthetic",
                     "X-Simulation-Run-Id": self.simulation_run_id})
        st = self.client.stats
        self.sent += st["sent"] - before["sent"]
        self.send_failed += ((st["dropped"] - before["dropped"])
                             + (st["gave_up"] - before["gave_up"]))

    def close(self):
        if self.queue is not None:
            self.queue.put(None)
            self.worker.join(timeout=self.timeout + 10)
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
