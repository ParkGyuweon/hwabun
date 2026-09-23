"""세션·날짜 경계에서 깨지던 grain 가정.

2026-09-22 운영 배치가 이 둘로 실패했다. 제품 결함이 아니라 집계·검사가 담고
있던 전제가 경계에서 성립하지 않은 것이다.

  funnel_session_grain_is_unique        8행 · 전부 actor_type='user'
  banner_daily_counts_and_ctr_are_valid 1행
"""

import unittest
from datetime import datetime

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import _build_funnel_session_fact
from streaming.jobs.validate_pipeline_job import _over_clicked_banner_count

STAGE_SCHEMA = (
    "session_id string, product_id string, user_id string, persona_id string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "actor_type string, source string, category_id string, brand_id string, "
    "event_name string, event_time timestamp"
)

BANNER_SCHEMA = (
    "event_date_kst string, brand_id string, product_id string, "
    "banner_type string, trait_source string, "
    "impression_count long, click_count long"
)

BANNER_IDENTITY = ["brand_id", "product_id", "banner_type", "trait_source"]


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
        """노출은 앞날, 클릭은 뒷날에 찍혀도 합치면 맞는다."""
        frame = self._banners([
            ("2026-09-19", "B1", "P1", "new_brand", "explore", 3, 2),
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1),
        ])

        self.assertEqual(0, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    def test_click_without_any_impression_is_reported(self):
        """어느 날에도 노출이 없으면 그대로 잡힌다."""
        frame = self._banners([
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1),
        ])

        self.assertEqual(1, _over_clicked_banner_count(frame, BANNER_IDENTITY))

    def test_other_banners_do_not_cover_the_gap(self):
        """다른 배너의 노출이 대신 메우지 않는다 — trait_source 가 다르면 별개다."""
        frame = self._banners([
            ("2026-09-20", "B1", "P1", "new_brand", "coldstart", 5, 5),
            ("2026-09-20", "B1", "P1", "new_brand", "explore", 0, 1),
        ])

        self.assertEqual(1, _over_clicked_banner_count(frame, BANNER_IDENTITY))


if __name__ == "__main__":
    unittest.main()
