from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streaming.jobs.dw_projection_source import (
    DEFAULT_PROJECTION_MARTS,
    MART,
    PROJECTION_MARTS,
    load_contract,
    partition_columns_for,
    source_path_for,
)
from streaming.jobs.publish_user_trait_job import main


class MartContractTests(unittest.TestCase):
    def test_default_targets_cover_recommendation_and_dashboard_core(self):
        self.assertEqual(MART, DEFAULT_PROJECTION_MARTS[0])
        self.assertIn("brand_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("product_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("funnel_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("purchase_reason_daily", DEFAULT_PROJECTION_MARTS)

    def test_all_contract_projection_targets_have_partition_rules(self):
        for mart in PROJECTION_MARTS:
            with self.subTest(mart=mart):
                contract = load_contract(mart=mart)
                self.assertEqual(mart, contract.mart)
                self.assertTrue(set(partition_columns_for(mart)) <= set(contract.names))

    def test_source_path_is_rooted_by_mart(self):
        self.assertEqual(
            Path("/data/marts/brand_daily_kpi"),
            source_path_for(Path("/data/marts"), "brand_daily_kpi"),
        )

    def test_unknown_partition_mart_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "No partition contract"):
            partition_columns_for("not_a_projection_mart")


class MultiMartCliTests(unittest.TestCase):
    class Source:
        row_count = 1

        def batches(self, _batch_size):
            return iter([[('value',)]])

        def assert_unchanged(self):
            return None

    def test_multiple_marts_use_each_default_source_path(self):
        contracts = []
        sources = []
        published = []

        def contract_for(_path, mart):
            contract = SimpleNamespace(mart=mart)
            contracts.append(contract)
            return contract

        def source_for(path, contract):
            sources.append((Path(path), contract.mart))
            return self.Source()

        def publish_for(_source, _store, _config, report, mart=None):
            published.append((report["mart"], mart))
            report.update(status="published", published=True, source_rows=1, inserted_rows=1)
            return report

        with patch("streaming.jobs.publish_user_trait_job.load_contract", side_effect=contract_for), \
                patch("streaming.jobs.publish_user_trait_job.ParquetSnapshot", side_effect=source_for), \
                patch("streaming.jobs.publish_user_trait_job.connect", return_value=SimpleNamespace(close=lambda: None)), \
                patch("streaming.jobs.publish_user_trait_job.publish", side_effect=publish_for), \
                patch.dict("os.environ", {
                    "DW_MYSQL_HOST": "localhost",
                    "DW_MYSQL_USER": "writer",
                    "DW_MYSQL_PASSWORD": "secret",
                }):
            code = main([
                    "--marts", "user_trait_daily,brand_daily_kpi",
                    "--source-root", "/data/marts",
                ])

        self.assertEqual(0, code)
        self.assertEqual(
            [
                (Path("/data/marts/user_trait_daily"), "user_trait_daily"),
                (Path("/data/marts/brand_daily_kpi"), "brand_daily_kpi"),
            ],
            sources,
        )
        self.assertEqual(
            [("user_trait_daily", "user_trait_daily"), ("brand_daily_kpi", "brand_daily_kpi")],
            published,
        )


if __name__ == "__main__":
    unittest.main()
