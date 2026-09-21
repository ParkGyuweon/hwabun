import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import (
    PRODUCT_CLICK_UNMATCHED_WARN_RATIO,
    _unmatched_banner_click_count,
    _unmatched_click_count,
)


FACT_SCHEMA = (
    "event_name string, session_id string, product_id string, list_id string, "
    "recommendation_id string, banner_type string, banner_value string, "
    "banner_slot int, trait_source string"
)


class UnmatchedClickBaselineTest(unittest.TestCase):
    def test_warn_ratio_sits_above_both_measured_baselines(self):
        """기준선은 생성기 7.63% · e2e-336-final 8.12% 다. 임계는 그 위여야 한다."""
        self.assertGreater(PRODUCT_CLICK_UNMATCHED_WARN_RATIO, 0.0812)
        # 너무 느슨하면 합성이 깨져도 안 걸린다
        self.assertLess(PRODUCT_CLICK_UNMATCHED_WARN_RATIO, 0.25)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class UnmatchedClickSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("unmatched-click-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _facts(self, rows):
        return self.spark.createDataFrame(rows, FACT_SCHEMA)

    @staticmethod
    def _row(event, session, product, list_id=None, rec=None,
             btype=None, bvalue=None, bslot=None, trait=None):
        return (event, session, product, list_id, rec, btype, bvalue, bslot, trait)

    # ---------------------------------------------------------------- 추천 쌍

    def test_recommendation_click_with_preceding_impression_matches(self):
        facts = self._facts([
            self._row("recommendation_impression", "S1", "P1", "promo_pick", "R1"),
            self._row("recommendation_click", "S1", "P1", "promo_pick", "R1"),
        ])

        result = _unmatched_click_count(
            facts, "recommendation_click", "recommendation_impression",
            ["session_id", "product_id", "recommendation_id", "list_id"],
        )

        self.assertEqual({"total": 1, "unmatched": 0}, result)

    def test_recommendation_click_without_impression_is_unmatched(self):
        facts = self._facts([
            self._row("recommendation_impression", "S1", "P1", "promo_pick", "R1"),
            self._row("recommendation_click", "S1", "P2", "promo_pick", "R1"),
        ])

        result = _unmatched_click_count(
            facts, "recommendation_click", "recommendation_impression",
            ["session_id", "product_id", "recommendation_id", "list_id"],
        )

        self.assertEqual({"total": 1, "unmatched": 1}, result)

    def test_impression_in_another_session_does_not_match(self):
        """같은 상품이라도 다른 세션의 노출은 이 클릭의 근거가 아니다."""
        facts = self._facts([
            self._row("recommendation_impression", "S1", "P1", "promo_pick", "R1"),
            self._row("recommendation_click", "S2", "P1", "promo_pick", "R1"),
        ])

        result = _unmatched_click_count(
            facts, "recommendation_click", "recommendation_impression",
            ["session_id", "product_id", "recommendation_id", "list_id"],
        )

        self.assertEqual(1, result["unmatched"])

    # ---------------------------------------------------------------- 상품 쌍

    def test_product_pair_ignores_list_id(self):
        """`list_id` 는 product_click 의 선택 property 라 키에서 뺐다.

        목록에서 본 상품을 추천 칸에서 눌러도 매칭된다 — 면 단위 정밀도를 잃는
        대신, 값을 싣지 않는 생산자의 정상 로그가 미매칭으로 잡히지 않는다.
        """
        facts = self._facts([
            self._row("product_impression", "S1", "P1", "list_grid"),
            self._row("product_click", "S1", "P1", None),
        ])

        result = _unmatched_click_count(
            facts, "product_click", "product_impression",
            ["session_id", "product_id"],
        )

        self.assertEqual({"total": 1, "unmatched": 0}, result)

    def test_product_click_without_any_impression_is_unmatched(self):
        facts = self._facts([
            self._row("product_impression", "S1", "P1", "list_grid"),
            self._row("product_click", "S1", "P9", None),
        ])

        result = _unmatched_click_count(
            facts, "product_click", "product_impression",
            ["session_id", "product_id"],
        )

        self.assertEqual({"total": 1, "unmatched": 1}, result)

    def test_duplicate_impressions_do_not_inflate_click_count(self):
        """노출이 여러 건이어도 클릭 총수가 조인으로 부풀면 안 된다."""
        facts = self._facts([
            self._row("product_impression", "S1", "P1", "list_grid"),
            self._row("product_impression", "S1", "P1", "list_grid"),
            self._row("product_click", "S1", "P1", None),
        ])

        result = _unmatched_click_count(
            facts, "product_click", "product_impression",
            ["session_id", "product_id"],
        )

        self.assertEqual({"total": 1, "unmatched": 0}, result)

    # ---------------------------------------------------------------- 배너 쌍

    def test_banner_helper_keeps_the_existing_six_key_rule(self):
        """일반화 뒤에도 배너는 trait_source 까지 여섯 키로 본다."""
        facts = self._facts([
            self._row("banner_impression", "S1", "P1", btype="concern",
                      bvalue="pore", bslot=1, trait="session"),
            # 같은 배너인데 trait_source 만 다르면 짝이 아니다
            self._row("banner_click", "S1", "P1", btype="concern",
                      bvalue="pore", bslot=1, trait="explore"),
        ])

        self.assertEqual(1, _unmatched_banner_click_count(facts))

    def test_banner_new_brand_null_value_still_matches(self):
        """new_brand 는 banner_value 가 NULL 이다. eqNullSafe 라 짝이 맞아야 한다."""
        facts = self._facts([
            self._row("banner_impression", "S1", "P1", btype="new_brand",
                      bvalue=None, bslot=1, trait="coldstart"),
            self._row("banner_click", "S1", "P1", btype="new_brand",
                      bvalue=None, bslot=1, trait="coldstart"),
        ])

        self.assertEqual(0, _unmatched_banner_click_count(facts))
