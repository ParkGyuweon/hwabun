"""섹션 정본 라벨 보정 (dw-schema.md §4.4).

성분 섹션은 화면이 `section_view` 에 `content_kind` 를 싣지 않는데 같은 섹션의
`text_selection` 은 싣는다. `content_kind` 가 그룹 키라 한 섹션이 두 행으로 갈리고,
드래그만 있는 쪽은 조회 0 에 세션만 남는다. 운영 마트에서 `ingredient_list` 가
조회 0 · 세션 3,430 으로 나온 것이 이 모양이다.
"""

import unittest
from datetime import date, datetime, timezone

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        BooleanType,
        DateType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )
except ImportError:  # Spark integration runs in the project Spark image.
    SparkSession = None

from streaming.jobs.derive_facts_job import (
    _content_interest_fact,
    _load_behavior_weights,
    _section_content_kind_map,
    _section_dwell_agg,
)


@unittest.skipUnless(SparkSession is not None, "pyspark is not installed")
class SectionContentKindBackfillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("content-kind-backfill-test")
            .getOrCreate()
        )
        cls.weights = _load_behavior_weights()

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _cleaned(self, rows):
        schema = StructType(
            [
                StructField("event_id", StringType(), False),
                StructField("event_date_kst", DateType(), False),
                StructField("event_time", TimestampType(), False),
                StructField("processed_at", TimestampType(), False),
                StructField("event_name", StringType(), False),
                StructField("intent", StringType(), False),
                StructField("user_id", StringType(), True),
                StructField("identity_scope", StringType(), True),
                StructField("is_seeded", BooleanType(), False),
                StructField("persona_id", StringType(), True),
                StructField("scenario_id", StringType(), True),
                StructField("simulation_run_id", StringType(), True),
                StructField("generator_type", StringType(), True),
                StructField("session_id", StringType(), False),
                StructField("page_view_id", StringType(), False),
                StructField("product_id", StringType(), True),
                StructField("actor_type", StringType(), False),
                StructField("source", StringType(), False),
                StructField("properties_json", StringType(), False),
            ]
        )
        now = datetime(2026, 9, 20, 1, 2, 3, tzinfo=timezone.utc).replace(tzinfo=None)
        values = [
            (
                event_id, date(2026, 9, 20), now, now, event_name, "interest",
                "U1", "persona", False, "PE1", "SC1", "RUN1", "python_batch",
                "S1", "PV1", "P1", "synthetic", "simulator", properties_json,
            )
            for event_id, event_name, properties_json in rows
        ]
        return self.spark.createDataFrame(values, schema)

    def _dimension(self):
        return self.spark.createDataFrame(
            [("P1", "C1", "B1")], ["product_id", "category_id", "brand_id"]
        )

    def _facts(self, cleaned):
        section_kind = _section_content_kind_map(cleaned)
        dwell = _section_dwell_agg(cleaned, self._dimension(), section_kind)
        return _content_interest_fact(
            cleaned, dwell, self.weights, self._dimension(), section_kind
        )

    @staticmethod
    def _view(event_id, section_id):
        """화면이 라벨을 안 싣는 조회 Event."""
        return (event_id, "section_view", '{"section_id": "%s"}' % section_id)

    @staticmethod
    def _select(event_id, section_id, content_kind):
        """같은 섹션에서 라벨을 싣는 드래그 Event."""
        return (
            event_id, "text_selection",
            '{"section_id": "%s", "content_kind": "%s"}' % (section_id, content_kind),
        )

    def test_single_label_section_merges_into_one_row(self):
        """라벨이 하나뿐인 섹션은 조회와 드래그가 한 행으로 합쳐진다.

        합치지 않으면 드래그 행이 view_count=0 인 채 세션만 갖고 남아
        `section_view_sessions > section_view_count` 가 된다.
        """
        cleaned = self._cleaned([
            self._view("v1", "ingredients"),
            self._select("s1", "ingredients", "ingredient_list"),
        ])

        rows = [r for r in self._facts(cleaned).collect() if r["section_id"] == "ingredients"]

        self.assertEqual(1, len(rows), "두 행으로 갈리면 안 된다")
        self.assertEqual("ingredient_list", rows[0]["content_kind"])
        self.assertEqual(1, rows[0]["view_count"])
        self.assertEqual(1, rows[0]["text_select_count"])

    def test_how_to_use_is_backfilled_the_same_way(self):
        """`how_to_use` 도 같은 모양이다 — 운영에서 조회 4,191 건이 라벨 없이 남아 있었다."""
        cleaned = self._cleaned([
            self._view("v1", "how_to_use"),
            self._select("s1", "how_to_use", "usage_guide"),
        ])

        rows = [r for r in self._facts(cleaned).collect() if r["section_id"] == "how_to_use"]

        self.assertEqual(1, len(rows))
        self.assertEqual("usage_guide", rows[0]["content_kind"])
        self.assertEqual(1, rows[0]["view_count"])

    def test_multi_label_section_is_left_alone(self):
        """라벨이 둘 이상인 섹션은 어느 것으로 채울 근거가 없어 건드리지 않는다.

        `about_product` 는 운영에서 라벨 8 종이 한 섹션에 붙어 있다.
        """
        cleaned = self._cleaned([
            self._view("v1", "about_product"),
            self._select("s1", "about_product", "ingredient_list"),
            self._select("s2", "about_product", "what_it_is"),
        ])

        rows = self._facts(cleaned).collect()
        kinds = sorted(
            "NULL" if r["content_kind"] is None else r["content_kind"]
            for r in rows if r["section_id"] == "about_product"
        )

        self.assertEqual(["NULL", "ingredient_list", "what_it_is"], kinds)

    def test_section_without_any_label_stays_null(self):
        """관측된 라벨이 없으면 만들어 내지 않는다."""
        cleaned = self._cleaned([self._view("v1", "list_controls")])

        rows = [r for r in self._facts(cleaned).collect() if r["section_id"] == "list_controls"]

        self.assertEqual(1, len(rows))
        self.assertIsNone(rows[0]["content_kind"])

    def test_map_is_deterministic_across_recomputation(self):
        """재계산 결정성. `F.first` 를 쓰면 셔플 순서를 타 여기서 갈린다."""
        cleaned = self._cleaned([
            self._view("v1", "ingredients"),
            self._select("s1", "ingredients", "ingredient_list"),
            self._view("v2", "how_to_use"),
            self._select("s2", "how_to_use", "usage_guide"),
        ])

        first = sorted(tuple(r) for r in _section_content_kind_map(cleaned).collect())
        second = sorted(tuple(r) for r in _section_content_kind_map(cleaned).collect())

        self.assertEqual(first, second)
        self.assertEqual(
            [("how_to_use", "usage_guide"), ("ingredients", "ingredient_list")], first
        )


if __name__ == "__main__":
    unittest.main()
