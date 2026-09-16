"""고객군 × 가격 밴드 교차 Mart (S5). 실데이터가 못 밟는 규칙을 고정한다.

계약 §4.26이 적어 둔 대로, 재생 데이터로는 세 규칙을 검증할 수 없다 —
카탈로그 208개가 전부 원화이고 `base_price` 결측이 0개이며 전부 `synthetic`이다.
통화 혼합·가격 결측·실사용자 미귀속은 여기서만 덮인다.
"""
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    CROSS_SEGMENT_TYPE,
    MISSING_SEGMENT_VALUES,
    S5_SEGMENT_TYPES,
    _segment_price_band_daily_kpi,
    load_price_bins,
)


ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = ROOT / "contracts" / "product-feature-vocab.json"

FACT_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "user_id string, persona_id string, event_name string, "
    "actor_type string, source string, generator_type string, "
    "scenario_id string, simulation_run_id string, is_seeded boolean"
)

DIM_SCHEMA = "product_id string, base_price decimal(18,2), currency string"

BRIDGE_SCHEMA = "persona_id string, segment_type string, segment_value string"


class S5AxisContractTest(unittest.TestCase):
    def test_cross_axis_is_not_one_of_the_s5_axes(self):
        """교차 축까지 얹으면 셀이 100개가 되어 표본이 무너진다 (§4.26)."""
        self.assertNotIn(CROSS_SEGMENT_TYPE, S5_SEGMENT_TYPES)
        self.assertEqual(("skin_type", "skin_tone"), S5_SEGMENT_TYPES)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class SegmentPriceBandMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("segment-price-band-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.bins = load_price_bins(str(VOCAB_PATH))

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    # ── 픽스처 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _event(session, event_name, persona="PC-1", product="P1", brand="B1",
               seeded=False):
        return (
            date(2026, 9, 8), brand, product, session, "U-" + session, persona,
            event_name, "synthetic", "simulator", "python_batch", None, None, seeded,
        )

    @staticmethod
    def _product(product_id, price, currency="KRW"):
        return (product_id, None if price is None else Decimal(str(price)), currency)

    @staticmethod
    def _bridge(persona, segment_type, segment_value):
        return (persona, segment_type, segment_value)

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    def _dim(self, rows):
        return self.spark.createDataFrame(rows, DIM_SCHEMA)

    def _bridge_df(self, rows):
        return self.spark.createDataFrame(rows, BRIDGE_SCHEMA)

    def _mart(self, facts, dim, bridge):
        return _segment_price_band_daily_kpi(facts, dim, bridge, self.bins)

    # ── 축 ─────────────────────────────────────────────────────────────────
    def test_cross_axis_rows_are_not_emitted(self):
        """bridge 에 두 축이 다 있어도 교차 축 행을 내지 않는다 (§4.26)."""
        facts = self._facts([self._event("S1", "product_view")])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([
            self._bridge("PC-1", "skin_type", "dry"),
            self._bridge("PC-1", "skin_tone", "fair"),
        ])

        types = {r["segment_type"] for r in self._mart(facts, dim, bridge).collect()}

        self.assertEqual(set(S5_SEGMENT_TYPES), types)
        self.assertNotIn(CROSS_SEGMENT_TYPE, types)

    def test_one_session_lands_in_both_segment_types(self):
        """그래서 segment_type 을 걸쳐 합산하면 안 된다 (§4.26)."""
        facts = self._facts([self._event("S1", "product_view")])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([
            self._bridge("PC-1", "skin_type", "dry"),
            self._bridge("PC-1", "skin_tone", "fair"),
        ])

        rows = self._mart(facts, dim, bridge).collect()

        self.assertEqual(2, len(rows))
        self.assertTrue(all(r["session_count"] == 1 for r in rows))

    def test_missing_segment_values_are_not_a_segment(self):
        """notSureST 는 값이 아니라 결측이다 (persona-schema.md §3)."""
        facts = self._facts([
            self._event("S1", "product_view", persona="PC-1"),
            self._event("S2", "product_view", persona="PC-2"),
        ])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([
            self._bridge("PC-1", "skin_tone", "fair"),
            self._bridge("PC-2", "skin_tone", MISSING_SEGMENT_VALUES[0]),
        ])

        values = {r["segment_value"] for r in self._mart(facts, dim, bridge).collect()}

        self.assertEqual({"fair"}, values)

    def test_sessions_without_a_persona_are_not_attributed(self):
        """임의 귀속은 없는 사실을 만들어 낸다. 실사용자가 이 경우다 (§4.26)."""
        facts = self._facts([
            self._event("S1", "product_view", persona=None),
            self._event("S2", "product_view", persona="PC-1"),
        ])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        rows = self._mart(facts, dim, bridge).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["session_count"])

    # ── 가격 ───────────────────────────────────────────────────────────────
    def test_price_bins_come_from_the_vocabulary(self):
        """어휘집 구간에 그대로 떨어져야 한다. 숫자를 Mart 에 복제하지 않는다."""
        facts = self._facts([
            self._event("S1", "product_view", product="P-CHEAP"),
            self._event("S2", "product_view", product="P-RICH"),
        ])
        dim = self._dim([
            self._product("P-CHEAP", 10000),
            self._product("P-RICH", 200000),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        bins = {r["price_bin"] for r in self._mart(facts, dim, bridge).collect()}
        vocabulary = {token for token, _ in self.bins}

        self.assertEqual(2, len(bins))
        self.assertTrue(bins <= vocabulary)

    def test_missing_price_is_kept_as_a_null_bin(self):
        """빼면 그 상품의 반응을 못 보고, 임의 구간에 넣으면 그 구간이 오염된다."""
        facts = self._facts([
            self._event("S1", "product_view", product="P-NULL"),
            self._event("S2", "product_view", product="P-ZERO"),
            self._event("S3", "product_view", product="P-OK"),
        ])
        dim = self._dim([
            self._product("P-NULL", None),
            self._product("P-ZERO", 0),
            self._product("P-OK", 30000),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        rows = self._mart(facts, dim, bridge).collect()
        null_rows = [r for r in rows if r["price_bin"] is None]

        self.assertEqual(1, len(null_rows))
        self.assertEqual(2, null_rows[0]["session_count"])

    def test_currency_is_in_the_grain_so_prices_do_not_merge(self):
        """환산 규칙 없이 통화가 다른 가격을 한 구간으로 합치지 않는다 (§4.26).

        카탈로그가 전부 원화라 실데이터로는 못 밟는다.
        """
        facts = self._facts([
            self._event("S1", "product_view", product="P-KRW"),
            self._event("S2", "product_view", product="P-USD"),
        ])
        dim = self._dim([
            self._product("P-KRW", 30000, "KRW"),
            self._product("P-USD", 30000, "USD"),
        ])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        rows = self._mart(facts, dim, bridge).collect()

        self.assertEqual(2, len(rows))
        self.assertEqual({"KRW", "USD"}, {r["currency"] for r in rows})

    def test_catalog_currency_wins_over_the_event_column(self):
        """product_event_fact 에도 currency 가 있지만 뜻이 다르다 (결제 시점 통화).

        이름이 겹쳐 Join 뒤 참조가 모호해지는 것을 Jira 277 에서 겪었다.
        """
        rows = self._mart(
            self._facts([self._event("S1", "product_view")]),
            self._dim([self._product("P1", 30000, "KRW")]),
            self._bridge_df([self._bridge("PC-1", "skin_type", "dry")]),
        ).collect()

        self.assertEqual("KRW", rows[0]["currency"])

    # ── 비율·시드 ──────────────────────────────────────────────────────────
    def test_cart_denominator_is_the_detail_view_sessions(self):
        """퀵룩으로만 연 세션도 분모다. 아니면 비율이 1.0 을 넘는다 (§4.1 규칙)."""
        facts = self._facts([
            self._event("S1", "quick_look"),
            self._event("S1", "add_to_cart"),
            self._event("S2", "product_view"),
        ])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        row = self._mart(facts, dim, bridge).collect()[0]

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["product_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        self.assertEqual(0.5, row["view_to_cart_rate"])

    def test_zero_denominator_rate_is_null_not_zero(self):
        facts = self._facts([self._event("S1", "product_impression")])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        row = self._mart(facts, dim, bridge).collect()[0]

        self.assertEqual(0, row["detail_view_sessions"])
        self.assertIsNone(row["view_to_cart_rate"])

    def test_seeded_events_are_excluded(self):
        facts = self._facts([
            self._event("S1", "product_view", seeded=True),
            self._event("S2", "product_view"),
        ])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        row = self._mart(facts, dim, bridge).collect()[0]

        self.assertEqual(1, row["session_count"])

    def test_one_product_maps_to_a_single_bin(self):
        """상품이 정의된 밴드에 중복 없이 매핑된다 (완료 조건)."""
        facts = self._facts([
            self._event("S1", "product_view"),
            self._event("S2", "product_view"),
        ])
        dim = self._dim([self._product("P1", 30000)])
        bridge = self._bridge_df([self._bridge("PC-1", "skin_type", "dry")])

        bins = [r["price_bin"] for r in self._mart(facts, dim, bridge).collect()]

        self.assertEqual(1, len(set(bins)))

    def test_grain_is_unique(self):
        facts = self._facts([
            self._event("S1", "product_view", product="P1"),
            self._event("S2", "product_view", product="P2"),
        ])
        dim = self._dim([
            self._product("P1", 30000), self._product("P2", 200000),
        ])
        bridge = self._bridge_df([
            self._bridge("PC-1", "skin_type", "dry"),
            self._bridge("PC-1", "skin_tone", "fair"),
        ])

        result = self._mart(facts, dim, bridge)
        key = [
            "event_date_kst", "brand_id", "segment_type", "segment_value",
            "price_bin", "currency", "actor_type", "source", "generator_type",
            "scenario_id", "simulation_run_id",
        ]

        self.assertEqual(result.count(), result.select(*key).distinct().count())


if __name__ == "__main__":
    unittest.main()
