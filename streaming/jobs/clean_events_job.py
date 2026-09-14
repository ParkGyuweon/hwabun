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
RFC3339_WITH_OFFSET_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)
SUPPORTED_SCHEMA_VERSIONS = ("0.2.0-draft",)

# Keep the Q2 semantic gate explicit.  A lower_snake_case value is not enough:
# only events registered by contracts/event-schema.json may enter Cleaned, and
# each registered event has exactly one intent.  The lightweight contract test
# fails when the JSON contract changes without this projection being updated.
EVENT_INTENTS = {
    "session_start": "session",
    "login": "session",
    "page_view": "session",
    "navigation_click": "session",
    "exit_summary": "session",
    "banner_impression": "session",
    "product_impression": "exposure",
    "recommendation_impression": "exposure",
    "scroll_depth": "exposure",
    "impression_dwell": "exposure",
    "recommendation_snapshot": "exposure",
    "product_view": "interest",
    "section_view": "interest",
    "section_dwell": "interest",
    "scroll_pause": "interest",
    "media_view": "interest",
    "quick_look": "interest",
    "quick_look_close": "interest",
    "banner_click": "interest",
    "scroll_backtrack": "comparison",
    "variant_select": "comparison",
    "product_click": "comparison",
    "recommendation_click": "comparison",
    "filter_change": "comparison",
    "sort_change": "comparison",
    "accordion_toggle": "validation",
    "ingredient_view_mode_change": "validation",
    "review_expand": "validation",
    "review_filter_apply": "validation",
    "text_selection": "validation",
    "text_copy": "validation",
    "purchase_reason_select": "validation",
    "hover_dwell": "hesitation",
    "remove_from_cart": "hesitation",
    "wishlist_toggle": "conversion",
    "quantity_change": "conversion",
    "add_to_cart": "conversion",
    "view_cart": "conversion",
    "begin_checkout": "conversion",
    "purchase": "conversion",
    "payment_failed": "conversion",
    "rage_click": "friction",
    "dead_click": "friction",
}

PRODUCT_ID_REQUIRED_EVENTS = (
    "product_view",
    "product_impression",
    "product_click",
    "accordion_toggle",
    "recommendation_impression",
    "recommendation_click",
    "wishlist_toggle",
    "add_to_cart",
    "impression_dwell",
    "media_view",
    "quick_look",
    "quick_look_close",
    "remove_from_cart",
    "variant_select",
    "quantity_change",
    "review_filter_apply",
    "review_expand",
    "ingredient_view_mode_change",
    "scroll_backtrack",
    "text_selection",
    "text_copy",
    "hover_dwell",
    "banner_impression",
    "banner_click",
)
PRODUCT_DETAIL_SCOPED_EVENTS = (
    "page_view",
    "section_view",
    "section_dwell",
    "scroll_depth",
    "scroll_pause",
)

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


def _ensure_raw_projection(raw_df: Any) -> Any:
    """Add nullable columns introduced after an older Raw snapshot.

    A full-snapshot rerun can read a directory containing files written before
    the source projection was added.  Treat that column as unknown rather than
    failing before Q2 can apply the source fallback rule.  Older Raw files may
    still contain the retired storefront-scope column; the explicit Processed projection
    below ignores it.
    """

    from pyspark.sql import functions as F

    if "account_id" not in raw_df.columns:
        raw_df = raw_df.withColumn("account_id", F.lit(None).cast("string"))
    if "source" not in raw_df.columns:
        raw_df = raw_df.withColumn("source", F.lit(None).cast("string"))
    return raw_df


def _properties_column(raw_df: Any, field_name: str) -> Any:
    from pyspark.sql import functions as F

    return F.get_json_object(F.col("properties_json"), f"$.{field_name}")


def _rfc3339_with_offset(column: Any) -> Any:
    """Require an RFC 3339 timestamp that carries an explicit timezone."""

    return _non_blank(column) & column.rlike(RFC3339_WITH_OFFSET_PATTERN)


