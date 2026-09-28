import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import (
    PROJECTION_MART_FRAMES,
    _load_dw_contract_rules,
    _projection_not_null_violations,
)


class ProjectionMartContractTest(unittest.TestCase):
    def test_mapping_covers_every_ddl_projection_mart(self):
        rules = _load_dw_contract_rules()

        self.assertEqual(24, len(PROJECTION_MART_FRAMES))
        self.assertEqual(set(rules.GRAINS), set(PROJECTION_MART_FRAMES))


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class ProjectionMartNotNullSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("projection-mart-not-null-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_intentional_null_in_not_null_count_is_reported(self):
        frame = self.spark.createDataFrame(
            [("B1", None)],
            "brand_id string, detail_view_sessions long",
        )

        violations = _projection_not_null_violations({"brand_daily": frame})

        self.assertEqual(
            1,
            violations["brand_daily_kpi.detail_view_sessions"],
        )

    def test_nullable_contract_column_is_ignored(self):
        frame = self.spark.createDataFrame(
            [("B1", None)],
            "brand_id string, category_id string",
        )

        self.assertEqual(
            {},
            _projection_not_null_violations({"brand_daily": frame}),
        )


if __name__ == "__main__":
    unittest.main()
