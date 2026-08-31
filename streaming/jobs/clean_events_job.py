"""Raw Parquet -> Processed Parquet canonicalization job.

Q2 reads the Raw snapshot produced by Q1, validates the common Event
contract, and selects one canonical row per ``event_id``.  The job is a batch
snapshot MVP on purpose: a late candidate can be compared with every existing
Raw candidate, so rerunning it converges to the contract's deterministic
winner.

The output is written as three datasets:

* ``cleaned_events``: one valid canonical row per event ID
* ``bad_events``: invalid rows with their Raw source coordinates and payload
* ``duplicate_events``: valid non-canonical candidates for audit

PySpark imports are lazy so the command-line configuration can be tested
without installing Spark locally.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_INPUT_PATH = "data/raw_events"
DEFAULT_CLEANED_PATH = "data/processed/cleaned_events"
DEFAULT_BAD_PATH = "data/processed/bad_events"
DEFAULT_DUPLICATE_PATH = "data/processed/duplicate_events"
DEFAULT_TIME_ZONE = "Asia/Seoul"

CANONICAL_ORDER_FIELDS = (
    "received_at",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
)

REQUIRED_FIELDS = (
    "kafka_cluster_id",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
    "schema_version",
    "event_id",
    "event_name",
    "intent",
    "event_time",
    "received_at",
    "session_id",
    "page_view_id",
    "sequence_no",
    "page_type",
    "actor_type",
    "environment",
)


@dataclass(frozen=True)
class CleanEventsConfig:
    """Runtime configuration for a Q2 full-snapshot run."""

    input_path: str = DEFAULT_INPUT_PATH
    cleaned_path: str = DEFAULT_CLEANED_PATH
    bad_path: str = DEFAULT_BAD_PATH
    duplicate_path: str = DEFAULT_DUPLICATE_PATH
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        values = {
            "input_path": self.input_path,
            "cleaned_path": self.cleaned_path,
            "bad_path": self.bad_path,
            "duplicate_path": self.duplicate_path,
            "time_zone": self.time_zone,
        }
        for name, value in values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Raw events and create canonical Processed Parquet datasets."
    )
    parser.add_argument(
        "--input-path",
        default=_env("RAW_EVENTS_PATH", DEFAULT_INPUT_PATH),
        help="Q1 raw_events Parquet path",
    )
    parser.add_argument(
        "--cleaned-path",
        default=_env("CLEANED_EVENTS_PATH", DEFAULT_CLEANED_PATH),
        help="Output path for canonical cleaned_events",
    )
    parser.add_argument(
        "--bad-path",
        default=_env("BAD_EVENTS_PATH", DEFAULT_BAD_PATH),
        help="Output path for bad_events",
    )
    parser.add_argument(
        "--duplicate-path",
        default=_env("DUPLICATE_EVENTS_PATH", DEFAULT_DUPLICATE_PATH),
        help="Output path for duplicate_events audit rows",
    )
    parser.add_argument(
        "--time-zone",
        default=_env("ANALYTICS_TIME_ZONE", DEFAULT_TIME_ZONE),
        help="Time zone used to derive event_date_kst",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> CleanEventsConfig:
    args = build_parser().parse_args(argv)
    return CleanEventsConfig(
        input_path=args.input_path,
        cleaned_path=args.cleaned_path,
        bad_path=args.bad_path,
        duplicate_path=args.duplicate_path,
        time_zone=args.time_zone,
    )


def _non_blank(column: Any) -> Any:
    from pyspark.sql import functions as F

    return column.isNotNull() & (F.length(F.trim(column.cast("string"))) > 0)


def _properties_column(raw_df: Any, field_name: str) -> Any:
    from pyspark.sql import functions as F

    return F.get_json_object(F.col("properties_json"), f"$.{field_name}")


def _validation_columns(raw_df: Any) -> dict[str, Any]:
    """Build validation expressions without mutating the input DataFrame."""

    from pyspark.sql import functions as F

    c = F.col
    required_ok = F.lit(True)
    for field in REQUIRED_FIELDS:
        required_ok = required_ok & _non_blank(c(field))

    coordinate_ok = (
        _non_blank(c("kafka_cluster_id"))
        & _non_blank(c("kafka_topic"))
        & c("kafka_partition").isNotNull()
        & c("kafka_offset").isNotNull()
    )
    sequence_ok = c("sequence_no").isNotNull() & (c("sequence_no") > 0)
    enum_ok = (
        c("event_name").rlike(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
        & c("intent").isin(
            "exposure",
            "interest",
            "comparison",
            "validation",
            "hesitation",
            "conversion",
            "friction",
            "session",
        )
        & c("page_type").isin("product_list", "product_detail", "cart")
        & c("actor_type").isin("user", "synthetic")
    )

    synthetic_properties_ok = (
        (c("actor_type") != F.lit("synthetic"))
        | (
            _non_blank(c("persona_id"))
            & _non_blank(_properties_column(raw_df, "scenario_id"))
            & _non_blank(_properties_column(raw_df, "simulation_run_id"))
            & _non_blank(_properties_column(raw_df, "generator_type"))
        )
    )

    return {
        "json_ok": c("is_json_parseable").eqNullSafe(True),
        "coordinate_ok": coordinate_ok,
        "required_ok": required_ok,
        "timestamp_ok": c("event_time").isNotNull() & c("received_at").isNotNull(),
        "sequence_ok": sequence_ok,
        "enum_ok": enum_ok,
        "synthetic_properties_ok": synthetic_properties_ok,
    }


def _bad_reason(expressions: dict[str, Any]) -> Any:
    from pyspark.sql import functions as F

    return (
        F.when(~expressions["json_ok"], F.lit("invalid_json"))
        .when(~expressions["coordinate_ok"], F.lit("missing_source_coordinate"))
        .when(~expressions["required_ok"], F.lit("missing_required_field"))
        .when(~expressions["timestamp_ok"], F.lit("invalid_timestamp"))
        .when(~expressions["sequence_ok"], F.lit("invalid_sequence_no"))
        .when(~expressions["enum_ok"], F.lit("invalid_enum"))
        .when(~expressions["synthetic_properties_ok"], F.lit("invalid_properties"))
        .otherwise(F.lit("invalid_record"))
    )


def _remove_replayed_coordinates(raw_df: Any) -> Any:
    """Keep one row for a repeated Kafka coordinate before event deduplication."""

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    coordinate_window = Window.partitionBy(
        "kafka_cluster_id", "kafka_topic", "kafka_partition", "kafka_offset"
    ).orderBy(
        F.col("raw_ingested_at").asc_nulls_last(),
        F.col("raw_value").asc_nulls_last(),
    )
    return (
        raw_df.withColumn("_coordinate_rank", F.row_number().over(coordinate_window))
        .where(F.col("_coordinate_rank") == 1)
        .drop("_coordinate_rank")
    )


def _rank_valid_candidates(valid_df: Any) -> Any:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    canonical_window = Window.partitionBy("event_id").orderBy(
        F.col("received_at").asc_nulls_last(),
        F.col("kafka_topic").asc_nulls_last(),
        F.col("kafka_partition").asc_nulls_last(),
        F.col("kafka_offset").asc_nulls_last(),
    )
    event_window = Window.partitionBy("event_id")
    return (
        valid_df.withColumn("_canonical_rank", F.row_number().over(canonical_window))
        .withColumn("_candidate_count", F.count(F.lit(1)).over(event_window))
    )


def build_processed_frames(raw_df: Any, time_zone: str) -> dict[str, Any]:
    """Return cleaned, bad, and duplicate DataFrames from a Raw snapshot."""

    from pyspark.sql import functions as F

    raw_df = _remove_replayed_coordinates(raw_df)
    expressions = _validation_columns(raw_df)
    valid_condition = F.lit(True)
    for expression in expressions.values():
        valid_condition = valid_condition & expression

    bad_events = (
        raw_df.where(~valid_condition)
        .select(
            "kafka_cluster_id",
            "kafka_topic",
            "kafka_partition",
            "kafka_offset",
            "kafka_timestamp",
            "kafka_key",
            "raw_value",
            "event_id",
            "event_time",
            "received_at",
            _bad_reason(expressions).alias("error_code"),
            F.lit("spark_semantic_validation").alias("error_stage"),
            F.current_timestamp().alias("bad_recorded_at"),
        )
    )

    ranked = _rank_valid_candidates(raw_df.where(valid_condition))
    canonical = ranked.where(F.col("_canonical_rank") == 1)

    scenario_id = _properties_column(canonical, "scenario_id")
    simulation_run_id = _properties_column(canonical, "simulation_run_id")
    generator_type = _properties_column(canonical, "generator_type")
    is_synthetic = F.col("actor_type") == F.lit("synthetic")

    cleaned_events = canonical.select(
        "event_id",
        "schema_version",
        "event_name",
        "intent",
        "event_time",
        "received_at",
        F.current_timestamp().alias("processed_at"),
        "request_id",
        F.when(is_synthetic, F.lit("simulator"))
        .otherwise(F.lit("web"))
        .alias("source"),
        "actor_type",
        is_synthetic.alias("is_synthetic"),
        F.when(is_synthetic, F.col("persona_id"))
        .otherwise(F.lit(None).cast("string"))
        .alias("user_id"),
        "persona_id",
        "session_id",
        "page_view_id",
        "sequence_no",
        "page_type",
        F.when(is_synthetic, scenario_id)
        .otherwise(F.lit(None).cast("string"))
        .alias("scenario_id"),
        F.when(is_synthetic, simulation_run_id)
        .otherwise(F.lit(None).cast("string"))
        .alias("simulation_run_id"),
        F.when(is_synthetic, generator_type)
        .otherwise(F.lit(None).cast("string"))
        .alias("generator_type"),
        "environment",
        "product_id",
        "properties_json",
        F.from_utc_timestamp(F.col("event_time"), time_zone)
        .cast("date")
        .alias("event_date_kst"),
        F.when(
            F.col("_candidate_count") > 1,
            F.array(F.lit("duplicate")),
        )
        .otherwise(F.array().cast("array<string>"))
        .alias("quality_flags"),
        F.col("_candidate_count").alias("raw_candidate_count"),
        "kafka_cluster_id",
        "kafka_topic",
        "kafka_partition",
        "kafka_offset",
        "kafka_timestamp",
        "kafka_key",
        "raw_ingested_at",
        "raw_value",
    )

    duplicate_events = ranked.where(F.col("_canonical_rank") > 1).select(
        "event_id",
        F.col("_canonical_rank").alias("canonical_rank"),
        F.col("_candidate_count").alias("candidate_count"),
        "received_at",
        "kafka_cluster_id",
        "kafka_topic",
        "kafka_partition",
        "kafka_offset",
        "raw_value",
        F.lit("event_id_duplicate").alias("audit_code"),
        F.current_timestamp().alias("audited_at"),
    )

    return {
        "cleaned_events": cleaned_events,
        "bad_events": bad_events,
        "duplicate_events": duplicate_events,
    }


def run(spark: Any, config: CleanEventsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    frames = build_processed_frames(spark.read.parquet(config.input_path), config.time_zone)
    frames["cleaned_events"].write.mode("overwrite").parquet(config.cleaned_path)
    frames["bad_events"].write.mode("overwrite").parquet(config.bad_path)
    frames["duplicate_events"].write.mode("overwrite").parquet(config.duplicate_path)


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("clean-events")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        run(spark, config)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
