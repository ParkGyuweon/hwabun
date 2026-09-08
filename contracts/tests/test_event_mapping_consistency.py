from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "event-schema.json"
CASES_PATH = ROOT / "contracts" / "samples" / "event-mapping-cases.json"
BASE_EVENT_PATH = ROOT / "contracts" / "samples" / "raw-event.user.valid.json"


class EventMappingConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.base_event = json.loads(BASE_EVENT_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def event_for(self, case: dict[str, str]) -> dict[str, object]:
        event = copy.deepcopy(self.base_event)
        event["event_name"] = case["event_name"]
        event["intent"] = case["intent"]
        event["page_type"] = "product_detail"
        event["product_id"] = (
            "P342" if case["product_id_policy"] == "required" else None
        )
        if case["product_id_policy"] == "conditional":
            event["page_type"] = "product_list"
        if case["event_name"] in {"banner_impression", "banner_click"}:
            event["properties"] = {
                "banner_type": "concern",
                "banner_value": "Pores",
                "banner_slot": 1,
                "trait_source": "session",
            }
        return event

    def error_messages(self, event: dict[str, object]) -> list[str]:
        return [error.message for error in self.validator.iter_errors(event)]

    def test_fixture_has_exactly_one_case_for_every_schema_event(self) -> None:
        schema_events = self.schema["properties"]["event_name"]["enum"]
        fixture_events = [case["event_name"] for case in self.cases]

        self.assertEqual(41, len(fixture_events))
        self.assertEqual(len(fixture_events), len(set(fixture_events)))
        self.assertEqual(set(schema_events), set(fixture_events))

    def test_fixture_shape_and_policy_values(self) -> None:
        for case in self.cases:
            with self.subTest(event_name=case["event_name"]):
                self.assertEqual(
                    {"event_name", "intent", "product_id_policy", "producer"},
                    set(case),
                )
                self.assertIn(
                    case["product_id_policy"],
                    {"required", "nullable", "conditional"},
                )
                self.assertIsInstance(case["producer"], str)
                self.assertTrue(case["producer"])

    def test_all_registered_event_and_intent_pairs_are_valid(self) -> None:
        for case in self.cases:
            with self.subTest(event_name=case["event_name"]):
                self.assertEqual([], self.error_messages(self.event_for(case)))

    def test_every_registered_event_rejects_a_wrong_intent(self) -> None:
        intents = self.schema["properties"]["intent"]["enum"]
        for case in self.cases:
            event = self.event_for(case)
            event["intent"] = next(
                intent for intent in intents if intent != case["intent"]
            )
            with self.subTest(event_name=case["event_name"]):
                errors = list(self.validator.iter_errors(event))
                self.assertTrue(
                    any(error.validator == "const" for error in errors),
                    [error.message for error in errors],
                )

    def test_unregistered_event_is_rejected(self) -> None:
        event = self.event_for(self.cases[0])
        event["event_name"] = "unregistered_event"

        errors = list(self.validator.iter_errors(event))

        self.assertTrue(any(error.validator == "enum" for error in errors))

    def test_required_product_events_reject_null_and_blank_product_id(self) -> None:
        for case in self.cases:
            if case["product_id_policy"] != "required":
                continue
            for invalid_product_id in (None, ""):
                event = self.event_for(case)
                event["product_id"] = invalid_product_id
                with self.subTest(
                    event_name=case["event_name"],
                    product_id=invalid_product_id,
                ):
                    self.assertNotEqual([], self.error_messages(event))

    def test_nullable_platform_events_allow_null_but_reject_blank_product_id(self) -> None:
        for case in self.cases:
            if case["product_id_policy"] != "nullable":
                continue
            with self.subTest(event_name=case["event_name"]):
                self.assertEqual([], self.error_messages(self.event_for(case)))
                blank_product_event = self.event_for(case)
                blank_product_event["product_id"] = ""
                self.assertNotEqual([], self.error_messages(blank_product_event))

    def test_conditional_product_id_policy_depends_on_page_type(self) -> None:
        conditional_cases = [
            case
            for case in self.cases
            if case["product_id_policy"] == "conditional"
        ]

        self.assertEqual(
            {"page_view", "section_view", "section_dwell"},
            {case["event_name"] for case in conditional_cases},
        )
        for case in conditional_cases:
            cases = (
                ("product_list", None, True),
                ("product_list", "", False),
                ("product_detail", None, False),
                ("product_detail", "", False),
                ("product_detail", "P342", True),
            )
            for page_type, product_id, should_be_valid in cases:
                event = self.event_for(case)
                event["page_type"] = page_type
                event["product_id"] = product_id
                with self.subTest(
                    event_name=case["event_name"],
                    page_type=page_type,
                    product_id=product_id,
                ):
                    errors = self.error_messages(event)
                    if should_be_valid:
                        self.assertEqual([], errors)
                    else:
                        self.assertNotEqual([], errors)

    def test_known_contract_pairs_with_cross_component_drift(self) -> None:
        mapping = {case["event_name"]: case["intent"] for case in self.cases}

        self.assertEqual("session", mapping["navigation_click"])
        self.assertEqual("conversion", mapping["begin_checkout"])
        self.assertEqual("conversion", mapping["purchase"])
        self.assertEqual("validation", mapping["purchase_reason_select"])


if __name__ == "__main__":
    unittest.main()
