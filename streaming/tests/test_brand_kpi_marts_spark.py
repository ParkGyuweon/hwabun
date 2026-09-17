import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    _brand_daily_kpi,
    _product_daily_kpi,
)


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
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P2", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_view"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P2", "product_view"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P2", "add_to_cart"),
                (event_date, None, "user", "web", None, None, None, "S-null", "U2", "P3", "product_view"),
                (event_date, "C", "agent", "simulator", "agent_llm", "K01", "RUN1", "S2", "U3", "P4", "product_view"),
                # 같은 브랜드라도 실행 축과 일자가 다르면 섞이면 안 된다.
                (event_date, "A", "agent", "simulator", "agent_llm", "K01", "RUN1", "S3", "U4", "P1", "product_view"),
                (next_date, "A", "user", "web", None, None, None, "S4", "U5", "P1", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [
                ("A", "user", "web", None, None, None, "S1", "U1", "P1", datetime(2026, 9, 8, 1, 5, tzinfo=timezone.utc)),
                ("A", "user", "web", None, None, None, "S1", "U1", "P2", datetime(2026, 9, 8, 1, 6, tzinfo=timezone.utc)),
                (None, "user", "web", None, None, None, "S-null", "U2", "P3", datetime(2026, 9, 8, 1, 7, tzinfo=timezone.utc)),
            ],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
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
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "quick_look"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "add_to_cart"),
                # 세션 2: 상품 상세만 열고 담지 않았다
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P1", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
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
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "quick_look"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_view"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P2", "quick_look"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        self.assertEqual(1, row["quick_look_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["detail_view_sessions"])

    def test_impression_sessions_count_all_three_surfaces(self):
        """노출 Event 는 셋이다 (§4.1). product_impression 만 세면 추천·배너로만

        노출된 세션이 분모에서 빠져 detail_entry_rate 가 1 을 넘는다.
        104만 건 실행에서 persona_segment 가 이것으로 6행 실패했다.
        """
        event_date = date(2026, 9, 8)
        product_fact = self.spark.createDataFrame(
            [
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "recommendation_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_view"),
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P2", "banner_impression"),
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P2", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        # product_impression 이 0 인데도 두 세션 다 노출로 잡혀야 한다
        self.assertEqual(2, row["impression_sessions"])
        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_detail_entry_rate_never_exceeds_one_on_recommendation_entry(self):
        """추천으로만 들어온 세션도 분모에 있어야 비율이 1 을 안 넘는다."""
        event_date = date(2026, 9, 8)
        product_fact = self.spark.createDataFrame(
            [
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "recommendation_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_view"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        self.assertLessEqual(row["detail_entry_rate"], 1.0)

    def test_same_brand_splits_by_date_and_execution_axes(self):
        """실사용자와 합성 로그, 서로 다른 일자가 한 행으로 섞이면 안 된다."""
        product_fact, funnel_session = self._facts()

        rows = _brand_daily_kpi(
            product_fact, funnel_session, "Asia/Seoul"
        ).where("brand_id = 'A'").collect()
        keys = {
            (
                row["event_date_kst"], row["actor_type"], row["source"],
                row["generator_type"], row["scenario_id"], row["simulation_run_id"],
            )
            for row in rows
        }

        self.assertEqual(3, len(rows))
        self.assertEqual(
            {
                (date(2026, 9, 8), "user", "web", None, None, None),
                (date(2026, 9, 8), "agent", "simulator", "agent_llm", "K01", "RUN1"),
                (date(2026, 9, 9), "user", "web", None, None, None),
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

    def test_click_sessions_are_deduplicated_across_products(self):
        """브랜드 클릭 세션도 상품 Mart 합산이 아니라 Fact 에서 직접 dedup 한다.

        한 세션이 같은 브랜드 상품 두 개를 클릭해도 브랜드 클릭 세션은 1이다
        (dashboard-mart-api-spec.md §6-1).
        """
        event_date = date(2026, 9, 8)
        product_fact = self.spark.createDataFrame(
            [
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_click"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P2", "product_click"),
                (event_date, "A", "user", "web", None, None, None, "S1", "U1", "P1", "product_view"),
                # 클릭 없이 Quick Look 으로 상세를 연 세션. 클릭 세션에 들어가면 안 된다
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P1", "product_impression"),
                (event_date, "A", "user", "web", None, None, None, "S2", "U2", "P1", "quick_look"),
            ],
            "event_date_kst date, brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, event_name string",
        )
        funnel_session = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, scenario_id string, "
            "simulation_run_id string, session_id string, user_id string, product_id string, "
            "first_information_view_at timestamp",
        )

        row = _brand_daily_kpi(product_fact, funnel_session, "Asia/Seoul").first()

        # 상품 두 개를 클릭했어도 세션은 하나다
        self.assertEqual(1, row["click_sessions"])
        self.assertEqual(2, row["impression_sessions"])
        # Quick Look 세션은 클릭 없이 상세를 열었다 — 그래서 클릭을 분모로 쓰지 않는다
        self.assertEqual(2, row["detail_view_sessions"])
        self.assertLessEqual(row["click_sessions"], row["impression_sessions"])


PRODUCT_FACT_SCHEMA = (
    "event_date_kst date, product_id string, category_id string, brand_id string, "
    "actor_type string, source string, generator_type string, scenario_id string, "
    "simulation_run_id string, session_id string, user_id string, event_name string, "
    "order_id string, purchase_quantity int, item_revenue decimal(18,2), currency string, "
    "close_reason string, action string, navigation_source string"
)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class ProductKpiMartsSparkTest(unittest.TestCase):
    """상품 grain KPI. 분모 규칙은 브랜드 Mart와 같아야 한다 (dw-schema.md §4.1)."""

    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("product-kpi-marts-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, PRODUCT_FACT_SCHEMA)

    @staticmethod
    def _event(session, user, event_name, day=8, product="P1", action=None):
        return (
            date(2026, 9, day), product, "CAT1", "A", "user", "web",
            None, None, None, session, user, event_name, None, None, None, None,
            None, action, None,
        )

    def test_quick_look_cart_counts_against_detail_view_sessions(self):
        """Quick Look 으로만 담은 세션도 분모에 들어가야 담기율이 1.0 을 넘지 않는다.

        브랜드 Mart 는 데이터 235 에서 고쳤는데 상품 Mart 가 빠져 있었다.
        재생 데이터에서 1,248행 중 323행이 1.0 을 넘었고 최댓값이 6.0 이었다 (Jira 277).
        """
        facts = self._facts([
            # 세션 1: 노출 → Quick Look → 담기. 상품 상세는 안 열었다
            self._event("S1", "U1", "product_impression"),
            self._event("S1", "U1", "quick_look"),
            self._event("S1", "U1", "add_to_cart"),
            # 세션 2: 상품 상세만 열고 담지 않았다
            self._event("S2", "U2", "product_impression"),
            self._event("S2", "U2", "product_view"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["quick_look_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        # 분모가 product_view(1) 였다면 1.0, detail_view(2) 라서 0.5 다.
        self.assertEqual(0.5, row["add_to_cart_rate"])
        self.assertLessEqual(row["add_to_cart_sessions"], row["detail_view_sessions"])

    def test_detail_view_counts_a_session_once_across_both_paths(self):
        """한 세션이 Quick Look 과 상품 상세를 모두 열어도 상세 세션은 하나다."""
        facts = self._facts([
            self._event("S1", "U1", "quick_look"),
            self._event("S1", "U1", "product_view"),
            self._event("S1", "U1", "add_to_cart"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["quick_look_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        # 더하면 2다. 합집합이라 1이어야 한다.
        self.assertEqual(1, row["detail_view_sessions"])
        self.assertEqual(1.0, row["add_to_cart_rate"])

    def test_purchase_rate_uses_detail_view_sessions(self):
        """구매율도 같은 분모다. Quick Look 에서 담아 산 세션이 분자에만 들어가면 안 된다."""
        facts = self._facts([
            self._event("S1", "U1", "quick_look"),
            (
                date(2026, 9, 8), "P1", "CAT1", "A", "user", "web", None, None, None,
                "S1", "U1", "purchase", "O1", 1, None, None, None, None, None,
            ),
            self._event("S2", "U2", "product_view"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["purchase_sessions"])
        self.assertEqual(0.5, row["purchase_rate"])

    def test_zero_denominator_rates_are_null_not_zero(self):
        """분모가 0인 비율은 0이 아니라 NULL 이다. 값 없음과 0%는 다른 신호다."""
        facts = self._facts([
            # 상세를 한 번도 안 연 상품. 노출만 있다
            self._event("S1", "U1", "product_impression"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(0, row["detail_view_sessions"])
        self.assertIsNone(row["add_to_cart_rate"])
        self.assertIsNone(row["purchase_rate"])
        # 노출은 1이라 분모가 0이 아니다. 클릭이 없으니 0.0 이 정답이다.
        self.assertEqual(1, row["product_impression_count"])
        self.assertEqual(0.0, row["product_ctr"])

    def test_impression_rates_use_event_counts_not_sessions(self):
        """product_ctr · detail_entry_rate 분모는 노출 Event 수다. 세션 수가 아니다.

        같은 세션이 목록에서 상품을 두 번 스치면 노출은 2다. 이 둘은 노출 하나하나를
        모수로 보는 지표라 브랜드 Mart 의 같은 이름 지표와 분모가 다르다.
        """
        facts = self._facts([
            self._event("S1", "U1", "product_impression"),
            self._event("S1", "U1", "product_impression"),
            self._event("S1", "U1", "product_click"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["product_impression_count"])
        self.assertEqual(1, row["product_click_count"])
        self.assertEqual(0.5, row["product_ctr"])


if __name__ == "__main__":
    unittest.main()
