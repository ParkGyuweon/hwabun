"""
평가 metadata — seed / target 을 **한 곳에서 정하고 파일로 남긴다.**

왜 필요했나
    세 평가 축이 각자 seed·target 을 계산하고 있었고 정의가 서로 달랐다.
        오프라인·동적    리뷰 등장 순서의 마지막 상품
        리뷰 순차 재생   시간순 정렬 후 마지막 **긍정** 상품
    9,900명 중 **792명(8.0%)** 이 축마다 다른 target 을 맞히고 있었다.
    축을 나란히 비교하려면 같은 문제를 풀어야 한다.

정본 정의 (docs/ai/evaluation-framework.md 1절)
    - 리뷰 상품을 **시간순**으로 정렬한다
    - 마지막 **긍정(평점 4 이상)** 상품 1개가 target 이다
    - 그 앞의 상품들이 seed 다. target 과 같은 상품의 리뷰는 앞선 것까지 전부 뺀다
      (누출 방지 — 같은 상품을 두 번 리뷰한 사람이 있다)

산출: batch/ingest/data/eval_metadata.jsonl (9,900행, 약 3MB)
    평가 때마다 다시 계산하지 않고 이 파일을 읽는다. 분석(새 브랜드 비율,
    인기 구간별 분포)도 이 파일 하나로 재현된다.

실행: python batch/jobs/eval_metadata.py
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
POSITIVE = 4        # 이 점수 이상이면 긍정
NEGATIVE = 2        # 이 점수 이하면 부정


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(personas=None, products=None):
    personas = personas if personas is not None else _load(PERSONAS)
    products = products if products is not None else _load(PRODUCTS)
    catalog = {p["product_id"]: p for p in products}
    by_reviews = sorted(products, key=lambda p: -p["_review_stats"]["review_count"])
    pop_rank = {p["product_id"]: i + 1 for i, p in enumerate(by_reviews)}

    rows, skipped = [], 0
    for persona in personas:
        reviews = sorted(
            [r for r in persona.get("reviews", []) if r.get("group_id") in catalog],
            key=lambda r: str(r.get("submission_time") or ""))
        target = None
        for r in reversed(reviews):
            if (r.get("rating") or 0) >= POSITIVE:
                target = r
                break
        if target is None:
            skipped += 1
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
            skipped += 1
            continue

        seed_brands = {catalog[g]["brand_name"] for g in seeds}
        target_brand = catalog[target["group_id"]]["brand_name"]
        rows.append({
            "persona_id": persona["persona_id"],
            "split": split_of(persona["persona_id"]),
            "seed_product_ids": seeds,
            "target_product_id": target["group_id"],
            "n_seed": len(seeds),
            "n_history_reviews": len(history),
            "n_positive": sum(1 for r in history
                              if (r.get("rating") or 0) >= POSITIVE),
            "n_negative": sum(1 for r in history
                              if (r.get("rating") or 0) <= NEGATIVE),
            # 분석 축 — 매번 다시 계산하지 않도록 여기 담는다
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
    rows, skipped = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(rows)
    print(f"평가 metadata {total:,}명 -> {os.path.relpath(OUT, ROOT)}"
          f" (제외 {skipped:,}명 — 긍정 리뷰나 seed 가 없음)")
    for name in ("train", "valid", "test"):
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