def _validation_columns(raw_df: Any) -> dict[str, Any]:
    """Build validation expressions without mutating the input DataFrame."""

    from pyspark.sql import functions as F

    c = F.col
    occurred_at_raw = F.get_json_object(c("raw_value"), "$.occurred_at")
    received_at_raw = F.get_json_object(c("raw_value"), "$.received_at")
    required_ok = F.lit(True)
    for field in REQUIRED_FIELDS:
        required_ok = required_ok & _non_blank(c(field))

    schema_version_ok = c("schema_version").isin(*SUPPORTED_SCHEMA_VERSIONS).eqNullSafe(
        True
    )
    source_missing = ~_non_blank(c("source"))
    source_ok = source_missing | (
        ((c("actor_type") == F.lit("user")) & (c("source") == F.lit("web")))
        | (
            (c("actor_type") == F.lit("synthetic"))
            & (c("source") == F.lit("simulator"))
        )
    )

    coordinate_ok = (
        _non_blank(c("kafka_cluster_id"))
        & _non_blank(c("kafka_topic"))
        & c("kafka_partition").isNotNull()
        & c("kafka_offset").isNotNull()
    )
    sequence_ok = c("sequence_no").isNotNull() & (c("sequence_no") > 0)
    event_index_ok = c("event_index").isNotNull() & (c("event_index") >= 0)
    properties_ok = _non_blank(c("properties_json")) & c("properties_json").rlike(
        r"^\s*\{.*\}\s*$"
    )
    registered_event_ok = c("event_name").isin(*EVENT_INTENTS)
    event_intent_ok = F.lit(False)
    for event_name, intent in EVENT_INTENTS.items():
        event_intent_ok = event_intent_ok | (
            (c("event_name") == F.lit(event_name)) & (c("intent") == F.lit(intent))
        )

    enum_ok = (
        registered_event_ok
        & event_intent_ok
        & c("page_type").isin("product_list", "product_detail", "cart")
        & c("actor_type").isin("user", "synthetic")
    )

    product_id_present = _non_blank(c("product_id"))
    product_id_required = c("event_name").isin(*PRODUCT_ID_REQUIRED_EVENTS) | (
        c("event_name").isin(*PRODUCT_DETAIL_SCOPED_EVENTS)
        & (c("page_type") == F.lit("product_detail"))
    )
    product_scope_ok = (c("product_id").isNull() | product_id_present) & (
        (~product_id_required) | product_id_present
    )

    # 합성 로그는 페르소나로 식별한다. 계정 식별자가 오면 두 축이 섞인다.
    identity_scope_ok = (c("actor_type") != F.lit("synthetic")) | ~_non_blank(
        c("account_id")
    )

    # 시드 표식은 생성기가 주입한 선호라 실사용자 Event에는 올 수 없다
    # (event-properties-schema.md §3.14·§7-8).
    seed_scope_ok = (c("actor_type") != F.lit("user")) | _properties_column(
        raw_df, "seeded"
    ).isNull()

    synthetic_properties_ok = (
        (c("actor_type") != F.lit("synthetic"))
        | (
            _non_blank(c("persona_id"))
            & _non_blank(_properties_column(raw_df, "scenario_id"))
            & _non_blank(_properties_column(raw_df, "simulation_run_id"))
            & _properties_column(raw_df, "generator_type").isin(
                "python_batch", "agent_llm"
            )
        )
    )

    is_banner = c("event_name").isin("banner_impression", "banner_click")
    banner_type = _properties_column(raw_df, "banner_type")
    banner_value = _properties_column(raw_df, "banner_value")
    banner_slot = _properties_column(raw_df, "banner_slot")
    trait_source = _properties_column(raw_df, "trait_source")
    banner_value_key_present = c("properties_json").rlike(
        r'"banner_value"\s*:'
    )
    banner_type_ok = banner_type.isin(
        "concern", "ingredient", "clean", "price_bin", "category", "segment", "new_brand"
    )
    banner_value_ok = banner_value_key_present & (
        ((banner_type == F.lit("new_brand")) & banner_value.isNull())
        | ((banner_type != F.lit("new_brand")) & _non_blank(banner_value))
    )
    banner_slot_ok = banner_slot.rlike(r"^[1-9][0-9]*$")
    trait_source_ok = trait_source.isin("session", "profile", "coldstart", "explore")
    banner_intent_ok = (
        ((c("event_name") == F.lit("banner_impression")) & (c("intent") == F.lit("session")))
        | ((c("event_name") == F.lit("banner_click")) & (c("intent") == F.lit("interest")))
    )
    banner_contract_ok = (~is_banner) | (
        _non_blank(c("product_id"))
        & banner_type_ok
        & banner_value_ok
        & banner_slot_ok
        & trait_source_ok
        & banner_intent_ok
        & ~c("properties_json").rlike(r'"slot"\s*:')
    )

    return {
        "json_ok": c("is_json_parseable").eqNullSafe(True),
        "coordinate_ok": coordinate_ok,
        "required_ok": required_ok,
        "schema_version_ok": schema_version_ok,
        "source_ok": source_ok,
        "timestamp_ok": c("event_time").isNotNull() & c("received_at").isNotNull(),
        "timestamp_format_ok": (
            _rfc3339_with_offset(occurred_at_raw)
            & _rfc3339_with_offset(received_at_raw)
        ),
        "sequence_ok": sequence_ok,
        "event_index_ok": event_index_ok,
        "properties_ok": properties_ok,
        "enum_ok": enum_ok,
        "product_scope_ok": product_scope_ok,
        "banner_contract_ok": banner_contract_ok,
        "synthetic_properties_ok": synthetic_properties_ok,
        "identity_scope_ok": identity_scope_ok,
        "seed_scope_ok": seed_scope_ok,
    }


