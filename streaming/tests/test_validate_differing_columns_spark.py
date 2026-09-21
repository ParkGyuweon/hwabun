"""결정성 검사의 실패 상세.

`differing_rows` 한 줄만으로는 원인을 좁힐 수 없다. 2026-09-20 운영 리포트가
`differing_rows=5824` 만 남겨 어느 컬럼이 흔들렸는지 알 수 없었다.
"""

import unittest
from datetime import date

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        DateType,
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
    )
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import _differing_columns

SCHEMA = None
if SparkSession is not None:
    SCHEMA = StructType([
        StructField("event_date_kst", DateType(), False),
        # grain 에 NULL 이 있는 것이 이 검사의 핵심 조건이다.
        StructField("brand_id", StringType(), True),
        StructField("product_id", StringType(), False),
        StructField("section_view_count", LongType(), False),
        StructField("content_interest_score", DoubleType(), True),
    ])

KEY = ["event_date_kst", "brand_id", "product_id"]


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class DifferingColumnsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("differing-columns-test")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _df(self, rows):
        return self.spark.createDataFrame(rows, SCHEMA)

    @staticmethod
    def _columns():
        return [f.name for f in SCHEMA.fields]

    def test_names_the_column_whose_value_drifted(self):
        """brand_id 가 NULL 인 grain 에서도 값 차이를 잡아낸다.

        평범한 equi-join 이면 NULL grain 이 한 건도 안 맞아 "전 컬럼이 전부
        어긋남" 으로 보인다. NULL-safe 여야 값 차이와 grain 차이가 갈린다.
        """
        stored = self._df([
            (date(2026, 9, 20), None, "P1", 10, 1.5),
            (date(2026, 9, 20), "B1", "P2", 20, 2.5),
        ])
        expected = self._df([
            (date(2026, 9, 20), None, "P1", 10, 9.5),
            (date(2026, 9, 20), "B1", "P2", 20, 2.5),
        ])

        detail = _differing_columns(stored, expected, KEY, self._columns())

        self.assertEqual("content_interest_score=1", detail)

    def test_separates_a_missing_grain_from_a_drifted_value(self):
        """한쪽에만 있는 grain 은 값 차이로 세지 않는다."""
        stored = self._df([(date(2026, 9, 20), None, "P1", 10, 1.5)])
        expected = self._df([
            (date(2026, 9, 20), None, "P1", 10, 1.5),
            (date(2026, 9, 20), "B1", "P9", 1, 0.5),
        ])

        detail = _differing_columns(stored, expected, KEY, self._columns())

        self.assertEqual("grain_only_on_one_side=1", detail)

    def test_reports_every_drifted_column_worst_first(self):
        stored = self._df([
            (date(2026, 9, 20), None, "P1", 10, 1.5),
            (date(2026, 9, 20), "B1", "P2", 20, 2.5),
        ])
        expected = self._df([
            (date(2026, 9, 20), None, "P1", 11, 9.5),
            (date(2026, 9, 20), "B1", "P2", 21, 2.5),
        ])

        detail = _differing_columns(stored, expected, KEY, self._columns())

        self.assertEqual(
            "section_view_count=2 · content_interest_score=1", detail
        )

    def test_reports_duplicate_grains_in_the_recomputed_frame(self):
        """`exceptAll` 은 다중집합 차이라 값이 같아도 중복이 있으면 차이로 센다.

        grain 으로 조인해 값만 비교하면 이 경우가 안 보인다. 2026-09-21 운영
        리포트가 differing_rows=5855 인데 상세가 비었던 자리다.
        """
        row = (date(2026, 9, 20), None, "P1", 10, 1.5)
        stored = self._df([row])
        expected = self._df([row, row])          # 재계산이 같은 행을 두 번 낸다

        detail = _differing_columns(stored, expected, KEY, self._columns())

        self.assertEqual("recomputed_duplicate_grains=1", detail)

    def test_reports_duplicate_grains_in_the_stored_frame(self):
        row = (date(2026, 9, 20), "B1", "P1", 10, 1.5)
        stored = self._df([row, row])
        expected = self._df([row])

        detail = _differing_columns(stored, expected, KEY, self._columns())

        self.assertEqual("stored_duplicate_grains=1", detail)

    def test_is_empty_when_nothing_drifted(self):
        rows = [(date(2026, 9, 20), None, "P1", 10, 1.5)]

        detail = _differing_columns(
            self._df(rows), self._df(rows), KEY, self._columns()
        )

        self.assertEqual("", detail)


if __name__ == "__main__":
    unittest.main()
