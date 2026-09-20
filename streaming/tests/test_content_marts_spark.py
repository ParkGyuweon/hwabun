"""E3 콘텐츠 Mart 3종. 실데이터가 밟지 않는 경계를 고정한다.

재생 데이터는 상품 조회가 늘 콘텐츠보다 많고 시드도 콘텐츠 Event 를 거의 내지
않는다. 분모 0·행동 0건·시드 혼입처럼 실행에서 안 나오는 조합은 여기서만 잡힌다.
"""
import unittest
from datetime import date, datetime

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    CONVERSION_BEHAVIOR_EVENTS,
    INGREDIENT_CONTENT_KINDS,
    INFORMATION_CONTENT_KINDS,
    REVIEW_CONTENT_KINDS,
    _behavior_conversion_daily,
    _content_conversion_daily,
    _content_daily_kpi,
)


CONTENT_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, category_id string, "
    "section_id string, content_kind string, session_id string, "
    "view_count bigint, dwell_ms_sum bigint, co_visible_le2_dwell_ms_sum bigint, "
    "accordion_expand_count bigint, "
    "text_select_count bigint, text_copy_count bigint, "
    "matched_ingredients array<string>, content_interest_score double, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

FUNNEL_SCHEMA = (
    "brand_id string, product_id string, session_id string, "
    "first_product_view_at timestamp, reached_product_view boolean, "
    "reached_add_to_cart boolean, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string"
)

SESSION_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "event_name string, actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

# KST 2026-09-08 12:00 을 UTC 로 적은 값. funnel_session_fact 는 UTC 로 저장되고
# Mart 가 KST 로 되돌린다.
VIEW_AT = datetime(2026, 9, 8, 3, 0, 0)


