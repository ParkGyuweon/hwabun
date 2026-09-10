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
DEFAULT_PURCHASE_FACT_PATH = "data/processed/purchase_fact"
DEFAULT_PURCHASE_REASON_FACT_PATH = "data/processed/purchase_reason_fact"
DEFAULT_REVIEW_EVENT_FACT_PATH = "data/processed/review_event_fact"
DEFAULT_SECTION_DWELL_PATH = "data/processed/section_dwell_agg"
DEFAULT_CONTENT_INTEREST_PATH = "data/processed/content_interest_fact"
DEFAULT_DIM_PRODUCT_PATH = "data/processed/dim_product"
DEFAULT_DIM_BRAND_PATH = "data/processed/dim_brand"
DEFAULT_FUNNEL_SESSION_PATH = "data/processed/funnel_session_fact"
DEFAULT_PRODUCT_DAILY_PATH = "data/marts/product_daily_kpi"
DEFAULT_FUNNEL_DAILY_PATH = "data/marts/funnel_daily_kpi"
DEFAULT_BRAND_DAILY_PATH = "data/marts/brand_daily_kpi"
DEFAULT_PRODUCT_REPURCHASE_PATH = "data/marts/product_repurchase_daily"
DEFAULT_BRAND_REPURCHASE_PATH = "data/marts/brand_repurchase_daily"
DEFAULT_PURCHASE_REASON_PATH = "data/marts/purchase_reason_daily"
DEFAULT_REASON_TRAIT_MAP_PATH = "contracts/purchase-reason-trait-map.json"
DEFAULT_INGREDIENT_WEEKLY_PATH = "data/marts/ingredient_weekly_interest"
DEFAULT_CATEGORY_PRICE_PATH = "data/marts/category_price_reference"
DEFAULT_BANNER_DAILY_PATH = "data/marts/banner_daily"
DEFAULT_USER_TRAIT_DAILY_PATH = "data/marts/user_trait_daily"
DEFAULT_CROSS_BRAND_DAILY_PATH = "data/marts/cross_brand_daily"
DEFAULT_BASELINE_PATH = "data/marts/analytics_baseline"
DEFAULT_TIME_ZONE = "Asia/Seoul"


