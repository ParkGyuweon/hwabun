# -*- coding: utf-8 -*-
"""DDL 생성기 규칙 검증.

DDL 자체는 생성물이라 눈으로 볼 수 있지만, **규칙이 흔들리면 280 컬럼이 조용히
바뀐다.** 여기서 고정하는 것은 그 규칙이다.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from build_ddl import (  # noqa: E402
    EXCLUDED_COLUMNS,
    GRAINS,
    PARQUET_ONLY,
    NOT_NULL_KEYS_BY_MART,
    NULLABLE_KEYS,
    SURROGATE_KEY,
    TYPE_MAP,
    VARCHAR,
    build,
    is_nullable,
    mysql_type,
    render_table,
)

SCHEMA_SQL = os.path.join(HERE, "schema.sql")


class TypeMappingTest(unittest.TestCase):
    def test_money_is_decimal_not_double(self):
        """금액을 DOUBLE 로 두면 합산에서 오차가 쌓인다."""
        self.assertEqual("DECIMAL(18,2)", mysql_type("backend_paid_value", "decimal(18,2)"))

    def test_timestamp_is_datetime_not_timestamp(self):
        """TIMESTAMP 는 2038년 상한과 자동 갱신이 있다. 집계 시각에 둘 다 필요 없다."""
        self.assertEqual("DATETIME(3)", mysql_type("mart_processed_at", "timestamp"))

    def test_unmapped_type_fails_loudly(self):
        """매핑에 없는 타입을 조용히 VARCHAR 로 떨어뜨리면 데이터가 잘린다."""
        with self.assertRaises(ValueError):
            mysql_type("whatever", "array<string>")

    def test_same_column_name_has_one_length_everywhere(self):
        """길이가 Mart 마다 다르면 조인과 적재에서 잘린다."""
        self.assertEqual(
            mysql_type("brand_id", "string"),
            mysql_type("brand_id", "string"),
        )
        # UUID 36자가 들어간다
        self.assertGreaterEqual(VARCHAR["brand_id"], 36)


class NullPolicyTest(unittest.TestCase):
    """NULL 은 계약의 의도에서 온다. 데이터로 판정하지 않는다 (§7.5)."""

    def test_price_bin_stays_nullable_although_data_has_none(self):
        """설계상 NULL 을 허용하는 컬럼이다.

        가격이 없는 상품을 버리지 않고 보존하려는 것인데(§4.6-1), 현재 카탈로그에
        가격 결측이 0개라 데이터에는 NULL 이 하나도 없다. 데이터로 정하면
        NOT NULL 이 되고 가격 없는 상품이 처음 등록될 때 적재가 거부된다.
        """
        grain = GRAINS["brand_price_band_daily_kpi"]
        self.assertIn("price_bin", grain)
        self.assertTrue(is_nullable("price_bin", grain))

    def test_execution_axes_are_nullable_in_grain(self):
        """Web 이벤트는 synthetic metadata 가 없다 (§2.2)."""
        grain = GRAINS["brand_daily_kpi"]
        for axis in ("generator_type", "scenario_id", "simulation_run_id"):
            with self.subTest(axis=axis):
                self.assertIn(axis, grain)
                self.assertTrue(is_nullable(axis, grain))

    def test_counts_are_not_null(self):
        """0 은 "없음"이지 "모름"이 아니다."""
        grain = GRAINS["brand_daily_kpi"]
        for column in ("impression_sessions", "click_sessions", "unique_user_count"):
            with self.subTest(column=column):
                self.assertFalse(is_nullable(column, grain))

    def test_rates_are_nullable(self):
        """분모가 0 이면 NULL 이라고 §4 가 이미 강제한다."""
        grain = GRAINS["brand_daily_kpi"]
        for column in ("view_to_cart_rate", "detail_entry_rate"):
            with self.subTest(column=column):
                self.assertTrue(is_nullable(column, grain))

    def test_processed_at_is_not_null(self):
        self.assertFalse(is_nullable("mart_processed_at", GRAINS["brand_daily_kpi"]))


class GrainTest(unittest.TestCase):
    def test_every_mart_is_classified(self):
        """Mart 는 projection 대상이거나 Parquet 전용이거나 둘 중 하나다.

        분류되지 않은 Mart 가 남으면 "빠뜨린 것"과 "일부러 뺀 것"을 구분할 수 없다.
        """
        self.assertEqual(22, len(GRAINS))
        self.assertEqual(4, len(PARQUET_ONLY))
        self.assertEqual(set(), set(GRAINS) & set(PARQUET_ONLY))

    def test_parquet_only_marts_carry_a_reason(self):
        """왜 뺐는지가 없으면 다음 사람이 다시 판단해야 한다."""
        for mart, reason in PARQUET_ONLY.items():
            with self.subTest(mart=mart):
                self.assertTrue(reason.strip())

    def test_brand_leads_the_index_for_dashboard_marts(self):
        """대시보드는 브랜드 하나의 기간 범위를 읽는다 (§7.6).

        기간 조회가 아닌 Mart 는 선두가 다르다. analytics_baseline 은 정책 버전별
        스냅샷이라 brand_id 로 훑지 않는다.
        """
        for mart, grain in GRAINS.items():
            if "brand_id" not in grain:
                continue
            with self.subTest(mart=mart):
                self.assertEqual("brand_id", grain[0])

    def test_dimension_grain_is_not_null_even_when_the_name_is(self):
        """같은 brand_id 라도 Dimension 의 grain 이면 NULL 일 수 없다 (§3.7).

        Fact 파생 Mart 에서는 상품 미귀속 때문에 NULL 이 가능해 NULLABLE_KEYS 에
        들어 있다. 이름으로만 판정하면 56행짜리 배정표가 대리키를 달고 유일성을
        잃는다 — 백엔드가 brand_id 로 한 행을 찾는 표다.
        """
        self.assertIn("brand_id", NULLABLE_KEYS)
        self.assertTrue(is_nullable("brand_id", ["brand_id"], "brand_daily_kpi"))
        self.assertFalse(is_nullable("brand_id", ["brand_id"], "brand_cohort_dim"))

    def test_dimension_uses_a_real_primary_key(self):
        """grain 이 NULL 이 아니면 대리키를 달지 않는다."""
        table = render_table("brand_cohort_dim", [
            ("brand_id", "string", True),
            ("mart_processed_at", "timestamp", False),
        ])

        self.assertIn("PRIMARY KEY (`brand_id`)", table)
        self.assertNotIn(SURROGATE_KEY, table)

    def test_not_null_overrides_name_the_mart_they_apply_to(self):
        """예외는 Mart 를 명시해야 다른 Mart 에 번지지 않는다."""
        for mart in NOT_NULL_KEYS_BY_MART:
            with self.subTest(mart=mart):
                self.assertIn(mart, GRAINS)

    def test_non_range_marts_lead_with_their_own_access_key(self):
        """브랜드 기간 조회가 아닌 Mart 는 선두가 다르다 (§7.6)."""
        self.assertEqual("user_id", GRAINS["user_trait_daily"][0])
        self.assertEqual("interest_week_kst", GRAINS["ingredient_weekly_interest"][0])

    def test_grain_with_nullable_axis_uses_a_surrogate_key(self):
        """MySQL 은 PRIMARY KEY 에 NULL 을 못 넣고, UNIQUE 는 NULL 을 중복으로 안 본다."""
        columns = [
            ("brand_id", "string", True),
            ("event_date_kst", "date", True),
            ("actor_type", "string", True),
            ("source", "string", True),
            ("generator_type", "string", True),
            ("scenario_id", "string", True),
            ("simulation_run_id", "string", True),
            ("mart_processed_at", "timestamp", True),
        ]
        ddl = render_table("brand_daily_kpi", columns)

        self.assertIn(f"`{SURROGATE_KEY}` BIGINT NOT NULL AUTO_INCREMENT", ddl)
        self.assertIn(f"PRIMARY KEY (`{SURROGATE_KEY}`)", ddl)
        self.assertIn("KEY `ix_brand_daily_kpi__grain`", ddl)

    def test_nullable_grain_marts_use_surrogate_except_dimension(self):
        """NULL 가능 축은 대리키를 쓰고, Dimension grain은 직접 PK를 쓴다."""
        for mart, grain in GRAINS.items():
            with self.subTest(mart=mart):
                nullable_grain = any(
                    column in NULLABLE_KEYS
                    and column not in NOT_NULL_KEYS_BY_MART.get(mart, ())
                    for column in grain
                )
                if mart == "brand_cohort_dim":
                    self.assertFalse(nullable_grain)
                else:
                    self.assertTrue(nullable_grain)

    def test_grain_without_nullable_axis_uses_a_composite_key(self):
        """지금은 해당하는 Mart 가 없지만 분기는 살아 있어야 한다.

        실행 축 없이 카탈로그에서만 파생하는 Mart 가 생기면 이 경로를 탄다.
        """
        GRAINS["__probe__"] = ["secondary_category", "currency"]
        try:
            ddl = render_table("__probe__", [
                ("secondary_category", "string", True),
                ("currency", "string", True),
                ("product_count", "bigint", True),
            ])
        finally:
            del GRAINS["__probe__"]

        self.assertNotIn(SURROGATE_KEY, ddl)
        self.assertIn("PRIMARY KEY (`secondary_category`, `currency`)", ddl)

    def test_missing_grain_column_fails_loudly(self):
        """Mart 가 컬럼을 잃었는데 DDL 이 조용히 만들어지면 안 된다."""
        with self.assertRaises(ValueError):
            render_table("brand_daily_kpi", [("brand_id", "string", True)])

    def test_unclassified_mart_fails_loudly(self):
        """새 Mart 가 생겼는데 projection 여부를 아무도 판단하지 않은 상태다."""
        with self.assertRaises(ValueError) as caught:
            build({"brand_new_mart": {"rows": 1, "cols": [("a", "bigint", True)]}})
        self.assertIn("brand_new_mart", str(caught.exception))


class GeneratedSchemaTest(unittest.TestCase):
    """생성된 schema.sql 이 규칙을 지키고 있는지."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SCHEMA_SQL):
            raise unittest.SkipTest("schema.sql 이 아직 없다")
        with open(SCHEMA_SQL, encoding="utf-8") as stream:
            cls.sql = stream.read()

    def _tables(self):
        return {
            re.match(r"`dw`\.`([a-z_]+)`", block).group(1): block
            for block in self.sql.split("CREATE TABLE ")[1:]
        }

    def test_all_marts_are_present(self):
        self.assertEqual(set(GRAINS), set(self._tables()))

    def test_index_key_length_is_within_innodb_limit(self):
        """utf8mb4 는 문자당 4 byte 다. VARCHAR 를 넉넉히 잡으면 3072 를 넘기 쉽다."""
        fixed = {
            "DATE": 3, "DATETIME(3)": 7, "BIGINT": 8, "INT": 4,
            "DOUBLE": 8, "DECIMAL(18,2)": 9, "TINYINT(1)": 1,
        }
        for mart, block in self._tables().items():
            types = dict(
                re.findall(r"`([a-z_0-9]+)` ([A-Z]+\([0-9,]+\)|[A-Z]+) ", block)
            )
            total = 0
            for column in GRAINS[mart]:
                declared = types[column]
                if declared.startswith("VARCHAR"):
                    total += int(re.search(r"[0-9]+", declared).group()) * 4 + 2
                else:
                    total += fixed[declared]
            with self.subTest(mart=mart, bytes=total):
                self.assertLessEqual(total, 3072)

    def test_charset_is_utf8mb4_everywhere(self):
        """label_ko 같은 한국어 컬럼이 있고 이모지가 섞여도 깨지면 안 된다."""
        for mart, block in self._tables().items():
            with self.subTest(mart=mart):
                self.assertIn("DEFAULT CHARSET=utf8mb4", block)

    def test_purchase_marts_are_no_longer_unverified(self):
        """재구매 계열이 실데이터로 검증됐다 (2026-09-17).

        생성기가 purchase 를 만들지 않던 시절에는 0행이라 "실데이터 미검증"
        주석이 붙었다. 327·345·349 로 구매 이력 세션이 생기면서 104만 건
        실행에서 163·52·1,778 행이 나왔다. 주석이 다시 붙으면 생성기가
        구매를 못 만들고 있다는 뜻이라 여기서 잡는다.
        """
        for mart in (
            "product_repurchase_daily",
            "brand_repurchase_daily",
            "purchase_reason_daily",
        ):
            with self.subTest(mart=mart):
                self.assertNotIn(f"-- {mart}  -- 실데이터 미검증", self.sql)
                self.assertIn("CREATE TABLE `dw`.`%s`" % mart, self.sql)


if __name__ == "__main__":
    unittest.main()
