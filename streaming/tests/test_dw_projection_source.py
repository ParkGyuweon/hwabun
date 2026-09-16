from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest

from streaming.jobs.dw_projection_source import (
    Column, ParquetSnapshot, ProjectionError, arrow_type, identifier, load_contract,
)


class ContractTests(unittest.TestCase):
    def test_checked_in_ddl_uses_grain_not_surrogate(self):
        contract = load_contract()
        self.assertEqual(16, len(contract.columns))
        self.assertNotIn("dw_row_id", contract.names)
        self.assertIn("scenario_id", contract.grain)
        self.assertIn("simulation_run_id", contract.grain)
        self.assertTrue(next(c for c in contract.columns if c.name == "scenario_id").nullable)

    def test_identifier_rejects_injection_and_long_names(self):
        for value in ("dw; DROP TABLE x", "x" * 65, "a.b", "A"):
            with self.subTest(value=value), self.assertRaises(ProjectionError):
                identifier(value)

    def test_null_is_preserved_but_required_null_fails(self):
        self.assertIsNone(Column("scenario_id", "VARCHAR(64)", True).normalize(None))
        with self.assertRaises(ProjectionError):
            Column("user_id", "VARCHAR(64)", False).normalize(None)

    def test_long_strings_are_not_truncated(self):
        with self.assertRaises(ProjectionError):
            Column("user_id", "VARCHAR(64)", False).normalize("a" * 65)

    def test_invalid_numbers_fail(self):
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ProjectionError):
                Column("trait_score", "DOUBLE", True).normalize(value)
        with self.assertRaises(ProjectionError):
            Column("trait_rank", "INT", True).normalize(2**31)

    def test_timestamp_utc_and_milliseconds(self):
        source = datetime(2026, 9, 16, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(datetime(2026, 9, 16, 3, 0, 0, 123000),
                         Column("mart_processed_at", "DATETIME(3)", False).normalize(source))

    def test_boolean_and_date(self):
        self.assertEqual(1, Column("is_primary_trait", "TINYINT(1)", True).normalize(True))
        with self.assertRaises(ProjectionError):
            Column("trait_date_kst", "DATE", False).normalize("2026-09-16")


try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = None


@unittest.skipIf(pa is None, "pyarrow is not installed")
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.contract = load_contract()
        self.schema = pa.schema([(c.name, arrow_type(c)) for c in self.contract.columns])

    def row(self):
        return dict(user_id="account-1", trait_date_kst=date(2026, 9, 16), trait="price",
                    identity_scope="account", actor_type="user", source="web", scenario_id=None,
                    simulation_run_id=None, trait_score=3.5, contributing_event_count=2,
                    trait_rank=1, is_primary_trait=True, window_start_date=date(2026, 8, 18),
                    window_end_date=date(2026, 9, 16), trait_policy_version="v1",
                    mart_processed_at=datetime(2026, 9, 16, 3))

    def write(self, rows, partitioned=True):
        table = pa.Table.from_pylist(rows, schema=self.schema)
        if partitioned and rows:
            pq.write_to_dataset(table, root_path=str(self.path), partition_cols=["trait_date_kst"])
        else:
            pq.write_table(table, self.path / "part-0.parquet")
        (self.path / "_SUCCESS").touch()

    def test_hive_date_null_axes_and_bounded_batches(self):
        self.write([self.row(), self.row()])
        source = ParquetSnapshot(self.path, self.contract)
        batches = list(source.batches(1))
        self.assertEqual(2, source.row_count)
        self.assertEqual([1, 1], [len(b) for b in batches])
        row = dict(zip(self.contract.names, batches[0][0]))
        self.assertEqual(date(2026, 9, 16), row["trait_date_kst"])
        self.assertIsNone(row["scenario_id"])

    def test_empty_snapshot_has_schema(self):
        self.write([], partitioned=False)
        source = ParquetSnapshot(self.path, self.contract)
        self.assertEqual(0, source.row_count)
        self.assertEqual(0, sum(len(b) for b in source.batches(10)))

    def test_success_only_directory_is_not_empty_snapshot(self):
        (self.path / "_SUCCESS").touch()
        with self.assertRaises(ProjectionError):
            ParquetSnapshot(self.path, self.contract)

    def test_incomplete_snapshot_rejected(self):
        self.write([self.row()])
        (self.path / "_SUCCESS").unlink()
        with self.assertRaises(ProjectionError):
            ParquetSnapshot(self.path, self.contract)

    def test_missing_column_in_second_file_rejected(self):
        self.write([self.row()], partitioned=False)
        table = pa.Table.from_pylist([self.row()], schema=self.schema).drop(["trait_score"])
        pq.write_table(table, self.path / "part-1.parquet")
        with self.assertRaises(ProjectionError):
            ParquetSnapshot(self.path, self.contract)

    def test_changed_snapshot_rejected(self):
        self.write([self.row()], partitioned=False)
        source = ParquetSnapshot(self.path, self.contract)
        pq.write_table(pa.Table.from_pylist([self.row()], schema=self.schema), self.path / "part-1.parquet")
        with self.assertRaises(ProjectionError):
            source.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
