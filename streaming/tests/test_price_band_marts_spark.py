import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    _brand_price_band_daily_kpi,
    load_price_bins,
)


ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = ROOT / "contracts" / "product-feature-vocab.json"

FACT_SCHEMA = (
    "event_date_kst date, brand_id string, product_id string, session_id string, "
    "user_id string, event_name string, actor_type string, source string, "
    "generator_type string, scenario_id string, simulation_run_id string, "
    "is_seeded boolean, currency string"
)
DIM_SCHEMA = "product_id string, base_price decimal(18,2), currency string"


class PriceBinContractTest(unittest.TestCase):
    """구간은 추천 어휘집이 정본이다. 여기에 숫자를 복제하지 않는다."""

    def test_bins_come_from_the_recommendation_vocabulary(self):
        vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        bins = load_price_bins(str(VOCAB_PATH))

        tokens = [token for token, _ in bins]
        uppers = [upper for _, upper in bins]
        block = next(
            b for b in vocab["blocks"] if b.get("name") == "price_bin"
        )

        self.assertEqual(block["vocab"], tokens)
        # 마지막 구간은 상한이 없다
        self.assertIsNone(uppers[-1])
        self.assertEqual([float(e) for e in vocab["price_bin_edges"][1:]], uppers[:-1])

    def test_edges_are_won_not_dollars(self):
        """원화 경계가 됐다. 달러 경계가 남아 있으면 화면과 갈린다."""
        bins = load_price_bins(str(VOCAB_PATH))
        first_upper = bins[0][1]

        self.assertGreater(first_upper, 1000)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class PriceBandMartSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("price-band-mart-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.bins = load_price_bins(str(VOCAB_PATH))

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    def _dim(self, rows):
        return self.spark.createDataFrame(rows, DIM_SCHEMA)

    @staticmethod
    def _event(product, session, event_name, seeded=False, brand="A",
               event_currency=None):
        """``currency`` 는 product_event_fact 에 실제로 있는 컬럼이다.

        결제 시점 통화라 카탈로그 기준 가격의 통화와 뜻이 다르다. 픽스처에서
        빠뜨렸다가 실데이터 재생에서 AMBIGUOUS_REFERENCE 로 터졌다.
        """
        return (
            date(2026, 9, 8), brand, product, session, "U-" + session, event_name,
            "user", "web", None, None, None, seeded, event_currency,
        )

    def _row(self, mart, price_bin):
        if price_bin is None:
            return mart.where(mart["price_bin"].isNull()).first()
        return mart.where(mart["price_bin"] == price_bin).first()

    def test_products_fall_into_the_expected_band(self):
        facts = self._facts([
            self._event("P-cheap", "S1", "product_view"),
            self._event("P-mid", "S2", "product_view"),
            self._event("P-high", "S3", "product_view"),
        ])
        dim = self._dim([
            ("P-cheap", Decimal("20000.00"), "KRW"),
            ("P-mid", Decimal("50000.00"), "KRW"),
            ("P-high", Decimal("200000.00"), "KRW"),
        ])

        mart = _brand_price_band_daily_kpi(facts, dim, self.bins)
        bins = {row["price_bin"] for row in mart.collect()}

        self.assertEqual({"~26k", "46k-66k", "105k+"}, bins)

    def test_boundary_price_falls_into_the_upper_band(self):
        """반열린 구간 [하한, 상한) 이라 경계값은 위쪽이다. 두 구간에 들어갈 수 없다."""
        facts = self._facts([
            self._event("P-edge", "S1", "product_view"),
        ])
        dim = self._dim([("P-edge", Decimal("26000.00"), "KRW")])

        mart = _brand_price_band_daily_kpi(facts, dim, self.bins)

        self.assertEqual(1, mart.count())
        self.assertEqual("26k-46k", mart.first()["price_bin"])

    def test_missing_or_non_positive_price_becomes_a_null_band(self):
        """빼면 그 상품의 반응을 못 보고, 임의 구간에 넣으면 그 구간이 오염된다."""
        facts = self._facts([
            self._event("P-null", "S1", "product_view"),
            self._event("P-zero", "S2", "product_view"),
            self._event("P-neg", "S3", "product_view"),
            self._event("P-ok", "S4", "product_view"),
        ])
        dim = self._dim([
            ("P-null", None, "KRW"),
            ("P-zero", Decimal("0.00"), "KRW"),
            ("P-neg", Decimal("-100.00"), "KRW"),
            ("P-ok", Decimal("30000.00"), "KRW"),
        ])

        mart = _brand_price_band_daily_kpi(facts, dim, self.bins)

        null_row = self._row(mart, None)
        self.assertEqual(3, null_row["product_count"])
        self.assertEqual(3, null_row["detail_view_sessions"])
        self.assertEqual(1, self._row(mart, "26k-46k")["product_count"])

    def test_currencies_are_not_merged_into_one_band(self):
        """환산 규칙 없이 통화를 합치지 않는다. 필터가 아니라 grain 으로 막는다."""
        facts = self._facts([
            self._event("P-krw", "S1", "product_view"),
            self._event("P-usd", "S2", "product_view"),
        ])
        dim = self._dim([
            ("P-krw", Decimal("30000.00"), "KRW"),
            # 같은 구간 숫자지만 통화가 다르다. 한 행으로 합치면 안 된다
            ("P-usd", Decimal("30000.00"), "USD"),
        ])

        mart = _brand_price_band_daily_kpi(facts, dim, self.bins)
        rows = mart.where(mart["price_bin"] == "26k-46k").collect()

        self.assertEqual(2, len(rows))
        self.assertEqual({"KRW", "USD"}, {row["currency"] for row in rows})
        for row in rows:
            self.assertEqual(1, row["product_count"])

    def test_band_sessions_are_deduplicated_across_products(self):
        """한 세션이 같은 구간의 상품 두 개를 봐도 세션은 하나다."""
        facts = self._facts([
            self._event("P1", "S1", "product_view"),
            self._event("P2", "S1", "quick_look"),
            self._event("P1", "S1", "add_to_cart"),
        ])
        dim = self._dim([
            ("P1", Decimal("30000.00"), "KRW"),
            ("P2", Decimal("40000.00"), "KRW"),
        ])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        self.assertEqual(1, row["session_count"])
        self.assertEqual(1, row["detail_view_sessions"])
        self.assertEqual(2, row["product_count"])
        self.assertEqual(1.0, row["view_to_cart_rate"])

    def test_cart_rate_uses_detail_view_sessions(self):
        facts = self._facts([
            # Quick Look 으로만 담은 세션
            self._event("P1", "S1", "quick_look"),
            self._event("P1", "S1", "add_to_cart"),
            # 상세만 열고 담지 않은 세션
            self._event("P1", "S2", "product_view"),
        ])
        dim = self._dim([("P1", Decimal("30000.00"), "KRW")])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        self.assertEqual(2, row["detail_view_sessions"])
        self.assertEqual(1, row["add_to_cart_sessions"])
        self.assertEqual(0.5, row["view_to_cart_rate"])

    def test_seed_events_are_excluded(self):
        facts = self._facts([
            self._event("P1", "S1", "product_view"),
            self._event("P1", "seed:RUN1:PC1:P1", "add_to_cart", seeded=True),
        ])
        dim = self._dim([("P1", Decimal("30000.00"), "KRW")])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        self.assertEqual(1, row["detail_view_sessions"])
        self.assertEqual(0, row["add_to_cart_sessions"])
        self.assertEqual(0.0, row["view_to_cart_rate"])

    def test_zero_denominator_rate_is_null(self):
        facts = self._facts([self._event("P1", "S1", "product_impression")])
        dim = self._dim([("P1", Decimal("30000.00"), "KRW")])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        self.assertEqual(0, row["detail_view_sessions"])
        self.assertIsNone(row["view_to_cart_rate"])
        self.assertEqual(1, row["impression_sessions"])
        self.assertEqual(0.0, row["detail_entry_rate"])

    def test_currency_comes_from_the_catalog_not_the_event(self):
        """이 Mart 의 통화는 카탈로그 기준 가격의 단위다. 이벤트 통화가 아니다.

        product_event_fact 에도 currency 가 있는데 그쪽은 결제 시점 통화라 뜻이
        다르다. 두 컬럼 이름이 겹치면 Join 뒤 참조가 모호해져 Job 이 죽는다.
        통화 전환(S15P21A306-303) 기간에는 둘이 실제로 다른 값이 된다.
        """
        facts = self._facts([
            self._event("P1", "S1", "product_view", event_currency="USD"),
        ])
        dim = self._dim([("P1", Decimal("30000.00"), "KRW")])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        self.assertEqual("KRW", row["currency"])
        self.assertEqual("26k-46k", row["price_bin"])

    def test_products_outside_the_dimension_are_dropped(self):
        """Dimension 에 없는 상품은 가격을 모른다. 임의 구간에 넣지 않는다."""
        facts = self._facts([
            self._event("P-known", "S1", "product_view"),
            self._event("P-unknown", "S2", "product_view"),
        ])
        dim = self._dim([("P-known", Decimal("30000.00"), "KRW")])

        mart = _brand_price_band_daily_kpi(facts, dim, self.bins)

        self.assertEqual(1, mart.count())
        self.assertEqual(1, mart.first()["detail_view_sessions"])


    # ── 노출 분모 ───────────────────────────────────────────
    def test_impression_sessions_count_all_three_surfaces(self):
        """노출 Event 는 셋이다 (§4.1). 추천·배너로만 노출된 세션도 분모다.

        product_impression 만 세면 그 세션이 분모에서 빠져 detail_entry_rate 가
        1 을 넘는다 — 104만 건 실행에서 같은 계열 Mart 가 그렇게 걸렸다.
        """
        facts = self._facts([
            self._event("P-mid", "S1", "recommendation_impression"),
            self._event("P-mid", "S1", "product_view"),
            self._event("P-mid", "S2", "banner_impression"),
            self._event("P-mid", "S2", "product_view"),
        ])
        dim = self._dim([("P-mid", Decimal("50000.00"), "KRW")])

        row = _brand_price_band_daily_kpi(facts, dim, self.bins).first()

        # product_impression 이 0 인데도 두 세션 다 노출로 잡혀야 한다
        self.assertEqual(2, row["impression_sessions"])
        self.assertEqual(2, row["detail_view_sessions"])
        self.assertLessEqual(row["detail_entry_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
