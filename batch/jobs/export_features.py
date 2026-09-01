"""
서빙용 피처 내보내기 — 백엔드 RankingService 가 읽을 파일을 만든다.

    product_feature.jsonl   상품 200개: 148차원 벡터 + prior + 카테고리·가격대·평점
    attribute_affinity.csv  200상품 x 20세그먼트 = 4,000행 (원본을 계약 열로 정리)
    ranking_golden.json     같은 입력에 같은 순위가 나오는지 대조할 기준 결과

**계약 문서(contracts/recommendation-io-spec.md)의 테이블 스키마를 그대로 따른다.**
백엔드는 이 파일을 MySQL 에 적재하고, 조회 시 딕셔너리 1회로 쓴다.

`ranking_golden.json` 을 함께 내는 이유는, 자바로 다시 구현한 점수 계산이
파이썬 구현과 같은 순위를 내는지 **숫자로 확인할 방법**이 있어야 하기 때문이다.
식이 맞아도 블록 가중치·L2 정규화·시드 제외 규칙 중 하나만 어긋나면 순위가 조용히
달라진다. 페르소나 20명의 상위 10개와 점수를 같이 실어 둔다.

실행: python batch/jobs/export_features.py [--out DIR] [--golden N]
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from persona_feature import AFFINITY_CSV, ATTRS, load as load_affinity  # noqa: E402
from product_encoder import Encoder                                     # noqa: E402
from recommender import LAMBDA, SCHEDULE, schedule_for                  # noqa: E402

OUT_DIR = os.path.join(ROOT, "batch", "ingest", "data", "serving")
PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
GOLDEN_N = 20
TOP_K = 10


def export_products(e, matrix, prior, path):
    """product_feature 테이블 1행 = JSONL 1줄"""
    now = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i, p in enumerate(e.products):
            f.write(json.dumps({
                "product_id": p["product_id"],
                "vocab_version": e.V["version"],
                # L2 정규화까지 끝난 값이다. 백엔드는 그대로 내적만 하면 된다
                "vector": [round(float(x), 6) for x in matrix[i]],
                "prior_score": round(float(prior[i]), 5),
                "secondary_category": p["secondary_category"],
                "tertiary_category": p["tertiary_category"],
                "price_bin": price_bin_of(e, p),
                "rating": round(float(p.get("rating") or 0), 2),
                "updated_at": now,
            }, ensure_ascii=False) + "\n")
    return len(e.products)


def price_bin_of(e, product):
    """어휘집 경계로 가격대 라벨을 정한다. 인코더와 같은 경계를 쓴다"""
    price = float(product.get("price_usd") or 0)
    labels = e.blk["price_bin"]["vocab"]
    for label, edge in zip(labels, e.edges):
        if price <= edge:
            return label
    return labels[-1]


def export_affinity(path):
    """원본 CSV 에서 계약 열만 추린다 (디버깅용 lift · n_reviews · z_score 포함)"""
    cols = ["product_id", "attribute", "segment", "affinity", "lift",
            "n_reviews", "z_score"]
    n = 0
    with open(AFFINITY_CSV, encoding="utf-8-sig", newline="") as src, \
         open(path, "w", encoding="utf-8", newline="") as dst:
        w = csv.DictWriter(dst, fieldnames=cols)
        w.writeheader()
        for row in csv.DictReader(src):
            if row["attribute"] not in ATTRS:
                continue
            w.writerow({"product_id": row["group_id"], "attribute": row["attribute"],
                        "segment": row["segment"], "affinity": row["affinity"],
                        "lift": row["lift"], "n_reviews": row["n_reviews"],
                        "z_score": row["z_score"]})
            n += 1
    return n


def export_golden(e, matrix, prior, affinity, index, personas, path, n_persona):
    """같은 입력에 같은 순위가 나오는지 대조할 기준 결과.

    서빙 기준이 아니라 **점수 계산 대조용**이다. 시드는 후보에서 빼고(평가와 동일),
    행동 로그 없이 리뷰 시드만으로 만든 사용자 벡터를 쓴다. 자바 구현이 이 파일을
    재현하면 벡터·가중치·정규화가 전부 맞다는 뜻이다.
    """
    cases = []
    for p in personas:
        seeds = []
        for r in p["reviews"]:
            g = r["group_id"]
            if g in index and g not in seeds:
                seeds.append(g)
        if len(seeds) < 2:
            continue
        si = [index[g] for g in seeds]
        u = matrix[si].mean(0)
        nu = np.linalg.norm(u)
        cos = matrix @ (u / nu) if nu > 1e-9 else np.zeros(len(matrix), np.float32)
        w1, w2, w3 = schedule_for(len(si))
        score = w1 * cos + w2 * affinity(p) + w3 * prior
        score[si] = -np.inf                      # 시드는 후보에서 뺀다
        top = np.argsort(-score)[:TOP_K]
        cases.append({
            "persona_id": p["persona_id"],
            "attributes": {a: p[a] for a in ATTRS},
            "seed_product_ids": seeds,
            "weights": {"w1_cosine": w1, "w2_attribute": w2, "w3_prior": w3,
                        "lambda_negative": LAMBDA},
            "expected_top10": [{"product_id": e.products[i]["product_id"],
                                "score": round(float(score[i]), 6)} for i in top],
        })
        if len(cases) >= n_persona:
            break

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "vocab_version": e.V["version"],
            "schedule": [list(x) for x in SCHEDULE],
            "note": ("행동 로그 없이 리뷰 시드만으로 만든 사용자 벡터 기준. "
                     "시드는 후보에서 제외하고 **MMR 은 적용하지 않았다** — 점수 계산 "
                     "자체를 대조하기 위한 값이다. 서빙은 여기에 노출 정책"
                     "(viewed 상한 2개)과 MMR(λ_mmr=0.8)이 더 붙는다."),
            "cases": cases,
        }, f, ensure_ascii=False, indent=2)
    return len(cases)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--golden", type=int, default=GOLDEN_N)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    e = Encoder()
    matrix = np.asarray(e.matrix(), np.float32)
    prior = np.asarray(e.prior(), np.float32) if hasattr(e, "prior") else None
    if prior is None:
        lg = np.log1p(np.array([p["loves_count"] for p in e.products], float))
        prior = ((lg - lg.min()) / (lg.max() - lg.min())).astype(np.float32)
    index = {p["product_id"]: i for i, p in enumerate(e.products)}
    affinity = load_affinity(index)
    personas = json.load(open(PERSONAS, encoding="utf-8"))

    n_p = export_products(e, matrix, prior,
                          os.path.join(a.out, "product_feature.jsonl"))
    n_a = export_affinity(os.path.join(a.out, "attribute_affinity.csv"))
    n_g = export_golden(e, matrix, prior, affinity, index, personas,
                        os.path.join(a.out, "ranking_golden.json"), a.golden)

    print(f"내보냄 -> {a.out}")
    print(f"  product_feature.jsonl   상품 {n_p}개 x {matrix.shape[1]}차원"
          f" (어휘집 v{e.V['version']})")
    print(f"  attribute_affinity.csv  {n_a:,}행")
    print(f"  ranking_golden.json     페르소나 {n_g}명 x 상위 {TOP_K}개")


if __name__ == "__main__":
    main()
