import json
import unittest
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.validate_pipeline_job import (
    IMPRESSION_EVENTS,
    _impression_origin_report,
    _impression_origin_values,
)


ROOT = Path(__file__).resolve().parents[2]


class ImpressionOriginContractTest(unittest.TestCase):
    """허용값을 코드에 적어 두지 않고 계약 파일에서 읽는지 확인한다."""

    def test_allowed_values_come_from_event_schema_json(self):
        with open(ROOT / "contracts" / "event-schema.json", encoding="utf-8") as handle:
            schema = json.load(handle)

        declared = None
        for branch in schema.get("allOf", []):
            names = branch.get("if", {}).get("properties", {}).get("event_name", {}).get("enum")
            if set(names or ()) != set(IMPRESSION_EVENTS):
                continue
            declared = (
                branch.get("then", {})
                .get("properties", {}).get("properties", {})
                .get("properties", {}).get("impression_origin", {})
                .get("enum")
            )
            break

        self.assertEqual(declared, _impression_origin_values())


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class ImpressionOriginSparkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("impression-origin-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _cleaned(self, rows):
        return self.spark.createDataFrame(rows, "event_name string, properties_json string")

    @staticmethod
    def _props(origin):
        if origin is None:
            return '{"list_id":"search:all","position":1}'
        return json.dumps({"list_id": "search:all", "position": 1,
                           "impression_origin": origin})

    def test_contract_values_and_absence_are_accepted(self):
        """선택 property 라 값이 없는 과거 로그는 위반이 아니다."""
        frame = self._cleaned([
            ("product_impression", self._props(None)),
            ("product_impression", self._props("observed")),
            ("recommendation_impression", self._props("implied_by_click")),
            ("banner_impression", self._props("implied_by_quick_look")),
        ])

        report = _impression_origin_report(frame)

        self.assertEqual(0, report["invalid_rows"])
        self.assertEqual({}, report["invalid"])
        self.assertEqual(1, report["counts"]["(없음)"])

    def test_value_outside_the_contract_is_reported(self):
        """enum 밖 값은 Q2·수집기가 못 잡으므로 여기서 걸려야 한다."""
        frame = self._cleaned([
            ("product_impression", self._props("observed")),
            ("product_impression", self._props("synthetic")),
            ("banner_impression", self._props("hold")),
        ])

        report = _impression_origin_report(frame)

        self.assertEqual(2, report["invalid_rows"])
        self.assertEqual({"synthetic": 1, "hold": 1}, report["invalid"])

    def test_non_impression_events_are_out_of_scope(self):
        """마커는 노출 3종 계약이다. 다른 Event 의 같은 키는 보지 않는다."""
        frame = self._cleaned([
            ("product_click", self._props("synthetic")),
            ("quick_look", self._props("hold")),
        ])

        report = _impression_origin_report(frame)

        self.assertEqual(0, report["invalid_rows"])
        self.assertEqual({}, report["counts"])

    def test_distribution_is_reported_for_synthetic_share(self):
        """합성 비중 실측 근거로 분포를 남긴다 (프론트 요청 2026-09-18)."""
        frame = self._cleaned([
            ("product_impression", self._props("observed")),
            ("product_impression", self._props("observed")),
            ("product_impression", self._props("implied_by_click")),
            ("product_impression", self._props("implied_by_quick_look")),
        ])

        report = _impression_origin_report(frame)

        self.assertEqual(2, report["counts"]["observed"])
        self.assertEqual(1, report["counts"]["implied_by_click"])
        self.assertEqual(1, report["counts"]["implied_by_quick_look"])
