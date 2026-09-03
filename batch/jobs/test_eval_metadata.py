"""평가 seed / target 정의를 한 곳에 고정한다.

축마다 각자 계산하다 9,900명 중 792명(8.0%)이 다른 target 을 맞히고 있었다.
그 정의가 다시 갈라지지 않게 여기서 못 박는다.

**2026-09-03.** 계약 §7.1 과 정본이 **같은 정답**을 고르게 맞췄다.
target 은 정렬 순서에서 **가장 마지막 긍정 리뷰**이고, 계약이 새로 명시한 두 가지를
여기서 받았다 — §7.1.1 긍정 조건에 `is_recommended`(평점 3 이상일 때만),
§7.1.2 같은 날짜 tie-break 은 `review_id DESC`. 그 둘로 PC 162명이 정렬됐고
`contracts/persona/compare_holdout_rules.py --require-zero` 가 0건이다.
"""
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from batch.jobs.eval_metadata import (POSITIVE, RECOMMEND_MIN,   # noqa: E402
                                      build, is_positive, load)
from batch.jobs.persona_split import split_of                # noqa: E402

META = os.path.join(ROOT, "batch", "ingest", "data", "eval_metadata.jsonl")


def persona(pid, reviews):
    return {"persona_id": pid, "reviews": reviews}


def review(gid, when, rating, recommended=None, rid=None):
    return {"group_id": gid, "submission_time": when, "rating": rating,
            "review_id": rid or f"RV-{gid}-{when}", "is_recommended": recommended,
            "product_name": gid, "brand_name": f"B-{gid}"}


