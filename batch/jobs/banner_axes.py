# -*- coding: utf-8 -*-
"""배너 축 6종 상품 목록 — 화면이 "왜 이 상품인지" 를 말할 수 있게 한다.

무엇을 만드는가
    계약 `recommendation-io-spec.md` §5-1 의 `banners[]` 에 실을 상품 목록을
    축별로 만든다. 축은 여섯 가지다.

        concern      피부 고민 9종      "모공이 고민이신 분께"
        ingredient   성분 30종          "나이아신아마이드가 들어간"
        clean        저자극·클린 16종    "비건 제품 중에서"
        price_bin    가격대 5구간        "3만원대에서 고르면"
        category     카테고리 8/19종     "세럼 중에서"
        segment      피부 타입 반응 20종  "지성 피부에서 반응이 좋았던"

    앞의 다섯은 **상품이 그 속성을 가졌는가**이고, `segment` 만 **같은 세그먼트
    사람들이 실제로 반응했는가**(친화도 lift)다. 문구가 가장 세고 자사몰에서는
    못 하는 이야기라 서비스 차별점과 맞는다.

배너는 정확도 장치가 아니다
    축 기준으로 배너 칸을 뽑아도 그냥 11등을 보여주는 것보다 못하다
    (+0.50%p vs +1.35%p, `evaluation-framework.md` 부록 Q ②). 사용자의 시드가
    특정 축에서 일관되지 않기 때문이다. **이 산출물의 값은 정확도가 아니라
    "이유를 말할 수 있는 것" 과 "신규 브랜드에 자리를 주는 것" 이다.**

    그래서 축 안에서의 순위는 **추천 점수 그대로** 쓴다. 축은 후보를 거르는
    필터이지 점수를 바꾸는 장치가 아니다.

`banner_value` 는 어휘집 원문
    화면에 보이는 한국어 라벨이 아니라 `product-feature-vocab.json` 의 문자열을
    그대로 쓴다. 한 글자만 달라도 그 축이 통째로 매칭 실패하는데 **화면에는
    아무 표시도 안 난다.** 한국어는 `product-form-labels-ko.json` 이 맡는다.

출력
    batch/ingest/data/serving/banner_axes.json

실행
    python batch/jobs/banner_axes.py [--top 20]
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)

from product_encoder import Encoder                     # noqa: E402

DATA = os.path.join(ROOT, "batch", "ingest", "data")
OUT = os.path.join(DATA, "serving", "banner_axes.json")
AFFINITY = os.path.join(DATA, "affinity_lift.csv")
LABELS = os.path.join(ROOT, "contracts", "product-form-labels-ko.json")

# 축 -> 어휘집 블록. `category` 는 두 블록을 합치고 `segment` 는 친화도에서 온다.
BLOCK_AXES = ["concern", "ingredient", "clean", "price_bin"]
CAT_BLOCKS = ["secondary_category", "tertiary_category"]

# 배너 한 칸에 상품이 하나면 되지만, 소비자가 중복 배제·품절 대체를 할 수 있게
# 여유분을 준다. 20개면 한 축이 통째로 품절이 아닌 한 채워진다.
TOP_DEFAULT = 20

# lift 가 이 값을 넘어야 "그 세그먼트에서 반응이 좋았다" 고 말할 수 있다.
# 1.0 은 평균이므로 그 근처를 문구로 쓰면 거짓말이 된다.
SEGMENT_LIFT_MIN = 1.2

# 상품이 이보다 적으면 배너로 쓰면 안 된다 — 매번 같은 상품이 뜬다.
# 지우지 않고 `too_thin` 으로 표시만 한다.
MIN_PRODUCTS = 5


def block_slices(enc):
    """블록 이름 -> 벡터 차원 구간"""
    from product_encoder import ORDER
    out, off = {}, 0
    for nm in ORDER:
        w = 1 if nm == "rating" else len(enc.blk[nm]["vocab"])
        out[nm] = (off, off + w)
        off += w
    return out


def axis_members(enc, matrix):
    """(축, 값) -> 그 값을 가진 상품 index 목록"""
    sl = block_slices(enc)
    members = {}
    for nm in BLOCK_AXES + CAT_BLOCKS:
        lo, hi = sl[nm]
        vocab = enc.blk[nm]["vocab"]
        blk = matrix[:, lo:hi]
        axis = "category" if nm in CAT_BLOCKS else nm
        for j, val in enumerate(vocab):
            idx = [int(i) for i in np.where(blk[:, j] > 0)[0]]
            if idx:
                members.setdefault((axis, val), []).extend(idx)
    return members


def segment_members(index):
    """세그먼트 -> lift 가 임계 이상인 상품. `affinity_lift.csv` 에서 읽는다"""
    out = {}
    if not os.path.exists(AFFINITY):
        return out
    with open(AFFINITY, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            gid = r.get("group_id")
            seg = r.get("segment")
            if not gid or not seg or gid not in index:
                continue
            try:
                lift = float(r.get("lift") or 0)
            except ValueError:
                continue
            if lift >= SEGMENT_LIFT_MIN:
                out.setdefault(("segment", seg), []).append((index[gid], lift))
    # lift 순으로 정렬해 둔다 — 세그먼트 축만은 반응 세기가 곧 문구의 근거다
    return {k: [i for i, _ in sorted(v, key=lambda t: -t[1])] for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=TOP_DEFAULT,
                    help="축마다 내려줄 상품 수 (소비자가 중복 배제할 여유분)")
    a = ap.parse_args()

    enc = Encoder()
    M = np.asarray(enc.matrix(), np.float32)
    P = enc.products
    prior = np.asarray(enc.prior(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(P)}

    members = axis_members(enc, M)
    members.update(segment_members(index))

    # 라벨 파일은 **블록별 중첩**이다. 평탄하게 찾으면 전부 못 찾는다.
    #   {"concern": [{"value": "Pores", "ko": "모공"}, ...], "segment": [...]}
    labels = {}
    if os.path.exists(LABELS):
        raw = json.load(open(LABELS, encoding="utf-8"))
        for blk, rows_ in raw.items():
            if not isinstance(rows_, list):
                continue
            axis = "category" if blk.endswith("_category") else blk
            for r in rows_:
                if isinstance(r, dict) and "value" in r:
                    labels[(axis, r["value"])] = r.get("ko")

    axes = {}
    for (axis, val), idx in sorted(members.items()):
        uniq = sorted(set(idx))
        # 사용자별 추천 점수는 서빙 시점에 곱해진다. 여기서는 **후보와 그 순서의
        # 기본값**만 준다 — prior 순이다. 소비자가 점수를 갖고 있으면 그걸로
        # 다시 정렬하면 된다.
        # segment 는 lift 순(반응 세기가 곧 문구의 근거), 나머지는 prior 순
        order = uniq if axis == "segment" else sorted(uniq, key=lambda i: -prior[i])
        picked = order[:a.top]
        axes.setdefault(axis, []).append({
            "banner_value": val,                 # 어휘집 원문 그대로
            "label_ko": labels.get((axis, val)),
            "n_products": len(uniq),
            # 상품이 너무 적으면 배너로 쓰면 안 된다 — 매번 같은 상품이 뜬다.
            # 지우지 않고 표시만 한다. 소비자가 쓸지 말지 정한다
            "too_thin": len(uniq) < MIN_PRODUCTS,
            "product_ids": [P[i]["product_id"] for i in picked],
        })

    doc = {
        "version": "banner-axes-v1",
        "vocab_version": enc.V.get("version"),
        "top": a.top,
        "segment_lift_min": SEGMENT_LIFT_MIN,
        "note": ("banner_value 는 어휘집 원문이다. 한국어는 label_ko 또는 "
                 "contracts/product-form-labels-ko.json 을 쓴다. product_ids 의 "
                 "기본 순서는 prior(인기도)이고, segment 축만 lift 순이다. "
                 "사용자별 추천 점수가 있으면 그것으로 다시 정렬한다."),
        "axes": axes,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    print(f"저장: {os.path.relpath(OUT, ROOT)}")
    for axis in ("concern", "ingredient", "clean", "price_bin", "category",
                 "segment"):
        vals = axes.get(axis, [])
        if not vals:
            print(f"  {axis:<12} 없음")
            continue
        thin = [v["banner_value"] for v in vals if v["too_thin"]]
        print(f"  {axis:<12} 값 {len(vals):>3}종 · "
              f"상품 중앙 {int(np.median([v['n_products'] for v in vals])):>3}개"
              + (f" · **too_thin {len(thin)}종**" if thin else ""))
    miss = [v["banner_value"] for vs in axes.values() for v in vs
            if v["label_ko"] is None]
    if miss:
        print(f"\n한국어 라벨 없는 값 {len(miss)}개 — 소비자가 문구를 채워야 한다:")
        print("  " + ", ".join(map(str, miss[:12]))
              + (" ..." if len(miss) > 12 else ""))


if __name__ == "__main__":
    main()
