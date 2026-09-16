import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streaming.jobs.publish_user_trait_job import (
    ProjectionError,
    main,
    read_user_trait_snapshot,
    write_user_trait_jsonl,
)


NAMES = (
    "trait_date_kst", "actor_type", "user_id", "identity_scope", "trait",
    "trait_score", "is_primary_trait", "window_end_date", "trait_policy_version",
)


def row(trait_date, actor_type, user_id, scope, trait, score, primary,
        window_end=date(2026, 9, 14)):
    return (
        trait_date, actor_type, user_id, scope, trait, score, primary,
        window_end, "user-trait-v2",
    )


class FakeSource:
    contract = SimpleNamespace(names=NAMES)

    def __init__(self, rows):
        self.rows = rows
        self.unchanged_checks = 0

    def batches(self, batch_size):
        for start in range(0, len(self.rows), batch_size):
            yield self.rows[start:start + batch_size]
        self.assert_unchanged()

    def assert_unchanged(self):
        self.unchanged_checks += 1


class JsonlExportTests(unittest.TestCase):
    def test_latest_user_rows_are_projected_and_sorted(self):
        source = FakeSource([
            row(date(2026, 9, 13), "user", "1001", "account", "price", 1.0, True),
            row(date(2026, 9, 14), "synthetic", "PC1", "persona", "price", 9.0, True),
            row(date(2026, 9, 14), "user", "1001", "account", "price", 4.5, True),
            row(date(2026, 9, 14), "user", "1001", "account", "concern", 2.5, False),
        ])

        rows = read_user_trait_snapshot(source, batch_size=2)

        self.assertEqual(["concern", "price"], [item["trait"] for item in rows])
        self.assertEqual({
            "user_id": "1001",
            "identity_scope": "account",
            "trait": "concern",
            "trait_score": 2.5,
            "is_primary_trait": False,
            "window_end_date": "2026-09-14",
            "trait_policy_version": "user-trait-v2",
        }, rows[0])
        self.assertGreaterEqual(source.unchanged_checks, 3)

    def test_duplicate_consumer_grain_is_rejected(self):
        source = FakeSource([
            row(date(2026, 9, 14), "user", "1001", "account", "price", 1.0, False),
            row(date(2026, 9, 14), "user", "1001", "account", "price", 2.0, True),
        ])

        with self.assertRaisesRegex(ProjectionError, "duplicate consumer grain"):
            read_user_trait_snapshot(source, batch_size=100)

    def test_write_is_atomic_and_empty_export_is_blocked(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "user_trait_snapshot.jsonl"
            path.write_text("old\n", encoding="utf-8")
            with self.assertRaisesRegex(ProjectionError, "Empty snapshot"):
                write_user_trait_jsonl([], path)
            self.assertEqual("old\n", path.read_text(encoding="utf-8"))

            rows = [{
                "user_id": "1001",
                "identity_scope": "account",
                "trait": "price",
                "trait_score": 4.5,
                "is_primary_trait": True,
                "window_end_date": "2026-09-14",
                "trait_policy_version": "user-trait-v2",
            }]
            self.assertEqual(1, write_user_trait_jsonl(rows, path))
            self.assertEqual(rows, [json.loads(path.read_text(encoding="utf-8"))])

    def test_jsonl_only_does_not_require_mysql(self):
        source = FakeSource([
            row(date(2026, 9, 14), "user", "1001", "account", "price", 4.5, True),
        ])
        contract = SimpleNamespace()
        with TemporaryDirectory() as directory:
            output = Path(directory) / "snapshot.jsonl"
            with patch("streaming.jobs.publish_user_trait_job.load_contract", return_value=contract), \
                    patch("streaming.jobs.publish_user_trait_job.ParquetSnapshot", return_value=source):
                self.assertEqual(0, main([
                    "--source", str(Path(directory) / "marts"),
                    "--ddl", str(Path(directory) / "schema.sql"),
                    "--emit-jsonl", str(output),
                    "--jsonl-only",
                ]))
            self.assertEqual("1001", json.loads(output.read_text(encoding="utf-8"))["user_id"])


if __name__ == "__main__":
    unittest.main()
