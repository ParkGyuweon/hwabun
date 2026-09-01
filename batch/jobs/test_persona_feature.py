"""페르소나 속성 피처의 계약 준수와 표기 정규화를 고정한다.

여기서 막고 싶은 사고는 두 가지다.
  * 정규화 표가 테이블 생성 쪽과 어긋나 조회가 조용히 빗나가는 것
  * 상품 순서가 어긋나 점수가 엉뚱한 상품에 붙는 것
둘 다 예외가 안 나서 평가 수치가 조금 이상해질 뿐이라 알아채기 어렵다.
"""
import csv
import os
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

if np is not None:
    from batch.jobs.persona_feature import (
        AFFINITY_CSV,
        ATTRS,
        NEUTRAL,
        AffinityTable,
        normalize,
        weights_for,
    )

EXPECTED_SEGMENTS = {"skin_type": 4, "skin_tone": 5, "hair_color": 6, "eye_color": 5}


def read_csv_rows():
    with open(AFFINITY_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@unittest.skipIf(np is None, "numpy is required")
class AffinityTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_csv_rows()
        cls.products = sorted({r["group_id"] for r in cls.rows})
        cls.index = {g: i for i, g in enumerate(cls.products)}
        cls.table = AffinityTable(cls.index)

    def test_shape_matches_contract(self):
        """4,000행 = 200상품 x 20세그먼트. 결측이 있으면 안 된다"""
        self.assertEqual(200, len(self.products))
        self.assertEqual(4000, len(self.rows))
        self.assertEqual(4000, self.table.n_rows)
        for attr, count in EXPECTED_SEGMENTS.items():
            self.assertEqual(count, len(self.table.segments(attr)), attr)
        self.assertEqual(20, sum(len(self.table.segments(a)) for a in ATTRS))

    def test_values_in_range(self):
        for attr in ATTRS:
            for seg, v in self.table.table[attr].items():
                self.assertEqual(len(self.products), len(v), f"{attr}/{seg}")
                self.assertTrue(bool(np.all((v >= 0) & (v <= 1))), f"{attr}/{seg}")

    def test_weights_sum_to_one(self):
        for skin_type in ("dry", "oily", "normal", "combination"):
            self.assertAlmostEqual(1.0, sum(weights_for(skin_type).values()), places=9)

    def test_combination_moves_type_weight_to_tone(self):
        """복합성은 skin_type 을 쓰지 않고 그 몫을 skin_tone 으로 넘긴다"""
        w = weights_for("combination")
        self.assertEqual(0.0, w["skin_type"])
        self.assertEqual(0.80, w["skin_tone"])
        self.assertEqual(0.40, weights_for("dry")["skin_type"])

    def test_normalize_alias(self):
        got = normalize({"skin_type": "dry", "skin_tone": "lightMedium",
                         "hair_color": "brunette", "eye_color": "Grey"})
        self.assertEqual({"skin_type": "dry", "skin_tone": "light",
                          "hair_color": "brown", "eye_color": "gray"}, got)

    def test_vector_matches_csv_by_hand(self):
        """CSV 값을 직접 가중합한 것과 같아야 한다 (테이블 동등성)"""
        persona = {"skin_type": "oily", "skin_tone": "mediumTan",
                   "hair_color": "black", "eye_color": "brown"}
        seg = normalize(persona)
        w = weights_for(persona["skin_type"])
        want = np.zeros(len(self.products), np.float32)
        for r in self.rows:
            if seg.get(r["attribute"]) == r["segment"]:
                want[self.index[r["group_id"]]] += (
                    w[r["attribute"]] * float(r["affinity"]))
        np.testing.assert_allclose(want, self.table.vector(persona), atol=1e-6)

    def test_unknown_segment_falls_back_to_neutral(self):
        """오타나 신규 값이 와도 죽지 않고, 그 축만 중립으로 들어간다"""
        base = {"skin_type": "dry", "skin_tone": "light",
                "hair_color": "black", "eye_color": "brown"}
        unknown = {**base, "hair_color": "teal", "eye_color": "violet"}
        got = self.table.vector(unknown)
        want = (self.table.vector(base)
                - 0.10 * self.table.table["hair_color"]["black"]
                - 0.10 * self.table.table["eye_color"]["brown"]
                + 0.20 * NEUTRAL)
        np.testing.assert_allclose(want, got, atol=1e-6)

    def test_respects_given_product_order(self):
        """상품 순서를 뒤집어도 상품별 값은 같아야 한다"""
        flipped = {g: i for i, g in enumerate(reversed(self.products))}
        other = AffinityTable(flipped)
        persona = {"skin_type": "combination", "skin_tone": "deep",
                   "hair_color": "red", "eye_color": "green"}
        a, b = self.table.vector(persona), other.vector(persona)
        for gid in self.products[:50]:
            self.assertAlmostEqual(float(a[self.index[gid]]),
                                   float(b[flipped[gid]]), places=6)


if __name__ == "__main__":
    unittest.main()
