import unittest
from datetime import date
from decimal import Decimal

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    COMMONS_METRICS,
    _brand_cohort_dim,
    _commons_cohort_weekly,
    load_price_bins,
)


VOCAB = "contracts/product-feature-vocab.json"

PRODUCT_SCHEMA = (
    "product_id string, brand_id string, brand_name string, "
    "secondary_category string, base_price decimal(18,2), currency string"
)
BRAND_SCHEMA = "brand_id string, brand_hash string, commons_participating boolean"
DAILY_SCHEMA = (
    "event_date_kst date, brand_id string, actor_type string, source string, "
    "generator_type string, scenario_id string, simulation_run_id string, "
    "impression_sessions bigint, detail_view_sessions bigint, "
    "product_view_sessions bigint, information_view_sessions bigint, "
    "add_to_cart_sessions bigint"
)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class BrandCohortDimSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("brand-cohort-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.bins = load_price_bins(VOCAB)

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _products(self, rows):
        return self.spark.createDataFrame(rows, PRODUCT_SCHEMA)

    def _brands(self, brand_ids):
        return self.spark.createDataFrame(
            [(b, "hash-" + b, True) for b in brand_ids], BRAND_SCHEMA
        )

    @staticmethod
    def _p(product, brand, price, category="Moisturizers"):
        return (
            product, brand, brand.upper(), category,
            None if price is None else Decimal(str(price)), "KRW",
        )

    def test_product_count_bands_follow_the_contract(self):
        """밴드 경계는 실측으로 잡았다 (dw-schema.md §3.7)."""
        products = self._products(
            [self._p("P1", "one", 30000)]
            + [self._p(f"P{i}", "three", 30000) for i in range(2, 5)]
            + [self._p(f"Q{i}", "seven", 30000) for i in range(7)]
            + [self._p(f"R{i}", "twelve", 30000) for i in range(12)]
        )
        brands = self._brands(["one", "three", "seven", "twelve"])

        rows = {
            row["brand_id"]: row
            for row in _brand_cohort_dim(products, brands, self.bins).collect()
        }

        self.assertEqual("1", rows["one"]["product_count_band"])
        self.assertEqual("2-3", rows["three"]["product_count_band"])
        self.assertEqual("4-10", rows["seven"]["product_count_band"])
        self.assertEqual("11+", rows["twelve"]["product_count_band"])

    def test_cohort_key_joins_band_and_price(self):
        products = self._products([
            self._p("P1", "b1", 30000), self._p("P2", "b1", 40000),
        ])
        row = _brand_cohort_dim(products, self._brands(["b1"]), self.bins).first()

        self.assertEqual("2-3", row["product_count_band"])
        self.assertEqual("26k-46k", row["dominant_price_bin"])
        self.assertEqual("2-3|26k-46k", row["cohort_key"])

    def test_dominant_price_bin_breaks_ties_deterministically(self):
        """동률에서 규칙이 없으면 실행마다 판정이 흔들려 재계산 결정성이 깨진다."""
        products = self._products([
            self._p("P1", "b1", 30000),    # 26k-46k
            self._p("P2", "b1", 200000),   # 105k+
        ])

        first = _brand_cohort_dim(products, self._brands(["b1"]), self.bins).first()
        second = _brand_cohort_dim(products, self._brands(["b1"]), self.bins).first()

        self.assertEqual(first["dominant_price_bin"], second["dominant_price_bin"])
        # 사전순으로 낮은 쪽
        self.assertEqual("105k+", first["dominant_price_bin"])

    def test_brand_without_known_price_has_no_cohort(self):
        """임의 구간에 넣으면 그 코호트의 분위가 오염된다. 빼는 쪽이 정직하다."""
        products = self._products([
            self._p("P1", "nopricce", None), self._p("P2", "nopricce", 0),
        ])
        row = _brand_cohort_dim(products, self._brands(["nopricce"]), self.bins).first()

        self.assertIsNone(row["dominant_price_bin"])
        self.assertIsNone(row["cohort_key"])
        self.assertEqual(2, row["product_count"])

    def test_brand_hash_comes_from_dim_brand(self):
        """같은 값을 두 곳에서 계산하면 조용히 갈라진다."""
        products = self._products([self._p("P1", "b1", 30000)])
        row = _brand_cohort_dim(products, self._brands(["b1"]), self.bins).first()

        self.assertEqual("hash-b1", row["brand_hash"])

    def test_blank_brand_is_dropped(self):
        products = self._products([
            self._p("P1", "b1", 30000), self._p("P2", "  ", 30000),
        ])
        mart = _brand_cohort_dim(products, self._brands(["b1"]), self.bins)

        self.assertEqual(1, mart.count())


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class CommonsCohortWeeklySparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("commons-cohort-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    @staticmethod
    def _daily(brand, impressions, detail, cart, day=8):
        return (
            date(2026, 9, day), brand, "synthetic", "simulator", "python_batch",
            "K01", "RUN1", impressions, detail, detail, 0, cart,
        )

    def _dailies(self, rows):
        return self.spark.createDataFrame(rows, DAILY_SCHEMA)

    def _cohort(self, brands, key="2-3|26k-46k"):
        return self.spark.createDataFrame(
            [(b, "hash-" + b, key, True) for b in brands],
            "brand_id string, brand_hash string, cohort_key string, "
            "commons_participating boolean",
        )

    def _row(self, mart, metric):
        """축별 행. 전체(`actor_type='all'`) 행은 `_collapsed_row` 로 따로 본다."""
        return mart.where(
            (mart["metric_name"] == metric) & (mart["actor_type"] != "all")
        ).first()

    def _collapsed_row(self, mart, metric):
        """실행축을 걷어낸 전체 행 (Jira 404)."""
        return mart.where(
            (mart["metric_name"] == metric) & (mart["actor_type"] == "all")
        ).first()

    def test_cohort_with_too_few_brands_is_suppressed(self):
        """R1 — 브랜드 5 미만이면 값을 지운다. 행은 남긴다."""
        brands = [f"b{i}" for i in range(4)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 300, 200, 40) for b in brands]),
            self._cohort(brands),
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertEqual(4, row["brand_count"])
        self.assertTrue(row["is_suppressed"])
        self.assertIsNone(row["p25"])
        self.assertIsNone(row["p50"])
        self.assertIsNone(row["p75"])
        # 억제돼도 행은 남는다 — "억제됐다"와 "코호트가 없다"는 다르다.
        # 축별 한 벌 + 실행축을 걷어낸 전체 한 벌이라 두 배다 (Jira 404).
        self.assertEqual(len(COMMONS_METRICS) * 2, mart.count())

    def test_collapsed_row_is_emitted_with_the_all_sentinel(self):
        """실행축을 걷어낸 전체 행을 한 벌 더 낸다 (Jira 404).

        분위수는 가중 평균으로 합칠 수 없어 (p50 둘의 평균은 합친 집합의 p50 이
        아니다) 축을 합친 값은 원본 브랜드 값에서 다시 계산해야 한다. 원본은
        Spark 에만 있으므로 조회하는 서버가 할 수 없다.
        """
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 300, 200, 40) for b in brands]),
            self._cohort(brands),
        )

        collapsed = self._collapsed_row(mart, "view_to_cart_rate")

        self.assertIsNotNone(collapsed)
        self.assertEqual(6, collapsed["brand_count"])
        # NULL 이 아니라 'all' 이다. generator_type 의 NULL 은 실사용자(Web)를
        # 뜻해서, NULL 로 두면 전체 행과 실사용자 행을 가를 수 없다.
        for axis in ("actor_type", "source", "generator_type"):
            self.assertEqual("all", collapsed[axis])

    def test_collapsed_row_covers_every_axis(self):
        """전체 행은 어느 축 행보다 브랜드가 적을 수 없다."""
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 300, 200, 40) for b in brands]),
            self._cohort(brands),
        )

        collapsed = self._collapsed_row(mart, "view_to_cart_rate")
        per_axis = self._row(mart, "view_to_cart_rate")

        self.assertGreaterEqual(collapsed["brand_count"], per_axis["brand_count"])

    def test_dominated_cohort_is_suppressed(self):
        """R3 — 한 브랜드가 분모의 50% 를 넘으면 중앙값이 곧 그 브랜드 숫자다."""
        rows = [self._daily("big", 2000, 1000, 100)]
        rows += [self._daily(f"s{i}", 100, 50, 10) for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies(rows), self._cohort(["big"] + [f"s{i}" for i in range(6)])
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertEqual(7, row["brand_count"])
        self.assertTrue(row["is_dominated"])
        self.assertTrue(row["is_suppressed"])
        self.assertIsNone(row["p50"])

    def test_thin_sample_keeps_values_but_flags(self):
        """R2 는 값을 지우지 않는다. 표본이 얇은 것과 식별 위험은 다른 문제다."""
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 30, 20, 4) for b in brands]),
            self._cohort(brands),
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertFalse(row["is_sample_sufficient"])
        self.assertFalse(row["is_suppressed"])
        self.assertIsNotNone(row["p50"])

    def test_healthy_cohort_reports_ordered_quantiles(self):
        rows = [
            self._daily(f"b{i}", 400, 300, 30 * (i + 1)) for i in range(6)
        ]
        mart = _commons_cohort_weekly(
            self._dailies(rows), self._cohort([f"b{i}" for i in range(6)])
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertEqual(6, row["brand_count"])
        self.assertFalse(row["is_suppressed"])
        self.assertTrue(row["is_sample_sufficient"])
        self.assertLessEqual(row["p25"], row["p50"])
        self.assertLessEqual(row["p50"], row["p75"])
        for quantile in ("p25", "p50", "p75"):
            self.assertGreaterEqual(row[quantile], 0.0)
            self.assertLessEqual(row[quantile], 1.0)

    def test_no_brand_identifier_survives(self):
        """B층이라 다른 브랜드에게 보여도 되는 형태여야 한다 (R5)."""
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 400, 300, 60) for b in brands]),
            self._cohort(brands),
        )

        for column in ("brand_id", "brand_hash", "brand_name"):
            self.assertNotIn(column, mart.columns)

    def test_no_absolute_counts_survive(self):
        """R4 — 절대 건수 컬럼을 두지 않는다. brand_count 는 브랜드 수라 예외다."""
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 400, 300, 60) for b in brands]),
            self._cohort(brands),
        )

        # 이름이 count 로 끝나도 절대 건수가 아닌 것이 둘 있다.
        #   brand_count      셀 안 브랜드 수. R1 판정과 화면의 표본 병기에 필요하다
        #   min_brand_count  실행 당시 임계값. 데이터가 아니라 파라미터다
        allowed = {"brand_count", "min_brand_count", "min_sample_size"}
        leaked = [
            column for column in mart.columns
            if column not in allowed
            and (column.endswith("_sessions") or column.endswith("_count"))
        ]
        self.assertEqual([], leaked)
        # 세션 분모는 불리언으로만 전달한다 — 숫자를 실으면 역산이 가능해진다
        self.assertIn("is_sample_sufficient", mart.columns)

    def test_non_participating_brand_is_excluded(self):
        brands = [f"b{i}" for i in range(6)]
        cohort = self.spark.createDataFrame(
            [(b, "hash-" + b, "2-3|26k-46k", b != "b0") for b in brands],
            "brand_id string, brand_hash string, cohort_key string, "
            "commons_participating boolean",
        )
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 400, 300, 60) for b in brands]), cohort
        )

        self.assertEqual(5, self._row(mart, "view_to_cart_rate")["brand_count"])

    def test_brand_without_cohort_is_excluded(self):
        brands = [f"b{i}" for i in range(6)]
        cohort = self.spark.createDataFrame(
            [(b, "hash-" + b, None if b == "b0" else "2-3|26k-46k", True)
             for b in brands],
            "brand_id string, brand_hash string, cohort_key string, "
            "commons_participating boolean",
        )
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 400, 300, 60) for b in brands]), cohort
        )

        self.assertEqual(5, self._row(mart, "view_to_cart_rate")["brand_count"])

    def test_window_covers_seven_days_from_the_last_day(self):
        rows = [self._daily(f"b{i}", 400, 300, 60, day=8) for i in range(6)]
        # 창 밖 (9/1 은 9/8 기준 8일 전)
        rows += [self._daily(f"b{i}", 9999, 9999, 9999, day=1) for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies(rows), self._cohort([f"b{i}" for i in range(6)])
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertEqual(date(2026, 9, 8), row["window_end_date"])
        self.assertEqual(date(2026, 9, 2), row["window_start_date"])
        self.assertEqual(0.2, row["p50"])

    def test_thresholds_are_recorded_on_every_row(self):
        """행만 보고 어떤 기준으로 계산됐는지 알 수 있어야 한다."""
        brands = [f"b{i}" for i in range(6)]
        mart = _commons_cohort_weekly(
            self._dailies([self._daily(b, 400, 300, 60) for b in brands]),
            self._cohort(brands),
            min_brand_count=3,
            min_sample_size=10,
            dominance_ratio=0.8,
        )
        row = self._row(mart, "view_to_cart_rate")

        self.assertEqual(3, row["min_brand_count"])
        self.assertEqual(10, row["min_sample_size"])
        self.assertEqual(0.8, row["dominance_ratio"])


if __name__ == "__main__":
    unittest.main()
