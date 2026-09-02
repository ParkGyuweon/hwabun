import unittest
from pathlib import Path

from contracts.coverage_report import (
    check_properties,
    load_events,
    parse_property_contract,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "event-properties-schema.md"
VALID_SAMPLE_PATH = ROOT / "contracts" / "samples" / "event-properties.valid.json"
INVALID_SAMPLE_PATH = ROOT / "contracts" / "samples" / "event-properties.invalid.json"


class PropertyContractCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec, cls.enums, source = parse_property_contract(CONTRACT_PATH)
        if source is None:
            raise AssertionError("Event Properties 계약을 읽지 못했습니다.")

    def test_contract_parser_reads_current_frontend_enum_values(self) -> None:
        self.assertIn("breadcrumb", self.enums["entry_source"])
        self.assertIn("cart_item", self.enums["content_kind"])
        self.assertEqual(
            {"backdrop", "escape", "close_button", "open_detail"},
            self.enums["quick_look_close.close_reason"],
        )

    def test_valid_sample_has_no_property_violations(self) -> None:
        result = check_properties(load_events(VALID_SAMPLE_PATH), self.spec, self.enums)

        self.assertEqual([], result["missing"])
        self.assertEqual([], result["invalid_types"])
        self.assertEqual([], result["invalid_enums"])

    def test_invalid_sample_reports_missing_type_and_enum_violations(self) -> None:
        result = check_properties(load_events(INVALID_SAMPLE_PATH), self.spec, self.enums)

        self.assertIn(
            (("quick_look_close", "wishlisted"), 1),
            result["missing"],
        )
        self.assertIn(
            (("navigation_click", "target", "string", "integer"), 1),
            result["invalid_types"],
        )
        self.assertIn(
            (("quick_look_close", "dwell_ms", "integer", "string"), 1),
            result["invalid_types"],
        )
        self.assertIn(
            (("navigation_click", "entry_source", "footer_link"), 1),
            result["invalid_enums"],
        )
        self.assertIn(
            (("quick_look_close", "close_reason", "esc"), 1),
            result["invalid_enums"],
        )

    def test_array_property_rejects_comma_separated_string(self) -> None:
        event = {
            "event_name": "scroll_pause",
            "properties": {
                "depth_percent": 50,
                "direction": "down",
                "distance_px": 300,
                "duration_ms": 800,
                "visible_content_kinds": "price,cta",
            },
        }

        result = check_properties([event], self.spec, self.enums)

        self.assertIn(
            (("scroll_pause", "visible_content_kinds", "string[]", "string"), 1),
            result["invalid_types"],
        )


if __name__ == "__main__":
    unittest.main()
