# -*- coding: utf-8 -*-
"""신규 브랜드 전용 칸의 계약을 고정한다 (Jira 129).

여기서 막고 싶은 것
  * 전용 칸에 신규가 아닌 상품이 들어오는 것
  * 신규가 없을 때 칸이 비거나 죽는 것 — 일반 칸으로 돌아가야 한다
  * reserved=0 인데 결과가 바뀌는 것 — 기존 골든·대표 지표가 흔들린다
  * 전용 칸 안에서 점수순이 아닌 것
  * 신규가 이미 일반 칸에 뽑혔는데 전용 칸에 또 들어오는 것 (중복)
"""
import os
import sys
import unittest

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

from recommender import (CF_MIN_SUPPORT, Recommender, new_product_mask,  # noqa: E402
                         reserve_slots)


class TestNewProductMask(unittest.TestCase):
    def test_supporters_below_threshold_are_new(self):
        m = new_product_mask(4, supporters=[0, 2, 3, 500])
        self.assertEqual(m.tolist(), [True, True, False, False])
        self.assertEqual(CF_MIN_SUPPORT, 3)

    def test_unknown_brand_is_new(self):
        m = new_product_mask(3, brands=["A", "B", "C"], known_brands={"A", "B"})
        self.assertEqual(m.tolist(), [False, False, True])

    def test_either_condition(self):
        m = new_product_mask(3, supporters=[0, 9, 9], brands=["A", "A", "Z"],
                             known_brands={"A"})
        self.assertEqual(m.tolist(), [True, False, True])

    def test_nothing_known_means_nothing_new(self):
        self.assertFalse(new_product_mask(5).any())


class TestReserveSlots(unittest.TestCase):
    def setUp(self):
        # 점수: 0 > 1 > 2 > 3 > 4 > 5.  신규 = 4, 5, 2
        self.s = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5])
        self.new = np.array([False, False, True, False, True, True])

    def test_reserved_slots_hold_new_products_in_score_order(self):
        out = reserve_slots(self.s, picked=[0, 1, 3], k=5, reserved=2, is_new=self.new)
        self.assertEqual(out[:3], [0, 1, 3])
        self.assertEqual(out[3:], [2, 4])          # 신규 중 점수순 (2 > 4 > 5)

    def test_no_duplicate_when_new_already_picked(self):
        out = reserve_slots(self.s, picked=[0, 2, 1], k=5, reserved=2, is_new=self.new)
        self.assertEqual(out[3:], [4, 5])          # 2 는 이미 있으니 다음 신규
        self.assertEqual(len(set(out)), 5)

    def test_falls_back_to_general_when_new_is_short(self):
        new = np.array([False, False, False, False, True, False])
        out = reserve_slots(self.s, picked=[0, 1, 2], k=5, reserved=2, is_new=new)
        self.assertEqual(out, [0, 1, 2, 4, 3])     # 신규 4 하나, 나머지는 일반 점수순

    def test_no_new_at_all_returns_general_top_k(self):
        out = reserve_slots(self.s, picked=[0, 1, 2], k=5, reserved=2,
                            is_new=np.zeros(6, bool))
        self.assertEqual(out, [0, 1, 2, 3, 4])

    def test_fallback_follows_given_order_not_raw_score(self):
        # MMR 이 이어 간 순서가 [0,1,2,5,4] 라면 신규가 없을 때 5 가 4 보다 먼저다
        out = reserve_slots(self.s, picked=[0, 1, 2], k=5, reserved=2,
                            is_new=np.zeros(6, bool), fallback=[0, 1, 2, 5, 4, 3])
        self.assertEqual(out, [0, 1, 2, 5, 4])

    def test_skips_blocked_minus_inf(self):
        s = self.s.copy(); s[4] = -np.inf
        out = reserve_slots(s, picked=[0, 1, 3], k=5, reserved=2, is_new=self.new)
        self.assertNotIn(4, out)


class TestRecommenderRank(unittest.TestCase):
    """실제 Recommender.rank 경로 — 선형 결합, 작은 카탈로그."""

    def setUp(self):
        rng = np.random.default_rng(3)
        M = rng.random((8, 4)).astype(np.float32)
        M /= np.linalg.norm(M, axis=1, keepdims=True)
        self.M = M
        self.idx = {f"P{i}": i for i in range(8)}
        prior = np.linspace(0.2, 1.0, 8).astype(np.float32)
        brands = ["A", "A", "B", "B", "C", "C", "NEW1", "NEW2"]
        self.rec = Recommender(M, self.idx, prior, brands=brands,
                               known_brands={"A", "B", "C"},
                               supporters=np.array([50, 50, 50, 50, 50, 50, 0, 1]))
        from user_vector import UserVector
        self.st = UserVector()
        self.st.observe({"event_name": "add_to_cart", "product_id": "P0", "properties": {}})

    def test_reserved_zero_is_unchanged(self):
        a = self.rec.rank(self.st, k=5)
        b = self.rec.rank(self.st, k=5, reserved=0)
        self.assertEqual(a, b)

    def test_reserved_slots_are_new_brand_products(self):
        out = self.rec.rank(self.st, k=5, reserved=2, flags=True)
        self.assertEqual(len(out), 5)
        flagged = [g for g, _, f in out if f]
        self.assertEqual(len(flagged), 2)
        self.assertTrue(set(flagged) <= {"P6", "P7"})
        self.assertEqual(len({g for g, _, _ in out}), 5)

    def test_general_part_equals_mmr_of_k_minus_r(self):
        full = [g for g, _ in self.rec.rank(self.st, k=5, reserved=2)]
        head = [g for g, _ in self.rec.rank(self.st, k=3, reserved=0)]
        self.assertEqual(full[:3], head)

    def test_no_new_products_falls_back(self):
        rec = Recommender(self.M, self.idx, np.linspace(0.2, 1.0, 8).astype(np.float32),
                          supporters=np.full(8, 500))
        self.assertEqual(rec.rank(self.st, k=5, reserved=2),
                         rec.rank(self.st, k=5, reserved=0))

    def test_reserved_capped_at_k(self):
        out = self.rec.rank(self.st, k=3, reserved=10)
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
