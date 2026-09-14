import re
import json
import unittest
from pathlib import Path

from streaming.jobs.raw_sink_job import (
    RAW_EVENT_FIELDS,
    RawSinkConfig,
    parse_args,
)
from streaming.jobs.clean_events_job import (
    CANONICAL_ORDER_FIELDS,
    CleanEventsConfig,
    EVENT_INTENTS,
    PRODUCT_DETAIL_SCOPED_EVENTS,
    PRODUCT_ID_REQUIRED_EVENTS,
    RFC3339_WITH_OFFSET_PATTERN,
    SUPPORTED_SCHEMA_VERSIONS,
    parse_args as parse_clean_args,
)
from streaming.jobs.build_marts_job import (
    ORDER_CHANNELS as MART_ORDER_CHANNELS,
    PAYMENT_METHODS as MART_PAYMENT_METHODS,
)
from streaming.jobs.validate_pipeline_job import (
    ORDER_CHANNELS as VALIDATE_ORDER_CHANNELS,
    PAYMENT_METHODS as VALIDATE_PAYMENT_METHODS,
)
from streaming.jobs.derive_facts_job import (
    CONTENT_INTEREST_EVENTS,
    DEFAULT_CONTENT_INTEREST_PATH,
    DEFAULT_DIM_PRODUCT_PATH,
    DEFAULT_DIM_BRAND_PATH,
    DEFAULT_PRODUCT_FACT_PATH,
    DEFAULT_PURCHASE_FACT_PATH,
    DEFAULT_PURCHASE_REASON_FACT_PATH,
    DEFAULT_REVIEW_EVENT_FACT_PATH,
    DEFAULT_SECTION_DWELL_PATH,
    DEFAULT_SESSIONIZED_PATH,
    DEFAULT_BEHAVIOR_WEIGHTS_PATH,
    PRODUCT_EVENT_NAMES,
    DeriveFactsConfig,
    parse_args as parse_derive_args,
)
from streaming.jobs.build_marts_job import (
    DEFAULT_BRAND_DAILY_PATH,
    DEFAULT_BRAND_REPURCHASE_PATH,
    DEFAULT_PRODUCT_REPURCHASE_PATH,
    DEFAULT_PURCHASE_REASON_PATH,
    DEFAULT_REASON_TRAIT_MAP_PATH,
    DEFAULT_REPURCHASE_WINDOW_DAYS,
    DEFAULT_CATEGORY_PRICE_PATH,
    DEFAULT_CLEANSING_CATEGORY_WEIGHT,
    DEFAULT_FUNNEL_DAILY_PATH,
    DEFAULT_FUNNEL_SESSION_PATH,
    DEFAULT_INGREDIENT_VOCAB_PATH,
    DEFAULT_INGREDIENT_WEEKLY_PATH,
    DEFAULT_PRICE_MIN_SAMPLE_SIZE,
    DEFAULT_PRODUCT_INGREDIENT_PATH,
    DEFAULT_PRODUCT_DAILY_PATH,
    FUNNEL_PRODUCT_EVENTS,
    BuildMartsConfig,
    parse_args as parse_mart_args,
)
from streaming.jobs.validate_pipeline_job import (
    DEFAULT_BRAND_DAILY_PATH as DEFAULT_VALIDATE_BRAND_DAILY_PATH,
    DEFAULT_BRAND_REPURCHASE_PATH as DEFAULT_VALIDATE_BRAND_REPURCHASE_PATH,
    DEFAULT_PRODUCT_REPURCHASE_PATH as DEFAULT_VALIDATE_PRODUCT_REPURCHASE_PATH,
    DEFAULT_PURCHASE_REASON_PATH as DEFAULT_VALIDATE_PURCHASE_REASON_PATH,
    DEFAULT_REASON_TRAIT_MAP_PATH as DEFAULT_VALIDATE_REASON_TRAIT_MAP_PATH,
    DEFAULT_CATEGORY_PRICE_PATH as DEFAULT_VALIDATE_CATEGORY_PRICE_PATH,
    DEFAULT_CONTENT_INTEREST_PATH as DEFAULT_VALIDATE_CONTENT_INTEREST_PATH,
    DEFAULT_DIM_PRODUCT_PATH as DEFAULT_VALIDATE_DIM_PRODUCT_PATH,
    DEFAULT_DIM_BRAND_PATH as DEFAULT_VALIDATE_DIM_BRAND_PATH,
    DEFAULT_FUNNEL_DAILY_PATH as DEFAULT_VALIDATE_FUNNEL_DAILY_PATH,
    DEFAULT_INGREDIENT_WEEKLY_PATH as DEFAULT_VALIDATE_INGREDIENT_WEEKLY_PATH,
    DEFAULT_PRODUCT_DAILY_PATH as DEFAULT_VALIDATE_PRODUCT_DAILY_PATH,
    DEFAULT_PURCHASE_FACT_PATH as DEFAULT_VALIDATE_PURCHASE_FACT_PATH,
    DEFAULT_PURCHASE_REASON_FACT_PATH as DEFAULT_VALIDATE_PURCHASE_REASON_FACT_PATH,
    DEFAULT_REVIEW_EVENT_FACT_PATH as DEFAULT_VALIDATE_REVIEW_EVENT_FACT_PATH,
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
    def test_q2_event_intents_match_the_43_event_json_contract(self):
        contract_path = Path(__file__).parents[2] / "contracts" / "event-schema.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        registered = set(contract["properties"]["event_name"]["enum"])
        contracted_intents = {}
        for rule in contract["allOf"]:
            intent = (
                rule.get("then", {})
                .get("properties", {})
                .get("intent", {})
                .get("const")
            )
            events = (
                rule.get("if", {})
                .get("properties", {})
                .get("event_name", {})
                .get("enum", [])
            )
            if intent:
                contracted_intents.update({event_name: intent for event_name in events})

        self.assertEqual(43, len(registered))
        self.assertEqual(registered, set(EVENT_INTENTS))
        self.assertEqual(contracted_intents, EVENT_INTENTS)
        self.assertEqual("session", EVENT_INTENTS["banner_impression"])
        self.assertEqual("interest", EVENT_INTENTS["banner_click"])

    def test_q2_product_scope_includes_banners_and_detail_scoped_events(self):
        self.assertIn("banner_impression", PRODUCT_ID_REQUIRED_EVENTS)
        self.assertIn("banner_click", PRODUCT_ID_REQUIRED_EVENTS)
        self.assertEqual(
            {
                "page_view",
                "section_view",
                "section_dwell",
                "scroll_depth",
                "scroll_pause",
            },
            set(PRODUCT_DETAIL_SCOPED_EVENTS),
        )
        self.assertNotIn("scroll_depth", PRODUCT_ID_REQUIRED_EVENTS)
        self.assertNotIn("scroll_pause", PRODUCT_ID_REQUIRED_EVENTS)

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

    def test_schema_version_contract_has_no_storefront_scope(self):
        self.assertEqual(
            ("0.2.0-draft",),
            SUPPORTED_SCHEMA_VERSIONS,
        )

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
        self.assertEqual(DEFAULT_PURCHASE_FACT_PATH, config.purchase_fact_path)
        self.assertEqual(
            DEFAULT_PURCHASE_REASON_FACT_PATH, config.purchase_reason_fact_path
        )
        self.assertEqual(DEFAULT_REVIEW_EVENT_FACT_PATH, config.review_event_fact_path)
        self.assertEqual(DEFAULT_SECTION_DWELL_PATH, config.section_dwell_path)
        self.assertEqual(DEFAULT_CONTENT_INTEREST_PATH, config.content_interest_path)
        self.assertEqual(DEFAULT_DIM_PRODUCT_PATH, config.dim_product_path)
        self.assertEqual(DEFAULT_DIM_BRAND_PATH, config.dim_brand_path)
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
        self.assertEqual(DEFAULT_BRAND_DAILY_PATH, config.brand_daily_path)
        self.assertEqual(DEFAULT_PRODUCT_REPURCHASE_PATH, config.product_repurchase_path)
        self.assertEqual(DEFAULT_BRAND_REPURCHASE_PATH, config.brand_repurchase_path)
        self.assertEqual(DEFAULT_PURCHASE_REASON_PATH, config.purchase_reason_path)
        self.assertEqual(DEFAULT_VALIDATE_REASON_TRAIT_MAP_PATH, config.reason_trait_map_path)
        self.assertEqual(DEFAULT_REPURCHASE_WINDOW_DAYS, config.repurchase_window_days)
        self.assertEqual(DEFAULT_PRODUCT_INGREDIENT_PATH, config.product_ingredient_path)
        self.assertEqual(DEFAULT_INGREDIENT_VOCAB_PATH, config.ingredient_vocab_path)
        self.assertEqual(DEFAULT_INGREDIENT_WEEKLY_PATH, config.ingredient_weekly_path)
        self.assertEqual(DEFAULT_CATEGORY_PRICE_PATH, config.category_price_path)
        self.assertEqual(DEFAULT_CLEANSING_CATEGORY_WEIGHT, config.cleansing_category_weight)
        self.assertEqual(DEFAULT_PRICE_MIN_SAMPLE_SIZE, config.price_min_sample_size)
        self.assertEqual("frontend/src/types/log.ts", config.behavior_weights_path)

    def test_empty_mart_path_is_rejected(self):
        with self.assertRaises(ValueError):
            BuildMartsConfig(funnel_daily_path=" ")

    def test_invalid_mart_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            BuildMartsConfig(cleansing_category_weight=0)
        with self.assertRaises(ValueError):
            BuildMartsConfig(price_min_sample_size=0)


class ValidatePipelineConfigTest(unittest.TestCase):
    def test_defaults_match_pipeline_outputs(self):
        config = parse_validate_args([])

        self.assertEqual("data/raw_events", config.raw_path)
        self.assertEqual("data/processed/cleaned_events", config.cleaned_path)
        self.assertEqual(
            DEFAULT_VALIDATE_PURCHASE_FACT_PATH, config.purchase_fact_path
        )
        self.assertEqual(
            DEFAULT_VALIDATE_PURCHASE_REASON_FACT_PATH,
            config.purchase_reason_fact_path,
        )
        self.assertEqual(
            DEFAULT_VALIDATE_REVIEW_EVENT_FACT_PATH, config.review_event_fact_path
        )
        self.assertEqual(
            DEFAULT_VALIDATE_SECTION_DWELL_PATH, config.section_dwell_path
        )
        self.assertEqual(
            DEFAULT_VALIDATE_CONTENT_INTEREST_PATH, config.content_interest_path
        )
        self.assertEqual(DEFAULT_VALIDATE_DIM_PRODUCT_PATH, config.dim_product_path)
        self.assertEqual(DEFAULT_VALIDATE_DIM_BRAND_PATH, config.dim_brand_path)
        self.assertEqual(DEFAULT_VALIDATE_PRODUCT_DAILY_PATH, config.product_daily_path)
        self.assertEqual(DEFAULT_VALIDATE_FUNNEL_DAILY_PATH, config.funnel_daily_path)
        self.assertEqual(DEFAULT_VALIDATE_BRAND_DAILY_PATH, config.brand_daily_path)
        self.assertEqual(DEFAULT_VALIDATE_PRODUCT_REPURCHASE_PATH, config.product_repurchase_path)
        self.assertEqual(DEFAULT_VALIDATE_BRAND_REPURCHASE_PATH, config.brand_repurchase_path)
        self.assertEqual(DEFAULT_VALIDATE_PURCHASE_REASON_PATH, config.purchase_reason_path)
        self.assertEqual(DEFAULT_REASON_TRAIT_MAP_PATH, config.reason_trait_map_path)
        self.assertEqual(
            DEFAULT_VALIDATE_INGREDIENT_WEEKLY_PATH, config.ingredient_weekly_path
        )
        self.assertEqual(DEFAULT_VALIDATE_CATEGORY_PRICE_PATH, config.category_price_path)
        self.assertFalse(config.require_events)

    def test_empty_report_path_is_rejected(self):
        with self.assertRaises(ValueError):
            ValidatePipelineConfig(report_path=" ")


class PaymentEnumContractTest(unittest.TestCase):
    """결제 enum 은 계약·Mart·검증 세 곳에 복사돼 있다. 어긋나면 조용히 갈린다."""

    @classmethod
    def setUpClass(cls):
        contract_path = Path(__file__).parents[2] / "contracts" / "event-schema.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        cls.purchase_properties = next(
            rule["then"]["properties"]["properties"]["properties"]
            for rule in contract["allOf"]
            if rule.get("if", {})
            .get("properties", {})
            .get("event_name", {})
            .get("const")
            == "purchase"
        )

    def test_payment_method_enum_matches_the_json_contract(self):
        contracted = self.purchase_properties["payment_method"]["enum"]

        self.assertEqual(set(contracted), set(MART_PAYMENT_METHODS))
        self.assertEqual(set(contracted), set(VALIDATE_PAYMENT_METHODS))

    def test_order_channel_enum_matches_the_json_contract(self):
        contracted = self.purchase_properties["order_channel"]["enum"]

        self.assertEqual(set(contracted), set(MART_ORDER_CHANNELS))
        self.assertEqual(set(contracted), set(VALIDATE_ORDER_CHANNELS))

    def test_optional_payment_keys_are_not_required(self):
        """키 생략이 계약이다. 필수로 바뀌면 confirm 을 건너뛴 시연 주문이 전부 거절된다."""
        required = set(
            next(
                rule["then"]["properties"]["properties"]["required"]
                for rule in json.loads(
                    (
                        Path(__file__).parents[2] / "contracts" / "event-schema.json"
                    ).read_text(encoding="utf-8")
                )["allOf"]
                if rule.get("if", {})
                .get("properties", {})
                .get("event_name", {})
                .get("const")
                == "purchase"
            )
        )

        self.assertEqual(
            {"order_id", "items", "payment_method", "paid_value", "order_channel"},
            required,
        )
        for optional in ("pg_provider", "payment_id", "paid_at"):
            with self.subTest(key=optional):
                self.assertNotIn(optional, required)
                self.assertIn(optional, self.purchase_properties)


if __name__ == "__main__":
    unittest.main()
