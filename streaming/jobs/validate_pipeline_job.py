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
DEFAULT_BEHAVIOR_WEIGHTS_PATH = "frontend/src/types/log.ts"
DEFAULT_INGREDIENT_WEEKLY_PATH = "data/marts/ingredient_weekly_interest"
DEFAULT_CATEGORY_PRICE_PATH = "data/marts/category_price_reference"
DEFAULT_PERSONA_SEGMENT_PATH = "data/marts/persona_segment_daily_kpi"
DEFAULT_PRICE_BAND_PATH = "data/marts/brand_price_band_daily_kpi"
DEFAULT_CONTENT_DAILY_PATH = "data/marts/content_daily_kpi"
DEFAULT_CONTENT_CONVERSION_PATH = "data/marts/content_conversion_daily"
DEFAULT_BEHAVIOR_CONVERSION_PATH = "data/marts/behavior_conversion_daily"
DEFAULT_FRICTION_DAILY_PATH = "data/marts/friction_daily"
DEFAULT_EXIT_DAILY_PATH = "data/marts/exit_daily"
DEFAULT_ENTRY_SOURCE_DAILY_PATH = "data/marts/entry_source_daily"
DEFAULT_PRODUCT_EXIT_DAILY_PATH = "data/marts/product_exit_daily"
DEFAULT_SEGMENT_CONTENT_DAILY_PATH = "data/marts/segment_content_daily"
DEFAULT_SEGMENT_PRICE_BAND_PATH = "data/marts/segment_price_band_daily_kpi"
DEFAULT_EVENT_DAILY_PATH = "data/marts/event_daily"
DEFAULT_BRAND_COHORT_PATH = "data/marts/brand_cohort_dim"
DEFAULT_COMMONS_COHORT_PATH = "data/marts/commons_cohort_weekly"
DEFAULT_BANNER_DAILY_PATH = "data/marts/banner_daily"
DEFAULT_USER_TRAIT_DAILY_PATH = "data/marts/user_trait_daily"
DEFAULT_CROSS_BRAND_DAILY_PATH = "data/marts/cross_brand_daily"
DEFAULT_BASELINE_PATH = "data/marts/analytics_baseline"
DEFAULT_TIME_ZONE = "Asia/Seoul"

# Mart 실행 축. build_marts_job.EXECUTION_AXES 와 같아야 한다.
EXECUTION_AXES = (
    "actor_type",
    "source",
    "generator_type",
    "scenario_id",
    "simulation_run_id",
)

# 결제 계약 enum. event-properties-schema.md §3.15 · §3.16 이 정본이고
# build_marts_job 의 같은 이름 상수와 일치해야 한다.
# 피부 세그먼트 축. build_marts_job 의 같은 이름 상수와 일치해야 한다.
PERSONA_SEGMENT_TYPES = ("skin_type", "skin_tone")
PERSONA_CROSS_SEGMENT_TYPE = "skin_type_x_skin_tone"

