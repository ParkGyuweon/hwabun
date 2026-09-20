import os
import tempfile
import unittest
from datetime import date

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import DateType, StringType, StructField, StructType
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.clean_events_job import _write_processed_dataset


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class CleanEventsWriteSparkTest(unittest.TestCase):
    """거부도 중복도 없는 실행에서 Q2 출력이 다시 읽히는지 본다.

    bad_events 와 duplicate_events 는 정상 실행에서 0행이다. 그때 partitionBy 로 쓰면
    `_SUCCESS` 만 남아 Q5 가 UNABLE_TO_INFER_SCHEMA 로 죽는다 (실행 검증에서 발견).
    """

    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("clean-events-write-contract-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

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
            path = os.path.join(directory, "duplicate_events")
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
            path = os.path.join(directory, "cleaned_events")
            _write_processed_dataset(frame, path, "event_date_kst")
            restored = self.spark.read.option("mergeSchema", "true").parquet(path)

            self.assertTrue(
                os.path.isdir(os.path.join(path, "event_date_kst=2026-09-09"))
            )
            self.assertEqual(
                [("event-1", date(2026, 9, 9))],
                [tuple(row) for row in restored.collect()],
            )


if __name__ == "__main__":
    unittest.main()
