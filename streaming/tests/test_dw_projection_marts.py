from pathlib import Path
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from streaming.jobs.dw_projection_source import (
    DEFAULT_PROJECTION_MARTS,
    ProjectionError,
    MART,
    PROJECTION_MARTS,
    load_contract,
    partition_columns_for,
    source_path_for,
)
from streaming.jobs.publish_user_trait_job import main


class MartContractTests(unittest.TestCase):
    def test_default_targets_cover_recommendation_and_dashboard_core(self):
        self.assertEqual(22, len(DEFAULT_PROJECTION_MARTS))
        self.assertEqual(22, len(set(DEFAULT_PROJECTION_MARTS)))
        self.assertEqual(MART, DEFAULT_PROJECTION_MARTS[0])
        self.assertIn("brand_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("product_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("funnel_daily_kpi", DEFAULT_PROJECTION_MARTS)
        self.assertIn("purchase_reason_daily", DEFAULT_PROJECTION_MARTS)
        self.assertIn("event_daily", DEFAULT_PROJECTION_MARTS)

    def test_all_contract_projection_targets_have_partition_rules(self):
        for mart in PROJECTION_MARTS:
            with self.subTest(mart=mart):
                contract = load_contract(mart=mart)
                self.assertEqual(mart, contract.mart)
                self.assertTrue(set(partition_columns_for(mart)) <= set(contract.names))

    def test_e4_projection_targets_use_their_contract_partitions(self):
        self.assertEqual(
            ("event_date_kst",),
            partition_columns_for("segment_price_band_daily_kpi"),
        )
        self.assertEqual((), partition_columns_for("brand_cohort_dim"))
        self.assertEqual(
            ("snapshot_week_kst",),
            partition_columns_for("commons_cohort_weekly"),
        )

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


class OneFailingMartDoesNotStopTheRest(unittest.TestCase):
    """마트 한 종이 실패해도 나머지는 발행된다 (Jira 359).

    예전에는 `for mart in marts:` 가 하나의 try 안에 있어서 첫 실패가 루프를 통째로
    끝냈다. 기본 목록 4번째인 `funnel_daily_kpi` 가 `direct_click_sessions` NULL 로
    막히면 뒤 18종이 같이 안 나가고 대시보드 전체가 빈 화면이 됐다.

    발행은 마트마다 staging + RENAME 이라 계속 가도 반쪽 발행이 남지 않는다 —
    실패한 종은 직전 내용을 유지한다.
    """

    class Source:
        row_count = 1

        def batches(self, _batch_size):
            return iter([[('value',)]])

        def assert_unchanged(self):
            return None

    def run_marts(self, marts, failing):
        """`failing` 에 든 마트만 발행에서 터뜨린다. (종료코드, 리포트, 발행된 마트)"""
        published = []
        printed = []

        def publish_for(_source, _store, _config, report, mart=None):
            if mart in failing:
                raise ProjectionError(f"{mart} has NULL in a required column")
            published.append(mart)
            report.update(status="published", published=True, source_rows=1, inserted_rows=1)
            return report

        with patch("streaming.jobs.publish_user_trait_job.load_contract",
                   side_effect=lambda _path, mart: SimpleNamespace(mart=mart)),                 patch("streaming.jobs.publish_user_trait_job.ParquetSnapshot",
                      side_effect=lambda _p, _c: self.Source()),                 patch("streaming.jobs.publish_user_trait_job.connect",
                      return_value=SimpleNamespace(close=lambda: None)),                 patch("streaming.jobs.publish_user_trait_job.publish", side_effect=publish_for),                 patch("builtins.print", side_effect=printed.append),                 patch.dict("os.environ", {"DW_MYSQL_HOST": "localhost",
                                          "DW_MYSQL_USER": "writer",
                                          "DW_MYSQL_PASSWORD": "secret"}):
            code = main(["--marts", ",".join(marts), "--source-root", "/data/marts"])
        return code, json.loads(printed[-1]), published

    def test_가운데가_실패해도_뒤가_발행된다(self):
        marts = ["user_trait_daily", "brand_daily_kpi", "funnel_daily_kpi",
                 "purchase_reason_daily", "event_daily"]
        code, report, published = self.run_marts(marts, {"funnel_daily_kpi"})

        self.assertEqual(["user_trait_daily", "brand_daily_kpi",
                          "purchase_reason_daily", "event_daily"], published)
        self.assertEqual(1, code, "실패가 있으면 타이머·CI 가 실패로 봐야 한다")
        self.assertEqual("partially_published", report["status"])
        self.assertTrue(report["published"])
        self.assertEqual(["funnel_daily_kpi"], report["failed_marts"])

    def test_실패한_종만_리포트에_오류가_남는다(self):
        marts = ["user_trait_daily", "funnel_daily_kpi", "event_daily"]
        _, report, _ = self.run_marts(marts, {"funnel_daily_kpi"})

        bad = report["marts"]["funnel_daily_kpi"]
        self.assertEqual("failed", bad["status"])
        self.assertFalse(bad["published"])
        self.assertEqual("ProjectionError", bad["error_type"])
        self.assertIn("NULL", bad["error"])
        for good in ("user_trait_daily", "event_daily"):
            self.assertEqual("published", report["marts"][good]["status"], good)
            self.assertNotIn("error", report["marts"][good])

    def test_전부_실패하면_발행_안_됨으로_남는다(self):
        marts = ["user_trait_daily", "event_daily"]
        code, report, published = self.run_marts(marts, set(marts))

        self.assertEqual([], published)
        self.assertEqual(1, code)
        self.assertEqual("failed", report["status"])
        self.assertFalse(report["published"])
        self.assertEqual(marts, report["failed_marts"])

    def test_전부_성공하면_예전과_같다(self):
        marts = ["user_trait_daily", "brand_daily_kpi"]
        code, report, published = self.run_marts(marts, set())

        self.assertEqual(marts, published)
        self.assertEqual(0, code)
        self.assertEqual("published", report["status"])
        self.assertTrue(report["published"])
        self.assertNotIn("failed_marts", report)

    def test_단일_마트는_예전처럼_위로_던진다(self):
        """`--mart` 하나는 리포트 모양이 달라 계속 갈 대상이 없다. 동작을 안 바꾼다."""
        code, report, published = self.run_marts(["user_trait_daily"], {"user_trait_daily"})

        self.assertEqual([], published)
        self.assertEqual(1, code)
        self.assertEqual("failed", report["status"])
        self.assertEqual("user_trait_daily", report["mart"])
        self.assertNotIn("marts", report)
        self.assertEqual("ProjectionError", report["error_type"])


if __name__ == "__main__":
    unittest.main()
