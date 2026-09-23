"""상품 진단·고객군 콘텐츠 Mart. 실데이터가 밟지 않는 경계를 고정한다.

재생 데이터의 페르소나 1,000명이 전원 `combination` 이라 세그먼트 축이 한 칸만
찬다. 여러 타입이 섞였을 때의 share 분모, persona 미귀속, section_dwell_agg 에
is_seeded 가 없다는 함정은 여기서만 잡힌다.
"""
import itertools
import unittest
from datetime import date, datetime, timedelta

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    MISSING_SEGMENT_VALUES,
    OPEN_DETAIL_CLOSE_REASON,
    _product_daily_kpi,
    _product_exit_daily,
    _segment_content_daily,
    _seeded_session_ids,
)


SESSION_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "event_id string, event_time timestamp, properties_json string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

DWELL_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "persona_id string, content_kind string, dwell_ms_sum bigint, "
    "co_visible_le2_dwell_ms_sum bigint, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string"
)

BRIDGE_SCHEMA = "persona_id string, segment_type string, segment_value string"

FACT_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, category_id string, "
    "session_id string, user_id string, event_name string, close_reason string, "
    "action string, navigation_source string, "
    "purchase_quantity int, order_id string, item_revenue decimal(18,2), "
    "currency string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean, "
    # 재조회 판정이 세션·상품 안의 Event 순서를 본다 (`_with_revisit_flag`).
    "event_id string, event_time timestamp"
)

