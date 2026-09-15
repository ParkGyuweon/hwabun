import unittest
from datetime import date

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import _persona_segment_daily_kpi


FACT_SCHEMA = (
    "event_date_kst date, brand_id string, persona_id string, session_id string, "
    "user_id string, product_id string, event_name string, actor_type string, "
    "source string, generator_type string, scenario_id string, "
    "simulation_run_id string, is_seeded boolean"
)
BRIDGE_SCHEMA = "persona_id string, segment_type string, segment_value string"


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class PersonaSegmentMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("persona-segment-mart-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    def _bridge(self, rows):
        return self.spark.createDataFrame(rows, BRIDGE_SCHEMA)

    @staticmethod
    def _event(persona, session, event_name, product="P1", seeded=False, brand="A"):
        return (
            date(2026, 9, 8), brand, persona, session, persona, product, event_name,
            "synthetic", "simulator", "python_batch", "K01", "RUN1", seeded,
        )

    def _row(self, mart, segment_type, segment_value):
        return mart.where(
            (mart["segment_type"] == segment_type)
            & (mart["segment_value"] == segment_value)
        ).first()

    def test_single_axis_sessions_are_counted_per_segment(self):
        facts = self._facts([
            self._event("PC1", "S1", "product_view"),
            self._event("PC1", "S1", "add_to_cart"),
            self._event("PC2", "S2", "product_view"),
        ])
        bridge = self._bridge([
            ("PC1", "skin_type", "dry"), ("PC1", "skin_tone", "fair"),
            ("PC2", "skin_type", "oily"), ("PC2", "skin_tone", "fair"),
        ])

        mart = _persona_segment_daily_kpi(facts, bridge)

        dry = self._row(mart, "skin_type", "dry")
        self.assertEqual(1, dry["segment_user_count"])
        self.assertEqual(1, dry["detail_view_sessions"])
        self.assertEqual(1, dry["add_to_cart_sessions"])
        self.assertEqual(1.0, dry["view_to_cart_rate"])

        # 톤은 두 페르소나가 같으므로 한 행에 모인다
        fair = self._row(mart, "skin_tone", "fair")
        self.assertEqual(2, fair["segment_user_count"])
        self.assertEqual(2, fair["detail_view_sessions"])
        self.assertEqual(0.5, fair["view_to_cart_rate"])

    def test_cross_segment_cannot_be_derived_from_single_axes(self):
        """교차 셀은 단일 축 합산으로 구할 수 없다. 그래서 따로 낸다."""
        facts = self._facts([
            self._event("PC1", "S1", "add_to_cart"),
            self._event("PC1", "S1", "product_view"),
            self._event("PC2", "S2", "product_view"),
        ])
        bridge = self._bridge([
            ("PC1", "skin_type", "dry"), ("PC1", "skin_tone", "fair"),
            ("PC2", "skin_type", "dry"), ("PC2", "skin_tone", "deep"),
        ])

        mart = _persona_segment_daily_kpi(facts, bridge)

        self.assertEqual(2, self._row(mart, "skin_type", "dry")["detail_view_sessions"])
        fair_cell = self._row(mart, "skin_type_x_skin_tone", "dry|fair")
        deep_cell = self._row(mart, "skin_type_x_skin_tone", "dry|deep")
        self.assertEqual(1, fair_cell["detail_view_sessions"])
        self.assertEqual(1, deep_cell["detail_view_sessions"])
        # 건성 담기율 0.5 를 셀로 쪼개면 fair 1.0 · deep 0.0 이다. 평균이 아니다.
        self.assertEqual(1.0, fair_cell["view_to_cart_rate"])
        self.assertEqual(0.0, deep_cell["view_to_cart_rate"])

    def test_sessions_without_persona_are_not_attributed(self):
        """실제 사용자 세션은 피부 정보가 이벤트 경로에 없다. 어느 세그먼트에도 넣지 않는다."""
        facts = self._facts([
            self._event("PC1", "S1", "product_view"),
            self._event(None, "S2", "product_view"),
            (
                date(2026, 9, 8), "A", "", "S3", "U3", "P1", "product_view",
                "user", "web", None, None, None, False,
            ),
        ])
        bridge = self._bridge([("PC1", "skin_type", "dry")])

        mart = _persona_segment_daily_kpi(facts, bridge)

        self.assertEqual(1, mart.count())
        # 세션 3개 중 귀속된 건 하나뿐이다. 합이 전체와 다른 것이 정상이다.
        self.assertEqual(1, self._row(mart, "skin_type", "dry")["detail_view_sessions"])

    def test_missing_skin_tone_marker_is_not_a_segment(self):
        """notSureST 는 값이 아니라 결측이다 (persona-schema.md §3)."""
        facts = self._facts([
            self._event("PC1", "S1", "product_view"),
            self._event("PC2", "S2", "product_view"),
        ])
        bridge = self._bridge([
            ("PC1", "skin_type", "dry"), ("PC1", "skin_tone", "notSureST"),
            ("PC2", "skin_type", "dry"), ("PC2", "skin_tone", "fair"),
        ])

        mart = _persona_segment_daily_kpi(facts, bridge)

        self.assertEqual(
            0, mart.where(mart["segment_value"].contains("notSureST")).count()
        )
        # 톤이 결측인 페르소나는 교차 축에도 들어가지 않는다
        self.assertEqual(
            1, mart.where(mart["segment_type"] == "skin_type_x_skin_tone").count()
        )
        # 타입 축에는 그대로 남는다 — 톤만 모르는 것이지 타입을 모르는 게 아니다
        self.assertEqual(2, self._row(mart, "skin_type", "dry")["segment_user_count"])

    def test_brand_sessions_are_deduplicated_across_products(self):
        """한 세션이 같은 브랜드 상품 여러 개를 봐도 세그먼트 세션은 하나다."""
        facts = self._facts([
            self._event("PC1", "S1", "product_view", product="P1"),
            self._event("PC1", "S1", "quick_look", product="P2"),
            self._event("PC1", "S1", "product_view", product="P3"),
        ])
        bridge = self._bridge([("PC1", "skin_type", "dry")])

        row = _persona_segment_daily_kpi(facts, bridge).first()

        self.assertEqual(1, row["session_count"])
        self.assertEqual(1, row["detail_view_sessions"])
        self.assertEqual(3, row["product_count_viewed"])

    def test_seed_events_are_excluded(self):
        """시드는 주입된 선호 표식이라 관측 행동이 아니다 (dw-schema.md §4.0)."""
        facts = self._facts([
            self._event("PC1", "S1", "product_view"),
            self._event("PC1", "seed:RUN1:PC1:P9", "add_to_cart", seeded=True),
        ])
        bridge = self._bridge([("PC1", "skin_type", "dry")])

        row = _persona_segment_daily_kpi(facts, bridge).first()

        self.assertEqual(1, row["detail_view_sessions"])
        # 시드 담기가 들어갔다면 담기율이 1.0 이 된다
        self.assertEqual(0, row["add_to_cart_sessions"])
        self.assertEqual(0.0, row["view_to_cart_rate"])

    def test_zero_denominator_rate_is_null(self):
        facts = self._facts([self._event("PC1", "S1", "product_impression")])
        bridge = self._bridge([("PC1", "skin_type", "dry")])

        row = _persona_segment_daily_kpi(facts, bridge).first()

        self.assertEqual(0, row["detail_view_sessions"])
        self.assertIsNone(row["view_to_cart_rate"])
        self.assertEqual(1, row["impression_sessions"])
        self.assertEqual(0.0, row["detail_entry_rate"])

    def test_non_skin_segment_types_are_ignored(self):
        """bridge 에 7종이 있지만 대시보드 고객군 화면은 피부 축만 쓴다."""
        facts = self._facts([self._event("PC1", "S1", "product_view")])
        bridge = self._bridge([
            ("PC1", "skin_type", "dry"),
            ("PC1", "skin_tone", "fair"),
            ("PC1", "hair_color", "brown"),
            ("PC1", "eye_color", "blue"),
            ("PC1", "review_bucket", "3"),
            ("PC1", "persona_source", "batch_sample"),
        ])

        mart = _persona_segment_daily_kpi(facts, bridge)

        self.assertEqual(
            {"skin_type", "skin_tone", "skin_type_x_skin_tone"},
            {row["segment_type"]
             for row in mart.select("segment_type").distinct().collect()},
        )

    def test_interest_score_is_averaged_over_sessions(self):
        """avg_interest_score 분모는 세션 수다 (dw-schema.md §2.3)."""
        facts = self._facts([
            self._event("PC1", "S1", "product_view"),
            self._event("PC1", "S1", "add_to_cart"),
            self._event("PC2", "S2", "product_view"),
        ])
        bridge = self._bridge([
            ("PC1", "skin_type", "dry"), ("PC2", "skin_type", "dry"),
        ])

        row = _persona_segment_daily_kpi(
            facts, bridge, {"product_view": 1.0, "add_to_cart": 3.0}
        ).first()

        self.assertEqual(2, row["session_count"])
        # (1 + 3 + 1) / 2
        self.assertEqual(2.5, row["avg_interest_score"])


if __name__ == "__main__":
    unittest.main()
