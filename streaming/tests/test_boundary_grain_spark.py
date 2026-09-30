"""세션·날짜 경계에서 깨지던 grain 가정.

2026-09-22 운영 배치가 이 둘로 실패했다. 제품 결함이 아니라 집계·검사가 담고
있던 전제가 경계에서 성립하지 않은 것이다.

  funnel_session_grain_is_unique        8행 · 전부 actor_type='user'
  banner_daily_counts_and_ctr_are_valid 1행

같은 전제(일자 칸에서 분자 ≤ 분모)가 Event 날짜로 칸을 나누는 Mart 여섯 종의
개수·비율 검사에도 남아 있었다. 그 조건들은 `_period_overflow_count` 로 옮겼다.
"""

import unittest
from datetime import datetime

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import _build_funnel_session_fact
from streaming.jobs.validate_pipeline_job import (
    _over_clicked_banner_count,
    _period_overflow_count,
)

STAGE_SCHEMA = (
    "session_id string, product_id string, user_id string, persona_id string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "actor_type string, source string, category_id string, brand_id string, "
    "event_name string, event_time timestamp"
)

BANNER_SCHEMA = (
    "event_date_kst string, brand_id string, product_id string, "
    "banner_type string, trait_source string, "
    "impression_count long, click_count long, skip_count long"
)

BANNER_IDENTITY = ["brand_id", "product_id", "banner_type", "trait_source"]

PRODUCT_SCHEMA = (
    "event_date_kst string, product_id string, scenario_id string, "
    "impression_count long, product_view_count long, "
    "detail_view_sessions long, add_to_cart_sessions long"
)

PRODUCT_IDENTITY = ["product_id", "scenario_id"]
CART_PAIR = [("add_to_cart_sessions", "detail_view_sessions")]
VIEW_PAIR = [("product_view_count", "impression_count")]


