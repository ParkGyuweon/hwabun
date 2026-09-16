"""Event 볼륨 Mart. 실데이터가 밟지 않는 경계를 고정한다.

이 Mart 의 핵심 규칙은 "Event 를 고르지 않는다" 와 "브랜드 없는 행도 남긴다" 이고,
둘 다 실수하면 조용히 지나간다 — 행이 사라져도 나머지 행은 멀쩡해 보인다.
"""
import unittest
from datetime import date

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import EXECUTION_AXES, _event_daily


CLEANED_SCHEMA = (
    "event_date_kst date, event_id string, event_name string, product_id string, "
    "session_id string, user_id string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

DIM_SCHEMA = "product_id string, brand_id string"


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class EventDailyMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("event-daily-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    @staticmethod
    def _event(event_id, event_name, product="P1", session="S1", user="U1",
               seeded=False):
        return (
            date(2026, 9, 8), event_id, event_name, product, session, user,
            "user", "web", None, None, None, seeded,
        )

    def _cleaned(self, rows):
        return self.spark.createDataFrame(rows, CLEANED_SCHEMA)

    def _dim(self, rows):
        return self.spark.createDataFrame(rows, DIM_SCHEMA)

    # ── 브랜드 보강 ────────────────────────────────────────────────────────
    def test_brand_comes_from_the_product_dimension(self):
        """cleaned_events 에는 상품 차원이 붙기 전이라 브랜드가 없다 (§4.27)."""
        cleaned = self._cleaned([self._event("e1", "product_view", product="P1")])
        dim = self._dim([("P1", "B1")])

        row = _event_daily(cleaned, dim).collect()[0]

        self.assertEqual("B1", row["brand_id"])

    def test_platform_wide_events_are_kept_with_a_null_brand(self):
        """상품에 안 붙는 Event 를 지우면 볼륨 진단이 성립하지 않는다 (§4.27).

        재생 데이터에서 이런 Event 가 전체의 59% 다 — section_dwell · page_view ·
        session_start · exit_summary 등.
        """
        cleaned = self._cleaned([
            self._event("e1", "product_view", product="P1"),
            self._event("e2", "session_start", product=None),
            self._event("e3", "exit_summary", product=None),
        ])
        dim = self._dim([("P1", "B1")])

        rows = _event_daily(cleaned, dim).collect()
        null_brand = [r for r in rows if r["brand_id"] is None]

        self.assertEqual(2, len(null_brand))
        self.assertEqual(
            {"session_start", "exit_summary"},
            {r["event_name"] for r in null_brand},
        )

    def test_unknown_product_keeps_the_row_with_a_null_brand(self):
        """Dimension 에 없는 상품도 지우지 않는다. left join 이라야 한다."""
        cleaned = self._cleaned([self._event("e1", "product_view", product="P-GHOST")])
        dim = self._dim([("P1", "B1")])

        rows = _event_daily(cleaned, dim).collect()

        self.assertEqual(1, len(rows))
        self.assertIsNone(rows[0]["brand_id"])

    # ── 전수 집계 ──────────────────────────────────────────────────────────
    def test_every_observed_event_is_counted(self):
        """Event 를 고르지 않는다. 합이 관측 Event 수와 같아야 한다 (§4.27)."""
        cleaned = self._cleaned([
            self._event("e1", "product_view"),
            self._event("e2", "banner_impression"),
            self._event("e3", "session_start", product=None),
            self._event("e4", "some_new_event_we_did_not_plan_for"),
        ])
        dim = self._dim([("P1", "B1")])

        total = sum(r["event_count"] for r in _event_daily(cleaned, dim).collect())

        self.assertEqual(4, total)

    def test_seeded_events_are_excluded(self):
        """관측된 볼륨을 재는 지표다. 시드는 생성기가 주입한 표식이다 (§4.0)."""
        cleaned = self._cleaned([
            self._event("e1", "product_view", seeded=True),
            self._event("e2", "product_view"),
        ])
        dim = self._dim([("P1", "B1")])

        row = _event_daily(cleaned, dim).collect()[0]

        self.assertEqual(1, row["event_count"])

    # ── 집계 ───────────────────────────────────────────────────────────────
    def test_sessions_and_users_are_deduplicated(self):
        cleaned = self._cleaned([
            self._event("e1", "product_view", session="S1", user="U1"),
            self._event("e2", "product_view", session="S1", user="U1"),
            self._event("e3", "product_view", session="S2", user="U1"),
        ])
        dim = self._dim([("P1", "B1")])

        row = _event_daily(cleaned, dim).collect()[0]

        self.assertEqual(3, row["event_count"])
        self.assertEqual(2, row["unique_session_count"])
        self.assertEqual(1, row["unique_user_count"])

    def test_event_names_are_separate_rows(self):
        cleaned = self._cleaned([
            self._event("e1", "product_view"),
            self._event("e2", "add_to_cart"),
        ])
        dim = self._dim([("P1", "B1")])

        rows = {r["event_name"]: r for r in _event_daily(cleaned, dim).collect()}

        self.assertEqual({"product_view", "add_to_cart"}, set(rows))

    def test_duplicate_product_rows_in_the_dimension_do_not_inflate(self):
        """dim_product 에 같은 상품이 여러 번 있어도 Event 가 부풀면 안 된다."""
        cleaned = self._cleaned([self._event("e1", "product_view", product="P1")])
        dim = self._dim([("P1", "B1"), ("P1", "B1")])

        rows = _event_daily(cleaned, dim).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["event_count"])

    def test_grain_is_unique(self):
        cleaned = self._cleaned([
            self._event("e1", "product_view", product="P1"),
            self._event("e2", "product_view", product="P2"),
            self._event("e3", "add_to_cart", product="P1"),
        ])
        dim = self._dim([("P1", "B1"), ("P2", "B2")])

        result = _event_daily(cleaned, dim)
        key = ["event_date_kst", "brand_id", "event_name", *EXECUTION_AXES]

        self.assertEqual(result.count(), result.select(*key).distinct().count())


if __name__ == "__main__":
    unittest.main()
