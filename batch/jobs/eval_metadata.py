"""
평가 metadata — seed / target 을 **한 곳에서 정하고 파일로 남긴다.**

왜 필요했나
    세 평가 축이 각자 seed·target 을 계산하고 있었고 정의가 서로 달랐다.
        오프라인·동적    리뷰 등장 순서의 마지막 상품
        리뷰 순차 재생   시간순 정렬 후 마지막 **긍정** 상품
    9,900명 중 **792명(8.0%)** 이 축마다 다른 target 을 맞히고 있었다.
    축을 나란히 비교하려면 같은 문제를 풀어야 한다.

정본 정의 (Persona 계약 §7.1 = docs/ai/evaluation-framework.md 1절)
    - 카탈로그에 있는 리뷰만 남기고
      `submission_time DESC NULLS LAST -> review_id DESC` 로 정렬한다
    - 그 순서에서 **긍정 조건을 만족하는 첫 리뷰**가 target 이다
      (= 가장 마지막 긍정 리뷰). 긍정은 `rating >= 4` 또는
      (`is_recommended=true` 그리고 `rating >= 3`)  — 계약 §7.1.1
    - 같은 날짜는 `review_id DESC` 로 가른다 — 계약 §7.1.2
    - 긍정 리뷰가 하나도 없으면 target 이 없다. 그 사람은 평가에서 빠진다
    - target 보다 앞선 상품들이 seed 다. target 과 같은 상품의 리뷰는 앞선 것까지
      전부 뺀다 (누출 방지 — 같은 상품을 두 번 리뷰한 사람이 21.8%)

**우리가 만드는 것은 선호 상품을 맞히는 추천기다.** 1점 준 상품을 맞히라는 것은
다른 과제라, 마지막 리뷰가 불만이어도 그 사람을 버리지 않고 **마지막 긍정 리뷰**를
정답으로 쓴다. 불만은 정답이 아니라 사람의 속성(`latest_review_label`)으로 남는다.

**2026-09-03 — 계약과 맞춘 것 두 가지.**
    §7.1.1  긍정 조건에 `is_recommended` 를 넣는다 (평점 3 이상일 때만).
            1~2점인데 추천한 8명은 모순 데이터라 긍정으로 보지 않는다.
            이 하나로 정본과 계약의 차이 **157명**이 사라진다
    §7.1.2  같은 날짜 tie-break 을 `review_id DESC` 로 고정한다 (**5명**)

산출: batch/ingest/data/eval_metadata.jsonl
    평가 때마다 다시 계산하지 않고 이 파일을 읽는다. 분석(새 브랜드 비율,
    인기 구간별 분포)도 이 파일 하나로 재현된다.

실행: python batch/jobs/eval_metadata.py            # PC 9,900명
      python batch/jobs/eval_metadata.py --agent    # PA 에이전트 100명 (대조군)
"""
import json
import os
import sys

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from persona_split import split_of                       # noqa: E402

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
OUT = os.path.join(ROOT, "batch", "ingest", "data", "eval_metadata.jsonl")

# LLM 에이전트 100명. **PC 9,900명의 대조군**이라 같은 규칙으로 만든다 —
# 규칙이 다르면 두 집단의 정확도를 나란히 놓을 수 없다 (데이터 파트 요청)
AGENT_PERSONAS = os.path.join(ROOT, "simulator", "personas", "data",
                              "personas_100_agent.json")
AGENT_OUT = os.path.join(ROOT, "batch", "ingest", "data",
                         "eval_metadata_agent.jsonl")
POSITIVE = 4        # 이 점수 이상이면 무조건 긍정
NEGATIVE = 2        # 이 점수 이하면 부정
RECOMMEND_MIN = 3   # is_recommended 로 긍정이 되려면 최소 이 점수는 돼야 한다


def sort_key(r):
    """계약 §7.1-1 · §7.1.2 의 정렬 키. `submission_time` -> `review_id` 오름차순.

    계약은 DESC 로 적고 첫 리뷰를 고른다. 여기서는 오름차순으로 세운 뒤 **뒤에서부터**
    보므로 같은 순서가 된다. 시각이 없으면 빈 문자열이라 가장 앞에 가고, 뒤에서부터
    보는 우리 순서에서는 가장 늦게 닿는다 = NULLS LAST 와 같다.
    """
    return (str(r.get("submission_time") or ""), str(r.get("review_id") or ""))


