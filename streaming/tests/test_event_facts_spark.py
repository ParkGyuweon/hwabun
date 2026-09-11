import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        BooleanType,
        DateType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.derive_facts_job import (
    _product_event_fact,
    _purchase_fact,
    _purchase_reason_fact,
    _review_event_fact,
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class EventFactsSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("event-facts-contract-test")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _cleaned(self, rows):
        schema = StructType(
            [
                StructField("event_id", StringType(), False),
                StructField("event_date_kst", DateType(), False),
                StructField("event_time", TimestampType(), False),
                StructField("processed_at", TimestampType(), False),
                StructField("event_name", StringType(), False),
                StructField("intent", StringType(), False),
                StructField("user_id", StringType(), True),
                StructField("identity_scope", StringType(), True),
                StructField("is_seed", BooleanType(), False),
                StructField("persona_id", StringType(), True),
                StructField("scenario_id", StringType(), True),
                StructField("simulation_run_id", StringType(), True),
                StructField("generator_type", StringType(), True),
                StructField("session_id", StringType(), False),
                StructField("page_view_id", StringType(), False),
                StructField("product_id", StringType(), True),
                StructField("actor_type", StringType(), False),
                StructField("source", StringType(), False),
                StructField("properties_json", StringType(), False),
            ]
        )
        now = datetime(2026, 9, 9, 1, 2, 3, tzinfo=timezone.utc).replace(tzinfo=None)
        values = [
            (
                event_id,
                date(2026, 9, 9),
                now,
                now,
                event_name,
                intent,
                "U1",
                "persona",
                False,
                "PE1",
                "SC1",
                "RUN1",
                "python_batch",
                "S1",
                "PV1",
                product_id,
                "synthetic",
                "simulator",
                properties_json,
            )
            for event_id, event_name, intent, product_id, properties_json in rows
        ]
        return self.spark.createDataFrame(values, schema)

    def _dimension(self):
        return self.spark.createDataFrame(
            [("P1", "C1", "B1")],
            ["product_id", "category_id", "brand_id"],
        )

    def test_purchase_fact_explodes_items_and_derives_behavior_revenue(self):
        cleaned = self._cleaned(
            [
                (
                    "purchase-1",
                    "purchase",
                    "conversion",
                    None,
                    '{"order_id":"O1","order_value":25.00,"currency":"USD",'
                    '"items":[{"product_id":"P1","sku_id":"SKU1",'
                    '"quantity":2,"unit_price":10.00}]}',
                )
            ]
        )

        product_fact = _product_event_fact(cleaned, "Asia/Seoul", self._dimension())
        row = _purchase_fact(product_fact).first()

        self.assertEqual("O1", row["order_id"])
        self.assertEqual("P1", row["product_id"])
        self.assertEqual("B1", row["brand_id"])
        self.assertEqual(2, row["quantity"])
        self.assertEqual(Decimal("10.00"), row["unit_price"])
        self.assertEqual(Decimal("20.00"), row["item_revenue"])
        self.assertEqual(Decimal("25.00"), row["order_value"])

    def test_purchase_reason_fact_expands_reasons_and_preserves_skip(self):
        cleaned = self._cleaned(
            [
                (
                    "reason-1",
                    "purchase_reason_select",
                    "validation",
                    None,
                    '{"order_id":"O1","reasons":["reviews","recommendation"],'
                    '"primary_reason":"reviews","free_text_kind":"none","skipped":false}',
                ),
                (
                    "reason-2",
                    "purchase_reason_select",
                    "validation",
                    None,
                    '{"order_id":"O2","reasons":[],"skipped":true}',
                ),
            ]
        )

        rows = _purchase_reason_fact(cleaned).orderBy("order_id", "reason_rank").collect()

        self.assertEqual(3, len(rows))
        self.assertEqual(("reviews", 1, True, False), tuple(rows[0][name] for name in ("reason", "reason_rank", "is_primary", "skipped")))
        self.assertEqual(("recommendation", 2, False, False), tuple(rows[1][name] for name in ("reason", "reason_rank", "is_primary", "skipped")))
        self.assertEqual((None, None, False, True), tuple(rows[2][name] for name in ("reason", "reason_rank", "is_primary", "skipped")))

    def test_review_fact_keeps_review_details_and_excludes_ingredient_expand(self):
        cleaned = self._cleaned(
            [
                (
                    "review-expand",
                    "review_expand",
                    "validation",
                    "P1",
                    '{"target":"review_text","review_id":"R1","revealed_count":3}',
                ),
                (
                    "ingredient-expand",
                    "review_expand",
                    "validation",
                    "P1",
                    '{"target":"ingredients","revealed_count":5}',
                ),
                (
                    "review-filter",
                    "review_filter_apply",
                    "validation",
                    "P1",
                    '{"filter":"same_skin","result_count":7,'
                    '"persona_skin_type":"dry","persona_skin_tone":"light"}',
                ),
                (
                    "review-dwell",
                    "section_dwell",
                    "interest",
                    "P1",
                    '{"section_id":"reviews","content_kind":"user_review","dwell_ms":1200}',
                ),
            ]
        )

        rows = {
            row["event_id"]: row
            for row in _review_event_fact(cleaned, self._dimension()).collect()
        }

        self.assertEqual({"review-expand", "review-filter", "review-dwell"}, set(rows))
        self.assertEqual("R1", rows["review-expand"]["review_id"])
        self.assertEqual(7, rows["review-filter"]["result_count"])
        self.assertEqual(1200, rows["review-dwell"]["dwell_ms"])
        self.assertTrue(all(row["brand_id"] == "B1" for row in rows.values()))

    def test_recommendation_events_keep_join_keys_in_product_fact(self):
        cleaned = self._cleaned(
            [
                (
                    "recommendation-impression",
                    "recommendation_impression",
                    "exposure",
                    "P1",
                    '{"recommendation_id":"REC1","list_id":"similar_products",'
                    '"algorithm":"cf_v1","position":2,"context_product_id":"P0"}',
                ),
                (
                    "recommendation-click",
                    "recommendation_click",
                    "comparison",
                    "P1",
                    '{"recommendation_id":"REC1","list_id":"similar_products",'
                    '"algorithm":"cf_v1","position":2,"context_product_id":"P0"}',
                ),
            ]
        )

        rows = _product_event_fact(
            cleaned, "Asia/Seoul", self._dimension()
        ).orderBy("event_id").collect()

        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertEqual("REC1", row["recommendation_id"])
            self.assertEqual("similar_products", row["list_id"])
            self.assertEqual("cf_v1", row["algorithm"])
            self.assertEqual(2, row["position"])
            self.assertEqual("P0", row["context_product_id"])
            self.assertEqual("B1", row["brand_id"])


if __name__ == "__main__":
    unittest.main()