# Event 순서는 `_fact` 를 부른 순서다. 테스트가 적은 순서가 곧 일어난 순서다.
_EVENT_SEQ = itertools.count(1)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class DiagnosticMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("diagnostic-mart-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    # ── 픽스처 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _content(session, content_kind, second, event_id, product="P1", brand="B1",
                 seeded=False):
        properties = (
            '{"content_kind": "%s"}' % content_kind if content_kind else "{}"
        )
        return (
            date(2026, 9, 8), brand, product, session, event_id,
            datetime(2026, 9, 8, 3, 0, second), properties,
            "user", "web", None, None, None, seeded,
        )

    @staticmethod
    def _dwell(session, persona, content_kind, dwell_ms, product="P1", brand="B1",
               clean_dwell_ms=None):
        return (
            date(2026, 9, 8), brand, product, session, persona, content_kind, dwell_ms,
            dwell_ms if clean_dwell_ms is None else clean_dwell_ms,
            "user", "web", None, None, None,
        )

    @staticmethod
    def _bridge(persona, skin_type):
        return (persona, "skin_type", skin_type)

    @staticmethod
    def _fact(session, event_name, close_reason=None, product="P1", brand="B1",
              seeded=False, action=None, navigation_source=None, at=None):
        seq = next(_EVENT_SEQ)
        return (
            date(2026, 9, 8), brand, product, "C1", session, "U-" + session,
            event_name, close_reason, action, navigation_source,
            None, None, None, None,
            "user", "web", None, None, None, seeded,
            f"E{seq:06d}", at or datetime(2026, 9, 8) + timedelta(seconds=seq),
        )

    def _events(self, rows):
        return self.spark.createDataFrame(rows, SESSION_SCHEMA)

    def _dwells(self, rows):
        return self.spark.createDataFrame(rows, DWELL_SCHEMA)

    def _bridge_df(self, rows):
        return self.spark.createDataFrame(rows, BRIDGE_SCHEMA)

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    # ── product_daily_kpi 신규 컬럼 ────────────────────────────────────────
    def test_open_detail_is_counted_from_close_reason(self):
        """close_reason 은 product_event_fact 가 싣는다 (§4.1)."""
        facts = self._facts([
            self._fact("S1", "quick_look"),
            self._fact("S1", "quick_look_close", OPEN_DETAIL_CLOSE_REASON),
            self._fact("S2", "quick_look"),
            self._fact("S2", "quick_look_close", "backdrop"),
        ])

        row = _product_daily_kpi(facts).collect()[0]

        self.assertEqual(1, row["quick_look_close_open_detail_count"])
        self.assertEqual(2, row["quick_look_count"])

    def test_variant_select_counts_events_not_sessions(self):
        """옵션 왕복이 많다는 것 자체가 진단 신호다 (§4.1)."""
        facts = self._facts([
            self._fact("S1", "variant_select"),
            self._fact("S1", "variant_select"),
            self._fact("S1", "variant_select"),
        ])

        row = _product_daily_kpi(facts).collect()[0]

        self.assertEqual(3, row["variant_select_count"])

    def test_diagnostic_columns_do_not_change_the_grain(self):
        facts = self._facts([
            self._fact("S1", "product_view"),
            self._fact("S1", "variant_select"),
            self._fact("S2", "quick_look_close", OPEN_DETAIL_CLOSE_REASON),
        ])

        result = _product_daily_kpi(facts)

        self.assertEqual(1, result.count())

    def test_seeded_events_do_not_reach_the_diagnostic_columns(self):
        facts = self._facts([
            self._fact("S1", "variant_select", seeded=True),
            self._fact("S2", "variant_select"),
        ])

        row = _product_daily_kpi(facts).collect()[0]

        self.assertEqual(1, row["variant_select_count"])

    # ── product_exit_daily ────────────────────────────────────────────────
    def test_last_content_event_decides_the_exit_point(self):
        events = self._events([
            self._content("S1", "user_review", 1, "E1"),
            self._content("S1", "cta", 5, "E2"),
        ])

        rows = _product_exit_daily(events).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual("cta", rows[0]["last_content_kind"])
        self.assertEqual(1, rows[0]["exit_sessions"])

    def test_ties_break_on_event_id_ascending(self):
        """규칙이 없으면 실행마다 판정이 흔들려 재계산 결정성이 깨진다 (§4.24)."""
        events = self._events([
            self._content("S1", "price", 5, "E9"),
            self._content("S1", "cta", 5, "E1"),
        ])

        rows = _product_exit_daily(events).collect()

        self.assertEqual("cta", rows[0]["last_content_kind"])

    def test_one_exit_point_per_session_and_product(self):
        """세션·상품마다 행이 하나다. 합산이 부풀지 않는 근거다 (§4.24)."""
        events = self._events([
            self._content("S1", "cta", 1, "E1", product="P1"),
            self._content("S1", "price", 2, "E2", product="P1"),
            self._content("S1", "cta", 3, "E3", product="P2"),
        ])

        rows = _product_exit_daily(events).collect()

        self.assertEqual(2, sum(r["exit_sessions"] for r in rows))

    def test_events_without_content_kind_are_ignored(self):
        events = self._events([
            self._content("S1", None, 9, "E9"),
            self._content("S1", "cta", 1, "E1"),
        ])

        rows = _product_exit_daily(events).collect()

        self.assertEqual("cta", rows[0]["last_content_kind"])

    def test_seeded_sessions_are_excluded_from_exit_points(self):
        events = self._events([
            self._content("S1", "cta", 1, "E1", seeded=True),
            self._content("S2", "price", 1, "E2"),
        ])

        rows = _product_exit_daily(events).collect()

        self.assertEqual(["price"], [r["last_content_kind"] for r in rows])

    def test_exit_grain_is_unique(self):
        events = self._events([
            self._content("S1", "cta", 1, "E1"),
            self._content("S2", "cta", 1, "E2"),
            self._content("S3", "price", 1, "E3"),
        ])

        result = _product_exit_daily(events)
        key = [
            "event_date_kst", "brand_id", "product_id", "last_content_kind",
            "actor_type", "source", "generator_type", "scenario_id",
            "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())

    # ── segment_content_daily ─────────────────────────────────────────────
    def test_share_denominator_is_the_skin_type_total(self):
        """한 타입 안에서 share 합이 1 이다. 타입끼리 더하면 안 된다 (§4.25)."""
        dwells = self._dwells([
            self._dwell("S1", "PC-1", "user_review", 300),
            self._dwell("S2", "PC-1", "ingredient_list", 100),
            self._dwell("S3", "PC-2", "user_review", 50),
        ])
        bridge = self._bridge_df([
            self._bridge("PC-1", "dry"), self._bridge("PC-2", "oily"),
        ])
        events = self._events([])

        rows = {
            (r["skin_type"], r["content_kind"]): r
            for r in _segment_content_daily(dwells, events, bridge).collect()
        }

        self.assertEqual(0.75, rows[("dry", "user_review")]["dwell_share"])
        self.assertEqual(0.25, rows[("dry", "ingredient_list")]["dwell_share"])
        # 다른 타입은 자기 총합이 분모다
        self.assertEqual(1.0, rows[("oily", "user_review")]["dwell_share"])

    def test_shares_sum_to_one_within_a_skin_type(self):
        dwells = self._dwells([
            self._dwell("S1", "PC-1", "user_review", 300),
            self._dwell("S2", "PC-1", "ingredient_list", 100),
            self._dwell("S3", "PC-1", "cta", 100),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "dry")])

        rows = _segment_content_daily(dwells, self._events([]), bridge).collect()

        self.assertAlmostEqual(1.0, sum(r["dwell_share"] for r in rows))

    def test_sessions_without_a_persona_are_not_attributed(self):
        """임의 귀속은 없는 고객군을 만들어 낸다 (§4.25 규칙)."""
        dwells = self._dwells([
            self._dwell("S1", None, "user_review", 100),
            self._dwell("S2", "PC-1", "user_review", 100),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "dry")])

        rows = _segment_content_daily(dwells, self._events([]), bridge).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual(100, rows[0]["dwell_ms_sum"])

    def test_personas_missing_from_the_bridge_are_dropped(self):
        dwells = self._dwells([
            self._dwell("S1", "PC-UNKNOWN", "user_review", 100),
            self._dwell("S2", "PC-1", "user_review", 100),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "dry")])

        rows = _segment_content_daily(dwells, self._events([]), bridge).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual(["dry"], [r["skin_type"] for r in rows])

    def test_missing_segment_values_are_not_a_segment(self):
        """notSureST 는 값이 아니라 결측이다 (persona-schema.md §3)."""
        dwells = self._dwells([
            self._dwell("S1", "PC-1", "user_review", 100),
            self._dwell("S2", "PC-2", "user_review", 100),
        ])
        bridge = self._bridge_df([
            self._bridge("PC-1", "dry"),
            self._bridge("PC-2", MISSING_SEGMENT_VALUES[0]),
        ])

        rows = _segment_content_daily(dwells, self._events([]), bridge).collect()

        self.assertEqual(["dry"], [r["skin_type"] for r in rows])

    def test_seeded_sessions_are_removed_without_an_is_seeded_column(self):
        """section_dwell_agg 에는 is_seeded 가 없다. 세션 목록으로 빼야 한다.

        재생 데이터에 시드 세션 행이 993건 있어, 빼지 않으면 조용히 섞인다.
        """
        dwells = self._dwells([
            self._dwell("seed:run:PC-1:P1", "PC-1", "user_review", 900),
            self._dwell("S2", "PC-1", "user_review", 100),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "dry")])
        events = self._events([
            self._content("seed:run:PC-1:P1", "user_review", 1, "E1", seeded=True),
            self._content("S2", "user_review", 1, "E2"),
        ])

        self.assertNotIn("is_seeded", dwells.columns)

        rows = _segment_content_daily(dwells, events, bridge).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual(100, rows[0]["dwell_ms_sum"])

    def test_seeded_session_ids_come_from_the_flag_not_the_prefix(self):
        """판정의 정본은 properties.seeded 다. session_id 접두는 파생이다 (§3.14)."""
        events = self._events([
            self._content("seed:looks-like-one", "cta", 1, "E1", seeded=False),
            self._content("S2", "cta", 1, "E2", seeded=True),
        ])

        ids = [r["session_id"] for r in _seeded_session_ids(events).collect()]

        self.assertEqual(["S2"], ids)

    def test_segment_grain_is_unique(self):
        dwells = self._dwells([
            self._dwell("S1", "PC-1", "user_review", 100),
            self._dwell("S2", "PC-1", "user_review", 100),
            self._dwell("S3", "PC-2", "cta", 100),
        ])
        bridge = self._bridge_df([
            self._bridge("PC-1", "dry"), self._bridge("PC-2", "oily"),
        ])

        result = _segment_content_daily(dwells, self._events([]), bridge)
        key = [
            "event_date_kst", "brand_id", "skin_type", "content_kind",
            "actor_type", "source", "generator_type", "scenario_id",
            "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())


    # ── 찜 수 ───────────────────────────────────────────────
    def test_wishlist_count_counts_adds_not_toggles(self):
        """찜은 토글이라 추가와 해제가 같은 Event 다.

        해제까지 세면 관심 신호가 아니라 버튼을 누른 횟수가 된다 (§4.1).
        """
        facts = self._facts([
            self._fact("S1", "wishlist_toggle", action="add"),
            self._fact("S1", "wishlist_toggle", action="remove"),
            self._fact("S2", "wishlist_toggle", action="add"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["wishlist_count"])

    def test_wishlist_count_treats_missing_action_as_an_add(self):
        """action 없이 쌓인 옛 로그는 해제를 보낸 적이 없다 (§4.1)."""
        facts = self._facts([
            self._fact("S1", "wishlist_toggle"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["wishlist_count"])

    def test_wishlist_count_counts_events_not_sessions(self):
        """같은 세션이 두 상품을 찜하면 2 다. 진단 신호라 Event 수다 (§4.1)."""
        facts = self._facts([
            self._fact("S1", "wishlist_toggle", action="add"),
            self._fact("S1", "wishlist_toggle", action="add"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["wishlist_count"])

    def test_seeded_wishlist_events_are_excluded(self):
        """시드는 관측이 아니다 (§4.0)."""
        facts = self._facts([
            self._fact("S1", "wishlist_toggle", action="add"),
            self._fact("S2", "wishlist_toggle", action="add", seeded=True),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["wishlist_count"])


    # ── 노출 분모 (프론트 확정 2026-09-17) ───────────────────
    def test_ctr_denominator_includes_recommendation_impressions(self):
        """추천 카드 클릭도 product_click 이라 분모에 추천 노출이 있어야 한다.

        프론트는 카드 하나에 노출 Event 를 하나만 낸다 — 목록은
        product_impression, 추천·배너는 recommendation_impression. 분모를
        전자만 두면 추천발 클릭이 분자에만 들어가 CTR 이 1 을 넘는다 (§4.1).
        """
        facts = self._facts([
            self._fact("S1", "recommendation_impression"),
            self._fact("S1", "product_click"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(0, row["product_impression_count"])
        self.assertEqual(1, row["recommendation_impression_count"])
        self.assertEqual(1, row["impression_count"])
        self.assertEqual(1.0, row["product_ctr"])

    def test_impression_count_is_the_sum_of_all_three_surfaces(self):
        """목록·추천·배너 셋을 더한다. 하나라도 빠지면 분모가 모자란다."""
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_impression"),
            self._fact("S2", "recommendation_impression"),
            self._fact("S3", "banner_impression"),
            self._fact("S1", "product_click"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["product_impression_count"])
        self.assertEqual(1, row["recommendation_impression_count"])
        self.assertEqual(1, row["banner_impression_count"])
        self.assertEqual(4, row["impression_count"])
        self.assertEqual(0.25, row["product_ctr"])

    def test_history_back_views_are_not_new_entries(self):
        """뒤로가기 재조회는 새 진입이 아니다 (§4.1, 프론트 확정 2026-09-17).

        건수 기준 detail_entry_rate 의 분자라, 재조회를 포함하면 노출보다
        조회가 많아져 비율이 1 을 넘을 수 있다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S1", "product_view", navigation_source="history_back"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])      # 재조회 제외
        self.assertEqual(1, row["product_view_sessions"])   # 세션은 원래 하나
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_reload_views_are_not_new_entries(self):
        """새로고침 재조회도 새 진입이 아니다 (§4.1, 프론트 !441·3802391).

        뒤로가기보다 나쁘다 — 노출은 세션 단위 중복 방지로 한 번만 나가는데
        조회만 또 나가서, 빼지 않으면 노출 1 · 조회 2 로 비율이 2.0 이 된다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="direct"),
            self._fact("S1", "product_view", navigation_source="reload"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])      # 재조회 제외
        self.assertEqual(1, row["product_view_sessions"])   # 세션은 원래 하나
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_revisit_views_are_not_new_entries(self):
        """화면 안에서 이미 본 상품으로 다시 온 것도 새 진입이 아니다
        (§4.1, 프론트 !445).

        장바구니를 열고 닫으면 그렇게 된다. 2026-09-23 운영 배치에서 실사용자 한
        세션이 노출 1 · 조회 3 으로 detail_entry_rate 300% 를 냈고, 그중 둘이 이
        경로였다 (14초·2초 간격).
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S1", "product_view", navigation_source="revisit"),
            self._fact("S1", "product_view", navigation_source="revisit"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])      # 재조회 둘 제외
        self.assertEqual(1, row["product_view_sessions"])   # 세션은 원래 하나
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_first_in_app_entry_stays_a_new_entry(self):
        """`in_app` 첫 진입은 빼지 않는다 — 목록에서 카드를 눌러 들어온 것이다."""
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_click"),
            self._fact("S1", "product_view", navigation_source="in_app"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_repeat_in_app_view_is_a_revisit_without_the_label(self):
        """라벨이 없어도 두 번째 화면 안 상세는 재조회다 (§4.1).

        프론트가 `revisit` 을 달기 시작한 건 2026-09-23 배포부터다. Mart 는 매
        배치 raw 전체를 다시 읽으므로 그 전에 쌓인 Event 도 같이 집계된다 —
        그것들은 `in_app` 으로만 남아 있다. 라벨만 믿으면 옛 데이터에서 노출보다
        조회가 많아진다(2026-09-23 배치 실패, P442566 노출 1 · 조회 3 → 300%).

        순서로 보면 라벨 유무와 무관하게 같은 답이 나온다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S1", "add_to_cart"),
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S1", "product_view", navigation_source="in_app"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_repeat_view_of_another_product_is_a_new_entry(self):
        """재조회 판정은 세션·상품 단위다. 다른 상품은 각자 첫 진입이다."""
        facts = self._facts([
            self._fact("S1", "product_view", navigation_source="in_app", product="P1"),
            self._fact("S1", "product_view", navigation_source="in_app", product="P2"),
        ])

        counts = {
            row["product_id"]: row["product_view_count"]
            for row in _product_daily_kpi(facts).collect()
        }

        self.assertEqual({"P1": 1, "P2": 1}, counts)

    def test_same_product_in_another_session_is_a_new_entry(self):
        """세션이 다르면 처음 보는 것이다 — 프론트의 `viewed` 집합도 세션 단위다."""
        facts = self._facts([
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S2", "product_view", navigation_source="in_app"),
        ])

        self.assertEqual(2, _product_daily_kpi(facts).first()["product_view_count"])

    def test_repeat_direct_entry_stays_a_new_entry(self):
        """바깥에서 다시 들어온 것은 몇 번째든 새 진입이다.

        `direct` 는 링크·검색으로 들어온 것이라 화면 안 재조회가 아니다. 순서만
        보고 빼면 생성기의 첫 진입 1,845건이 사라진다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="direct"),
            self._fact("S1", "product_view", navigation_source="direct"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(2, row["product_view_count"])
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_direct_entry_stays_a_new_entry(self):
        """`direct` 는 빼지 않는다 — 목록을 안 거친 진짜 첫 진입이다.

        생성기가 1,845건 낸다 (2026-09-22 실측). 새로고침을 `direct` 로 묶어
        빼버리면 그것까지 사라져서, 프론트가 `reload` 를 따로 뒀다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="direct"),
        ])

        self.assertEqual(1, _product_daily_kpi(facts).first()["product_view_count"])

    def test_repeat_view_without_navigation_source_is_a_new_entry(self):
        """값이 없으면 재조회라고 단정하지 않는다 — 순서만으로는 모른다.

        `coalesce` 없이 두면 두 번째 조회에서 조건이 NULL 로 번져 새 진입도 재조회도
        아닌 상태가 되고, 그 행이 조용히 0 으로 떨어진다.
        """
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view"),
            self._fact("S1", "product_view"),
        ])

        self.assertEqual(2, _product_daily_kpi(facts).first()["product_view_count"])

    def test_revisit_judgement_ignores_row_order(self):
        """행이 어떤 순서로 도착해도 같은 답이 나와야 한다.

        `product_daily_kpi_is_deterministic_from_inputs` 가 Mart 를 재계산해
        `exceptAll` 로 비교한다. 재조회 판정이 파티션 도착 순서를 타면 그 검사가
        깨진다 — 그래서 순서를 매기는 창 대신 `min` 으로 첫 조회를 고른다.
        """
        events = [
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="in_app"),
            self._fact("S1", "product_view", navigation_source="in_app"),
        ]

        forward = _product_daily_kpi(self._facts(events)).first()
        backward = _product_daily_kpi(self._facts(list(reversed(events)))).first()

        self.assertEqual(1, forward["product_view_count"])
        self.assertEqual(forward["product_view_count"], backward["product_view_count"])

    def test_views_at_the_same_instant_still_leave_one_new_entry(self):
        """시각이 같아도 `event_id` 가 갈라 준다.

        시각만 보면 둘 다 "첫 조회" 가 되어 재조회가 하나도 안 걸러지고, 노출 1 ·
        조회 2 로 `detail_entry_rate` 가 2.0 이 된다.
        """
        same = datetime(2026, 9, 8, 3, 0, 0)
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view", navigation_source="in_app", at=same),
            self._fact("S1", "product_view", navigation_source="in_app", at=same),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["product_view_count"])
        self.assertEqual(1.0, row["detail_entry_rate"])

    def test_missing_navigation_source_counts_as_a_new_entry(self):
        """값이 없는 옛 로그는 재조회로 보지 않는다."""
        facts = self._facts([
            self._fact("S1", "product_impression"),
            self._fact("S1", "product_view"),
        ])

        self.assertEqual(1, _product_daily_kpi(facts).first()["product_view_count"])

    def test_banner_click_counts_against_the_banner_impression(self):
        """배너는 banner_click 뒤에 product_click 도 낸다 (생성기 :1289).

        분자에 들어가므로 banner_impression 이 분모에 없으면 1 을 넘는다.
        """
        facts = self._facts([
            self._fact("S1", "banner_impression"),
            self._fact("S1", "banner_click"),
            self._fact("S1", "product_click"),
        ])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(1, row["impression_count"])
        self.assertEqual(1.0, row["product_ctr"])

    def test_ctr_is_null_when_neither_surface_had_an_impression(self):
        """분모 0 은 0% 가 아니라 모름이다 (§2)."""
        facts = self._facts([self._fact("S1", "product_view")])

        row = _product_daily_kpi(facts).first()

        self.assertEqual(0, row["impression_count"])
        self.assertIsNone(row["product_ctr"])
        self.assertIsNone(row["detail_entry_rate"])


if __name__ == "__main__":
    unittest.main()
