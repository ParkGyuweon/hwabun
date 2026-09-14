import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

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


PURCHASE_FIELDS = (
    "order_id string",
    "product_id string",
    "brand_id string",
    "user_id string",
    "event_date_kst date",
    "event_time timestamp",
    "actor_type string",
    "source string",
    "generator_type string",
    "scenario_id string",
    "simulation_run_id string",
    "paid_value decimal(18,2)",
    "payment_method string",
    "order_channel string",
)
PURCHASE_SCHEMA = ", ".join(PURCHASE_FIELDS)
REASON_SCHEMA = (
    "order_id string, reason string, event_date_kst date, user_id string, "
    "is_primary boolean, skipped boolean, actor_type string, source string, "
    "generator_type string, scenario_id string, simulation_run_id string"
)
TRAIT_SCHEMA = (
    "trait_date_kst date, user_id string, trait string, is_primary_trait boolean"
)


PURCHASE_COLUMN_COUNT = len(PURCHASE_FIELDS)
DEFAULT_PAYMENT = (Decimal("10.00"), "kakaopay", "backend")


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
        """결제 컬럼을 생략한 행은 기본 결제(카카오페이 · backend 주문)로 채운다.

        결제 계약(299) 이전에 쓰인 픽스처가 많아 전부 다시 쓰면 무엇을 검증하던
        테스트인지 흐려진다. 결제 축을 보는 테스트만 값을 직접 준다.
        """
        padded = [
            row if len(row) == PURCHASE_COLUMN_COUNT else row + DEFAULT_PAYMENT
            for row in rows
        ]
        return self.spark.createDataFrame(padded, PURCHASE_SCHEMA)

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

    def test_payment_split_counts_orders_not_item_rows(self):
        """결제 분포는 주문 단위다. 상품 row 를 그대로 세면 장바구니 크기만큼 부푼다.

        O1 은 상품 3개짜리 한 주문이다. 주문 경로·결제수단은 각각 1로 잡혀야 하고
        실결제액도 30.00 이 아니라 30.00 한 번이어야 한다.
        """
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("30.00"), "kakaopay", "backend"),
                ("O1", "P2", "A", "U1", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("30.00"), "kakaopay", "backend"),
                ("O1", "P3", "A", "U1", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("30.00"), "kakaopay", "backend"),
            ]
        )

        row = _brand_repurchase_daily(
            purchases, self._reasons([]), 90
        ).where("brand_id = 'A'").first()

        self.assertEqual(1, row["backend_order_count"])
        self.assertEqual(1, row["kakaopay_order_count"])
        self.assertEqual(Decimal("30.00"), row["backend_paid_value"])

    def test_payment_split_separates_channel_and_method(self):
        """시연 주문(local)을 버리지 않고 축으로 가른다.

        빼버리면 재구매율이 왜 달라졌는지 되짚을 근거가 사라진다. 대신 실결제액
        합은 backend 주문만 세어 시연 금액이 섞이지 않게 한다.
        """
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("10.00"), "kakaopay", "backend"),
                ("O2", "P1", "A", "U2", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("20.00"), "card", "backend"),
                ("O3", "P1", "A", "U3", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, Decimal("99.00"), "test", "local"),
            ]
        )

        row = _product_repurchase_daily(purchases, 90).where("product_id = 'P1'").first()

        self.assertEqual(2, row["backend_order_count"])
        self.assertEqual(1, row["local_order_count"])
        self.assertEqual(1, row["kakaopay_order_count"])
        self.assertEqual(1, row["card_order_count"])
        self.assertEqual(1, row["test_order_count"])
        self.assertEqual(Decimal("30.00"), row["backend_paid_value"])
        # local 주문도 구매자 수에는 그대로 남는다 — 걸러내는 게 아니라 가르는 것이다.
        self.assertEqual(3, row["buyer_count"])

    def test_payment_split_is_zero_when_payment_keys_are_absent(self):
        """결제 계약 이전에 쌓인 주문은 분포가 0이고 NULL 이 아니다.

        NULL 이면 대시보드가 "아직 안 들어왔다"와 "0건"을 구분하지 못한다.
        """
        purchases = self._purchases(
            [
                ("O1", "P1", "A", "U1", date(2026, 9, 11), _at(11), "user", "web",
                 None, None, None, None, None, None),
            ]
        )

        row = _product_repurchase_daily(purchases, 90).where("product_id = 'P1'").first()

        self.assertEqual(0, row["backend_order_count"])
        self.assertEqual(0, row["local_order_count"])
        self.assertEqual(0, row["kakaopay_order_count"])
        self.assertIsNone(row["backend_paid_value"])



if __name__ == "__main__":
    unittest.main()
