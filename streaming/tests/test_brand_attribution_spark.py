import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.derive_facts_job import (
    _attach_product_dimension,
    _build_dim_brand,
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class BrandAttributionSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("brand-attribution-contract-test")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_dimension_join_preserves_rows_and_never_infers_unknown_brand(self):
        facts = self.spark.createDataFrame(
            [
                ("event-known", "P1"),
                ("event-unknown", "P404"),
                ("event-platform", None),
            ],
            ["event_id", "product_id"],
        )
        # Repeated dimension input must not multiply the known Fact row.
        dimension = self.spark.createDataFrame(
            [("P1", "C1", "B1"), ("P1", "C1", "B1")],
            ["product_id", "category_id", "brand_id"],
        )

        first = _attach_product_dimension(facts, dimension)
        second = _attach_product_dimension(facts, dimension)
        first_rows = {
            row["event_id"]: row["brand_id"] for row in first.collect()
        }
        second_rows = {
            row["event_id"]: row["brand_id"] for row in second.collect()
        }

        self.assertEqual(3, first.count())
        self.assertEqual("B1", first_rows["event-known"])
        self.assertIsNone(first_rows["event-unknown"])
        self.assertIsNone(first_rows["event-platform"])
        self.assertEqual(first_rows, second_rows)

    def test_conflicting_dimension_brand_is_not_chosen_arbitrarily(self):
        facts = self.spark.createDataFrame(
            [("event-conflict", "P1")], ["event_id", "product_id"]
        )
        dimension = self.spark.createDataFrame(
            [("P1", "C1", "B1"), ("P1", "C1", "B2")],
            ["product_id", "category_id", "brand_id"],
        )

        result = _attach_product_dimension(facts, dimension).first()

        self.assertIsNone(result["brand_id"])

    def test_dim_brand_has_one_row_per_brand(self):
        products = self.spark.createDataFrame(
            [("P1", "B1", "Brand One"), ("P2", "B1", "Brand One")],
            ["product_id", "brand_id", "brand_name"],
        )

        rows = _build_dim_brand(products).select("brand_id", "brand_name").collect()

        self.assertEqual([("B1", "Brand One")], [tuple(row) for row in rows])


if __name__ == "__main__":
    unittest.main()
