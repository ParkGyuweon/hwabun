import json
import unittest
from datetime import datetime, timezone

from streaming.jobs.clean_events_job import build_processed_frames
from streaming.jobs.raw_sink_job import build_raw_events_frame


try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        BinaryType,
        IntegerType,
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )
except ImportError:  # pragma: no cover - local machines may use Docker Spark only
    SparkSession = None


@unittest.skipIf(SparkSession is None, "pyspark is not installed")
class RawToCleanedSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("raw-cleaned-contract-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    @staticmethod
    def _event(
        event_id,
        event_name="banner_impression",
        intent="session",
        received_at="2026-09-09T01:00:00Z",
        product_id="P1",
        properties=None,
    ):
        if properties is None:
            properties = {
                "banner_type": "new_brand",
                "banner_value": None,
                "banner_slot": 1,
                "trait_source": "explore",
                "policy_version": "banner_sort_v1",
            }
        return {
            "schema_version": "0.2.0-draft",
            "event_id": event_id,
            "event_name": event_name,
            "intent": intent,
            "occurred_at": "2026-09-09T00:59:59Z",
            "received_at": received_at,
            "source": "web",
            "persona_id": None,
            "session_id": "session-150",
            "page_view_id": "page-150",
            "sequence_no": 1,
            "page_type": "product_list",
            "product_id": product_id,
            "actor_type": "user",
            "environment": "test",
            "request_id": "request-150",
            "event_index": 0,
            "properties": properties,
        }

    def _kafka_frame(self, payloads):
        schema = StructType(
            [
                StructField("key", BinaryType(), True),
                StructField("value", BinaryType(), True),
                StructField("topic", StringType(), False),
                StructField("partition", IntegerType(), False),
                StructField("offset", LongType(), False),
                StructField("timestamp", TimestampType(), False),
                StructField("timestampType", IntegerType(), False),
            ]
        )
        now = datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)
        rows = [
            (
                b"session-150",
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "activity-events",
                index % 2,
                index,
                now,
                0,
            )
            for index, payload in enumerate(payloads)
        ]
        return self.spark.createDataFrame(rows, schema)

    def test_raw_is_lossless_and_q2_routes_banner_duplicates_and_errors(self):
        first = self._event("banner-duplicate")
        later = self._event(
            "banner-duplicate", received_at="2026-09-09T01:00:01Z"
        )
        click = self._event(
            "banner-click",
            event_name="banner_click",
            intent="interest",
            properties={
                "banner_type": "concern",
                "banner_value": "Pores",
                "banner_slot": 2,
                "trait_source": "session",
            },
        )
        unknown = self._event("unknown", event_name="unknown_event")
        wrong_intent = self._event("wrong-intent", intent="interest")
        missing_product = self._event("missing-product", product_id=None)
        invalid_slot = self._event(
            "invalid-slot",
            properties={
                "banner_type": "concern",
                "banner_value": "Pores",
                "banner_slot": 0,
                "trait_source": "session",
            },
        )
        invalid_source = self._event("invalid-source")
        invalid_source["source"] = "simulator"
        invalid_event_index = self._event("invalid-event-index")
        invalid_event_index["event_index"] = -1
        missing_properties = self._event("missing-properties")
        del missing_properties["properties"]
        payloads = [
            first,
            later,
            click,
            unknown,
            wrong_intent,
            missing_product,
            invalid_slot,
            invalid_source,
            invalid_event_index,
            missing_properties,
        ]
        raw_json = [json.dumps(payload, separators=(",", ":")) for payload in payloads]
        kafka = self._kafka_frame(payloads)
        raw = build_raw_events_frame(kafka, "test-cluster")
        frames = build_processed_frames(raw, "Asia/Seoul")

        self.assertEqual(10, raw.count())
        self.assertEqual(raw_json[0], raw.orderBy("kafka_offset").first()["raw_value"])
        self.assertEqual(2, frames["cleaned_events"].count())
        self.assertEqual(1, frames["duplicate_events"].count())
        self.assertEqual(7, frames["bad_events"].count())
        self.assertEqual(
            {"banner-duplicate", "banner-click"},
            {row["event_id"] for row in frames["cleaned_events"].select("event_id").collect()},
        )
        self.assertEqual(
            {
                "invalid_enum",
                "missing_product_id",
                "invalid_banner_properties",
                "invalid_event_index",
                "invalid_properties",
                "invalid_source",
            },
            {row["error_code"] for row in frames["bad_events"].select("error_code").collect()},
        )
        duplicate = frames["duplicate_events"].first()
        self.assertEqual("banner-duplicate", duplicate["event_id"])
        self.assertEqual(2, duplicate["canonical_rank"])
        self.assertEqual(2, duplicate["candidate_count"])

    def test_scroll_product_scope_depends_on_page_type(self):
        events = []
        for event_name, intent in (
            ("scroll_depth", "exposure"),
            ("scroll_pause", "interest"),
        ):
            platform = self._event(
                f"{event_name}-platform",
                event_name=event_name,
                intent=intent,
                product_id=None,
                properties={"depth_percent": 50},
            )
            detail = self._event(
                f"{event_name}-detail",
                event_name=event_name,
                intent=intent,
                product_id=None,
                properties={"depth_percent": 50},
            )
            detail["page_type"] = "product_detail"
            events.extend((platform, detail))

        raw = build_raw_events_frame(self._kafka_frame(events), "test-cluster")
        frames = build_processed_frames(raw, "Asia/Seoul")

        self.assertEqual(
            {"scroll_depth-platform", "scroll_pause-platform"},
            {
                row["event_id"]
                for row in frames["cleaned_events"].select("event_id").collect()
            },
        )
        self.assertEqual(
            {"scroll_depth-detail", "scroll_pause-detail"},
            {
                row["event_id"]
                for row in frames["bad_events"]
                .where("error_code = 'missing_product_id'")
                .select("event_id")
                .collect()
            },
        )


if __name__ == "__main__":
    unittest.main()
