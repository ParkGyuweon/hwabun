# -*- coding: utf-8 -*-
"""eval_baselines 의 순수 함수 — 작은 고정 데이터로 확인한다 (레포 데이터 없이 돈다)."""
import os
import sys
import unittest

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
sys.path.insert(0, os.path.normpath(os.path.join(BD, "..", "..")))

import eval_baselines as B  # noqa: E402

INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}
PERSONAS = [
    {"reviews": [{"group_id": "A", "rating": 5, "submission_time": "2020-01-01"},
                 {"group_id": "B", "rating": 1, "submission_time": "2021-01-01"},
                 {"product_id": "A", "rating": 4, "submission_time": "2022-01-01"}]},
    {"reviews": [{"group_id": "A", "rating": 5, "submission_time": "2020-06-01"},
                 {"group_id": "B", "rating": 2, "submission_time": "2020-06-01"},
                 {"group_id": "C", "rating": 3, "is_recommended": True,
                  "submission_time": "2023-01-01"},
                 {"group_id": "Z", "rating": 5, "submission_time": "2020-01-01"}]},   # 카탈로그 밖
]


class PopularityTest(unittest.TestCase):
    def test_counts_all_time(self):
        d = B.review_dates(PERSONAS, INDEX)
        self.assertEqual(B.popularity(d, INDEX).tolist(), [3, 2, 1, 0])

    def test_cutoff_counts_only_strictly_before(self):
        d = B.review_dates(PERSONAS, INDEX)
        # 2020-06-01 당일 리뷰는 세지 않는다 (target 과 같은 날도 미래로 본다)
        self.assertEqual(B.popularity(d, INDEX, "2020-06-01").tolist(), [1, 0, 0, 0])
        self.assertEqual(B.popularity(d, INDEX, "2021-06-01").tolist(), [2, 2, 0, 0])

    def test_positive_only_uses_contract_rule(self):
        d = B.review_dates(PERSONAS, INDEX, positive_only=True)
        # 3점 + 추천 은 긍정, 1~2점은 아니다 (계약 §7.1.1)
        self.assertEqual(B.popularity(d, INDEX).tolist(), [3, 0, 1, 0])


class RankingTest(unittest.TestCase):
    def test_order_ties_are_deterministic(self):
        pop = np.array([2, 5, 2, 0])
        loves = np.array([1, 0, 9, 0])
        self.assertEqual(B.order_by(pop, loves).tolist(), [1, 2, 0, 3])
        self.assertEqual(B.order_by(pop).tolist(), [1, 0, 2, 3])

    def test_rank_skips_seen_items(self):
        order = np.array([1, 2, 0, 3])
        cand = np.array([True, False, True, True])     # 1번 상품은 이미 본 상품(seed)
        self.assertEqual(B.rank_in(order, cand, 2), 1)
        self.assertEqual(B.rank_in(order, cand, 0), 2)
        self.assertEqual(B.rank_in(order, cand, 3), 3)
        with self.assertRaises(ValueError):
            B.rank_in(order, cand, 1)

    def test_random_expectation(self):
        r, mrr, ndcg = B.random_expectation(4, k=2)
        self.assertAlmostEqual(r, 0.5)
        self.assertAlmostEqual(mrr, (1 + 1 / 2 + 1 / 3 + 1 / 4) / 4)
        self.assertAlmostEqual(ndcg, (1 + 1 / np.log2(3)) / 4)
        self.assertEqual(B.random_expectation(5, k=10)[0], 1.0)


class MetricTest(unittest.TestCase):
    def test_summarize_matches_definitions(self):
        m = B.summarize([True, False, True, False], [1, 20, 3, 11], k=10)
        self.assertAlmostEqual(m["recall"], 50.0)
        self.assertAlmostEqual(m["mrr"], (1 + 1 / 20 + 1 / 3 + 1 / 11) / 4)
        self.assertAlmostEqual(m["ndcg"], (1 + 1 / np.log2(4)) / 4)
        self.assertLessEqual(m["ci"][0], 50.0)
        self.assertGreaterEqual(m["ci"][1], 50.0)

    def test_paired_diff(self):
        d, lo, hi = B.paired_diff([1, 1, 1, 0], [0, 1, 0, 0])
        self.assertAlmostEqual(d, 50.0)
        self.assertLessEqual(lo, d)
        self.assertGreaterEqual(hi, d)


if __name__ == "__main__":
    unittest.main()
