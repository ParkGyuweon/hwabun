import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import _parse_datatype_string
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import _observed_events, build_mart_frames


# product_event_fact 실제 스키마 (derive_facts_job 출력)
PRODUCT_FACT_DDL = (
    "event_id string, event_date date, event_hour timestamp, event_hour_kst timestamp, "
    "event_time timestamp, processed_at timestamp, event_name string, intent string, "
    "user_id string, identity_scope string, is_seed boolean, persona_id string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "session_id string, page_view_id string, item_index int, product_id string, "
    "context_product_id string, sku_id string, list_id string, entry_source string, "
    "recommendation_id string, algorithm string, search_id string, section_id string, "
    "position int, banner_type string, banner_value string, banner_slot int, "
    "trait_source string, policy_version string, quantity int, purchase_quantity int, "
    "cart_size_after int, unit_price decimal(18,2), order_value decimal(18,2), "
    "item_revenue decimal(18,2), cart_value decimal(18,2), currency string, "
    "cart_id string, order_id string, variants_viewed int, added_to_cart boolean, "
    "wishlisted boolean, actor_type string, source string, category_id string, "
    "brand_id string, event_date_kst date"
)

SESSIONIZED_DDL = (
    "event_id string, event_date_kst date, event_time timestamp, event_name string, "
    "session_id string, user_id string, persona_id string, product_id string, "
    "brand_id string, category_id string, actor_type string, source string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "event_order int, properties_json string, is_seed boolean"
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class SeedExclusionSparkTest(unittest.TestCase):
    """시드 Event는 주입된 선호 표식이라 행동 Mart 집계에서 빠져야 한다.

    긍정 시드는 조회 없이 담기만, 부정 시드는 담기 없는 조회를 낸다. 그대로 두면
    전환 지표의 분자와 분모를 양방향으로 왜곡한다 (Jira 235 실행 검증: 전체 세션의
    57%가 시드였고 brand_daily 876행 중 603행이 담기 > 조회였다).
    """

    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("seed-exclusion-test")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")
        cls.product_fact_schema = _parse_datatype_string(PRODUCT_FACT_DDL)

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _product_fact(self, rows):
        names = [field.name for field in self.product_fact_schema.fields]
        values = [tuple(row.get(name) for name in names) for row in rows]
        return self.spark.createDataFrame(values, self.product_fact_schema)

    @staticmethod
    def _event(event_id, event_name, session_id, is_seed, minute):
        moment = datetime(2026, 9, 8, 1, minute, tzinfo=timezone.utc)
        return {
            "event_id": event_id,
            "event_date": date(2026, 9, 8),
            "event_date_kst": date(2026, 9, 8),
            "event_time": moment,
            "processed_at": moment,
            "event_name": event_name,
            "intent": "interest",
            "user_id": "PC00001",
            "identity_scope": "persona",
            "is_seed": is_seed,
            "persona_id": "PC00001",
            "scenario_id": "K01",
            "simulation_run_id": "RUN1",
            "generator_type": "python_batch",
            "session_id": session_id,
            "item_index": 0,
            "product_id": "P1",
            "actor_type": "synthetic",
            "source": "simulator",
            "category_id": "C1",
            "brand_id": "B1",
        }

    def _empty_sessionized(self):
        return self.spark.createDataFrame([], SESSIONIZED_DDL)

    def test_observed_events_drops_seed_rows(self):
        frame = self._product_fact(
            [
                self._event("observed", "product_view", "S1", False, 1),
                self._event("seeded", "add_to_cart", "seed:RUN1:PC00001:P1", True, 2),
            ]
        )

        observed = _observed_events(frame)

        self.assertEqual(
            ["observed"],
            [row["event_id"] for row in observed.select("event_id").collect()],
        )

    def test_frame_without_is_seed_passes_through(self):
        """시드 판정 이전에 만들어진 입력은 그대로 통과시킨다."""
        frame = self.spark.createDataFrame(
            [("e1", "product_view")], "event_id string, event_name string"
        )

        self.assertEqual(1, _observed_events(frame).count())

    def test_none_input_stays_none(self):
        self.assertIsNone(_observed_events(None))

    def test_seed_cart_never_inflates_brand_conversion(self):
        """긍정 시드(조회 없는 담기)가 담기율을 끌어올리면 안 된다."""
        product_fact = self._product_fact(
            [
                # 관측 세션: 노출 → 상세 조회. 담지 않았다
                self._event("i1", "product_impression", "S1", False, 1),
                self._event("v1", "product_view", "S1", False, 2),
                # 시드 세션: 조회 없이 담기만 (생성기가 선호를 주입한 것)
                self._event("c1", "add_to_cart", "seed:RUN1:PC00001:P1", True, 3),
            ]
        )

        frames = build_mart_frames(
            self._empty_sessionized(), product_fact, "Asia/Seoul"
        )
        brand = frames["brand_daily_kpi"].first()

        self.assertEqual(1, brand["detail_view_sessions"])
        self.assertEqual(0, brand["add_to_cart_sessions"])
        self.assertEqual(0.0, brand["view_to_cart_rate"])

    def test_seed_view_never_deflates_brand_conversion(self):
        """부정 시드(담기 없는 조회)가 분모만 키우면 안 된다."""
        product_fact = self._product_fact(
            [
                self._event("v1", "product_view", "S1", False, 1),
                self._event("c1", "add_to_cart", "S1", False, 2),
                # 시드 세션: 조회만 남기고 담지 않는다
                self._event("v2", "product_view", "seed:RUN1:PC00001:P1", True, 3),
            ]
        )

        frames = build_mart_frames(
            self._empty_sessionized(), product_fact, "Asia/Seoul"
        )
        brand = frames["brand_daily_kpi"].first()

        self.assertEqual(1, brand["detail_view_sessions"])
        self.assertEqual(1, brand["add_to_cart_sessions"])
        self.assertEqual(1.0, brand["view_to_cart_rate"])

    def test_seed_rows_stay_out_of_the_funnel_fact(self):
        product_fact = self._product_fact(
            [
                self._event("v1", "product_view", "S1", False, 1),
                self._event("c1", "add_to_cart", "seed:RUN1:PC00001:P1", True, 2),
            ]
        )

        frames = build_mart_frames(
            self._empty_sessionized(), product_fact, "Asia/Seoul"
        )

        sessions = {
            row["session_id"]
            for row in frames["funnel_session_fact"].select("session_id").collect()
        }
        self.assertEqual({"S1"}, sessions)


if __name__ == "__main__":
    unittest.main()
