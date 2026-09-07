import re
import unittest

from streaming.jobs.raw_sink_job import (
    RAW_EVENT_FIELDS,
    RawSinkConfig,
    parse_args,
)
from streaming.jobs.clean_events_job import (
    CANONICAL_ORDER_FIELDS,
    CleanEventsConfig,
    RFC3339_WITH_OFFSET_PATTERN,
    SUPPORTED_SCHEMA_VERSIONS,
    TENANT_ID_PATTERN,
    parse_args as parse_clean_args,
)
from streaming.jobs.derive_facts_job import (
    CONTENT_INTEREST_EVENTS,
    DEFAULT_CONTENT_INTEREST_PATH,
    DEFAULT_DIM_PRODUCT_PATH,
    DEFAULT_PRODUCT_FACT_PATH,
    DEFAULT_SECTION_DWELL_PATH,
    DEFAULT_SESSIONIZED_PATH,
    DEFAULT_BEHAVIOR_WEIGHTS_PATH,
    PRODUCT_EVENT_NAMES,
    DeriveFactsConfig,
    parse_args as parse_derive_args,
)
from streaming.jobs.build_marts_job import (
    DEFAULT_FUNNEL_DAILY_PATH,
    DEFAULT_FUNNEL_SESSION_PATH,
    DEFAULT_PRODUCT_DAILY_PATH,
    FUNNEL_PRODUCT_EVENTS,
    BuildMartsConfig,
    parse_args as parse_mart_args,
)
from streaming.jobs.validate_pipeline_job import (
    DEFAULT_CONTENT_INTEREST_PATH as DEFAULT_VALIDATE_CONTENT_INTEREST_PATH,
    DEFAULT_DIM_PRODUCT_PATH as DEFAULT_VALIDATE_DIM_PRODUCT_PATH,
    DEFAULT_FUNNEL_DAILY_PATH as DEFAULT_VALIDATE_FUNNEL_DAILY_PATH,
    DEFAULT_PRODUCT_DAILY_PATH as DEFAULT_VALIDATE_PRODUCT_DAILY_PATH,
    DEFAULT_SECTION_DWELL_PATH as DEFAULT_VALIDATE_SECTION_DWELL_PATH,
    ValidatePipelineConfig,
    parse_args as parse_validate_args,
)
from streaming.jobs.behavior_weights import load as load_behavior_weights


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
            "source",
            "tenant_id",
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


class CleanEventsConfigTest(unittest.TestCase):
    def test_canonical_order_matches_team_contract(self):
        self.assertEqual(
            (
                "received_at",
                "kafka_topic",
                "kafka_partition",
                "kafka_offset",
            ),
            CANONICAL_ORDER_FIELDS,
        )

    def test_defaults_use_q1_raw_path_and_processed_outputs(self):
        config = parse_clean_args([])

        self.assertEqual("data/raw_events", config.input_path)
        self.assertEqual("data/processed/cleaned_events", config.cleaned_path)
        self.assertEqual("data/processed/bad_events", config.bad_path)
        self.assertEqual("data/processed/duplicate_events", config.duplicate_path)

    def test_schema_version_transition_and_tenant_slug_contract(self):
        self.assertEqual(
            ("0.2.0-draft", "0.3.0-draft"),
            SUPPORTED_SCHEMA_VERSIONS,
        )
        self.assertIsNotNone(re.fullmatch(TENANT_ID_PATTERN, "estee-lauder"))
        self.assertIsNone(re.fullmatch(TENANT_ID_PATTERN, "Estee Lauder"))

    def test_empty_output_path_is_rejected(self):
        with self.assertRaises(ValueError):
            CleanEventsConfig(cleaned_path=" ")

    def test_timestamp_contract_accepts_explicit_rfc3339_offsets(self):
        self.assertIsNotNone(
            re.fullmatch(
                RFC3339_WITH_OFFSET_PATTERN,
                "2026-08-31T10:00:00.123+09:00",
            )
        )
        self.assertIsNotNone(
            re.fullmatch(
                RFC3339_WITH_OFFSET_PATTERN,
                "2026-08-31T01:00:00Z",
            )
        )

    def test_timestamp_contract_rejects_timezone_less_values(self):
        self.assertIsNone(
            re.fullmatch(
                RFC3339_WITH_OFFSET_PATTERN,
                "2026-08-31T10:00:00.123",
            )
        )


