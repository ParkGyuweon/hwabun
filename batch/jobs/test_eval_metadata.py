"""평가 seed / target 정의를 한 곳에 고정한다.

축마다 각자 계산하다 9,900명 중 792명(8.0%)이 다른 target 을 맞히고 있었다.
그 정의가 다시 갈라지지 않게 여기서 못 박는다.
"""
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from batch.jobs.eval_metadata import POSITIVE, build, load   # noqa: E402
from batch.jobs.persona_split import split_of                # noqa: E402

META = os.path.join(ROOT, "batch", "ingest", "data", "eval_metadata.jsonl")


def persona(pid, reviews):
    return {"persona_id": pid, "reviews": reviews}


def review(gid, when, rating):
    return {"group_id": gid, "submission_time": when, "rating": rating,
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
        return (rows[0] if rows else None), skipped

    def test_target_is_last_positive_by_time(self):
        row, _ = self.build_one([
            review("A", "2024-01-01", 5),
            review("B", "2024-03-01", 5),      # 마지막 긍정 -> target
            review("D", "2024-05-01", 2),      # 뒤에 있지만 부정이라 target 아님
        ])
        self.assertEqual("B", row["target_product_id"])
        self.assertEqual(["A"], row["seed_product_ids"])

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


@unittest.skipUnless(os.path.exists(META), "먼저 eval_metadata.py 를 실행하세요")
class SavedMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load()

    def test_covers_all_personas_with_split(self):
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