@dataclass(frozen=True)
class ValidatePipelineConfig:
    raw_path: str = DEFAULT_RAW_PATH
    cleaned_path: str = DEFAULT_CLEANED_PATH
    bad_path: str = DEFAULT_BAD_PATH
    duplicate_path: str = DEFAULT_DUPLICATE_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    purchase_fact_path: str = DEFAULT_PURCHASE_FACT_PATH
    purchase_reason_fact_path: str = DEFAULT_PURCHASE_REASON_FACT_PATH
    review_event_fact_path: str = DEFAULT_REVIEW_EVENT_FACT_PATH
    section_dwell_path: str = DEFAULT_SECTION_DWELL_PATH
    content_interest_path: str = DEFAULT_CONTENT_INTEREST_PATH
    dim_product_path: str = DEFAULT_DIM_PRODUCT_PATH
    dim_brand_path: str = DEFAULT_DIM_BRAND_PATH
    funnel_session_path: str = DEFAULT_FUNNEL_SESSION_PATH
    product_daily_path: str = DEFAULT_PRODUCT_DAILY_PATH
    funnel_daily_path: str = DEFAULT_FUNNEL_DAILY_PATH
    brand_daily_path: str = DEFAULT_BRAND_DAILY_PATH
    product_repurchase_path: str = DEFAULT_PRODUCT_REPURCHASE_PATH
    brand_repurchase_path: str = DEFAULT_BRAND_REPURCHASE_PATH
    purchase_reason_path: str = DEFAULT_PURCHASE_REASON_PATH
    reason_trait_map_path: str = DEFAULT_REASON_TRAIT_MAP_PATH
    ingredient_weekly_path: str = DEFAULT_INGREDIENT_WEEKLY_PATH
    category_price_path: str = DEFAULT_CATEGORY_PRICE_PATH
    banner_daily_path: str = DEFAULT_BANNER_DAILY_PATH
    user_trait_daily_path: str = DEFAULT_USER_TRAIT_DAILY_PATH
    cross_brand_daily_path: str = DEFAULT_CROSS_BRAND_DAILY_PATH
    baseline_path: str = DEFAULT_BASELINE_PATH
    time_zone: str = DEFAULT_TIME_ZONE
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
            "purchase_fact_path": self.purchase_fact_path,
            "purchase_reason_fact_path": self.purchase_reason_fact_path,
            "review_event_fact_path": self.review_event_fact_path,
            "section_dwell_path": self.section_dwell_path,
            "content_interest_path": self.content_interest_path,
            "dim_product_path": self.dim_product_path,
            "dim_brand_path": self.dim_brand_path,
            "funnel_session_path": self.funnel_session_path,
            "product_daily_path": self.product_daily_path,
            "funnel_daily_path": self.funnel_daily_path,
            "brand_daily_path": self.brand_daily_path,
            "product_repurchase_path": self.product_repurchase_path,
            "brand_repurchase_path": self.brand_repurchase_path,
            "purchase_reason_path": self.purchase_reason_path,
            "reason_trait_map_path": self.reason_trait_map_path,
            "ingredient_weekly_path": self.ingredient_weekly_path,
            "category_price_path": self.category_price_path,
            "banner_daily_path": self.banner_daily_path,
            "user_trait_daily_path": self.user_trait_daily_path,
            "cross_brand_daily_path": self.cross_brand_daily_path,
            "baseline_path": self.baseline_path,
        }
        for name, value in paths.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.time_zone, str) or not self.time_zone.strip():
            raise ValueError("time_zone must be a non-empty string")
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
        "--purchase-fact-path",
        default=_env("PURCHASE_FACT_PATH", DEFAULT_PURCHASE_FACT_PATH),
    )
    parser.add_argument(
        "--purchase-reason-fact-path",
        default=_env("PURCHASE_REASON_FACT_PATH", DEFAULT_PURCHASE_REASON_FACT_PATH),
    )
    parser.add_argument(
        "--review-event-fact-path",
        default=_env("REVIEW_EVENT_FACT_PATH", DEFAULT_REVIEW_EVENT_FACT_PATH),
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
        "--brand-daily-path",
        default=_env("BRAND_DAILY_KPI_PATH", DEFAULT_BRAND_DAILY_PATH),
    )
    parser.add_argument(
        "--product-repurchase-path",
        default=_env("PRODUCT_REPURCHASE_DAILY_PATH", DEFAULT_PRODUCT_REPURCHASE_PATH),
    )
    parser.add_argument(
        "--brand-repurchase-path",
        default=_env("BRAND_REPURCHASE_DAILY_PATH", DEFAULT_BRAND_REPURCHASE_PATH),
    )
    parser.add_argument(
        "--purchase-reason-path",
        default=_env("PURCHASE_REASON_DAILY_PATH", DEFAULT_PURCHASE_REASON_PATH),
    )
    parser.add_argument(
        "--reason-trait-map-path",
        default=_env("REASON_TRAIT_MAP_PATH", DEFAULT_REASON_TRAIT_MAP_PATH),
        help="Build Job과 같은 매핑이어야 구매 이유 Mart 재계산 비교가 성립한다",
    )
    parser.add_argument(
        "--ingredient-weekly-path",
        default=_env("INGREDIENT_WEEKLY_INTEREST_PATH", DEFAULT_INGREDIENT_WEEKLY_PATH),
    )
    parser.add_argument(
        "--category-price-path",
        default=_env("CATEGORY_PRICE_REFERENCE_PATH", DEFAULT_CATEGORY_PRICE_PATH),
    )
    parser.add_argument("--banner-daily-path", default=_env("BANNER_DAILY_PATH", DEFAULT_BANNER_DAILY_PATH))
    parser.add_argument("--user-trait-daily-path", default=_env("USER_TRAIT_DAILY_PATH", DEFAULT_USER_TRAIT_DAILY_PATH))
    parser.add_argument("--cross-brand-daily-path", default=_env("CROSS_BRAND_DAILY_PATH", DEFAULT_CROSS_BRAND_DAILY_PATH))
    parser.add_argument("--baseline-path", default=_env("ANALYTICS_BASELINE_PATH", DEFAULT_BASELINE_PATH))
    parser.add_argument(
        "--time-zone",
        default=_env("ANALYTICS_TIME_ZONE", DEFAULT_TIME_ZONE),
        help="Build Job과 같은 값이어야 브랜드 KPI 재계산 비교가 성립한다",
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
        purchase_fact_path=args.purchase_fact_path,
        purchase_reason_fact_path=args.purchase_reason_fact_path,
        review_event_fact_path=args.review_event_fact_path,
        section_dwell_path=args.section_dwell_path,
        content_interest_path=args.content_interest_path,
        dim_product_path=args.dim_product_path,
        dim_brand_path=args.dim_brand_path,
        funnel_session_path=args.funnel_session_path,
        product_daily_path=args.product_daily_path,
        funnel_daily_path=args.funnel_daily_path,
        brand_daily_path=args.brand_daily_path,
        product_repurchase_path=args.product_repurchase_path,
        brand_repurchase_path=args.brand_repurchase_path,
        purchase_reason_path=args.purchase_reason_path,
        reason_trait_map_path=args.reason_trait_map_path,
        ingredient_weekly_path=args.ingredient_weekly_path,
        category_price_path=args.category_price_path,
        banner_daily_path=args.banner_daily_path,
        user_trait_daily_path=args.user_trait_daily_path,
        cross_brand_daily_path=args.cross_brand_daily_path,
        baseline_path=args.baseline_path,
        time_zone=args.time_zone,
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


def _unmatched_banner_click_count(product_fact: Any) -> int:
    """A click must match an impression in the same session and banner grain."""

    from pyspark.sql import functions as F

    columns = ["session_id", "product_id", "banner_type", "banner_value", "banner_slot"]
    clicks = product_fact.where(F.col("event_name") == "banner_click").alias("click")
    impressions = (
        product_fact.where(F.col("event_name") == "banner_impression")
        .select(*columns, "trait_source")
        .dropDuplicates()
        .alias("impression")
    )
    condition = F.lit(True)
    for name in columns:
        condition = condition & F.col(f"click.{name}").eqNullSafe(F.col(f"impression.{name}"))
    condition = condition & F.col("click.trait_source").eqNullSafe(F.col("impression.trait_source"))
    return clicks.join(impressions, condition, "left_anti").count()


def validate_frames(
    frames: dict[str, Any],
    require_events: bool = False,
    time_zone: str = DEFAULT_TIME_ZONE,
    reason_trait_map_path: str = DEFAULT_REASON_TRAIT_MAP_PATH,
) -> dict[str, Any]:
    """Run cross-dataset checks and return a JSON-serializable report."""

    from pyspark.sql import functions as F

    raw = frames["raw"]
    cleaned = frames["cleaned"]
    bad = frames["bad"]
    duplicates = frames["duplicates"]
    sessionized = frames["sessionized"]
    product_fact = frames["product_fact"]
    purchase_fact = frames["purchase_fact"]
    purchase_reason_fact = frames["purchase_reason_fact"]
    review_event_fact = frames["review_event_fact"]
    section_dwell = frames["section_dwell"]
    content_interest = frames["content_interest"]
    dim_product = frames["dim_product"]
    dim_brand = frames["dim_brand"]
    funnel_session = frames["funnel_session"]
    product_daily = frames["product_daily"]
    funnel_daily = frames["funnel_daily"]
    brand_daily = frames["brand_daily"]
    product_repurchase = frames["product_repurchase"]
    brand_repurchase = frames["brand_repurchase"]
    purchase_reason = frames["purchase_reason"]
    ingredient_weekly = frames["ingredient_weekly"]
    category_price = frames["category_price"]
    banner_daily = frames["banner_daily"]
    user_trait_daily = frames["user_trait_daily"]
    cross_brand_daily = frames["cross_brand_daily"]

    counts = {
        "raw": raw.count(),
        "cleaned": cleaned.count(),
        "bad": bad.count(),
        "duplicates": duplicates.count(),
        "sessionized": sessionized.count(),
        "product_fact": product_fact.count(),
        "purchase_fact": purchase_fact.count(),
        "purchase_reason_fact": purchase_reason_fact.count(),
        "review_event_fact": review_event_fact.count(),
        "section_dwell": section_dwell.count(),
        "content_interest": content_interest.count(),
        "dim_product": dim_product.count(),
        "dim_brand": dim_brand.count(),
        "funnel_session": funnel_session.count(),
        "product_daily": product_daily.count(),
        "funnel_daily": funnel_daily.count(),
        "brand_daily": brand_daily.count(),
        "product_repurchase": product_repurchase.count(),
        "brand_repurchase": brand_repurchase.count(),
        "purchase_reason": purchase_reason.count(),
        "ingredient_weekly": ingredient_weekly.count(),
        "category_price": category_price.count(),
        "banner_daily": banner_daily.count(),
        "user_trait_daily": user_trait_daily.count(),
        "cross_brand_daily": cross_brand_daily.count(),
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
    checks.append(
        _check(
            "purchase_fact_grain_is_unique",
            _duplicate_count(purchase_fact, ["order_id", "product_id"]) == 0,
            "purchase_fact grain=order_id+product_id",
        )
    )
    invalid_purchase_rows = purchase_fact.where(
        F.col("order_id").isNull()
        | (F.length(F.trim(F.col("order_id"))) == 0)
        | F.col("product_id").isNull()
        | (F.length(F.trim(F.col("product_id"))) == 0)
        | F.col("quantity").isNull()
        | (F.col("quantity") <= 0)
        | F.col("unit_price").isNull()
        | (F.col("unit_price") < 0)
        | F.col("item_revenue").isNull()
        | (F.col("item_revenue") != F.col("quantity") * F.col("unit_price"))
    ).count()
    checks.append(
        _check(
            "purchase_fact_required_fields_are_valid",
            invalid_purchase_rows == 0,
            f"invalid_rows={invalid_purchase_rows}; revenue is behavioral only",
        )
    )
    checks.append(
        _check(
            "purchase_fact_references_purchase_events",
            purchase_fact.select("event_id")
            .distinct()
            .join(
                cleaned.where(F.col("event_name") == "purchase")
                .select("event_id")
                .distinct(),
                ["event_id"],
                "left_anti",
            )
            .count()
            == 0,
            "purchase facts must originate from cleaned purchase events",
        )
    )
    checks.append(
        _check(
            "purchase_reason_fact_grain_is_unique",
            _duplicate_count(purchase_reason_fact, ["order_id", "reason"]) == 0,
            "purchase_reason_fact grain=order_id+reason with NULL-safe skipped row",
        )
    )
    invalid_reason_rows = purchase_reason_fact.where(
        F.col("order_id").isNull()
        | (F.length(F.trim(F.col("order_id"))) == 0)
        | F.col("skipped").isNull()
        | F.col("is_primary").isNull()
        | (F.col("reason").isNull() & ~F.col("skipped"))
        | (F.col("reason").isNotNull() & F.col("skipped"))
        | (F.col("reason").isNotNull() & (F.col("reason_rank") < 1))
    ).count()
    checks.append(
        _check(
            "purchase_reason_fact_fields_are_consistent",
            invalid_reason_rows == 0,
            f"invalid_rows={invalid_reason_rows}; skipped surveys keep one NULL reason",
        )
    )
    checks.append(
        _check(
            "purchase_reason_fact_references_reason_events",
            purchase_reason_fact.select("event_id")
            .distinct()
            .join(
                cleaned.where(F.col("event_name") == "purchase_reason_select")
                .select("event_id")
                .distinct(),
                ["event_id"],
                "left_anti",
            )
            .count()
            == 0,
            "purchase reasons must originate from cleaned purchase_reason_select events",
        )
    )
    checks.append(
        _check(
            "review_event_fact_grain_is_unique",
            _duplicate_count(review_event_fact, ["event_id", "product_id"]) == 0,
            "review_event_fact grain=event_id+product_id",
        )
    )
    invalid_review_rows = review_event_fact.where(
        ~F.col("event_name").isin(
            "section_view", "section_dwell", "review_expand", "review_filter_apply"
        )
        | F.col("product_id").isNull()
        | (F.length(F.trim(F.col("product_id"))) == 0)
        | ((F.col("event_name") == "review_expand") & ~F.col("target").isin("review_text", "jump_to_reviews"))
    ).count()
    checks.append(
        _check(
            "review_event_fact_scope_is_valid",
            invalid_review_rows == 0,
            f"invalid_rows={invalid_review_rows}; ingredient expands are excluded",
        )
    )
    checks.append(
        _check(
            "review_event_fact_references_cleaned",
            review_event_fact.select("event_id")
            .distinct()
            .join(cleaned.select("event_id").distinct(), ["event_id"], "left_anti")
            .count()
            == 0,
            "review facts must originate from cleaned events",
        )
    )
    recommendation_rows = product_fact.where(
        F.col("event_name").isin("recommendation_impression", "recommendation_click")
    )
    invalid_recommendation_rows = recommendation_rows.where(
        F.col("recommendation_id").isNull()
        | (F.length(F.trim(F.col("recommendation_id"))) == 0)
        | F.col("list_id").isNull()
        | (F.length(F.trim(F.col("list_id"))) == 0)
        | F.col("algorithm").isNull()
        | (F.length(F.trim(F.col("algorithm"))) == 0)
        | F.col("position").isNull()
        | (F.col("position") < 1)
    ).count()
    checks.append(
        _check(
            "recommendation_fact_fields_are_valid",
            invalid_recommendation_rows == 0,
            f"invalid_rows={invalid_recommendation_rows}; product_event_fact is recommendation truth",
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
    for fact_name, fact_frame in (
        ("purchase_fact", purchase_fact),
        ("review_event_fact", review_event_fact),
    ):
        fact_attribution = _attribution_quality(fact_frame, dim_product)
        checks.extend(
            [
                _check(
                    f"{fact_name}_dimension_join_preserves_row_count",
                    fact_attribution["fact_rows"] == fact_attribution["join_rows"],
                    f"before={fact_attribution['fact_rows']} after={fact_attribution['join_rows']}",
                ),
                _check(
                    f"{fact_name}_brand_snapshot_matches_dimension",
                    fact_attribution["brand_mismatch_rows"] == 0,
                    f"mismatched_rows={fact_attribution['brand_mismatch_rows']}",
                ),
                _check(
                    f"{fact_name}_unmatched_product_does_not_infer_brand",
                    fact_attribution["unmatched_with_brand_rows"] == 0,
                    f"violations={fact_attribution['unmatched_with_brand_rows']}",
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
    owner_columns = {
        name: sorted({"tenant_id", "business_id"}.intersection(frame.columns))
        for name, frame in frames.items()
        if name not in {"raw", "bad", "duplicates"}
    }
    checks.append(
        _check(
            "processed_contract_has_no_tenant_or_business_id",
            not any(owner_columns.values()),
            "datasets_with_forbidden_owner_columns="
            f"{sorted((name, columns) for name, columns in owner_columns.items() if columns)}",
        )
    )
    invalid_identity_scope = cleaned.where(
        ~F.col("identity_scope").isin("persona", "account", "session")
        | ((F.col("identity_scope") == "persona") & (F.col("actor_type") != "synthetic"))
        | (
            (F.col("identity_scope") == "account")
            & (
                ~F.col("user_id").eqNullSafe(F.col("account_id"))
                | (F.length(F.trim(F.coalesce(F.col("account_id"), F.lit("")))) == 0)
            )
        )
        | ((F.col("identity_scope") == "session") & F.col("user_id").isNotNull())
        # 합성 로그와 계정 식별자는 같은 row 에 오면 안 된다.
        | ((F.col("actor_type") == "synthetic") & F.col("account_id").isNotNull())
    ).count()
    checks.append(_check(
        "cleaned_identity_scope_matches_user_id",
        invalid_identity_scope == 0,
        f"invalid_rows={invalid_identity_scope}; persona|account|session",
    ))
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
    brand_grain = [
        "event_date_kst", "brand_id", "actor_type", "source",
        "scenario_id", "simulation_run_id",
    ]
    checks.append(
        _check(
            "brand_daily_grain_is_unique",
            _duplicate_count(brand_daily, brand_grain) == 0,
            "brand_daily_kpi configured grain is unique",
        )
    )
    invalid_brand_ids = brand_daily.where(
        F.col("brand_id").isNull()
        | (F.length(F.trim(F.col("brand_id"))) == 0)
    ).count()
    checks.append(_check(
        "brand_daily_brand_id_is_valid",
        invalid_brand_ids == 0,
        f"invalid_rows={invalid_brand_ids}",
    ))
    invalid_brand_counts = brand_daily.where(
        (F.col("add_to_cart_sessions") > F.col("product_view_sessions"))
        | (F.col("information_view_sessions") > F.col("product_view_sessions"))
    ).count()
    checks.append(_check(
        "brand_daily_counts_are_bounded",
        invalid_brand_counts == 0,
        f"invalid_rows={invalid_brand_counts}",
    ))
    rate_columns = [
        "detail_entry_rate", "information_view_rate", "view_to_cart_rate"
    ]
    invalid_brand_rates = brand_daily.where(
        F.greatest(*[
            F.when(
                F.col(column).isNotNull()
                & ~F.col(column).between(0.0, 1.0),
                F.lit(1),
            ).otherwise(F.lit(0))
            for column in rate_columns
        ]) == 1
    ).count()
    invalid_zero_denominators = brand_daily.where(
        ((F.col("impression_sessions") == 0) & F.col("detail_entry_rate").isNotNull())
        | ((F.col("product_view_sessions") == 0) & (
            F.col("information_view_rate").isNotNull()
            | F.col("view_to_cart_rate").isNotNull()
        ))
    ).count()
    checks.append(_check(
        "brand_daily_rates_follow_contract",
        invalid_brand_rates == 0 and invalid_zero_denominators == 0,
        f"out_of_range={invalid_brand_rates}; non_null_zero_denominator={invalid_zero_denominators}",
    ))

    try:
        from .build_marts_job import _brand_daily_kpi
    except ImportError:
        from build_marts_job import _brand_daily_kpi
    expected_brand = _brand_daily_kpi(product_fact, funnel_session, time_zone)
    comparison_columns = [
        column for column in brand_daily.columns if column != "mart_processed_at"
    ]
    brand_difference_count = (
        expected_brand.select(*comparison_columns)
        .exceptAll(brand_daily.select(*comparison_columns)).count()
        + brand_daily.select(*comparison_columns)
        .exceptAll(expected_brand.select(*comparison_columns)).count()
    )
    checks.append(_check(
        "brand_daily_is_deterministic_from_inputs",
        brand_difference_count == 0,
        f"differing_rows={brand_difference_count}; mart_processed_at excluded",
    ))

    axes = ["actor_type", "source", "scenario_id", "simulation_run_id"]
    purchase_grains = {
        "product_repurchase_daily": (
            product_repurchase,
            ["snapshot_date_kst", "brand_id", "product_id", *axes],
        ),
        "brand_repurchase_daily": (
            brand_repurchase,
            ["snapshot_date_kst", "brand_id", *axes],
        ),
        "purchase_reason_daily": (
            purchase_reason,
            ["event_date_kst", "brand_id", "reason", *axes],
        ),
    }
    for name, (frame, grain) in purchase_grains.items():
        checks.append(_check(
            f"{name}_grain_is_unique",
            _duplicate_count(frame, grain) == 0,
            f"{name} configured grain is unique",
        ))
        invalid_brands = frame.where(
            F.col("brand_id").isNull() | (F.length(F.trim(F.col("brand_id"))) == 0)
        ).count()
        checks.append(_check(
            f"{name}_brand_id_is_valid",
            invalid_brands == 0,
            f"invalid_rows={invalid_brands}",
        ))

    for name, frame in (
        ("product_repurchase_daily", product_repurchase),
        ("brand_repurchase_daily", brand_repurchase),
    ):
        invalid_counts = frame.where(
            (F.col("repeat_buyer_count") > F.col("buyer_count"))
            | (F.col("purchase_order_count") < F.col("buyer_count"))
            | (F.col("buyer_count") < 0)
            | (
                (F.col("buyer_count") == 0)
                & F.col("repurchase_rate").isNotNull()
            )
            | (
                (F.col("buyer_count") > 0)
                & ~F.col("repurchase_rate").between(0.0, 1.0)
            )
            | (F.col("median_days_between_purchases") < 0)
        ).count()
        checks.append(_check(
            f"{name}_counts_and_rate_follow_contract",
            invalid_counts == 0,
            f"invalid_rows={invalid_counts}",
        ))

    invalid_restock = brand_repurchase.where(
        F.col("declared_restock_order_count").isNull()
        | (F.col("declared_restock_order_count") < 0)
        | (F.col("declared_restock_order_count") > F.col("purchase_order_count"))
    ).count()
    checks.append(_check(
        "brand_repurchase_declared_restock_is_bounded",
        invalid_restock == 0,
        f"invalid_rows={invalid_restock}",
    ))

    invalid_reason_counts = purchase_reason.where(
        (F.col("primary_order_count") > F.col("order_count"))
        | (F.col("skipped_order_count") > F.col("order_count"))
        | (F.col("trait_matched_order_count") > F.col("trait_compared_order_count"))
        | (F.col("trait_compared_order_count") > F.col("order_count"))
        # 건너뛴 응답은 이유가 없으므로 비중 분모에 들어가면 안 된다.
        | (F.col("reason").isNull() & F.col("reason_share").isNotNull())
        | (
            (F.col("trait_compared_order_count") == 0)
            & F.col("trait_match_rate").isNotNull()
        )
        | (
            (F.col("trait_compared_order_count") > 0)
            & ~F.col("trait_match_rate").between(0.0, 1.0)
        )
        | (
            F.col("reason_share").isNotNull()
            & ~F.col("reason_share").between(0.0, 1.0)
        )
    ).count()
    checks.append(_check(
        "purchase_reason_daily_counts_and_rates_follow_contract",
        invalid_reason_counts == 0,
        f"invalid_rows={invalid_reason_counts}",
    ))

    try:
        from .build_marts_job import (
            _brand_repurchase_daily,
            _product_repurchase_daily,
            _purchase_reason_daily,
            load_reason_trait_map,
        )
    except ImportError:
        from build_marts_job import (
            _brand_repurchase_daily,
            _product_repurchase_daily,
            _purchase_reason_daily,
            load_reason_trait_map,
        )
    window_days = int(
        product_repurchase.select("window_days").first()["window_days"]
    ) if product_repurchase.head(1) else 0
    if window_days > 0:
        rebuilt = {
            "product_repurchase_daily": (
                product_repurchase,
                _product_repurchase_daily(purchase_fact, window_days),
            ),
            "brand_repurchase_daily": (
                brand_repurchase,
                _brand_repurchase_daily(purchase_fact, purchase_reason_fact, window_days),
            ),
        }
        # 매핑이 빌드 때와 다르면 재계산이 어긋난다. Build Job 과 같은 파일을 읽는다.
        rebuilt["purchase_reason_daily"] = (
            purchase_reason,
            _purchase_reason_daily(
                purchase_reason_fact,
                purchase_fact,
                user_trait_daily,
                load_reason_trait_map(reason_trait_map_path),
            ),
        )
        for name, (stored, expected) in rebuilt.items():
            columns = [c for c in stored.columns if c != "mart_processed_at"]
            difference = (
                expected.select(*columns).exceptAll(stored.select(*columns)).count()
                + stored.select(*columns).exceptAll(expected.select(*columns)).count()
            )
            checks.append(_check(
                f"{name}_is_deterministic_from_inputs",
                difference == 0,
                f"differing_rows={difference}; mart_processed_at excluded",
            ))

    checks.append(
        _check(
            "ingredient_weekly_grain_is_unique",
            _duplicate_count(
                ingredient_weekly,
                [
                    "interest_week_kst",
                    "ingredient_id",
                    "actor_type",
                    "source",
                    "scenario_id",
                    "simulation_run_id",
                ],
            )
            == 0,
            "ingredient_weekly_interest grain is unique",
        )
    )
    invalid_ingredient_scores = ingredient_weekly.where(
        F.col("ingredient_interest_score").isNull()
        | (F.col("ingredient_interest_score") < 0)
        | (F.col("ingredient_interest_share") < 0)
        | (F.col("ingredient_interest_share") > 1)
    ).count()
    checks.append(
        _check(
            "ingredient_weekly_scores_are_valid",
            invalid_ingredient_scores == 0,
            f"invalid_rows={invalid_ingredient_scores}",
        )
    )
    checks.append(
        _check(
            "category_price_grain_is_unique",
            _duplicate_count(category_price, ["secondary_category", "currency"]) == 0,
            "category_price_reference grain=secondary_category+currency",
        )
    )
    invalid_price_rows = category_price.where(
        F.col("reference_median_price").isNull()
        | (F.col("reference_median_price") <= 0)
        | ~F.col("reference_source").isin("category", "global_fallback")
    ).count()
    checks.append(
        _check(
            "category_price_reference_is_valid",
            invalid_price_rows == 0,
            f"invalid_rows={invalid_price_rows}",
        )
    )

    banner_grain = [
        "event_date_kst", "brand_id", "product_id", "banner_type", "banner_value",
        "banner_slot", "trait_source", "policy_version", "actor_type", "source",
        "scenario_id", "simulation_run_id",
    ]
    checks.append(_check(
        "banner_daily_grain_is_unique",
        _duplicate_count(banner_daily, banner_grain) == 0,
        "banner_daily configured grain is unique",
    ))
    invalid_banner_counts = banner_daily.where(
        (F.col("click_count") > F.col("impression_count"))
        | (F.col("skip_count") < 0)
        | (
            (F.col("impression_count") == 0)
            & F.col("banner_ctr").isNotNull()
        )
        | (
            (F.col("impression_count") > 0)
            & ~F.col("banner_ctr").between(0, 1)
        )
    ).count()
    checks.append(_check(
        "banner_daily_counts_and_ctr_are_valid",
        invalid_banner_counts == 0,
        f"invalid_rows={invalid_banner_counts}",
    ))
    invalid_banner_values = banner_daily.where(~F.col("banner_value_is_valid")).count()
    checks.append(_check(
        "banner_value_uses_source_vocabulary",
        invalid_banner_values == 0,
        f"invalid_rows={invalid_banner_values}; new_brand alone permits NULL",
    ))
    unmatched_clicks = _unmatched_banner_click_count(product_fact)
    checks.append(_check(
        "banner_click_matches_impression_trait_source",
        unmatched_clicks == 0,
        f"unmatched_clicks={unmatched_clicks}",
    ))
    banner_facts = product_fact.where(F.col("event_name").isin("banner_impression", "banner_click"))
    invalid_banner_facts = banner_facts.where(
        F.col("banner_type").isNull()
        | F.col("banner_slot").isNull()
        | (F.col("banner_slot") <= 0)
        | ~F.col("trait_source").isin("session", "profile", "coldstart", "explore")
        | ((F.col("banner_type") == "new_brand") & F.col("banner_value").isNotNull())
        | ((F.col("banner_type") != "new_brand") & F.col("banner_value").isNull())
    ).count()
    checks.append(_check(
        "banner_fact_contract_is_valid",
        invalid_banner_facts == 0,
        f"invalid_rows={invalid_banner_facts}",
    ))
    impressions = banner_facts.where(F.col("event_name") == "banner_impression")
    impression_count = impressions.count()
    # trait_source 는 배정 결과가 아니라 그 시점에 무엇으로 축을 골랐는지다.
    # 성향이 아직 없는 세션은 explore 배정과 무관하게 coldstart 로 빠지므로
    # (Front 의 성향 계산기), 탐색 조작이 적용된 모집단만 분모로 쓴다.
    # 히어로 배너가 목록 첫 화면이라 coldstart 노출 비중이 크고, 전체를 분모로
    # 잡으면 배정이 정상이어도 20% 가 나올 수 없다.
    assigned = impressions.where(F.col("trait_source") != F.lit("coldstart"))
    assigned_count = assigned.count()
    explore_count = assigned.where(F.col("trait_source") == "explore").count()
    explore_share = explore_count / assigned_count if assigned_count else None
    # Sampling fluctuates at small N; enforce a broad operational guardrail only at N>=100.
    explore_ok = assigned_count < 100 or (explore_share is not None and 0.1 <= explore_share <= 0.3)
    checks.append(_check(
        "banner_explore_impression_share_is_near_twenty_percent",
        explore_ok,
        f"impressions={impression_count} assigned={assigned_count} "
        f"explore={explore_count} share={explore_share}; coldstart 는 분모에서 제외",
    ))
    checks.append(_check(
        "user_trait_daily_grain_is_unique",
        _duplicate_count(user_trait_daily, [
            "trait_date_kst", "user_id", "identity_scope", "actor_type",
            "source", "scenario_id", "simulation_run_id", "trait",
        ]) == 0,
        "user_trait_daily grain=trait_date_kst+user_id+identity/실행 축+trait",
    ))
    invalid_traits = user_trait_daily.where(
        ~F.col("trait").isin("price", "ingredient", "review", "concern", "participate")
        | F.col("trait_score").isNull()
        | F.col("trait").isNull()
        | (F.col("contributing_event_count") <= 0)
    ).count()
    checks.append(_check(
        "user_trait_daily_values_are_valid",
        invalid_traits == 0,
        f"invalid_rows={invalid_traits}",
    ))
    checks.append(_check(
        "cross_brand_daily_grain_is_unique",
        _duplicate_count(cross_brand_daily, [
            "event_date_kst", "destination_brand_id", "actor_type", "source",
            "scenario_id", "simulation_run_id",
        ]) == 0,
        "cross_brand_daily configured grain is unique",
    ))
    invalid_cross_rates = cross_brand_daily.where(
        (F.col("cross_brand_entry_sessions") > F.col("brand_view_sessions"))
        | (F.col("recommendation_cross_brand_entry_sessions") > F.col("cross_brand_entry_sessions"))
        | (F.col("banner_cross_brand_entry_sessions") > F.col("cross_brand_entry_sessions"))
    ).count()
    checks.append(_check(
        "cross_brand_daily_counts_are_bounded",
        invalid_cross_rates == 0,
        f"invalid_rows={invalid_cross_rates}",
    ))
    invalid_cross_rate_values = cross_brand_daily.where(
        (F.col("cross_brand_entry_rate") < 0)
        | (F.col("cross_brand_entry_rate") > 1)
        | (F.col("recommendation_cross_brand_entry_rate") < 0)
        | (F.col("recommendation_cross_brand_entry_rate") > 1)
        | (F.col("banner_cross_brand_entry_rate") < 0)
        | (F.col("banner_cross_brand_entry_rate") > 1)
        | (
            (F.col("cross_brand_entry_sessions") == 0)
            & (
                F.col("recommendation_share_of_cross_brand_entries").isNotNull()
                | F.col("banner_share_of_cross_brand_entries").isNotNull()
            )
        )
        | (
            (F.col("cross_brand_entry_sessions") > 0)
            & (
                ~F.col("recommendation_share_of_cross_brand_entries").between(0, 1)
                | ~F.col("banner_share_of_cross_brand_entries").between(0, 1)
            )
        )
    ).count()
    checks.append(_check(
        "cross_brand_daily_rates_use_contract_denominators",
        invalid_cross_rate_values == 0,
        f"invalid_rows={invalid_cross_rate_values}; share denominator=cross-brand entries",
    ))

    baseline = frames.get("analytics_baseline")
    if baseline is None:
        # 기준선은 BASELINE_* 세 값을 준 실행에서만 나온다. 없다고 실패는 아니다.
        warnings.append({
            "check": "analytics_baseline_is_absent",
            "detail": "baseline policy version, start date, end date를 준 실행에서만 생성된다",
        })
    else:
        counts["analytics_baseline"] = baseline.count()
        checks.append(_check(
            "analytics_baseline_grain_is_unique",
            _duplicate_count(baseline, [
                "baseline_policy_version", "metric_name", "brand_id", "algorithm",
            ]) == 0,
            "analytics_baseline grain=policy_version+metric+brand+algorithm",
        ))
        checks.append(_check(
            "analytics_baseline_metrics_are_pre_banner_only",
            baseline.where(
                ~F.col("metric_name").isin("recommendation_ctr", "cross_brand_entry_rate")
            ).count() == 0,
            "배너 CTR 기준선은 존재하지 않는 값이므로 만들지 않는다",
        ))
        invalid_baseline = baseline.where(
            (F.col("numerator") > F.col("denominator"))
            | (F.col("numerator") < 0)
            | (F.col("denominator") < 0)
            | ((F.col("denominator") == 0) & F.col("metric_value").isNotNull())
            | ((F.col("denominator") > 0) & ~F.col("metric_value").between(0, 1))
            | F.col("baseline_policy_version").isNull()
            | F.col("baseline_start_date").isNull()
            | F.col("baseline_end_date").isNull()
            | (F.col("baseline_start_date") > F.col("baseline_end_date"))
        ).count()
        checks.append(_check(
            "analytics_baseline_values_and_period_are_valid",
            invalid_baseline == 0,
            f"invalid_rows={invalid_baseline}",
        ))

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
        "purchase_fact": config.purchase_fact_path,
        "purchase_reason_fact": config.purchase_reason_fact_path,
        "review_event_fact": config.review_event_fact_path,
        "section_dwell": config.section_dwell_path,
        "content_interest": config.content_interest_path,
        "dim_product": config.dim_product_path,
        "dim_brand": config.dim_brand_path,
        "funnel_session": config.funnel_session_path,
        "product_daily": config.product_daily_path,
        "funnel_daily": config.funnel_daily_path,
        "brand_daily": config.brand_daily_path,
        "product_repurchase": config.product_repurchase_path,
        "brand_repurchase": config.brand_repurchase_path,
        "purchase_reason": config.purchase_reason_path,
        "ingredient_weekly": config.ingredient_weekly_path,
        "category_price": config.category_price_path,
        "banner_daily": config.banner_daily_path,
        "user_trait_daily": config.user_trait_daily_path,
        "cross_brand_daily": config.cross_brand_daily_path,
    }
    frames = {
        name: spark.read.option("mergeSchema", "true").parquet(path)
        for name, path in paths.items()
    }
    try:
        frames["analytics_baseline"] = spark.read.option("mergeSchema", "true").parquet(
            config.baseline_path
        )
    except Exception:
        # 기준선을 만들지 않은 실행에서는 경로가 없다. 검증은 그대로 진행한다.
        pass
    return validate_frames(
        frames, config.require_events, config.time_zone, config.reason_trait_map_path
    )


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
