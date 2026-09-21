"""실사용자 계측 완결성 검사.

2026-09-21 배치에서 실사용자 이벤트는 전체의 0.011%(158/1,375,364)인데 Q5 실패
4건 중 3건이 거기서 나왔다. 합성이 99.99%라 실사용자 결함이 평균에 묻히고,
그나마 보인 것도 표본이 작아 분모가 우연히 뒤집힌 덕분이었다.

**사용자 행동이 아니라 계측을 본다.** 링크 공유·북마크로 상세에 바로 들어오는
것은 정상이고 오히려 흔한 경로다. 막는 것은 그 진입이 로그에 짝을 안 남기는 것이다.
"""

import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import (
    _real_user_detail_entries_without_impression,
    _real_user_unmatched_clicks,
)

SCHEMA = (
    "event_date_kst string, brand_id string, session_id string, "
    "product_id string, recommendation_id string, list_id string, "
    "event_name string, actor_type string"
)

DATE = "2026-09-21"


def _row(session, event, actor="user", brand="B1", product="P1",
         recommendation=None, list_id="grid"):
    return (DATE, brand, session, product, recommendation, list_id, event, actor)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class RealUserInstrumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("real-user-instrumentation-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _fact(self, rows):
        return self.spark.createDataFrame(rows, SCHEMA)

    # ── 상세 진입 ────────────────────────────────────────────────────
    def test_detail_entry_without_any_impression_is_reported(self):
        """링크로 바로 들어와 노출 Event 가 하나도 없는 세션."""
        result = _real_user_detail_entries_without_impression(
            self._fact([_row("S1", "product_view")])
        )

        self.assertEqual({"total": 1, "without_impression": 1}, result)

    def test_synthesised_impression_makes_the_entry_pass(self):
        """화면이 노출을 보강하면 통과한다 — 직접 진입을 막는 검사가 아니다."""
        result = _real_user_detail_entries_without_impression(
            self._fact([
                _row("S1", "product_impression"),
                _row("S1", "product_view"),
            ])
        )

        self.assertEqual({"total": 1, "without_impression": 0}, result)

    def test_any_of_the_three_impression_events_counts(self):
        """노출은 셋이다. 추천·배너로만 보인 세션도 계측된 것이다 (§4.1)."""
        result = _real_user_detail_entries_without_impression(
            self._fact([
                _row("S1", "recommendation_impression"),
                _row("S1", "product_view"),
                _row("S2", "banner_impression"),
                _row("S2", "quick_look"),
            ])
        )

        self.assertEqual({"total": 2, "without_impression": 0}, result)

    def test_quick_look_is_a_detail_entry(self):
        result = _real_user_detail_entries_without_impression(
            self._fact([_row("S1", "quick_look")])
        )

        self.assertEqual({"total": 1, "without_impression": 1}, result)

    def test_synthetic_traffic_is_out_of_scope(self):
        """생성기는 direct 진입을 의도적으로 만든다. 같은 불변식을 걸 수 없다."""
        result = _real_user_detail_entries_without_impression(
            self._fact([_row("S1", "product_view", actor="synthetic")])
        )

        self.assertEqual({"total": 0, "without_impression": 0}, result)

    def test_impression_for_another_brand_does_not_cover_the_entry(self):
        """비율의 grain 이 날짜·브랜드·세션이라 브랜드를 넘겨 덮지 못한다."""
        result = _real_user_detail_entries_without_impression(
            self._fact([
                _row("S1", "product_impression", brand="B1"),
                _row("S1", "product_view", brand="B2"),
            ])
        )

        self.assertEqual(1, result["without_impression"])

    # ── 클릭 ─────────────────────────────────────────────────────────
    def test_recommendation_click_with_a_fresh_id_is_reported(self):
        """노출은 있는데 클릭이 새 recommendation_id 를 달고 나간 경우."""
        result = _real_user_unmatched_clicks(self._fact([
            _row("S1", "recommendation_impression",
                 recommendation="R1", list_id="promo_pick"),
            _row("S1", "recommendation_click",
                 recommendation="R2", list_id="promo_pick"),
        ]))

        self.assertEqual(1, result["recommendation_unmatched"])
        self.assertEqual(1, result["recommendation_total"])

    def test_recommendation_click_reusing_the_id_passes(self):
        result = _real_user_unmatched_clicks(self._fact([
            _row("S1", "recommendation_impression",
                 recommendation="R1", list_id="promo_pick"),
            _row("S1", "recommendation_click",
                 recommendation="R1", list_id="promo_pick"),
        ]))

        self.assertEqual(0, result["recommendation_unmatched"])

    def test_product_click_without_impression_is_reported(self):
        """전체 product_click 은 비율 경고라 실사용자 몫이 묻힌다. 여기서 센다."""
        result = _real_user_unmatched_clicks(
            self._fact([_row("S1", "product_click")])
        )

        self.assertEqual(1, result["product_unmatched"])

    def test_synthetic_clicks_are_out_of_scope(self):
        result = _real_user_unmatched_clicks(self._fact([
            _row("S1", "recommendation_click",
                 recommendation="R2", actor="synthetic"),
            _row("S1", "product_click", actor="synthetic"),
        ]))

        self.assertEqual(0, result["recommendation_unmatched"])
        self.assertEqual(0, result["product_unmatched"])


if __name__ == "__main__":
    unittest.main()
