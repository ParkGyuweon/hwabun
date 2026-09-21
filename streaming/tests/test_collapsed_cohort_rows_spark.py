"""축을 걷어낸 코호트 전체 행 검사 (dw-schema.md §4.18).

2026-09-21 운영 배치는 Mart 수정 이전 코드라 전체 행이 한 건도 없었는데, 검사는
통과했다. 전체 행에서 출발해 조인하면 비교할 짝이 없어 공허히 통과한다.
"""

import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import COLLAPSED_AXIS_VALUE
from streaming.jobs.validate_pipeline_job import _collapsed_cohort_violations

SCHEMA = (
    "snapshot_week_kst string, cohort_key string, metric_name string, "
    "actor_type string, brand_count long"
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class CollapsedCohortRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("collapsed-cohort-rows-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _violations(self, rows):
        frame = self.spark.createDataFrame(rows, SCHEMA)
        return _collapsed_cohort_violations(frame, COLLAPSED_AXIS_VALUE)

    def test_missing_collapsed_row_is_reported(self):
        """전체 행이 아예 없으면 잡아낸다 — 운영에서 놓쳤던 상태다."""
        violations = self._violations([
            ("2026-W38", "C1", "view_to_cart_rate", "synthetic", 6),
            ("2026-W38", "C1", "view_to_cart_rate", "user", 4),
        ])

        self.assertEqual(1, violations["missing"])
        self.assertEqual(0, violations["shrunk"])

    def test_collapsed_row_with_fewer_brands_is_reported(self):
        """축을 합쳤는데 브랜드가 줄면 합치는 과정에서 흘린 것이다."""
        violations = self._violations([
            ("2026-W38", "C1", "view_to_cart_rate", "synthetic", 6),
            ("2026-W38", "C1", "view_to_cart_rate", COLLAPSED_AXIS_VALUE, 5),
        ])

        self.assertEqual(0, violations["missing"])
        self.assertEqual(1, violations["shrunk"])

    def test_covering_collapsed_row_passes(self):
        violations = self._violations([
            ("2026-W38", "C1", "view_to_cart_rate", "synthetic", 6),
            ("2026-W38", "C1", "view_to_cart_rate", "user", 4),
            ("2026-W38", "C1", "view_to_cart_rate", COLLAPSED_AXIS_VALUE, 6),
        ])

        self.assertEqual({"missing": 0, "shrunk": 0}, violations)

    def test_only_the_cohort_without_a_collapsed_row_is_counted(self):
        """코호트마다 따로 본다. 하나가 멀쩡해도 다른 하나를 덮어주지 않는다."""
        violations = self._violations([
            ("2026-W38", "C1", "view_to_cart_rate", "synthetic", 6),
            ("2026-W38", "C1", "view_to_cart_rate", COLLAPSED_AXIS_VALUE, 6),
            ("2026-W38", "C2", "view_to_cart_rate", "synthetic", 7),
        ])

        self.assertEqual(1, violations["missing"])

    def test_empty_mart_has_nothing_to_check(self):
        violations = self._violations([])

        self.assertEqual({"missing": 0, "shrunk": 0}, violations)


if __name__ == "__main__":
    unittest.main()
