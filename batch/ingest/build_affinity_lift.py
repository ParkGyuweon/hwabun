# -*- coding: utf-8 -*-
"""
속성 친화도 테이블 (lift 기반) — batch/ingest/data/affinity_lift.csv
================================================================================

상품 200개 x (skin_type / skin_tone / hair_color / eye_color) 세그먼트 = 4,000행.
"이 세그먼트가 이 상품을 평균보다 몇 배 더 고르는가" 를 lift 로 재고, 표본이 적은
칸은 shrinkage 로 1.0 쪽으로 당긴다. 평점 기반도 함께 내어 판별력을 비교한다.

**왜 레포에 있는가** — 이 스크립트는 개인 분석 폴더에만 있었고 레포에서는
`affinity_lift.csv` 를 다시 만들 방법이 없었다. 상품 목록이 바뀌면 이 표도 함께
바뀌어야 하는데, 재생성 경로가 레포 밖에 있으면 둘이 조용히 어긋난다.
(같은 사고가 페르소나 파일에서 이미 한 번 났다.)

입력
    <SEPHORA_DATASET>/reviews_*.csv       리뷰 원본 5개 (.gitignore 대상)
    batch/ingest/data/products_200.json   상품 200개 — member_product_ids 로 조인
출력
    batch/ingest/data/affinity_lift.csv   4,000행. persona_feature.py 가 읽는다
    batch/ingest/data/affinity_power.csv  속성별 판별력 비교 (분석용)

실행
    SEPHORA_DATASET=/path/to/dataset/sephora python batch/ingest/build_affinity_lift.py

소비처: `batch/jobs/persona_feature.py` · `batch/ingest/build_feature_sample.py`
계약: `contracts/recommendation-io-spec.md` §3
"""
import glob, json, os
import collections
import numpy as np
import pandas as pd

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
# 원본 CSV 는 레포에 없다. 위치를 환경변수로 받는다 (build_products_json.py 와 같은 규칙)
SRC = os.environ.get("SEPHORA_DATASET")
if not SRC or not os.path.isdir(SRC):
    raise SystemExit(
        "SEPHORA_DATASET 환경변수에 리뷰 CSV 폴더 경로를 주십시오. "
        "예) SEPHORA_DATASET=.../Research/dataset/sephora")
ART = os.path.join(ROOT, "batch", "ingest", "data")
UF = ["skin_type", "skin_tone", "hair_color", "eye_color"]
K_SHRINK = 50          # lift 축소(shrinkage) 강도: 표본 적은 셀을 1.0으로 당김
CLIP_LO, CLIP_HI = 0.60, 1.60   # lift -> affinity 변환 구간
K_RATING = 20          # 평점 베이지안 스무딩
TONE_BUCKET = {"porcelain": "fair", "fair": "fair", "fairLight": "fair",
               "light": "light", "lightMedium": "light",
               "medium": "medium", "mediumTan": "medium", "olive": "medium",
               "tan": "tan", "deep": "deep", "rich": "deep", "dark": "deep", "ebony": "deep"}

prods = json.load(open(os.path.join(ART, "products_200.json"), encoding="utf-8"))
pid2group = {m: p["product_id"] for p in prods for m in p["_merged"]["member_product_ids"]}
meta = {p["product_id"]: (p["rank"], p["product_name"], p["brand_name"],
                          p["tertiary_category"]) for p in prods}

parts = []
for path in sorted(glob.glob(os.path.join(SRC, "reviews_*.csv"))):
    df = pd.read_csv(path, usecols=["author_id", "product_id", "rating"] + UF, low_memory=False)
    parts.append(df[df[UF].notna().sum(axis=1) == 4])
r = pd.concat(parts, ignore_index=True)
del parts
r = r[r.skin_tone != "notSureST"].copy()
r["skin_tone"] = r.skin_tone.map(TONE_BUCKET)
r["eye_color"] = r.eye_color.replace({"Grey": "gray", "grey": "gray"})
# brunette는 brown의 표기 변형(수집 배치별 라벨 차이). 200개 중 99개는 0%인데
# 4개 상품에서 40%를 넘고 그 상품의 brown은 0.6~10%로 붕괴 -> 동일 범주로 병합
r["hair_color"] = r.hair_color.replace({"brunette": "brown"})
r["group_id"] = r.product_id.map(pid2group)
r = r[r.group_id.notna()]
print(f"리뷰 {len(r):,}건 / 상품 {r.group_id.nunique()}개")