def is_positive(r):
    """계약 §7.1-3. `rating >= 4` 또는 (`is_recommended` 이고 `rating >= 3`).

    3점에 추천은 정상 긍정 신호지만 **1~2점에 추천은 모순 데이터**라 정답으로
    쓰면 노이즈다. 그래서 is_recommended 단독이 아니라 3점 하한을 함께 건다.
    실측 9,900명 중 이 조건으로 늘어나는 사람 141명, 걸러지는 모순 8명.
    """
    rating = r.get("rating") or 0
    return rating >= POSITIVE or (bool(r.get("is_recommended"))
                                  and rating >= RECOMMEND_MIN)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(personas=None, products=None, split_label=None):
    """split_label 을 주면 split_of() 대신 그 값을 그대로 넣는다.

    홀드아웃 집단용이다. `split_of` 는 persona_id 해시로 train/valid/test 를
    나누는데, 홀드아웃은 **집단 전체가 하나의 평가 집합**이라 쪼개면 안 된다.
    """
    personas = personas if personas is not None else _load(PERSONAS)
    products = products if products is not None else _load(PRODUCTS)
    catalog = {p["product_id"]: p for p in products}
    by_reviews = sorted(products, key=lambda p: -p["_review_stats"]["review_count"])
    pop_rank = {p["product_id"]: i + 1 for i, p in enumerate(by_reviews)}

    rows, skipped = [], {"no_review": 0, "no_positive": 0, "no_seed": 0}
    for persona in personas:
        # 계약 §7.1-1 의 Product Join 은 여기서 끝난다. group_id 가 카탈로그에
        # 없는 리뷰는 target 도 seed 도 될 수 없다 (실측 9,900명에서는 0건이다)
        reviews = sorted(
            [r for r in persona.get("reviews", []) if r.get("group_id") in catalog],
            key=sort_key)
        if not reviews:
            skipped["no_review"] += 1
            continue

        # 계약 §7.1-2 — 뒤에서부터 보며 긍정 조건을 만족하는 첫 리뷰가 target 이다
        target = next((r for r in reversed(reviews) if is_positive(r)), None)
        if target is None:                # §7.1-3 긍정 리뷰가 하나도 없다
            skipped["no_positive"] += 1
            continue

        cut = reviews.index(target)
        # target 과 같은 상품의 리뷰는 앞선 것까지 전부 뺀다
        history = [r for r in reviews[:cut] if r["group_id"] != target["group_id"]]
        seeds, seen = [], set()
        for r in history:
            if r["group_id"] not in seen:
                seen.add(r["group_id"])
                seeds.append(r["group_id"])
        if not seeds:
            skipped["no_seed"] += 1
            continue

        seed_brands = {catalog[g]["brand_name"] for g in seeds}
        target_brand = catalog[target["group_id"]]["brand_name"]
        rows.append({
            "persona_id": persona["persona_id"],
            "split": split_label or split_of(persona["persona_id"]),
            "seed_product_ids": seeds,
            "target_product_id": target["group_id"],
            "n_seed": len(seeds),
            "n_history_reviews": len(history),
            "n_positive": sum(1 for r in history
                              if (r.get("rating") or 0) >= POSITIVE),
            "n_negative": sum(1 for r in history
                              if (r.get("rating") or 0) <= NEGATIVE),
            # 분석 축 — 매번 다시 계산하지 않도록 여기 담는다
            # 정답 리뷰 자체를 식별할 수 있게 남긴다. 계약 §7.3 의
            # `target_review_id` 와 붙는 값이다.
            #
            # **상품 ID 만으로는 어느 리뷰가 정답인지 특정되지 않는다.**
            # target 상품에 리뷰를 2건 이상 쓴 사람이 2,017명(21.7%)이고,
            # 그중 1,988명은 그 리뷰들이 같은 날짜라 날짜로도 못 가린다.
            # 계약 표와 대조할 때 review_id 가 있어야 한 행으로 떨어진다
            "target_review_id": target.get("review_id"),
            "target_rating": target.get("rating"),
            "target_is_recommended": bool(target.get("is_recommended")),
            "target_popularity_rank": pop_rank[target["group_id"]],
            "target_is_longtail": pop_rank[target["group_id"]] > 100,
            "target_is_new_brand": target_brand not in seed_brands,
            "target_brand": target_brand,
            "target_submitted_at": str(target.get("submission_time") or ""),
        })
    return rows, skipped


def load(path=OUT, split=None):
    """저장된 metadata 를 읽는다. split 을 주면 그 집합만"""
    if not os.path.exists(path):
        raise SystemExit(f"{path} 가 없습니다. python batch/jobs/eval_metadata.py 먼저 실행")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if split in (None, "all") or row["split"] == split:
                out.append(row)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", action="store_true",
                    help="PA 에이전트 100명으로 만든다 (대조군)")
    ap.add_argument("--personas", default=None,
                    help="임의의 페르소나 파일로 만든다 (홀드아웃용)")
    ap.add_argument("--tag", default=None,
                    help="--personas 와 함께. split 값이자 출력 파일 꼬리표")
    a = ap.parse_args()

    global OUT
    if a.personas:
        if not a.tag:
            raise SystemExit("--personas 를 쓰려면 --tag 도 필요하다")
        rows, skipped = build(_load(a.personas), split_label=a.tag)
        OUT = os.path.join(ROOT, "batch", "ingest", "data",
                           f"eval_metadata_{a.tag}.jsonl")
    else:
        rows, skipped = build(_load(AGENT_PERSONAS) if a.agent else None)
        if a.agent:
            OUT = AGENT_OUT
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(rows)
    dropped = sum(skipped.values())
    print(f"평가 metadata {total:,}명 -> {os.path.relpath(OUT, ROOT)}"
          f" (제외 {dropped:,}명)")
    print(f"  제외 내역 · 긍정 리뷰 없음 {skipped['no_positive']:,}명"
          f" · seed 없음 {skipped['no_seed']:,}명"
          f" · 카탈로그 리뷰 없음 {skipped['no_review']:,}명")
    for name in ((a.tag,) if a.personas else ("train", "valid", "test")):
        sub = [r for r in rows if r["split"] == name]
        if not sub:
            continue
        longtail = sum(r["target_is_longtail"] for r in sub)
        newbrand = sum(r["target_is_new_brand"] for r in sub)
        seeds = sum(r["n_seed"] for r in sub) / len(sub)
        print(f"  {name:<6} {len(sub):>6,}명 · 시드 평균 {seeds:.1f}개"
              f" · 롱테일 target {longtail / len(sub) * 100:.1f}%"
              f" · 새 브랜드 target {newbrand / len(sub) * 100:.1f}%")


if __name__ == "__main__":
    main()