def _bad_reason(expressions: dict[str, Any]) -> Any:
    from pyspark.sql import functions as F

    return (
        F.when(~expressions["json_ok"], F.lit("invalid_json"))
        .when(~expressions["coordinate_ok"], F.lit("missing_source_coordinate"))
        .when(~expressions["required_ok"], F.lit("missing_required_field"))
        .when(~expressions["schema_version_ok"], F.lit("invalid_schema_version"))
        .when(~expressions["source_ok"], F.lit("invalid_source"))
        .when(~expressions["timestamp_ok"], F.lit("invalid_timestamp"))
        .when(~expressions["timestamp_format_ok"], F.lit("invalid_timestamp_format"))
        .when(~expressions["sequence_ok"], F.lit("invalid_sequence_no"))
        .when(~expressions["event_index_ok"], F.lit("invalid_event_index"))
        .when(~expressions["properties_ok"], F.lit("invalid_properties"))
        .when(~expressions["enum_ok"], F.lit("invalid_enum"))
        .when(~expressions["product_scope_ok"], F.lit("missing_product_id"))
        .when(~expressions["banner_contract_ok"], F.lit("invalid_banner_properties"))
        .when(~expressions["synthetic_properties_ok"], F.lit("invalid_properties"))
        .when(~expressions["identity_scope_ok"], F.lit("invalid_identity_scope"))
        .when(~expressions["seed_scope_ok"], F.lit("invalid_seed_scope"))
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

    raw_df = _ensure_raw_projection(raw_df)
    raw_df = _remove_replayed_coordinates(raw_df)
    expressions = _validation_columns(raw_df)
    valid_condition = F.lit(True)
    for expression in expressions.values():
        valid_condition = valid_condition & expression

    raw_source = F.when(_non_blank(F.col("source")), F.trim(F.col("source")))
    is_synthetic = F.col("actor_type") == F.lit("synthetic")
    has_account = _non_blank(F.col("account_id"))
    # 분석 식별자는 세 갈래다. 합성 로그는 페르소나, 로그인 사용자는 계정,
    # 비로그인 사용자는 식별자 없이 session_id 로만 본다.
    user_id = (
        F.when(is_synthetic, F.col("persona_id"))
        .when(has_account, F.col("account_id"))
        .otherwise(F.lit(None).cast("string"))
    )
    identity_scope = (
        F.when(is_synthetic, F.lit("persona"))
        .when(has_account, F.lit("account"))
        .otherwise(F.lit("session"))
    )
    resolved_source = F.coalesce(
        raw_source,
        F.when(is_synthetic, F.lit("simulator")).otherwise(F.lit("web")),
    )
    bad_reason = _bad_reason(expressions)
    bad_recorded_at = F.current_timestamp()

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
            "event_name",
            "schema_version",
            "request_id",
            "event_index",
            "event_time",
            "received_at",
            "actor_type",
            resolved_source.alias("source"),
            bad_reason.alias("error_code"),
            F.lit("spark_semantic_validation").alias("error_stage"),
            F.concat(F.lit("semantic validation failed: "), bad_reason).alias(
                "error_message"
            ),
            bad_recorded_at.alias("bad_recorded_at"),
            F.to_date(bad_recorded_at).alias("bad_recorded_date"),
        )
    )

    ranked = _rank_valid_candidates(raw_df.where(valid_condition))
    canonical = ranked.where(F.col("_canonical_rank") == 1)

    scenario_id = _properties_column(canonical, "scenario_id")
    simulation_run_id = _properties_column(canonical, "simulation_run_id")
    generator_type = _properties_column(canonical, "generator_type")
    # 시드 Event는 관측된 행동이 아니라 생성기가 주입한 선호 표식이다
    # (event-properties-schema.md §3.14). 행동 Mart가 한 컬럼으로 거를 수 있어야 해서
    # cleaned_events에서 판정해 아래 Fact까지 실어 나른다. 판정 정본은
    # properties.seeded 이고 session_id 의 "seed:" 접두는 파생이라 쓰지 않는다.
    is_seeded = F.coalesce(
        _properties_column(canonical, "seeded") == F.lit("true"),
        F.lit(False),
    )
    processed_at = F.current_timestamp()
    source_fallback = raw_source.isNull()
    quality_flags = F.when(
        F.col("_candidate_count") > 1,
        F.array(F.lit("duplicate")),
    ).otherwise(F.array().cast("array<string>"))
    quality_flags = F.when(
        source_fallback,
        F.concat(quality_flags, F.array(F.lit("source_fallback"))),
    ).otherwise(quality_flags)

    cleaned_events = canonical.select(
        "event_id",
        "schema_version",
        "event_name",
        "intent",
        "event_time",
        "received_at",
        processed_at.alias("processed_at"),
        (
            F.unix_millis(F.col("received_at"))
            - F.unix_millis(F.col("event_time"))
        ).cast("long").alias("latency_ms"),
        (
            F.unix_millis(processed_at) - F.unix_millis(F.col("received_at"))
        ).cast("long").alias("processing_lag_ms"),
        "request_id",
        "event_index",
        resolved_source.alias("source"),
        "actor_type",
        is_synthetic.alias("is_synthetic"),
        user_id.alias("user_id"),
        identity_scope.alias("identity_scope"),
        is_seeded.alias("is_seeded"),
        "account_id",
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
        F.lit(None).cast("string").alias("category_id"),
        F.lit(None).cast("string").alias("brand_id"),
        _properties_column(canonical, "section_id").alias("section_id"),
        _properties_column(canonical, "content_kind").alias("content_kind"),
        _properties_column(canonical, "position").cast("int").alias("position"),
        "properties_json",
        F.from_utc_timestamp(F.col("event_time"), time_zone)
        .cast("date")
        .alias("event_date_kst"),
        quality_flags.alias("quality_flags"),
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
        F.from_utc_timestamp(F.col("event_time"), time_zone)
        .cast("date")
        .alias("event_date_kst"),
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


def _write_processed_dataset(
    frame: Any,
    path: str,
    partition_column: str | None = None,
) -> None:
    """빈 결과에 partitionBy를 걸면 데이터 파일이 없어 스키마를 다시 읽을 수 없다.

    거부도 중복도 없는 실행에서는 `bad_events`와 `duplicate_events`가 정상적으로
    0행이다. 그때 파티션 쓰기를 하면 `_SUCCESS`만 남아 Q5의 읽기가
    UNABLE_TO_INFER_SCHEMA로 실패한다. 0행이면 파티션 없이 써서 스키마를 남긴다.
    """

    writer = frame.write.mode("overwrite")
    if partition_column is not None and not frame.isEmpty():
        writer.parquet(path, partitionBy=partition_column)
    else:
        writer.parquet(path)


def run(spark: Any, config: CleanEventsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    raw_df = spark.read.option("mergeSchema", "true").parquet(config.input_path)
    frames = build_processed_frames(raw_df, config.time_zone)
    _write_processed_dataset(
        frames["cleaned_events"], config.cleaned_path, "event_date_kst"
    )
    _write_processed_dataset(
        frames["bad_events"], config.bad_path, "bad_recorded_date"
    )
    _write_processed_dataset(
        frames["duplicate_events"], config.duplicate_path, "event_date_kst"
    )


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
