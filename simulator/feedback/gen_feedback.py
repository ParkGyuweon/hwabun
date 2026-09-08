# -*- coding: utf-8 -*-
"""시연용 고객 피드백 생성 — 페르소나가 사장님에게 쓰는 개선 요청.

무엇을 만드나
    브랜드 대시보드의 "고객 피드백" 화면에 쓸 자연어 데이터다. 리뷰가 아니다.

        리뷰    사용자 -> 다른 사용자 · 공개 · 별점 포함 · "살 만한가"
        피드백  사용자 -> 브랜드 사장님 · 비공개 · 별점 없음 · **고칠 부분**

    기획이 "고객 피드백으로 함께 성장하는 플랫폼" 이므로 **전부 불만·개선
    요청**이다. 칭찬은 리뷰가 받는다.

왜 만들어야 하나
    피드백은 우리 서비스에서 받는 것이라 **기존 데이터가 한 건도 없다.**
    Sephora 리뷰 84만 건은 리뷰지 피드백이 아니라 대체할 수 없다.

한 칸에 하나 (생성 규칙 — 분류 계약이 아니다)
    용기 불만과 향 불만은 같은 칸에 못 쓴다. 화면에서 칸을 나눠 받는 설계라
    여기서는 **한 건 = 한 축**으로 만든다 (생성 축이 곧 고객이 고른 축이 된다).
    ⚠ 이건 생성기 사정이다 — 분류 계약 0.2.0 은 한 건에 카테고리 여러 개를 허용한다
    ("뚜껑도 이상하고 펌프도 이상" 은 둘). 실사용자는 한 축 칸 안에 불만을 여럿 쓴다.

⚠ 이 데이터로 분류 정확도를 재면 안 된다
    같은 모델이 축을 알고 쓴 문장을 같은 모델이 분류하면 당연히 맞는다.
    `intended_axis` 는 **성능 근거가 아니라 바닥 점검용**이다 — 이것조차 못
    되찾으면 파이프라인이 깨진 것이다. 정확도는 사람이 쓴 문장으로 잰다.

실행
    set -a && . ./.env && set +a
    python simulator/feedback/gen_feedback.py --n 100
"""
import argparse
import json
import os
import random
import sys
import time
from collections import Counter

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GMS_BASE = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
MODEL = "gpt-4.1-nano"
BATCH = 5

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
OUT_DIR = os.path.join(BD, "data")
NL = chr(10)

# 브랜드가 **제품을 고쳐서** 해결할 수 있는 축만 둔다.
# 배송·CS 는 플랫폼 문제라 사장님이 제품으로 못 고친다 — 그래서 뺀다.
AXES = {
    "효능": "기대한 효과가 안 나거나 부작용이 났다 (모공·미백·주름·진정 등)",
    "사용감": "발림성·흡수·끈적임·자극·백탁 등 쓸 때의 느낌",
    "향": "향의 세기·종류·지속. 인공적인 냄새",
    "용기·포장": "뚜껑·펌프·튜브·용기 재질·라벨 표기. **부품 고장은 전부 여기**",
    "용량·가격": "용량 대비 가격, 소·대용량이 없음",
}

TONE_KR = {"fair": "매우 밝은 톤", "light": "밝은 톤", "medium": "중간 톤",
           "tan": "어두운 톤", "deep": "깊은 톤"}
TYPE_KR = {"oily": "지성", "dry": "건성", "combination": "복합성", "normal": "중성"}

PROMPT = """당신은 화장품을 산 고객 {n}명이 각각 브랜드 사장님에게 **비공개로** 보내는 개선 요청을 쓴다.

지켜야 할 것
- 다른 고객에게 보이지 않는다. 사장님만 읽는다. 그래서 솔직하다.
- **한 칸에 하나의 이야기만** 쓴다. 두 가지 불만을 한 문장에 섞지 않는다.
- 리뷰가 아니다. 별점도, "추천합니다" 도 쓰지 않는다.
- **고칠 부분**만 쓴다. 칭찬으로 시작하지 않는다.
- 1~2문장. 실제 사람이 쓰듯 구어체로. 존댓말.
- 그 사람의 피부 타입과 상품 특성에서 나올 법한 말이어야 한다.

각 항목:
{items}

JSON 배열만 출력하라. 다른 말은 쓰지 마라.
[{{"i": 0, "body": "..."}}]"""


