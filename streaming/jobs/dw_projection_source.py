"""Read a completed DW Mart snapshot using the checked-in DW DDL.

No MySQL/Spark dependency is needed to inspect the contract. PyArrow is imported
only when reading Parquet. The loader never changes grain axes or fills NULLs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import importlib.util
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MART = "user_trait_daily"
DEFAULT_DDL = ROOT / "contracts/dw/schema.sql"

# Keep the checked-in projection allowlist aligned with the DW DDL. The EC2-2
# Compose still passes the seven core Marts by default for the first rehearsal;
# callers can select any of these Marts with ``--marts``.
DEFAULT_PROJECTION_MARTS = (
    "user_trait_daily",
    "brand_daily_kpi",
    "product_daily_kpi",
    "funnel_daily_kpi",
    "brand_repurchase_daily",
    "product_repurchase_daily",
    "purchase_reason_daily",
    "persona_segment_daily_kpi",
    "brand_price_band_daily_kpi",
    "segment_price_band_daily_kpi",
    "brand_cohort_dim",
    "commons_cohort_weekly",
    "ingredient_weekly_interest",
    "product_exit_daily",
    "segment_content_daily",
    "friction_daily",
    "exit_daily",
    "entry_source_daily",
    "content_daily_kpi",
    "content_conversion_daily",
    "behavior_conversion_daily",
    "event_daily",
)

PROJECTION_MARTS = DEFAULT_PROJECTION_MARTS

MART_PARTITION_COLUMNS = {
    "user_trait_daily": ("trait_date_kst",),
    "brand_daily_kpi": ("event_date_kst",),
    "product_daily_kpi": (),
    "funnel_daily_kpi": (),
    "brand_repurchase_daily": ("snapshot_date_kst",),
    "product_repurchase_daily": ("snapshot_date_kst",),
    "purchase_reason_daily": ("event_date_kst",),
    "persona_segment_daily_kpi": ("event_date_kst",),
    "brand_price_band_daily_kpi": ("event_date_kst",),
    "segment_price_band_daily_kpi": ("event_date_kst",),
    "brand_cohort_dim": (),
    "commons_cohort_weekly": ("snapshot_week_kst",),
    "ingredient_weekly_interest": ("interest_week_kst",),
    "product_exit_daily": ("event_date_kst",),
    "segment_content_daily": ("event_date_kst",),
    "friction_daily": ("event_date_kst",),
    "exit_daily": ("event_date_kst",),
    "entry_source_daily": ("event_date_kst",),
    "content_daily_kpi": ("event_date_kst",),
    "content_conversion_daily": ("event_date_kst",),
    "behavior_conversion_daily": ("event_date_kst",),
    "event_daily": ("event_date_kst",),
}


class ProjectionError(ValueError):
    pass


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value):
        raise ProjectionError("Invalid SQL identifier")
    return f"`{value}`"


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool

    def normalize(self, value):
        # Error messages deliberately name columns, never user data.
        def invalid():
            return ProjectionError(f"Invalid value for {self.name} ({self.sql_type})")

        if value is None:
            if not self.nullable:
                raise invalid()
            return None
        if self.sql_type.startswith("VARCHAR("):
            limit = int(self.sql_type[8:-1])
            if not isinstance(value, str) or len(value) > limit:
                raise invalid()
        elif self.sql_type == "DATE":
            if not isinstance(value, date) or isinstance(value, datetime):
                raise invalid()
        elif self.sql_type == "DATETIME(3)":
            if not isinstance(value, datetime):
                raise invalid()
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            value = value.replace(microsecond=(value.microsecond // 1000) * 1000)
        elif self.sql_type in {"INT", "BIGINT"}:
            bits = 32 if self.sql_type == "INT" else 64
            if type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
                raise invalid()
        elif self.sql_type == "DOUBLE":
            if type(value) not in (int, float) or not math.isfinite(value):
                raise invalid()
        elif self.sql_type == "TINYINT(1)":
            if type(value) is not bool:
                raise invalid()
            value = int(value)
        else:
            raise ProjectionError(f"Unsupported SQL type: {self.sql_type}")
        return value


@dataclass(frozen=True)
class Contract:
    columns: tuple[Column, ...]
    grain: tuple[str, ...]
    create_sql: str
    mart: str = MART
    uses_surrogate_key: bool = True

    @property
    def names(self):
        return tuple(column.name for column in self.columns)

    def create_staging_sql(self, database: str, staging: str) -> str:
        return self.create_sql.replace(
            f"`dw`.`{self.mart}`", f"{identifier(database)}.{identifier(staging)}", 1
        )


def load_contract(path: Path = DEFAULT_DDL, mart: str = MART) -> Contract:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", mart):
        raise ProjectionError("Invalid Mart identifier")
    sql = path.read_text(encoding="utf-8")
    match = re.search(
        rf"CREATE TABLE `dw`\.`{mart}` \(\n(.*?)\n\) ENGINE=InnoDB[^;]*;",
        sql, re.DOTALL,
    )
    if not match:
        raise ProjectionError(f"Missing {mart} DDL")
    definitions = re.findall(
        r"^  `([a-z][a-z0-9_]*)` ([A-Z]+(?:\([0-9,]+\))?) (NOT NULL|NULL)([^\n]*),$",
        match[1], re.MULTILINE,
    )
    columns = tuple(Column(n, t, null == "NULL") for n, t, null, _ in definitions if n != "dw_row_id")
    surrogate = "PRIMARY KEY (`dw_row_id`)" in match[1]
    index = re.search(rf"KEY `ix_{mart}__grain` \(([^)]+)\)", match[1])
    if surrogate:
        if not index:
            raise ProjectionError("DDL with surrogate PK must contain a grain index")
        grain = tuple(re.findall(r"`([^`]+)`", index[1]))
    else:
        primary = re.search(r"PRIMARY KEY \(([^)]+)\)", match[1])
        if not primary:
            raise ProjectionError("DDL must contain a primary key")
        grain = tuple(re.findall(r"`([^`]+)`", primary[1]))
    if len(set(c.name for c in columns)) != len(columns) or not set(grain) <= {c.name for c in columns}:
        raise ProjectionError("Malformed DDL columns/grain")
    # Reuse the data team's policy without editing their generator or schema.
    spec = importlib.util.spec_from_file_location("dw_contract_rules", path.with_name("build_ddl.py"))
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    try:
        expected_grain = tuple(rules.GRAINS[mart])
    except KeyError as error:
        raise ProjectionError(f"Unknown Mart: {mart}") from error
    if grain != expected_grain:
        raise ProjectionError("DDL grain differs from build_ddl.GRAINS")
    for column in columns:
        if column.nullable != rules.is_nullable(column.name, list(grain), mart):
            raise ProjectionError(f"DDL NULL policy differs: {column.name}")
    return Contract(columns, grain, match[0], mart, uses_surrogate_key=surrogate)


def partition_columns_for(mart: str) -> tuple[str, ...]:
    try:
        return MART_PARTITION_COLUMNS[mart]
    except KeyError as error:
        raise ProjectionError(f"No partition contract for Mart: {mart}") from error


def source_path_for(root: Path, mart: str) -> Path:
    partition_columns_for(mart)
    return Path(root) / mart


def arrow_type(column: Column):
    import pyarrow as pa

    types = {"DATE": pa.date32(), "DATETIME(3)": pa.timestamp("us"),
             "BIGINT": pa.int64(), "INT": pa.int32(), "DOUBLE": pa.float64(),
             "TINYINT(1)": pa.bool_()}
    if column.sql_type.startswith("VARCHAR("):
        return pa.string()
    if column.sql_type not in types:
        raise ProjectionError(f"Unsupported SQL type: {column.sql_type}")
    return types[column.sql_type]


class ParquetSnapshot:
    """Bounded reads of a completed local Spark snapshot, including Hive dates.

    The input must not be overwritten during publication. A manifest detects
    ordinary concurrent writes before publication; it is not a filesystem lock.
    """

    def __init__(self, path: Path, contract: Contract,
                 partition_columns: tuple[str, ...] | None = None):
        import pyarrow as pa
        import pyarrow.dataset as ds
        import pyarrow.parquet as pq

        self.path = path.resolve()
        self.contract = contract
        self.partition_columns = tuple(
            partition_columns if partition_columns is not None
            else partition_columns_for(contract.mart)
        )
        self.manifest = self._manifest()
        files = sorted(self.path.rglob("*.parquet"))
        expected = {c.name: arrow_type(c) for c in contract.columns}
        # Read every physical schema: ds.dataset otherwise uses the first file
        # and can silently materialize missing nullable columns as NULL.
        for file in files:
            # Spark 3.5 writes timestamps as INT96 by default. Arrow otherwise
            # exposes these as ns (and may need pandas to produce Python values).
            physical = pq.ParquetFile(file, coerce_int96_timestamp_unit="us").schema_arrow
            fields = {field.name: field.type for field in physical}
            partitions = {}
            for part in file.relative_to(self.path).parts[:-1]:
                if "=" in part:
                    name, value = part.split("=", 1)
                    if name not in self.partition_columns or name in partitions:
                        raise ProjectionError("Unexpected partition layout")
                    if value != "__HIVE_DEFAULT_PARTITION__":
                        date.fromisoformat(value)
                    partitions[name] = pa.date32()
            if set(fields) | set(partitions) != set(expected):
                raise ProjectionError("Parquet columns differ from DW DDL")
            if set(fields) & set(partitions):
                raise ProjectionError("Partition column also stored in file")
            for name, dtype in (fields | partitions).items():
                target = expected[name]
                timestamp_ok = (pa.types.is_timestamp(dtype) and pa.types.is_timestamp(target)
                                and dtype.unit in {"ms", "us"} and dtype.tz in {None, "UTC"})
                if dtype != target and not timestamp_ok:
                    raise ProjectionError(f"Parquet type differs from DDL: {name}")

        layouts = {
            (
                frozenset(
                    name.split("=", 1)[0]
                    for part in file.relative_to(self.path).parts[:-1]
                    if "=" in part
                ),
                frozenset(
                    field.name
                    for field in pq.ParquetFile(
                        file, coerce_int96_timestamp_unit="us"
                    ).schema_arrow
                ),
            )
            for file in files
        }
        if len(layouts) != 1:
            raise ProjectionError("Parquet files use inconsistent partition layouts")
        partition_names = next(iter(layouts))[0]
        if partition_names and partition_names != set(self.partition_columns):
            raise ProjectionError("Parquet partition columns differ from Mart contract")

        partitioning = (
            ds.partitioning(
                pa.schema([(name, pa.date32()) for name in self.partition_columns]),
                flavor="hive",
            )
            if partition_names else None
        )
        parquet_format = ds.ParquetFileFormat(
            read_options=ds.ParquetReadOptions(coerce_int96_timestamp_unit="us")
        )
        self.dataset = ds.dataset([str(f) for f in files], format=parquet_format,
                                  partitioning=partitioning, partition_base_dir=str(self.path))
        self.row_count = self.dataset.count_rows()
        self.assert_unchanged()

    def _manifest(self):
        if not (self.path / "_SUCCESS").is_file():
            raise ProjectionError("Source must have a completed Spark _SUCCESS marker")
        files = sorted(self.path.rglob("*.parquet"))
        if not files:
            raise ProjectionError("Source has no Parquet schema files (not a valid empty snapshot)")
        return tuple((str(f.relative_to(self.path)), f.stat().st_size, f.stat().st_mtime_ns)
                     for f in [self.path / "_SUCCESS", *files])

    def assert_unchanged(self):
        if self._manifest() != self.manifest:
            raise ProjectionError("Source changed during projection; keep batch and projection sequential")

    def batches(self, batch_size: int):
        if batch_size <= 0:
            raise ProjectionError("batch_size must be positive")
        for batch in self.dataset.to_batches(columns=list(self.contract.names), batch_size=batch_size,
                                              batch_readahead=1, fragment_readahead=1, use_threads=False):
            yield [tuple(column.normalize(row[column.name]) for column in self.contract.columns)
                   for row in batch.to_pylist()]
        self.assert_unchanged()
