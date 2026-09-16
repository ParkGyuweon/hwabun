import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import _parse_datatype_string
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.build_marts_job import (
    EXECUTION_AXES,
    _observed_events,
    build_mart_frames,
)
from streaming.jobs.validate_pipeline_job import (
    EXECUTION_AXES as VALIDATE_EXECUTION_AXES,
)


# product_event_fact 실제 스키마 (derive_facts_job 출력)
PRODUCT_FACT_DDL = (
    "event_id string, event_date date, event_hour timestamp, event_hour_kst timestamp, "
    "event_time timestamp, processed_at timestamp, event_name string, intent string, "
    "user_id string, identity_scope string, is_seeded boolean, persona_id string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "session_id string, page_view_id string, item_index int, product_id string, "
    "context_product_id string, sku_id string, list_id string, entry_source string, "
    "recommendation_id string, algorithm string, search_id string, section_id string, "
    "position int, banner_type string, banner_value string, banner_slot int, "
    "trait_source string, policy_version string, quantity int, purchase_quantity int, "
    "cart_size_after int, unit_price decimal(18,2), order_value decimal(18,2), "
    "item_revenue decimal(18,2), cart_value decimal(18,2), currency string, "
    "cart_id string, order_id string, variants_viewed int, added_to_cart boolean, "
    "wishlisted boolean, close_reason string, "
    "actor_type string, source string, category_id string, "
    "brand_id string, event_date_kst date"
)

SESSIONIZED_DDL = (
    "event_id string, event_date_kst date, event_time timestamp, event_name string, "
    "session_id string, user_id string, persona_id string, product_id string, "
    "brand_id string, category_id string, actor_type string, source string, "
    "scenario_id string, simulation_run_id string, generator_type string, "
    "event_order int, properties_json string, is_seeded boolean"
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
    def _event(event_id, event_name, session_id, is_seeded, minute):
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
            "is_seeded": is_seeded,
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

    def test_execution_axes_match_between_marts_and_validation(self):
        """축이 어긋나면 grain 검사가 조용히 다른 것을 재게 된다."""
        self.assertEqual(EXECUTION_AXES, VALIDATE_EXECUTION_AXES)

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

    def test_mart_function_filters_seeds_without_the_caller(self):
        """시드 제외는 Mart 정의의 일부여야 한다.

        호출부(build_mart_frames)에만 두면 Mart 함수를 직접 부르는 경로가 다른 값을
        낸다. Q5 의 brand_daily_is_deterministic_from_inputs 가 원본 Fact 에서
        _brand_daily_kpi 를 재계산해 대조하므로, 그 경로가 어긋나면 Mart 는 자기
        입력으로부터 재현되지 않는다 (Jira 235 실행 검증에서 542행 불일치로 드러남).
        """
        from streaming.jobs.build_marts_job import _brand_daily_kpi

        product_fact = self._product_fact(
            [
                self._event("i1", "product_impression", "S1", False, 1),
                self._event("v1", "product_view", "S1", False, 2),
                self._event("c1", "add_to_cart", "seed:RUN1:PC00001:P1", True, 3),
            ]
        )
        empty_funnel = self.spark.createDataFrame(
            [],
            "brand_id string, actor_type string, source string, generator_type string, "
            "scenario_id string, simulation_run_id string, session_id string, "
            "user_id string, product_id string, first_information_view_at timestamp",
        )

        # 호출부를 거치지 않고 Mart 함수를 직접 불러도 같은 결과여야 한다.
        direct = _brand_daily_kpi(product_fact, empty_funnel, "Asia/Seoul").first()
        through_frames = build_mart_frames(
            self._empty_sessionized(), product_fact, "Asia/Seoul"
        )["brand_daily_kpi"].first()

        self.assertEqual(0, direct["add_to_cart_sessions"])
        self.assertEqual(
            through_frames["add_to_cart_sessions"], direct["add_to_cart_sessions"]
        )
        self.assertEqual(
            through_frames["detail_view_sessions"], direct["detail_view_sessions"]
        )
        self.assertEqual(through_frames["view_to_cart_rate"], direct["view_to_cart_rate"])

    def test_detail_entry_paths_split_exclusively_by_first_touch(self):
        """상세 진입 경로는 배타여야 합이 detail_view_sessions 와 맞는다.

        quick_look_sessions 는 "퀵룩을 썼나" 라서 비배타로 남는다 (E2 진단의
        퀵룩 담기율 분모). 그래서 배타 판정은 direct_click_* 쪽에만 건다.
        둘 다 한 세션은 먼저 일어난 쪽으로 귀속한다.
        """
        rows = [
            # S1 퀵룩만
            self._event("s1-q", "quick_look", "S1", False, 1),
            # S2 상세만
            self._event("s2-v", "product_view", "S2", False, 1),
            # S3 퀵룩 먼저 → 상세
            self._event("s3-q", "quick_look", "S3", False, 1),
            self._event("s3-v", "product_view", "S3", False, 2),
            # S4 상세 먼저 → 퀵룩. 담기까지 간다
            self._event("s4-v", "product_view", "S4", False, 1),
            self._event("s4-q", "quick_look", "S4", False, 2),
            self._event("s4-c", "add_to_cart", "S4", False, 3),
        ]

        frames = build_mart_frames(
            self._empty_sessionized(), self._product_fact(rows), "Asia/Seoul"
        )
        funnel = frames["funnel_daily_kpi"].first()
        paths = {
            row["session_id"]: row["detail_entry_path"]
            for row in frames["funnel_session_fact"]
            .select("session_id", "detail_entry_path").collect()
        }

        self.assertEqual("quick_look", paths["S1"])
        self.assertEqual("direct_click", paths["S2"])
        self.assertEqual("quick_look", paths["S3"])
        self.assertEqual("direct_click", paths["S4"])

        self.assertEqual(4, funnel["detail_view_sessions"])
        self.assertEqual(2, funnel["direct_click_sessions"])       # S2 S4
        self.assertEqual(3, funnel["quick_look_sessions"])         # S1 S3 S4 (비배타)
        self.assertEqual(1, funnel["quick_look_cart_sessions"])    # S4
        self.assertEqual(1, funnel["direct_click_cart_sessions"])  # S4

        # 퀵룩 선진입(S1 S3) + direct_click(S2 S4) = detail_view(4)
        quick_look_entry = sum(1 for p in paths.values() if p == "quick_look")
        self.assertEqual(
            funnel["detail_view_sessions"],
            quick_look_entry + funnel["direct_click_sessions"],
        )
        # 비배타 컬럼끼리 더하면 안 맞는다는 것도 고정한다.
        self.assertNotEqual(
            funnel["detail_view_sessions"],
            funnel["quick_look_sessions"] + funnel["direct_click_sessions"],
        )

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
