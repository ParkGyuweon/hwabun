"""Validate invariants across the Kafka -> Raw -> Processed -> Mart outputs.

This job is intentionally a Spark batch check instead of a test that inserts
or deletes data.  It can be run after a finite K01-K16 scenario and exits with
status 1 when a pipeline invariant is broken.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_RAW_PATH = "data/raw_events"
DEFAULT_CLEANED_PATH = "data/processed/cleaned_events"
DEFAULT_BAD_PATH = "data/processed/bad_events"
DEFAULT_DUPLICATE_PATH = "data/processed/duplicate_events"
DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_SECTION_DWELL_PATH = "data/processed/section_dwell_agg"
DEFAULT_CONTENT_INTEREST_PATH = "data/processed/content_interest_fact"
DEFAULT_DIM_PRODUCT_PATH = "data/processed/dim_product"
DEFAULT_DIM_BRAND_PATH = "data/processed/dim_brand"
DEFAULT_FUNNEL_SESSION_PATH = "data/processed/funnel_session_fact"
DEFAULT_PRODUCT_DAILY_PATH = "data/marts/product_daily_kpi"
DEFAULT_FUNNEL_DAILY_PATH = "data/marts/funnel_daily_kpi"


@dataclass(frozen=True)
class ValidatePipelineConfig:
    raw_path: str = DEFAULT_RAW_PATH
    cleaned_path: str = DEFAULT_CLEANED_PATH
    bad_path: str = DEFAULT_BAD_PATH
    duplicate_path: str = DEFAULT_DUPLICATE_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    section_dwell_path: str = DEFAULT_SECTION_DWELL_PATH
    content_interest_path: str = DEFAULT_CONTENT_INTEREST_PATH
    dim_product_path: str = DEFAULT_DIM_PRODUCT_PATH
    dim_brand_path: str = DEFAULT_DIM_BRAND_PATH
    funnel_session_path: str = DEFAULT_FUNNEL_SESSION_PATH
    product_daily_path: str = DEFAULT_PRODUCT_DAILY_PATH
    funnel_daily_path: str = DEFAULT_FUNNEL_DAILY_PATH
    report_path: str | None = None
    require_events: bool = False

    def __post_init__(self) -> None:
        paths = {
            "raw_path": self.raw_path,
            "cleaned_path": self.cleaned_path,
            "bad_path": self.bad_path,
            "duplicate_path": self.duplicate_path,
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
            "section_dwell_path": self.section_dwell_path,
            "content_interest_path": self.content_interest_path,
            "dim_product_path": self.dim_product_path,
            "dim_brand_path": self.dim_brand_path,
            "funnel_session_path": self.funnel_session_path,
            "product_daily_path": self.product_daily_path,
            "funnel_daily_path": self.funnel_daily_path,
        }
        for name, value in paths.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.report_path is not None and (
            not isinstance(self.report_path, str) or not self.report_path.strip()
        ):
            raise ValueError("report_path must be a non-empty string when provided")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Kafka pipeline output invariants with Spark."
    )
    parser.add_argument("--raw-path", default=_env("RAW_EVENTS_PATH", DEFAULT_RAW_PATH))
    parser.add_argument(
        "--cleaned-path",
        default=_env("CLEANED_EVENTS_PATH", DEFAULT_CLEANED_PATH),
    )
    parser.add_argument("--bad-path", default=_env("BAD_EVENTS_PATH", DEFAULT_BAD_PATH))
    parser.add_argument(
        "--duplicate-path",
        default=_env("DUPLICATE_EVENTS_PATH", DEFAULT_DUPLICATE_PATH),
    )
    parser.add_argument(
        "--sessionized-path",
        default=_env("SESSIONIZED_EVENTS_PATH", DEFAULT_SESSIONIZED_PATH),
    )
    parser.add_argument(
        "--product-fact-path",
        default=_env("PRODUCT_EVENT_FACT_PATH", DEFAULT_PRODUCT_FACT_PATH),
    )
    parser.add_argument(
        "--section-dwell-path",
        default=_env("SECTION_DWELL_PATH", DEFAULT_SECTION_DWELL_PATH),
    )
    parser.add_argument(
        "--content-interest-path",
        default=_env("CONTENT_INTEREST_PATH", DEFAULT_CONTENT_INTEREST_PATH),
    )
    parser.add_argument(
        "--dim-product-path",
        default=_env("DIM_PRODUCT_PATH", DEFAULT_DIM_PRODUCT_PATH),
    )
    parser.add_argument(
        "--dim-brand-path",
        default=_env("DIM_BRAND_PATH", DEFAULT_DIM_BRAND_PATH),
    )
    parser.add_argument(
        "--funnel-session-path",
        default=_env("FUNNEL_SESSION_FACT_PATH", DEFAULT_FUNNEL_SESSION_PATH),
    )
    parser.add_argument(
        "--product-daily-path",
        default=_env("PRODUCT_DAILY_KPI_PATH", DEFAULT_PRODUCT_DAILY_PATH),
    )
    parser.add_argument(
        "--funnel-daily-path",
        default=_env("FUNNEL_DAILY_KPI_PATH", DEFAULT_FUNNEL_DAILY_PATH),
    )
    parser.add_argument(
        "--report-path",
        default=os.getenv("PIPELINE_VALIDATION_REPORT_PATH"),
        help="Optional local JSON report path",
    )
    parser.add_argument(
        "--require-events",
        action="store_true",
        help="Fail when raw_events is empty",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> ValidatePipelineConfig:
    args = build_parser().parse_args(argv)
    return ValidatePipelineConfig(
        raw_path=args.raw_path,
        cleaned_path=args.cleaned_path,
        bad_path=args.bad_path,
        duplicate_path=args.duplicate_path,
        sessionized_path=args.sessionized_path,
        product_fact_path=args.product_fact_path,
        section_dwell_path=args.section_dwell_path,
        content_interest_path=args.content_interest_path,
        dim_product_path=args.dim_product_path,
        dim_brand_path=args.dim_brand_path,
        funnel_session_path=args.funnel_session_path,
        product_daily_path=args.product_daily_path,
        funnel_daily_path=args.funnel_daily_path,
        report_path=args.report_path,
        require_events=args.require_events,
    )


def _duplicate_count(df: Any, columns: list[str]) -> int:
    from pyspark.sql import functions as F

    return df.groupBy(*columns).count().where(F.col("count") > 1).count()


def _synthetic_session_persona_conflict_count(cleaned: Any) -> int:
    """Count synthetic sessions that contain more than one Persona."""

    from pyspark.sql import functions as F

    return (
        cleaned.where(F.col("actor_type") == F.lit("synthetic"))
        .groupBy("simulation_run_id", "session_id")
        .agg(F.countDistinct("persona_id").alias("persona_count"))
        .where(F.col("persona_count") > 1)
        .count()
    )


def _session_sequence_collision_count(cleaned: Any) -> int:
    """Count sessions where multiple Event IDs use the same sequence number."""

    from pyspark.sql import functions as F

    return (
        cleaned.where(F.col("sequence_no").isNotNull())
        .groupBy("simulation_run_id", "session_id", "sequence_no")
        .count()
        .where(F.col("count") > 1)
        .count()
    )


def _synthetic_run_metadata_conflict_count(cleaned: Any) -> int:
    """Count synthetic runs with contradictory runtime metadata."""

    from pyspark.sql import functions as F

    return (
        cleaned.where(F.col("actor_type") == F.lit("synthetic"))
        .groupBy("simulation_run_id")
        .agg(
            F.countDistinct("scenario_id").alias("scenario_count"),
            F.countDistinct("generator_type").alias("generator_count"),
        )
        .where(
            (F.col("scenario_count") > 1)
            | (F.col("generator_count") > 1)
        )
        .count()
    )


def _raw_event_id_duplicate_group_count(raw: Any) -> int:
    """Count Raw duplicate groups; this is a warning, not a failure."""

    from pyspark.sql import functions as F

    return _duplicate_count(
        raw.where(F.col("event_id").isNotNull()),
        ["event_id"],
    )


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def _attribution_quality(fact: Any, dim_product: Any) -> dict[str, Any]:
    """Measure the row-preserving product-to-brand snapshot contract."""

    from pyspark.sql import functions as F

    dimension = dim_product.select(
        F.col("product_id").alias("_dim_product_id"),
        F.col("brand_id").alias("_expected_brand_id"),
    )
    joined = fact.alias("fact").join(
        dimension.alias("dimension"),
        F.col("fact.product_id") == F.col("dimension._dim_product_id"),
        "left",
    )
    unmatched = joined.where(F.col("_dim_product_id").isNull())
    mismatched = joined.where(
        F.col("_dim_product_id").isNotNull()
        & ~F.col("fact.brand_id").eqNullSafe(F.col("_expected_brand_id"))
    )
    samples = [
        row["product_id"]
        for row in unmatched.select(F.col("fact.product_id").alias("product_id"))
        .distinct()
        .orderBy("product_id")
        .limit(20)
        .collect()
    ]
    return {
        "fact_rows": fact.count(),
        "join_rows": joined.count(),
        "unmatched_rows": unmatched.count(),
        "unmatched_product_ids": samples,
        "brand_mismatch_rows": mismatched.count(),
        "unmatched_with_brand_rows": unmatched.where(
            F.col("fact.brand_id").isNotNull()
        ).count(),
    }


def validate_frames(frames: dict[str, Any], require_events: bool = False) -> dict[str, Any]:
    """Run cross-dataset checks and return a JSON-serializable report."""

    from pyspark.sql import functions as F

    raw = frames["raw"]
    cleaned = frames["cleaned"]
    bad = frames["bad"]
    duplicates = frames["duplicates"]
    sessionized = frames["sessionized"]
    product_fact = frames["product_fact"]
    section_dwell = frames["section_dwell"]
    content_interest = frames["content_interest"]
    dim_product = frames["dim_product"]
    dim_brand = frames["dim_brand"]
    funnel_session = frames["funnel_session"]
    product_daily = frames["product_daily"]
    funnel_daily = frames["funnel_daily"]

    counts = {
        "raw": raw.count(),
        "cleaned": cleaned.count(),
        "bad": bad.count(),
        "duplicates": duplicates.count(),
        "sessionized": sessionized.count(),
        "product_fact": product_fact.count(),
        "section_dwell": section_dwell.count(),
        "content_interest": content_interest.count(),
        "dim_product": dim_product.count(),
        "dim_brand": dim_brand.count(),
        "funnel_session": funnel_session.count(),
        "product_daily": product_daily.count(),
        "funnel_daily": funnel_daily.count(),
    }
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    checks.append(
        _check(
            "dim_product_key_is_unique",
            _duplicate_count(dim_product, ["product_id"]) == 0,
            "dim_product grain=product_id",
        )
    )
    checks.append(
        _check(
            "dim_brand_key_is_unique",
            _duplicate_count(dim_brand, ["brand_id"]) == 0,
            "dim_brand grain=brand_id",
        )
    )
    invalid_brands = dim_brand.where(
        F.col("brand_id").isNull()
        | (F.length(F.trim(F.col("brand_id"))) == 0)
        | F.col("brand_name").isNull()
        | (F.length(F.trim(F.col("brand_name"))) == 0)
    ).count()
    checks.append(
        _check(
            "dim_brand_required_fields_are_valid",
            invalid_brands == 0,
            f"invalid_rows={invalid_brands}; brand_id and brand_name are required",
        )
    )
    invalid_product_ids = dim_product.where(
        F.col("product_id").isNull()
        | (F.length(F.trim(F.col("product_id"))) == 0)
    ).count()
    checks.append(
        _check(
            "dim_product_has_valid_product_id",
            invalid_product_ids == 0,
            f"invalid_product_id_rows={invalid_product_ids}",
        )
    )
    invalid_product_brands = dim_product.where(
        F.col("brand_id").isNull() | (F.length(F.trim(F.col("brand_id"))) == 0)
    ).count()
    checks.append(
        _check(
            "dim_product_has_valid_brand_id",
            invalid_product_brands == 0,
            f"invalid_brand_rows={invalid_product_brands}; every selling product has one brand",
        )
    )
    orphan_product_brands = (
        dim_product.select("brand_id")
        .distinct()
        .join(dim_brand.select("brand_id").distinct(), ["brand_id"], "left_anti")
        .count()
    )
    checks.append(
        _check(
            "dim_product_references_dim_brand",
            orphan_product_brands == 0,
            f"orphan_brand_ids={orphan_product_brands}",
        )
    )
    brand_name_conflicts = (
        dim_product.groupBy("brand_id")
        .agg(F.countDistinct("brand_name").alias("brand_name_count"))
        .where(F.col("brand_name_count") > 1)
        .count()
    )
    checks.append(
        _check(
            "brand_id_has_one_brand_name",
            brand_name_conflicts == 0,
            f"conflicting_brand_ids={brand_name_conflicts}",
        )
    )
    checks.append(
        _check(
            "content_interest_score_is_materialized",
            content_interest.where(F.col("content_interest_score").isNull()).count()
            == 0,
            "content_interest_fact score is non-null for every content grain",
        )
    )
    raw_duplicate_groups = _raw_event_id_duplicate_group_count(raw)
    if raw_duplicate_groups:
        warnings.append(
            {
                "name": "raw_event_id_duplicates",
                "count": raw_duplicate_groups,
                "details": "Raw preserves repeated event_id values; Q2 owns canonicalization",
            }
        )

    checks.append(
        _check(
            "raw_has_events",
            not require_events or counts["raw"] > 0,
            f"raw={counts['raw']}",
        )
    )
    checks.append(
        _check(
            "cleaned_event_id_is_unique",
            _duplicate_count(cleaned, ["event_id"]) == 0,
            "cleaned_events grain=event_id",
        )
    )
    synthetic_session_persona_conflicts = _synthetic_session_persona_conflict_count(cleaned)
    checks.append(
        _check(
            "synthetic_session_has_one_persona",
            synthetic_session_persona_conflicts == 0,
            "conflicting_sessions="
            f"{synthetic_session_persona_conflicts}; "
            "grain=(simulation_run_id, session_id) has one persona_id",
        )
    )
    sequence_collisions = _session_sequence_collision_count(cleaned)
    checks.append(
        _check(
            "session_sequence_no_is_unique",
            sequence_collisions == 0,
            "conflicting_keys="
            f"{sequence_collisions}; "
            "grain=(simulation_run_id, session_id, sequence_no)",
        )
    )
    runtime_metadata_conflicts = _synthetic_run_metadata_conflict_count(cleaned)
    checks.append(
        _check(
            "synthetic_run_metadata_is_consistent",
            runtime_metadata_conflicts == 0,
            "conflicting_runs="
            f"{runtime_metadata_conflicts}; "
            "one simulation_run_id maps to one scenario_id and generator_type",
        )
    )
    checks.append(
        _check(
            "cleaned_has_no_null_event_id",
            cleaned.where(F.col("event_id").isNull()).count() == 0,
            "canonical rows require event_id",
        )
    )
    checks.append(
        _check(
            "raw_count_covers_processed_outputs",
            counts["raw"] >= counts["cleaned"] + counts["bad"],
            f"raw={counts['raw']} cleaned+bad={counts['cleaned'] + counts['bad']}",
        )
    )
    checks.append(
        _check(
            "duplicate_audit_has_canonical_event",
            duplicates.select("event_id")
            .distinct()
            .join(cleaned.select("event_id").distinct(), ["event_id"], "left_anti")
            .count()
            == 0,
            "every duplicate audit ID has one cleaned canonical row",
        )
    )
    checks.append(
        _check(
            "sessionized_matches_cleaned",
            sessionized.select("event_id").distinct()
            .join(cleaned.select("event_id").distinct(), ["event_id"], "left_anti")
            .count()
            == 0
            and cleaned.select("event_id").distinct()
            .join(sessionized.select("event_id").distinct(), ["event_id"], "left_anti")
            .count()
            == 0
            and counts["sessionized"] == counts["cleaned"]
            and _duplicate_count(sessionized, ["event_id"]) == 0,
            "sessionized is a one-to-one cleaned Event projection",
        )
    )
    checks.append(
        _check(
            "product_fact_has_product_id",
            product_fact.where(
                F.col("product_id").isNull() | (F.length(F.trim(F.col("product_id"))) == 0)
            ).count()
            == 0,
            "product fact grain requires product_id",
        )
    )
    checks.append(
        _check(
            "product_fact_references_cleaned",
            product_fact.select("event_id")
            .distinct()
            .join(cleaned.select("event_id").distinct(), ["event_id"], "left_anti")
            .count()
            == 0,
            "product facts must originate from cleaned events",
        )
    )
    checks.append(
        _check(
            "product_fact_grain_is_unique",
            _duplicate_count(product_fact, ["event_id", "item_index", "product_id"]) == 0,
            "product_event_fact grain=event_id+item_index+product_id",
        )
    )
    attribution = _attribution_quality(product_fact, dim_product)
    checks.extend(
        [
            _check(
                "product_dimension_join_preserves_row_count",
                attribution["fact_rows"] == attribution["join_rows"],
                f"before={attribution['fact_rows']} after={attribution['join_rows']}",
            ),
            _check(
                "product_fact_products_match_dimension",
                attribution["unmatched_rows"] == 0,
                "unmatched_rows="
                f"{attribution['unmatched_rows']} sample_product_ids="
                f"{attribution['unmatched_product_ids']}",
            ),
            _check(
                "product_fact_brand_snapshot_matches_dimension",
                attribution["brand_mismatch_rows"] == 0,
                f"mismatched_rows={attribution['brand_mismatch_rows']}",
            ),
            _check(
                "unmatched_product_does_not_infer_brand",
                attribution["unmatched_with_brand_rows"] == 0,
                f"violations={attribution['unmatched_with_brand_rows']}",
            ),
        ]
    )
    null_product_with_brand = sum(
        frame.where(F.col("product_id").isNull() & F.col("brand_id").isNotNull()).count()
        for frame in (sessionized, section_dwell, content_interest)
    )
    checks.append(
        _check(
            "unattributed_events_keep_null_brand",
            null_product_with_brand == 0,
            f"violations={null_product_with_brand}; no previous/session product inference",
        )
    )
    business_columns = {
        name: "business_id" in frame.columns
        for name, frame in frames.items()
        if name not in {"raw", "bad", "duplicates"}
    }
    checks.append(
        _check(
            "processed_fact_mart_contract_has_no_business_id",
            not any(business_columns.values()),
            "datasets_with_business_id="
            f"{sorted(name for name, present in business_columns.items() if present)}",
        )
    )
    checks.append(
        _check(
            "funnel_session_grain_is_unique",
            _duplicate_count(funnel_session, ["session_id", "product_id"])
            == 0,
            "funnel_session_fact grain=session_id+product_id",
        )
    )
    checks.append(
        _check(
            "product_daily_grain_is_unique",
            _duplicate_count(
                product_daily,
                [
                    "event_date_kst",
                    "product_id",
                    "actor_type",
                    "source",
                    "scenario_id",
                    "simulation_run_id",
                ],
            )
            == 0,
            "product_daily_kpi grain is unique",
        )
    )
    checks.append(
        _check(
            "funnel_daily_grain_is_unique",
            _duplicate_count(
                funnel_daily,
                [
                    "funnel_date_kst",
                    "product_id",
                    "actor_type",
                    "source",
                    "scenario_id",
                    "simulation_run_id",
                ],
            )
            == 0,
            "funnel_daily_kpi grain is unique",
        )
    )

    failures = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failures else "failed",
        "counts": counts,
        "checks": checks,
        "product_attribution": attribution,
        "warnings": warnings,
        "failure_count": len(failures),
    }


def run(spark: Any, config: ValidatePipelineConfig) -> dict[str, Any]:
    paths = {
        "raw": config.raw_path,
        "cleaned": config.cleaned_path,
        "bad": config.bad_path,
        "duplicates": config.duplicate_path,
        "sessionized": config.sessionized_path,
        "product_fact": config.product_fact_path,
        "section_dwell": config.section_dwell_path,
        "content_interest": config.content_interest_path,
        "dim_product": config.dim_product_path,
        "dim_brand": config.dim_brand_path,
        "funnel_session": config.funnel_session_path,
        "product_daily": config.product_daily_path,
        "funnel_daily": config.funnel_daily_path,
    }
    frames = {
        name: spark.read.option("mergeSchema", "true").parquet(path)
        for name, path in paths.items()
    }
    return validate_frames(frames, config.require_events)


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("validate-analytics-pipeline")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        report = run(spark, config)
    finally:
        spark.stop()

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if config.report_path:
        Path(config.report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(config.report_path, "w", encoding="utf-8") as report_file:
            report_file.write(rendered + "\n")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
