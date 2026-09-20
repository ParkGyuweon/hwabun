import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import (
    EXPLORE_MIN_SAMPLE_SIZE,
    _banner_explore_share,
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class BannerExploreShareSparkTest(unittest.TestCase):
    """탐색 배정 비중은 실사용자 노출에서만 잰다.

    추천 서버는 `explore` 를 내보내지 않고(batch/serving/banners.py 의 trait_source
    계약), 합성 로그의 `explore` 는 생성기가 정한 값이다. 합성 로그에 화면 동작
    비율을 요구하면 통과할 수 있는 입력이 존재하지 않는다 (실행 검증).
    """

    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("banner-explore-share-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _impressions(self, rows):
        return self.spark.createDataFrame(
            rows, "actor_type string, trait_source string"
        )

    @staticmethod
    def _rows(actor_type, trait_source, count):
        return [(actor_type, trait_source)] * count

    def test_synthetic_only_run_is_exempt(self):
        # 합성 로그만 있으면 실사용자 표본이 0 이라 면제된다.
        frame = self._impressions(
            self._rows("synthetic", "explore", 900)
            + self._rows("synthetic", "session", 100)
        )

        result = _banner_explore_share(frame)

        self.assertTrue(result["passed"])
        self.assertEqual(0, result["user_impressions"])
        self.assertEqual(0, result["assigned"])
        self.assertIsNone(result["share"])
        self.assertIn("면제", result["note"])

    def test_synthetic_rows_never_enter_the_denominator(self):
        # 실사용자가 정상 범위여도 합성 로그가 비중을 끌어내리면 안 된다.
        frame = self._impressions(
            self._rows("user", "explore", 40)
            + self._rows("user", "session", 160)
            + self._rows("synthetic", "session", 5000)
        )

        result = _banner_explore_share(frame)

        self.assertTrue(result["passed"])
        self.assertEqual(200, result["user_impressions"])
        self.assertEqual(200, result["assigned"])
        self.assertAlmostEqual(0.2, result["share"])

    def test_coldstart_stays_out_of_the_denominator(self):
        frame = self._impressions(
            self._rows("user", "explore", 30)
            + self._rows("user", "session", 120)
            + self._rows("user", "coldstart", 400)
        )

        result = _banner_explore_share(frame)

        self.assertEqual(550, result["user_impressions"])
        self.assertEqual(150, result["assigned"])
        self.assertAlmostEqual(0.2, result["share"])
        self.assertTrue(result["passed"])

    def test_real_traffic_outside_the_range_still_fails(self):
        # 화면이 탐색을 너무 많이 섞으면 잡아야 한다.
        frame = self._impressions(
            self._rows("user", "explore", 120)
            + self._rows("user", "session", 80)
        )

        result = _banner_explore_share(frame)

        self.assertFalse(result["passed"])
        self.assertAlmostEqual(0.6, result["share"])
        self.assertNotIn("면제", result["note"])

    def test_real_traffic_with_no_explore_fails(self):
        frame = self._impressions(self._rows("user", "session", 200))

        result = _banner_explore_share(frame)

        self.assertFalse(result["passed"])
        self.assertEqual(0.0, result["share"])

    def test_small_real_sample_is_exempt(self):
        frame = self._impressions(
            self._rows("user", "session", EXPLORE_MIN_SAMPLE_SIZE - 1)
        )

        result = _banner_explore_share(frame)

        self.assertTrue(result["passed"])
        self.assertIn("면제", result["note"])


if __name__ == "__main__":
    unittest.main()
