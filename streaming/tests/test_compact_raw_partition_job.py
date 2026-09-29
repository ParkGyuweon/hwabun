import os
import shutil
import tempfile
import unittest
from pathlib import Path

from streaming.jobs.compact_raw_partition_job import (
    DEFAULT_TARGET_FILE_BYTES,
    CompactConfig,
    parse_args,
    run,
    skip_reason,
    target_file_count,
)

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

# Local Parquet writes on Windows need Hadoop winutils; the Spark image has none
# of that problem, so the write test runs there.
CAN_WRITE_LOCAL = SparkSession is not None and (
    os.name != "nt" or bool(os.getenv("HADOOP_HOME"))
)


def _skip(**overrides):
    args = {
        "partition_date": "2026-09-28",
        "today_utc": "2026-09-29",
        "partition_exists": True,
        "sink_log_present": False,
        "current_file_count": 500,
        "wanted_file_count": 1,
    }
    args.update(overrides)
    return skip_reason(**args)


class CompactPlanTest(unittest.TestCase):
    def test_default_target_is_128mb(self):
        self.assertEqual(128 * 1024 * 1024, DEFAULT_TARGET_FILE_BYTES)
        self.assertEqual(128 * 1024 * 1024, parse_args(["--date", "2026-09-28"]).target_file_bytes)

    def test_target_file_count_rounds_up_and_never_hits_zero(self):
        mb = 1024 * 1024
        self.assertEqual(1, target_file_count(0, 128 * mb))
        self.assertEqual(1, target_file_count(5 * mb, 128 * mb))
        self.assertEqual(2, target_file_count(129 * mb, 128 * mb))

    def test_bad_date_is_rejected(self):
        with self.assertRaises(ValueError):
            CompactConfig(partition_date="yesterday")

    def test_runs_only_for_a_finished_fragmented_partition_without_sink_log(self):
        self.assertIsNone(_skip())
        self.assertEqual("partition_not_finished", _skip(partition_date="2026-09-29"))
        self.assertEqual("partition_missing", _skip(partition_exists=False))
        self.assertEqual("sink_log_present", _skip(sink_log_present=True))
        self.assertEqual("already_compact", _skip(current_file_count=1))


@unittest.skipUnless(CAN_WRITE_LOCAL, "needs pyspark with local Parquet writes")
class CompactRawPartitionSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("compact-raw-partition-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "raw_events"
        rows = self.spark.sql(
            """
            SELECT 'ec2-2' AS kafka_cluster_id, 'activity-events' AS kafka_topic,
                   CAST(id % 3 AS INT) AS kafka_partition, id AS kafka_offset,
                   CAST(id AS STRING) AS event_id,
                   DATE'2026-09-28' AS raw_ingest_date
            FROM range(60)
            """
        )
        rows.repartition(6).write.partitionBy("raw_ingest_date").parquet(str(self.root))
        self.partition = self.root / "raw_ingest_date=2026-09-28"

    def tearDown(self):
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def _parquet_files(self):
        return sorted(self.partition.glob("*.parquet"))

    def test_fragmented_partition_is_rewritten_with_the_same_rows(self):
        self.assertGreater(len(self._parquet_files()), 1)
        before = sorted(
            r.asDict() for r in self.spark.read.parquet(str(self.root)).collect()
        )

        report = run(
            self.spark,
            CompactConfig(raw_path=str(self.root), partition_date="2026-09-28"),
            today_utc="2026-09-29",
        )

        self.assertEqual("compacted", report["status"])
        self.assertEqual(1, len(self._parquet_files()))
        self.assertFalse((self.root / "_compaction_tmp" / self.partition.name).exists())
        self.assertFalse((self.root / "_compaction_backup" / self.partition.name).exists())
        # Q2 reads the Raw root with partition discovery; the result must not move.
        after = sorted(
            r.asDict()
            for r in self.spark.read.option("mergeSchema", "true")
            .parquet(str(self.root))
            .collect()
        )
        self.assertEqual(before, after)

    def test_sink_log_makes_the_job_a_no_op(self):
        (self.root / "_spark_metadata").mkdir()
        files = self._parquet_files()

        report = run(
            self.spark,
            CompactConfig(raw_path=str(self.root), partition_date="2026-09-28"),
            today_utc="2026-09-29",
        )

        self.assertEqual("skipped", report["status"])
        self.assertEqual("sink_log_present", report["reason"])
        self.assertEqual(files, self._parquet_files())


if __name__ == "__main__":
    unittest.main()
