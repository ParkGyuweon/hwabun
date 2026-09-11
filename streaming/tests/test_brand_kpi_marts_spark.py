import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import _brand_daily_kpi


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class BrandKpiMartsSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("brand-kpi-marts-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _facts(self):
        event_date = date(2026, 9, 8)
        next_date = date(2026, 9, 9)
        product_fact = self.spark.createDataFrame(
            [
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P2", "product_impression"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "product_view"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P2", "product_view"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P2", "add_to_cart"),
                (event_date, None, "user", "web", None, None, "S-null", "U2", "P3", "product_view"),
                (event_date, "C", "agent", "simulator", "K01", "RUN1", "S2", "U3", "P4", "product_view"),
                # 같은 브랜드라도 실행 축과 일자가 다르면 섞이면 안 된다.
                (event_date, "A", "agent", "simulator", "K01", "RUN1", "S3", "U4", "P1", "product_view"),
                (next_date, "A", "user", "web", None, None, "S4", "U5", "P1", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [
                ("A", "user", "web", None, None, "S1", "U1", "P1", datetime(2026, 9, 8, 1, 5, tzinfo=timezone.utc)),
                ("A", "user", "web", None, None, "S1", "U1", "P2", datetime(2026, 9, 8, 1, 6, tzinfo=timezone.utc)),
                (None, "user", "web", None, None, "S-null", "U2", "P3", datetime(2026, 9, 8, 1, 7, tzinfo=timezone.utc)),
            ],
            "brand_id string, actor_type string, source string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )
        return product_fact, funnel_session

    def test_brand_sessions_are_deduplicated_across_products(self):
        product_fact, funnel_session = self._facts()

        row = _brand_daily_kpi(
            product_fact, funnel_session, "Asia/Seoul"
        ).where(
            "brand_id = 'A' and source = 'web' and event_date_kst = date '2026-09-08'"
        ).first()

        self.assertEqual(1, row["impression_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["information_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        self.assertEqual(1, row["unique_user_count"])
        self.assertEqual(2, row["product_count_viewed"])
        self.assertEqual(1.0, row["detail_entry_rate"])
        self.assertEqual(1.0, row["information_view_rate"])
        self.assertEqual(1.0, row["view_to_cart_rate"])

    def test_null_brand_is_excluded_and_zero_denominator_rate_is_null(self):
        product_fact, funnel_session = self._facts()
        mart = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul")

        self.assertEqual(0, mart.where("brand_id is null").count())
        row = mart.where("brand_id = 'C'").first()
        self.assertEqual("agent", row["actor_type"])
        self.assertEqual("K01", row["scenario_id"])
        self.assertEqual("RUN1", row["simulation_run_id"])
        # 노출 세션이 0이므로 상세 진입률만 NULL이다.
        self.assertEqual(0, row["impression_sessions"])
        self.assertIsNone(row["detail_entry_rate"])
        # 조회 세션은 1이라 분모가 0이 아니다. 값 없음이 아니라 0.0이 정답이다.
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(0.0, row["information_view_rate"])
        self.assertEqual(0.0, row["view_to_cart_rate"])

    def test_quick_look_cart_counts_against_detail_view_sessions(self):
        """Quick Look 으로만 담은 세션도 분모에 들어가야 비율이 1.0 을 넘지 않는다.

        목록에서 Quick Look 을 열어 PDP 없이 담는 건 화면에 있는 정상 동선이다.
        분모를 product_view 로 두면 분자에만 잡혀 담기율이 1.0 을 넘는다
        (Jira 235 실행 검증: 담기 6,029쌍 중 2,356쌍이 이 경로).
        """
        event_date = date(2026, 9, 8)
        product_fact = self.spark.createDataFrame(
            [
                # 세션 1: 목록 노출 → Quick Look → 담기. 상품 상세는 열지 않았다
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "quick_look"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "add_to_cart"),
                # 세션 2: 상품 상세만 열고 담지 않았다
                (event_date, "A", "user", "web", None, None, "S2", "U2", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, "S2", "U2", "P1", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        self.assertEqual(1, row["quick_look_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        # 분모가 product_view(1) 였다면 1.0, detail_view(2) 라서 0.5 다.
        self.assertEqual(0.5, row["view_to_cart_rate"])
        self.assertLessEqual(row["add_to_cart_sessions"], row["detail_view_sessions"])
        # 상세 진입률도 Quick Look 을 포함한다 — 이름이 가리키는 동작이다.
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_detail_view_counts_a_session_once_across_both_paths(self):
        """한 세션이 Quick Look 과 상품 상세를 모두 열어도 상세 세션은 하나다."""
        event_date = date(2026, 9, 8)
        product_fact = self.spark.createDataFrame(
            [
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "quick_look"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P1", "product_view"),
                (event_date, "A", "user", "web", None, None, "S1", "U1", "P2", "quick_look"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        self.assertEqual(1, row["quick_look_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["detail_view_sessions"])

    def test_same_brand_splits_by_date_and_execution_axes(self):
        """실사용자와 합성 로그, 서로 다른 일자가 한 행으로 섞이면 안 된다."""
        product_fact, funnel_session = self._facts()

        rows = _brand_daily_kpi(
            product_fact, funnel_session, "Asia/Seoul"
        ).where("brand_id = 'A'").collect()
        keys = {
            (
                row["event_date_kst"], row["actor_type"], row["source"],
                row["scenario_id"], row["simulation_run_id"],
            )
            for row in rows
        }

        self.assertEqual(3, len(rows))
        self.assertEqual(
            {
                (date(2026, 9, 8), "user", "web", None, None),
                (date(2026, 9, 8), "agent", "simulator", "K01", "RUN1"),
                (date(2026, 9, 9), "user", "web", None, None),
            },
            keys,
        )

    def test_grain_is_unique_and_rebuild_is_deterministic(self):
        product_fact, funnel_session = self._facts()
        first = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul")
        second = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul")
        grain = [
            "event_date_kst", "brand_id", "actor_type", "source",
            "scenario_id", "simulation_run_id",
        ]
        duplicates = first.groupBy(*grain).count().where("count > 1").count()
        columns = [column for column in first.columns if column != "mart_processed_at"]

        self.assertEqual(0, duplicates)
        self.assertEqual(0, first.select(*columns).exceptAll(second.select(*columns)).count())
        self.assertEqual(0, second.select(*columns).exceptAll(first.select(*columns)).count())


if __name__ == "__main__":
    unittest.main()