def product(pid, brand=None, reviews=100):
    return {"product_id": pid, "brand_name": brand or f"B-{pid}",
            "_review_stats": {"review_count": reviews}}


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.products = [product("A"), product("B"), product("C", brand="B-A"),
                         product("D")]

    def build_one(self, reviews):
        rows, skipped = build([persona("PT", reviews)], self.products)
        return (rows[0] if rows else None), sum(skipped.values())

    def test_target_is_the_last_positive_review(self):
        """계약 §7.1-2. 정렬 순서에서 긍정 조건을 만족하는 첫 리뷰가 target 이다"""
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-03-01", 5),
            review("D", "2024-05-01", 5),      # 마지막 긍정 -> target
        ])
        self.assertEqual("D", row["target_product_id"])
        self.assertEqual(["A", "B"], row["seed_product_ids"])

    def test_negative_last_review_does_not_drop_the_person(self):
        """마지막 리뷰가 불만이어도 그 사람을 버리지 않는다.

        우리가 만드는 것은 **선호 상품을 맞히는 추천기**다. 1점 준 상품을 맞히라는
        것은 다른 과제라, 뒤로 물러나 마지막 긍정 리뷰를 정답으로 쓴다.
        불만은 정답이 아니라 사람의 속성(`latest_review_label`)으로 남는다.
        """
        row, skipped = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-03-01", 5),      # 마지막 긍정 -> target
            review("D", "2024-05-01", 2),      # 마지막 리뷰지만 부정
        ])
        self.assertEqual("B", row["target_product_id"])
        self.assertEqual(["A"], row["seed_product_ids"])
        self.assertEqual(0, skipped)
        # target 이후 리뷰(D)는 시간 절단이라 seed 에도 들어가지 않는다
        self.assertNotIn("D", row["seed_product_ids"])

    def test_recommended_needs_rating_three(self):
        """계약 §7.1.1. 3점 추천은 긍정, 1~2점 추천은 모순이라 긍정이 아니다.

        정본이 이것을 반영하지 않아 계약과 157명이 갈려 있었다.
        """
        self.assertTrue(is_positive({"rating": 3, "is_recommended": True}))
        self.assertFalse(is_positive({"rating": 2, "is_recommended": True}))
        self.assertFalse(is_positive({"rating": 3, "is_recommended": False}))
        self.assertTrue(is_positive({"rating": 4, "is_recommended": False}))

        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("D", "2024-05-01", 3, recommended=True),   # 3점 + 추천 -> target
        ])
        self.assertEqual("D", row["target_product_id"])
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-03-01", 4),
            review("D", "2024-05-01", 2, recommended=True),   # 모순 -> 긍정 아님
        ])
        self.assertEqual("B", row["target_product_id"])

    def test_same_day_tie_break_is_review_id(self):
        """계약 §7.1.2. 같은 날짜면 review_id 가 큰 쪽이 target 이다 (5명)"""
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-05-01", 5, rid="RV-1"),
            review("D", "2024-05-01", 5, rid="RV-2"),   # 같은 날 · 더 큰 ID
        ])
        self.assertEqual("D", row["target_product_id"])

    def test_order_is_time_not_appearance(self):
        """파일에 적힌 순서가 아니라 submission_time 을 따른다"""
        row, _ = self.build_one([
            review("B", "2024-05-01", 5),      # 파일에서는 먼저 나오지만 나중 시각
            review("A", "2024-01-01", 5),
        ])
        self.assertEqual("B", row["target_product_id"])
        self.assertEqual(["A"], row["seed_product_ids"])

    def test_same_product_reviewed_twice_is_excluded_from_seed(self):
        """target 상품을 앞서 리뷰했어도 seed 에 넣지 않는다 (누출 방지)"""
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-02-01", 4),
            review("B", "2024-06-01", 5),      # 같은 상품 재리뷰 -> target
        ])
        self.assertEqual("B", row["target_product_id"])
        self.assertNotIn("B", row["seed_product_ids"])

    def test_skips_when_no_positive_or_no_seed(self):
        _, skipped = self.build_one([review("A", "2024-01-01", 2)])
        self.assertEqual(1, skipped)
        _, skipped = self.build_one([review("A", "2024-01-01", 5)])  # seed 없음
        self.assertEqual(1, skipped)

    def test_target_review_id_is_recorded(self):
        """target 상품에 리뷰를 2건 이상 쓴 사람이 2,017명이다 (같은 날짜가 1,988명).

        상품 ID 만으로는 어느 리뷰가 정답인지 특정되지 않아 계약 §7.3 과 대조할 수
        없다. review_id 가 있어야 한 행으로 떨어진다.
        """
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("D", "2024-05-01", 4, recommended=True, rid="RV-9"),
        ])
        self.assertEqual("RV-9", row["target_review_id"])
        self.assertEqual(4, row["target_rating"])
        self.assertTrue(row["target_is_recommended"])

    def test_new_brand_flag(self):
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("C", "2024-02-01", 5),      # C 의 브랜드는 A 와 같다
        ])
        self.assertFalse(row["target_is_new_brand"])
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("D", "2024-02-01", 5),      # 다른 브랜드
        ])
        self.assertTrue(row["target_is_new_brand"])

    def test_positive_threshold(self):
        self.assertEqual(4, POSITIVE)
        self.assertEqual(3, RECOMMEND_MIN)


@unittest.skipUnless(os.path.exists(META), "먼저 eval_metadata.py 를 실행하세요")
class SavedMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load()

    def test_covers_all_personas_with_split(self):
        # 모집단 조건이 긍정 3개 이상이라 target 이 없는 사람은 나오지 않는다
        self.assertEqual(9900, len(self.rows))
        for row in self.rows[:200]:
            self.assertEqual(split_of(row["persona_id"]), row["split"])

    def test_target_not_in_seeds(self):
        for row in self.rows:
            self.assertNotIn(row["target_product_id"], row["seed_product_ids"],
                             row["persona_id"])

    def test_seeds_are_unique_and_nonempty(self):
        for row in self.rows[:500]:
            seeds = row["seed_product_ids"]
            self.assertTrue(seeds, row["persona_id"])
            self.assertEqual(len(seeds), len(set(seeds)), row["persona_id"])

    def test_split_filter(self):
        test = load(split="test")
        self.assertTrue(test)
        self.assertTrue(all(r["split"] == "test" for r in test))


if __name__ == "__main__":
    unittest.main()
