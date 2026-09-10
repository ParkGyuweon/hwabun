import gzip
import json
import os
import tempfile
import unittest

from streaming.tools.replay_collector import inspect_file, replay


class ReplayCollectorTest(unittest.TestCase):
    def _input(self, count=3):
        directory = tempfile.TemporaryDirectory()
        path = os.path.join(directory.name, "events.jsonl.gz")
        with gzip.open(path, "wt", encoding="utf-8") as target:
            for index in range(count):
                target.write(
                    json.dumps(
                        {
                            "schema_version": "0.2.0-draft",
                            "event_id": f"e{index}",
                            "event_name": "banner_impression",
                            "occurred_at": "2026-08-28T00:00:00Z",
                            "session_id": "s1",
                            "properties": {
                                "simulation_run_id": "run1",
                                "algorithm": "ltr-v1",
                            },
                        }
                    )
                    + "\n"
                )
        return directory, path

    def test_streams_bounded_batches_and_counts_partial_acceptance(self):
        directory, path = self._input(3)
        payload_sizes = []

        def sender(payload):
            payload_sizes.append(len(payload["events"]))
            size = len(payload["events"])
            if size == 2:
                return 202, {
                    "accepted": 1,
                    "rejected": 1,
                    "rejections": [{"code": "event_intent_mismatch"}],
                }, {}
            return 202, {"accepted": 1, "rejected": 0, "rejections": []}, {}

        try:
            report = replay(path, sender, batch_size=2, sleep=lambda _: None)
        finally:
            directory.cleanup()

        self.assertEqual([2, 1], payload_sizes)
        self.assertEqual(3, report["total"])
        self.assertEqual(2, report["accepted"])
        self.assertEqual(1, report["rejected"])
        self.assertEqual(1, report["partial_acceptance_batches"])
        self.assertTrue(report["accounting_matches_total"])

    def test_retries_transient_response_then_abandons(self):
        directory, path = self._input(2)
        attempts = []

        def sender(_):
            attempts.append(1)
            return 503, {}, {}

        try:
            report = replay(
                path, sender, batch_size=2, max_retries=2, sleep=lambda _: None
            )
        finally:
            directory.cleanup()

        self.assertEqual(3, len(attempts))
        self.assertEqual(2, report["abandoned"])
        self.assertEqual(1, report["retried_batches"])
        self.assertTrue(report["accounting_matches_total"])

    def test_inspection_reports_missing_banner_policy_version(self):
        directory, path = self._input(2)
        try:
            report = inspect_file(path)
        finally:
            directory.cleanup()

        self.assertEqual(2, report["total"])
        self.assertEqual(1, report["sessions"])
        self.assertEqual(2, report["banner_policy_version_missing"])
        self.assertEqual(["ltr-v1"], report["algorithms"])
        self.assertEqual(
            0, report["banner_clicks_without_preceding_matching_impression"]
        )
        self.assertEqual(0, report["new_brand_non_null_banner_value"])


if __name__ == "__main__":
    unittest.main()
