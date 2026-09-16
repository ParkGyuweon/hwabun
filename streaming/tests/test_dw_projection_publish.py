import unittest
from unittest.mock import Mock

from streaming.jobs.dw_projection_source import ProjectionError, load_contract
from streaming.jobs.publish_user_trait_job import Config, MysqlStore, publish


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.config = Config("localhost", "writer", "secret")
        self.source = Mock(
            spec=["row_count", "batches", "assert_unchanged"],
            row_count=2,
            unsafe=True,
        )
        self.source.batches.return_value = iter([[("row-1",)], [("row-2",)]])
        # MysqlStore.assert_lock 도 mock 의 assert 접두 가드에 걸린다. Python 3.8 은
        # spec 에 선언돼 있어도 막으므로 source 와 같이 unsafe 를 준다.
        self.store = Mock(spec=MysqlStore, unsafe=True)
        self.store.acquire.return_value = True
        self.report = {}

    def run_job(self, **kwargs):
        return publish(self.source, self.store, self.config, self.report, **kwargs)

    def test_publish_after_validation_and_repeat_is_replacement(self):
        self.run_job()
        first = self.report["staging"]
        self.assertTrue(self.report["published"])
        self.assertEqual(2, self.report["inserted_rows"])
        actions = [c[0] for c in self.store.mock_calls]
        self.assertLess(actions.index("validate"), actions.index("swap"))
        self.assertLess(actions.index("swap"), actions.index("cleanup"))
        self.source.batches.return_value = iter([[("row-1",), ("row-2",)]])
        self.run_job()
        self.assertNotEqual(first, self.report["staging"])

    def test_validation_failure_keeps_staging_and_current(self):
        self.store.validate.side_effect = ProjectionError("duplicate NULL grain")
        with self.assertRaises(ProjectionError):
            self.run_job()
        self.store.swap.assert_not_called()
        self.store.prepare_swap.assert_not_called()
        self.store.cleanup.assert_not_called()
        self.store.release.assert_called_once()

    def test_partial_insert_failure_keeps_current(self):
        self.store.insert.side_effect = [None, RuntimeError("connection lost")]
        with self.assertRaises(RuntimeError):
            self.run_job()
        self.assertEqual(1, self.report["inserted_rows"])
        self.assertEqual("failed", self.report["status"])
        self.store.swap.assert_not_called()

    def test_lock_conflict_does_not_mutate(self):
        self.store.acquire.return_value = False
        with self.assertRaises(ProjectionError):
            self.run_job()
        self.store.create_staging.assert_not_called()
        self.store.release.assert_not_called()

    def test_schema_drift_does_not_mutate(self):
        self.store.check_target.side_effect = ProjectionError("schema mismatch")
        with self.assertRaises(ProjectionError):
            self.run_job()
        self.store.create_staging.assert_not_called()

    def test_empty_requires_explicit_flag(self):
        self.source.row_count = 0
        with self.assertRaises(ProjectionError):
            self.run_job()
        self.store.acquire.assert_not_called()
        self.config = Config("localhost", "writer", "secret", allow_empty=True)
        self.source.batches.return_value = iter([])
        self.run_job()
        self.store.validate.assert_called_once_with(self.report["staging"], 0)
        self.assertTrue(self.report["published"])

    def test_source_changes_block_publication(self):
        self.source.assert_unchanged.side_effect = [None, ProjectionError("source changed")]
        with self.assertRaises(ProjectionError):
            self.run_job()
        self.store.swap.assert_not_called()

    def test_cleanup_failure_is_still_published(self):
        self.store.cleanup.side_effect = RuntimeError("cleanup failed")
        self.run_job()
        self.assertEqual("published", self.report["status"])
        self.assertTrue(self.report["warnings"])

    def test_lost_rename_response_is_unknown_not_retried(self):
        self.store.swap.side_effect = RuntimeError("response lost")
        with self.assertRaises(RuntimeError):
            self.run_job()
        self.assertEqual("publication_unknown", self.report["status"])
        self.store.swap.assert_called_once()
        self.store.cleanup.assert_not_called()

    def test_password_not_in_config_repr(self):
        self.assertNotIn("secret", repr(self.config))


class SqlValidationTests(unittest.TestCase):
    def setUp(self):
        self.store = MysqlStore(Mock(), "dw", load_contract())
        self.store.scalar = Mock(side_effect=[2, 0])
        self.store.rows = Mock(return_value=())

    def test_duplicate_query_uses_nullable_grain_not_dw_row_id(self):
        self.store.validate("user_trait_daily__stg_0000000000000001", 2)
        query = self.store.rows.call_args.args[0]
        self.assertIn("`scenario_id`", query)
        self.assertIn("`simulation_run_id`", query)
        self.assertIn("GROUP BY", query)
        self.assertNotIn("dw_row_id", query)
        self.assertNotIn("COALESCE", query)

    def test_count_mismatch_rejected(self):
        with self.assertRaises(ProjectionError):
            self.store.validate("user_trait_daily__stg_0000000000000001", 3)

    def test_duplicates_rejected(self):
        self.store.rows.return_value = ((1,),)
        with self.assertRaises(ProjectionError):
            self.store.validate("user_trait_daily__stg_0000000000000001", 2)

    def test_required_null_rejected(self):
        self.store.scalar.side_effect = [2, 1]
        with self.assertRaises(ProjectionError):
            self.store.validate("user_trait_daily__stg_0000000000000001", 2)


if __name__ == "__main__":
    unittest.main()
