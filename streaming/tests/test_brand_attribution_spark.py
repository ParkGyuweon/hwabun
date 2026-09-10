import json
import os
import tempfile
import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.derive_facts_job import (
    DEFAULT_PRODUCT_CATALOG_PATH,
    DEFAULT_REGISTERED_PRODUCT_PATH,
    _active_registered_product_records,
    _attach_product_dimension,
    _build_dim_brand,
    _build_registered_dim_product,
    _build_seed_dim_product,
    _merge_dim_products,
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

    def test_registered_dimension_uses_shop_brand_mapping_without_guessing(self):
        registered = self.spark.createDataFrame(
            [
                (
                    "SB000001", "토닝 패드", "SSAFY Beauty", "",
                    "Treatments", "Exfoliators", 22.0, 4.4, "injected", 0,
                    "2026-09-09T10:08:34",
                )
            ],
            [
                "product_id", "product_name", "brand_name", "brand_id",
                "secondary_category", "tertiary_category", "price_usd", "rating",
                "rating_source", "loves_count", "registered_at",
            ],
        )
        product_brand = self.spark.createDataFrame(
            [("SB000001", "brand-from-shop-db")],
            ["product_id", "brand_id"],
        )

        row = _build_registered_dim_product(registered, product_brand).first()

        self.assertEqual("brand-from-shop-db", row["brand_id"])
        self.assertEqual("brand_registered", row["product_source"])

    def test_registered_dimension_leaves_missing_brand_id_null(self):
        registered = self.spark.createDataFrame(
            [
                (
                    "SB000001", "토닝 패드", "SSAFY Beauty", "",
                    "Treatments", "Exfoliators", 22.0, 4.4, "injected", 0,
                    "2026-09-09T10:08:34",
                )
            ],
            [
                "product_id", "product_name", "brand_name", "brand_id",
                "secondary_category", "tertiary_category", "price_usd", "rating",
                "rating_source", "loves_count", "registered_at",
            ],
        )

        row = _build_registered_dim_product(registered).first()

        self.assertIsNone(row["brand_id"])

    def test_registered_product_overrides_seed_product_on_id_collision(self):
        columns = ["product_id", "product_name", "product_source", "brand_id"]
        seed = self.spark.createDataFrame(
            [("P1", "seed", "seed_catalog", "B1")],
            columns,
        )
        registered = self.spark.createDataFrame(
            [("P1", "registered", "brand_registered", "B2")],
            columns,
        )

        row = _merge_dim_products(seed, registered).first()

        self.assertEqual("registered", row["product_name"])
        self.assertEqual("B2", row["brand_id"])

    def test_checked_in_registry_adds_eight_ssafy_products_when_mapped(self):
        seed_catalog = self.spark.read.option("multiLine", "true").json(
            DEFAULT_PRODUCT_CATALOG_PATH
        )
        records = _active_registered_product_records(DEFAULT_REGISTERED_PRODUCT_PATH)
        registered_catalog = self.spark.read.json(
            self.spark.sparkContext.parallelize(
                [json.dumps(record, ensure_ascii=False) for record in records]
            )
        )
        product_brand = self.spark.createDataFrame(
            [(f"SB00000{index}", "brand-from-shop-db") for index in range(1, 9)],
            ["product_id", "brand_id"],
        )

        dimension = _merge_dim_products(
            _build_seed_dim_product(seed_catalog),
            _build_registered_dim_product(registered_catalog, product_brand),
        )
        ssafy = dimension.where("product_id like 'SB%'")

        self.assertEqual(208, dimension.count())
        self.assertEqual(8, ssafy.count())
        self.assertEqual(0, ssafy.where("brand_id is null").count())
        self.assertEqual(
            {"brand-from-shop-db"},
            {row["brand_id"] for row in ssafy.select("brand_id").collect()},
        )


class RegisteredProductRegistryTest(unittest.TestCase):
    def test_last_record_wins_and_deactivated_product_is_excluded(self):
        rows = [
            {"product_id": "P1", "product_name": "old"},
            {"product_id": "P2", "product_name": "active"},
            {"product_id": "P1", "product_name": "new"},
            {"product_id": "P2", "_op": "deactivate"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "registered.jsonl")
            with open(path, "w", encoding="utf-8") as target:
                for row in rows:
                    target.write(json.dumps(row) + "\n")

            records = _active_registered_product_records(path)

        self.assertEqual([{"product_id": "P1", "product_name": "new"}], records)


if __name__ == "__main__":
    unittest.main()