GLOBAL_MEAN = r.rating.mean()
rows = []
summary = []

for attr in UF:
    base = r[attr].value_counts(normalize=True)
    piv_n = r.pivot_table(index="group_id", columns=attr, values="rating", aggfunc="size").fillna(0)
    piv_sum = r.pivot_table(index="group_id", columns=attr, values="rating", aggfunc="sum").fillna(0)
    total = piv_n.sum(axis=1)

    # --- lift (shrinkage 적용) ---
    # 축소된 비율: (관측 + K*기준비율) / (표본수 + K)  -> 표본 적으면 기준비율로 당겨짐
    share_s = (piv_n + K_SHRINK * base) .div(total + K_SHRINK, axis=0)
    lift = share_s.div(base, axis=1)

    # --- 평점 기반 (비교용) ---
    rate = (piv_sum + GLOBAL_MEAN * K_RATING).div(piv_n + K_RATING, axis=0)

    # --- 유의성: 이항 z-score ---
    b_al = base.reindex(piv_n.columns).values          # piv_n 컬럼 순서에 맞춤
    exp = total.values[:, None] * b_al[None, :]
    var = total.values[:, None] * b_al[None, :] * (1 - b_al[None, :])
    z = pd.DataFrame((piv_n.values - exp) / np.sqrt(np.maximum(var, 1e-9)),
                     index=piv_n.index, columns=piv_n.columns)

    eff = float(np.abs(lift.values - 1).mean())
    sig = float((np.abs(z.values) > 3).mean())
    spread = float((lift.max(axis=1) - lift.min(axis=1)).mean())
    rspread = float((rate.max(axis=1) - rate.min(axis=1)).mean())
    summary.append({"attribute": attr, "n_segments": len(base),
                    "lift_effect_size": round(eff, 4),
                    "lift_spread_in_product": round(spread, 4),
                    "significant_cell_pct": round(sig * 100, 1),
                    "rating_spread_in_product": round(rspread, 4),
                    "min_segment_share": round(float(base.min()), 4)})

    for gid in piv_n.index:
        for seg in base.index:
            n = int(piv_n.at[gid, seg])
            rows.append({
                "attribute": attr, "segment": seg,
                "group_id": gid, "rank": meta[gid][0],
                "product_name": meta[gid][1], "brand_name": meta[gid][2],
                "n_reviews": n,
                "share": round(float(piv_n.at[gid, seg] / total[gid]), 5),
                "base_share": round(float(base[seg]), 5),
                "lift": round(float(lift.at[gid, seg]), 4),
                "affinity": round(float(np.clip((lift.at[gid, seg] - CLIP_LO) / (CLIP_HI - CLIP_LO), 0, 1)), 4),
                "rating_affinity": round(float(rate.at[gid, seg] / 5), 4),
                "z_score": round(float(z.at[gid, seg]), 2),
            })

A = pd.DataFrame(rows).sort_values(["attribute", "rank", "segment"])
A.to_csv(os.path.join(ART, "affinity_lift.csv"), index=False, encoding="utf-8-sig")
S = pd.DataFrame(summary)
S.to_csv(os.path.join(ART, "affinity_power.csv"), index=False, encoding="utf-8-sig")

print(f"\n저장: affinity_lift.csv ({len(A):,}행) / affinity_power.csv")
print("\n" + "=" * 92)
print("속성별 판별력 비교  (lift 기반 vs 평점 기반)")
print("=" * 92)
print(f"{'속성':<12}{'세그먼트':>7}{'lift 효과크기':>13}{'상품내 lift 편차':>16}"
      f"{'유의 셀%':>10}{'평점 편차':>11}")
for s in summary:
    print(f"  {s['attribute']:<10}{s['n_segments']:>7}{s['lift_effect_size']:>13.4f}"
          f"{s['lift_spread_in_product']:>16.4f}{s['significant_cell_pct']:>9.1f}%"
          f"{s['rating_spread_in_product']:>11.4f}")

print("\n" + "=" * 92)
print("속성별 극단 사례 (lift 최고)")
print("=" * 92)
for attr in UF:
    sub = A[A.attribute == attr].nlargest(3, "lift")
    print(f"\n[{attr}]")
    for _, x in sub.iterrows():
        print(f"   {x.segment:<12} lift {x.lift:>5.2f}  z={x.z_score:>7.1f}  "
              f"{x.product_name[:44]:<44}")