class DeriveFactsConfigTest(unittest.TestCase):
    def test_product_event_scope_matches_processed_contract(self):
        self.assertIn("product_view", PRODUCT_EVENT_NAMES)
        self.assertIn("purchase", PRODUCT_EVENT_NAMES)
        self.assertNotIn("view_cart", PRODUCT_EVENT_NAMES)

    def test_defaults_point_to_q2_and_fact_outputs(self):
        config = parse_derive_args([])

        self.assertEqual("data/processed/cleaned_events", config.input_path)
        self.assertEqual(DEFAULT_SESSIONIZED_PATH, config.sessionized_path)
        self.assertEqual(DEFAULT_PRODUCT_FACT_PATH, config.product_fact_path)
        self.assertEqual(DEFAULT_SECTION_DWELL_PATH, config.section_dwell_path)
        self.assertEqual(DEFAULT_CONTENT_INTEREST_PATH, config.content_interest_path)
        self.assertEqual(DEFAULT_DIM_PRODUCT_PATH, config.dim_product_path)
        self.assertEqual(DEFAULT_BEHAVIOR_WEIGHTS_PATH, config.behavior_weights_path)

    def test_content_interest_scope_is_limited_to_contract_events(self):
        self.assertEqual(
            {
                "accordion_toggle",
                "review_filter_apply",
                "text_selection",
                "text_copy",
            },
            set(CONTENT_INTEREST_EVENTS),
        )

    def test_empty_fact_path_is_rejected(self):
        with self.assertRaises(ValueError):
            DeriveFactsConfig(product_fact_path="")


class BehaviorWeightContractTest(unittest.TestCase):
    def test_spark_uses_frontend_weight_source(self):
        weights = load_behavior_weights()

        self.assertTrue(weights["event"])
        self.assertTrue(weights["section"])
        self.assertTrue(
            {"accordion_toggle", "review_filter_apply", "text_selection", "text_copy"}
            .issubset(weights["event"])
        )
        self.assertLess(weights["event"]["remove_from_cart"], 0)


class BuildMartsConfigTest(unittest.TestCase):
    def test_funnel_scope_contains_product_and_checkout_stages(self):
        self.assertIn("product_view", FUNNEL_PRODUCT_EVENTS)
        self.assertIn("purchase", FUNNEL_PRODUCT_EVENTS)
        self.assertNotIn("view_cart", FUNNEL_PRODUCT_EVENTS)

    def test_defaults_chain_q3_inputs_to_mart_outputs(self):
        config = parse_mart_args([])

        self.assertEqual("data/processed/sessionized_events", config.sessionized_path)
        self.assertEqual("data/processed/product_event_fact", config.product_fact_path)
        self.assertEqual(DEFAULT_FUNNEL_SESSION_PATH, config.funnel_session_path)
        self.assertEqual(DEFAULT_PRODUCT_DAILY_PATH, config.product_daily_path)
        self.assertEqual(DEFAULT_FUNNEL_DAILY_PATH, config.funnel_daily_path)
        self.assertEqual("frontend/src/types/log.ts", config.behavior_weights_path)

    def test_empty_mart_path_is_rejected(self):
        with self.assertRaises(ValueError):
            BuildMartsConfig(funnel_daily_path=" ")


class ValidatePipelineConfigTest(unittest.TestCase):
    def test_defaults_match_pipeline_outputs(self):
        config = parse_validate_args([])

        self.assertEqual("data/raw_events", config.raw_path)
        self.assertEqual("data/processed/cleaned_events", config.cleaned_path)
        self.assertEqual(
            DEFAULT_VALIDATE_SECTION_DWELL_PATH, config.section_dwell_path
        )
        self.assertEqual(
            DEFAULT_VALIDATE_CONTENT_INTEREST_PATH, config.content_interest_path
        )
        self.assertEqual(DEFAULT_VALIDATE_DIM_PRODUCT_PATH, config.dim_product_path)
        self.assertEqual(DEFAULT_VALIDATE_PRODUCT_DAILY_PATH, config.product_daily_path)
        self.assertEqual(DEFAULT_VALIDATE_FUNNEL_DAILY_PATH, config.funnel_daily_path)
        self.assertFalse(config.require_events)

    def test_empty_report_path_is_rejected(self):
        with self.assertRaises(ValueError):
            ValidatePipelineConfig(report_path=" ")


if __name__ == "__main__":
    unittest.main()
