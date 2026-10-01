import json
import unittest
from pathlib import Path

from contracts.coverage_report import (
    check_properties,
    load_events,
    parse_property_contract,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "event-properties-schema.md"
EVENT_SCHEMA_PATH = ROOT / "contracts" / "event-schema.json"
IMPRESSION_EVENTS = {
    "product_impression",
    "recommendation_impression",
    "banner_impression",
}
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

    def test_contract_parser_reads_impression_origin_enum_and_type(self) -> None:
        self.assertEqual(
            {
                "observed",
                "implied_by_click",
                "implied_by_quick_look",
                "implied_by_direct_view",
            },
            self.enums["impression_origin"],
        )
        for event_name in (
            "banner_impression",
            "product_impression",
            "recommendation_impression",
        ):
            # 선택 property라 required 목록(`all`)에는 없고, 값이 실렸을 때
            # 타입·enum을 강제하도록 `types`에만 있어야 한다.
            self.assertNotIn("impression_origin", self.spec[event_name]["all"])
            self.assertEqual(
                "string",
                self.spec[event_name]["types"]["impression_origin"],
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

    def _product_impression(self, **overrides):
        props = {
            "list_id": "search:all",
            "position": 1,
            "hold_ms": 1200,
            "visible_ratio": 0.8,
            "impression_origin": "observed",
        }
        props.update(overrides)
        return {"event_name": "product_impression", "properties": props}

    def test_impression_origin_accepts_contract_values(self) -> None:
        events = [
            self._product_impression(impression_origin="observed"),
            self._product_impression(impression_origin="implied_by_click"),
            # Quick Look 열기는 클릭이 아니라 별도 값이다 (프론트 합의 2026-09-18)
            self._product_impression(impression_origin="implied_by_quick_look"),
        ]

        result = check_properties(events, self.spec, self.enums)

        self.assertEqual([], result["missing"])
        self.assertEqual([], result["invalid_types"])
        self.assertEqual([], result["invalid_enums"])

    def test_impression_origin_enum_matches_event_schema_json(self) -> None:
        """마크다운 계약과 실행 Envelope 계약이 어긋나면 Q5 가 잘못된 목록을 강제한다.

        Q5 는 `event-schema.json` 에서 허용값을 읽고, 사람은 §3.12-1 을 읽는다.
        둘이 갈라지면 문서대로 보낸 값이 런타임에서 거절된다.
        """
        with open(EVENT_SCHEMA_PATH, encoding="utf-8") as handle:
            schema = json.load(handle)

        declared = None
        for branch in schema.get("allOf", []):
            names = branch.get("if", {}).get("properties", {}).get("event_name", {}).get("enum")
            if set(names or ()) != IMPRESSION_EVENTS:
                continue
            declared = (
                branch.get("then", {})
                .get("properties", {}).get("properties", {})
                .get("properties", {}).get("impression_origin", {})
                .get("enum")
            )
            break

        self.assertIsNotNone(
            declared,
            "event-schema.json 에 노출 3종의 impression_origin enum 분기가 없습니다.",
        )
        self.assertEqual(self.enums["impression_origin"], set(declared))

    def test_impression_origin_is_optional(self) -> None:
        """값이 없는 과거 로그는 위반이 아니다 (없으면 `observed`로 간주)."""
        event = self._product_impression()
        del event["properties"]["impression_origin"]

        result = check_properties([event], self.spec, self.enums)

        self.assertNotIn(
            (("product_impression", "impression_origin"), 1),
            result["missing"],
        )
        self.assertEqual([], result["missing"])

    def test_impression_origin_rejects_unknown_value(self) -> None:
        event = self._product_impression(impression_origin="synthetic")

        result = check_properties([event], self.spec, self.enums)

        self.assertIn(
            (("product_impression", "impression_origin", "synthetic"), 1),
            result["invalid_enums"],
        )

    def test_impression_origin_rejects_non_string_value(self) -> None:
        event = self._product_impression(impression_origin=True)

        result = check_properties([event], self.spec, self.enums)

        self.assertIn(
            (("product_impression", "impression_origin", "string", "boolean"), 1),
            result["invalid_types"],
        )

    def _reason_event(self, reasons, **extra):
        props = {"order_id": "ORD-1", "reasons": reasons}
        props.update(extra)
        return {"event_name": "purchase_reason_select", "properties": props}

    def test_array_enum_accepts_contract_values(self) -> None:
        """reasons 는 계약 최초의 배열 원소 enum 이다.

        enum 검사가 스칼라 문자열만 가정하면 배열이 통째로 타입 오류가 된다.
        """
        result = check_properties(
            [self._reason_event(["ingredient", "review_same_skin"])], self.spec, self.enums
        )

        self.assertEqual(result["invalid_types"], [])
        self.assertEqual(result["invalid_enums"], [])

    def test_array_enum_rejects_unknown_element(self) -> None:
        result = check_properties([self._reason_event(["ingredient", "gift"])],
                                  self.spec, self.enums)

        self.assertIn(
            (("purchase_reason_select", "reasons", "gift"), 1),
            result["invalid_enums"],
        )

    def test_array_enum_rejects_non_array(self) -> None:
        result = check_properties([self._reason_event("ingredient")], self.spec, self.enums)

        self.assertIn(
            (("purchase_reason_select", "reasons", "string[]", "string"), 1),
            result["invalid_types"],
        )

    def test_skipped_survey_sends_empty_reasons(self) -> None:
        """건너뛰기는 위반이 아니다.

        건너뛴 것과 응답이 유실된 것을 구분해야 응답률을 셀 수 있어, reasons 키는
        항상 존재하고 값만 빈 배열이다 (계약 §5).
        """
        result = check_properties([self._reason_event([], skipped=True)],
                                  self.spec, self.enums)

        self.assertEqual(result["invalid_types"], [])
        self.assertEqual(result["invalid_enums"], [])
        self.assertEqual(result["missing"], [])


if __name__ == "__main__":
    unittest.main()