class ContentKindVocabularyTest(unittest.TestCase):
    """성분·리뷰 묶음이 §4.14 의 정보 확인 묶음과 갈라지면 두 Mart 가 어긋난다."""

    def test_ingredient_and_review_kinds_partition_the_information_kinds(self):
        self.assertEqual(
            set(INFORMATION_CONTENT_KINDS),
            set(INGREDIENT_CONTENT_KINDS) | set(REVIEW_CONTENT_KINDS),
        )

    def test_the_two_groups_do_not_overlap(self):
        self.assertEqual(
            set(), set(INGREDIENT_CONTENT_KINDS) & set(REVIEW_CONTENT_KINDS)
        )


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class ContentMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("content-mart-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    # ── 픽스처 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _content(session, content_kind, product="P1", brand="B1",
                 section="details", dwell=1000, seeded=False, views=1,
                 clean_dwell=None):
        # clean_dwell 을 안 주면 전액이 겹침 없는 체류다. 대부분의 테스트가
        # 겹침을 다루지 않으므로 그쪽 기대값을 흔들지 않는다.
        return (
            date(2026, 9, 8), brand, product, "C1", section, content_kind, session,
            views, dwell, dwell if clean_dwell is None else clean_dwell,
            0, 0, 0, ["retinol"], 1.5,
            "user", "web", None, None, None, seeded,
        )

    @staticmethod
    def _session(session, product="P1", brand="B1", cart=False, viewed=True):
        return (
            brand, product, session, VIEW_AT if viewed else None, viewed, cart,
            "user", "web", None, None, None,
        )

    @staticmethod
    def _event(session, event_name, product="P1", brand="B1", seeded=False):
        return (
            date(2026, 9, 8), brand, product, session, event_name,
            "user", "web", None, None, None, seeded,
        )

    def _content_df(self, rows):
        return self.spark.createDataFrame(rows, CONTENT_SCHEMA)

    def _funnel_df(self, rows):
        return self.spark.createDataFrame(rows, FUNNEL_SCHEMA)

    def _session_df(self, rows):
        return self.spark.createDataFrame(rows, SESSION_SCHEMA)

    # ── content_daily_kpi ──────────────────────────────────────────────────
    def test_platform_sections_are_excluded(self):
        """product_id 가 NULL 인 목록 섹션은 상품 KPI 에 섞이지 않는다 (§4.4).

        재생 데이터에서 content_interest_fact 의 67% 가 이 행이다.
        """
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S2", "recommendation_card", product=None),
        ])
        funnel = self._funnel_df([self._session("S1")])

        result = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()

        self.assertEqual(1, len(result))
        self.assertEqual("P1", result[0]["product_id"])

    def test_seeded_content_is_excluded(self):
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S2", "user_review", seeded=True),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        result = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()

        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0]["section_view_sessions"])

    def test_denominator_repeats_across_content_kinds(self):
        """상품 단위 분모라 content_kind 마다 같은 값이어야 한다 (§4.4).

        행 단위로 세면 user_review 행이 ingredient_view_sessions=0 을 달고 나와
        "아무도 성분을 안 봤다" 로 읽힌다.
        """
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S1", "ingredient_list"),
        ])
        funnel = self._funnel_df([self._session("S1")])

        result = {r["content_kind"]: r for r in
                  _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()}

        self.assertEqual(2, len(result))
        for content_kind in ("user_review", "ingredient_list"):
            row = result[content_kind]
            self.assertEqual(1, row["product_view_sessions"], content_kind)
            self.assertEqual(1, row["ingredient_view_sessions"], content_kind)
            self.assertEqual(1, row["review_view_sessions"], content_kind)

    def test_ingredient_rate_cannot_exceed_one(self):
        """분자를 분모 모집단으로 제한한다 (§4.4).

        Quick Look 으로 상세를 연 세션은 콘텐츠를 읽고도 퍼널의 product_view 에
        없다. 제한하지 않으면 비율이 1.0 을 넘는다 — 실제로 났던
        분자·분모 모집단 불일치와 같은 유형이다.
        """
        rows = self._content_df([
            self._content("S1", "ingredient_list"),
            # 퍼널에 상품 조회가 없는 세션. 분자에도 들어가면 안 된다.
            self._content("S2", "ingredient_list"),
        ])
        funnel = self._funnel_df([self._session("S1")])

        row = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(2, row["section_view_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["ingredient_view_sessions"])
        self.assertEqual(1.0, row["ingredient_view_rate"])

    def test_rates_are_null_when_no_product_view_exists(self):
        """퍼널에 상품 조회가 없으면 분모가 0이다. 비율은 NULL, 건수는 0."""
        rows = self._content_df([self._content("S1", "user_review")])
        funnel = self._funnel_df([self._session("S9", viewed=False)])

        row = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(0, row["product_view_sessions"])
        self.assertIsNone(row["avg_dwell_ms_per_session"])
        self.assertIsNone(row["review_view_rate"])

    def test_dwell_comes_from_content_interest_only(self):
        """같은 세션의 여러 조회는 합산되지만 원천은 하나다 (§4.4)."""
        rows = self._content_df([
            self._content("S1", "user_review", dwell=1000, views=2),
            self._content("S2", "user_review", dwell=3000, views=1),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        row = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(4000, row["dwell_ms_sum"])
        self.assertEqual(3, row["section_view_count"])
        self.assertEqual(2, row["section_view_sessions"])
        self.assertEqual(2000.0, row["avg_dwell_ms_per_session"])

    def test_sessions_without_a_view_are_not_counted_as_viewers(self):
        """조회 없이 체류·드래그만 남긴 세션은 "본 세션" 이 아니다.

        세면 section_view_sessions > section_view_count 가 되어 화면에 "본 사람이
        조회 수보다 많다" 가 뜬다. 운영 마트에서 성분 줄이 조회 23,285 · 세션
        26,715 로 나온 것이 이 모양이다 (§4.4).
        """
        rows = self._content_df([
            self._content("S1", "ingredient_list", views=1),
            self._content("S2", "ingredient_list", views=0),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        row = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["section_view_count"])
        self.assertEqual(1, row["section_view_sessions"])
        self.assertLessEqual(
            row["section_view_sessions"], row["section_view_count"]
        )

    def test_matched_ingredients_are_counted_not_listed(self):
        rows = self._content_df([self._content("S1", "ingredient_list")])
        funnel = self._funnel_df([self._session("S1")])

        row = _content_daily_kpi(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["matched_ingredient_count"])

    def test_grain_is_unique(self):
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S2", "user_review"),
            self._content("S1", "ingredient_list"),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        result = _content_daily_kpi(rows, funnel, "Asia/Seoul")
        key = [
            "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
            "actor_type", "source", "generator_type", "scenario_id",
            "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())

    # ── content_conversion_daily ───────────────────────────────────────────
    def test_conversion_denominator_is_the_viewing_sessions(self):
        """분모가 §4.4 와 다르다. 그래서 Mart 를 나눴다 (§4.19)."""
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S2", "user_review"),
        ])
        funnel = self._funnel_df([
            self._session("S1", cart=True),
            self._session("S2", cart=False),
            # 콘텐츠를 안 본 세션은 분모에 들어가지 않는다
            self._session("S3", cart=True),
        ])

        row = _content_conversion_daily(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(2, row["viewed_sessions"])
        self.assertEqual(1, row["viewed_cart_sessions"])
        self.assertEqual(0.5, row["viewed_cart_rate"])

    def test_cart_must_be_for_the_same_product(self):
        """다른 상품을 담은 것은 이 콘텐츠의 효과가 아니다 (§4.19)."""
        rows = self._content_df([self._content("S1", "user_review", product="P1")])
        funnel = self._funnel_df([
            self._session("S1", product="P1", cart=False),
            self._session("S1", product="P2", cart=True),
        ])

        row = _content_conversion_daily(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["viewed_sessions"])
        self.assertEqual(0, row["viewed_cart_sessions"])

    def test_conversion_drops_unknown_content_kind(self):
        rows = self._content_df([
            self._content("S1", None),
            self._content("S2", "user_review"),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        result = _content_conversion_daily(rows, funnel, "Asia/Seoul").collect()

        self.assertEqual(["user_review"], [r["content_kind"] for r in result])

    def test_conversion_excludes_seeded_sessions(self):
        rows = self._content_df([
            self._content("S1", "user_review"),
            self._content("S2", "user_review", seeded=True),
        ])
        funnel = self._funnel_df([
            self._session("S1", cart=False), self._session("S2", cart=True),
        ])

        row = _content_conversion_daily(rows, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["viewed_sessions"])
        self.assertEqual(0, row["viewed_cart_sessions"])

    # ── behavior_conversion_daily ──────────────────────────────────────────
    def test_both_populations_sum_to_the_universe(self):
        """이 Mart 의 불변식이다 (§4.20). 한쪽만 세면 대조가 성립하지 않는다."""
        events = self._session_df([self._event("S1", "accordion_toggle")])
        funnel = self._funnel_df([
            self._session("S1", cart=True),
            self._session("S2", cart=False),
            self._session("S3", cart=True),
        ])

        rows = _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()

        self.assertEqual(len(CONVERSION_BEHAVIOR_EVENTS), len(rows))
        for row in rows:
            with self.subTest(event_name=row["event_name"]):
                self.assertEqual(
                    3, row["done_sessions"] + row["not_done_sessions"]
                )

    def test_rates_split_by_behaviour(self):
        events = self._session_df([self._event("S1", "accordion_toggle")])
        funnel = self._funnel_df([
            self._session("S1", cart=True),
            self._session("S2", cart=False),
        ])

        row = next(
            r for r in _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()
            if r["event_name"] == "accordion_toggle"
        )

        self.assertEqual(1, row["done_sessions"])
        self.assertEqual(1, row["done_cart_sessions"])
        self.assertEqual(1.0, row["done_cart_rate"])
        self.assertEqual(1, row["not_done_sessions"])
        self.assertEqual(0, row["not_done_cart_sessions"])
        self.assertEqual(0.0, row["not_done_cart_rate"])

    def test_events_with_no_occurrence_keep_a_row(self):
        """"아무도 안 했다" 와 "집계하지 않는다" 를 구분한다 (§4.20).

        재생 데이터의 text_copy 가 128 세션뿐이라 실제로 밟는 경우다.
        """
        events = self._session_df([self._event("S1", "accordion_toggle")])
        funnel = self._funnel_df([self._session("S1", cart=True)])

        rows = {
            r["event_name"]: r for r in
            _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()
        }

        self.assertEqual(set(CONVERSION_BEHAVIOR_EVENTS), set(rows))
        self.assertEqual(0, rows["text_copy"]["done_sessions"])
        self.assertIsNone(rows["text_copy"]["done_cart_rate"])
        self.assertEqual(1, rows["text_copy"]["not_done_sessions"])

    def test_repeated_behaviour_counts_once(self):
        """재는 것은 빈도가 아니라 여부다 (§4.20)."""
        events = self._session_df([
            self._event("S1", "accordion_toggle"),
            self._event("S1", "accordion_toggle"),
            self._event("S1", "accordion_toggle"),
        ])
        funnel = self._funnel_df([self._session("S1", cart=True)])

        row = next(
            r for r in _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()
            if r["event_name"] == "accordion_toggle"
        )

        self.assertEqual(1, row["done_sessions"])

    def test_unrelated_events_are_ignored(self):
        events = self._session_df([
            self._event("S1", "product_view"),
            self._event("S1", "add_to_cart"),
        ])
        funnel = self._funnel_df([self._session("S1", cart=True)])

        rows = _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()

        self.assertTrue(all(row["done_sessions"] == 0 for row in rows))

    def test_seeded_behaviour_does_not_count_as_done(self):
        """시드는 관측된 행동이 아니다. done 이 아니라 not_done 으로 간다."""
        events = self._session_df([
            self._event("S1", "accordion_toggle", seeded=True),
        ])
        funnel = self._funnel_df([self._session("S1", cart=True)])

        row = next(
            r for r in _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()
            if r["event_name"] == "accordion_toggle"
        )

        self.assertEqual(0, row["done_sessions"])
        self.assertEqual(1, row["not_done_sessions"])

    def test_behaviour_without_a_product_view_is_dropped(self):
        """모집단은 퍼널이 정한다. 행동만 있는 세션은 들어오지 않는다."""
        events = self._session_df([self._event("S9", "accordion_toggle")])
        funnel = self._funnel_df([self._session("S1", cart=False)])

        row = next(
            r for r in _behavior_conversion_daily(events, funnel, "Asia/Seoul").collect()
            if r["event_name"] == "accordion_toggle"
        )

        self.assertEqual(0, row["done_sessions"])
        self.assertEqual(1, row["not_done_sessions"])

    def test_behavior_grain_is_unique(self):
        events = self._session_df([
            self._event("S1", "accordion_toggle"),
            self._event("S2", "text_copy", product="P2"),
        ])
        funnel = self._funnel_df([
            self._session("S1"), self._session("S2", product="P2"),
        ])

        result = _behavior_conversion_daily(events, funnel, "Asia/Seoul")
        key = [
            "event_date_kst", "brand_id", "product_id", "event_name",
            "actor_type", "source", "generator_type", "scenario_id",
            "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())


    # ── 겹침 제외 체류 ──────────────────────────────────────
    def test_co_visible_sum_is_aggregated_alongside_the_total(self):
        """총합과 겹침 제외 합계를 나란히 낸다. 총합을 대체하지 않는다 (§4.4)."""
        content = self._content_df([
            self._content("S1", "ingredient", dwell=1000, clean_dwell=400),
            self._content("S2", "ingredient", dwell=500, clean_dwell=500),
        ])
        funnel = self._funnel_df([self._session("S1"), self._session("S2")])

        row = _content_daily_kpi(content, funnel, "Asia/Seoul").first()

        self.assertEqual(1500, row["dwell_ms_sum"])
        self.assertEqual(900, row["co_visible_le2_dwell_ms_sum"])

    def test_co_visible_sum_never_exceeds_the_total(self):
        """겹침을 걷어낸 몫이라 총합을 넘을 수 없다. Q5 가 보는 불변식이다."""
        content = self._content_df([
            self._content("S1", "ingredient", dwell=1000, clean_dwell=0),
        ])
        funnel = self._funnel_df([self._session("S1")])

        row = _content_daily_kpi(content, funnel, "Asia/Seoul").first()

        self.assertEqual(0, row["co_visible_le2_dwell_ms_sum"])
        self.assertLessEqual(
            row["co_visible_le2_dwell_ms_sum"], row["dwell_ms_sum"]
        )

    def test_seeded_content_is_excluded_from_the_co_visible_sum(self):
        """시드는 관측이 아니다. 새 컬럼도 같은 규칙을 따라야 한다 (§4.0)."""
        content = self._content_df([
            self._content("S1", "ingredient", dwell=1000, clean_dwell=1000),
            self._content("S2", "ingredient", dwell=800, clean_dwell=800,
                          seeded=True),
        ])
        funnel = self._funnel_df([self._session("S1")])

        row = _content_daily_kpi(content, funnel, "Asia/Seoul").first()

        self.assertEqual(1000, row["co_visible_le2_dwell_ms_sum"])


    # ── 성분·리뷰 세션의 0 채우기 ───────────────────────────
    def test_non_matching_content_kinds_report_zero_not_null(self):
        """cta·price 같은 행은 성분 집계에 짝이 없어 조인이 NULL 을 낸다.

        계약이 N 으로 선언했고, "그 종류가 아니라 성분 열람이 0" 이 맞는
        뜻이다. NULL 로 두면 rate 도 NULL 이 되어 분모 0 과 구분되지 않는다
        (§4.4). 104만 건 재생에서 193행이 이 상태였다.
        """
        content = self._content_df([self._content("S1", "cta")])
        funnel = self._funnel_df([self._session("S1")])

        row = _content_daily_kpi(content, funnel, "Asia/Seoul").first()

        self.assertEqual("cta", row["content_kind"])
        self.assertEqual(0, row["ingredient_view_sessions"])
        self.assertEqual(0, row["review_view_sessions"])
        self.assertEqual(0.0, row["ingredient_view_rate"])


if __name__ == "__main__":
    unittest.main()
