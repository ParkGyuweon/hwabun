import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None

from streaming.jobs.build_marts_job import (
    _brand_repurchase_daily,
    _product_repurchase_daily,
    _purchase_reason_daily,
    load_reason_trait_map,
)


PURCHASE_SCHEMA = (
    "order_id string, product_id string, brand_id string, user_id string, "
    "event_date_kst date, event_time timestamp, actor_type string, source string, "
    "generator_type string, scenario_id string, simulation_run_id string"
)
REASON_SCHEMA = (
    "order_id string, reason string, event_date_kst date, user_id string, "
    "is_primary boolean, skipped boolean, actor_type string, source string, "
    "generator_type string, scenario_id string, simulation_run_id string"
)
TRAIT_SCHEMA = (
    "trait_date_kst date, user_id string, trait string, is_primary_trait boolean"
)


def _at(day, hour=1):
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)


@unittest.skipIf(SparkSession is None, "pyspark is available in the Spark image")
class PurchaseMartsSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("purchase-marts-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.reason_map = load_reason_trait_map(
            "contracts/purchase-reason-trait-map.json"
        )

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _purchases(self, rows):
        return self.spark.createDataFrame(rows, PURCHASE_SCHEMA)

    def _reasons(self, rows):
        return self.spark.createDataFrame(rows, REASON_SCHEMA)

    def _base_purchases(self):
        """U1은 P1을 두 주문에 걸쳐 산다. U2는 한 번만 산다."""
        return self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web", None, None, None),
                ("O3", "P1", "A", "U2", date(2026, 9, 11), _at(11), "user", "web", None, None, None),
            ]
        )

    def test_repeat_buyer_needs_two_distinct_orders(self):
        mart = _product_repurchase_daily(self._base_purchases(), 90)
        row = mart.where("product_id = 'P1'").first()

        self.assertEqual(2, row["buyer_count"])
        self.assertEqual(1, row["repeat_buyer_count"])
        self.assertEqual(3, row["purchase_order_count"])
        self.assertEqual(0.5, row["repurchase_rate"])
        self.assertEqual(date(2026, 9, 11), row["snapshot_date_kst"])

    def test_same_order_repeated_rows_are_not_a_repurchase(self):
        """한 주문 안의 같은 상품 row가 여러 개여도 구매는 한 번이다."""
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1, 2), "user", "web", None, None, None),
            ]
        )

        row = _product_repurchase_daily(purchases, 90).first()

        self.assertEqual(1, row["buyer_count"])
        self.assertEqual(0, row["repeat_buyer_count"])
        self.assertEqual(1, row["purchase_order_count"])
        # 구매자는 있으므로 분모가 0이 아니다. 재구매가 없을 뿐이라 0.0이다.
        self.assertEqual(0.0, row["repurchase_rate"])
        self.assertIsNone(row["median_days_between_purchases"])

    def test_brand_repurchase_counts_different_products(self):
        """상품이 달라도 같은 브랜드를 다시 사면 브랜드 재구매다."""
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P2", "A", "U1", date(2026, 9, 11), _at(11), "user", "web", None, None, None),
            ]
        )
        reasons = self._reasons([])

        product_rows = _product_repurchase_daily(purchases, 90).collect()
        brand_row = _brand_repurchase_daily(purchases, reasons, 90).first()

        self.assertEqual(2, len(product_rows))
        self.assertTrue(all(row["repeat_buyer_count"] == 0 for row in product_rows))
        self.assertEqual(1, brand_row["buyer_count"])
        self.assertEqual(1, brand_row["repeat_buyer_count"])
        self.assertEqual(1.0, brand_row["repurchase_rate"])

    def test_median_interval_matches_actual_days(self):
        row = _product_repurchase_daily(self._base_purchases(), 90).first()

        self.assertAlmostEqual(10.0, row["median_days_between_purchases"], places=3)

    def test_window_excludes_older_purchases(self):
        """관측 창 밖의 첫 구매는 재구매 근거가 되지 않는다."""
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web", None, None, None),
            ]
        )

        wide = _product_repurchase_daily(purchases, 90).first()
        narrow = _product_repurchase_daily(purchases, 5).first()

        self.assertEqual(1, wide["repeat_buyer_count"])
        self.assertEqual(0, narrow["repeat_buyer_count"])
        self.assertEqual(1, narrow["purchase_order_count"])

    def test_null_brand_and_null_user_are_excluded(self):
        purchases = self._purchases(
            [
                ("O1", "P1", None, "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "   ", "U2", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O3", "P1", "A", None, date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O4", "P1", "A", "U3", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
            ]
        )

        rows = _product_repurchase_daily(purchases, 90).collect()

        self.assertEqual(1, len(rows))
        self.assertEqual("A", rows[0]["brand_id"])
        self.assertEqual(1, rows[0]["buyer_count"])

    def test_declared_restock_is_kept_beside_observed_repurchase(self):
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web", None, None, None),
            ]
        )
        reasons = self._reasons(
            [
                ("O2", "restock", date(2026, 9, 11), "U1", True, False, "user", "web", None, None, None),
                ("O1", "price", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
            ]
        )

        row = _brand_repurchase_daily(purchases, reasons, 90).first()

        self.assertEqual(1, row["repeat_buyer_count"])
        self.assertEqual(1, row["declared_restock_order_count"])

    def test_multi_brand_order_counts_reason_once_per_brand(self):
        """이유는 주문 단위 선언이라 각 브랜드에 한 번씩만 계상한다."""
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O1", "P2", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O1", "P3", "B", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
            ]
        )
        reasons = self._reasons(
            [
                ("O1", "price", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
            ]
        )

        rows = {
            row["brand_id"]: row
            for row in _purchase_reason_daily(reasons, purchases, None, self.reason_map).collect()
        }

        self.assertEqual({"A", "B"}, set(rows))
        # 브랜드 A 는 상품 두 개가 걸려 있어도 주문은 하나다.
        self.assertEqual(1, rows["A"]["order_count"])
        self.assertEqual(1, rows["B"]["order_count"])
        self.assertEqual(1.0, rows["A"]["reason_share"])

    def test_skipped_survey_does_not_pollute_share_denominator(self):
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U2", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
            ]
        )
        reasons = self._reasons(
            [
                ("O1", "price", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
                ("O2", None, date(2026, 9, 1), "U2", False, True, "user", "web", None, None, None),
            ]
        )

        rows = {
            row["reason"]: row
            for row in _purchase_reason_daily(reasons, purchases, None, self.reason_map).collect()
        }

        self.assertEqual(1, rows["price"]["order_count"])
        # 응답한 주문만 분모다. 건너뛴 주문이 들어가면 0.5 가 된다.
        self.assertEqual(1.0, rows["price"]["reason_share"])
        self.assertEqual(1, rows[None]["skipped_order_count"])
        self.assertIsNone(rows[None]["reason_share"])

    def test_trait_comparison_skips_unmapped_reasons(self):
        """texture_finish 는 성향 축에 대응이 없어 대조 분모에서 빠진다."""
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U2", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O3", "P1", "A", "U3", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
            ]
        )
        reasons = self._reasons(
            [
                ("O1", "price", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
                ("O2", "ingredient", date(2026, 9, 1), "U2", True, False, "user", "web", None, None, None),
                ("O3", "texture_finish", date(2026, 9, 1), "U3", True, False, "user", "web", None, None, None),
            ]
        )
        traits = self.spark.createDataFrame(
            [
                (date(2026, 9, 1), "U1", "price", True),
                (date(2026, 9, 1), "U2", "review", True),
                (date(2026, 9, 1), "U3", "price", True),
            ],
            TRAIT_SCHEMA,
        )

        rows = {
            row["reason"]: row
            for row in _purchase_reason_daily(reasons, purchases, traits, self.reason_map).collect()
        }

        # price 선언 + price 관측 = 일치
        self.assertEqual(1, rows["price"]["trait_compared_order_count"])
        self.assertEqual(1, rows["price"]["trait_matched_order_count"])
        self.assertEqual(1.0, rows["price"]["trait_match_rate"])
        # ingredient 선언 + review 관측 = 불일치이되 대조는 했다
        self.assertEqual(1, rows["ingredient"]["trait_compared_order_count"])
        self.assertEqual(0, rows["ingredient"]["trait_matched_order_count"])
        self.assertEqual(0.0, rows["ingredient"]["trait_match_rate"])
        # 매핑 없는 이유는 대조 자체를 하지 않는다
        self.assertEqual(0, rows["texture_finish"]["trait_compared_order_count"])
        self.assertIsNone(rows["texture_finish"]["trait_match_rate"])

    def test_brand_without_declared_restock_keeps_its_key(self):
        """선언 restock 이 없는 브랜드도 key 가 살아 있어야 한다.

        left join 뒤 같은 이름의 key 를 지우면 매칭되지 않은 행의 brand_id 가
        NULL 로 남는다. 그 행은 검증에서 통째로 걸린다.
        """
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P2", "B", "U2", date(2026, 9, 1), _at(1), "agent", "simulator", "agent_llm", "K01", "RUN1"),
            ]
        )
        reasons = self._reasons(
            [
                ("O1", "restock", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
            ]
        )

        rows = {row["brand_id"]: row for row in _brand_repurchase_daily(purchases, reasons, 90).collect()}

        self.assertEqual({"A", "B"}, set(rows))
        self.assertEqual(1, rows["A"]["declared_restock_order_count"])
        # 매칭이 없어도 0 이지 NULL 이 아니다.
        self.assertEqual(0, rows["B"]["declared_restock_order_count"])
        self.assertEqual("RUN1", rows["B"]["simulation_run_id"])

    def test_execution_axes_split_rows(self):
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 1), _at(1), "user", "web", None, None, None),
                ("O2", "P1", "A", "U2", date(2026, 9, 1), _at(1), "agent", "simulator", "agent_llm", "K01", "RUN1"),
            ]
        )

        rows = _product_repurchase_daily(purchases, 90).collect()
        keys = {(row["actor_type"], row["source"], row["simulation_run_id"]) for row in rows}

        self.assertEqual(2, len(rows))
        self.assertEqual({("user", "web", None), ("agent", "simulator", "RUN1")}, keys)

    def test_grain_is_unique_and_rebuild_is_deterministic(self):
        purchases = self._base_purchases()
        reasons = self._reasons(
            [
                ("O1", "price", date(2026, 9, 1), "U1", True, False, "user", "web", None, None, None),
            ]
        )
        cases = [
            (
                _product_repurchase_daily(purchases, 90),
                _product_repurchase_daily(purchases, 90),
                ["snapshot_date_kst", "brand_id", "product_id", "actor_type", "source", "scenario_id", "simulation_run_id"],
            ),
            (
                _brand_repurchase_daily(purchases, reasons, 90),
                _brand_repurchase_daily(purchases, reasons, 90),
                ["snapshot_date_kst", "brand_id", "actor_type", "source", "scenario_id", "simulation_run_id"],
            ),
            (
                _purchase_reason_daily(reasons, purchases, None, self.reason_map),
                _purchase_reason_daily(reasons, purchases, None, self.reason_map),
                ["event_date_kst", "brand_id", "reason", "actor_type", "source", "scenario_id", "simulation_run_id"],
            ),
        ]

        for first, second, grain in cases:
            with self.subTest(grain=grain[1]):
                columns = [c for c in first.columns if c != "mart_processed_at"]
                duplicates = first.groupBy(*grain).count().where("count > 1").count()

                self.assertEqual(0, duplicates)
                self.assertEqual(0, first.select(*columns).exceptAll(second.select(*columns)).count())
                self.assertEqual(0, second.select(*columns).exceptAll(first.select(*columns)).count())


if __name__ == "__main__":
    unittest.main()
