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
from ltr_features import LtrFeatures, load_ltr                         # noqa: E402
from recommender import (BRAND_W, CF_BETA, LAMBDA, SCHEDULE,            # noqa: E402
                        cf_bonus, load_cooc,
                         brand_match, schedule_for)

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
    brands = [q["brand_name"] for q in e.products]
    known = set(e.blk["brand"]["vocab"])       # 어휘집 밖 브랜드에만 폴백을 건다
    cooc, supporters = load_cooc()
    ltr = load_ltr()
    if ltr is None:
        print("  ⚠ 골든이 **선형 결합** 기준이다 (ltr_model.pkl 이 없다). "
              "학습 결합은 2026-09-07 에 채택됐으므로 "
              "`python batch/jobs/train_ltr.py` 를 먼저 도십시오")
    else:
        print(f"  골든 학습 결합(LTR) 기준 · 트리 {ltr[1]['n_trees']}개")
    print("  골든 " + ("CF 가점 포함" if cooc is not None else
                       "**CF 없이** (item_cooc.npz 가 없다)"))
    feat = (None if ltr is None
            else LtrFeatures(e, matrix, prior, affinity, cooc, supporters))
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
        bm = brand_match(brands, si, known)   # 어휘집 밖 브랜드 폴백 (0.5)
        if bm is not None:
            score = score + BRAND_W * bm
        # CF 가점 (계약 §4-1). **이 파일이 CBF 기준이면 자바 구현이 CBF 순위를
        # 재현하게 되고, 그러면 검증이 통과해도 서빙이 틀린다.**
        if cooc is not None:
            cand = np.ones(len(matrix), bool)
            cand[si] = False
            cfb = cf_bonus(cooc, si, cand, supporters)
            if cfb is not None:
                score = score + CF_BETA * cfb
        # 학습 결합이 채택되면 **선형 합을 통째로 대체**한다 (계약 §5 처리 4단계).
        # 위에서 만든 항들은 버려지지 않고 모델의 피처로 들어간다.
        if feat is not None:
            cand = np.ones(len(matrix), bool)
            cand[si] = False
            score = ltr[0].predict_proba(feat.make(p, si, cand))[:, 1]
        score[si] = -np.inf                      # 시드는 후보에서 뺀다
        top = np.argsort(-score)[:TOP_K]
        cases.append({
            "persona_id": p["persona_id"],
            "attributes": {a: p[a] for a in ATTRS},
            "seed_product_ids": seeds,
            "scorer": "ltr" if feat is not None else "linear",
            "weights": ({"w1_cosine": w1, "w2_attribute": w2, "w3_prior": w3,
                         "lambda_negative": LAMBDA} if feat is None else None),
            "expected_top10": [{"product_id": e.products[i]["product_id"],
                                "score": round(float(score[i]), 6)} for i in top],
        })
        if len(cases) >= n_persona:
            break

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "vocab_version": e.V["version"],
            "scorer": "ltr" if ltr is not None else "linear",
            "ltr_model": (None if ltr is None else
                          {"n_trees": ltr[1]["n_trees"],
                           "trained_at": ltr[1]["trained_at"],
                           "feature_names": ltr[1]["feature_names"]}),
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
    # ⚠ 골든은 **내보낸 값 그대로** 계산해야 한다.
    #
    # product_feature.jsonl 은 벡터를 소수 6자리, 인기도를 5자리로 반올림해 내보낸다.
    # 자바가 읽는 것은 그 반올림된 값이다. 선형 합에서는 차이가 소수점 아래로
    # 묻혔지만 **학습 결합은 트리라, 피처가 분기점 근처에 놓이면 잎이 통째로
    # 갈린다** — 실제로 한 페르소나에서 두 상품의 순서가 뒤집혔다.
    # 정본 정밀도로 골든을 만들면 자바는 그것을 **영원히 재현할 수 없다.**
    matrix_out = np.round(matrix, 6).astype(np.float32)
    prior_out = np.round(prior, 5).astype(np.float32)
    n_g = export_golden(e, matrix_out, prior_out, affinity, index, personas,
                        os.path.join(a.out, "ranking_golden.json"), a.golden)

    print(f"내보냄 -> {a.out}")
    print(f"  product_feature.jsonl   상품 {n_p}개 x {matrix.shape[1]}차원"
          f" (어휘집 v{e.V['version']})")
    print(f"  attribute_affinity.csv  {n_a:,}행")
    print(f"  ranking_golden.json     페르소나 {n_g}명 x 상위 {TOP_K}개")


if __name__ == "__main__":
    main()