def load_products(path):
    d = json.load(open(path, encoding="utf-8"))
    return d if isinstance(d, list) else (d.get("products") or list(d.values())[0])


def product_brief(p):
    """LLM 에게 줄 상품 요약. 전성분을 통째로 넣으면 토큰만 먹는다"""
    desc = p.get("description") or {}
    what = desc.get("what_it_is", "") if isinstance(desc, dict) else ""
    return {
        "product_id": p["product_id"],
        "name": p["product_name"],
        "category": (p.get("category") or ["", "", ""])[-1],
        "price_usd": p.get("price_usd"),
        "size": p.get("size"),
        "concerns": p.get("skincare_concerns") or [],
        "suitable": p.get("suitable_skin_types") or [],
        "what": what[:110],
    }


def plan(products, n, rng):
    """(상품, 축) 배정. 축은 고르게, 상품은 **일부러 불균등하게** 준다.

    현실에서 불만은 특정 상품에 몰린다. 고르게 흩뿌리면 사장님 화면이
    "전 상품이 똑같이 조금씩 문제" 로 보여서 판단할 거리가 안 나온다.
    """
    axes = list(AXES)
    weights = [3.0, 2.0, 2.0, 1.5, 1.0, 1.0, 1.0, 1.0][:len(products)]
    weights += [1.0] * (len(products) - len(weights))
    rows = []
    for i in range(n):
        rows.append((rng.choices(products, weights=weights, k=1)[0],
                     axes[i % len(axes)]))
    rng.shuffle(rows)
    return rows


