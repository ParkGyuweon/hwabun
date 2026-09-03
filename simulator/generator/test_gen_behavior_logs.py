import unittest
from datetime import datetime, timezone

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

if np is not None:
    from simulator.generator.gen_behavior_logs import (
        DEFAULT_GENERATOR_TYPE,
        DEFAULT_SCENARIO_ID,
        Emitter,
        SimulationContext,
        default_simulation_run_id,
        seed_session_id,
        selectable_variants,
        validate_property_contract,
    )


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class SyntheticEventMetadataTest(unittest.TestCase):
    def setUp(self):
        self.context = SimulationContext(
            scenario_id=DEFAULT_SCENARIO_ID,
            simulation_run_id="run_test_001",
            generator_type=DEFAULT_GENERATOR_TYPE,
        )

    def test_default_run_id_uses_utc_timestamp(self):
        run_id = default_simulation_run_id(
            datetime(2026, 8, 31, 1, 2, 3, tzinfo=timezone.utc)
        )

        self.assertEqual("run_20260831T010203Z", run_id)

    def test_emitter_adds_required_runtime_metadata(self):
        events = []
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
        )

        emitter.emit("session_start")

        self.assertEqual(
            {
                "scenario_id": "normal_day",
                "simulation_run_id": "run_test_001",
                "generator_type": "python_batch",
            },
            {
                key: events[0]["properties"][key]
                for key in ("scenario_id", "simulation_run_id", "generator_type")
            },
        )
        self.assertFalse(events[0]["properties"].get("seeded", False))
        self.assertTrue(events[0]["session_id"].startswith("run_test_001:"))

    def test_seed_emitter_marks_every_event_and_scopes_session(self):
        events = []
        session_id = seed_session_id(self.context, "PC00001", "P00001")
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
            session_id=session_id,
            is_seed=True,
        )

        emitter.emit("add_to_cart", "P00001")

        self.assertEqual("seed:run_test_001:PC00001:P00001", events[0]["session_id"])
        self.assertTrue(events[0]["properties"]["seeded"])

    def test_emitter_omits_absent_optional_properties(self):
        events = []
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
        )

        emitter.emit(
            "section_view",
            "P00001",
            section_id="ingredients",
            content_kind=None,
            content_ref=None,
        )

        self.assertEqual("ingredients", events[0]["properties"]["section_id"])
        self.assertNotIn("content_kind", events[0]["properties"])
        self.assertNotIn("content_ref", events[0]["properties"])

    def test_selectable_variants_excludes_initial_frontend_selection(self):
        product = {
            "variants": [
                {"sku_id": "SKU-1", "label": "30ml"},
                {"sku_id": "SKU-2", "label": "50ml"},
                {"sku_id": "SKU-3", "label": "100ml"},
            ]
        }

        self.assertEqual(product["variants"][1:], selectable_variants(product))
        self.assertEqual([], selectable_variants({}))

    def test_property_contract_accepts_valid_event(self):
        events = [
            {
                "event_name": "quick_look_close",
                "properties": {
                    "close_reason": "escape",
                    "dwell_ms": 1200,
                    "variants_viewed": 1,
                    "added_to_cart": False,
                    "wishlisted": False,
                },
            }
        ]

        result = validate_property_contract(events)

        self.assertEqual(1, result["checked"])

    def test_property_contract_rejects_invalid_enum(self):
        events = [
            {
                "event_name": "quick_look_close",
                "properties": {
                    "close_reason": "esc",
                    "dwell_ms": 1200,
                    "variants_viewed": 1,
                    "added_to_cart": False,
                    "wishlisted": False,
                },
            }
        ]

        with self.assertRaisesRegex(ValueError, "Event Properties"):
            validate_property_contract(events)


if __name__ == "__main__":
    unittest.main()
