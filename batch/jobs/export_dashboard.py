# -*- coding: utf-8 -*-
"""대시보드용 파생 산출물 — 프론트 요청 4종 (Jira 176).

무엇을 내보내는가
    프론트가 2026-09-03 에 요청한 것들이다 (`docs/dashboard/data-event-backlog.md`).
    **전부 이미 계산되고 있는데 밖으로 안 나가던 값**이다. 새로 만드는 것은
    ③ 하나뿐이다.

    ① 상품 x 성분 **위치가중값**
       `product_encoder.ingredient_values()` 안에서 계산되고 벡터에 들어간 뒤
       **버려진다.** 대시보드가 "이 상품에서 어떤 성분이 앞쪽에 있나" 를 말하려면
       그 값이 필요하다. 태그로 표시된 성분은 1.0, 전성분에서만 찾은 것은 위치
       기반 감쇠다 — **1.0 이 곧 "함량이 많다" 가 아니다** (§주의).

    ② 상품 x concern 상위 2축
       `concern_from_reviews.npz` 에 200x9 로 이미 있다. 대시보드는 상품마다
       "리뷰가 말하는 고민 두 개" 만 쓰므로 상위 2개로 줄여 내보낸다.

    ③ 성분 x 피부타입 lift  **(신규 · 파생)**
       기존 두 표의 곱이다 — `상품x성분 위치가중값` 과 `상품x세그먼트 lift`.
       "지성 피부가 반응한 상품에 어떤 성분이 많은가" 를 말할 수 있게 된다.
       **곱이므로 인과가 아니다** (§주의).

    ④ `affinity_lift.csv` 는 이미 나가고 있어 여기서 다시 만들지 않는다.

출력
    batch/ingest/data/serving/product_ingredient_position.csv
    batch/ingest/data/serving/product_concern_top2.csv
    batch/ingest/data/serving/ingredient_skin_lift.csv

실행
    python batch/jobs/export_dashboard.py
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)

from product_encoder import Encoder                     # noqa: E402

DATA = os.path.join(ROOT, "batch", "ingest", "data")
OUT_DIR = os.path.join(DATA, "serving")
CONCERN_NPZ = os.path.join(DATA, "concern_from_reviews.npz")
AFFINITY = os.path.join(DATA, "affinity_lift.csv")

# 피부타입 네 값만 쓴다. 성분과 묶어 말이 되는 축이 이것뿐이다 —
# 눈동자색·머리색과 성분을 곱하면 숫자는 나오지만 문장이 안 된다.
SKIN_TYPES = ("combination", "dry", "normal", "oily")

# lift 가 이 값을 넘는 (상품, 세그먼트) 만 ③ 의 입력으로 쓴다.
# 1.0 은 평균이라 그 근처를 섞으면 신호가 묽어진다.
LIFT_MIN = 1.2

# ③ 에서 이 개수보다 적은 상품으로 만들어진 칸은 내보내지 않는다.
# 상품 두셋으로 "지성 피부는 세라마이드" 라고 말하면 안 된다.
MIN_SUPPORT = 5


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def export_ingredient_position(enc, path):
    """① 상품 x 성분 위치가중값 — 인코더 안에서 버려지던 값"""
    rows = []
    for p in enc.products:
        vals = enc.ingredient_values(p)
        tagged = {h for h in p["highlights"] if h in enc.tag_ing}
        for name, v in sorted(vals.items(), key=lambda kv: -kv[1]):
            rows.append([p["product_id"], p["product_name"], p["brand_name"],
                         name, round(float(v), 4),
                         "tag" if name in tagged else "parsed"])
    return write_csv(path,
                     ["product_id", "product_name", "brand_name",
                      "ingredient", "position_weight", "source"], rows)


def export_concern_top2(enc, path, top=2):
    """② 상품 x concern 상위 2축 — npz 를 줄여서 낸다"""
    if not os.path.exists(CONCERN_NPZ):
        print("  concern_from_reviews.npz 없음 — 건너뜁니다")
        return 0
    d = np.load(CONCERN_NPZ, allow_pickle=True)
    gid = [str(x) for x in d["group_id"]]
    axes = [str(x) for x in d["axes"]]
    score = np.asarray(d["score"], np.float64)
    meta = {p["product_id"]: p for p in enc.products}
    rows = []
    for i, g in enumerate(gid):
        p = meta.get(g)
        if p is None:
            continue
        order = np.argsort(-score[i])[:top]
        for rank, j in enumerate(order, 1):
            if score[i][j] <= 0:
                continue                       # 0 이면 "그 고민을 말한 리뷰가 없다"
            rows.append([g, p["product_name"], p["brand_name"], rank,
                         axes[j], round(float(score[i][j]), 4)])
    return write_csv(path,
                     ["product_id", "product_name", "brand_name", "rank",
                      "concern", "score"], rows)


def export_ingredient_skin_lift(enc, path):
    """③ 성분 x 피부타입 — 위치가중값과 세그먼트 lift 의 곱 (신규)"""
    if not os.path.exists(AFFINITY):
        print("  affinity_lift.csv 없음 — 건너뜁니다")
        return 0
    # 상품 -> 피부타입 -> lift
    by_seg = defaultdict(dict)
    with open(AFFINITY, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            seg = r.get("segment")
            gid = r.get("group_id")
            if seg not in SKIN_TYPES or not gid:
                continue
            try:
                lift = float(r.get("lift") or 0)
            except ValueError:
                continue
            if lift >= LIFT_MIN:
                by_seg[seg][gid] = lift

    ing = {p["product_id"]: enc.ingredient_values(p) for p in enc.products}
    rows = []
    for seg in SKIN_TYPES:
        acc, support = defaultdict(float), defaultdict(set)
        for gid, lift in by_seg.get(seg, {}).items():
            for name, w in ing.get(gid, {}).items():
                acc[name] += w * lift
                support[name].add(gid)
        if not acc:
            continue
        # 정규화 — 세그먼트마다 상품 수가 달라 절대값을 나란히 놓으면 안 된다
        total = sum(acc.values()) or 1.0
        for name, v in sorted(acc.items(), key=lambda kv: -kv[1]):
            n = len(support[name])
            if n < MIN_SUPPORT:
                continue
            rows.append([seg, name, round(v / total, 5), n])
    # 비어 있는 피부타입을 알린다. 조용히 빠지면 대시보드에 그 세그먼트만
    # 아무것도 안 뜨는데 화면에는 이유가 안 나온다.
    empty = [st for st in SKIN_TYPES
             if not any(r[0] == st for r in rows)]
    if empty:
        print(f"  ⚠️ 결과가 비어 있는 피부타입: {', '.join(empty)}")
        print(f"     그 세그먼트는 모집단 비중이 커서 base_share 가 높고, "
              f"lift >= {LIFT_MIN} 를 넘는 상품이 적습니다.")
        print(f"     **lift 의 성질이지 데이터가 없는 것이 아닙니다.** "
              f"대시보드는 '비교할 만큼 두드러진 성분 없음' 으로 표시하십시오.")
    return write_csv(path,
                     ["skin_type", "ingredient", "share", "n_products"], rows)


def main():
    ap = argparse.ArgumentParser()
    a = ap.parse_args()

    enc = Encoder()
    os.makedirs(OUT_DIR, exist_ok=True)

    n1 = export_ingredient_position(
        enc, os.path.join(OUT_DIR, "product_ingredient_position.csv"))
    n2 = export_concern_top2(
        enc, os.path.join(OUT_DIR, "product_concern_top2.csv"))
    n3 = export_ingredient_skin_lift(
        enc, os.path.join(OUT_DIR, "ingredient_skin_lift.csv"))

    print(f"① product_ingredient_position.csv  {n1:,}행")
    print(f"② product_concern_top2.csv         {n2:,}행")
    print(f"③ ingredient_skin_lift.csv         {n3:,}행 "
          f"(lift>={LIFT_MIN} · 상품 {MIN_SUPPORT}개 이상만)")
    print(f"④ affinity_lift.csv 는 이미 나가고 있어 다시 만들지 않습니다")
    print()
    print("⚠️ 대시보드 문구로 쓸 때 주의")
    print("  ① position_weight 1.0 은 **태그로 표시된 성분**이지 함량이 아닙니다.")
    print("     전성분 순서는 함량순이지만 1% 미만은 순서가 자유라 하위는 뜻이 약합니다")
    print("  ③ 은 두 표의 **곱**입니다. '지성 피부에 세라마이드가 좋다' 가 아니라")
    print("     '지성 피부가 반응한 상품에 세라마이드가 많더라' 입니다. 인과가 아닙니다")


if __name__ == "__main__":
    main()
