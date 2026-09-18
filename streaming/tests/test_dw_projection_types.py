# -*- coding: utf-8 -*-
"""dw projection 의 DECIMAL 지원과 계약 §7.2.1 제외 컬럼 (Jira 355).

09-18 에 마트를 dw 로 올리다 세 종이 여기서 막혔다.

  * `brand_repurchase_daily` · `product_repurchase_daily` — `Unsupported SQL type: DECIMAL(18,2)`
    `build_ddl.py:52` 는 decimal 을 알고 있는데 projection 쪽에만 분기가 없었다.
  * `product_daily_kpi` — `Parquet columns differ from DW DDL`
    계약 §7.2.1 이 `revenue_amount`·`currency` 를 **일부러** 발행에서 빼는데, 컬럼 비교가
    완전 일치라 의도적으로 뺀 둘이 오히려 발행을 막았다.

projection 은 첫 실패에서 멈추므로 한 종이 막으면 뒤가 전부 안 돈다. 그래서 이 세 종이
대시보드 개요·상품·재구매 화면을 동시에 비웠다.
"""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from streaming.jobs.dw_projection_source import (
    Column, ParquetSnapshot, ProjectionError, _decimal_spec, arrow_type, load_contract,
)

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = None

DDL = Path("contracts/dw/schema.sql")


class DecimalType(unittest.TestCase):
    """`backend_paid_value` 가 DECIMAL(18,2) 다. 백엔드 결제가 붙으면 값이 들어온다."""

    def col(self, nullable=True):
        return Column("backend_paid_value", "DECIMAL(18,2)", nullable)

    def test_스펙을_읽는다(self):
        self.assertEqual((18, 2), _decimal_spec("DECIMAL(18,2)"))
        self.assertEqual((10, 0), _decimal_spec("DECIMAL(10,0)"))

    def test_스펙이_아닌_문자열은_거절한다(self):
        with self.assertRaises(ProjectionError):
            _decimal_spec("DECIMAL")

    @unittest.skipIf(pa is None, "pyarrow is not installed")
    def test_arrow_타입이_decimal128_이다(self):
        self.assertEqual(pa.decimal128(18, 2), arrow_type(self.col()))

    def test_Decimal_값을_받는다(self):
        self.assertEqual(Decimal("12.34"), self.col().normalize(Decimal("12.34")))
        self.assertEqual(Decimal("0"), self.col().normalize(Decimal("0")))

    def test_float_은_받지_않는다(self):
        # 받아 주면 반올림이 조용히 생긴다. 다른 타입도 같은 강도로 보고 있다
        with self.assertRaises(ProjectionError):
            self.col().normalize(12.34)

    def test_스케일을_넘으면_거절한다(self):
        with self.assertRaises(ProjectionError):
            self.col().normalize(Decimal("1.234"))

    def test_정밀도를_넘으면_거절한다(self):
        with self.assertRaises(ProjectionError):
            self.col().normalize(Decimal("1234567890123456789.12"))

    def test_유한하지_않은_값을_거절한다(self):
        for bad in (Decimal("NaN"), Decimal("Infinity")):
            with self.assertRaises(ProjectionError):
                self.col().normalize(bad)

    def test_nullable_이면_None_을_통과시킨다(self):
        self.assertIsNone(self.col().normalize(None))

    def test_NOT_NULL_이면_None_을_거절한다(self):
        with self.assertRaises(ProjectionError):
            self.col(nullable=False).normalize(None)

    def test_재구매_계약이_실제로_DECIMAL_을_쓴다(self):
        for mart in ("brand_repurchase_daily", "product_repurchase_daily"):
            contract = load_contract(DDL, mart)
            column = next(c for c in contract.columns if c.name == "backend_paid_value")
            self.assertEqual("DECIMAL(18,2)", column.sql_type, mart)


