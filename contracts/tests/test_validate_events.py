from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from contracts.validate_events import (
    ValidatorInputError,
    main,
    validate_event_files,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "event-schema.json"
USER_SAMPLE_PATH = ROOT / "contracts" / "samples" / "raw-event.user.valid.json"
SYNTHETIC_PC_SAMPLE_PATH = (
    ROOT / "contracts" / "samples" / "raw-event.synthetic.valid.json"
)
SYNTHETIC_PA_SAMPLE_PATH = (
    ROOT / "contracts" / "samples" / "raw-event.synthetic.agent-llm.valid.json"
)


class EventValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user_event = json.loads(USER_SAMPLE_PATH.read_text(encoding="utf-8"))

    def validate_values(self, values: object, **kwargs: object):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "events.json"
            input_path.write_text(
                json.dumps(values, ensure_ascii=False),
                encoding="utf-8",
            )
            return validate_event_files([input_path], SCHEMA_PATH, **kwargs)

    def assert_has_error(self, errors: list[str], marker: str) -> None:
        self.assertTrue(
            any(marker in error for error in errors),
            f"Expected {marker!r} in errors: {errors}",
        )

    def test_valid_user_and_synthetic_samples(self) -> None:
        result = validate_event_files(
            [USER_SAMPLE_PATH, SYNTHETIC_PC_SAMPLE_PATH, SYNTHETIC_PA_SAMPLE_PATH],
            SCHEMA_PATH,
        )

        self.assertEqual(3, result.event_count)
        self.assertEqual([], result.errors)

    def test_missing_required_field(self) -> None:
        event = copy.deepcopy(self.user_event)
        del event["session_id"]

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[required]")
        self.assert_has_error(result.errors, "session_id")

    def test_field_type_error(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["sequence_no"] = "12"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[type] $.sequence_no")

    def test_invalid_timestamp_format(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["occurred_at"] = "2026-08-31"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[format] $.occurred_at")

    def test_unregistered_event_name(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["event_name"] = "search"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[enum] $.event_name")

    def test_schema_version_must_be_known(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["schema_version"] = "1.0.0-draft"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[enum] $.schema_version")

    def test_current_schema_does_not_accept_tenant_id(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["tenant_id"] = "legacy-storefront"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[additionalProperties] $")

    def test_current_schema_does_not_accept_business_id(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["business_id"] = "legacy-business"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[additionalProperties] $")

    def test_withdrawn_tenant_schema_version_is_rejected(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["schema_version"] = "0.3.0-draft"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[enum] $.schema_version")

    def test_product_detail_page_requires_product_id(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "event_name": "page_view",
                "intent": "session",
                "page_type": "product_detail",
                "product_id": None,
                "properties": {"route": "/products/P342"},
            }
        )

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[type] $.product_id")

    def test_platform_page_can_have_no_product_owner(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "event_name": "page_view",
                "intent": "session",
                "page_type": "product_list",
                "product_id": None,
                "properties": {"route": "/products"},
            }
        )

        result = self.validate_values(event)

        self.assertEqual(result.errors, [])

    def test_scroll_events_are_product_scoped_only_on_product_detail(self) -> None:
        for event_name, intent in (
            ("scroll_depth", "exposure"),
            ("scroll_pause", "interest"),
        ):
            for page_type, product_id, should_be_valid in (
                ("product_list", None, True),
                ("product_list", "", False),
                ("product_detail", None, False),
                ("product_detail", "P342", True),
            ):
                event = copy.deepcopy(self.user_event)
                event.update(
                    {
                        "event_name": event_name,
                        "intent": intent,
                        "page_type": page_type,
                        "product_id": product_id,
                    }
                )

                result = self.validate_values(event)

                with self.subTest(
                    event_name=event_name,
                    page_type=page_type,
                    product_id=product_id,
                ):
                    if should_be_valid:
                        self.assertEqual([], result.errors)
                    else:
                        self.assert_has_error(result.errors, "$.product_id")

    def test_product_target_event_requires_product_id(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["product_id"] = None

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[type] $.product_id")

    def test_event_name_and_intent_must_match(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["intent"] = "interest"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[const] $.intent")

    def test_navigation_click_with_session_intent_is_allowed(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "event_name": "navigation_click",
                "intent": "session",
                "product_id": None,
                "properties": {
                    "target": "home",
                    "entry_source": "breadcrumb",
                },
            }
        )

        result = self.validate_values(event)

        self.assertEqual([], result.errors)

    def test_navigation_click_requires_session_intent(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "event_name": "navigation_click",
                "intent": "comparison",
                "product_id": None,
                "properties": {
                    "target": "home",
                    "entry_source": "breadcrumb",
                },
            }
        )

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[const] $.intent")

    def banner_event(self, event_name: str = "banner_impression") -> dict[str, object]:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "event_name": event_name,
                "intent": "session" if event_name == "banner_impression" else "interest",
                "product_id": "P342",
                "properties": {
                    "banner_type": "concern",
                    "banner_value": "Pores",
                    "banner_slot": 1,
                    "trait_source": "explore",
                },
            }
        )
        return event

    def test_banner_contract_accepts_impression_click_and_new_brand_null(self) -> None:
        click = self.banner_event("banner_click")
        new_brand = self.banner_event()
        new_brand["event_id"] = "evt-banner-new-brand"
        new_brand["properties"] = {
            "banner_type": "new_brand",
            "banner_value": None,
            "banner_slot": 2,
            "trait_source": "coldstart",
        }

        result = self.validate_values([self.banner_event(), click, new_brand])

        self.assertEqual([], result.errors)

    def test_banner_contract_rejects_slot_alias_and_invalid_values(self) -> None:
        invalid_events = []
        mutations = (
            {"banner_slot": None},
            {"banner_type": "unknown"},
            {"trait_source": "random"},
            {"banner_type": "new_brand", "banner_value": "must-be-null"},
            {"banner_type": "concern", "banner_value": None},
            {"slot": 1},
        )
        for index, mutation in enumerate(mutations):
            event = self.banner_event()
            event["event_id"] = f"evt-banner-invalid-{index}"
            properties = event["properties"]
            assert isinstance(properties, dict)
            if mutation == {"banner_slot": None}:
                properties.pop("banner_slot")
            else:
                properties.update(mutation)
            invalid_events.append(event)

        result = self.validate_values(invalid_events)

        self.assertEqual(len(mutations), len(result.errors))

    def test_account_id_accepts_string_or_null_but_not_other_types(self) -> None:
        logged_in = copy.deepcopy(self.user_event)
        logged_in["account_id"] = "acc-1"
        anonymous = copy.deepcopy(self.user_event)
        anonymous["account_id"] = None

        self.assertEqual([], self.validate_values([logged_in, anonymous]).errors)

        wrong_type = copy.deepcopy(self.user_event)
        wrong_type["account_id"] = 123
        missing = copy.deepcopy(self.user_event)
        missing.pop("account_id")

        self.assert_has_error(
            self.validate_values([wrong_type]).errors, "[type] $.account_id"
        )
        self.assert_has_error(
            self.validate_values([missing]).errors, "[required] $"
        )

    def test_login_event_requires_session_intent(self) -> None:
        login = copy.deepcopy(self.user_event)
        login.update({"event_name": "login", "intent": "session", "product_id": None})
        login["properties"] = {}

        self.assertEqual([], self.validate_values([login]).errors)

        wrong_intent = copy.deepcopy(login)
        wrong_intent["intent"] = "conversion"

        self.assert_has_error(
            self.validate_values([wrong_intent]).errors, "[const] $.intent"
        )

    def test_actor_type_and_source_must_match(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["source"] = "simulator"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[const] $.source")

    def test_unknown_top_level_field_is_rejected(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["unknown_field"] = "unexpected"

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[additionalProperties] $")

    def test_duplicates_are_warnings_by_default_for_raw(self) -> None:
        result = self.validate_values([self.user_event, self.user_event])

        self.assertEqual([], result.errors)
        self.assert_has_error(result.warnings, "[duplicate_event_id] $.event_id")

    def test_duplicate_event_id_can_be_ignored(self) -> None:
        result = self.validate_values(
            [self.user_event, self.user_event],
            duplicate_policy="ignore",
        )

        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)

    def test_duplicate_event_id_can_be_warning(self) -> None:
        result = self.validate_values(
            [self.user_event, self.user_event],
            duplicate_policy="warn",
        )

        self.assertEqual([], result.errors)
        self.assert_has_error(result.warnings, "[duplicate_event_id] $.event_id")

    def test_duplicate_event_id_can_be_error(self) -> None:
        result = self.validate_values(
            [self.user_event, self.user_event],
            duplicate_policy="error",
        )

        self.assert_has_error(result.errors, "[duplicate_event_id] $.event_id")

    def test_synthetic_runtime_metadata_is_required(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "actor_type": "synthetic",
                "source": "simulator",
                "persona_id": "PC00001",
                "properties": {
                    "scenario_id": "normal_day",
                    "simulation_run_id": "run_20260831T051100Z",
                },
            }
        )

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "generator_type")

    def test_agent_llm_generator_type_is_allowed(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "actor_type": "synthetic",
                "source": "simulator",
                "persona_id": "PA00001",
                "properties": {
                    "scenario_id": "normal_day",
                    "simulation_run_id": "run_20260831T051100Z",
                    "generator_type": "agent_llm",
                },
            }
        )

        result = self.validate_values(event)

        self.assertEqual([], result.errors)

    def test_legacy_agent_realtime_generator_type_is_rejected(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "actor_type": "synthetic",
                "source": "simulator",
                "persona_id": "PA00001",
                "properties": {
                    "scenario_id": "normal_day",
                    "simulation_run_id": "run_20260831T051100Z",
                    "generator_type": "agent_realtime",
                },
            }
        )

        result = self.validate_values(event)

        self.assert_has_error(result.errors, "[enum] $.properties.generator_type")

    def test_jsonl_input(self) -> None:
        second_event = copy.deepcopy(self.user_event)
        second_event["event_id"] = "evt-user-0002"
        second_event["event_index"] = 1

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "events.jsonl"
            input_path.write_text(
                "\n".join(
                    json.dumps(event) for event in [self.user_event, second_event]
                ),
                encoding="utf-8",
            )
            result = validate_event_files([input_path], SCHEMA_PATH)

        self.assertEqual(2, result.event_count)
        self.assertEqual([], result.errors)

    def test_utf8_bom_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "event.json"
            input_path.write_text(
                json.dumps(self.user_event),
                encoding="utf-8-sig",
            )
            result = validate_event_files([input_path], SCHEMA_PATH)

        self.assertEqual(1, result.event_count)
        self.assertEqual([], result.errors)

    def test_empty_jsonl_is_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "empty.jsonl"
            input_path.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValidatorInputError, "no Events"):
                validate_event_files([input_path], SCHEMA_PATH)

    def test_non_utf8_input_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "cp949.json"
            input_path.write_bytes('{"메시지":"테스트"}'.encode("cp949"))
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main([str(input_path)])

        self.assertEqual(2, exit_code)
        self.assertIn("input must be UTF-8", stderr.getvalue())

    def test_jsonl_parse_error_includes_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "broken.jsonl"
            input_path.write_text(
                json.dumps(self.user_event) + "\n{not-json\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValidatorInputError, r"broken\.jsonl:2:"):
                validate_event_files([input_path], SCHEMA_PATH)

    def test_api_batch_body_is_unwrapped(self) -> None:
        second_event = copy.deepcopy(self.user_event)
        second_event["event_id"] = "evt-user-0002"
        batch = {
            "schema_version": "0.2.0-draft",
            "events": [self.user_event, second_event],
        }

        result = self.validate_values(batch)

        self.assertEqual(2, result.event_count)
        self.assertEqual([], result.errors)

    def test_api_batch_schema_version_is_required(self) -> None:
        result = self.validate_values({"events": [self.user_event]})

        self.assert_has_error(result.errors, "[required] $.schema_version")

    def test_api_batch_schema_version_must_be_a_string(self) -> None:
        result = self.validate_values(
            {"schema_version": 2, "events": [self.user_event]}
        )

        self.assert_has_error(result.errors, "[type] $.schema_version")

    def test_seeded_marker_must_be_a_boolean_on_synthetic_events(self) -> None:
        """시드 표식은 boolean 이다. 문자열 "true" 는 걸러야 한다.

        Spark 는 properties.seeded 로 is_seed 를 파생하는데, 타입이 흔들리면
        판정이 조용히 달라진다 (event-properties-schema.md §3.14).
        """
        synthetic = json.loads(SYNTHETIC_PC_SAMPLE_PATH.read_text(encoding="utf-8"))

        valid = copy.deepcopy(synthetic)
        valid["properties"]["seeded"] = True
        self.assertEqual([], self.validate_values([valid]).errors)

        for bad_value in ("true", 1):
            with self.subTest(value=bad_value):
                event = copy.deepcopy(synthetic)
                event["properties"]["seeded"] = bad_value
                result = self.validate_values([event])
                self.assert_has_error(result.errors, "$.properties.seeded")

    def test_seeded_marker_is_rejected_on_real_user_events(self) -> None:
        """주입 표식이 실사용자 행동에 섞이면 안 된다 (event-properties-schema.md §7-8)."""
        event = copy.deepcopy(self.user_event)
        event["properties"]["seeded"] = True

        result = self.validate_values([event])

        self.assert_has_error(result.errors, "$.properties")

    def test_withdrawn_api_batch_schema_version_is_rejected(self) -> None:
        result = self.validate_values(
            {"schema_version": "0.3.0-draft", "events": [self.user_event]}
        )

        self.assert_has_error(result.errors, "[enum] $.schema_version")
        self.assert_has_error(result.errors, "[schema_version_mismatch]")

    def test_event_schema_version_must_match_api_batch(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["schema_version"] = "0.3.0-draft"

        result = self.validate_values(
            {"schema_version": "0.2.0-draft", "events": [event]}
        )

        self.assert_has_error(result.errors, "[schema_version_mismatch]")
        self.assert_has_error(result.errors, "[enum] $.schema_version")

    def test_mixed_event_schema_versions_in_api_batch_are_rejected(self) -> None:
        second_event = copy.deepcopy(self.user_event)
        second_event["event_id"] = "evt-user-0002"
        second_event["schema_version"] = "0.3.0-draft"

        result = self.validate_values(
            {
                "schema_version": "0.2.0-draft",
                "events": [self.user_event, second_event],
            }
        )

        self.assert_has_error(result.errors, ".events[1]: [schema_version_mismatch]")

    def test_duplicate_input_path_is_skipped_with_warning(self) -> None:
        result = validate_event_files(
            [USER_SAMPLE_PATH, USER_SAMPLE_PATH],
            SCHEMA_PATH,
        )

        self.assertEqual(1, result.event_count)
        self.assert_has_error(result.warnings, "[duplicate_input_path]")

    def test_max_errors_stops_validation_early(self) -> None:
        events = []
        for index in range(5):
            event = copy.deepcopy(self.user_event)
            event["event_id"] = f"invalid-{index}"
            event["schema_version"] = "invalid"
            events.append(event)

        result = self.validate_values(events, max_errors=2)

        self.assertEqual(2, len(result.errors))
        self.assertTrue(result.stopped_early)
        self.assertLess(result.event_count, len(events))

    def test_cli_returns_zero_for_valid_events(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    str(USER_SAMPLE_PATH),
                    str(SYNTHETIC_PC_SAMPLE_PATH),
                    str(SYNTHETIC_PA_SAMPLE_PATH),
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertIn("PASSED: 3 event(s)", stdout.getvalue())

    def test_cli_returns_one_for_validation_errors(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["schema_version"] = "invalid"

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "invalid.json"
            input_path.write_text(json.dumps(event), encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main([str(input_path)])

        self.assertEqual(1, exit_code)
        self.assertIn("FAILED: 1 event(s) checked", stderr.getvalue())

    def test_cli_returns_two_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "broken.json"
            input_path.write_text("{not-json", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main([str(input_path)])

        self.assertEqual(2, exit_code)
        self.assertIn("Validator setup/input error", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