def build_prompt(items):
    lines = []
    for i, (persona, prod, axis) in enumerate(items):
        b = product_brief(prod)
        lines.append(
            f"{i}. 고객: {TYPE_KR.get(persona['skin_type'], persona['skin_type'])} 피부 · "
            f"{TONE_KR.get(persona['skin_tone'], persona['skin_tone'])} · "
            f"리뷰 {persona.get('n_reviews', 0)}건 작성 경험\n"
            f"   상품: {b['name']} ({b['category']}, ${b['price_usd']}, {b['size']}) "
            f"— {b['what']}\n"
            f"   불만 주제: **{axis}** — {AXES[axis]}")
    return PROMPT.format(n=len(items), items="\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default=None,
                    help="상품 JSON. 기본은 SSAFY Beauty 시드")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM 없이 프롬프트만 본다 (크레딧 0)")
    a = ap.parse_args()

    # 정본은 프론트가 들고 있다 (Jira 193). 아직 dev 에 안 들어와서 사본을
    # 여기 두었다 — **머지되면 사본을 지우고 정본만 본다.** 둘이 갈리면
    # 생성한 피드백이 화면에 없는 상품을 가리키게 된다.
    canonical = os.path.join(ROOT, "frontend", "src", "mocks",
                             "products.ssafy-beauty.json")
    snapshot = os.path.join(BD, "products.ssafy-beauty.json")
    path = a.products or (canonical if os.path.exists(canonical) else snapshot)
    if not os.path.exists(path):
        raise SystemExit("상품 파일이 없습니다: " + path)
    if path == snapshot:
        print("⚠ 프론트 정본이 아직 dev 에 없어 사본을 씁니다 "
              "(simulator/feedback/products.ssafy-beauty.json)")
    products = load_products(path)
    brand = products[0].get("brand_name", "")
    personas = json.load(open(PERSONAS, encoding="utf-8"))

    rng = random.Random(a.seed)
    picked = rng.sample(personas, min(a.n, len(personas)))
    assign = plan(products, a.n, rng)
    items = [(picked[i], assign[i][0], assign[i][1]) for i in range(a.n)]

    print(f"브랜드 {brand} · 상품 {len(products)}개 · 피드백 {a.n}건")
    print(f"축 {len(AXES)}종 (전부 불만) · 배치 {a.batch}건")
    print(f"축당 {a.n / len(AXES):.0f}건 · 상품당 평균 {a.n / len(products):.1f}건\n")

    if a.dry_run:
        print(build_prompt(items[:a.batch]))
        return

    from openai import OpenAI
    key = (os.environ.get("GMS_KEY") or os.environ.get("GMS_API_KEY")
           or os.environ.get("OPENAI_API_KEY"))
    if not key:
        raise SystemExit("GMS 키를 못 찾았습니다. `set -a && . ./.env && set +a` 먼저.")
    client = OpenAI(api_key=key, base_url=GMS_BASE)

    os.makedirs(a.out or OUT_DIR, exist_ok=True)
    out_path = os.path.join(a.out or OUT_DIR, "feedback_demo.jsonl")
    tok_in = tok_out = 0
    rows = []
    t0 = time.time()
    missing = []          # 끝내 못 받은 계획 항목
    for s in range(0, len(items), a.batch):
        chunk = items[s:s + a.batch]

        # 모델이 배치의 일부만 돌려주는 일이 있다. 예전에는 그걸 그냥 넘겨서
        # --n 100 이 조용히 99건을 냈다 (배치 7 에서 1건 증발). 축 분포까지
        # 어긋나는데 아무 표시가 없었다. **못 받은 것은 다시 물어본다.**
        need = list(range(len(chunk)))
        done = {}
        for attempt in range(3):
            sub = [chunk[i] for i in need]
            r = client.chat.completions.create(
                model=MODEL, temperature=0.9,
                messages=[{"role": "user", "content": build_prompt(sub)}])
            tok_in += r.usage.prompt_tokens
            tok_out += r.usage.completion_tokens
            txt = r.choices[0].message.content.strip()
            txt = txt[txt.find("["):txt.rfind("]") + 1]
            try:
                got = json.loads(txt)
            except json.JSONDecodeError:
                print(f"  [{s}] JSON 파싱 실패 — 다시 물어봅니다 ({attempt + 1}/3)")
                continue
            for g in got:
                j = g.get("i")
                if not isinstance(j, int) or not (0 <= j < len(sub)):
                    continue
                real = need[j]
                if real in done:      # 같은 i 를 두 번 주면 뒤엣것을 버린다
                    continue
                body = (g.get("body") or "").strip()
                if body:
                    done[real] = body
            need = [i for i in range(len(chunk)) if i not in done]
            if not need:
                break
            print(f"  [{s}] {len(need)}건 못 받음 — 다시 물어봅니다 ({attempt + 1}/3)")
        for i in need:
            persona, prod, axis = chunk[i]
            missing.append((s + i, persona["persona_id"], prod["product_name"], axis))

        for i in sorted(done):
            persona, prod, axis = chunk[i]
            rows.append({
                "feedback_id": f"FB{len(rows) + 1:05d}",
                "persona_id": persona["persona_id"],
                "skin_type": persona["skin_type"],
                "skin_tone": persona["skin_tone"],
                "brand_name": brand,
                "product_id": prod["product_id"],
                "product_name": prod["product_name"],
                "body": done[i],
                # 생성 시점에 지시한 축. **성능 근거가 아니라 바닥 점검용**이다
                "intended_axis": axis,
                "generator": MODEL,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        print(f"  {min(s + a.batch, len(items)):>4}/{len(items)}건", flush=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for r_ in rows:
            f.write(json.dumps(r_, ensure_ascii=False) + "\n")

    dt = time.time() - t0
    if missing:
        print(f"{NL}⚠ {len(missing)}건을 끝내 못 받았습니다"
              f" — 계획 {len(items)}건 대비 부족합니다")
        for idx, pid, pn, ax in missing:
            print(f"    계획 {idx}번 · {pid} · {pn} · 축={ax}")
    print(f"{NL}{len(rows)}건 -> {out_path}")
    print(f"토큰 in {tok_in:,} / out {tok_out:,} · {dt:.0f}초 · 호출 {(len(items) + a.batch - 1) // a.batch}회")
    print("\n축 분포:", dict(Counter(r["intended_axis"] for r in rows)))
    print("상품 분포:", dict(Counter(r["product_id"] for r in rows).most_common()))


if __name__ == "__main__":
    main()
