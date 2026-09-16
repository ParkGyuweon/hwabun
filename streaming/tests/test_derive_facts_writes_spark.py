import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import DateType, StringType, StructField, StructType
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.derive_facts_job import _write_processed_dataset
from streaming.jobs.validate_pipeline_job import (
    DEFAULT_BEHAVIOR_WEIGHTS_PATH,
    DEFAULT_REASON_TRAIT_MAP_PATH,
    ValidatePipelineConfig,
    run as run_validation,
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class DeriveFactsWriteSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("derive-facts-write-contract-test")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    @staticmethod
    def _schema():
        return StructType(
            [
                StructField("event_id", StringType(), True),
                StructField("event_date_kst", DateType(), True),
            ]
        )

    def test_empty_partitioned_output_keeps_a_readable_parquet_schema(self):
        empty = self.spark.createDataFrame([], self._schema())

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "empty_fact")
            _write_processed_dataset(empty, path, "event_date_kst")
            restored = self.spark.read.option("mergeSchema", "true").parquet(path)

            self.assertEqual(0, restored.count())
            self.assertEqual(empty.schema, restored.schema)

    def test_non_empty_output_is_partitioned_by_event_date(self):
        frame = self.spark.createDataFrame(
            [("event-1", date(2026, 9, 9))],
            self._schema(),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "normal_fact")
            _write_processed_dataset(frame, path, "event_date_kst")
            restored = self.spark.read.option("mergeSchema", "true").parquet(path)

            partition_path = os.path.join(path, "event_date_kst=2026-09-09")
            self.assertTrue(os.path.isdir(partition_path))
            self.assertEqual(
                [("event-1", date(2026, 9, 9))],
                [tuple(row) for row in restored.collect()],
            )

    def test_validation_job_reads_all_empty_derived_fact_outputs(self):
        empty = self.spark.createDataFrame([], self._schema())

        with tempfile.TemporaryDirectory() as directory:
            supporting_path = os.path.join(directory, "supporting_dataset")
            empty.write.mode("overwrite").parquet(supporting_path)
            derived_paths = {
                name: os.path.join(directory, name)
                for name in (
                    "sessionized",
                    "product_fact",
                    "purchase_fact",
                    "purchase_reason_fact",
                    "review_event_fact",
                    "section_dwell",
                    "content_interest",
                )
            }
            for path in derived_paths.values():
                _write_processed_dataset(empty, path, "event_date_kst")

            config = ValidatePipelineConfig(
                raw_path=supporting_path,
                cleaned_path=supporting_path,
                bad_path=supporting_path,
                duplicate_path=supporting_path,
                sessionized_path=derived_paths["sessionized"],
                product_fact_path=derived_paths["product_fact"],
                purchase_fact_path=derived_paths["purchase_fact"],
                purchase_reason_fact_path=derived_paths["purchase_reason_fact"],
                review_event_fact_path=derived_paths["review_event_fact"],
                section_dwell_path=derived_paths["section_dwell"],
                content_interest_path=derived_paths["content_interest"],
                dim_product_path=supporting_path,
                dim_brand_path=supporting_path,
                funnel_session_path=supporting_path,
                product_daily_path=supporting_path,
                funnel_daily_path=supporting_path,
                brand_daily_path=supporting_path,
                product_repurchase_path=supporting_path,
                brand_repurchase_path=supporting_path,
                purchase_reason_path=supporting_path,
                reason_trait_map_path=DEFAULT_REASON_TRAIT_MAP_PATH,
                ingredient_weekly_path=supporting_path,
                category_price_path=supporting_path,
                banner_daily_path=supporting_path,
                user_trait_daily_path=supporting_path,
                cross_brand_daily_path=supporting_path,
                content_daily_path=supporting_path,
                content_conversion_path=supporting_path,
                behavior_conversion_path=supporting_path,
                friction_daily_path=supporting_path,
                exit_daily_path=supporting_path,
                entry_source_daily_path=supporting_path,
                baseline_path=supporting_path,
            )

            def verify_loaded_frames(
                frames, require_events, time_zone, reason_map_path, weights_path
            ):
                self.assertFalse(require_events)
                self.assertEqual("Asia/Seoul", time_zone)
                self.assertEqual(DEFAULT_REASON_TRAIT_MAP_PATH, reason_map_path)
                self.assertEqual(DEFAULT_BEHAVIOR_WEIGHTS_PATH, weights_path)
                for name in derived_paths:
                    self.assertEqual(0, frames[name].count())
                    self.assertEqual(empty.schema, frames[name].schema)
                return {"status": "passed"}

            with patch(
                "streaming.jobs.validate_pipeline_job.validate_frames",
                side_effect=verify_loaded_frames,
            ):
                self.assertEqual(
                    {"status": "passed"},
                    run_validation(self.spark, config),
                )


if __name__ == "__main__":
    unittest.main()
