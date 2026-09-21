"""double 합의 결정성.

Spark 의 `sum` 은 파티션 부분합을 셔플 도착 순서대로 합친다. 부동소수점 덧셈은
결합법칙이 성립하지 않아 같은 입력이라도 실행마다 끝자리가 달라진다 — 2026-09-21
운영 리포트에서 `content_daily_kpi` 가 이 이유로 어긋났고, 같은 코드가 같은 날
한 번은 통과했다.
"""

import unittest

try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import _deterministic_sum


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class DeterministicSumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("deterministic-sum-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _sum(self, values, aggregate):
        frame = self.spark.createDataFrame(
            [("g", value) for value in values], "g string, v double"
        )
        return frame.groupBy("g").agg(
            aggregate.cast("double").alias("total")
        ).collect()[0]["total"]

    def test_decimal_sum_lands_on_the_exact_value(self):
        """0.1 + 0.2 는 double 로는 0.30000000000000004 다."""
        values = [0.1, 0.2]

        self.assertEqual(0.3, self._sum(values, _deterministic_sum("v")))
        self.assertNotEqual(0.3, self._sum(values, F.sum("v")))

    def test_order_does_not_change_the_result(self):
        """같은 값들을 다른 순서로 더해도 같은 값이 나온다.

        double 덧셈은 순서에 따라 끝자리가 달라진다. 배치마다 셔플 순서가 달라서
        재계산 결과가 저장된 Mart 와 어긋나던 자리다.
        """
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]

        first = self._sum(values, _deterministic_sum("v"))
        second = self._sum(list(reversed(values)), _deterministic_sum("v"))

        self.assertEqual(first, second)
        self.assertEqual(2.8, first)

    def test_column_expression_is_accepted(self):
        """가중치 합처럼 컬럼 식을 그대로 받는 호출부가 있다."""
        frame = self.spark.createDataFrame(
            [("g", 0.1), ("g", 0.2)], "g string, v double"
        )
        doubled = F.col("v") * F.lit(2.0)

        total = frame.groupBy("g").agg(
            _deterministic_sum(doubled).cast("double").alias("total")
        ).collect()[0]["total"]

        self.assertEqual(0.6, total)


if __name__ == "__main__":
    unittest.main()
