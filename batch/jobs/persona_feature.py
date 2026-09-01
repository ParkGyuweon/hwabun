"""
페르소나 속성 피처 — 사람의 프로필을 상품별 친화도 점수로 바꾼다.

    attr_affinity(u, i) = w_type x A[i][skin_type][u.skin_type]
                        + w_tone x A[i][skin_tone][u.skin_tone]
                        + 0.10   x A[i][hair_color][u.hair_color]
                        + 0.10   x A[i][eye_color][u.eye_color]

행동 피처(user_vector.py)와 달리 **상품 벡터 공간의 벡터가 아니다.** 피부 타입은
상품과 같은 공간에 없기 때문에, 사람을 벡터로 만드는 대신 "이 사람 기준 각 상품의
점수" (상품수,) 를 직접 만든다. 근거는 리뷰에서 관측한 lift 다 —
건성이 전체의 19.2% 인데 어떤 상품의 리뷰어는 38.7% 가 건성이면 lift 1.98 이다.

**행동이 0건이어도 계산된다.** 그래서 시드가 적은 구간을 이 항이 떠받친다.
행동이 쌓일수록 recommender.SCHEDULE 이 이 항의 몫을 코사인으로 넘긴다.

계약: contracts/recommendation-io-spec.md (친화도 테이블 · 조회 가중치)
원본: batch/ingest/data/affinity_lift.csv (4,000행 = 200상품 x 20세그먼트)
"""
import csv
import json
import os

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
AFFINITY_CSV = os.path.join(ROOT, "batch", "ingest", "data", "affinity_lift.csv")

ATTRS = ("skin_type", "skin_tone", "hair_color", "eye_color")

# 셀이 없을 때의 값. 0 을 쓰면 "표본이 없다" 가 "안 맞는다" 로 둔갑한다
NEUTRAL = 0.5

# ── 표기 정규화 ──────────────────────────────────────────────────────────
# 리뷰 원본의 표기를 친화도 테이블의 세그먼트 이름에 맞춘다.
# 이 표는 테이블을 만들 때(build_affinity_lift) 쓴 것과 **같아야 한다.**
# 어긋나면 조회가 조용히 빗나가 전원이 NEUTRAL 을 받는다.
TONE_BUCKET = {
    "porcelain": "fair", "fair": "fair", "fairLight": "fair",
    "light": "light", "lightMedium": "light",
    "medium": "medium", "mediumTan": "medium", "olive": "medium",
    "tan": "tan",
    "deep": "deep", "rich": "deep", "dark": "deep", "ebony": "deep",
}
EYE_ALIAS = {"Grey": "gray", "grey": "gray"}
# brunette 는 brown 의 표기 변형이다(수집 배치별 라벨 차이). 200개 중 99개는 0%
# 인데 4개 상품에서 40% 를 넘고 그 상품의 brown 은 0.6~10% 로 붕괴한다
HAIR_ALIAS = {"brunette": "brown"}

# ── 조회 가중치 ──────────────────────────────────────────────────────────
# 복합성(전체의 55.3%)은 skin_type 항을 쓰지 않는다. 200개 상품 전부
# lift 0.85~1.19(표준편차 0.053)로 판별력이 없어서다. 그 몫은 skin_tone 으로 간다.
WEIGHTS_DEFAULT = {"skin_type": 0.40, "skin_tone": 0.40,
                   "hair_color": 0.10, "eye_color": 0.10}
WEIGHTS_COMBINATION = {"skin_type": 0.00, "skin_tone": 0.80,
                       "hair_color": 0.10, "eye_color": 0.10}


def normalize(persona):
    """페르소나 속성 -> 테이블 세그먼트 이름. 모르는 값은 그대로 두고 조회에서 걸린다"""
    return {
        "skin_type": persona.get("skin_type"),
        "skin_tone": TONE_BUCKET.get(persona.get("skin_tone"), persona.get("skin_tone")),
        "hair_color": HAIR_ALIAS.get(persona.get("hair_color"), persona.get("hair_color")),
        "eye_color": EYE_ALIAS.get(persona.get("eye_color"), persona.get("eye_color")),
    }


def weights_for(skin_type):
    return dict(WEIGHTS_COMBINATION if skin_type == "combination" else WEIGHTS_DEFAULT)


class AffinityTable:
    """친화도 테이블을 상품 순서에 맞춘 배열로 들고 있다가 페르소나마다 합성한다.

    `index` 는 product_id -> 행 번호다. Recommender 가 쓰는 것과 **같은 순서**여야
    하므로 호출하는 쪽에서 넘겨준다. 순서가 어긋나면 점수가 엉뚱한 상품에 붙는데
    예외가 안 나서 알아채기 어렵다.
    """

    def __init__(self, index, path=AFFINITY_CSV):
        self.index = index
        self.n = len(index)
        self.table = {a: {} for a in ATTRS}
        self.n_rows = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                attr, seg, gid = row["attribute"], row["segment"], row["group_id"]
                if attr not in self.table or gid not in index:
                    continue
                v = self.table[attr].get(seg)
                if v is None:
                    # 표에 없는 (상품, 세그먼트) 조합은 중립으로 남는다
                    v = np.full(self.n, NEUTRAL, np.float32)
                    self.table[attr][seg] = v
                v[index[gid]] = float(row["affinity"])
                self.n_rows += 1

    def segments(self, attr):
        return sorted(self.table[attr])

    def vector(self, persona):
        """페르소나 -> (상품수,) 친화도 점수. 0~1"""
        seg = normalize(persona)
        w = weights_for(persona.get("skin_type"))
        out = np.zeros(self.n, np.float32)
        for attr, weight in w.items():
            if not weight:
                continue
            v = self.table[attr].get(seg[attr])
            # 모르는 세그먼트(오타·신규 값)는 중립으로 둔다. 여기서 죽으면
            # 프로필 하나 때문에 추천 전체가 멈춘다
            out += weight * (v if v is not None else np.full(self.n, NEUTRAL, np.float32))
        return out

    def __call__(self, persona):
        """Recommender(affinity=...) 에 그대로 넘길 수 있게 한다"""
        return self.vector(persona)


def load(index=None, path=AFFINITY_CSV):
    """상품 순서를 안 주면 product_encoder 의 순서를 쓴다"""
    if index is None:
        import sys
        sys.path.insert(0, BD)
        from product_encoder import Encoder
        e = Encoder()
        index = {p["product_id"]: i for i, p in enumerate(e.products)}
    return AffinityTable(index, path)


if __name__ == "__main__":
    A = load()
    print(f"친화도 테이블 {A.n_rows:,}행 · 상품 {A.n}개")
    total = 0
    for attr in ATTRS:
        segs = A.segments(attr)
        total += len(segs)
        print(f"  {attr:<12} {len(segs)}세그먼트  {', '.join(segs)}")
    print(f"  합계 {total}세그먼트 x {A.n}상품 = {total * A.n:,}칸")

    sample = {"skin_type": "dry", "skin_tone": "lightMedium",
              "hair_color": "brunette", "eye_color": "Grey"}
    v = A.vector(sample)
    print(f"\n예시 페르소나 {sample}")
    print(f"  정규화 {normalize(sample)}")
    print(f"  가중치 {weights_for(sample['skin_type'])}")
    print(f"  점수 min {v.min():.4f} / 평균 {v.mean():.4f} / max {v.max():.4f}")
