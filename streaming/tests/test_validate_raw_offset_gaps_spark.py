import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import _raw_kafka_offset_gaps


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class RawKafkaOffsetGapSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("raw-kafka-offset-gap-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _raw(self, rows):
        # SQL VALUES keeps the frame on the JVM side (no Python worker needed).
        values = ", ".join(
            f"('{cluster}', '{topic}', {partition}, "
            f"{'NULL' if offset is None else offset})"
            for cluster, topic, partition, offset in rows
        )
        return self.spark.sql(
            "SELECT kafka_cluster_id, kafka_topic, CAST(kafka_partition AS INT) "
            "AS kafka_partition, CAST(kafka_offset AS BIGINT) AS kafka_offset "
            f"FROM VALUES {values} "
            "AS t(kafka_cluster_id, kafka_topic, kafka_partition, kafka_offset)"
        )

    def test_contiguous_offsets_report_no_gap(self):
        # Partition 0 starts at 5 (older records expired from Kafka) -- not a gap.
        # A replayed coordinate (offset 6 twice) is not a gap either.
        raw = self._raw([
            ("ec2-2", "activity-events", 0, 5),
            ("ec2-2", "activity-events", 0, 6),
            ("ec2-2", "activity-events", 0, 6),
            ("ec2-2", "activity-events", 0, 7),
            ("ec2-2", "activity-events", 1, 0),
            ("ec2-2", "activity-events", 1, 1),
        ])

        self.assertEqual(
            {"partitions_checked": 2, "gap_count": 0, "missing_offsets": 0},
            _raw_kafka_offset_gaps(raw),
        )

    def test_holes_are_counted_per_partition(self):
        raw = self._raw([
            ("ec2-2", "activity-events", 0, 0),
            ("ec2-2", "activity-events", 0, 3),  # hole: 1, 2
            ("ec2-2", "activity-events", 0, 4),
            ("ec2-2", "activity-events", 0, 9),  # hole: 5..8
            # Same offsets in another partition must not bridge partition 0.
            ("ec2-2", "activity-events", 1, 1),
            ("ec2-2", "activity-events", 1, 2),
            # A different cluster is a separate offset space.
            ("local", "activity-events", 0, 100),
            ("local", "activity-events", 0, 102),  # hole: 101
            ("ec2-2", "activity-events", 2, None),
        ])

        self.assertEqual(
            {"partitions_checked": 3, "gap_count": 3, "missing_offsets": 7},
            _raw_kafka_offset_gaps(raw),
        )


if __name__ == "__main__":
    unittest.main()
