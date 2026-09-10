import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession, functions as F
except ImportError:
    SparkSession = None
    F = None

from streaming.jobs.build_marts_job import (
    _analytics_baseline,
    _banner_daily,
    _cross_brand_daily,
    _user_trait_daily,
    _write_mart,
)
from streaming.jobs.derive_facts_job import _product_event_fact


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class BannerTraitMartsSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("banner-trait-marts-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_product_fact_and_banner_daily_preserve_banner_contract(self):
        now = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
        properties = json.dumps(
            {
                "banner_type": "concern",
                "banner_value": "Pores",
                "banner_slot": 2,
                "trait_source": "explore",
                "policy_version": "banner_sort_v1",
            }
        )
        cleaned = self.spark.createDataFrame(
            [
                ("i", "banner_impression", "session", "P1", properties),
                ("c", "banner_click", "interest", "P1", properties),
            ],
            ["event_id", "event_name", "intent", "product_id", "properties_json"],
        )
        values = {
            "event_time": now,
            "processed_at": now,
            "event_date_kst": date(2026, 9, 8),
            "user_id": "U1",
            "identity_scope": "persona",
            "persona_id": None,
            "scenario_id": None,
            "simulation_run_id": None,
            "generator_type": None,
            "session_id": "S1",
            "page_view_id": "PV1",
            "actor_type": "user",
            "source": "web",
        }
        for name, value in values.items():
            cleaned = cleaned.withColumn(name, F.lit(value))

        fact = _product_event_fact(cleaned, "Asia/Seoul")
        row = _banner_daily(fact, {"Pores"}).first()

        self.assertEqual("concern", row["banner_type"])
        self.assertEqual(2, row["banner_slot"])
        self.assertEqual("explore", row["trait_source"])
        self.assertEqual("banner_sort_v1", row["policy_version"])
        self.assertEqual(1, row["impression_count"])
        self.assertEqual(1, row["click_count"])
        self.assertEqual(1.0, row["banner_ctr"])
        self.assertEqual(0, row["skip_count"])
        self.assertTrue(row["banner_value_is_valid"])

    def test_cross_brand_uses_first_brand_and_preceding_clicks(self):
        now = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
        events = self.spark.createDataFrame(
            [
                ("a1", "S1", 1, "product_view", "P-A", "A", "{}"),
                ("rec", "S1", 2, "recommendation_click", "P-B", "B", '{"recommendation_id":"R1"}'),
                ("noise", "S1", 3, "page_view", "P-B", "B", "{}"),
                ("banner", "S1", 4, "banner_click", "P-B", "B", "{}"),
                ("b1", "S1", 5, "product_view", "P-B", "B", "{}"),
                ("b2", "S1", 6, "product_view", "P-B", "B", "{}"),
                ("a2", "S1", 7, "product_view", "P-A", "A", "{}"),
                ("c1", "S2", 1, "product_view", "P-C", "C", "{}"),
                ("d1", "S2", 2, "product_view", "P-D", "D", '{"recommendation_id":"R2"}'),
            ],
            ["event_id", "session_id", "event_order", "event_name", "product_id", "brand_id", "properties_json"],
        )
        values = {
            "event_time": now,
            "event_date_kst": date(2026, 9, 8),
            "actor_type": "user",
            "source": "web",
            "scenario_id": None,
            "simulation_run_id": None,
        }
        for name, value in values.items():
            events = events.withColumn(name, F.lit(value))

        row = _cross_brand_daily(events).where("destination_brand_id = 'B'").first()

        self.assertEqual(1, row["brand_view_sessions"])
        self.assertEqual(1, row["cross_brand_entry_sessions"])
        self.assertEqual(1, row["recommendation_cross_brand_entry_sessions"])
        self.assertEqual(1, row["banner_cross_brand_entry_sessions"])
        self.assertEqual(1.0, row["recommendation_share_of_cross_brand_entries"])
        self.assertEqual(1.0, row["banner_share_of_cross_brand_entries"])
        first_brand_row = _cross_brand_daily(events).where(
            "destination_brand_id = 'A'"
        ).first()
        self.assertEqual(0, first_brand_row["cross_brand_entry_sessions"])
        direct_recommendation_row = _cross_brand_daily(events).where(
            "destination_brand_id = 'D'"
        ).first()
        self.assertEqual(
            1, direct_recommendation_row["recommendation_cross_brand_entry_sessions"]
        )

    def test_user_trait_daily_scores_and_ranks_configured_signals(self):
        events = self.spark.createDataFrame(
            [
                (
                    "price-filter",
                    "filter_change",
                    date(2026, 9, 8),
                    "U1",
                    "account",
                    "user",
                    "web",
                    None,
                    None,
                    '{"filter_kind":"price"}',
                )
            ],
            "event_id string, event_name string, event_date_kst date, user_id string, "
            "identity_scope string, actor_type string, source string, scenario_id string, "
            "simulation_run_id string, properties_json string",
        )
        contract = {
            "version": "test-v1",
            "window_days": 30,
            "traits": {
                "price": [
                    {
                        "event_name": "filter_change",
                        "property": "filter_kind",
                        "values": ["price"],
                        "weight": 1.0,
                    }
                ],
                "ingredient": [],
                "review": [],
                "concern": [],
                "participate": [],
            },
        }

        row = _user_trait_daily(events, contract).first()

        self.assertEqual("price", row["trait"])
        self.assertEqual(1.0, row["trait_score"])
        self.assertEqual(1, row["trait_rank"])
        self.assertTrue(row["is_primary_trait"])
        self.assertEqual("test-v1", row["trait_policy_version"])

    def test_banner_daily_stays_readable_when_no_banner_event_exists(self):
        """배너를 아직 아무도 발행하지 않는 기간에도 검증 Job이 Mart를 읽어야 한다."""
        from pyspark.sql.types import (
            DateType,
            IntegerType,
            StringType,
            StructField,
            StructType,
        )

        text_columns = [
            "event_id", "event_name", "product_id", "brand_id", "session_id",
            "banner_type", "banner_value", "trait_source", "policy_version",
            "actor_type", "source", "scenario_id", "simulation_run_id",
        ]
        schema = StructType(
            [StructField(name, StringType(), True) for name in text_columns]
            + [
                StructField("banner_slot", IntegerType(), True),
                StructField("event_date_kst", DateType(), True),
            ]
        )
        fact = self.spark.createDataFrame(
            [
                (
                    "e1", "product_view", "P1", "B1", "S1",
                    None, None, None, None,
                    "user", "web", None, None,
                    None, date(2026, 9, 8),
                )
            ],
            schema,
        )

        daily = _banner_daily(fact, {"Pores"})
        self.assertEqual(0, daily.count())

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "banner_daily")
            _write_mart(daily, path, "event_date_kst")
            restored = self.spark.read.option("mergeSchema", "true").parquet(path)

            self.assertEqual(0, restored.count())
            self.assertIn("banner_ctr", restored.columns)
            self.assertIn("event_date_kst", restored.columns)

    def test_analytics_baseline_keeps_pre_banner_metrics_only(self):
        facts = self.spark.createDataFrame(
            [
                ("e1", date(2026, 9, 1), "A", "recommendation_impression", "cf_v1"),
                ("e2", date(2026, 9, 1), "A", "recommendation_impression", "cf_v1"),
                ("e3", date(2026, 9, 1), "A", "recommendation_click", "cf_v1"),
                # 기간 밖이므로 기준선에 들어오면 안 된다.
                ("e4", date(2026, 9, 9), "A", "recommendation_click", "cf_v1"),
                ("e5", date(2026, 9, 1), "A", "banner_impression", None),
            ],
            ["event_id", "event_date_kst", "brand_id", "event_name", "algorithm"],
        )
        cross_brand = self.spark.createDataFrame(
            [
                (date(2026, 9, 1), "A", 10, 4),
                (date(2026, 9, 9), "A", 100, 90),
            ],
            [
                "event_date_kst",
                "destination_brand_id",
                "brand_view_sessions",
                "cross_brand_entry_sessions",
            ],
        )

        baseline = _analytics_baseline(
            facts, cross_brand, "pre_banner_sort_v1", "2026-09-01", "2026-09-07"
        )
        rows = {row["metric_name"]: row for row in baseline.collect()}

        self.assertEqual({"recommendation_ctr", "cross_brand_entry_rate"}, set(rows))
        recommendation = rows["recommendation_ctr"]
        self.assertEqual(2, recommendation["denominator"])
        self.assertEqual(1, recommendation["numerator"])
        self.assertAlmostEqual(0.5, recommendation["metric_value"])
        self.assertEqual("cf_v1", recommendation["algorithm"])
        cross = rows["cross_brand_entry_rate"]
        self.assertEqual(10, cross["denominator"])
        self.assertAlmostEqual(0.4, cross["metric_value"])
        self.assertIsNone(cross["algorithm"])
        for row in rows.values():
            self.assertEqual("pre_banner_sort_v1", row["baseline_policy_version"])
            self.assertEqual(date(2026, 9, 1), row["baseline_start_date"])
            self.assertEqual(date(2026, 9, 7), row["baseline_end_date"])


if __name__ == "__main__":
    unittest.main()