def _stage(session, event, when, user_id=None, product="P1"):
    return (
        session, product, user_id, None, None, None, None,
        "user", "web", "C1", "B1", event, datetime(2026, 9, 22, *when),
    )


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class BoundaryGrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("boundary-grain-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    # ── 세션 경계: 로그인이 여정을 쪼개지 않는다 ──────────────────────
    def _funnel(self, rows):
        frame = self.spark.createDataFrame(rows, STAGE_SCHEMA)
        return _build_funnel_session_fact(frame, "Asia/Seoul")

    def test_login_midway_keeps_one_row(self):
        """비회원으로 보다 로그인해도 한 세션·한 상품은 한 행이다.

        `user_id` 를 묶음 기준에 두면 앞(NULL)과 뒤(계정 id)가 갈려, 실제로는
        상세까지 간 세션이 "노출에서 이탈" 한 행을 하나 더 만든다.
        """
        fact = self._funnel([
            _stage("S1", "product_impression", (4, 48, 20)),
            _stage("S1", "product_click", (4, 48, 21), user_id="U1"),
            _stage("S1", "product_view", (4, 48, 22), user_id="U1"),
        ])

        rows = fact.collect()

        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["reached_impression"])
        self.assertTrue(rows[0]["reached_product_view"])
        self.assertEqual("U1", rows[0]["user_id"])

    def test_anonymous_only_session_keeps_null_user(self):
        """로그인이 없으면 대표값도 없다."""
        fact = self._funnel([
            _stage("S1", "product_impression", (4, 48, 20)),
        ])

        rows = fact.collect()

        self.assertEqual(1, len(rows))
        self.assertIsNone(rows[0]["user_id"])

    def test_two_products_stay_two_rows(self):
        """grain 은 세션·상품이다. 상품이 다르면 행도 다르다."""
        fact = self._funnel([
            _stage("S1", "product_view", (4, 48, 20), product="P1"),
            _stage("S1", "product_view", (4, 48, 21), product="P2"),
        ])

        self.assertEqual(2, fact.count())

    # ── 날짜 경계: 자정을 넘긴 배너 클릭 ──────────────────────────────
    def _banners(self, rows):
        return self.spark.createDataFrame(rows, BANNER_SCHEMA)

    def test_click_after_midnight_is_not_a_violation(self):
        """노출은 앞날, 클릭은 뒷날에 찍혀도 합치면 맞는다.

        `skip_count` 도 같이 상쇄된다 — 정의가 `impression - click` 이라 뒷날 칸은
        자동으로 음수다. 일자별로 음수를 막으면 이 정상 동선이 걸린다.
        """
        frame = self._banners([
            ("2026-09-19", "B1", "P1", "new_brand", "explore", 3, 2, 1),
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1, -1),
        ])

        self.assertEqual(0, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    def test_click_without_any_impression_is_reported(self):
        """어느 날에도 노출이 없으면 그대로 잡힌다."""
        frame = self._banners([
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1, -1),
        ])

        self.assertEqual(1, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    def test_negative_skip_sum_is_reported(self):
        """합산해도 skip 이 음수면 잡는다 — 클릭이 노출보다 많다는 뜻이다."""
        frame = self._banners([
            ("2026-09-19", "B1", "P1", "new_brand", "explore", 1, 2, -1),
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 1, 2, -1),
        ])

        self.assertEqual(1, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    def test_other_banners_do_not_cover_the_gap(self):
        """다른 배너의 노출이 대신 메우지 않는다 — trait_source 가 다르면 별개다."""
        frame = self._banners([
            ("2026-09-20", "B1", "P1", "new_brand", "coldstart", 5, 5, 0),
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1, -1),
        ])

        self.assertEqual(1, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    # ── 날짜 경계: 분자와 분모의 날짜가 따로인 상품 Mart ─────────────────
    def _products(self, rows):
        return self.spark.createDataFrame(rows, PRODUCT_SCHEMA)

    def test_cart_after_midnight_is_not_a_violation(self):
        """23:50 상세 · 00:05 담기면 뒷날 칸은 담기 1 · 상세 0 이다. 합치면 맞는다."""
        frame = self._products([
            ("2026-09-19", "P1", None, 4, 1, 1, 0),
            ("2026-09-20", "P1", None, 0, 0, 0, 1),
        ])

        self.assertEqual(0, _period_overflow_count(frame, PRODUCT_IDENTITY, CART_PAIR))

    def test_cart_without_any_detail_is_reported(self):
        """어느 날에도 상세가 없으면 그대로 잡힌다."""
        frame = self._products([
            ("2026-09-20", "P1", None, 0, 0, 0, 1),
        ])

        self.assertEqual(1, _period_overflow_count(frame, PRODUCT_IDENTITY, CART_PAIR))

    def test_other_products_do_not_cover_the_gap(self):
        """다른 상품의 상세가 대신 메우지 않는다."""
        frame = self._products([
            ("2026-09-20", "P2", None, 5, 5, 5, 0),
            ("2026-09-20", "P1", None, 0, 0, 0, 1),
        ])

        self.assertEqual(1, _period_overflow_count(frame, PRODUCT_IDENTITY, CART_PAIR))

    def test_null_axis_rows_are_summed_together(self):
        """실사용자 행은 scenario_id 가 NULL 이다. NULL 끼리도 같은 칸으로 합친다."""
        frame = self._products([
            ("2026-09-19", "P1", None, 4, 1, 1, 0),
            ("2026-09-20", "P1", None, 0, 0, 0, 1),
            ("2026-09-20", "P1", "S-1", 0, 0, 0, 1),
        ])

        # NULL 칸은 상쇄되고, 시나리오 칸은 상세가 없어 하나만 남는다.
        self.assertEqual(1, _period_overflow_count(frame, PRODUCT_IDENTITY, CART_PAIR))

    def test_rate_bound_skips_days_without_denominator(self):
        """비율 상한은 분모가 0 인 날을 더하지 않는다.

        일자 검사는 그날 비율이 NULL 이라 보지 않았다. 옛 로그의 직접 진입처럼
        노출 없는 조회를 여기서 더하면 일자 검사에 없던 실패가 생긴다.
        """
        frame = self._products([
            ("2026-09-19", "P1", None, 4, 2, 2, 0),
            ("2026-09-20", "P1", None, 0, 3, 3, 0),
        ])

        self.assertEqual(
            0,
            _period_overflow_count(
                frame, PRODUCT_IDENTITY, [], positive_day_pairs=VIEW_PAIR
            ),
        )
        # 같은 데이터를 개수 비교로 더하면 걸린다 — 두 범위를 나눈 이유다.
        self.assertEqual(1, _period_overflow_count(frame, PRODUCT_IDENTITY, VIEW_PAIR))

    def test_rate_overflow_on_counted_days_is_reported(self):
        """분모가 있는 날끼리 더해도 분자가 크면 잡는다."""
        frame = self._products([
            ("2026-09-19", "P1", None, 1, 3, 3, 0),
            ("2026-09-20", "P1", None, 1, 1, 1, 0),
        ])

        self.assertEqual(
            1,
            _period_overflow_count(
                frame, PRODUCT_IDENTITY, [], positive_day_pairs=VIEW_PAIR
            ),
        )


if __name__ == "__main__":
    unittest.main()
