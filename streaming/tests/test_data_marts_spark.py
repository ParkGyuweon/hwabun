import csv
import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import (
    _category_price_reference,
    _ingredient_weekly_interest,
)


ROOT = Path(__file__).resolve().parents[2]


class IngredientCsvContractTest(unittest.TestCase):
    def test_seed_catalog_explicitly_has_twelve_unmapped_products(self):
        with open(
            ROOT / "batch" / "ingest" / "data" / "products_200.json",
            encoding="utf-8",
        ) as stream:
            products = json.load(stream)
        with open(
            ROOT
            / "batch"
            / "ingest"
            / "data"
            / "serving"
            / "product_ingredient.csv",
            encoding="utf-8",
            newline="",
        ) as stream:
            ingredient_products = {row["product_id"] for row in csv.DictReader(stream)}

        product_ids = {product["product_id"] for product in products}
        self.assertEqual(200, len(product_ids))
        self.assertEqual(188, len(ingredient_products))
        self.assertEqual(12, len(product_ids - ingredient_products))


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class DataMartsSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("jira-199-data-marts-test")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _event(self, event_id, event_name, product_id, properties):
        return (
            event_id,
            event_name,
            product_id,
            datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
            "synthetic",
            "simulator",
            "python_batch",
            "scenario-1",
            "run-1",
            json.dumps(properties),
        )

    def test_ingredient_interest_uses_position_weight_and_excludes_unmapped_product(self):
        events = self.spark.createDataFrame(
            [
                self._event("clean", "add_to_cart", "P-CLEAN", {}),
                self._event("leave", "add_to_cart", "P-LEAVE", {}),
                self._event("unmapped", "add_to_cart", "P-NONE", {}),
                self._event(
                    "direct",
                    "text_copy",
                    "P-NONE",
                    {"matched_ingredients": ["Hyaluronic Acid"]},
                ),
            ],
            [
                "event_id",
                "event_name",
                "product_id",
                "event_time",
                "actor_type",
                "source",
                "generator_type",
                "scenario_id",
                "simulation_run_id",
                "properties_json",
            ],
        )
        products = self.spark.createDataFrame(
            [
                ("P-CLEAN", "Cleansers"),
                ("P-LEAVE", "Treatments"),
                ("P-NONE", "Treatments"),
            ],
            ["product_id", "secondary_category"],
        )
        product_ingredients = self.spark.createDataFrame(
            [
                ("P-CLEAN", 0, "Hyaluronic Acid", 0.5, "parsed", "0.5"),
                ("P-LEAVE", 0, "Hyaluronic Acid", 0.5, "parsed", "0.5"),
            ],
            [
                "product_id",
                "ingredient_id",
                "ingredient",
                "position_weight",
                "source",
                "vocab_version",
            ],
        )
        vocab = self.spark.createDataFrame(
            [(0, "Hyaluronic Acid", "히알루론산", 2, "0.5")],
            ["ingredient_id", "ingredient", "label_ko", "doc_freq", "vocab_version"],
        )

        row = _ingredient_weekly_interest(
            events,
            products,
            product_ingredients,
            vocab,
            "Asia/Seoul",
            {"add_to_cart": 4.0, "text_copy": 1.0},
            0.5,
        ).first()

        # clean: 4 * .5 * .5 = 1; leave-on: 4 * .5 = 2; direct = 1.
        self.assertAlmostEqual(4.0, row["ingredient_interest_score"])
        self.assertAlmostEqual(3.0, row["product_attributed_score"])
        self.assertAlmostEqual(1.0, row["direct_match_score"])
        self.assertEqual(3, row["contributing_event_count"])
        self.assertAlmostEqual(1.0, row["ingredient_interest_share"])

    def test_thin_price_category_uses_currency_global_median_and_ignores_sale(self):
        products = self.spark.createDataFrame(
            [
                ("P1", "Self Tanners", Decimal("20.00"), "USD", Decimal("1.00")),
                ("P2", "Self Tanners", Decimal("40.00"), "USD", Decimal("1.00")),
                ("P3", "Treatments", Decimal("50.00"), "USD", Decimal("1.00")),
                ("P4", "Treatments", Decimal("60.00"), "USD", None),
                ("P5", "Treatments", Decimal("70.00"), "USD", None),
            ],
            ["product_id", "secondary_category", "base_price", "currency", "sale_price"],
        )

        rows = {
            row["secondary_category"]: row
            for row in _category_price_reference(products, 3).collect()
        }

        thin = rows["Self Tanners"]
        self.assertEqual(Decimal("30.00"), thin["observed_median_price"])
        self.assertEqual(Decimal("50.00"), thin["reference_median_price"])
        self.assertFalse(thin["is_sample_sufficient"])
        self.assertEqual("global_fallback", thin["reference_source"])
        self.assertEqual(Decimal("60.00"), rows["Treatments"]["reference_median_price"])


if __name__ == "__main__":
    unittest.main()