class ExcludedColumns(unittest.TestCase):
    """계약 §7.2.1 — Mart 에는 있지만 발행하지 않는 컬럼."""

    def test_product_daily_kpi_가_두_컬럼을_뺀다(self):
        contract = load_contract(DDL, "product_daily_kpi")
        self.assertEqual({"revenue_amount", "currency"}, set(contract.excluded))

    def test_뺀_컬럼은_DDL_에도_없다(self):
        contract = load_contract(DDL, "product_daily_kpi")
        self.assertFalse(set(contract.excluded) & set(contract.names))

    def test_목록은_build_ddl_이_정본이다(self):
        # 하드코딩이면 생성기에서 항목을 지워도 여기가 남는다
        import importlib.util
        spec = importlib.util.spec_from_file_location("rules", DDL.with_name("build_ddl.py"))
        rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rules)
        expected = {c for (m, c) in rules.EXCLUDED_COLUMNS if m == "product_daily_kpi"}
        self.assertEqual(expected, set(load_contract(DDL, "product_daily_kpi").excluded))

    def test_다른_마트는_빼는_컬럼이_없다(self):
        for mart in ("brand_repurchase_daily", "funnel_daily_kpi", "event_daily"):
            self.assertEqual(frozenset(), load_contract(DDL, mart).excluded, mart)


@unittest.skipIf(pa is None, "pyarrow is not installed")
class ExcludedColumnsInSnapshot(unittest.TestCase):
    """Parquet 에 제외 컬럼이 **있어야** 정상이다. 없어야 하는 것이 아니다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.contract = load_contract(DDL, "product_daily_kpi")

    def row(self):
        row = {}
        for c in self.contract.columns:
            if c.name == "event_date_kst":
                row[c.name] = date(2026, 9, 17)
            elif c.sql_type == "DATE":
                row[c.name] = date(2026, 9, 17)
            elif c.sql_type == "DATETIME(3)":
                row[c.name] = datetime(2026, 9, 17, 3)
            elif c.sql_type.startswith("VARCHAR("):
                row[c.name] = "x"
            elif c.sql_type == "DOUBLE":
                row[c.name] = 0.5
            elif c.sql_type == "TINYINT(1)":
                row[c.name] = True
            else:
                row[c.name] = 1
        return row

    def write(self, extra: dict):
        """Q4 가 실제로 쓰는 모양 — DDL 컬럼 + 제외 컬럼.

        product_daily_kpi 은 MART_PARTITION_COLUMNS 가 비어 있어 Hive 분할을 쓰지 않는다.
        """
        row = {**self.row(), **extra}
        fields = [(c.name, arrow_type(c)) for c in self.contract.columns]
        for name, value in extra.items():
            fields.append((name, pa.float64() if isinstance(value, float) else pa.string()))
        table = pa.Table.from_pylist([row], schema=pa.schema(fields))
        pq.write_table(table, self.path / "part-0.parquet")
        (self.path / "_SUCCESS").touch()

    def test_제외_컬럼이_있어도_발행이_열린다(self):
        self.write({"revenue_amount": 12000.0, "currency": "KRW"})
        source = ParquetSnapshot(self.path, self.contract)      # 예전에는 여기서 죽었다
        self.assertEqual(1, source.row_count)

    def test_제외_컬럼은_MySQL_로_안_간다(self):
        self.write({"revenue_amount": 12000.0, "currency": "KRW"})
        source = ParquetSnapshot(self.path, self.contract)
        batches = list(source.batches(10))
        self.assertEqual(len(self.contract.names), len(batches[0][0]))
        self.assertNotIn("revenue_amount", self.contract.names)

    def test_제외_컬럼이_없어도_발행된다(self):
        # 계약이 "빼도 된다" 고만 하므로 Q4 가 안 써도 막지 않는다
        self.write({})
        self.assertEqual(1, ParquetSnapshot(self.path, self.contract).row_count)

    def test_계약에_없는_초과_컬럼은_여전히_막는다(self):
        self.write({"revenue_amount": 1.0, "currency": "KRW", "who_added_this": "?"})
        with self.assertRaises(ProjectionError):
            ParquetSnapshot(self.path, self.contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
