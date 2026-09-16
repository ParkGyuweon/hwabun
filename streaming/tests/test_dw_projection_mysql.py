"""Opt-in MySQL 8.4 integration test against a disposable test server.

Set DW_TEST_MYSQL_HOST/PORT/USER/PASSWORD explicitly. These tests create and
delete only a randomly named dw_projection_test_* database, never the real dw.
"""
from datetime import date, datetime
import os
from pathlib import Path
import re
import tempfile
import unittest
from uuid import uuid4

from streaming.jobs.dw_projection_source import ParquetSnapshot, ProjectionError, arrow_type, load_contract
from streaming.jobs.publish_user_trait_job import Config, MysqlStore, connect, publish


@unittest.skipUnless(os.getenv("DW_TEST_MYSQL_HOST"), "requires explicit disposable MySQL test server")
class MysqlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql

        cls.database = "dw_projection_test_" + uuid4().hex[:12]
        cls.host = os.environ["DW_TEST_MYSQL_HOST"]
        cls.port = int(os.getenv("DW_TEST_MYSQL_PORT", "3306"))
        cls.user = os.environ["DW_TEST_MYSQL_USER"]
        cls.password = os.environ["DW_TEST_MYSQL_PASSWORD"]
        cls.admin = pymysql.connect(host=cls.host, port=cls.port, user=cls.user,
                                   password=cls.password, autocommit=True)
        with cls.admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{cls.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        cls.addClassCleanup(cls.cleanup_database)

    @classmethod
    def cleanup_database(cls):
        if not re.fullmatch(r"dw_projection_test_[0-9a-f]{12}", cls.database):
            raise RuntimeError("Refusing to drop an unexpected database")
        try:
            with cls.admin.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{cls.database}`")
        finally:
            cls.admin.close()

    def setUp(self):
        import pyarrow as pa

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.contract = load_contract()
        self.schema = pa.schema([(c.name, arrow_type(c)) for c in self.contract.columns])
        self.config = Config(self.host, self.user, self.password, self.port, self.database, batch_size=2)
        self.connection = connect(self.config)
        self.addCleanup(self.connection.close)
        self.store = MysqlStore(self.connection, self.database, self.contract)
        self.store.execute(f"DROP TABLE IF EXISTS {self.store.table('user_trait_daily')}")
        self.store.execute(self.contract.create_staging_sql(self.database, "user_trait_daily"))
        self.store.cleanup()

    def rows(self, user="회원-1", score=2.5):
        return [dict(user_id=user, trait_date_kst=date(2026, 9, 16), trait=trait,
                     identity_scope="account", actor_type="user", source="web",
                     scenario_id=None, simulation_run_id=None, trait_score=score,
                     contributing_event_count=2, trait_rank=index + 1, is_primary_trait=index == 0,
                     window_start_date=date(2026, 8, 18), window_end_date=date(2026, 9, 16),
                     trait_policy_version="v1", mart_processed_at=datetime(2026, 9, 16, 3, 0, 0, 123000))
                for index, trait in enumerate(("price", "ingredient", "review", "concern", "participate"))]

    def source(self, rows):
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self.path / uuid4().hex
        path.mkdir()
        table = pa.Table.from_pylist(rows, schema=self.schema)
        if rows:
            pq.write_to_dataset(table, root_path=str(path), partition_cols=["trait_date_kst"])
        else:
            pq.write_table(table, path / "empty.parquet")
        (path / "_SUCCESS").touch()
        return ParquetSnapshot(path, self.contract)

    def count(self):
        return self.store.scalar(f"SELECT COUNT(*) FROM {self.store.table('user_trait_daily')}")

    def test_roundtrip_repeat_and_recommendation_reader(self):
        from batch.serving.user_trait import read_mysql, aggregate

        source = self.source(self.rows())
        publish(source, self.store, self.config, {})
        publish(source, self.store, self.config, {})
        self.assertEqual(5, self.count())
        loaded = read_mysql(dict(host=self.host, port=self.port, user=self.user,
                                 password=self.password, db=self.database))
        self.assertEqual(5, len(loaded))
        self.assertEqual("price", aggregate(loaded)[("account", "회원-1")]["primary"])
        self.assertEqual(2.5, aggregate(loaded)[("account", "회원-1")]["price"])
        result = self.store.rows(f"SELECT scenario_id, simulation_run_id, mart_processed_at "
                                 f"FROM {self.store.table('user_trait_daily')} LIMIT 1")[0]
        self.assertEqual((None, None, datetime(2026, 9, 16, 3, 0, 0, 123000)), result)

    def test_null_duplicate_failure_preserves_serving_then_cleans_up(self):
        publish(self.source(self.rows()), self.store, self.config, {})
        duplicate = self.rows("other")
        duplicate.append(duplicate[0])
        report = {}
        with self.assertRaises(ProjectionError):
            publish(self.source(duplicate), self.store, self.config, report)
        self.assertEqual(5, self.count())
        self.assertEqual(6, self.store.scalar(f"SELECT COUNT(*) FROM {self.store.table(report['staging'])}"))
        publish(self.source(self.rows("new-user")), self.store, self.config, {})
        self.assertEqual(0, self.store.scalar("SELECT COUNT(*) FROM information_schema.TABLES "
                                             "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                                             (self.database, report["staging"])))

    def test_collation_equivalent_grain_is_rejected(self):
        publish(self.source(self.rows()), self.store, self.config, {})
        with self.assertRaises(ProjectionError):
            publish(self.source(self.rows("Alice") + self.rows("alice")), self.store, self.config, {})
        self.assertEqual(5, self.count())

    def test_required_null_preserves_serving(self):
        publish(self.source(self.rows()), self.store, self.config, {})
        bad = self.rows()
        bad[-1]["contributing_event_count"] = None
        with self.assertRaises(ProjectionError):
            publish(self.source(bad), self.store, self.config, {})
        self.assertEqual(5, self.count())

    def test_empty_explicitly_replaces_old_rows(self):
        publish(self.source(self.rows()), self.store, self.config, {})
        source = self.source([])
        with self.assertRaises(ProjectionError):
            publish(source, self.store, self.config, {})
        self.assertEqual(5, self.count())
        config = Config(self.host, self.user, self.password, self.port, self.database, allow_empty=True)
        publish(source, self.store, config, {})
        self.assertEqual(0, self.count())

    def test_second_publisher_is_blocked(self):
        other = connect(self.config)
        self.addCleanup(other.close)
        locked = MysqlStore(other, self.database, self.contract)
        self.assertTrue(locked.acquire())
        try:
            with self.assertRaises(ProjectionError):
                publish(self.source(self.rows()), self.store, self.config, {})
        finally:
            locked.release()
        self.assertEqual(0, self.count())


if __name__ == "__main__":
    unittest.main()
