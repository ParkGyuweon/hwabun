from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from contracts.validate_events import validate_event_files


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "event-schema.json"
USER_SAMPLE_PATH = ROOT / "contracts" / "samples" / "raw-event.user.valid.json"
SYNTHETIC_SAMPLE_PATH = (
    ROOT / "contracts" / "samples" / "raw-event.synthetic.valid.json"
)


class EventValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user_event = json.loads(USER_SAMPLE_PATH.read_text(encoding="utf-8"))

    def validate_values(self, values: object) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "events.json"
            input_path.write_text(
                json.dumps(values, ensure_ascii=False),
                encoding="utf-8",
            )
            return validate_event_files([input_path], SCHEMA_PATH)

    def assert_has_error(self, errors: list[str], marker: str) -> None:
        self.assertTrue(
            any(marker in error for error in errors),
            f"Expected {marker!r} in errors: {errors}",
        )

    def test_valid_user_and_synthetic_samples(self) -> None:
        count, errors = validate_event_files(
            [USER_SAMPLE_PATH, SYNTHETIC_SAMPLE_PATH],
            SCHEMA_PATH,
        )

        self.assertEqual(2, count)
        self.assertEqual([], errors)

    def test_missing_required_field(self) -> None:
        event = copy.deepcopy(self.user_event)
        del event["session_id"]

        _, errors = self.validate_values(event)

        self.assert_has_error(errors, "[required]")

    def test_field_type_error(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["sequence_no"] = "12"

        _, errors = self.validate_values(event)

        self.assert_has_error(errors, "[type] $.sequence_no")

    def test_unregistered_event_name(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["event_name"] = "search"

        _, errors = self.validate_values(event)

        self.assert_has_error(errors, "[enum] $.event_name")

    def test_schema_version_mismatch(self) -> None:
        event = copy.deepcopy(self.user_event)
        event["schema_version"] = "1.0.0-draft"

        _, errors = self.validate_values(event)

        self.assert_has_error(errors, "[const] $.schema_version")

    def test_duplicate_event_id(self) -> None:
        duplicate = copy.deepcopy(self.user_event)

        _, errors = self.validate_values([self.user_event, duplicate])

        self.assert_has_error(errors, "[duplicate_event_id] $.event_id")

    def test_synthetic_runtime_metadata_is_required(self) -> None:
        event = copy.deepcopy(self.user_event)
        event.update(
            {
                "actor_type": "synthetic",
                "source": "simulator",
                "persona_id": "PC00001",
                "properties": {
                    "scenario_id": "normal_day",
                    "simulation_run_id": "run-20260831-001"
                },
            }
        )

        _, errors = self.validate_values(event)

        self.assert_has_error(errors, "generator_type")


if __name__ == "__main__":
    unittest.main()