PAYMENT_METHODS = ("kakaopay", "card", "test")
ORDER_CHANNELS = ("backend", "local")


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
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH
    ingredient_weekly_path: str = DEFAULT_INGREDIENT_WEEKLY_PATH
    category_price_path: str = DEFAULT_CATEGORY_PRICE_PATH
    persona_segment_path: str = DEFAULT_PERSONA_SEGMENT_PATH
    price_band_path: str = DEFAULT_PRICE_BAND_PATH
    content_daily_path: str = DEFAULT_CONTENT_DAILY_PATH
    content_conversion_path: str = DEFAULT_CONTENT_CONVERSION_PATH
    behavior_conversion_path: str = DEFAULT_BEHAVIOR_CONVERSION_PATH
    friction_daily_path: str = DEFAULT_FRICTION_DAILY_PATH
    exit_daily_path: str = DEFAULT_EXIT_DAILY_PATH
    entry_source_daily_path: str = DEFAULT_ENTRY_SOURCE_DAILY_PATH
    product_exit_daily_path: str = DEFAULT_PRODUCT_EXIT_DAILY_PATH
    segment_content_daily_path: str = DEFAULT_SEGMENT_CONTENT_DAILY_PATH
    segment_price_band_path: str = DEFAULT_SEGMENT_PRICE_BAND_PATH
    event_daily_path: str = DEFAULT_EVENT_DAILY_PATH
    brand_cohort_path: str = DEFAULT_BRAND_COHORT_PATH
    commons_cohort_path: str = DEFAULT_COMMONS_COHORT_PATH
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
            "behavior_weights_path": self.behavior_weights_path,
            "ingredient_weekly_path": self.ingredient_weekly_path,
            "category_price_path": self.category_price_path,
            "persona_segment_path": self.persona_segment_path,
            "price_band_path": self.price_band_path,
            "content_daily_path": self.content_daily_path,
            "content_conversion_path": self.content_conversion_path,
            "behavior_conversion_path": self.behavior_conversion_path,
            "friction_daily_path": self.friction_daily_path,
            "exit_daily_path": self.exit_daily_path,
            "entry_source_daily_path": self.entry_source_daily_path,
            "product_exit_daily_path": self.product_exit_daily_path,
            "segment_content_daily_path": self.segment_content_daily_path,
            "segment_price_band_path": self.segment_price_band_path,
            "event_daily_path": self.event_daily_path,
            "brand_cohort_path": self.brand_cohort_path,
            "commons_cohort_path": self.commons_cohort_path,
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
        "--behavior-weights-path",
        default=_env("BEHAVIOR_WEIGHTS_PATH", DEFAULT_BEHAVIOR_WEIGHTS_PATH),
        help="Build Job과 같은 EVENT_WEIGHT 원본이어야 상품 Mart 재계산 비교가 성립한다",
    )
    parser.add_argument(
        "--ingredient-weekly-path",
        default=_env("INGREDIENT_WEEKLY_INTEREST_PATH", DEFAULT_INGREDIENT_WEEKLY_PATH),
    )
    parser.add_argument(
        "--category-price-path",
        default=_env("CATEGORY_PRICE_REFERENCE_PATH", DEFAULT_CATEGORY_PRICE_PATH),
    )
    parser.add_argument(
        "--persona-segment-path",
        default=_env("PERSONA_SEGMENT_DAILY_PATH", DEFAULT_PERSONA_SEGMENT_PATH),
    )
    parser.add_argument(
        "--price-band-path",
        default=_env("BRAND_PRICE_BAND_DAILY_PATH", DEFAULT_PRICE_BAND_PATH),
    )
    parser.add_argument(
        "--content-daily-path",
        default=_env("CONTENT_DAILY_KPI_PATH", DEFAULT_CONTENT_DAILY_PATH),
    )
    parser.add_argument(
        "--content-conversion-path",
        default=_env("CONTENT_CONVERSION_DAILY_PATH", DEFAULT_CONTENT_CONVERSION_PATH),
    )
    parser.add_argument(
        "--behavior-conversion-path",
        default=_env("BEHAVIOR_CONVERSION_DAILY_PATH", DEFAULT_BEHAVIOR_CONVERSION_PATH),
    )
    parser.add_argument(
        "--friction-daily-path",
        default=_env("FRICTION_DAILY_PATH", DEFAULT_FRICTION_DAILY_PATH),
    )
    parser.add_argument(
        "--exit-daily-path",
        default=_env("EXIT_DAILY_PATH", DEFAULT_EXIT_DAILY_PATH),
    )
    parser.add_argument(
        "--entry-source-daily-path",
        default=_env("ENTRY_SOURCE_DAILY_PATH", DEFAULT_ENTRY_SOURCE_DAILY_PATH),
    )
    parser.add_argument(
        "--product-exit-daily-path",
        default=_env("PRODUCT_EXIT_DAILY_PATH", DEFAULT_PRODUCT_EXIT_DAILY_PATH),
    )
    parser.add_argument(
        "--segment-content-daily-path",
        default=_env(
            "SEGMENT_CONTENT_DAILY_PATH", DEFAULT_SEGMENT_CONTENT_DAILY_PATH
        ),
    )
    parser.add_argument(
        "--event-daily-path",
        default=_env("EVENT_DAILY_PATH", DEFAULT_EVENT_DAILY_PATH),
    )
    parser.add_argument(
        "--segment-price-band-path",
        default=_env("SEGMENT_PRICE_BAND_PATH", DEFAULT_SEGMENT_PRICE_BAND_PATH),
    )
    parser.add_argument(
        "--brand-cohort-path",
        default=_env("BRAND_COHORT_DIM_PATH", DEFAULT_BRAND_COHORT_PATH),
    )
    parser.add_argument(
        "--commons-cohort-path",
        default=_env("COMMONS_COHORT_WEEKLY_PATH", DEFAULT_COMMONS_COHORT_PATH),
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
        behavior_weights_path=args.behavior_weights_path,
        ingredient_weekly_path=args.ingredient_weekly_path,
        category_price_path=args.category_price_path,
        persona_segment_path=args.persona_segment_path,
        price_band_path=args.price_band_path,
        content_daily_path=args.content_daily_path,
        content_conversion_path=args.content_conversion_path,
        behavior_conversion_path=args.behavior_conversion_path,
        friction_daily_path=args.friction_daily_path,
        exit_daily_path=args.exit_daily_path,
        entry_source_daily_path=args.entry_source_daily_path,
        product_exit_daily_path=args.product_exit_daily_path,
        segment_content_daily_path=args.segment_content_daily_path,
        segment_price_band_path=args.segment_price_band_path,
        event_daily_path=args.event_daily_path,
        brand_cohort_path=args.brand_cohort_path,
        commons_cohort_path=args.commons_cohort_path,
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


EXPLORE_MIN_SAMPLE_SIZE = 100
EXPLORE_SHARE_RANGE = (0.1, 0.3)


def _banner_explore_share(impressions: Any) -> dict[str, Any]:
    """실사용자 배너 노출에서 탐색 배정 비중을 잰다.

    탐색 배정은 화면이 한다. 추천 서버는 `explore` 를 아예 내보내지 않고
    (`batch/serving/banners.py` 의 trait_source 계약 — "프론트 플랜의 무작위 탐색은
    서버가 아니라 화면 몫"), 합성 로그의 `explore` 는 생성기가 정한 값이라 검증
    대상이 아니다. 그래서 `actor_type='user'` 노출만 모집단으로 쓴다. 합성 로그만
    있는 실행에서는 표본이 0 이라 이 검사가 자연히 면제된다.

    `trait_source` 는 배정 결과가 아니라 그 시점에 무엇으로 축을 골랐는지다.
    성향이 아직 없는 세션은 탐색 배정과 무관하게 `coldstart` 로 빠지므로 분모에서 뺀다.
    히어로 배너가 목록 첫 화면이라 coldstart 노출 비중이 커서, 전체를 분모로 잡으면
    배정이 정상이어도 20% 가 나올 수 없다.
    """

    from pyspark.sql import functions as F

    user_impressions = impressions.where(F.col("actor_type") == F.lit("user"))
    user_count = user_impressions.count()
    assigned = user_impressions.where(F.col("trait_source") != F.lit("coldstart"))
    assigned_count = assigned.count()
    explore_count = assigned.where(F.col("trait_source") == F.lit("explore")).count()
    share = explore_count / assigned_count if assigned_count else None

    low, high = EXPLORE_SHARE_RANGE
    # 표본이 작으면 비중이 크게 흔들린다. 운영 가드레일은 N>=100 에서만 건다.
    exempt = assigned_count < EXPLORE_MIN_SAMPLE_SIZE
    passed = exempt or (share is not None and low <= share <= high)
    note = "실사용자 노출만 평가하고 coldstart 는 분모에서 제외"
    if exempt:
        note += f"; 실사용자 표본이 {EXPLORE_MIN_SAMPLE_SIZE} 미만이라 면제"
    return {
        "user_impressions": user_count,
        "assigned": assigned_count,
        "explore": explore_count,
        "share": share,
        "passed": passed,
        "note": note,
    }


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
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH,
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
    content_daily = frames["content_daily"]
    content_conversion = frames["content_conversion"]
    behavior_conversion = frames["behavior_conversion"]
    friction_daily = frames["friction_daily"]
    exit_daily = frames["exit_daily"]
    entry_source_daily = frames["entry_source_daily"]
    product_exit_daily = frames["product_exit_daily"]
    event_daily = frames["event_daily"]

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
                    "generator_type",
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
                    "generator_type",
                    "scenario_id",
                    "simulation_run_id",
                ],
            )
            == 0,
            "funnel_daily_kpi grain is unique",
        )
    )
    # 단계 도달 세션은 앞 단계를 넘을 수 없다. 담기는 Quick Look 경로가 있어
    # 분모가 detail_view_sessions 이고, 정보 조회는 상품 상세에서만 일어난다.
    invalid_funnel_counts = funnel_daily.where(
        (F.col("product_view_sessions") > F.col("detail_view_sessions"))
        | (F.col("quick_look_sessions") > F.col("detail_view_sessions"))
        | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
        | (F.col("information_view_sessions") > F.col("product_view_sessions"))
        | (F.col("checkout_sessions") > F.col("add_to_cart_sessions"))
        | (F.col("purchase_sessions") > F.col("checkout_sessions"))
    ).count()
    checks.append(_check(
        "funnel_daily_counts_are_bounded",
        invalid_funnel_counts == 0,
        f"invalid_rows={invalid_funnel_counts}",
    ))
    # 두 진입 경로는 배타라야 한다. 각각은 상한 안에 있으면서 합만 넘칠 수 있어서
    # (한 세션이 양쪽에 계상되는 경우) 상한 검사로는 안 잡힌다.
    # 퀵룩 선진입은 Mart 컬럼으로 두지 않고 여기서 funnel_session_fact 로 직접 센다 —
    # 소비자가 없는 값을 공개 Mart 에 늘리지 않는다.
    entry_paths = (
        funnel_session.groupBy(
            F.col("funnel_date_kst"), F.col("product_id"),
            *[F.col(axis) for axis in EXECUTION_AXES],
        )
        .agg(
            F.sum(
                (F.col("detail_entry_path") == F.lit("quick_look")).cast("int")
            ).cast("long").alias("_quick_look_entry_sessions"),
            F.sum(
                (F.col("detail_entry_path") == F.lit("direct_click")).cast("int")
            ).cast("long").alias("_direct_click_sessions"),
            F.sum(F.col("reached_detail_view").cast("int")).cast("long").alias("_detail_view_sessions"),
        )
    )
    unbalanced_entry_paths = entry_paths.where(
        F.col("_quick_look_entry_sessions") + F.col("_direct_click_sessions")
        != F.col("_detail_view_sessions")
    ).count()
    checks.append(_check(
        "funnel_detail_entry_paths_are_exclusive",
        unbalanced_entry_paths == 0,
        f"unbalanced_rows={unbalanced_entry_paths}; "
        "quick_look 선진입 + direct_click = detail_view",
    ))

    # click_to_view_rate 의 분자는 분모의 부분집합이라야 한다 (§4.5).
    # direct_click 만으로 세면 클릭 없이 상세를 연 세션이 분자에만 들어간다.
    invalid_click_through = funnel_daily.where(
        (F.col("click_through_detail_sessions") > F.col("click_sessions"))
        | (F.col("click_through_detail_sessions") > F.col("direct_click_sessions"))
        | (F.col("click_through_detail_sessions") < 0)
    ).count()
    checks.append(_check(
        "funnel_click_through_is_a_subset_of_clicks",
        invalid_click_through == 0,
        f"invalid_rows={invalid_click_through}; 클릭하고 상세로 간 세션 <= 클릭 세션 · direct_click 세션",
    ))
    funnel_rate_columns = [
        "impression_to_click_rate", "click_to_view_rate", "view_to_information_rate",
        "view_to_cart_rate", "cart_to_purchase_rate", "view_to_purchase_rate",
        "dropoff_after_impression_rate", "dropoff_after_view_rate",
        "dropoff_after_cart_rate",
    ]
    invalid_funnel_rates = funnel_daily.where(
        F.greatest(*[
            F.when(
                F.col(column).isNotNull() & ~F.col(column).between(0.0, 1.0),
                F.lit(1),
            ).otherwise(F.lit(0))
            for column in funnel_rate_columns
        ]) == 1
    ).count()
    checks.append(_check(
        "funnel_daily_rates_are_within_unit_interval",
        invalid_funnel_rates == 0,
        f"out_of_range={invalid_funnel_rates}",
    ))
    brand_grain = [
        "event_date_kst", "brand_id", "actor_type", "source",
        "generator_type", "scenario_id", "simulation_run_id",
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
    # 담기는 Quick Look에서도 일어나므로 분모는 상세를 연 세션이다.
    # 정보 조회는 상품 상세에서만 일어나 product_view 기준을 유지한다.
    invalid_brand_counts = brand_daily.where(
        (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
        | (F.col("information_view_sessions") > F.col("product_view_sessions"))
        | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
        | (F.col("quick_look_sessions") > F.col("detail_view_sessions"))
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
        | ((F.col("product_view_sessions") == 0)
           & F.col("information_view_rate").isNotNull())
        | ((F.col("detail_view_sessions") == 0)
           & F.col("view_to_cart_rate").isNotNull())
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

    # product_daily_kpi — 지금까지 grain 유일성 하나만 검사했다. 비율 네 개가
    # 검증 없이 나가는 동안 add_to_cart_rate 가 1.0 을 넘고 있었다 (Jira 277).
    invalid_product_counts = product_daily.where(
        (F.col("product_view_sessions") < 0)
        | (F.col("quick_look_sessions") < 0)
        | (F.col("session_count") < 0)
        | (F.col("unique_user_count") > F.col("session_count"))
        | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
        | (F.col("quick_look_sessions") > F.col("detail_view_sessions"))
        | (F.col("detail_view_sessions") > F.col("session_count"))
        | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
        | (F.col("purchase_sessions") > F.col("detail_view_sessions"))
        # 분모는 두 노출의 합이다. 추천 카드 클릭도 product_click 이라
        # product_impression 만 보면 1 을 넘는다 (§4.1, 프론트 확인 2026-09-17).
        | (F.col("product_click_count") > F.col("impression_count"))
        | (F.col("impression_count")
           != F.col("product_impression_count") + F.col("recommendation_impression_count"))
        | (F.col("purchase_count") > F.col("purchase_quantity"))
    ).count()
    checks.append(_check(
        "product_daily_counts_are_bounded",
        invalid_product_counts == 0,
        f"invalid_rows={invalid_product_counts}",
    ))

    product_rate_columns = [
        "product_ctr", "detail_entry_rate", "add_to_cart_rate", "purchase_rate"
    ]
    invalid_product_rates = product_daily.where(
        F.greatest(*[
            F.when(
                F.col(column).isNotNull() & ~F.col(column).between(0.0, 1.0),
                F.lit(1),
            ).otherwise(F.lit(0))
            for column in product_rate_columns
        ]) == 1
    ).count()
    invalid_product_denominators = product_daily.where(
        ((F.col("impression_count") == 0) & F.col("product_ctr").isNotNull())
        | ((F.col("impression_count") == 0)
           & F.col("detail_entry_rate").isNotNull())
        | ((F.col("detail_view_sessions") == 0) & F.col("add_to_cart_rate").isNotNull())
        | ((F.col("detail_view_sessions") == 0) & F.col("purchase_rate").isNotNull())
    ).count()
    checks.append(_check(
        "product_daily_rates_follow_contract",
        invalid_product_rates == 0 and invalid_product_denominators == 0,
        f"out_of_range={invalid_product_rates}; "
        f"non_null_zero_denominator={invalid_product_denominators}",
    ))

    # 상품 Dimension 매칭. Fact 단계에는 같은 검사가 있지만 Mart 단계에는 없었다.
    product_dimension_gap = (
        product_daily.select("product_id", "brand_id")
        .distinct()
        .join(
            dim_product.select(
                F.col("product_id").alias("_dim_product_id"),
                F.col("brand_id").alias("_dim_brand_id"),
            ),
            F.col("product_id") == F.col("_dim_product_id"),
            "left",
        )
        .where(
            F.col("_dim_product_id").isNull()
            | ~F.col("brand_id").eqNullSafe(F.col("_dim_brand_id"))
        )
        .count()
    )
    checks.append(_check(
        "product_daily_products_match_dimension",
        product_dimension_gap == 0,
        f"unmatched_rows={product_dimension_gap}",
    ))

    # 통화는 grain 이 아니라 대표값 한 개다 (F.first). 한 상품·하루에 통화가
    # 섞이면 revenue_amount 가 두 통화를 그냥 더하고 currency 는 하나만 보고한다.
    # grain 에 올리면 통화 없는 조회 행과 결제 행이 갈려 Mart 가 깨지므로
    # 여기서 혼합 자체를 막는다 (Jira 303 통화 전환 경계일 대비).
    mixed_currency_groups = (
        product_fact.where(
            F.col("currency").isNotNull()
            & ~F.coalesce(F.col("is_seeded"), F.lit(False))
        )
        .groupBy("event_date_kst", "product_id", *EXECUTION_AXES)
        .agg(F.countDistinct("currency").alias("_currencies"))
        .where(F.col("_currencies") > 1)
        .count()
    )
    checks.append(_check(
        "product_daily_currency_is_unambiguous",
        mixed_currency_groups == 0,
        f"mixed_currency_groups={mixed_currency_groups}",
    ))

    # 금액을 합산하는 나머지 Mart 도 같은 규칙을 지켜야 한다 (dw-schema §3.2).
    # purchase_fact 는 재구매·구매 이유 Mart 셋의 공통 입력이라 여기서 한 번 본다.
    # NULL 은 통과시킨다 — 값이 없는 것과 섞인 것은 다르다. 2026-09-11 생성기가
    # currency 를 보내지 않아 현재 재생 데이터는 전부 NULL 이다.
    purchase_currency_groups = (
        purchase_fact.where(
            F.col("currency").isNotNull()
            & ~F.coalesce(F.col("is_seeded"), F.lit(False))
        )
        .groupBy("event_date_kst", "brand_id", *EXECUTION_AXES)
        .agg(F.countDistinct("currency").alias("_currencies"))
        .where(F.col("_currencies") > 1)
        .count()
    )
    checks.append(_check(
        "purchase_fact_currency_is_unambiguous",
        purchase_currency_groups == 0,
        f"mixed_currency_groups={purchase_currency_groups}; paid_value·order_value·item_revenue 합이 두 통화를 더하면 안 된다",
    ))

    # 통화가 실리기 시작했는지 보이게 남긴다. 검사는 아니고 관측값이다 —
    # 원화 전환(303) 이 실제로 파이프라인까지 닿았는지 리포트에서 확인한다.
    counts["purchase_fact_rows_with_currency"] = purchase_fact.where(
        F.col("currency").isNotNull()
    ).count()
    counts["product_fact_rows_with_currency"] = product_fact.where(
        F.col("currency").isNotNull()
    ).count()

    # product_daily_kpi · funnel_daily_kpi 재계산 결정성. 두 Mart 에만 없었다.
    # 235 에서 시드 필터를 Mart 함수 밖(호출부)에 뒀다가 brand_daily 가 542행
    # 어긋났던 것과 같은 함정을 잡는다.
    try:
        from .behavior_weights import load as load_behavior_weights
    except ImportError:
        from behavior_weights import load as load_behavior_weights
    try:
        from .build_marts_job import _funnel_daily_kpi, _product_daily_kpi
    except ImportError:
        from build_marts_job import _funnel_daily_kpi, _product_daily_kpi

    daily_rebuilt = {
        "product_daily_kpi": (
            product_daily,
            _product_daily_kpi(
                product_fact, load_behavior_weights(behavior_weights_path)["event"]
            ),
        ),
        "funnel_daily_kpi": (funnel_daily, _funnel_daily_kpi(funnel_session)),
    }
    for name, (stored, expected) in daily_rebuilt.items():
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

    axes = list(EXECUTION_AXES)
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

    # 결제 계약(299) — purchase_fact 의 결제 축이 enum 밖으로 나가면
    # 결제수단 분포가 조용히 미등록 값으로 채워진다.
    invalid_payment = purchase_fact.where(
        (
            F.col("payment_method").isNotNull()
            & ~F.col("payment_method").isin(*PAYMENT_METHODS)
        )
        | (
            F.col("order_channel").isNotNull()
            & ~F.col("order_channel").isin(*ORDER_CHANNELS)
        )
        | (F.col("paid_value") < 0)
    ).count()
    checks.append(_check(
        "purchase_fact_payment_contract_is_valid",
        invalid_payment == 0,
        f"invalid_rows={invalid_payment}",
    ))

    for name, frame in (
        ("product_repurchase_daily", product_repurchase),
        ("brand_repurchase_daily", brand_repurchase),
    ):
        # 분포는 주문 단위다. 상품 row 를 세면 장바구니 크기만큼 부풀어
        # 고유 주문 수를 넘어선다.
        channel_total = F.col("backend_order_count") + F.col("local_order_count")
        method_total = (
            F.col("kakaopay_order_count")
            + F.col("card_order_count")
            + F.col("test_order_count")
        )
        invalid_split = frame.where(
            F.col("backend_order_count").isNull()
            | F.col("local_order_count").isNull()
            | (channel_total > F.col("purchase_order_count"))
            | (method_total > F.col("purchase_order_count"))
            | (F.col("backend_paid_value") < 0)
            | (
                (F.col("backend_order_count") == 0)
                & F.col("backend_paid_value").isNotNull()
            )
        ).count()
        checks.append(_check(
            f"{name}_payment_split_is_bounded",
            invalid_split == 0,
            f"invalid_rows={invalid_split}",
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
                    "generator_type",
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
        "banner_slot", "trait_source", "policy_version", *EXECUTION_AXES,
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
    explore = _banner_explore_share(impressions)
    checks.append(_check(
        "banner_explore_impression_share_is_near_twenty_percent",
        explore["passed"],
        f"impressions={impression_count} user_impressions={explore['user_impressions']} "
        f"assigned={explore['assigned']} explore={explore['explore']} "
        f"share={explore['share']}; {explore['note']}",
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
            "event_date_kst", "destination_brand_id", *EXECUTION_AXES,
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


    persona_segment = frames.get("persona_segment_daily")
    if persona_segment is None:
        # bridge_persona_segment 는 저장소에 없는 생성물이다. 만들지 않은 실행에는
        # 이 Mart 도 없다. 없다고 실패로 보지 않는다.
        warnings.append({
            "check": "persona_segment_daily_is_absent",
            "detail": (
                "py contracts/persona/build_persona_tables.py --sample PC:all 로 "
                "bridge_persona_segment 를 만든 실행에서만 생성된다"
            ),
        })
    else:
        counts["persona_segment_daily"] = persona_segment.count()
        checks.append(_check(
            "persona_segment_daily_grain_is_unique",
            _duplicate_count(persona_segment, [
                "event_date_kst", "brand_id", "segment_type", "segment_value",
                *EXECUTION_AXES,
            ]) == 0,
            "persona_segment_daily_kpi grain=date+brand+segment_type+segment_value+축",
        ))
        checks.append(_check(
            "persona_segment_types_are_registered",
            persona_segment.where(
                ~F.col("segment_type").isin(
                    *PERSONA_SEGMENT_TYPES, PERSONA_CROSS_SEGMENT_TYPE
                )
            ).count() == 0,
            f"허용 축={sorted((*PERSONA_SEGMENT_TYPES, PERSONA_CROSS_SEGMENT_TYPE))}",
        ))
        invalid_segment_counts = persona_segment.where(
            (F.col("segment_user_count") < 0)
            | (F.col("segment_user_count") > F.col("session_count"))
            | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
            | (F.col("quick_look_sessions") > F.col("detail_view_sessions"))
            | (F.col("detail_view_sessions") > F.col("session_count"))
            | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
            | (F.col("purchase_sessions") > F.col("detail_view_sessions"))
            | (F.col("impression_sessions") > F.col("session_count"))
        ).count()
        checks.append(_check(
            "persona_segment_counts_are_bounded",
            invalid_segment_counts == 0,
            f"invalid_rows={invalid_segment_counts}",
        ))
        segment_rate_columns = [
            "view_to_cart_rate", "view_to_purchase_rate", "detail_entry_rate"
        ]
        invalid_segment_rates = persona_segment.where(
            F.greatest(*[
                F.when(
                    F.col(column).isNotNull() & ~F.col(column).between(0.0, 1.0),
                    F.lit(1),
                ).otherwise(F.lit(0))
                for column in segment_rate_columns
            ]) == 1
        ).count()
        invalid_segment_denominators = persona_segment.where(
            ((F.col("detail_view_sessions") == 0) & F.col("view_to_cart_rate").isNotNull())
            | ((F.col("detail_view_sessions") == 0)
               & F.col("view_to_purchase_rate").isNotNull())
            | ((F.col("impression_sessions") == 0) & F.col("detail_entry_rate").isNotNull())
            | ((F.col("session_count") == 0) & F.col("avg_interest_score").isNotNull())
        ).count()
        checks.append(_check(
            "persona_segment_rates_follow_contract",
            invalid_segment_rates == 0 and invalid_segment_denominators == 0,
            f"out_of_range={invalid_segment_rates}; "
            f"non_null_zero_denominator={invalid_segment_denominators}",
        ))

        # 세그먼트 세션 합은 브랜드 전체와 같지 않다 — persona 없는 세션을 귀속하지
        # 않기 때문이다. 다만 넘어설 수는 없다. 넘으면 조인이 행을 불린 것이다.
        segment_overflow = (
            persona_segment.where(
                F.col("segment_type") == F.lit(PERSONA_CROSS_SEGMENT_TYPE)
            )
            .groupBy("event_date_kst", "brand_id", *EXECUTION_AXES)
            .agg(F.sum("detail_view_sessions").cast("long").alias("_segment_sessions"))
            .join(
                brand_daily.select(
                    "event_date_kst", "brand_id", *EXECUTION_AXES,
                    F.col("detail_view_sessions").alias("_brand_sessions"),
                ),
                ["event_date_kst", "brand_id", *EXECUTION_AXES],
                "inner",
            )
            .where(F.col("_segment_sessions") > F.col("_brand_sessions"))
            .count()
        )
        checks.append(_check(
            "persona_segment_sessions_do_not_exceed_brand_total",
            segment_overflow == 0,
            f"overflowing_rows={segment_overflow}; "
            "교차 축은 배타라 합이 브랜드 전체를 넘을 수 없다",
        ))

    price_band = frames.get("price_band_daily")
    if price_band is None:
        warnings.append({
            "check": "brand_price_band_daily_is_absent",
            "detail": "어휘집 price_bin_edges 와 dim_product 가 있는 실행에서만 생성된다",
        })
    else:
        counts["brand_price_band_daily"] = price_band.count()
        checks.append(_check(
            "price_band_daily_grain_is_unique",
            _duplicate_count(price_band, [
                "event_date_kst", "brand_id", "price_bin", "currency", *EXECUTION_AXES,
            ]) == 0,
            "brand_price_band_daily_kpi grain=date+brand+price_bin+currency+축",
        ))

        invalid_price_counts = price_band.where(
            (F.col("session_count") < 0)
            | (F.col("unique_user_count") > F.col("session_count"))
            | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
            | (F.col("quick_look_sessions") > F.col("detail_view_sessions"))
            | (F.col("detail_view_sessions") > F.col("session_count"))
            | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
            | (F.col("purchase_sessions") > F.col("detail_view_sessions"))
            | (F.col("product_count") < 1)
        ).count()
        checks.append(_check(
            "price_band_counts_are_bounded",
            invalid_price_counts == 0,
            f"invalid_rows={invalid_price_counts}",
        ))

        price_rate_columns = [
            "detail_entry_rate", "view_to_cart_rate", "view_to_purchase_rate"
        ]
        invalid_price_rates = price_band.where(
            F.greatest(*[
                F.when(
                    F.col(column).isNotNull() & ~F.col(column).between(0.0, 1.0),
                    F.lit(1),
                ).otherwise(F.lit(0))
                for column in price_rate_columns
            ]) == 1
        ).count()
        invalid_price_denominators = price_band.where(
            ((F.col("impression_sessions") == 0) & F.col("detail_entry_rate").isNotNull())
            | ((F.col("detail_view_sessions") == 0) & F.col("view_to_cart_rate").isNotNull())
            | ((F.col("detail_view_sessions") == 0)
               & F.col("view_to_purchase_rate").isNotNull())
        ).count()
        checks.append(_check(
            "price_band_rates_follow_contract",
            invalid_price_rates == 0 and invalid_price_denominators == 0,
            f"out_of_range={invalid_price_rates}; "
            f"non_null_zero_denominator={invalid_price_denominators}",
        ))

        checks.append(_check(
            "price_band_currency_is_present",
            price_band.where(
                F.col("currency").isNull()
                | (F.length(F.trim(F.col("currency"))) == 0)
            ).count() == 0,
            "통화는 grain 이라 비어 있으면 서로 다른 통화가 한 행에 섞인다",
        ))

        # 반열린 구간이라 한 상품은 한 구간에만 속한다. 구간별 상품 수를 더하면
        # 그 브랜드·일자에 실제로 등장한 상품 수와 같아야 한다. 크면 Dimension
        # 조인이 상품을 복제했거나 경계 판정이 겹친 것이다.
        observed_products = (
            product_fact.where(
                ~F.coalesce(F.col("is_seeded"), F.lit(False))
                & F.col("brand_id").isNotNull()
                & (F.length(F.trim(F.col("brand_id"))) > 0)
            )
            .join(
                dim_product.select(F.col("product_id").alias("_dim_product_id")),
                F.col("product_id") == F.col("_dim_product_id"),
                "left_semi",
            )
            .groupBy("event_date_kst", "brand_id", *EXECUTION_AXES)
            .agg(F.countDistinct("product_id").cast("long").alias("_observed_products"))
        )
        banded_products = price_band.groupBy(
            "event_date_kst", "brand_id", *EXECUTION_AXES
        ).agg(F.sum("product_count").cast("long").alias("_banded_products"))
        # 실행 축에 NULL 이 있으므로 등호 Join 이면 그 행이 통째로 빠진다.
        join_keys = ["event_date_kst", "brand_id", *EXECUTION_AXES]
        condition = None
        for column in join_keys:
            clause = banded_products[column].eqNullSafe(observed_products[column])
            condition = clause if condition is None else condition & clause
        overlapping = (
            banded_products.join(observed_products, condition, "inner")
            .where(F.col("_banded_products") != F.col("_observed_products"))
            .count()
        )
        checks.append(_check(
            "price_band_maps_each_product_once",
            overlapping == 0,
            f"mismatched_rows={overlapping}; 구간별 상품 수 합 != 관측 상품 수",
        ))

    brand_cohort = frames.get("brand_cohort")
    commons_cohort = frames.get("commons_cohort")
    if brand_cohort is None or commons_cohort is None:
        warnings.append({
            "check": "commons_marts_are_absent",
            "detail": "dim_brand 와 어휘집이 있는 실행에서만 생성된다",
        })
    else:
        counts["brand_cohort_dim"] = brand_cohort.count()
        counts["commons_cohort_weekly"] = commons_cohort.count()

        checks.append(_check(
            "brand_cohort_grain_is_unique",
            _duplicate_count(brand_cohort, ["brand_id"]) == 0,
            "brand_cohort_dim grain=brand_id",
        ))
        checks.append(_check(
            "commons_cohort_grain_is_unique",
            _duplicate_count(commons_cohort, [
                "snapshot_week_kst", "cohort_key", "metric_name", *EXECUTION_AXES,
            ]) == 0,
            "commons_cohort_weekly grain=week+cohort+metric+축",
        ))

        # R5 — B층 Mart 는 다른 브랜드에게 보여도 되는 형태여야 한다.
        leaked_identifiers = [
            column for column in commons_cohort.columns
            if column in ("brand_id", "brand_hash", "brand_name")
        ]
        checks.append(_check(
            "commons_cohort_has_no_brand_identifier",
            leaked_identifiers == [],
            f"leaked={leaked_identifiers}; 코호트 단위 집계라 행이 브랜드에 대응하지 않는다",
        ))

        # R4 — 절대 건수를 두지 않는다. brand_count 와 임계값 파라미터만 예외다.
        allowed_counts = {"brand_count", "min_brand_count", "min_sample_size"}
        leaked_counts = [
            column for column in commons_cohort.columns
            if column not in allowed_counts
            and (column.endswith("_count") or column.endswith("_sessions"))
        ]
        checks.append(_check(
            "commons_cohort_has_no_absolute_counts",
            leaked_counts == [],
            f"leaked={leaked_counts}; 세션 분모는 is_sample_sufficient 로만 전달한다",
        ))

        # R1·R3 — 억제된 셀은 값이 비어야 한다. 행은 남는다.
        leaked_suppressed = commons_cohort.where(
            F.col("is_suppressed")
            & (
                F.col("p25").isNotNull()
                | F.col("p50").isNotNull()
                | F.col("p75").isNotNull()
            )
        ).count()
        checks.append(_check(
            "commons_cohort_suppressed_cells_are_empty",
            leaked_suppressed == 0,
            f"leaked_rows={leaked_suppressed}",
        ))

        invalid_commons = commons_cohort.where(
            (F.col("brand_count") < 0)
            | (F.col("p25") > F.col("p50"))
            | (F.col("p50") > F.col("p75"))
            | (
                F.greatest(
                    *[
                        F.when(
                            F.col(column).isNotNull()
                            & ~F.col(column).between(0.0, 1.0),
                            F.lit(1),
                        ).otherwise(F.lit(0))
                        for column in ("p25", "p50", "p75")
                    ]
                )
                == 1
            )
            | (
                # 억제되지 않았는데 값이 비면 계산이 끊긴 것이다
                ~F.col("is_suppressed") & F.col("p50").isNull()
            )
        ).count()
        checks.append(_check(
            "commons_cohort_quantiles_follow_contract",
            invalid_commons == 0,
            f"invalid_rows={invalid_commons}; p25<=p50<=p75 · 0~1 · 억제 아니면 값 존재",
        ))

        # R1 이 실제로 걸렸는지. 임계값을 넘는데 억제된 셀이 있으면 판정이 어긋난 것이다.
        wrong_suppression = commons_cohort.where(
            (F.col("brand_count") >= F.col("min_brand_count"))
            & ~F.col("is_dominated")
            & F.col("is_suppressed")
        ).count()
        checks.append(_check(
            "commons_cohort_suppression_matches_thresholds",
            wrong_suppression == 0,
            f"invalid_rows={wrong_suppression}",
        ))

        # cohort_key 는 brand_cohort_dim 이 만든 값이어야 한다.
        unknown_cohorts = (
            commons_cohort.select("cohort_key")
            .distinct()
            .join(
                brand_cohort.where(F.col("cohort_key").isNotNull())
                .select("cohort_key")
                .distinct(),
                ["cohort_key"],
                "left_anti",
            )
            .count()
        )
        checks.append(_check(
            "commons_cohort_keys_come_from_brand_cohort_dim",
            unknown_cohorts == 0,
            f"unknown_keys={unknown_cohorts}",
        ))

        # 가격을 모르는 브랜드는 코호트에 넣지 않는다 (dw-schema §3.7).
        invalid_cohort_keys = brand_cohort.where(
            (F.col("dominant_price_bin").isNull() & F.col("cohort_key").isNotNull())
            | (F.col("product_count") < 1)
            | F.col("product_count_band").isNull()
            | F.col("brand_hash").isNull()
        ).count()
        checks.append(_check(
            "brand_cohort_assignment_is_valid",
            invalid_cohort_keys == 0,
            f"invalid_rows={invalid_cohort_keys}",
        ))
    # ── E3 콘텐츠 Mart (dw-schema §4.4·§4.19·§4.20) ────────────────────────
    # Event 목록은 Mart 가 정본이다. 여기에 복제하면 조용히 갈라진다.
    try:
        from .build_marts_job import (
            CONVERSION_BEHAVIOR_EVENTS,
            _behavior_conversion_daily,
            _content_conversion_daily,
            _content_daily_kpi,
        )
    except ImportError:
        from build_marts_job import (
            CONVERSION_BEHAVIOR_EVENTS,
            _behavior_conversion_daily,
            _content_conversion_daily,
            _content_daily_kpi,
        )

    counts["content_daily_kpi"] = content_daily.count()
    counts["content_conversion_daily"] = content_conversion.count()
    counts["behavior_conversion_daily"] = behavior_conversion.count()

    content_key = [
        "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
        *EXECUTION_AXES,
    ]
    checks.append(_check(
        "content_daily_grain_is_unique",
        _duplicate_count(content_daily, content_key) == 0,
        "content_daily_kpi grain=date+brand+product+section+content_kind+축",
    ))
    checks.append(_check(
        "content_conversion_grain_is_unique",
        _duplicate_count(content_conversion, [
            "event_date_kst", "brand_id", "product_id", "content_kind",
            *EXECUTION_AXES,
        ]) == 0,
        "content_conversion_daily grain=date+brand+product+content_kind+축",
    ))
    checks.append(_check(
        "behavior_conversion_grain_is_unique",
        _duplicate_count(behavior_conversion, [
            "event_date_kst", "brand_id", "product_id", "event_name",
            *EXECUTION_AXES,
        ]) == 0,
        "behavior_conversion_daily grain=date+brand+product+event_name+축",
    ))

    # §4.4 — 플랫폼 목록 섹션은 상품 KPI 에 섞이지 않는다. 재생 데이터에서
    # content_interest_fact 의 67% 가 product_id NULL 이라 빠짐없이 걸러야 한다.
    platform_rows = content_daily.where(
        F.col("product_id").isNull() | (F.length(F.trim(F.col("product_id"))) == 0)
        | F.col("brand_id").isNull()
    ).count()
    checks.append(_check(
        "content_daily_excludes_platform_sections",
        platform_rows == 0,
        f"leaked_rows={platform_rows}",
    ))

    invalid_content_counts = content_daily.where(
        (F.col("section_view_sessions") > F.col("section_view_count"))
        | (F.col("section_view_sessions") < 0)
        | (F.col("dwell_ms_sum") < 0)
        | (F.col("matched_ingredient_count") < 0)
        # 겹침을 걷어낸 몫이라 총합을 넘을 수 없다. 넘으면 두 컬럼이
        # 서로 다른 모집단을 세고 있다는 뜻이다 (§4.4).
        | (F.col("co_visible_le2_dwell_ms_sum") < 0)
        | (F.col("co_visible_le2_dwell_ms_sum") > F.col("dwell_ms_sum"))
        # 분자는 분모 모집단으로 제한돼 있다 (§4.4)
        | (F.col("ingredient_view_sessions") > F.col("product_view_sessions"))
        | (F.col("review_view_sessions") > F.col("product_view_sessions"))
    ).count()
    checks.append(_check(
        "content_daily_counts_are_bounded",
        invalid_content_counts == 0,
        f"invalid_rows={invalid_content_counts}; 세션 <= 조회수 · 열람 <= 상품 조회 세션 · 겹침 제외 체류 <= 체류 합계",
    ))

    invalid_content_rates = content_daily.where(
        (F.col("ingredient_view_rate").isNotNull()
         & ~F.col("ingredient_view_rate").between(0.0, 1.0))
        | (F.col("review_view_rate").isNotNull()
           & ~F.col("review_view_rate").between(0.0, 1.0))
        | (F.col("avg_dwell_ms_per_session").isNotNull()
           & (F.col("avg_dwell_ms_per_session") < 0))
        # 분모가 0이면 NULL 이고, 0이 아니면 값이 있어야 한다 (§2.3)
        | ((F.col("product_view_sessions") == 0)
           & F.col("ingredient_view_rate").isNotNull())
        | ((F.col("product_view_sessions") > 0)
           & F.col("ingredient_view_rate").isNull())
    ).count()
    checks.append(_check(
        "content_daily_rates_follow_contract",
        invalid_content_rates == 0,
        f"invalid_rows={invalid_content_rates}; 0~1 · 분모 0이면 NULL",
    ))

    # §4.4 — 상품 단위 컬럼은 content_kind 마다 같은 값이어야 한다. 갈라지면
    # 대시보드가 콘텐츠별로 다른 분모를 보고 비교한다.
    repeated = content_daily.groupBy(
        "event_date_kst", "brand_id", "product_id", *EXECUTION_AXES
    ).agg(
        F.countDistinct("product_view_sessions").alias("_views"),
        F.countDistinct("ingredient_view_sessions").alias("_ingredients"),
        F.countDistinct("review_view_sessions").alias("_reviews"),
    ).where(
        (F.col("_views") > 1) | (F.col("_ingredients") > 1) | (F.col("_reviews") > 1)
    ).count()
    checks.append(_check(
        "content_daily_product_scoped_columns_repeat",
        repeated == 0,
        f"split_rows={repeated}; product_view/ingredient/review 세션은 상품 단위다",
    ))

    invalid_conversion = content_conversion.where(
        (F.col("viewed_cart_sessions") > F.col("viewed_sessions"))
        | (F.col("viewed_sessions") <= 0)
        | F.col("content_kind").isNull()
        | (F.col("viewed_cart_rate").isNotNull()
           & ~F.col("viewed_cart_rate").between(0.0, 1.0))
    ).count()
    checks.append(_check(
        "content_conversion_counts_are_bounded",
        invalid_conversion == 0,
        f"invalid_rows={invalid_conversion}; 담기 <= 열람 · content_kind 필수",
    ))

    # §4.20 의 불변식. 두 모집단의 합이 상품 조회 세션과 같아야 한다.
    behaviour_totals = behavior_conversion.groupBy(
        "event_date_kst", "brand_id", "product_id", *EXECUTION_AXES
    ).agg(
        F.countDistinct(
            F.col("done_sessions") + F.col("not_done_sessions")
        ).alias("_universes"),
        F.countDistinct("event_name").alias("_events"),
    ).where(
        (F.col("_universes") > 1) | (F.col("_events") != len(CONVERSION_BEHAVIOR_EVENTS))
    ).count()
    checks.append(_check(
        "behavior_conversion_populations_partition_the_universe",
        behaviour_totals == 0,
        f"invalid_groups={behaviour_totals}; done+not_done 이 Event 마다 같고 "
        f"Event {len(CONVERSION_BEHAVIOR_EVENTS)}종이 모두 있어야 한다",
    ))

    invalid_behaviour = behavior_conversion.where(
        ~F.col("event_name").isin(*CONVERSION_BEHAVIOR_EVENTS)
        | (F.col("done_cart_sessions") > F.col("done_sessions"))
        | (F.col("not_done_cart_sessions") > F.col("not_done_sessions"))
        | ((F.col("done_sessions") + F.col("not_done_sessions")) <= 0)
        | (F.col("done_cart_rate").isNotNull()
           & ~F.col("done_cart_rate").between(0.0, 1.0))
        | (F.col("not_done_cart_rate").isNotNull()
           & ~F.col("not_done_cart_rate").between(0.0, 1.0))
        | ((F.col("done_sessions") == 0) & F.col("done_cart_rate").isNotNull())
        | ((F.col("done_sessions") > 0) & F.col("done_cart_rate").isNull())
    ).count()
    checks.append(_check(
        "behavior_conversion_values_follow_contract",
        invalid_behaviour == 0,
        f"invalid_rows={invalid_behaviour}; 담기 <= 모집단 · 0~1 · 분모 0이면 NULL",
    ))

    # 재계산 결정성. 시드 제외가 Mart 함수 안에 있는지를 이 검사가 잡는다 —
    # 235 에서 필터를 호출부에 뒀다가 brand_daily 가 542행 어긋났다.
    content_rebuilt = {
        "content_daily_kpi": (
            content_daily,
            _content_daily_kpi(content_interest, funnel_session, time_zone),
        ),
        "content_conversion_daily": (
            content_conversion,
            _content_conversion_daily(content_interest, funnel_session, time_zone),
        ),
        "behavior_conversion_daily": (
            behavior_conversion,
            _behavior_conversion_daily(sessionized, funnel_session, time_zone),
        ),
    }
    for name, (stored, expected) in content_rebuilt.items():
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

    # ── E6 마찰·이탈·유입 Mart (dw-schema §4.21·§4.22·§4.23) ──────────────
    # 어휘는 Mart 가 정본이다. 여기에 복제하면 조용히 갈라진다.
    try:
        from .build_marts_job import (
            ENTRY_SOURCES,
            FRICTION_EVENTS,
            _entry_source_daily,
            _exit_daily,
            _friction_daily,
        )
    except ImportError:
        from build_marts_job import (
            ENTRY_SOURCES,
            FRICTION_EVENTS,
            _entry_source_daily,
            _exit_daily,
            _friction_daily,
        )

    counts["friction_daily"] = friction_daily.count()
    counts["exit_daily"] = exit_daily.count()
    counts["entry_source_daily"] = entry_source_daily.count()

    checks.append(_check(
        "friction_daily_grain_is_unique",
        _duplicate_count(friction_daily, [
            "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
            "event_name", *EXECUTION_AXES,
        ]) == 0,
        "friction_daily grain=date+brand+product+section+content_kind+event_name+축",
    ))
    checks.append(_check(
        "exit_daily_grain_is_unique",
        _duplicate_count(exit_daily, [
            "event_date_kst", "brand_id", "product_id", *EXECUTION_AXES,
        ]) == 0,
        "exit_daily grain=date+brand+product+축",
    ))
    checks.append(_check(
        "entry_source_daily_grain_is_unique",
        _duplicate_count(entry_source_daily, [
            "event_date_kst", "brand_id", "entry_source", *EXECUTION_AXES,
        ]) == 0,
        "entry_source_daily grain=date+brand+entry_source+축",
    ))

    invalid_friction = friction_daily.where(
        ~F.col("event_name").isin(*FRICTION_EVENTS)
        | (F.col("event_count") < 0)
        | (F.col("friction_sessions") < 0)
        | (F.col("friction_sessions") > F.col("event_count"))
        | (F.col("friction_sessions") > F.col("detail_view_sessions"))
        | (F.col("friction_rate").isNotNull()
           & ~F.col("friction_rate").between(0.0, 1.0))
        | ((F.col("detail_view_sessions") == 0) & F.col("friction_rate").isNotNull())
        | ((F.col("detail_view_sessions") > 0) & F.col("friction_rate").isNull())
        | F.col("product_id").isNull()
        | F.col("brand_id").isNull()
    ).count()
    checks.append(_check(
        "friction_daily_values_follow_contract",
        invalid_friction == 0,
        f"invalid_rows={invalid_friction}; 세션 <= Event · 세션 <= 분모 · 0~1 · 분모 0이면 NULL",
    ))

    # §4.21 — 마찰 Event 3종이 모든 위치에 행으로 있어야 한다. dead_click 이 0이라고
    # 행이 사라지면 화면이 "0" 과 "집계 안 함" 을 구분할 수 없다.
    missing_friction_events = friction_daily.groupBy(
        "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
        *EXECUTION_AXES,
    ).agg(
        F.countDistinct("event_name").alias("_events")
    ).where(F.col("_events") != len(FRICTION_EVENTS)).count()
    checks.append(_check(
        "friction_daily_keeps_a_row_per_event",
        missing_friction_events == 0,
        f"invalid_groups={missing_friction_events}; 위치마다 Event {len(FRICTION_EVENTS)}종",
    ))

    invalid_exit = exit_daily.where(
        (F.col("quick_exit_sessions") > F.col("exit_summary_sessions"))
        | (F.col("exit_summary_sessions") > F.col("detail_view_sessions"))
        | (F.col("detail_view_sessions") <= 0)
        | (F.col("quick_exit_rate").isNotNull()
           & ~F.col("quick_exit_rate").between(0.0, 1.0))
        | F.col("quick_exit_rate").isNull()
        | F.col("product_id").isNull()
        | F.col("brand_id").isNull()
    ).count()
    checks.append(_check(
        "exit_daily_values_follow_contract",
        invalid_exit == 0,
        f"invalid_rows={invalid_exit}; 조기이탈 <= 기록 <= 분모 · 0~1",
    ))

    invalid_entry = entry_source_daily.where(
        ~F.col("entry_source").isin(*ENTRY_SOURCES)
        | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
        | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
        | (F.col("detail_view_sessions") <= 0)
        | (F.col("view_to_cart_rate").isNotNull()
           & ~F.col("view_to_cart_rate").between(0.0, 1.0))
        | F.col("view_to_cart_rate").isNull()
        | F.col("brand_id").isNull()
    ).count()
    checks.append(_check(
        "entry_source_daily_values_follow_contract",
        invalid_entry == 0,
        f"invalid_rows={invalid_entry}; 담기·조회 <= 상세 세션 · 어휘 · 0~1",
    ))

    # 재계산 결정성. 시드 제외가 Mart 함수 안에 있는지를 이 검사가 잡는다.
    # friction 은 부정 시드가 직접 rage_click 을 내므로 특히 크게 갈린다 (§4.0).
    e6_rebuilt = {
        "friction_daily": (
            friction_daily, _friction_daily(sessionized, funnel_session, time_zone)
        ),
        "exit_daily": (
            exit_daily, _exit_daily(sessionized, funnel_session, time_zone)
        ),
        "entry_source_daily": (
            entry_source_daily,
            _entry_source_daily(product_fact, funnel_session, time_zone),
        ),
    }
    for name, (stored, expected) in e6_rebuilt.items():
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

    # product_id -> brand_id Dimension 매칭 (티켓 검증 항목).
    for name, frame in (("friction_daily", friction_daily), ("exit_daily", exit_daily)):
        unmatched = (
            frame.select("product_id", "brand_id").distinct()
            .join(
                dim_product.select(
                    "product_id", F.col("brand_id").alias("_dim_brand_id")
                ),
                ["product_id"],
                "left",
            )
            .where(
                F.col("_dim_brand_id").isNull()
                | (F.col("brand_id") != F.col("_dim_brand_id"))
            )
            .count()
        )
        checks.append(_check(
            f"{name}_brand_matches_dimension",
            unmatched == 0,
            f"unmatched_rows={unmatched}",
        ))

    # ── 상품 진단·고객군 콘텐츠 (dw-schema §4.1·§4.24·§4.25) ─────────────
    try:
        from .build_marts_job import MISSING_SEGMENT_VALUES, _product_exit_daily
    except ImportError:
        from build_marts_job import MISSING_SEGMENT_VALUES, _product_exit_daily

    counts["product_exit_daily"] = product_exit_daily.count()

    checks.append(_check(
        "product_exit_daily_grain_is_unique",
        _duplicate_count(product_exit_daily, [
            "event_date_kst", "brand_id", "product_id", "last_content_kind",
            *EXECUTION_AXES,
        ]) == 0,
        "product_exit_daily grain=date+brand+product+last_content_kind+축",
    ))

    invalid_exit_points = product_exit_daily.where(
        (F.col("exit_sessions") <= 0)
        | F.col("last_content_kind").isNull()
        | (F.length(F.trim(F.col("last_content_kind"))) == 0)
        | F.col("product_id").isNull()
        | F.col("brand_id").isNull()
    ).count()
    checks.append(_check(
        "product_exit_daily_values_follow_contract",
        invalid_exit_points == 0,
        f"invalid_rows={invalid_exit_points}",
    ))

    # §4.24 — 세션·상품마다 이탈 지점이 하나다. 합산이 상세를 연 세션을 넘으면
    # 한 세션이 두 지점에 들어갔다는 뜻이다.
    exit_totals = product_exit_daily.groupBy(
        "event_date_kst", "brand_id", "product_id", *EXECUTION_AXES
    ).agg(F.sum("exit_sessions").cast("long").alias("_exit_sessions"))
    detail_totals = exit_daily.select(
        "event_date_kst", "brand_id", "product_id", *EXECUTION_AXES,
        "detail_view_sessions",
    )
    exit_join_keys = ["event_date_kst", "brand_id", "product_id", *EXECUTION_AXES]
    exit_condition = None
    for column in exit_join_keys:
        clause = exit_totals[column].eqNullSafe(detail_totals[column])
        exit_condition = clause if exit_condition is None else exit_condition & clause
    exit_over_detail = (
        exit_totals.join(detail_totals, exit_condition, "inner")
        .where(F.col("_exit_sessions") > F.col("detail_view_sessions"))
        .count()
    )
    checks.append(_check(
        "product_exit_sessions_do_not_exceed_detail_views",
        exit_over_detail == 0,
        f"invalid_rows={exit_over_detail}; 세션당 이탈 지점은 하나다",
    ))

    # §4.1 신규 컬럼. grain 은 위쪽 product_daily 검사가 이미 본다.
    invalid_diagnostics = product_daily.where(
        (F.col("variant_select_count") < 0)
        | (F.col("wishlist_count") < 0)
        | (F.col("quick_look_close_open_detail_count") < 0)
        | (F.col("quick_look_close_open_detail_count") > F.col("quick_look_count"))
    ).count()
    checks.append(_check(
        "product_daily_diagnostic_counts_are_bounded",
        invalid_diagnostics == 0,
        f"invalid_rows={invalid_diagnostics}; 퀵룩→상세 <= 퀵룩 횟수",
    ))
    checks.append(_check(
        "product_event_fact_carries_close_reason",
        "close_reason" in product_fact.columns,
        "quick_look_close_open_detail_count 의 원천이다 (Q3 재실행 필요)",
    ))
    checks.append(_check(
        "product_event_fact_carries_action",
        "action" in product_fact.columns,
        "wishlist_count 가 찜 추가와 해제를 가르는 근거다 (Q3 재실행 필요)",
    ))
    checks.append(_check(
        "content_interest_fact_carries_co_visible_sum",
        "co_visible_le2_dwell_ms_sum" in content_interest.columns,
        "content_daily_kpi 의 겹침 제외 체류 원천이다 (Q3 재실행 필요)",
    ))

    segment_content = frames.get("segment_content_daily")
    if segment_content is None:
        warnings.append({
            "check": "segment_content_daily_is_absent",
            "detail": "bridge_persona_segment 를 만든 실행에서만 생성된다",
        })
    else:
        counts["segment_content_daily"] = segment_content.count()
        checks.append(_check(
            "segment_content_grain_is_unique",
            _duplicate_count(segment_content, [
                "event_date_kst", "brand_id", "skin_type", "content_kind",
                *EXECUTION_AXES,
            ]) == 0,
            "segment_content_daily grain=date+brand+skin_type+content_kind+축",
        ))

        invalid_segment_content = segment_content.where(
            (F.col("dwell_ms_sum") < 0)
            | (F.col("dwell_sessions") < 0)
            | (F.col("dwell_ms_sum") > F.col("segment_dwell_ms_sum"))
            | F.col("skin_type").isNull()
            | F.col("content_kind").isNull()
            | (F.col("dwell_share").isNotNull()
               & ~F.col("dwell_share").between(0.0, 1.0))
            | ((F.col("segment_dwell_ms_sum") == 0)
               & F.col("dwell_share").isNotNull())
            | ((F.col("segment_dwell_ms_sum") > 0) & F.col("dwell_share").isNull())
        ).count()
        checks.append(_check(
            "segment_content_values_follow_contract",
            invalid_segment_content == 0,
            f"invalid_rows={invalid_segment_content}; 분자 <= 분모 · 0~1 · 분모 0이면 NULL",
        ))

        # §4.25 — 한 피부 타입 안에서 share 합이 1 이다. 넘으면 분모가 어긋난 것이다.
        share_sums = segment_content.groupBy(
            "event_date_kst", "brand_id", "skin_type", *EXECUTION_AXES
        ).agg(F.sum("dwell_share").alias("_total")).where(
            F.col("_total") > F.lit(1.0) + F.lit(1e-6)
        ).count()
        checks.append(_check(
            "segment_content_shares_do_not_exceed_one",
            share_sums == 0,
            f"invalid_groups={share_sums}",
        ))

        # §4.25 — 세그먼트를 모르는 세션은 들어오면 안 된다.
        unknown_segments = segment_content.where(
            F.col("skin_type").isin(*MISSING_SEGMENT_VALUES)
        ).count()
        checks.append(_check(
            "segment_content_excludes_missing_segments",
            unknown_segments == 0,
            f"leaked_rows={unknown_segments}; notSureST 는 값이 아니라 결측이다",
        ))

    # 재계산 결정성. 시드 제외가 Mart 함수 안에 있는지를 잡는다.
    # segment_content_daily 는 bridge 가 검증 Job 입력에 없어 여기서 재계산하지
    # 못한다 — 시드 제외 경로는 단위 테스트가 고정한다.
    diagnostic_rebuilt = {
        "product_exit_daily": (product_exit_daily, _product_exit_daily(sessionized)),
    }
    for name, (stored, expected) in diagnostic_rebuilt.items():
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

    # ── 고객군 × 가격 밴드 (dw-schema §4.26) ──────────────────────────────
    segment_price_band = frames.get("segment_price_band")
    if segment_price_band is None:
        warnings.append({
            "check": "segment_price_band_daily_is_absent",
            "detail": "bridge_persona_segment 를 만든 실행에서만 생성된다",
        })
    else:
        counts["segment_price_band_daily_kpi"] = segment_price_band.count()
        s5_key = [
            "event_date_kst", "brand_id", "segment_type", "segment_value",
            "price_bin", "currency", *EXECUTION_AXES,
        ]
        checks.append(_check(
            "segment_price_band_grain_is_unique",
            _duplicate_count(segment_price_band, s5_key) == 0,
            "segment_price_band_daily_kpi grain=date+brand+segment+price_bin+통화+축",
        ))

        # 교차 축은 내지 않는다 — 셀이 100개가 되어 표본이 무너진다 (§4.26).
        checks.append(_check(
            "segment_price_band_axes_are_registered",
            segment_price_band.where(
                ~F.col("segment_type").isin(*PERSONA_SEGMENT_TYPES)
            ).count() == 0,
            f"허용 축={sorted(PERSONA_SEGMENT_TYPES)}; 교차 축은 제외한다",
        ))

        invalid_s5 = segment_price_band.where(
            (F.col("session_count") <= 0)
            | (F.col("segment_user_count") <= 0)
            | (F.col("product_view_sessions") > F.col("detail_view_sessions"))
            | (F.col("add_to_cart_sessions") > F.col("detail_view_sessions"))
            | (F.col("purchase_sessions") > F.col("detail_view_sessions"))
            | (F.col("detail_view_sessions") > F.col("session_count"))
            | (F.col("product_count") <= 0)
            | F.col("segment_value").isNull()
            | F.col("brand_id").isNull()
            | (F.col("view_to_cart_rate").isNotNull()
               & ~F.col("view_to_cart_rate").between(0.0, 1.0))
            | (F.col("view_to_purchase_rate").isNotNull()
               & ~F.col("view_to_purchase_rate").between(0.0, 1.0))
            | ((F.col("detail_view_sessions") == 0)
               & F.col("view_to_cart_rate").isNotNull())
            | ((F.col("detail_view_sessions") > 0)
               & F.col("view_to_cart_rate").isNull())
        ).count()
        checks.append(_check(
            "segment_price_band_values_follow_contract",
            invalid_s5 == 0,
            f"invalid_rows={invalid_s5}; 분자 <= 분모 · 0~1 · 분모 0이면 NULL",
        ))

        # price_bin 은 어휘집에서 파생한 값이어야 한다. NULL 은 가격 결측 보존이다.
        unknown_bins = (
            segment_price_band.where(F.col("price_bin").isNotNull())
            .select("price_bin").distinct()
            .join(
                price_band.where(F.col("price_bin").isNotNull())
                .select("price_bin").distinct(),
                ["price_bin"], "left_anti",
            ).count()
        ) if price_band is not None else 0
        checks.append(_check(
            "segment_price_band_bins_match_the_vocabulary",
            unknown_bins == 0,
            f"unknown_bins={unknown_bins}; §4.6-1 과 같은 구간이어야 한다",
        ))

        # §4.26 — 한 가격 구간의 세션은 그 세그먼트 세션의 부분집합이다.
        # 구간을 걸쳐 더하면 세션이 중복되므로 합이 아니라 **최댓값**으로 본다.
        if persona_segment is not None:
            segment_key = [
                "event_date_kst", "brand_id", "segment_type", "segment_value",
                *EXECUTION_AXES,
            ]
            per_cell = segment_price_band.groupBy(*segment_key).agg(
                F.max("detail_view_sessions").cast("long").alias("_bin_max")
            )
            parent = persona_segment.select(
                *segment_key,
                F.col("detail_view_sessions").alias("_segment_sessions"),
            )
            condition = None
            for column in segment_key:
                clause = per_cell[column].eqNullSafe(parent[column])
                condition = clause if condition is None else condition & clause
            over_parent = (
                per_cell.join(parent, condition, "inner")
                .where(F.col("_bin_max") > F.col("_segment_sessions"))
                .count()
            )
            checks.append(_check(
                "segment_price_band_cells_fit_inside_the_segment",
                over_parent == 0,
                f"invalid_cells={over_parent}; 구간 세션 <= 세그먼트 세션 (§4.6)",
            ))

    # ── Event 볼륨 (dw-schema §4.27) ──────────────────────────────────────
    try:
        from .build_marts_job import _event_daily, _observed_events
    except ImportError:
        from build_marts_job import _event_daily, _observed_events

    counts["event_daily"] = event_daily.count()

    checks.append(_check(
        "event_daily_grain_is_unique",
        _duplicate_count(event_daily, [
            "event_date_kst", "brand_id", "event_name", *EXECUTION_AXES,
        ]) == 0,
        "event_daily grain=date+brand+event_name+축",
    ))

    invalid_event_daily = event_daily.where(
        (F.col("event_count") <= 0)
        | (F.col("unique_session_count") < 0)
        | (F.col("unique_user_count") < 0)
        | (F.col("unique_session_count") > F.col("event_count"))
        | (F.col("unique_user_count") > F.col("event_count"))
        | F.col("event_name").isNull()
    ).count()
    checks.append(_check(
        "event_daily_counts_are_bounded",
        invalid_event_daily == 0,
        f"invalid_rows={invalid_event_daily}; 세션·사용자 <= Event 수",
    ))

    # §4.27 — Event 를 고르지 않고 전부 센다. 합이 어긋나면 어딘가에서 행이 빠진
    # 것이다. brand_id 가 NULL 인 플랫폼 공통 Event 를 지우면 여기서 걸린다.
    observed_events = _observed_events(cleaned).count()
    volume_total = event_daily.agg(
        F.sum("event_count").cast("long").alias("_total")
    ).first()["_total"] or 0
    checks.append(_check(
        "event_daily_covers_every_observed_event",
        observed_events == volume_total,
        f"cleaned={observed_events} · event_daily={volume_total}",
    ))

    # §4.27 — 상품에 귀속되지 않는 Event 가 남아 있어야 한다. 재생 데이터에서
    # 그것이 전체의 59% 다.
    platform_rows = event_daily.where(F.col("brand_id").isNull()).count()
    checks.append(_check(
        "event_daily_keeps_platform_wide_events",
        platform_rows > 0,
        f"brand_id NULL 행={platform_rows}; 지우면 볼륨 진단이 성립하지 않는다",
    ))

    # 재계산 결정성. 시드 제외가 Mart 함수 안에 있는지를 잡는다.
    columns = [c for c in event_daily.columns if c != "mart_processed_at"]
    expected_event_daily = _event_daily(cleaned, dim_product)
    difference = (
        expected_event_daily.select(*columns).exceptAll(
            event_daily.select(*columns)
        ).count()
        + event_daily.select(*columns).exceptAll(
            expected_event_daily.select(*columns)
        ).count()
    )
    checks.append(_check(
        "event_daily_is_deterministic_from_inputs",
        difference == 0,
        f"differing_rows={difference}; mart_processed_at excluded",
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
        "content_daily": config.content_daily_path,
        "content_conversion": config.content_conversion_path,
        "behavior_conversion": config.behavior_conversion_path,
        "friction_daily": config.friction_daily_path,
        "exit_daily": config.exit_daily_path,
        "entry_source_daily": config.entry_source_daily_path,
        "product_exit_daily": config.product_exit_daily_path,
        "event_daily": config.event_daily_path,
    }
    frames = {
        name: spark.read.option("mergeSchema", "true").parquet(path)
        for name, path in paths.items()
    }
    try:
        frames["persona_segment_daily"] = spark.read.option(
            "mergeSchema", "true"
        ).parquet(config.persona_segment_path)
    except Exception:
        # bridge_persona_segment 를 만들지 않은 실행에는 이 Mart 가 없다.
        pass
    try:
        frames["segment_price_band"] = spark.read.option(
            "mergeSchema", "true"
        ).parquet(config.segment_price_band_path)
    except Exception:
        # bridge_persona_segment 를 만들지 않은 실행에는 이 Mart 가 없다.
        pass
    try:
        frames["segment_content_daily"] = spark.read.option(
            "mergeSchema", "true"
        ).parquet(config.segment_content_daily_path)
    except Exception:
        # bridge_persona_segment 를 만들지 않은 실행에는 이 Mart 가 없다.
        pass
    try:
        frames["price_band_daily"] = spark.read.option(
            "mergeSchema", "true"
        ).parquet(config.price_band_path)
    except Exception:
        pass
    for name, path in (
        ("brand_cohort", config.brand_cohort_path),
        ("commons_cohort", config.commons_cohort_path),
    ):
        try:
            frames[name] = spark.read.option("mergeSchema", "true").parquet(path)
        except Exception:
            # Commons Mart 를 만들지 않은 실행에는 없다.
            pass
    try:
        frames["analytics_baseline"] = spark.read.option("mergeSchema", "true").parquet(
            config.baseline_path
        )
    except Exception:
        # 기준선을 만들지 않은 실행에서는 경로가 없다. 검증은 그대로 진행한다.
        pass
    return validate_frames(
        frames,
        config.require_events,
        config.time_zone,
        config.reason_trait_map_path,
        config.behavior_weights_path,
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
