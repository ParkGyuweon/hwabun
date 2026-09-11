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
        account_id=None,
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
            "account_id": account_id,
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

    def test_user_id_and_identity_scope_split_three_ways(self):
        """로그인·비로그인·합성 로그가 각각 다른 식별자 축으로 정리돼야 한다."""
        member = self._event("member-login", account_id="acc-1")
        anonymous = self._event("anonymous-visit")
        synthetic = self._event("synthetic-run")
        synthetic.update({
            "actor_type": "synthetic",
            "source": "simulator",
            "persona_id": "PC00001",
        })
        synthetic["properties"] = dict(
            synthetic["properties"],
            scenario_id="K01",
            simulation_run_id="RUN1",
            generator_type="python_batch",
        )
        # 합성 로그에 계정 식별자가 오면 두 축이 섞이므로 격리한다.
        contaminated = self._event("synthetic-with-account", account_id="acc-2")
        contaminated.update({
            "actor_type": "synthetic",
            "source": "simulator",
            "persona_id": "PC00002",
        })
        contaminated["properties"] = dict(
            contaminated["properties"],
            scenario_id="K01",
            simulation_run_id="RUN1",
            generator_type="python_batch",
        )

        raw = build_raw_events_frame(
            self._kafka_frame([member, anonymous, synthetic, contaminated]),
            "test-cluster",
        )
        frames = build_processed_frames(raw, "Asia/Seoul")
        rows = {
            row["event_id"]: row
            for row in frames["cleaned_events"]
            .select("event_id", "user_id", "identity_scope", "account_id")
            .collect()
        }

        self.assertEqual({"member-login", "anonymous-visit", "synthetic-run"}, set(rows))
        self.assertEqual("acc-1", rows["member-login"]["user_id"])
        self.assertEqual("account", rows["member-login"]["identity_scope"])
        self.assertIsNone(rows["anonymous-visit"]["user_id"])
        self.assertEqual("session", rows["anonymous-visit"]["identity_scope"])
        self.assertEqual("PC00001", rows["synthetic-run"]["user_id"])
        self.assertEqual("persona", rows["synthetic-run"]["identity_scope"])
        self.assertEqual(
            {"synthetic-with-account"},
            {
                row["event_id"]
                for row in frames["bad_events"]
                .where("error_code = 'invalid_identity_scope'")
                .select("event_id")
                .collect()
            },
        )

        raw_account = {
            row["event_id"]: row["account_id"]
            for row in raw.select("event_id", "account_id").collect()
        }
        self.assertEqual("acc-1", raw_account["member-login"])
        self.assertIsNone(raw_account["anonymous-visit"])

    def test_is_seed_comes_from_the_seeded_property(self):
        """시드 Event는 주입된 선호 표식이라 한 컬럼으로 걸러낼 수 있어야 한다.

        판정 정본은 `properties.seeded` 다. `session_id` 의 "seed:" 접두는 파생이라
        쓰지 않는다 (event-properties-schema.md §3.14).
        """

        def _synthetic(event_id, **overrides):
            event = self._event(event_id)
            event.update({
                "actor_type": "synthetic",
                "source": "simulator",
                "persona_id": "PC00001",
            })
            event["properties"] = dict(
                event["properties"],
                scenario_id="K01",
                simulation_run_id="RUN1",
                generator_type="python_batch",
                **overrides.pop("properties", {}),
            )
            event.update(overrides)
            return event

        seeded = _synthetic(
            "seed-event",
            session_id="seed:RUN1:PC00001:P1",
            properties={"seeded": True},
        )
        observed = _synthetic("observed-event")
        # session_id 만 시드 형식이고 표식이 없으면 관측 행동이다.
        lookalike = _synthetic("seed-shaped-session", session_id="seed:RUN1:PC00001:P2")

        raw = build_raw_events_frame(
            self._kafka_frame([seeded, observed, lookalike]),
            "test-cluster",
        )
        frames = build_processed_frames(raw, "Asia/Seoul")
        rows = {
            row["event_id"]: row["is_seeded"]
            for row in frames["cleaned_events"].select("event_id", "is_seeded").collect()
        }

        self.assertTrue(rows["seed-event"])
        self.assertFalse(rows["observed-event"])
        self.assertFalse(rows["seed-shaped-session"])

    def test_seed_marker_on_real_user_traffic_is_quarantined(self):
        """실사용자 Event에는 주입 표식이 올 수 없다 (event-properties-schema.md §7-8)."""
        contaminated = self._event("user-with-seed-marker")
        contaminated["properties"] = dict(contaminated["properties"], seeded=True)

        raw = build_raw_events_frame(
            self._kafka_frame([contaminated, self._event("clean-user")]),
            "test-cluster",
        )
        frames = build_processed_frames(raw, "Asia/Seoul")

        self.assertEqual(
            {"clean-user"},
            {row["event_id"] for row in frames["cleaned_events"].select("event_id").collect()},
        )
        self.assertEqual(
            {"user-with-seed-marker"},
            {
                row["event_id"]
                for row in frames["bad_events"]
                .where("error_code = 'invalid_seed_scope'")
                .select("event_id")
                .collect()
            },
        )


if __name__ == "__main__":
    unittest.main()
