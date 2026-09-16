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
    _section_dwell_agg,
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
                StructField("is_seeded", BooleanType(), False),
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

    # ── 겹침 제외 체류 (Jira 338) ──────────────────────────────────────
    def _dwell_row(self, event_id, dwell_ms, co_visible):
        blocks = "" if co_visible is None else ', "co_visible_blocks": %d' % co_visible
        return (
            event_id, "section_dwell", "interest", "P1",
            '{"section_id": "details", "content_kind": "ingredient", '
            '"dwell_ms": %d%s}' % (dwell_ms, blocks),
        )

    def test_co_visible_sum_filters_each_event_not_the_group_maximum(self):
        """한 grain 안에서도 Event 마다 겹침 수가 다르다.

        max_co_visible_blocks 로 거르면 큰 값 하나 때문에 그룹 전체가 빠져
        깨끗한 체류까지 사라진다. 건당으로 걸러야 한다
        (processed-schema.md §12).
        """
        cleaned = self._cleaned([
            self._dwell_row("d1", 1000, 1),
            self._dwell_row("d2", 500, 9),
        ])

        row = _section_dwell_agg(cleaned, self._dimension()).collect()[0]

        self.assertEqual(1500, row["dwell_ms_sum"])
        self.assertEqual(1000, row["co_visible_le2_dwell_ms_sum"])
        # 그룹 최댓값은 9 다. 이 값으로 걸렀다면 위가 0 이 된다.
        self.assertEqual(9, row["max_co_visible_blocks"])

    def test_co_visible_sum_excludes_events_without_the_property(self):
        """값이 없으면 겹치지 않았다고 볼 근거가 없다. NULL 은 뺀다."""
        cleaned = self._cleaned([
            self._dwell_row("d1", 1000, None),
            self._dwell_row("d2", 300, 2),
        ])

        row = _section_dwell_agg(cleaned, self._dimension()).collect()[0]

        self.assertEqual(1300, row["dwell_ms_sum"])
        self.assertEqual(300, row["co_visible_le2_dwell_ms_sum"])

    def test_co_visible_sum_is_zero_not_null_when_nothing_qualifies(self):
        """0 은 "깨끗한 체류가 없었다" 다. 계약이 N 으로 선언했다."""
        cleaned = self._cleaned([self._dwell_row("d1", 1000, 36)])

        row = _section_dwell_agg(cleaned, self._dimension()).collect()[0]

        self.assertEqual(0, row["co_visible_le2_dwell_ms_sum"])

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
