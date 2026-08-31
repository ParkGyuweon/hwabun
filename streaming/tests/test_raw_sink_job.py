import unittest

from streaming.jobs.raw_sink_job import (
    RAW_EVENT_FIELDS,
    RawSinkConfig,
    parse_args,
)


class RawSinkConfigTest(unittest.TestCase):
    def test_defaults_match_local_kafka_contract(self):
        config = parse_args([])

        self.assertEqual("localhost:9092", config.bootstrap_servers)
        self.assertEqual("activity-events", config.topic)
        self.assertEqual("earliest", config.starting_offsets)
        self.assertIsNone(config.max_offsets_per_trigger)

    def test_raw_schema_keeps_kafka_coordinates_and_original_value(self):
        required = {
            "kafka_cluster_id",
            "kafka_topic",
            "kafka_partition",
            "kafka_offset",
            "raw_value",
            "is_json_parseable",
            "properties_json",
        }

        self.assertTrue(required.issubset(set(RAW_EVENT_FIELDS)))

    def test_invalid_max_offsets_is_rejected(self):
        with self.assertRaises(ValueError):
            RawSinkConfig(max_offsets_per_trigger=0)

    def test_custom_runtime_options_are_parsed(self):
        config = parse_args(
            [
                "--bootstrap-servers",
                "kafka:19092",
                "--topic",
                "activity-events-dev",
                "--max-offsets-per-trigger",
                "5000",
                "--cluster-id",
                "dev-local",
            ]
        )

        self.assertEqual("kafka:19092", config.bootstrap_servers)
        self.assertEqual("activity-events-dev", config.topic)
        self.assertEqual(5000, config.max_offsets_per_trigger)
        self.assertEqual("dev-local", config.cluster_id)


if __name__ == "__main__":
    unittest.main()
