"""E6 마찰·이탈·유입 Mart. 실데이터가 밟지 않는 경계를 고정한다.

재생 데이터는 `dead_click` 이 0건이고 `rage_click` 은 전부 시드라, 마찰이 실제로
집계되는 경로가 `scroll_backtrack` 하나뿐이다. 시드 혼입·분모 0·동률 진입 경로처럼
실행에서 안 나오는 조합은 여기서만 잡힌다.
"""
import unittest
from datetime import date, datetime

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    ENTRY_SOURCES,
    ENTRY_SOURCE_EVENTS,
    FRICTION_EVENTS,
    QUICK_EXIT_MS,
    _entry_source_daily,
    _exit_daily,
    _friction_daily,
)


SESSION_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "event_name string, properties_json string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

FUNNEL_SCHEMA = (
    "brand_id string, product_id string, session_id string, "
    "first_product_view_at timestamp, first_quick_look_at timestamp, "
    "reached_detail_view boolean, reached_product_view boolean, "
    "reached_add_to_cart boolean, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string"
)

FACT_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "event_name string, entry_source string, event_time timestamp, event_id string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

# KST 2026-09-08 12:00 을 UTC 로 적은 값.
VIEW_AT = datetime(2026, 9, 8, 3, 0, 0)


class FrictionVocabularyTest(unittest.TestCase):
    def test_friction_events_are_the_three_ui_signals(self):
        """상품 선호가 아니라 UI 마찰이다. 전환 Event 가 섞이면 뜻이 달라진다."""
        self.assertEqual(
            ("rage_click", "dead_click", "scroll_backtrack"), FRICTION_EVENTS
        )

    def test_entry_source_events_exclude_impression(self):
        """product_impression 에는 entry_source 가 없다 (실측 100,625건 중 0건)."""
        self.assertNotIn("product_impression", ENTRY_SOURCE_EVENTS)

    def test_quick_exit_threshold_matches_the_spec(self):
        self.assertEqual(3000, QUICK_EXIT_MS)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class FrictionMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("friction-mart-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    # ── 픽스처 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _friction(session, event_name, section="reviews", content_kind="user_review",
                  product="P1", brand="B1", seeded=False):
        # 값이 없으면 키 자체를 싣지 않는다. 실제 Event 가 그렇게 오고,
        # get_json_object 는 없는 키에 NULL 을 낸다.
        pairs = [('"section_id": "%s"' % section) if section else None,
                 ('"content_kind": "%s"' % content_kind) if content_kind else None]
        properties = "{%s}" % ", ".join(p for p in pairs if p)
        return (
            date(2026, 9, 8), brand, product, session, event_name, properties,
            "user", "web", None, None, None, seeded,
        )

    @staticmethod
    def _exit(session, dwell_ms, seeded=False):
        return (
            date(2026, 9, 8), None, None, session, "exit_summary",
            '{"dwell_ms": %d}' % dwell_ms,
            "user", "web", None, None, None, seeded,
        )

    @staticmethod
    def _session(session, product="P1", brand="B1", cart=False, viewed=True,
                 quick_look_only=False):
        return (
            brand, product, session,
            None if quick_look_only else VIEW_AT,
            VIEW_AT if quick_look_only else None,
            True, not quick_look_only, cart,
            "user", "web", None, None, None,
        )

    @staticmethod
    def _entry(session, entry_source, event_name="product_click", product="P1",
               brand="B1", second=0, event_id="E1", seeded=False):
        return (
            date(2026, 9, 8), brand, product, session, event_name, entry_source,
            datetime(2026, 9, 8, 3, 0, second), event_id,
            "user", "web", None, None, None, seeded,
        )

    def _events(self, rows):
        return self.spark.createDataFrame(rows, SESSION_SCHEMA)

    def _funnel(self, rows):
        return self.spark.createDataFrame(rows, FUNNEL_SCHEMA)

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    # ── friction_daily ─────────────────────────────────────────────────────
    def test_every_location_keeps_a_row_per_friction_event(self):
        """dead_click 은 생성기가 만들지 않아 항상 0이다. 행은 남아야 한다 (§4.21)."""
        events = self._events([self._friction("S1", "scroll_backtrack")])
        funnel = self._funnel([self._session("S1")])

        rows = {r["event_name"]: r for r in
                _friction_daily(events, funnel, "Asia/Seoul").collect()}

        self.assertEqual(set(FRICTION_EVENTS), set(rows))
        self.assertEqual(1, rows["scroll_backtrack"]["event_count"])
        self.assertEqual(0, rows["dead_click"]["event_count"])
        self.assertEqual(0, rows["dead_click"]["friction_sessions"])
        self.assertEqual(0.0, rows["dead_click"]["friction_rate"])

    def test_seeded_friction_is_excluded(self):
        """부정 시드가 rage_click 을 직접 낸다. 재생 데이터 43건이 전부 시드다."""
        events = self._events([
            self._friction("S1", "rage_click", seeded=True),
            self._friction("S2", "scroll_backtrack"),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        rows = {r["event_name"]: r for r in
                _friction_daily(events, funnel, "Asia/Seoul").collect()}

        self.assertEqual(0, rows["rage_click"]["event_count"])
        self.assertEqual(1, rows["scroll_backtrack"]["event_count"])

    def test_repeated_friction_counts_events_and_sessions_apart(self):
        events = self._events([
            self._friction("S1", "scroll_backtrack"),
            self._friction("S1", "scroll_backtrack"),
            self._friction("S2", "scroll_backtrack"),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        row = next(r for r in _friction_daily(events, funnel, "Asia/Seoul").collect()
                   if r["event_name"] == "scroll_backtrack")

        self.assertEqual(3, row["event_count"])
        self.assertEqual(2, row["friction_sessions"])

    def test_denominator_is_the_detail_view_sessions(self):
        """분모는 상세 ∪ 퀵룩이다 (§6-6). 퀵룩만 연 세션도 들어간다."""
        events = self._events([self._friction("S1", "scroll_backtrack")])
        funnel = self._funnel([
            self._session("S1"),
            self._session("S2", quick_look_only=True),
        ])

        row = next(r for r in _friction_daily(events, funnel, "Asia/Seoul").collect()
                   if r["event_name"] == "scroll_backtrack")

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(0.5, row["friction_rate"])

    def test_rate_is_null_when_no_detail_view_exists(self):
        events = self._events([self._friction("S1", "scroll_backtrack")])
        funnel = self._funnel([self._session("S9", product="P9")])

        row = next(r for r in _friction_daily(events, funnel, "Asia/Seoul").collect()
                   if r["event_name"] == "scroll_backtrack")

        self.assertEqual(0, row["detail_view_sessions"])
        self.assertIsNone(row["friction_rate"])

    def test_missing_content_kind_is_kept_as_its_own_location(self):
        """content_kind 는 실측 67% 만 실린다. 결측을 버리면 마찰이 사라진다."""
        events = self._events([
            self._friction("S1", "scroll_backtrack", content_kind=None),
            self._friction("S2", "scroll_backtrack", content_kind="user_review"),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        rows = [r for r in _friction_daily(events, funnel, "Asia/Seoul").collect()
                if r["event_name"] == "scroll_backtrack"]

        self.assertEqual(2, len(rows))
        self.assertIn(None, [r["content_kind"] for r in rows])

    def test_friction_grain_is_unique(self):
        events = self._events([
            self._friction("S1", "scroll_backtrack", section="reviews"),
            self._friction("S2", "scroll_backtrack", section="ingredients"),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        result = _friction_daily(events, funnel, "Asia/Seoul")
        key = [
            "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
            "event_name", "actor_type", "source", "generator_type", "scenario_id",
            "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())

    # ── exit_daily ─────────────────────────────────────────────────────────
    def test_quick_exit_uses_the_three_second_threshold(self):
        events = self._events([
            self._exit("S1", 2999),
            self._exit("S2", 3000),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        row = _exit_daily(events, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(2, row["exit_summary_sessions"])
        self.assertEqual(1, row["quick_exit_sessions"])
        self.assertEqual(0.5, row["quick_exit_rate"])

    def test_longest_dwell_decides_the_session(self):
        """어느 페이지에도 오래 머물지 않았을 때만 조기 이탈이다 (§4.22)."""
        events = self._events([
            self._exit("S1", 500),
            self._exit("S1", 9000),
        ])
        funnel = self._funnel([self._session("S1")])

        row = _exit_daily(events, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(0, row["quick_exit_sessions"])

    def test_sessions_without_exit_summary_stay_in_the_denominator(self):
        """기록이 없는 것은 "빨리 안 나갔다" 가 아니다. 두 값을 따로 낸다 (§4.22)."""
        events = self._events([self._exit("S1", 100)])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        row = _exit_daily(events, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["exit_summary_sessions"])
        self.assertEqual(1, row["quick_exit_sessions"])
        self.assertEqual(0.5, row["quick_exit_rate"])

    def test_exit_is_attributed_to_every_product_the_session_opened(self):
        """exit_summary 는 세션 단위라 상품이 없다. 상품 축 합산은 세션을 부풀린다."""
        events = self._events([self._exit("S1", 100)])
        funnel = self._funnel([
            self._session("S1", product="P1"),
            self._session("S1", product="P2"),
        ])

        rows = _exit_daily(events, funnel, "Asia/Seoul").collect()

        self.assertEqual(2, len(rows))
        self.assertTrue(all(r["quick_exit_sessions"] == 1 for r in rows))

    def test_seeded_exit_summary_is_excluded(self):
        events = self._events([
            self._exit("S1", 100, seeded=True),
            self._exit("S2", 100),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        row = _exit_daily(events, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["exit_summary_sessions"])

    # ── entry_source_daily ─────────────────────────────────────────────────
    def test_first_entry_decides_the_session_path(self):
        """같은 세션·상품에 경로가 둘이면 첫 진입으로 정한다 (§4.23)."""
        facts = self._facts([
            self._entry("S1", "similar_products", second=5, event_id="E2"),
            self._entry("S1", "list_grid", second=1, event_id="E1"),
        ])
        funnel = self._funnel([self._session("S1")])

        rows = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()

        self.assertEqual(1, len(rows))
        self.assertEqual("list_grid", rows[0]["entry_source"])

    def test_ties_break_on_event_id(self):
        """동률 규칙이 없으면 실행마다 판정이 흔들려 재계산 결정성이 깨진다."""
        facts = self._facts([
            self._entry("S1", "similar_products", second=1, event_id="E9"),
            self._entry("S1", "promo_pick", second=1, event_id="E1"),
        ])
        funnel = self._funnel([self._session("S1")])

        rows = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()

        self.assertEqual("promo_pick", rows[0]["entry_source"])

    def test_cart_denominator_is_the_detail_view_sessions(self):
        """퀵룩으로만 연 세션도 분모다. 아니면 비율이 1.0 을 넘는다 (§6-6)."""
        facts = self._facts([
            self._entry("S1", "list_grid"),
            self._entry("S2", "list_grid", event_name="quick_look"),
        ])
        funnel = self._funnel([
            self._session("S1", cart=False),
            self._session("S2", cart=True, quick_look_only=True),
        ])

        row = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        self.assertEqual(0.5, row["view_to_cart_rate"])

    def test_unknown_entry_source_is_dropped(self):
        """어휘집(§3.3) 밖 값은 내지 않는다."""
        facts = self._facts([
            self._entry("S1", "mystery_source"),
            self._entry("S2", "list_grid"),
        ])
        funnel = self._funnel([self._session("S1"), self._session("S2")])

        rows = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()

        self.assertEqual(["list_grid"], [r["entry_source"] for r in rows])
        self.assertTrue(all(r["entry_source"] in ENTRY_SOURCES for r in rows))

    def test_seeded_entries_are_excluded(self):
        facts = self._facts([
            self._entry("S1", "list_grid", seeded=True),
            self._entry("S2", "list_grid"),
        ])
        funnel = self._funnel([
            self._session("S1", cart=True), self._session("S2", cart=False),
        ])

        row = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()[0]

        self.assertEqual(1, row["detail_view_sessions"])
        self.assertEqual(0, row["add_to_cart_sessions"])

    def test_product_is_not_in_the_grain(self):
        """브랜드 단위 세션 dedup 이다. 상품을 두면 브랜드로 합산할 수 없다 (§4.23)."""
        facts = self._facts([
            self._entry("S1", "list_grid", product="P1"),
            self._entry("S1", "list_grid", product="P2"),
        ])
        funnel = self._funnel([
            self._session("S1", product="P1"),
            self._session("S1", product="P2"),
        ])

        rows = _entry_source_daily(facts, funnel, "Asia/Seoul").collect()

        self.assertEqual(1, len(rows))
        self.assertNotIn("product_id", rows[0].asDict())
        self.assertEqual(1, rows[0]["detail_view_sessions"])

    def test_entry_grain_is_unique(self):
        facts = self._facts([
            self._entry("S1", "list_grid"),
            self._entry("S2", "promo_pick", product="P2"),
        ])
        funnel = self._funnel([
            self._session("S1"), self._session("S2", product="P2"),
        ])

        result = _entry_source_daily(facts, funnel, "Asia/Seoul")
        key = [
            "event_date_kst", "brand_id", "entry_source", "actor_type", "source",
            "generator_type", "scenario_id", "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())


if __name__ == "__main__":
    unittest.main()
