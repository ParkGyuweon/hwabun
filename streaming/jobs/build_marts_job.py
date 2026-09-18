"""Build Funnel facts and dashboard marts from Processed datasets.

The job is a full-snapshot batch MVP.  Its inputs are the deduplicated
``sessionized_events`` and ``product_event_fact`` datasets only; Raw is never
read directly by a Mart job.

Outputs:

* ``funnel_session_fact``: one row per session and product
* ``product_daily_kpi``: product/event-date KPI counts and rates
* ``funnel_daily_kpi``: session-based funnel reach and conversion rates
* ``brand_daily_kpi``: brand/event-date KPI sessions and rates
* ``ingredient_weekly_interest``: position-weighted ingredient interest
* ``category_price_reference``: secondary-category median price reference
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any


DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_FUNNEL_SESSION_PATH = "data/processed/funnel_session_fact"
DEFAULT_PRODUCT_DAILY_PATH = "data/marts/product_daily_kpi"
DEFAULT_FUNNEL_DAILY_PATH = "data/marts/funnel_daily_kpi"
DEFAULT_BRAND_DAILY_PATH = "data/marts/brand_daily_kpi"
DEFAULT_PRODUCT_REPURCHASE_PATH = "data/marts/product_repurchase_daily"
DEFAULT_BRAND_REPURCHASE_PATH = "data/marts/brand_repurchase_daily"
DEFAULT_PURCHASE_REASON_PATH = "data/marts/purchase_reason_daily"
DEFAULT_PURCHASE_FACT_PATH = "data/processed/purchase_fact"
DEFAULT_PURCHASE_REASON_FACT_PATH = "data/processed/purchase_reason_fact"
DEFAULT_REASON_TRAIT_MAP_PATH = "contracts/purchase-reason-trait-map.json"
DEFAULT_REPURCHASE_WINDOW_DAYS = 90
DEFAULT_DIM_PRODUCT_PATH = "data/processed/dim_product"
DEFAULT_PRODUCT_INGREDIENT_PATH = "batch/ingest/data/serving/product_ingredient.csv"
DEFAULT_INGREDIENT_VOCAB_PATH = "batch/ingest/data/serving/ingredient_vocab.csv"
DEFAULT_INGREDIENT_WEEKLY_PATH = "data/marts/ingredient_weekly_interest"
DEFAULT_CATEGORY_PRICE_PATH = "data/marts/category_price_reference"
DEFAULT_PERSONA_SEGMENT_PATH = "data/marts/persona_segment_daily_kpi"
DEFAULT_PRICE_BAND_PATH = "data/marts/brand_price_band_daily_kpi"
DEFAULT_DIM_BRAND_PATH = "data/processed/dim_brand"
DEFAULT_BRAND_COHORT_PATH = "data/marts/brand_cohort_dim"
DEFAULT_COMMONS_COHORT_PATH = "data/marts/commons_cohort_weekly"
DEFAULT_CONTENT_INTEREST_PATH = "data/processed/content_interest_fact"
DEFAULT_CONTENT_DAILY_PATH = "data/marts/content_daily_kpi"
DEFAULT_CONTENT_CONVERSION_PATH = "data/marts/content_conversion_daily"
DEFAULT_BEHAVIOR_CONVERSION_PATH = "data/marts/behavior_conversion_daily"
DEFAULT_FRICTION_DAILY_PATH = "data/marts/friction_daily"
DEFAULT_EXIT_DAILY_PATH = "data/marts/exit_daily"
DEFAULT_ENTRY_SOURCE_DAILY_PATH = "data/marts/entry_source_daily"
DEFAULT_SECTION_DWELL_PATH = "data/processed/section_dwell_agg"
DEFAULT_PRODUCT_EXIT_DAILY_PATH = "data/marts/product_exit_daily"
DEFAULT_SEGMENT_CONTENT_DAILY_PATH = "data/marts/segment_content_daily"
DEFAULT_SEGMENT_PRICE_BAND_PATH = "data/marts/segment_price_band_daily_kpi"
DEFAULT_CLEANED_PATH = "data/processed/cleaned_events"
DEFAULT_EVENT_DAILY_PATH = "data/marts/event_daily"
# 저장소에 커밋하지 않는 생성물이다. 실행 전에
#   py contracts/persona/build_persona_tables.py --sample PC:all
DEFAULT_PERSONA_BRIDGE_PATH = (
    "contracts/persona/data/pcall/bridge_persona_segment.jsonl"
)
DEFAULT_BANNER_DAILY_PATH = "data/marts/banner_daily"
DEFAULT_USER_TRAIT_DAILY_PATH = "data/marts/user_trait_daily"
DEFAULT_CROSS_BRAND_DAILY_PATH = "data/marts/cross_brand_daily"
DEFAULT_BASELINE_PATH = "data/marts/analytics_baseline"
DEFAULT_TRAIT_WEIGHTS_PATH = "contracts/user-trait-weights.json"
DEFAULT_FEATURE_VOCAB_PATH = "contracts/product-feature-vocab.json"
DEFAULT_AFFINITY_LIFT_PATH = "batch/ingest/data/affinity_lift.csv"
DEFAULT_TIME_ZONE = "Asia/Seoul"
DEFAULT_BEHAVIOR_WEIGHTS_PATH = "frontend/src/types/log.ts"
DEFAULT_CLEANSING_CATEGORY_WEIGHT = 0.5
DEFAULT_PRICE_MIN_SAMPLE_SIZE = 3

DIRECT_INGREDIENT_EVENTS = ("text_selection", "text_copy")

# Quick Look은 목록에서 상세를 여는 경로다. 화면에 있는 정상 동선이고 여기서 바로
# 장바구니에 담을 수 있어서, 퍼널에서 빼면 담기 세션이 조회 세션보다 많아진다
# (Jira 235 실행 검증: 담기 6,029쌍 중 2,356쌍이 Quick Look 경유).
# 노출 Event 는 셋이다. 프론트는 카드 하나에 하나만 내는데, 목록 그리드는
# product_impression, 유사상품·맞춤 기획전은 recommendation_impression,
# 히어로 배너는 banner_impression 이다 (프론트 !305, 2026-09-17).
# **클릭은 어느 목록이든 product_click 을 낸다** — 배너도 banner_click 뒤에
# product_click 을 함께 낸다 (gen_behavior_logs.py:1289). 그래서 분자에 맞는
# 분모는 세 노출의 합이다. 하나라도 빼면 그 경로의 클릭이 분자에만 들어가
# 비율이 1 을 넘는다 (§4.1).
IMPRESSION_EVENTS = (
    "product_impression",
    "recommendation_impression",
    "banner_impression",
)

FUNNEL_PRODUCT_EVENTS = (
    *IMPRESSION_EVENTS,
    "product_click",
    "quick_look",
    "product_view",
    "add_to_cart",
    "begin_checkout",
    "purchase",
)

INFORMATION_SECTION_IDS = ("ingredients", "reviews")
INFORMATION_CONTENT_KINDS = (
    "ingredient_list",
    "ingredient_callout",
    "user_review",
    "review_stats",
    "review_filter",
)


@dataclass(frozen=True)
class BuildMartsConfig:
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    funnel_session_path: str = DEFAULT_FUNNEL_SESSION_PATH
    product_daily_path: str = DEFAULT_PRODUCT_DAILY_PATH
    funnel_daily_path: str = DEFAULT_FUNNEL_DAILY_PATH
    brand_daily_path: str = DEFAULT_BRAND_DAILY_PATH
    product_repurchase_path: str = DEFAULT_PRODUCT_REPURCHASE_PATH
    brand_repurchase_path: str = DEFAULT_BRAND_REPURCHASE_PATH
    purchase_reason_path: str = DEFAULT_PURCHASE_REASON_PATH
    purchase_fact_path: str = DEFAULT_PURCHASE_FACT_PATH
    purchase_reason_fact_path: str = DEFAULT_PURCHASE_REASON_FACT_PATH
    reason_trait_map_path: str = DEFAULT_REASON_TRAIT_MAP_PATH
    repurchase_window_days: int = DEFAULT_REPURCHASE_WINDOW_DAYS
    dim_product_path: str = DEFAULT_DIM_PRODUCT_PATH
    product_ingredient_path: str = DEFAULT_PRODUCT_INGREDIENT_PATH
    ingredient_vocab_path: str = DEFAULT_INGREDIENT_VOCAB_PATH
    ingredient_weekly_path: str = DEFAULT_INGREDIENT_WEEKLY_PATH
    category_price_path: str = DEFAULT_CATEGORY_PRICE_PATH
    persona_segment_path: str = DEFAULT_PERSONA_SEGMENT_PATH
    price_band_path: str = DEFAULT_PRICE_BAND_PATH
    dim_brand_path: str = DEFAULT_DIM_BRAND_PATH
    brand_cohort_path: str = DEFAULT_BRAND_COHORT_PATH
    commons_cohort_path: str = DEFAULT_COMMONS_COHORT_PATH
    content_interest_path: str = DEFAULT_CONTENT_INTEREST_PATH
    content_daily_path: str = DEFAULT_CONTENT_DAILY_PATH
    content_conversion_path: str = DEFAULT_CONTENT_CONVERSION_PATH
    behavior_conversion_path: str = DEFAULT_BEHAVIOR_CONVERSION_PATH
    friction_daily_path: str = DEFAULT_FRICTION_DAILY_PATH
    exit_daily_path: str = DEFAULT_EXIT_DAILY_PATH
    entry_source_daily_path: str = DEFAULT_ENTRY_SOURCE_DAILY_PATH
    section_dwell_path: str = DEFAULT_SECTION_DWELL_PATH
    product_exit_daily_path: str = DEFAULT_PRODUCT_EXIT_DAILY_PATH
    segment_content_daily_path: str = DEFAULT_SEGMENT_CONTENT_DAILY_PATH
    segment_price_band_path: str = DEFAULT_SEGMENT_PRICE_BAND_PATH
    cleaned_path: str = DEFAULT_CLEANED_PATH
    event_daily_path: str = DEFAULT_EVENT_DAILY_PATH
    persona_bridge_path: str = DEFAULT_PERSONA_BRIDGE_PATH
    banner_daily_path: str = DEFAULT_BANNER_DAILY_PATH
    user_trait_daily_path: str = DEFAULT_USER_TRAIT_DAILY_PATH
    cross_brand_daily_path: str = DEFAULT_CROSS_BRAND_DAILY_PATH
    baseline_path: str = DEFAULT_BASELINE_PATH
    trait_weights_path: str = DEFAULT_TRAIT_WEIGHTS_PATH
    feature_vocab_path: str = DEFAULT_FEATURE_VOCAB_PATH
    affinity_lift_path: str = DEFAULT_AFFINITY_LIFT_PATH
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH
    time_zone: str = DEFAULT_TIME_ZONE
    cleansing_category_weight: float = DEFAULT_CLEANSING_CATEGORY_WEIGHT
    price_min_sample_size: int = DEFAULT_PRICE_MIN_SAMPLE_SIZE
    baseline_policy_version: str | None = None
    baseline_start_date: str | None = None
    baseline_end_date: str | None = None

    def __post_init__(self) -> None:
        values = {
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
            "funnel_session_path": self.funnel_session_path,
            "product_daily_path": self.product_daily_path,
            "funnel_daily_path": self.funnel_daily_path,
            "brand_daily_path": self.brand_daily_path,
            "product_repurchase_path": self.product_repurchase_path,
            "brand_repurchase_path": self.brand_repurchase_path,
            "purchase_reason_path": self.purchase_reason_path,
            "purchase_fact_path": self.purchase_fact_path,
            "purchase_reason_fact_path": self.purchase_reason_fact_path,
            "reason_trait_map_path": self.reason_trait_map_path,
            "dim_product_path": self.dim_product_path,
            "product_ingredient_path": self.product_ingredient_path,
            "ingredient_vocab_path": self.ingredient_vocab_path,
            "ingredient_weekly_path": self.ingredient_weekly_path,
            "category_price_path": self.category_price_path,
            "persona_segment_path": self.persona_segment_path,
            "price_band_path": self.price_band_path,
            "dim_brand_path": self.dim_brand_path,
            "brand_cohort_path": self.brand_cohort_path,
            "commons_cohort_path": self.commons_cohort_path,
            "content_interest_path": self.content_interest_path,
            "content_daily_path": self.content_daily_path,
            "content_conversion_path": self.content_conversion_path,
            "behavior_conversion_path": self.behavior_conversion_path,
            "friction_daily_path": self.friction_daily_path,
            "exit_daily_path": self.exit_daily_path,
            "entry_source_daily_path": self.entry_source_daily_path,
            "section_dwell_path": self.section_dwell_path,
            "product_exit_daily_path": self.product_exit_daily_path,
            "segment_content_daily_path": self.segment_content_daily_path,
            "segment_price_band_path": self.segment_price_band_path,
            "cleaned_path": self.cleaned_path,
            "event_daily_path": self.event_daily_path,
            "persona_bridge_path": self.persona_bridge_path,
            "banner_daily_path": self.banner_daily_path,
            "user_trait_daily_path": self.user_trait_daily_path,
            "cross_brand_daily_path": self.cross_brand_daily_path,
            "baseline_path": self.baseline_path,
            "trait_weights_path": self.trait_weights_path,
            "feature_vocab_path": self.feature_vocab_path,
            "affinity_lift_path": self.affinity_lift_path,
            "behavior_weights_path": self.behavior_weights_path,
            "time_zone": self.time_zone,
        }
        for name, value in values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not 0 < self.cleansing_category_weight <= 1:
            raise ValueError("cleansing_category_weight must be in (0, 1]")
        if self.price_min_sample_size < 1:
            raise ValueError("price_min_sample_size must be at least 1")
        if self.repurchase_window_days < 1:
            raise ValueError("repurchase_window_days must be at least 1")
        baseline_values = (
            self.baseline_policy_version,
            self.baseline_start_date,
            self.baseline_end_date,
        )
        if any(baseline_values) and not all(baseline_values):
            raise ValueError("baseline policy version, start date, and end date must be supplied together")
        if all(baseline_values):
            try:
                start_date = date.fromisoformat(self.baseline_start_date or "")
                end_date = date.fromisoformat(self.baseline_end_date or "")
            except ValueError as error:
                raise ValueError("baseline dates must use YYYY-MM-DD") from error
            if start_date > end_date:
                raise ValueError("baseline start date must not be after end date")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None and value.strip() else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None and value.strip() else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Funnel facts and dashboard KPI marts from Processed Parquet."
    )
    parser.add_argument(
        "--sessionized-path",
        default=_env("SESSIONIZED_EVENTS_PATH", DEFAULT_SESSIONIZED_PATH),
        help="sessionized_events input path",
    )
    parser.add_argument(
        "--product-fact-path",
        default=_env("PRODUCT_EVENT_FACT_PATH", DEFAULT_PRODUCT_FACT_PATH),
        help="product_event_fact input path",
    )
    parser.add_argument(
        "--funnel-session-path",
        default=_env("FUNNEL_SESSION_FACT_PATH", DEFAULT_FUNNEL_SESSION_PATH),
        help="funnel_session_fact output path",
    )
    parser.add_argument(
        "--product-daily-path",
        default=_env("PRODUCT_DAILY_KPI_PATH", DEFAULT_PRODUCT_DAILY_PATH),
        help="product_daily_kpi output path",
    )
    parser.add_argument(
        "--funnel-daily-path",
        default=_env("FUNNEL_DAILY_KPI_PATH", DEFAULT_FUNNEL_DAILY_PATH),
        help="funnel_daily_kpi output path",
    )
    parser.add_argument(
        "--brand-daily-path",
        default=_env("BRAND_DAILY_KPI_PATH", DEFAULT_BRAND_DAILY_PATH),
        help="brand_daily_kpi output path",
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
        "--purchase-fact-path",
        default=_env("PURCHASE_FACT_PATH", DEFAULT_PURCHASE_FACT_PATH),
    )
    parser.add_argument(
        "--purchase-reason-fact-path",
        default=_env("PURCHASE_REASON_FACT_PATH", DEFAULT_PURCHASE_REASON_FACT_PATH),
    )
    parser.add_argument(
        "--reason-trait-map-path",
        default=_env("REASON_TRAIT_MAP_PATH", DEFAULT_REASON_TRAIT_MAP_PATH),
    )
    parser.add_argument(
        "--repurchase-window-days",
        type=int,
        default=_env_int("REPURCHASE_WINDOW_DAYS", DEFAULT_REPURCHASE_WINDOW_DAYS),
        help="재구매를 관측하는 창 길이(일)",
    )
    parser.add_argument(
        "--dim-product-path",
        default=_env("DIM_PRODUCT_PATH", DEFAULT_DIM_PRODUCT_PATH),
        help="dim_product input path",
    )
    parser.add_argument(
        "--product-ingredient-path",
        default=_env("PRODUCT_INGREDIENT_PATH", DEFAULT_PRODUCT_INGREDIENT_PATH),
        help="product_ingredient.csv input path",
    )
    parser.add_argument(
        "--ingredient-vocab-path",
        default=_env("INGREDIENT_VOCAB_PATH", DEFAULT_INGREDIENT_VOCAB_PATH),
        help="ingredient_vocab.csv input path",
    )
    parser.add_argument(
        "--ingredient-weekly-path",
        default=_env("INGREDIENT_WEEKLY_INTEREST_PATH", DEFAULT_INGREDIENT_WEEKLY_PATH),
        help="ingredient_weekly_interest output path",
    )
    parser.add_argument(
        "--category-price-path",
        default=_env("CATEGORY_PRICE_REFERENCE_PATH", DEFAULT_CATEGORY_PRICE_PATH),
        help="category_price_reference output path",
    )
    parser.add_argument(
        "--persona-segment-path",
        default=_env("PERSONA_SEGMENT_DAILY_PATH", DEFAULT_PERSONA_SEGMENT_PATH),
        help="persona_segment_daily_kpi output path",
    )
    parser.add_argument(
        "--price-band-path",
        default=_env("BRAND_PRICE_BAND_DAILY_PATH", DEFAULT_PRICE_BAND_PATH),
        help="brand_price_band_daily_kpi output path",
    )
    parser.add_argument(
        "--dim-brand-path",
        default=_env("DIM_BRAND_PATH", DEFAULT_DIM_BRAND_PATH),
        help="dim_brand input path (brand_hash · commons_participating)",
    )
    parser.add_argument(
        "--brand-cohort-path",
        default=_env("BRAND_COHORT_DIM_PATH", DEFAULT_BRAND_COHORT_PATH),
        help="brand_cohort_dim output path",
    )
    parser.add_argument(
        "--commons-cohort-path",
        default=_env("COMMONS_COHORT_WEEKLY_PATH", DEFAULT_COMMONS_COHORT_PATH),
        help="commons_cohort_weekly output path (B층 — dw-schema §2.5)",
    )
    parser.add_argument(
        "--content-interest-path",
        default=_env("CONTENT_INTEREST_FACT_PATH", DEFAULT_CONTENT_INTEREST_PATH),
        help="content_interest_fact input path",
    )
    parser.add_argument(
        "--content-daily-path",
        default=_env("CONTENT_DAILY_KPI_PATH", DEFAULT_CONTENT_DAILY_PATH),
        help="content_daily_kpi output path",
    )
    parser.add_argument(
        "--content-conversion-path",
        default=_env("CONTENT_CONVERSION_DAILY_PATH", DEFAULT_CONTENT_CONVERSION_PATH),
        help="content_conversion_daily output path",
    )
    parser.add_argument(
        "--behavior-conversion-path",
        default=_env("BEHAVIOR_CONVERSION_DAILY_PATH", DEFAULT_BEHAVIOR_CONVERSION_PATH),
        help="behavior_conversion_daily output path",
    )
    parser.add_argument(
        "--friction-daily-path",
        default=_env("FRICTION_DAILY_PATH", DEFAULT_FRICTION_DAILY_PATH),
        help="friction_daily output path",
    )
    parser.add_argument(
        "--exit-daily-path",
        default=_env("EXIT_DAILY_PATH", DEFAULT_EXIT_DAILY_PATH),
        help="exit_daily output path",
    )
    parser.add_argument(
        "--entry-source-daily-path",
        default=_env("ENTRY_SOURCE_DAILY_PATH", DEFAULT_ENTRY_SOURCE_DAILY_PATH),
        help="entry_source_daily output path",
    )
    parser.add_argument(
        "--section-dwell-path",
        default=_env("SECTION_DWELL_AGG_PATH", DEFAULT_SECTION_DWELL_PATH),
        help="section_dwell_agg input path",
    )
    parser.add_argument(
        "--product-exit-daily-path",
        default=_env("PRODUCT_EXIT_DAILY_PATH", DEFAULT_PRODUCT_EXIT_DAILY_PATH),
        help="product_exit_daily output path",
    )
    parser.add_argument(
        "--segment-content-daily-path",
        default=_env(
            "SEGMENT_CONTENT_DAILY_PATH", DEFAULT_SEGMENT_CONTENT_DAILY_PATH
        ),
        help="segment_content_daily output path",
    )
    parser.add_argument(
        "--segment-price-band-path",
        default=_env("SEGMENT_PRICE_BAND_PATH", DEFAULT_SEGMENT_PRICE_BAND_PATH),
        help="segment_price_band_daily_kpi output path",
    )
    parser.add_argument(
        "--cleaned-path",
        default=_env("CLEANED_EVENTS_PATH", DEFAULT_CLEANED_PATH),
        help="cleaned_events input path (event_daily)",
    )
    parser.add_argument(
        "--event-daily-path",
        default=_env("EVENT_DAILY_PATH", DEFAULT_EVENT_DAILY_PATH),
        help="event_daily output path",
    )
    parser.add_argument(
        "--persona-bridge-path",
        default=_env("PERSONA_BRIDGE_PATH", DEFAULT_PERSONA_BRIDGE_PATH),
        help="bridge_persona_segment JSONL. build_persona_tables.py --sample PC:all 로 만든다",
    )
    parser.add_argument("--banner-daily-path", default=_env("BANNER_DAILY_PATH", DEFAULT_BANNER_DAILY_PATH))
    parser.add_argument("--user-trait-daily-path", default=_env("USER_TRAIT_DAILY_PATH", DEFAULT_USER_TRAIT_DAILY_PATH))
    parser.add_argument("--cross-brand-daily-path", default=_env("CROSS_BRAND_DAILY_PATH", DEFAULT_CROSS_BRAND_DAILY_PATH))
    parser.add_argument("--baseline-path", default=_env("ANALYTICS_BASELINE_PATH", DEFAULT_BASELINE_PATH))
    parser.add_argument("--trait-weights-path", default=_env("TRAIT_WEIGHTS_PATH", DEFAULT_TRAIT_WEIGHTS_PATH))
    parser.add_argument("--feature-vocab-path", default=_env("FEATURE_VOCAB_PATH", DEFAULT_FEATURE_VOCAB_PATH))
    parser.add_argument("--affinity-lift-path", default=_env("AFFINITY_LIFT_PATH", DEFAULT_AFFINITY_LIFT_PATH))
    parser.add_argument(
        "--behavior-weights-path",
        default=_env("BEHAVIOR_WEIGHTS_PATH", DEFAULT_BEHAVIOR_WEIGHTS_PATH),
        help="Execution source for EVENT_WEIGHT",
    )
    parser.add_argument(
        "--time-zone",
        default=_env("ANALYTICS_TIME_ZONE", DEFAULT_TIME_ZONE),
        help="Time zone used for KST date columns",
    )
    parser.add_argument(
        "--cleansing-category-weight",
        type=float,
        default=_env_float(
            "CLEANSING_CATEGORY_WEIGHT", DEFAULT_CLEANSING_CATEGORY_WEIGHT
        ),
        help="Multiplier for secondary_category=Cleansers ingredient signals",
    )
    parser.add_argument(
        "--price-min-sample-size",
        type=int,
        default=_env_int("PRICE_MIN_SAMPLE_SIZE", DEFAULT_PRICE_MIN_SAMPLE_SIZE),
        help="Minimum valid prices required to use a category median",
    )
    parser.add_argument("--baseline-policy-version", default=os.getenv("BASELINE_POLICY_VERSION"))
    parser.add_argument("--baseline-start-date", default=os.getenv("BASELINE_START_DATE"))
    parser.add_argument("--baseline-end-date", default=os.getenv("BASELINE_END_DATE"))
    return parser


def parse_args(argv: list[str] | None = None) -> BuildMartsConfig:
    args = build_parser().parse_args(argv)
    return BuildMartsConfig(
        sessionized_path=args.sessionized_path,
        product_fact_path=args.product_fact_path,
        funnel_session_path=args.funnel_session_path,
        product_daily_path=args.product_daily_path,
        funnel_daily_path=args.funnel_daily_path,
        brand_daily_path=args.brand_daily_path,
        product_repurchase_path=args.product_repurchase_path,
        brand_repurchase_path=args.brand_repurchase_path,
        purchase_reason_path=args.purchase_reason_path,
        purchase_fact_path=args.purchase_fact_path,
        purchase_reason_fact_path=args.purchase_reason_fact_path,
        reason_trait_map_path=args.reason_trait_map_path,
        repurchase_window_days=args.repurchase_window_days,
        dim_product_path=args.dim_product_path,
        product_ingredient_path=args.product_ingredient_path,
        ingredient_vocab_path=args.ingredient_vocab_path,
        ingredient_weekly_path=args.ingredient_weekly_path,
        category_price_path=args.category_price_path,
        persona_segment_path=args.persona_segment_path,
        price_band_path=args.price_band_path,
        dim_brand_path=args.dim_brand_path,
        brand_cohort_path=args.brand_cohort_path,
        commons_cohort_path=args.commons_cohort_path,
        content_interest_path=args.content_interest_path,
        content_daily_path=args.content_daily_path,
        content_conversion_path=args.content_conversion_path,
        behavior_conversion_path=args.behavior_conversion_path,
        friction_daily_path=args.friction_daily_path,
        exit_daily_path=args.exit_daily_path,
        entry_source_daily_path=args.entry_source_daily_path,
        section_dwell_path=args.section_dwell_path,
        product_exit_daily_path=args.product_exit_daily_path,
        segment_content_daily_path=args.segment_content_daily_path,
        segment_price_band_path=args.segment_price_band_path,
        cleaned_path=args.cleaned_path,
        event_daily_path=args.event_daily_path,
        persona_bridge_path=args.persona_bridge_path,
        banner_daily_path=args.banner_daily_path,
        user_trait_daily_path=args.user_trait_daily_path,
        cross_brand_daily_path=args.cross_brand_daily_path,
        baseline_path=args.baseline_path,
        trait_weights_path=args.trait_weights_path,
        feature_vocab_path=args.feature_vocab_path,
        affinity_lift_path=args.affinity_lift_path,
        behavior_weights_path=args.behavior_weights_path,
        time_zone=args.time_zone,
        cleansing_category_weight=args.cleansing_category_weight,
        price_min_sample_size=args.price_min_sample_size,
        baseline_policy_version=args.baseline_policy_version,
        baseline_start_date=args.baseline_start_date,
        baseline_end_date=args.baseline_end_date,
    )


def _funnel_stage_events(sessionized_df: Any, product_fact_df: Any) -> Any:
    """Return one product-scoped Event stream for Funnel aggregation."""

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    sessionized_df = _observed_events(sessionized_df)
    product_fact_df = _observed_events(product_fact_df)

    product_events = product_fact_df.where(
        F.col("event_name").isin(*FUNNEL_PRODUCT_EVENTS)
    ).select(
        "event_id",
        "session_id",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "product_id",
        "category_id",
        "brand_id",
        "event_name",
        "event_time",
        "actor_type",
        "source",
    )

    properties = F.col("properties_json")
    section_id = F.get_json_object(properties, "$.section_id")
    content_kind = F.get_json_object(properties, "$.content_kind")
    action = F.get_json_object(properties, "$.action")
    opened = F.get_json_object(properties, "$.open")
    matched_ingredients = F.get_json_object(properties, "$.matched_ingredients")
    matched_keywords = F.get_json_object(properties, "$.matched_keywords")
    event_name = F.col("event_name")

    information_condition = (
        (
            (event_name == F.lit("section_view"))
            & (
                section_id.isin(*INFORMATION_SECTION_IDS)
                | content_kind.isin(*INFORMATION_CONTENT_KINDS)
            )
        )
        | (
            (event_name == F.lit("accordion_toggle"))
            & ((action == F.lit("expand")) | (opened == F.lit("true")))
        )
        | event_name.isin("review_filter_apply", "review_expand")
        | (
            event_name.isin("text_selection", "text_copy")
            & (matched_ingredients.isNotNull() | matched_keywords.isNotNull())
        )
    )

    information_events = sessionized_df.where(
        information_condition & F.col("product_id").isNotNull()
    ).select(
        "event_id",
        "session_id",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "product_id",
        "category_id",
        "brand_id",
        "event_name",
        "event_time",
        "actor_type",
        "source",
    )
    return product_events.unionByName(information_events)


def _build_funnel_session_fact(stage_events: Any, time_zone: str) -> Any:
    from pyspark.sql import functions as F

    # Information events retain their original names in the union.  Build the
    # timestamp separately so a section/review action counts as one Funnel
    # information stage without mutating the source Event name.
    stage_events = stage_events.withColumn(
        "_is_information_view",
        F.col("event_name").isin(
            "section_view",
            "accordion_toggle",
            "review_filter_apply",
            "review_expand",
            "text_selection",
            "text_copy",
        ),
    )
    grouped = stage_events.groupBy(
        "session_id",
        "product_id",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "actor_type",
        "source",
    ).agg(
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.first("brand_id", ignorenulls=True).alias("brand_id"),
        F.min(
            F.when(F.col("event_name").isin(*IMPRESSION_EVENTS), F.col("event_time"))
        ).alias("first_impression_at"),
        F.min(F.when(F.col("event_name") == "product_click", F.col("event_time"))).alias(
            "first_click_at"
        ),
        F.min(F.when(F.col("event_name") == "quick_look", F.col("event_time"))).alias(
            "first_quick_look_at"
        ),
        F.min(F.when(F.col("event_name") == "product_view", F.col("event_time"))).alias(
            "first_product_view_at"
        ),
        F.min(F.when(F.col("_is_information_view"), F.col("event_time"))).alias(
            "first_information_view_at"
        ),
        F.min(F.when(F.col("event_name") == "add_to_cart", F.col("event_time"))).alias(
            "first_add_to_cart_at"
        ),
        F.min(F.when(F.col("event_name") == "begin_checkout", F.col("event_time"))).alias(
            "first_checkout_at"
        ),
        F.min(F.when(F.col("event_name") == "purchase", F.col("event_time"))).alias(
            "first_purchase_at"
        ),
        F.max("event_time").alias("_last_event_at"),
    )

    first_stage = F.coalesce(
        F.col("first_impression_at"),
        F.col("first_click_at"),
        F.col("first_quick_look_at"),
        F.col("first_product_view_at"),
        F.col("first_information_view_at"),
        F.col("first_add_to_cart_at"),
        F.col("first_checkout_at"),
        F.col("first_purchase_at"),
    )
    reached = {
        "impression": F.col("first_impression_at").isNotNull(),
        "click": F.col("first_click_at").isNotNull(),
        "quick_look": F.col("first_quick_look_at").isNotNull(),
        "product_view": F.col("first_product_view_at").isNotNull(),
        "information_view": F.col("first_information_view_at").isNotNull(),
        "add_to_cart": F.col("first_add_to_cart_at").isNotNull(),
        "checkout": F.col("first_checkout_at").isNotNull(),
        "purchase": F.col("first_purchase_at").isNotNull(),
    }
    # 상세를 연 세션은 Quick Look이든 상품 상세든 하나다. 담기율의 분모는 이쪽이라야
    # 분자(담기)와 같은 모집단을 센다.
    reached["detail_view"] = reached["product_view"] | reached["quick_look"]
    # 상세를 어느 경로로 열었나. 둘 다 했으면 먼저 일어난 쪽으로 귀속한다.
    # 두 값이 배타라야 합이 detail_view_sessions 와 맞는다. 반대로
    # reached_quick_look 은 "퀵룩을 썼나" 라서 비배타로 남는다 — E2 진단의
    # quick_look_open_detail_rate 분모가 그 값이라 여기서 바꾸면 어긋난다.
    entry_path = (
        F.when(~reached["detail_view"], F.lit(None).cast("string"))
        .when(~reached["quick_look"], F.lit("direct_click"))
        .when(~reached["product_view"], F.lit("quick_look"))
        .when(
            F.col("first_quick_look_at") <= F.col("first_product_view_at"),
            F.lit("quick_look"),
        )
        .otherwise(F.lit("direct_click"))
    )
    dropoff_step = (
        F.when(reached["purchase"], F.lit(None).cast("string"))
        .when(reached["checkout"], F.lit("checkout"))
        .when(reached["add_to_cart"], F.lit("add_to_cart"))
        .when(reached["information_view"], F.lit("information_view"))
        .when(reached["product_view"], F.lit("product_view"))
        .when(reached["quick_look"], F.lit("quick_look"))
        .when(reached["click"], F.lit("click"))
        .when(reached["impression"], F.lit("impression"))
    )

    return grouped.select(
        F.to_date(F.from_utc_timestamp(first_stage, time_zone)).alias("funnel_date_kst"),
        "session_id",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "product_id",
        "category_id",
        "brand_id",
        "actor_type",
        "source",
        "first_impression_at",
        "first_click_at",
        "first_quick_look_at",
        "first_product_view_at",
        "first_information_view_at",
        "first_add_to_cart_at",
        "first_checkout_at",
        "first_purchase_at",
        reached["impression"].alias("reached_impression"),
        reached["click"].alias("reached_click"),
        reached["quick_look"].alias("reached_quick_look"),
        entry_path.alias("detail_entry_path"),
        reached["detail_view"].alias("reached_detail_view"),
        reached["product_view"].alias("reached_product_view"),
        reached["information_view"].alias("reached_information_view"),
        reached["add_to_cart"].alias("reached_add_to_cart"),
        reached["checkout"].alias("reached_checkout"),
        reached["purchase"].alias("reached_purchase"),
        dropoff_step.alias("dropoff_step"),
        F.current_timestamp().alias("processed_at"),
    )


def _safe_ratio(numerator: Any, denominator: Any) -> Any:
    from pyspark.sql import functions as F

    return F.when(
        denominator > 0,
        numerator.cast("double") / denominator.cast("double"),
    ).otherwise(F.lit(None).cast("double"))


def _product_daily_kpi(
    product_fact_df: Any, event_weights: dict[str, float] | None = None
) -> Any:
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    group_columns = ["event_date_kst", "product_id", *EXECUTION_AXES]

    def count_events(event_name: str) -> Any:
        return F.sum(
            F.when(F.col("event_name") == F.lit(event_name), F.lit(1)).otherwise(F.lit(0))
        ).cast("long").alias(f"{event_name}_count")

    aggregations = [
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.first("brand_id", ignorenulls=True).alias("brand_id"),
        count_events("product_impression"),
        # 추천·배너 카드의 노출. product_click 이 여기서도 나오므로 CTR 분모에
        # 함께 들어간다. 컬럼을 따로 두는 이유는 노출 판정 기준이 달라서다
        # — 목록은 hold 300ms, 추천은 1000ms (§4.1).
        count_events("recommendation_impression"),
        count_events("banner_impression"),
        count_events("product_click"),
        count_events("quick_look"),
        # 뒤로가기 재조회를 뺀 새 진입만 센다 (§4.1). detail_entry_rate 의
        # 분자라, 재조회를 포함하면 노출보다 조회가 많아질 수 있다.
        F.sum(
            F.when(
                (F.col("event_name") == F.lit("product_view"))
                & ~F.coalesce(
                    F.col("navigation_source") == F.lit(HISTORY_BACK_NAVIGATION),
                    F.lit(False),
                ),
                F.lit(1),
            ).otherwise(F.lit(0))
        ).cast("long").alias("product_view_count"),
        count_events("add_to_cart"),
        count_events("remove_from_cart"),
        count_events("purchase"),
        # 옵션 왕복. 같은 상품을 여러 번 고르면 그만큼 센다 (§4.1).
        count_events("variant_select"),
        # 찜은 토글이라 같은 Event 가 추가와 해제를 모두 싣는다. 관심을
        # 재는 지표라서 추가만 센다 (§4.1). action 이 없는 옛 로그는
        # 해제를 보낸 적이 없어 추가로 본다.
        F.sum(
            F.when(
                (F.col("event_name") == F.lit("wishlist_toggle"))
                & F.coalesce(F.col("action"), F.lit(WISHLIST_ADD_ACTION))
                .eqNullSafe(F.lit(WISHLIST_ADD_ACTION)),
                F.lit(1),
            ).otherwise(F.lit(0))
        ).cast("long").alias("wishlist_count"),
        # 퀵룩에서 상세로 넘어간 횟수. close_reason 은 product_event_fact 가
        # 싣는다 — 여기서 properties 를 다시 파싱하면 원천이 둘이 된다.
        F.sum(
            F.when(
                (F.col("event_name") == F.lit("quick_look_close"))
                & (F.col("close_reason") == F.lit(OPEN_DETAIL_CLOSE_REASON)),
                F.lit(1),
            ).otherwise(F.lit(0))
        ).cast("long").alias("quick_look_close_open_detail_count"),
        F.coalesce(
            F.sum(F.when(F.col("event_name") == "purchase", F.col("purchase_quantity"))),
            F.lit(0),
        ).cast("long").alias("purchase_quantity"),
        F.countDistinct(
            F.when(F.col("event_name") == "quick_look", F.col("session_id"))
        ).alias("quick_look_sessions"),
        F.countDistinct(
            F.when(F.col("event_name") == "product_view", F.col("session_id"))
        ).alias("product_view_sessions"),
        # 상세를 연 세션은 상품 상세든 Quick Look이든 하나다. 담기·구매의 분모라서
        # 분자와 같은 모집단을 세야 한다 (dw-schema.md §4.1, 데이터 235 수정안 2).
        F.countDistinct(
            F.when(
                F.col("event_name").isin("product_view", "quick_look"),
                F.col("session_id"),
            )
        ).alias("detail_view_sessions"),
        F.countDistinct(
            F.when(F.col("event_name") == "add_to_cart", F.col("session_id"))
        ).alias("add_to_cart_sessions"),
        F.countDistinct(
            F.when(F.col("event_name") == "remove_from_cart", F.col("session_id"))
        ).alias("remove_from_cart_sessions"),
        F.countDistinct(
            F.when(F.col("event_name") == "purchase", F.col("session_id"))
        ).alias("purchase_sessions"),
        F.countDistinct(
            F.when(F.col("event_name") == "purchase", F.col("order_id"))
        ).alias("purchase_count_distinct_order"),
        F.sum(
            F.when(F.col("event_name") == "purchase", F.col("item_revenue"))
        ).cast("decimal(18,2)").alias("revenue_amount"),
        # 통화 혼입은 Q5가 별도로 실패시킨다. 실패 보고서와 재계산 결과 자체는
        # 입력 파티션 순서에 흔들리지 않아야 하므로 대표값은 결정적으로 고른다.
        F.min("currency").alias("currency"),
        F.countDistinct(F.col("user_id")).alias("unique_user_count"),
        F.countDistinct(F.col("session_id")).alias("session_count"),
        F.current_timestamp().alias("mart_processed_at"),
    ]
    if event_weights:
        product_interest_score = F.lit(0.0)
        for event_name, weight in event_weights.items():
            product_interest_score = product_interest_score + F.when(
                F.col("event_name") == F.lit(event_name), F.lit(float(weight))
            ).otherwise(F.lit(0.0))
        aggregations.append(
            F.sum(product_interest_score)
            .cast("double")
            .alias("product_interest_score")
        )
    else:
        aggregations.append(F.lit(None).cast("double").alias("product_interest_score"))

    result = product_fact_df.groupBy(*group_columns).agg(*aggregations)

    return (
        result.withColumn(
            "purchase_count",
            F.col("purchase_count_distinct_order"),
        )
        .drop("purchase_count_distinct_order")
        # 분모는 두 노출의 합이다. product_impression 만 쓰면 추천 카드에서 온
        # 클릭이 분자에만 들어가 비율이 1 을 넘는다 (§4.1).
        .withColumn(
            "impression_count",
            (
                F.col("product_impression_count")
                + F.col("recommendation_impression_count")
                + F.col("banner_impression_count")
            ).cast("long"),
        )
        .withColumn("product_ctr", _safe_ratio(F.col("product_click_count"), F.col("impression_count")))
        .withColumn("detail_entry_rate", _safe_ratio(F.col("product_view_count"), F.col("impression_count")))
        .withColumn("add_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")))
        .withColumn("purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")))
    )


def _funnel_daily_kpi(funnel_session_df: Any) -> Any:
    from pyspark.sql import functions as F

    group_columns = ["funnel_date_kst", "product_id", *EXECUTION_AXES]
    # detail_entry_path 는 상세를 열지 않은 세션에서 의도적으로 NULL 이다.
    # 일반 == 비교는 그 세션을 False 가 아닌 NULL 로 만들어, 그룹 전체가 해당하면
    # sum 결과까지 NULL 로 전파한다. 경로 없음은 direct click 이 아니라는 뜻이다.
    is_direct_entry = F.col("detail_entry_path").eqNullSafe(F.lit("direct_click"))
    result = funnel_session_df.groupBy(*group_columns).agg(
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.first("brand_id", ignorenulls=True).alias("brand_id"),
        F.sum(F.col("reached_impression").cast("int")).cast("long").alias("impression_sessions"),
        F.sum(F.col("reached_click").cast("int")).cast("long").alias("click_sessions"),
        # 퀵룩 계열은 비배타다 — "퀵룩을 썼나". E2 진단의 퀵룩 담기율이 이 분모를 쓴다.
        F.sum(F.col("reached_quick_look").cast("int")).cast("long").alias("quick_look_sessions"),
        F.sum(
            (F.col("reached_quick_look") & F.col("reached_add_to_cart")).cast("int")
        ).cast("long").alias("quick_look_cart_sessions"),
        # 직접 클릭 계열은 배타다 — "퀵룩 없이 상세로 직행했나". 둘 다면 먼저 한 쪽.
        F.sum(
            is_direct_entry.cast("int")
        ).cast("long").alias("direct_click_sessions"),
        F.sum(
            (
                is_direct_entry & F.col("reached_add_to_cart")
            ).cast("int")
        ).cast("long").alias("direct_click_cart_sessions"),
        # "클릭한 세션 중 상세로 간 세션". direct_click 만으로는 부족하다 —
        # 그 값은 "퀵룩 없이 상세로 갔나" 라서 클릭을 요구하지 않는다.
        # hist: 이력 세션처럼 클릭 없이 상세를 여는 경로가 있어 분자가 분모를
        # 넘는다 (104만 건 재생에서 1,493 세션 · 849행). 둘을 AND 해야
        # click_to_view_rate 가 1 을 넘지 않는다 (§4.5, 프론트 확정 2026-09-17).
        F.sum(
            (
                F.col("reached_click")
                & is_direct_entry
            ).cast("int")
        ).cast("long").alias("click_through_detail_sessions"),
        F.sum(F.col("reached_detail_view").cast("int")).cast("long").alias("detail_view_sessions"),
        F.sum(F.col("reached_product_view").cast("int")).cast("long").alias("product_view_sessions"),
        F.sum(F.col("reached_information_view").cast("int")).cast("long").alias("information_view_sessions"),
        F.sum(F.col("reached_add_to_cart").cast("int")).cast("long").alias("add_to_cart_sessions"),
        F.sum(F.col("reached_checkout").cast("int")).cast("long").alias("checkout_sessions"),
        F.sum(F.col("reached_purchase").cast("int")).cast("long").alias("purchase_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumn("impression_to_click_rate", _safe_ratio(F.col("click_sessions"), F.col("impression_sessions")))
        # 분자는 "클릭하고 상세로 간 세션" 이다. product_view_sessions 를 쓰면
        # 클릭 없이 상세에 도달한 세션이 분자에만 들어가 1 을 넘는다.
        .withColumn(
            "click_to_view_rate",
            _safe_ratio(F.col("click_through_detail_sessions"), F.col("click_sessions")),
        )
        .withColumn("view_to_information_rate", _safe_ratio(F.col("information_view_sessions"), F.col("product_view_sessions")))
        # 전환 분모는 상세를 연 세션이다. Quick Look에서 담거나 사는 경로가 있어서
        # product_view만 분모로 두면 분자와 모집단이 어긋나 비율이 1.0을 넘는다.
        .withColumn("view_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")))
        .withColumn("cart_to_purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("add_to_cart_sessions")))
        .withColumn("view_to_purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")))
        .withColumn(
            "dropoff_after_impression_rate",
            F.when(
                F.col("impression_sessions") > 0,
                F.lit(1.0) - F.col("click_sessions") / F.col("impression_sessions"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            # view_to_cart_rate 의 여집합이라 같은 분모를 써야 한다.
            "dropoff_after_view_rate",
            F.when(
                F.col("detail_view_sessions") > 0,
                F.lit(1.0) - F.col("add_to_cart_sessions") / F.col("detail_view_sessions"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "dropoff_after_cart_rate",
            F.when(
                F.col("add_to_cart_sessions") > 0,
                F.lit(1.0) - F.col("purchase_sessions") / F.col("add_to_cart_sessions"),
            ).otherwise(F.lit(None).cast("double")),
        )
    )


def _brand_daily_kpi(product_fact_df: Any, funnel_session_df: Any, time_zone: str) -> Any:
    """Aggregate brand KPIs from facts without summing product-grain sessions."""

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    axes = list(EXECUTION_AXES)
    key_columns = ["event_date_kst", "brand_id", *axes]
    valid_brand = F.col("brand_id").isNotNull() & (
        F.length(F.trim(F.col("brand_id"))) > 0
    )

    product_events = product_fact_df.where(
        valid_brand
        & F.col("event_name").isin(
            # 노출 세 Event 를 다 들여야 한다. 여기서 빠지면 아래 _impression
            # 판정을 고쳐도 그 행이 애초에 안 들어온다 (§4.1).
            *IMPRESSION_EVENTS,
            "product_click", "product_view",
            "quick_look", "add_to_cart",
        )
    ).select(
        *key_columns,
        "session_id",
        "user_id",
        "product_id",
        # 노출은 세 Event 다 (IMPRESSION_EVENTS, §4.1). product_impression 만
        # 세면 추천·배너로만 노출된 세션이 분모에서 빠져 detail_entry_rate 가
        # 1 을 넘는다 — 104만 건 실행에서 persona_segment 가 그렇게 걸렸다.
        F.col("event_name").isin(*IMPRESSION_EVENTS).alias("_impression"),
        (F.col("event_name") == "product_click").alias("_click"),
        (F.col("event_name") == "product_view").alias("_product_view"),
        (F.col("event_name") == "quick_look").alias("_quick_look"),
        # 상세를 연 세션은 Quick Look이든 상품 상세든 하나다. 담기율의 분모라서
        # 분자(담기)와 같은 모집단을 세야 한다.
        F.col("event_name").isin("product_view", "quick_look").alias("_detail_view"),
        F.lit(False).alias("_information_view"),
        (F.col("event_name") == "add_to_cart").alias("_add_to_cart"),
    )

    # Information actions are stored on the product-scoped Funnel fact. Keep
    # only brand sessions that also reached a product view on the same KST day;
    # this preserves the information/cart <= view Funnel contract at day grain.
    view_keys = product_events.where(F.col("_product_view")).select(
        *key_columns, "session_id"
    ).distinct()
    information_events = funnel_session_df.where(
        valid_brand & F.col("first_information_view_at").isNotNull()
    ).select(
        F.to_date(
            F.from_utc_timestamp(F.col("first_information_view_at"), time_zone)
        ).alias("event_date_kst"),
        "brand_id",
        *axes,
        "session_id",
        "user_id",
        "product_id",
    )
    join_condition = [
        information_events[column].eqNullSafe(view_keys[column])
        for column in [*key_columns, "session_id"]
    ]
    information_events = information_events.join(
        view_keys, join_condition, "left_semi"
    ).select(
        *key_columns,
        "session_id",
        "user_id",
        "product_id",
        F.lit(False).alias("_impression"),
        F.lit(False).alias("_click"),
        F.lit(False).alias("_product_view"),
        F.lit(False).alias("_quick_look"),
        F.lit(False).alias("_detail_view"),
        F.lit(True).alias("_information_view"),
        F.lit(False).alias("_add_to_cart"),
    )

    stages = product_events.unionByName(information_events)
    result = stages.groupBy(*key_columns).agg(
        F.countDistinct(F.when(F.col("_impression"), F.col("session_id"))).cast("long").alias("impression_sessions"),
        F.countDistinct(F.when(F.col("_click"), F.col("session_id"))).cast("long").alias("click_sessions"),
        F.countDistinct(F.when(F.col("_quick_look"), F.col("session_id"))).cast("long").alias("quick_look_sessions"),
        F.countDistinct(F.when(F.col("_detail_view"), F.col("session_id"))).cast("long").alias("detail_view_sessions"),
        F.countDistinct(F.when(F.col("_product_view"), F.col("session_id"))).cast("long").alias("product_view_sessions"),
        F.countDistinct(F.when(F.col("_information_view"), F.col("session_id"))).cast("long").alias("information_view_sessions"),
        F.countDistinct(F.when(F.col("_add_to_cart"), F.col("session_id"))).cast("long").alias("add_to_cart_sessions"),
        F.countDistinct("user_id").cast("long").alias("unique_user_count"),
        F.countDistinct(F.when(F.col("_product_view"), F.col("product_id"))).cast("long").alias("product_count_viewed"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumn("detail_entry_rate", _safe_ratio(F.col("detail_view_sessions"), F.col("impression_sessions")))
        .withColumn("information_view_rate", _safe_ratio(F.col("information_view_sessions"), F.col("product_view_sessions")))
        # 담기 분모는 상세를 연 세션이다. Quick Look에서 담는 경로가 있어서
        # product_view만 분모로 두면 분자와 모집단이 어긋나 비율이 1.0을 넘는다.
        .withColumn("view_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")))
    )


# 실행 축. `generator_type`이 있어야 PC(python_batch)와 PA(agent_llm)를 가른다.
# PA 로그는 정성 축이라 정량 지표에 섞으면 안 되는데 `actor_type`은 둘 다
# `synthetic`이라 구분이 안 된다 (persona-schema.md §9, dw-schema.md §2).
EXECUTION_AXES = (
    "actor_type",
    "source",
    "generator_type",
    "scenario_id",
    "simulation_run_id",
)


def _observed_events(frame: Any | None) -> Any | None:
    """시드 Event를 뺀 관측 행동만 남긴다.

    시드는 생성기가 Persona의 사전 선호를 주입하려고 만든 것이라 관측된 행동이 아니다
    (`event-properties-schema.md` §3.14). 긍정 시드는 조회 없이 담기만, 부정 시드는
    담기 없는 조회를 내서 전환 지표의 분자와 분모를 양방향으로 왜곡한다. 어느 Mart가
    제외 대상인지는 `dw-schema.md`가 정본이다.

    `is_seeded`가 없는 입력은 시드 판정 이전에 만들어진 것이라 그대로 통과시킨다.
    """

    from pyspark.sql import functions as F

    if frame is None or "is_seeded" not in frame.columns:
        return frame
    return frame.where(~F.coalesce(F.col("is_seeded"), F.lit(False)))


def _valid_brand() -> Any:
    from pyspark.sql import functions as F

    return F.col("brand_id").isNotNull() & (F.length(F.trim(F.col("brand_id"))) > 0)


def _null_safe_join(left: Any, right: Any, columns: list[str]) -> Any:
    """실행 축의 NULL은 같은 값으로 봐야 한다. 등호 Join이면 그 행이 통째로 빠진다.

    오른쪽 key를 임시 이름으로 바꾼 뒤 붙인다. 같은 이름을 그대로 두면 Join 뒤
    `drop`이 어느 쪽인지 못 가려 왼쪽 key까지 지우고, 매칭되지 않은 행의 key가
    NULL로 남는다.
    """

    renamed = right
    aliases = {column: f"_join_{column}" for column in columns}
    for column, alias in aliases.items():
        renamed = renamed.withColumnRenamed(column, alias)
    condition = None
    for column, alias in aliases.items():
        clause = left[column].eqNullSafe(renamed[alias])
        condition = clause if condition is None else condition & clause
    return left.join(renamed, condition, "left").drop(*aliases.values())


def _null_safe_semi_join(left: Any, right: Any, columns: list[str]) -> Any:
    """``left`` 에서 ``right`` 에 있는 key 의 행만 남긴다. NULL 축을 같은 값으로 본다.

    ``_null_safe_join`` 과 달리 오른쪽 컬럼을 가져오지 않으므로 이름 충돌이
    없고 rename 도 필요 없다.
    """

    condition = None
    for column in columns:
        clause = left[column].eqNullSafe(right[column])
        condition = clause if condition is None else condition & clause
    return left.join(right, condition, "left_semi")


# 피부 세그먼트 축. Jira 277 이 요구하는 세 종류만 낸다. bridge 에는
# hair_color·eye_color·review_bucket·persona_source 도 있지만 대시보드 고객군
# 화면(dashboard-redesign-spec.md §2-3)이 피부 축만 쓴다.
SEGMENT_TYPES = ("skin_type", "skin_tone")
CROSS_SEGMENT_TYPE = "skin_type_x_skin_tone"

# 값이 아니라 결측이다 (persona-schema.md §3). segment_value 로 새면
# "모르겠다" 가 하나의 고객군으로 잡힌다.
MISSING_SEGMENT_VALUES = ("notSureST",)


def load_persona_segments(spark: Any, path: str) -> Any:
    """bridge_persona_segment JSONL 을 읽는다.

    저장소에 커밋하지 않는 생성물이라 (`.gitignore` 의 ``data/``) 실행 전에
    ``py contracts/persona/build_persona_tables.py --sample PC:all`` 로 만든다.
    """

    from pyspark.sql.types import StringType, StructField, StructType

    schema = StructType([
        StructField("persona_id", StringType(), True),
        StructField("segment_type", StringType(), True),
        StructField("segment_value", StringType(), True),
    ])
    return spark.read.schema(schema).json(path)


def _persona_segments(bridge_df: Any) -> Any:
    """bridge 를 단일 축 2종과 교차 축 1종으로 넓힌다.

    교차 축을 따로 만드는 이유는 합산으로 구할 수 없기 때문이다. 건성·fair 셀의
    세션 수는 건성 행과 fair 행 어디에도 없다.
    """

    from pyspark.sql import functions as F

    base = bridge_df.where(
        F.col("segment_type").isin(*SEGMENT_TYPES)
        & F.col("segment_value").isNotNull()
        & (F.length(F.trim(F.col("segment_value"))) > 0)
        & ~F.col("segment_value").isin(*MISSING_SEGMENT_VALUES)
    ).select("persona_id", "segment_type", "segment_value")

    wide = base.groupBy("persona_id").pivot(
        "segment_type", list(SEGMENT_TYPES)
    ).agg(F.first("segment_value", ignorenulls=True))
    cross = wide.where(
        F.col("skin_type").isNotNull() & F.col("skin_tone").isNotNull()
    ).select(
        "persona_id",
        F.lit(CROSS_SEGMENT_TYPE).alias("segment_type"),
        F.concat_ws("|", F.col("skin_type"), F.col("skin_tone")).alias("segment_value"),
    )
    return base.unionByName(cross)


def _persona_segment_daily_kpi(
    product_fact_df: Any,
    bridge_df: Any,
    event_weights: dict[str, float] | None = None,
) -> Any:
    """피부 세그먼트별 브랜드 KPI.

    브랜드 grain 이다. `product_id` 를 key 에 두면 세그먼트 합계를 낼 때 한 세션이
    상품 수만큼 중복으로 세어진다 — `brand_daily_kpi` 가 `product_daily_kpi` 합산으로
    만들어질 수 없는 것과 같은 이유다 (dw-schema.md §4.6).

    `persona_id` 가 없는 세션은 어느 행에도 들어가지 않는다. 실제 사용자의 피부 정보는
    이벤트 경로에 없으므로 임의 세그먼트에 귀속하면 없는 사실을 만들어 낸다. 그래서
    세그먼트 행의 합은 `brand_daily_kpi` 전체와 같지 않고, 다른 것이 정상이다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    segments = _persona_segments(bridge_df)
    events = product_fact_df.where(
        _valid_brand()
        & F.col("persona_id").isNotNull()
        & (F.length(F.trim(F.col("persona_id"))) > 0)
    ).join(segments, ["persona_id"], "inner")

    key_columns = [
        "event_date_kst", "brand_id", "segment_type", "segment_value", *EXECUTION_AXES
    ]

    def stage_sessions(condition: Any, alias: str) -> Any:
        return F.countDistinct(
            F.when(condition, F.col("session_id"))
        ).cast("long").alias(alias)

    is_detail = F.col("event_name").isin("product_view", "quick_look")
    aggregations = [
        F.countDistinct("user_id").cast("long").alias("segment_user_count"),
        F.countDistinct("session_id").cast("long").alias("session_count"),
        # 노출 세 Event 를 함께 센다 (§4.1). 분모가 좁으면 비율이 1 을 넘는다.
        stage_sessions(
            F.col("event_name").isin(*IMPRESSION_EVENTS), "impression_sessions"
        ),
        stage_sessions(F.col("event_name") == "quick_look", "quick_look_sessions"),
        stage_sessions(F.col("event_name") == "product_view", "product_view_sessions"),
        stage_sessions(is_detail, "detail_view_sessions"),
        stage_sessions(F.col("event_name") == "add_to_cart", "add_to_cart_sessions"),
        stage_sessions(F.col("event_name") == "purchase", "purchase_sessions"),
        F.countDistinct(
            F.when(is_detail, F.col("product_id"))
        ).cast("long").alias("product_count_viewed"),
        F.current_timestamp().alias("mart_processed_at"),
    ]
    if event_weights:
        interest = F.lit(0.0)
        for event_name, weight in event_weights.items():
            interest = interest + F.when(
                F.col("event_name") == F.lit(event_name), F.lit(float(weight))
            ).otherwise(F.lit(0.0))
        aggregations.append(
            F.sum(interest).cast("double").alias("interest_score")
        )
    else:
        aggregations.append(F.lit(None).cast("double").alias("interest_score"))

    result = events.groupBy(*key_columns).agg(*aggregations)
    return (
        result
        # 담기·구매 분모는 상세를 연 세션이다 (§4.1·§4.14 와 같은 규칙).
        .withColumn(
            "view_to_cart_rate",
            _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")),
        )
        .withColumn(
            "view_to_purchase_rate",
            _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")),
        )
        .withColumn(
            "detail_entry_rate",
            _safe_ratio(F.col("detail_view_sessions"), F.col("impression_sessions")),
        )
        # 관심도 평균의 분모는 세션 수다 (dw-schema.md §2.3).
        .withColumn(
            "avg_interest_score",
            _safe_ratio(F.col("interest_score"), F.col("session_count")),
        )
        .drop("interest_score")
    )


def load_price_bins(feature_vocab_path: str) -> list[tuple[str, float | None]]:
    """추천 어휘집에서 가격 구간을 읽는다. 경계 숫자를 여기에 복제하지 않는다.

    ``price_bin`` 은 추천 CBF 피처·배너 축·상품 등록 화면이 이미 쓰는 축이다
    (`product-feature-spec.md` §4.1). 대시보드가 다른 구간을 정의하면 같은 이름의
    가격대가 두 벌이 되어 "이 가격대 반응" 이 어느 쪽 구간인지 알 수 없게 된다.

    반환은 ``(토큰, 상한)`` 목록이고 마지막 구간의 상한은 ``None`` 이다. 구간은
    반열린 ``[하한, 상한)`` 이라 한 상품이 두 구간에 들어갈 수 없다 — 검사가 아니라
    구조로 막는다.
    """

    with open(feature_vocab_path, encoding="utf-8") as stream:
        vocab = json.load(stream)
    edges = [float(edge) for edge in vocab["price_bin_edges"]]
    tokens = next(
        block["vocab"]
        for block in vocab.get("blocks", [])
        if block.get("name") == "price_bin"
    )
    if len(tokens) != len(edges):
        raise ValueError(
            "price_bin vocab and price_bin_edges must describe the same bins: "
            f"{len(tokens)} tokens vs {len(edges)} edges"
        )
    # edges[0] 은 첫 구간의 하한(0)이라 상한 목록은 한 칸 밀린다.
    uppers: list[float | None] = [*edges[1:], None]
    return list(zip(tokens, uppers))


def _price_bin_column(price_bins: list[tuple[str, float | None]]) -> Any:
    """``base_price`` 를 구간 토큰으로 바꾼다. 가격이 없거나 0 이하면 NULL."""

    from pyspark.sql import functions as F

    price = F.col("base_price").cast("double")
    expression = None
    for token, upper in price_bins:
        condition = price < F.lit(upper) if upper is not None else F.lit(True)
        clause = F.when(condition, F.lit(token))
        expression = clause if expression is None else expression.when(
            condition, F.lit(token)
        )
    return F.when(
        price.isNull() | (price <= F.lit(0.0)), F.lit(None).cast("string")
    ).otherwise(expression)


def _brand_price_band_daily_kpi(
    product_fact_df: Any,
    dim_product_df: Any,
    price_bins: list[tuple[str, float | None]],
) -> Any:
    """브랜드 × 가격대 반응 KPI.

    ``currency`` 를 key 에 둔다. 통화가 다른 가격을 환산 규칙 없이 한 구간으로 합치지
    않는 것을 필터가 아니라 grain 으로 지킨다. 카탈로그가 전부 원화인 지금은 행 수에
    차이가 없지만, 다른 통화가 들어와도 조용히 섞이지 않는다.

    가격이 NULL 이거나 0 이하인 상품은 ``price_bin = NULL`` 행으로 보존한다. 빼면 그
    상품들의 반응을 볼 수 없고, 임의 구간에 넣으면 그 구간이 오염된다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    # 이 Mart 의 통화는 **카탈로그 기준 가격의 단위**다. product_event_fact 에도
    # 같은 이름의 컬럼이 있지만 그쪽은 결제 시점 통화라 뜻이 다르고, 이름이
    # 겹치면 Join 뒤 참조가 모호해진다. 조인 전에 이름을 갈라 둔다.
    catalog = dim_product_df.select(
        F.col("product_id").alias("_dim_product_id"),
        _price_bin_column(price_bins).alias("price_bin"),
        F.col("currency").alias("_catalog_currency"),
    )
    events = product_fact_df.where(_valid_brand()).join(
        catalog, F.col("product_id") == F.col("_dim_product_id"), "inner"
    )

    key_columns = [
        "event_date_kst", "brand_id", "price_bin", "_catalog_currency",
        *EXECUTION_AXES,
    ]

    def stage_sessions(condition: Any, alias: str) -> Any:
        return F.countDistinct(
            F.when(condition, F.col("session_id"))
        ).cast("long").alias(alias)

    is_detail = F.col("event_name").isin("product_view", "quick_look")
    result = events.groupBy(*key_columns).agg(
        F.countDistinct("session_id").cast("long").alias("session_count"),
        F.countDistinct("user_id").cast("long").alias("unique_user_count"),
        # 노출 세 Event 를 함께 센다 (§4.1). 분모가 좁으면 비율이 1 을 넘는다.
        stage_sessions(
            F.col("event_name").isin(*IMPRESSION_EVENTS), "impression_sessions"
        ),
        stage_sessions(F.col("event_name") == "quick_look", "quick_look_sessions"),
        stage_sessions(F.col("event_name") == "product_view", "product_view_sessions"),
        stage_sessions(is_detail, "detail_view_sessions"),
        stage_sessions(F.col("event_name") == "add_to_cart", "add_to_cart_sessions"),
        stage_sessions(F.col("event_name") == "purchase", "purchase_sessions"),
        F.countDistinct("product_id").cast("long").alias("product_count"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumnRenamed("_catalog_currency", "currency")
        .withColumn(
            "detail_entry_rate",
            _safe_ratio(F.col("detail_view_sessions"), F.col("impression_sessions")),
        )
        .withColumn(
            "view_to_cart_rate",
            _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")),
        )
        .withColumn(
            "view_to_purchase_rate",
            _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")),
        )
    )


# 상품 상세 안에서 읽는 콘텐츠 묶음. §4.4 의 ingredient_view_sessions ·
# review_view_sessions 가 무엇을 세는지 정하는 값이다. INFORMATION_CONTENT_KINDS 를
# 성분·리뷰로 쪼갠 것이라 둘의 합집합이 그것과 같아야 한다.
INGREDIENT_CONTENT_KINDS = ("ingredient_list", "ingredient_callout")
REVIEW_CONTENT_KINDS = ("user_review", "review_stats", "review_filter")

# E3 behaviors 블록이 대조를 요구하는 행동 (dashboard-mart-api-spec.md §6-2).
# 네 Event 는 PRODUCT_EVENT_NAMES 밖이라 product_event_fact 에 없다.
# sessionized_events 를 읽는 이유가 이것이다.
CONVERSION_BEHAVIOR_EVENTS = (
    "ingredient_view_mode_change",
    "review_filter_apply",
    "accordion_toggle",
    "text_copy",
)


def _product_view_sessions(funnel_session_df: Any, time_zone: str) -> Any:
    """상품을 조회한 세션. E3 세 Mart 가 공유하는 모집단이자 분모다.

    날짜는 ``first_product_view_at`` 의 KST 일자로 잡는다. ``funnel_date_kst`` 는
    퍼널 첫 단계(대개 노출)의 날짜라 자정을 넘긴 세션에서 콘텐츠를 읽은 날과
    어긋난다. ``_brand_daily_kpi`` 의 정보 확인 세션이 같은 방식을 쓴다.
    """

    from pyspark.sql import functions as F

    return funnel_session_df.where(
        F.col("reached_product_view") & _valid_brand()
    ).select(
        F.to_date(
            F.from_utc_timestamp(F.col("first_product_view_at"), time_zone)
        ).alias("event_date_kst"),
        "brand_id",
        "product_id",
        *EXECUTION_AXES,
        "session_id",
        F.col("reached_add_to_cart").alias("_reached_cart"),
    )


def _product_scoped_content(content_interest_df: Any) -> Any:
    """상품 상세 콘텐츠만 남긴다.

    ``product_id`` 가 NULL 인 행은 플랫폼 목록 섹션이다 (재생 데이터 기준 67%).
    어느 상품의 관심인지 알 수 없어 상품·브랜드 KPI 에 섞으면 지표를 흔든다.
    계약 §4.4 가 별도 grain 으로 미룬 대상이다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    return _observed_events(content_interest_df).where(
        F.col("product_id").isNotNull()
        & (F.length(F.trim(F.col("product_id"))) > 0)
        & _valid_brand()
    )


def _content_daily_kpi(
    content_interest_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """상품 상세 콘텐츠별 행동 집계 (dw-schema.md §4.4).

    ``dwell_ms_sum`` 은 ``content_interest_fact`` 만 원천으로 쓴다. ``section_dwell_agg``
    를 같이 합산하면 같은 체류가 두 번 들어간다 — 전자가 후자를 이미 병합한다.
    """

    from pyspark.sql import functions as F

    content = _product_scoped_content(content_interest_df)

    axes = list(EXECUTION_AXES)
    content_key = [
        "event_date_kst", "brand_id", "product_id", "section_id", "content_kind", *axes
    ]
    product_key = ["event_date_kst", "brand_id", "product_id", *axes]

    per_content = content.groupBy(*content_key).agg(
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.sum("view_count").cast("long").alias("section_view_count"),
        F.countDistinct("session_id").cast("long").alias("section_view_sessions"),
        # 합이 NULL 이 되는 경우(모든 입력이 NULL)를 0 으로 맞춘다. 체류 0 은
        # "머물지 않았다" 이지 "모른다" 가 아니라서 계약이 N 으로 선언했다.
        F.coalesce(F.sum("dwell_ms_sum"), F.lit(0)).cast("long").alias("dwell_ms_sum"),
        # 겹쳐 보인 체류를 뺀 몫. 같은 시간이 블록마다 중복 귀속된 것을
        # 걷어낸 값이라 항상 dwell_ms_sum 이하다 (§4.4).
        F.coalesce(F.sum("co_visible_le2_dwell_ms_sum"), F.lit(0))
        .cast("long").alias("co_visible_le2_dwell_ms_sum"),
        F.sum("accordion_expand_count").cast("long").alias("accordion_expand_count"),
        F.sum("text_select_count").cast("long").alias("text_selection_count"),
        F.sum("text_copy_count").cast("long").alias("text_copy_count"),
        # size(NULL) 은 설정에 따라 -1 을 낸다. 배열이 없으면 0 으로 센다.
        F.coalesce(
            F.sum(F.size(F.coalesce(
                F.col("matched_ingredients"), F.array().cast("array<string>")
            ))),
            F.lit(0),
        ).cast("long").alias("matched_ingredient_count"),
        F.sum("content_interest_score").cast("double").alias("content_interest_score"),
    )

    # 분모와 성분·리뷰 열람 세션은 **상품 단위**라 content_kind 마다 같은 값이 반복된다.
    # 행 단위로 세면 user_review 행이 ingredient_view_sessions=0 을 달고 나와
    # "아무도 성분을 안 봤다" 로 읽힌다. 소비자도 반복을 정상으로 본다
    # (docs/dashboard/dashboard-mart-api-spec.md E3).
    view_sessions = _product_view_sessions(funnel_session_df, time_zone).select(
        *product_key, "session_id"
    ).distinct()
    views = view_sessions.groupBy(*product_key).agg(
        F.countDistinct("session_id").cast("long").alias("product_view_sessions")
    )

    # 분자를 분모의 모집단으로 제한한다. Quick Look 으로 상세를 연 세션은 콘텐츠를
    # 읽고도 퍼널의 product_view 에 없어서, 제한하지 않으면 비율이 1.0 을 넘는다.
    # product_daily_kpi 의 add_to_cart_rate 가 같은 이유로 1,248행 중 323행에서
    # 1.0 을 넘었다 (Jira 277). 분자와 분모는 같은 모집단을 세야 한다.
    viewed_content = _null_safe_semi_join(
        content, view_sessions, [*product_key, "session_id"]
    )

    def kind_sessions(kinds: tuple[str, ...], alias: str) -> Any:
        return viewed_content.groupBy(*product_key).agg(
            F.countDistinct(
                F.when(F.col("content_kind").isin(*kinds), F.col("session_id"))
            ).cast("long").alias(alias)
        )

    result = _null_safe_join(per_content, views, product_key)
    result = _null_safe_join(
        result, kind_sessions(INGREDIENT_CONTENT_KINDS, "ingredient_view_sessions"),
        product_key,
    )
    result = _null_safe_join(
        result, kind_sessions(REVIEW_CONTENT_KINDS, "review_view_sessions"), product_key
    )
    return (
        # 콘텐츠를 읽었는데 퍼널에 상품 조회가 없는 조합은 분모가 0이다. 비율은
        # _safe_ratio 가 NULL 로 만들고, 건수는 계약이 N 이라 0 으로 채운다.
        result.withColumn(
            "product_view_sessions",
            F.coalesce(F.col("product_view_sessions"), F.lit(0).cast("long")),
        )
        # 성분·리뷰가 아닌 content_kind 행(cta·price·product_image …)은 조인에
        # 짝이 없어 NULL 이 된다. 계약이 N 으로 선언했고, "그 콘텐츠 종류가
        # 아니라 성분 열람이 0" 이 맞는 뜻이다 (§4.4).
        .withColumn(
            "ingredient_view_sessions",
            F.coalesce(F.col("ingredient_view_sessions"), F.lit(0).cast("long")),
        )
        .withColumn(
            "review_view_sessions",
            F.coalesce(F.col("review_view_sessions"), F.lit(0).cast("long")),
        )
        .withColumn(
            "avg_dwell_ms_per_session",
            _safe_ratio(F.col("dwell_ms_sum"), F.col("product_view_sessions")),
        )
        .withColumn(
            "ingredient_view_rate",
            _safe_ratio(
                F.col("ingredient_view_sessions"), F.col("product_view_sessions")
            ),
        )
        .withColumn(
            "review_view_rate",
            _safe_ratio(F.col("review_view_sessions"), F.col("product_view_sessions")),
        )
        .withColumn("mart_processed_at", F.current_timestamp())
    )


def _content_conversion_daily(
    content_interest_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """"그 콘텐츠를 본 세션이 담았는가" (dw-schema.md §4.19).

    세션 단위 조인이라 프론트가 Mart 두 개를 받아 만들 수 없다. 콘텐츠를 본 세션
    집합과 그 세션의 담기 도달 여부를 ``funnel_session_fact`` 에서 맞춘다.

    분모는 **그 콘텐츠를 본 세션**이다. 브랜드 담기율과 나누면 "본 사람의 담기율
    배수"(E3 cart_lift)가 되는데, 그 나눗셈은 읽는 쪽 몫이다 — 여기서 미리 나누면
    어느 브랜드 비율을 썼는지가 행에 박혀 재사용이 막힌다.
    """

    from pyspark.sql import functions as F

    content = _product_scoped_content(content_interest_df).where(
        F.col("content_kind").isNotNull()
    )

    axes = list(EXECUTION_AXES)
    key_columns = ["event_date_kst", "brand_id", "product_id", "content_kind", *axes]

    # 세션이 그 상품을 담았는지. 같은 세션·상품이면 퍼널 행은 하나다.
    cart = _product_view_sessions(funnel_session_df, time_zone).select(
        "brand_id", "product_id", "session_id", "_reached_cart"
    ).distinct()

    joined = content.select(*key_columns, "category_id", "session_id").join(
        cart, ["brand_id", "product_id", "session_id"], "left"
    )
    return joined.groupBy(*key_columns).agg(
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.countDistinct("session_id").cast("long").alias("viewed_sessions"),
        F.countDistinct(
            F.when(F.col("_reached_cart"), F.col("session_id"))
        ).cast("long").alias("viewed_cart_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    ).withColumn(
        "viewed_cart_rate",
        _safe_ratio(F.col("viewed_cart_sessions"), F.col("viewed_sessions")),
    )


def _behavior_conversion_daily(
    sessionized_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """행동을 한 세션과 안 한 세션의 담기율을 나란히 낸다 (dw-schema.md §4.20).

    모집단은 **그 상품을 조회한 세션 전체**이고 행동 여부로 둘로 가른다. 그래서
    ``done_sessions + not_done_sessions`` 가 모집단과 같다. 한쪽만 세면 "안 한 사람"
    담기율이 비어 대조가 성립하지 않는다 — 이 Mart 의 존재 이유가 그 대조다.
    """

    from pyspark.sql import functions as F

    axes = list(EXECUTION_AXES)
    product_key = ["event_date_kst", "brand_id", "product_id", *axes]
    key_columns = [*product_key, "event_name"]

    universe = _product_view_sessions(funnel_session_df, time_zone).select(
        *product_key, "session_id", "_reached_cart"
    ).distinct()

    behaviours = _observed_events(sessionized_df).where(
        F.col("event_name").isin(*CONVERSION_BEHAVIOR_EVENTS)
        & F.col("product_id").isNotNull()
        & (F.length(F.trim(F.col("product_id"))) > 0)
        & _valid_brand()
    ).select("brand_id", "product_id", "session_id", "event_name").distinct()

    # 한 건도 일어나지 않은 Event 도 행을 남긴다. 그래야 "아무도 안 했다" 와
    # "그 Event 를 집계하지 않는다" 가 구분된다. 모집단 × Event 4개라 행이 네 배가
    # 되지만 모집단 자체가 상품·일자 grain 이라 규모가 유지된다.
    events = universe.sparkSession.createDataFrame(
        [(name,) for name in CONVERSION_BEHAVIOR_EVENTS], "event_name string"
    )
    scored = (
        universe.crossJoin(F.broadcast(events))
        .join(
            behaviours.withColumn("_done", F.lit(True)),
            ["brand_id", "product_id", "session_id", "event_name"],
            "left",
        )
        .withColumn("_done", F.coalesce(F.col("_done"), F.lit(False)))
    )
    return (
        scored.groupBy(*key_columns).agg(
            F.countDistinct(
                F.when(F.col("_done"), F.col("session_id"))
            ).cast("long").alias("done_sessions"),
            F.countDistinct(
                F.when(F.col("_done") & F.col("_reached_cart"), F.col("session_id"))
            ).cast("long").alias("done_cart_sessions"),
            F.countDistinct(
                F.when(~F.col("_done"), F.col("session_id"))
            ).cast("long").alias("not_done_sessions"),
            F.countDistinct(
                F.when(~F.col("_done") & F.col("_reached_cart"), F.col("session_id"))
            ).cast("long").alias("not_done_cart_sessions"),
            F.current_timestamp().alias("mart_processed_at"),
        )
        .withColumn(
            "done_cart_rate",
            _safe_ratio(F.col("done_cart_sessions"), F.col("done_sessions")),
        )
        .withColumn(
            "not_done_cart_rate",
            _safe_ratio(F.col("not_done_cart_sessions"), F.col("not_done_sessions")),
        )
    )

# E6 "막히는 곳" 화면이 읽는 UI 마찰 Event (dashboard-mart-api-spec.md §3 E6).
#
# 재생 데이터 실측: scroll_backtrack 2,018건(시드 135) · rage_click 43건(**전부 시드**) ·
# dead_click 0건. 시드를 빼면 실질 신호는 scroll_backtrack 하나다. 그래도 세 Event 를
# 모두 목록에 두는 이유는, 0 인 것과 집계하지 않는 것이 다르기 때문이다 — 화면이
# "이 브랜드에는 dead_click 이 없다" 를 적는다 (spec §3 E6).
FRICTION_EVENTS = ("rage_click", "dead_click", "scroll_backtrack")

# 조기 이탈 판정 기준. spec §3 E6 의 quick_exit_rate 정의다.
QUICK_EXIT_MS = 3000

# 진입 경로 어휘 (event-properties-schema.md §3.3). Mart 는 이 값만 낸다 —
# 새 경로가 생기면 어휘집을 먼저 고친다.
ENTRY_SOURCES = (
    "list_grid", "promo_pick", "similar_products", "quick_look", "cart", "breadcrumb",
)

# 진입 경로를 싣는 Event. product_impression 에는 entry_source 가 없어
# (재생 데이터 100,625건 중 0건) 노출 단계는 이 축으로 가를 수 없다.
ENTRY_SOURCE_EVENTS = ("product_click", "quick_look")


def _detail_view_sessions(funnel_session_df: Any, time_zone: str) -> Any:
    """상세를 연 세션. E6 세 Mart 가 공유하는 분모다 (spec §6-6).

    상세는 ``product_view`` 와 ``quick_look`` 의 **합집합**이다. Quick Look 에서
    바로 담을 수 있어서 ``product_view`` 만 분모로 두면 분자와 모집단이 어긋나
    비율이 1.0 을 넘는다 (Jira 235·277).

    ``funnel_session_fact`` 에 ``first_detail_view_at`` 이 없으므로 두 시각 중
    이른 쪽을 쓴다. ``funnel_date_kst`` 는 퍼널 첫 단계(대개 노출)의 날짜라
    상세를 연 날과 어긋난다.
    """

    from pyspark.sql import functions as F

    # least 는 NULL 을 건너뛴다. 둘 중 하나만 있어도 그 값이 나온다.
    detail_at = F.least(
        F.col("first_product_view_at"), F.col("first_quick_look_at")
    )
    return funnel_session_df.where(
        F.col("reached_detail_view") & _valid_brand()
    ).select(
        F.to_date(F.from_utc_timestamp(detail_at, time_zone)).alias("event_date_kst"),
        "brand_id",
        "product_id",
        *EXECUTION_AXES,
        "session_id",
        F.col("reached_product_view").alias("_reached_product_view"),
        F.col("reached_add_to_cart").alias("_reached_cart"),
    )


def _friction_daily(
    sessionized_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """화면 어디에서 막히는가 (dw-schema.md §4.21).

    **상품 선호와 분리한다.** "이 상품이 별로다" 가 아니라 "이 화면이 불편하다" 를
    재는 지표다. 그래서 전환 Mart 와 grain 을 따로 두고 분모만 공유한다.

    ``event_name`` 을 grain 에 두는 롱 포맷이다. 마찰 Event 를 나중에 더해도 grain 이
    바뀌지 않고, E6 의 ``by_location`` 이 ``section_id`` + ``event_name`` 을 그대로
    읽는다. ``counts`` 는 ``event_name`` 으로 합산해 만든다.

    입력이 ``sessionized_events`` 인 이유는 세 Event 가 ``product_event_fact`` 에
    없고, ``cleaned_events`` 는 ``brand_id`` 가 비어 있기 때문이다(실측 0%).
    ``section_id``·``content_kind`` 는 ``properties_json`` 에 있다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    # 부정 시드가 scroll_backtrack·rage_click 을 내므로 여기서는 특히 크게 갈린다
    # (event-properties-schema.md §3.14).
    events = _observed_events(sessionized_df).where(
        F.col("event_name").isin(*FRICTION_EVENTS)
        & F.col("product_id").isNotNull()
        & (F.length(F.trim(F.col("product_id"))) > 0)
        & _valid_brand()
    ).select(
        "event_date_kst",
        "brand_id",
        "product_id",
        F.get_json_object("properties_json", "$.section_id").alias("section_id"),
        F.get_json_object("properties_json", "$.content_kind").alias("content_kind"),
        *EXECUTION_AXES,
        "event_name",
        "session_id",
    )

    axes = list(EXECUTION_AXES)
    product_key = ["event_date_kst", "brand_id", "product_id", *axes]
    key_columns = [
        "event_date_kst", "brand_id", "product_id", "section_id", "content_kind",
        *axes, "event_name",
    ]

    observed = events.groupBy(*key_columns).agg(
        F.count("*").cast("long").alias("event_count"),
        F.countDistinct("session_id").cast("long").alias("friction_sessions"),
    )

    # 마찰이 한 건도 없는 Event 도 행을 남긴다. dead_click 은 생성기가 만들지 않아
    # 항상 0 인데, 행이 없으면 화면이 "0 이다" 와 "안 본다" 를 구분할 수 없다.
    locations = events.select(
        *product_key, "section_id", "content_kind"
    ).distinct()
    names = locations.sparkSession.createDataFrame(
        [(name,) for name in FRICTION_EVENTS], "event_name string"
    )
    skeleton = locations.crossJoin(F.broadcast(names))

    filled = _null_safe_join(skeleton, observed, key_columns).select(
        *key_columns,
        F.coalesce(F.col("event_count"), F.lit(0).cast("long")).alias("event_count"),
        F.coalesce(F.col("friction_sessions"), F.lit(0).cast("long")).alias(
            "friction_sessions"
        ),
    )

    # 분모는 그 상품의 상세를 연 세션이다 (§6-6). 마찰은 상세 안에서 일어난다.
    denominators = _detail_view_sessions(funnel_session_df, time_zone).groupBy(
        *product_key
    ).agg(F.countDistinct("session_id").cast("long").alias("detail_view_sessions"))

    return (
        _null_safe_join(filled, denominators, product_key)
        .withColumn(
            "detail_view_sessions",
            F.coalesce(F.col("detail_view_sessions"), F.lit(0).cast("long")),
        )
        .withColumn(
            "friction_rate",
            _safe_ratio(F.col("friction_sessions"), F.col("detail_view_sessions")),
        )
        .withColumn("mart_processed_at", F.current_timestamp())
    )


def _exit_daily(
    sessionized_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """세션이 얼마나 빨리 나갔는가 (dw-schema.md §4.22).

    ``exit_summary`` 는 **세션 단위 Event** 라 ``product_id``·``brand_id`` 가 없다
    (실측 0건). 그래서 그 세션이 상세를 연 상품 **전부**에 귀속한다. 세션 하나가
    상품 셋을 봤으면 세 행에 들어간다 — **상품 축으로 합산하면 세션이 부푼다.**

    ``exit_summary.last_content_kind`` 로 이탈 지점을 가르는 방식은 쓸 수 없다.
    계약에 선언돼 있지만 재생 데이터 1,000건 중 **0건**만 값을 싣는다. 콘텐츠별
    이탈 지점은 콘텐츠 Event 의 마지막 시각으로 따로 낸다 (spec §6-3 product_exit_daily, 후속).

    세션에 ``exit_summary`` 가 여럿이면 **가장 긴** 체류로 판정한다. 어느 페이지에도
    오래 머물지 않았을 때만 조기 이탈이다 — 최솟값을 쓰면 오래 머문 세션도 짧은
    페이지 하나 때문에 조기 이탈이 된다.
    """

    from pyspark.sql import functions as F

    exits = _observed_events(sessionized_df).where(
        F.col("event_name") == F.lit("exit_summary")
    ).groupBy("session_id").agg(
        F.max(
            F.get_json_object("properties_json", "$.dwell_ms").cast("long")
        ).alias("_dwell_ms")
    ).withColumn(
        "_is_quick_exit", F.col("_dwell_ms") < F.lit(QUICK_EXIT_MS)
    )

    axes = list(EXECUTION_AXES)
    key_columns = ["event_date_kst", "brand_id", "product_id", *axes]

    sessions = _detail_view_sessions(funnel_session_df, time_zone).select(
        *key_columns, "session_id"
    ).distinct()

    joined = sessions.join(exits, ["session_id"], "left")
    return joined.groupBy(*key_columns).agg(
        F.countDistinct("session_id").cast("long").alias("detail_view_sessions"),
        F.countDistinct(
            F.when(F.col("_dwell_ms").isNotNull(), F.col("session_id"))
        ).cast("long").alias("exit_summary_sessions"),
        F.countDistinct(
            F.when(F.col("_is_quick_exit"), F.col("session_id"))
        ).cast("long").alias("quick_exit_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    ).withColumn(
        # 분모는 상세를 연 세션 전체다. exit_summary 가 없는 세션은 "빨리 나가지
        # 않았다" 가 아니라 "기록이 없다" 라서 exit_summary_sessions 를 따로 낸다 —
        # 두 값이 크게 다르면 수집 누락이다.
        "quick_exit_rate",
        _safe_ratio(F.col("quick_exit_sessions"), F.col("detail_view_sessions")),
    )


def _entry_source_daily(
    product_fact_df: Any,
    funnel_session_df: Any,
    time_zone: str,
) -> Any:
    """어느 경로로 들어온 손님이 잘 담는가 (dw-schema.md §4.23).

    grain 에 ``product_id`` 를 두지 않는다. E6 는 브랜드 단위 수치를 그리는데 상품
    단위 세션 수는 브랜드로 합산할 수 없다 — 한 세션이 같은 브랜드 상품 여럿을 보면
    상품 수만큼 부푼다 (§4.6 과 같은 이유).

    **``entry_source`` 축으로도 합산하면 안 된다.** 한 세션이 상품 A 는 목록에서,
    상품 B 는 유사 상품에서 열면 두 행에 모두 들어간다.

    노출 단계는 이 축으로 가를 수 없다. ``product_impression`` 에 ``entry_source``
    가 없다 (재생 데이터 100,625건 중 0건). 그래서 ``detail_entry_rate`` 를 내지
    않고 ``product_view_sessions`` 를 대신 싣는다 — spec §3 E6 가 요구하는 형태다.
    """

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다.
    entries = _observed_events(product_fact_df).where(
        F.col("event_name").isin(*ENTRY_SOURCE_EVENTS)
        & F.col("entry_source").isin(*ENTRY_SOURCES)
        & F.col("product_id").isNotNull()
        & _valid_brand()
    )

    # 한 세션이 같은 상품에 여러 경로로 들어올 수 있다 (실측 21,555쌍 중 249쌍).
    # **첫 진입**을 그 세션의 경로로 본다. 동률이면 event_id 사전순 — 규칙이 없으면
    # 실행마다 판정이 흔들려 재계산 결정성이 깨진다.
    order = Window.partitionBy("session_id", "product_id").orderBy(
        F.col("event_time").asc(), F.col("event_id").asc()
    )
    first_entry = (
        entries.withColumn("_rank", F.row_number().over(order))
        .where(F.col("_rank") == 1)
        .select("session_id", "product_id", "entry_source")
    )

    axes = list(EXECUTION_AXES)
    key_columns = ["event_date_kst", "brand_id", "entry_source", *axes]

    sessions = _detail_view_sessions(funnel_session_df, time_zone).join(
        first_entry, ["session_id", "product_id"], "inner"
    )

    return sessions.groupBy(*key_columns).agg(
        F.countDistinct(
            F.when(F.col("_reached_product_view"), F.col("session_id"))
        ).cast("long").alias("product_view_sessions"),
        F.countDistinct("session_id").cast("long").alias("detail_view_sessions"),
        F.countDistinct(
            F.when(F.col("_reached_cart"), F.col("session_id"))
        ).cast("long").alias("add_to_cart_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    ).withColumn(
        # 담기 분모는 상세를 연 세션이다 (§6-6). Quick Look 에서 담는 경로가 있어
        # product_view 만 분모로 두면 비율이 1.0 을 넘는다.
        "view_to_cart_rate",
        _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")),
    )


# 세션이 마지막으로 읽은 콘텐츠를 고르는 판정 재료.
# exit_summary 로는 낼 수 없다 — last_content_kind 커버리지가 0% 라서(§4.22),
# 콘텐츠 Event 의 마지막 시각으로 대신 정한다.
EXIT_CONTENT_EVENT_MIN_COLUMNS = ("event_time", "event_id")

# 퀵룩 창을 닫은 이유 중 "상세로 넘어갔다" 를 뜻하는 값
# (event-properties-schema.md §3.5).
# 뒤로가기 재조회. 새 진입이 아니라 같은 상세를 다시 연 것이라 건수 집계에서
# 뺀다 (프론트 확정 2026-09-17). 세션 dedup 지표에는 영향이 없다 — 어차피
# 같은 세션이라 countDistinct 가 한 번만 센다.
HISTORY_BACK_NAVIGATION = "history_back"

# 찜 토글에서 "추가" 를 뜻하는 action 값 (event-properties-schema §4.5).
WISHLIST_ADD_ACTION = "add"

OPEN_DETAIL_CLOSE_REASON = "open_detail"


def _seeded_session_ids(sessionized_df: Any) -> Any:
    """시드 세션 목록. ``is_seeded`` 가 없는 입력을 거르는 데 쓴다.

    ``section_dwell_agg`` 에는 ``is_seeded`` 컬럼이 없어서 ``_observed_events`` 가
    그대로 통과시킨다. 그런데 재생 데이터에 시드 세션 행이 993건 들어 있다.
    판정의 정본은 ``properties.seeded`` 이므로(§3.14) ``session_id`` 접두사가 아니라
    ``sessionized_events`` 의 플래그에서 세션 목록을 만들어 뺀다.
    """

    from pyspark.sql import functions as F

    return sessionized_df.where(
        F.coalesce(F.col("is_seeded"), F.lit(False))
    ).select("session_id").distinct()


def _product_exit_daily(sessionized_df: Any) -> Any:
    """상품마다 어느 콘텐츠에서 손님이 떠났는가 (dw-schema.md §4.24).

    ``exit_daily``(§4.22)와 다른 Mart 다. 그쪽은 "얼마나 빨리 나갔나"(체류 3초
    미만)를 재고 이쪽은 "어디에서 멈췄나"를 잰다. 합칠 수 없는 이유는 원천이
    다르기 때문이다 — ``exit_summary.last_content_kind`` 는 값이 실리지 않아
    (실측 0/1,000) 여기서는 콘텐츠 Event 의 마지막 시각으로 판정한다.

    같은 시각이면 ``event_id`` 사전순으로 고정한다. 규칙이 없으면 실행마다 판정이
    흔들려 재계산 결정성이 깨진다.
    """

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    content = _observed_events(sessionized_df).select(
        "event_date_kst",
        "brand_id",
        "product_id",
        *EXECUTION_AXES,
        "session_id",
        "event_time",
        "event_id",
        F.get_json_object("properties_json", "$.content_kind").alias(
            "last_content_kind"
        ),
    ).where(
        F.col("last_content_kind").isNotNull()
        & (F.length(F.trim(F.col("last_content_kind"))) > 0)
        & F.col("product_id").isNotNull()
        & (F.length(F.trim(F.col("product_id"))) > 0)
        & _valid_brand()
    )

    # 세션·상품마다 마지막 한 건만 남긴다. 그래서 세션당 이탈 지점이 하나다.
    order = Window.partitionBy("session_id", "product_id").orderBy(
        F.col("event_time").desc(), F.col("event_id").asc()
    )
    last = content.withColumn("_rank", F.row_number().over(order)).where(
        F.col("_rank") == 1
    )

    key_columns = [
        "event_date_kst", "brand_id", "product_id", "last_content_kind",
        *EXECUTION_AXES,
    ]
    return last.groupBy(*key_columns).agg(
        F.countDistinct("session_id").cast("long").alias("exit_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    )


def _segment_content_daily(
    section_dwell_df: Any,
    sessionized_df: Any,
    bridge_df: Any,
) -> Any:
    """피부 타입별로 어떤 콘텐츠를 오래 보는가 (dw-schema.md §4.25).

    ``dwell_share`` 의 분모는 **그 피부 타입의 같은 브랜드·일자 체류 총합**이다.
    그래서 한 타입 안에서 share 를 더하면 1 이 된다. 타입끼리 더하면 안 된다 —
    타입마다 모집단이 다르다.

    ``persona_id`` 가 없는 세션은 어느 세그먼트에도 넣지 않는다. 임의 귀속은
    없는 고객군을 만들어 내는 일이라, 빼는 쪽이 정직하다 (Jira 277 과 같은 규칙).
    """

    from pyspark.sql import functions as F

    skin_types = bridge_df.where(
        (F.col("segment_type") == F.lit("skin_type"))
        & F.col("segment_value").isNotNull()
        & (F.length(F.trim(F.col("segment_value"))) > 0)
        & ~F.col("segment_value").isin(*MISSING_SEGMENT_VALUES)
    ).select(
        "persona_id", F.col("segment_value").alias("skin_type")
    ).distinct()

    # section_dwell_agg 에는 is_seeded 가 없다. 세션 목록으로 빼야 한다.
    seeded = _seeded_session_ids(sessionized_df)

    dwell = section_dwell_df.where(
        F.col("persona_id").isNotNull()
        & (F.length(F.trim(F.col("persona_id"))) > 0)
        & F.col("content_kind").isNotNull()
        & (F.length(F.trim(F.col("content_kind"))) > 0)
        & _valid_brand()
    ).join(seeded, ["session_id"], "left_anti").join(
        # persona 가 bridge 에 없으면 세그먼트를 모르는 것이라 뺀다.
        skin_types, ["persona_id"], "inner"
    )

    axes = list(EXECUTION_AXES)
    key_columns = ["event_date_kst", "brand_id", "skin_type", "content_kind", *axes]
    segment_key = ["event_date_kst", "brand_id", "skin_type", *axes]

    per_content = dwell.groupBy(*key_columns).agg(
        F.sum("dwell_ms_sum").cast("long").alias("dwell_ms_sum"),
        F.countDistinct("session_id").cast("long").alias("dwell_sessions"),
    )
    totals = per_content.groupBy(*segment_key).agg(
        F.sum("dwell_ms_sum").cast("long").alias("segment_dwell_ms_sum")
    )
    return (
        _null_safe_join(per_content, totals, segment_key)
        .withColumn(
            "dwell_share",
            _safe_ratio(F.col("dwell_ms_sum"), F.col("segment_dwell_ms_sum")),
        )
        .withColumn("mart_processed_at", F.current_timestamp())
    )



# S5 히트맵 축. 교차 축(skin_type_x_skin_tone)은 넣지 않는다 — 여기에 또 얹으면
# 셀이 100개가 되어 표본이 무너진다. S5 정의가 5밴드 × 4타입 = 20셀이다
# (docs/dashboard/dashboard-redesign-spec.md §2-3).
S5_SEGMENT_TYPES = ("skin_type", "skin_tone")


def _segment_price_band_daily_kpi(
    product_fact_df: Any,
    dim_product_df: Any,
    bridge_df: Any,
    price_bins: list[tuple[str, float | None]],
) -> Any:
    """고객군 × 가격 밴드 교차 KPI (dw-schema.md §4.26).

    ``persona_segment_daily_kpi``(§4.6)와 ``brand_price_band_daily_kpi``(§4.6-1)의
    축을 교차한다. **둘 중 어느 쪽에도 축을 얹을 수 없어서** 별도 Mart 로 나눴다 —
    축을 더하면 그 축을 걷어낸 합계가 같은 세션을 여러 번 센다. 세션 하나가 여러
    가격대의 상품을 밟고, 동시에 ``skin_type`` 행과 ``skin_tone`` 행에 들어간다.

    같은 함정이 Jira 235 에서 실제로 났다 — 브랜드 세션을 상품 Mart 합산으로 구했다가
    876행이 336행으로 정정됐다.

    **세 Mart 를 서로 대체하지 않는다.** ``price_bin`` 을 걷어낸 합계는 §4.6 과 같지
    않고, ``segment_*`` 를 걷어낸 합계는 §4.6-1 과 같지 않다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    # 교차 축은 쓰지 않는다. _persona_segments 는 교차 축까지 내므로 여기서 거른다.
    segments = _persona_segments(bridge_df).where(
        F.col("segment_type").isin(*S5_SEGMENT_TYPES)
    )

    # 이 Mart 의 통화는 **카탈로그 기준 가격의 단위**다. product_event_fact 에도 같은
    # 이름의 컬럼이 있지만 그쪽은 결제 시점 통화라 뜻이 다르다. 이름이 겹치면 Join 뒤
    # 참조가 모호해져 실행에서만 터진다 (Jira 277 에서 AMBIGUOUS_REFERENCE 로 겪었다).
    catalog = dim_product_df.select(
        F.col("product_id").alias("_dim_product_id"),
        _price_bin_column(price_bins).alias("price_bin"),
        F.col("currency").alias("_catalog_currency"),
    )

    events = (
        product_fact_df.where(
            _valid_brand()
            # persona_id 가 없는 세션은 어느 세그먼트에도 넣지 않는다. 실제 사용자의
            # 피부 정보는 Event 경로에 없어서, 귀속하면 없는 사실을 만들어 낸다.
            & F.col("persona_id").isNotNull()
            & (F.length(F.trim(F.col("persona_id"))) > 0)
        )
        .join(segments, ["persona_id"], "inner")
        .join(catalog, F.col("product_id") == F.col("_dim_product_id"), "inner")
    )

    key_columns = [
        "event_date_kst", "brand_id", "segment_type", "segment_value",
        "price_bin", "_catalog_currency", *EXECUTION_AXES,
    ]

    def stage_sessions(condition: Any, alias: str) -> Any:
        return F.countDistinct(
            F.when(condition, F.col("session_id"))
        ).cast("long").alias(alias)

    is_detail = F.col("event_name").isin("product_view", "quick_look")
    result = events.groupBy(*key_columns).agg(
        F.countDistinct("user_id").cast("long").alias("segment_user_count"),
        F.countDistinct("session_id").cast("long").alias("session_count"),
        stage_sessions(F.col("event_name") == "product_view", "product_view_sessions"),
        stage_sessions(is_detail, "detail_view_sessions"),
        stage_sessions(F.col("event_name") == "add_to_cart", "add_to_cart_sessions"),
        stage_sessions(F.col("event_name") == "purchase", "purchase_sessions"),
        F.countDistinct("product_id").cast("long").alias("product_count"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumnRenamed("_catalog_currency", "currency")
        # 담기 분모는 상세를 연 세션이다 (§4.1·§4.6·§4.6-1 과 같은 규칙).
        # Quick Look 에서 담는 경로가 있어 product_view 만 분모로 두면 1.0 을 넘는다.
        .withColumn(
            "view_to_cart_rate",
            _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")),
        )
        .withColumn(
            "view_to_purchase_rate",
            _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")),
        )
    )



def _event_daily(cleaned_df: Any, dim_product_df: Any) -> Any:
    """브랜드별 Event 볼륨 (dw-schema.md §4.27).

    E6 의 ``event_volumes`` 블록이 읽는다. "어제 로그가 정상적으로 들어왔나" 를 보는
    진단 지표라, 다른 Mart 와 달리 **Event 를 고르지 않고 전부 센다.**

    ``brand_id`` 는 ``dim_product`` 에서 보강한다. ``cleaned_events`` 에는 상품 차원이
    붙기 전이라 브랜드가 없다.

    **상품에 귀속되지 않는 Event 도 남긴다.** ``exit_summary``·``page_view``·
    ``session_start`` 같은 플랫폼 공통 Event 는 ``brand_id`` 가 NULL 이고, 지우면
    "어제 로그가 정상인가" 를 볼 수 없다. 화면이 브랜드로 거르면 자연히 빠지므로
    Mart 가 미리 지울 이유가 없다. Q5 가 ``event_count`` 합을 ``cleaned_events`` 의
    관측 Event 수와 대조하는데, 지우면 그 검사가 성립하지 않는다.

    §5.1 ``realtime_event_stats`` 를 쓰지 않은 이유는 그 key 에 ``brand_id`` 가 없어
    E6 의 "브랜드 필터 가능" 요구를 못 맞추기 때문이다. 그쪽은 운영 모니터링용
    정의라 목적이 다르다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    # 볼륨 진단이라 관측 Event 만 센다 — 시드는 생성기가 주입한 표식이다.
    events = _observed_events(cleaned_df)

    # 상품에 안 붙는 Event 도 남겨야 하므로 left join 이다. inner 로 하면 플랫폼
    # 공통 Event 가 통째로 사라진다.
    catalog = dim_product_df.select(
        F.col("product_id").alias("_dim_product_id"),
        F.col("brand_id").alias("_brand_id"),
    ).distinct()
    joined = events.join(
        catalog, F.col("product_id") == F.col("_dim_product_id"), "left"
    )

    key_columns = ["event_date_kst", "brand_id", "event_name", *EXECUTION_AXES]
    return joined.select(
        "event_date_kst",
        F.col("_brand_id").alias("brand_id"),
        "event_name",
        *EXECUTION_AXES,
        "session_id",
        "user_id",
    ).groupBy(*key_columns).agg(
        F.count("*").cast("long").alias("event_count"),
        F.countDistinct("session_id").cast("long").alias("unique_session_count"),
        F.countDistinct("user_id").cast("long").alias("unique_user_count"),
        F.current_timestamp().alias("mart_processed_at"),
    )


PAYMENT_METHODS = ("kakaopay", "card", "test")
ORDER_CHANNELS = ("backend", "local")


def _order_payment_aggs(F: Any) -> list[Any]:
    """주문 단위 결제 속성을 주문 fold 단계에서 한 번만 집는다.

    ``paid_value`` · ``payment_method`` · ``order_channel`` 은 한 주문의 상품 row 마다
    같은 값이 반복된다 (``derive_facts_job._purchase_fact``). 상품 row 를 그대로 더하면
    상품 수만큼 부풀어 오르므로 ``order_id`` 로 접을 때 ``max`` 로 대표값 하나만 남긴다.
    """

    return [
        F.max("paid_value").alias("paid_value"),
        F.max("payment_method").alias("payment_method"),
        F.max("order_channel").alias("order_channel"),
    ]


def _payment_split(orders_df: Any, key_columns: list[str]) -> Any:
    """key 단위 결제수단·주문경로 분포. 행을 버리지 않고 축으로만 가른다.

    ``order_channel='local'`` 은 브라우저에서만 만든 시연 주문이라 Backend 주문과
    대사할 수 없다 (``event-properties-schema.md`` §3.16). 여기서 걸러내지 않는 이유는
    무엇이 시연이었는지가 Mart 를 읽는 쪽에서 보여야 하기 때문이다. 조용히 빼면
    재구매율이 왜 달라졌는지 되짚을 근거가 사라진다.

    ``paid_value`` 합은 ``backend`` 주문만 센다. 시연 주문의 금액을 섞으면 실결제액
    축이 시연 횟수에 따라 흔들린다.
    """

    from pyspark.sql import functions as F

    def _count(column: str, value: str) -> Any:
        return F.countDistinct(
            F.when(F.col(column) == F.lit(value), F.col("order_id"))
        ).cast("long")

    aggregations = [
        _count("order_channel", channel).alias(f"{channel}_order_count")
        for channel in ORDER_CHANNELS
    ] + [
        _count("payment_method", method).alias(f"{method}_order_count")
        for method in PAYMENT_METHODS
    ]
    return orders_df.groupBy(*key_columns).agg(
        *aggregations,
        F.sum(
            F.when(F.col("order_channel") == F.lit("backend"), F.col("paid_value"))
        )
        .cast("decimal(18,2)")
        .alias("backend_paid_value"),
    )


def _repurchase_orders(purchase_fact_df: Any, window_days: int, key_columns: list[str]) -> Any:
    """관측 창 안의 구매를 주문 단위로 접는다.

    한 주문에 같은 상품 row가 여러 개 있어도 구매는 한 번이다. `order_id`로 먼저
    접지 않으면 같은 주문이 재구매로 잡힌다.
    """

    from pyspark.sql import functions as F

    valid = purchase_fact_df.where(
        _valid_brand()
        & F.col("user_id").isNotNull()
        & (F.length(F.trim(F.col("user_id"))) > 0)
        & F.col("order_id").isNotNull()
        & (F.length(F.trim(F.col("order_id"))) > 0)
    )
    snapshot = valid.agg(F.max("event_date_kst").alias("snapshot")).first()["snapshot"]
    if snapshot is None:
        # 구매가 없는 스냅샷도 스키마는 유지한다.
        empty = valid.withColumn("snapshot_date_kst", F.col("event_date_kst"))
        return empty.groupBy(*key_columns, "user_id", "order_id").agg(
            F.min("event_time").alias("purchased_at"),
            *_order_payment_aggs(F),
        )
    windowed = valid.where(
        F.col("event_date_kst")
        > F.date_sub(F.lit(snapshot).cast("date"), int(window_days))
    ).withColumn("snapshot_date_kst", F.lit(snapshot).cast("date"))
    return windowed.groupBy(*key_columns, "user_id", "order_id").agg(
        F.min("event_time").alias("purchased_at"),
        *_order_payment_aggs(F),
    )


def _repurchase_metrics(orders_df: Any, key_columns: list[str], window_days: int) -> Any:
    """구매자별 주문 수와 평균 간격을 낸 뒤 key 단위로 요약한다."""

    from pyspark.sql import functions as F

    per_buyer = orders_df.groupBy(*key_columns, "user_id").agg(
        F.countDistinct("order_id").cast("long").alias("buyer_order_count"),
        F.min("purchased_at").alias("first_purchased_at"),
        F.max("purchased_at").alias("last_purchased_at"),
    )
    # 재구매 간격은 첫 구매와 마지막 구매의 간격을 구매 횟수로 나눈 평균이다.
    # 1회 구매자는 간격이 없으므로 NULL로 두어 중앙값을 끌어내리지 않는다.
    per_buyer = per_buyer.withColumn(
        "days_between_purchases",
        F.when(
            F.col("buyer_order_count") > 1,
            (
                F.col("last_purchased_at").cast("double")
                - F.col("first_purchased_at").cast("double")
            )
            / F.lit(86400.0)
            / (F.col("buyer_order_count") - F.lit(1)).cast("double"),
        ),
    )
    result = per_buyer.groupBy(*key_columns).agg(
        F.countDistinct("user_id").cast("long").alias("buyer_count"),
        F.countDistinct(
            F.when(F.col("buyer_order_count") > 1, F.col("user_id"))
        ).cast("long").alias("repeat_buyer_count"),
        F.sum("buyer_order_count").cast("long").alias("purchase_order_count"),
        F.expr("percentile_approx(days_between_purchases, 0.5)")
        .cast("double")
        .alias("median_days_between_purchases"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    summary = (
        result.withColumn(
            "repurchase_rate",
            _safe_ratio(F.col("repeat_buyer_count"), F.col("buyer_count")),
        )
        .withColumn("window_days", F.lit(int(window_days)).cast("int"))
        .withColumn(
            "window_start_date",
            F.date_sub(F.col("snapshot_date_kst"), int(window_days) - 1),
        )
        .withColumn("window_end_date", F.col("snapshot_date_kst"))
    )
    # 결제수단·주문경로 분포는 주문 단위라 구매자 단위 집계와 grain 이 다르다.
    # 같은 groupBy 에 섞으면 한 주문의 상품 row 수만큼 중복되므로 따로 세어 붙인다.
    return _null_safe_join(summary, _payment_split(orders_df, key_columns), key_columns)


def _product_repurchase_daily(purchase_fact_df: Any, window_days: int) -> Any:
    """상품 재구매 — 같은 사용자가 같은 상품을 서로 다른 주문으로 다시 산 비율."""

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    purchase_fact_df = _observed_events(purchase_fact_df)

    key_columns = ["snapshot_date_kst", "brand_id", "product_id", *EXECUTION_AXES]
    orders = _repurchase_orders(purchase_fact_df, window_days, key_columns)
    return _repurchase_metrics(orders, key_columns, window_days)


def _brand_repurchase_daily(
    purchase_fact_df: Any, purchase_reason_fact_df: Any, window_days: int
) -> Any:
    """브랜드 재구매 — 상품이 달라도 같은 브랜드를 다시 산 비율.

    상품 Mart를 합산해서 구할 수 없다. 한 사용자가 같은 브랜드의 다른 상품 두 개를
    사면 상품 단위로는 1회 구매가 둘이지만 브랜드 단위로는 재구매다.

    `restock`은 재구매의 선언 신호이므로(`event-properties-schema.md` §3.9) 관측
    재구매와 교차 검증할 수 있도록 같은 행에 보존한다.
    """

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    purchase_fact_df = _observed_events(purchase_fact_df)
    purchase_reason_fact_df = _observed_events(purchase_reason_fact_df)

    from pyspark.sql import functions as F

    key_columns = ["snapshot_date_kst", "brand_id", *EXECUTION_AXES]
    orders = _repurchase_orders(purchase_fact_df, window_days, key_columns)
    metrics = _repurchase_metrics(orders, key_columns, window_days)

    restock_orders = (
        purchase_reason_fact_df.where(F.col("reason") == F.lit("restock"))
        .select("order_id")
        .distinct()
    )
    declared = (
        orders.select(*key_columns, "order_id")
        .distinct()
        .join(restock_orders, ["order_id"], "left_semi")
        .groupBy(*key_columns)
        .agg(
            F.countDistinct("order_id")
            .cast("long")
            .alias("declared_restock_order_count")
        )
    )
    return _null_safe_join(metrics, declared, key_columns).withColumn(
        "declared_restock_order_count",
        F.coalesce(F.col("declared_restock_order_count"), F.lit(0)).cast("long"),
    )


def _reason_trait_column(reason_trait_map: dict[str, Any]) -> Any:
    """선언 이유를 관측 성향 축으로 옮긴다. 매핑이 없는 이유는 NULL로 남긴다."""

    from pyspark.sql import functions as F

    mapped = F.lit(None).cast("string")
    for reason, trait in sorted(reason_trait_map.items()):
        if trait:
            mapped = F.when(
                F.col("reason") == F.lit(reason), F.lit(trait)
            ).otherwise(mapped)
    return mapped


def _purchase_reason_daily(
    purchase_reason_fact_df: Any,
    purchase_fact_df: Any,
    user_trait_daily_df: Any | None,
    reason_trait_map: dict[str, Any],
) -> Any:
    """구매 이유 분포와 행동 추론 대조.

    `purchase_reason_fact`의 grain은 `order_id + reason`이라 브랜드 축이 없다.
    이유는 주문 단위 선언이므로 다브랜드 주문에서 어느 브랜드 때문인지 알 수 없다.
    그래서 한 주문을 그 주문에 든 각 브랜드에 한 번씩만 계상한다. 집계를
    `countDistinct(order_id)`로 하는 이유도 상품 수만큼 부풀지 않게 하기 위해서다.
    """

    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    purchase_reason_fact_df = _observed_events(purchase_reason_fact_df)
    purchase_fact_df = _observed_events(purchase_fact_df)

    key_columns = ["event_date_kst", "brand_id", "reason", *EXECUTION_AXES]
    order_brands = (
        purchase_fact_df.where(_valid_brand() & F.col("order_id").isNotNull())
        .select("order_id", "brand_id")
        .distinct()
    )
    reasons = purchase_reason_fact_df.select(
        "order_id",
        "reason",
        "event_date_kst",
        "user_id",
        "is_primary",
        "skipped",
        *EXECUTION_AXES,
    ).where(F.col("order_id").isNotNull())
    attributed = reasons.join(order_brands, ["order_id"], "inner").withColumn(
        "_mapped_trait", _reason_trait_column(reason_trait_map)
    )

    if user_trait_daily_df is None:
        attributed = attributed.withColumn(
            "_primary_trait", F.lit(None).cast("string")
        )
    else:
        primary_traits = (
            user_trait_daily_df.where(F.col("is_primary_trait"))
            .select(
                F.col("trait_date_kst").alias("_trait_date"),
                F.col("user_id").alias("_trait_user_id"),
                F.col("trait").alias("_primary_trait"),
            )
            .distinct()
        )
        attributed = attributed.join(
            primary_traits,
            (F.col("event_date_kst") == F.col("_trait_date"))
            & (F.col("user_id") == F.col("_trait_user_id")),
            "left",
        ).drop("_trait_date", "_trait_user_id")

    compared = F.col("_mapped_trait").isNotNull() & F.col("_primary_trait").isNotNull()
    result = attributed.groupBy(*key_columns).agg(
        F.countDistinct("order_id").cast("long").alias("order_count"),
        F.countDistinct(F.when(F.col("is_primary"), F.col("order_id")))
        .cast("long")
        .alias("primary_order_count"),
        F.countDistinct(F.when(F.col("skipped"), F.col("order_id")))
        .cast("long")
        .alias("skipped_order_count"),
        F.countDistinct(F.when(compared, F.col("order_id")))
        .cast("long")
        .alias("trait_compared_order_count"),
        F.countDistinct(
            F.when(compared & (F.col("_mapped_trait") == F.col("_primary_trait")), F.col("order_id"))
        ).cast("long").alias("trait_matched_order_count"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    brand_day = ["event_date_kst", "brand_id", *EXECUTION_AXES]
    answered_totals = (
        attributed.where(F.col("reason").isNotNull())
        .groupBy(*brand_day)
        .agg(
            F.countDistinct("order_id")
            .cast("long")
            .alias("answered_order_count")
        )
    )
    return (
        _null_safe_join(result, answered_totals, brand_day)
        .withColumn(
            "reason_share",
            F.when(
                F.col("reason").isNotNull(),
                _safe_ratio(F.col("order_count"), F.col("answered_order_count")),
            ),
        )
        .withColumn(
            "trait_match_rate",
            _safe_ratio(
                F.col("trait_matched_order_count"),
                F.col("trait_compared_order_count"),
            ),
        )
        .drop("answered_order_count")
    )


def _event_weight_column(event_weights: dict[str, float]) -> Any:
    from pyspark.sql import functions as F

    result = F.lit(0.0)
    for event_name, weight in event_weights.items():
        result = F.when(
            F.col("event_name") == F.lit(event_name), F.lit(float(weight))
        ).otherwise(result)
    return result


def _ingredient_weekly_interest(
    sessionized_df: Any,
    dim_product_df: Any,
    product_ingredient_df: Any,
    ingredient_vocab_df: Any,
    time_zone: str,
    event_weights: dict[str, float],
    cleansing_category_weight: float,
) -> Any:
    """Build ingredient interest without reading an AI vector slice.

    Direct text matches are attributed only to the named ingredient. Product-wide
    signals are expanded through ``product_ingredient.position_weight``. Events
    for products without a bridge row are deliberately absent from both the
    ingredient numerator and its share denominator; they are not zero-filled.
    """

    from pyspark.sql import functions as F
    from pyspark.sql.types import ArrayType, StringType
    from pyspark.sql.window import Window

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    sessionized_df = _observed_events(sessionized_df)

    dimensions = [
        "interest_week_kst",
        *EXECUTION_AXES,
    ]
    events = (
        sessionized_df.withColumn(
            "interest_week_kst",
            F.to_date(
                F.date_trunc("week", F.from_utc_timestamp("event_time", time_zone))
            ),
        )
        .withColumn("_section_id", F.get_json_object("properties_json", "$.section_id"))
        .withColumn("_action", F.get_json_object("properties_json", "$.action"))
        .withColumn(
            "_dwell_ms",
            F.get_json_object("properties_json", "$.dwell_ms").cast("long"),
        )
        .withColumn(
            "_matched_ingredients",
            F.from_json(
                F.get_json_object("properties_json", "$.matched_ingredients"),
                ArrayType(StringType()),
            ),
        )
    )
    weight = _event_weight_column(event_weights)

    direct = (
        events.where(F.col("event_name").isin(*DIRECT_INGREDIENT_EVENTS))
        .where(F.size(F.col("_matched_ingredients")) > 0)
        .withColumn(
            "ingredient", F.explode(F.array_distinct("_matched_ingredients"))
        )
        .join(
            ingredient_vocab_df.select(
                "ingredient_id", "ingredient", "label_ko", "vocab_version"
            ),
            "ingredient",
            "inner",
        )
        .select(
            *dimensions,
            "event_id",
            "ingredient_id",
            "ingredient",
            "label_ko",
            "vocab_version",
            weight.alias("ingredient_interest_score"),
            weight.alias("direct_match_score"),
            F.lit(0.0).alias("product_attributed_score"),
        )
    )

    product_signal_condition = (
        (F.col("event_name") == F.lit("ingredient_view_mode_change"))
        | (F.col("event_name") == F.lit("add_to_cart"))
        | (
            (F.col("event_name") == F.lit("accordion_toggle"))
            & (F.col("_section_id") == F.lit("ingredients"))
            & (F.col("_action") == F.lit("expand"))
        )
        | (
            (F.col("event_name") == F.lit("section_dwell"))
            & (F.col("_section_id") == F.lit("ingredients"))
        )
    )
    product_events = events.where(product_signal_condition).where(
        F.col("product_id").isNotNull()
    )
    base_score = F.when(
        F.col("event_name") == F.lit("section_dwell"),
        F.least(
            F.coalesce(F.col("_dwell_ms"), F.lit(0)).cast("double") / F.lit(1000.0),
            F.lit(60.0),
        )
        * weight,
    ).otherwise(weight)
    product = (
        product_events.join(
            dim_product_df.select("product_id", "secondary_category"),
            "product_id",
            "left",
        )
        # Inner join is intentional. A product with no ingredient row has no
        # defensible ingredient attribution and does not enter the denominator.
        .join(
            product_ingredient_df.select(
                "product_id",
                "ingredient_id",
                "ingredient",
                "position_weight",
                F.col("source").alias("ingredient_source"),
                "vocab_version",
            ),
            "product_id",
            "inner",
        )
        .join(
            ingredient_vocab_df.select(
                "ingredient_id", "ingredient", "label_ko", "vocab_version"
            ),
            ["ingredient_id", "ingredient", "vocab_version"],
            "inner",
        )
        .withColumn(
            "_category_weight",
            F.when(
                F.col("secondary_category") == F.lit("Cleansers"),
                F.lit(float(cleansing_category_weight)),
            ).otherwise(F.lit(1.0)),
        )
        .withColumn(
            "_score",
            base_score
            * F.col("position_weight").cast("double")
            * F.col("_category_weight"),
        )
        .select(
            *dimensions,
            "event_id",
            "ingredient_id",
            "ingredient",
            "label_ko",
            "vocab_version",
            F.col("_score").alias("ingredient_interest_score"),
            F.lit(0.0).alias("direct_match_score"),
            F.col("_score").alias("product_attributed_score"),
        )
    )

    signals = direct.unionByName(product)
    grouped = signals.groupBy(
        *dimensions, "ingredient_id", "ingredient", "label_ko", "vocab_version"
    ).agg(
        F.sum("ingredient_interest_score").cast("double").alias(
            "ingredient_interest_score"
        ),
        F.sum("direct_match_score").cast("double").alias("direct_match_score"),
        F.sum("product_attributed_score").cast("double").alias(
            "product_attributed_score"
        ),
        F.countDistinct("event_id").cast("long").alias("contributing_event_count"),
    )
    share_window = Window.partitionBy(*dimensions)
    denominator = F.sum("ingredient_interest_score").over(share_window)
    return (
        grouped.withColumn(
            "ingredient_interest_share",
            _safe_ratio(F.col("ingredient_interest_score"), denominator),
        )
        .withColumn("mart_processed_at", F.current_timestamp())
    )


def _category_price_reference(dim_product_df: Any, min_sample_size: int) -> Any:
    """Build a currency-safe secondary-category price median.

    Only ``base_price`` participates. Sale/discount fields are intentionally not
    accepted by this function. Thin categories fall back to the catalog-wide
    median in the same currency.
    """

    from pyspark.sql import functions as F

    valid = dim_product_df.where(
        F.col("secondary_category").isNotNull()
        & F.col("currency").isNotNull()
        & F.col("base_price").isNotNull()
        & (F.col("base_price") > 0)
    )
    by_category = valid.groupBy("secondary_category", "currency").agg(
        F.countDistinct("product_id").cast("long").alias("product_count"),
        F.expr("percentile(CAST(base_price AS DOUBLE), 0.5)")
        .cast("decimal(18,2)")
        .alias("observed_median_price"),
    )
    global_by_currency = valid.groupBy("currency").agg(
        F.countDistinct("product_id").cast("long").alias("global_product_count"),
        F.expr("percentile(CAST(base_price AS DOUBLE), 0.5)")
        .cast("decimal(18,2)")
        .alias("global_median_price"),
    )
    sufficient = F.col("product_count") >= F.lit(int(min_sample_size))
    return (
        by_category.join(global_by_currency, "currency", "inner")
        .withColumn("is_sample_sufficient", sufficient)
        .withColumn(
            "reference_median_price",
            F.when(sufficient, F.col("observed_median_price")).otherwise(
                F.col("global_median_price")
            ),
        )
        .withColumn(
            "reference_source",
            F.when(sufficient, F.lit("category")).otherwise(
                F.lit("global_fallback")
            ),
        )
        .withColumn("min_sample_size", F.lit(int(min_sample_size)).cast("int"))
        .withColumn("mart_processed_at", F.current_timestamp())
    )


# 코호트 축. 상품 수 밴드 경계는 재생 데이터 실측으로 잡았다 (dw-schema.md §3.7).
# 기획 문서의 1-15 / 16-50 / 51+ 는 이 카탈로그에서 브랜드 56개 중 55개를 한 칸에
# 몰아넣어 축이 상수가 된다 — 최대 상품 수가 16개다.
PRODUCT_COUNT_BANDS = ((1, "1"), (3, "2-3"), (10, "4-10"), (None, "11+"))


def _product_count_band_column(count_column: Any) -> Any:
    """상품 수를 밴드 토큰으로 바꾼다."""

    from pyspark.sql import functions as F

    expression = None
    for upper, token in PRODUCT_COUNT_BANDS:
        condition = count_column <= F.lit(upper) if upper is not None else F.lit(True)
        expression = (
            F.when(condition, F.lit(token)) if expression is None
            else expression.when(condition, F.lit(token))
        )
    return expression


def _dominant_value(frame: Any, key: str, value: str, alias: str) -> Any:
    """``key`` 마다 가장 많이 나온 ``value``. 동률이면 사전순으로 낮은 쪽.

    동률에서 규칙이 없으면 실행마다 판정이 흔들려 재계산 결정성이 깨진다.
    """

    from pyspark.sql import functions as F

    counted = (
        frame.where(F.col(value).isNotNull())
        .groupBy(key, value)
        .agg(F.count("*").alias("_n"))
    )
    # struct 정렬로 (빈도 내림차순, 값 오름차순) 최댓값을 한 번에 고른다.
    return counted.groupBy(key).agg(
        F.min(F.struct((-F.col("_n")).alias("_rank"), F.col(value).alias("_value")))
        .getField("_value")
        .alias(alias)
    )


def _brand_cohort_dim(
    dim_product_df: Any,
    dim_brand_df: Any,
    price_bins: list[tuple[str, float | None]],
) -> Any:
    """브랜드를 "비슷한 처지" 끼리 묶는다 (dw-schema.md §3.7).

    상품 16개짜리 브랜드와 1개짜리 브랜드를 같은 잣대로 재면 비교가 의미를 잃는다.
    규모(상품 수 밴드) × 가격 구간 두 축으로 묶고 그 안에서만 분위를 낸다.

    카테고리를 축에 넣지 않는다. 3축이면 R1(브랜드 5 미만 억제)에서 56개 중 21개만
    살아남아, 억제 규칙이 이 기능의 대상인 소규모 브랜드를 정확히 지운다.

    ``brand_hash`` 는 ``dim_brand`` 에서 Join 으로 가져온다. 같은 값을 두 곳에서
    계산하면 조용히 갈라진다.
    """

    from pyspark.sql import functions as F

    products = dim_product_df.select(
        F.trim(F.col("brand_id").cast("string")).alias("brand_id"),
        "product_id",
        "secondary_category",
        _price_bin_column(price_bins).alias("price_bin"),
    ).where(_valid_brand())

    counts = products.groupBy("brand_id").agg(
        F.countDistinct("product_id").cast("long").alias("product_count")
    )
    price = _dominant_value(products, "brand_id", "price_bin", "dominant_price_bin")
    category = _dominant_value(
        products, "brand_id", "secondary_category", "dominant_secondary_category"
    )

    cohort = (
        counts.join(price, ["brand_id"], "left")
        .join(category, ["brand_id"], "left")
        .withColumn(
            "product_count_band", _product_count_band_column(F.col("product_count"))
        )
        # 가격을 모르는 브랜드는 코호트에 넣지 않는다. 임의 구간에 넣으면 그 코호트의
        # 분위가 오염되고, 빼면 그 브랜드가 벤치마크를 못 본다 — 후자가 정직하다.
        .withColumn(
            "cohort_key",
            F.when(
                F.col("dominant_price_bin").isNotNull(),
                F.concat_ws(
                    "|", F.col("product_count_band"), F.col("dominant_price_bin")
                ),
            ),
        )
    )
    brands = dim_brand_df.select(
        "brand_id", "brand_hash", "commons_participating"
    )
    return cohort.join(brands, ["brand_id"], "inner").select(
        "brand_id",
        "brand_hash",
        "product_count",
        "product_count_band",
        "dominant_price_bin",
        "dominant_secondary_category",
        "cohort_key",
        "commons_participating",
        F.current_timestamp().alias("mart_processed_at"),
    )


# 공유 규칙 임계값 (dw-schema.md §2.5.1). 값을 여기서 바꾸면 계약과 갈라진다.
DEFAULT_MIN_BRAND_COUNT = 5        # R1
DEFAULT_MIN_SAMPLE_SIZE = 200      # R2 — 주간 분모 기준
DEFAULT_DOMINANCE_RATIO = 0.5      # R3

# B층이 공유하는 비율. brand_daily_kpi 에서 나온다.
# 지표를 더하려면 여기에 (이름, 분자, 분모) 를 추가한다 — grain 은 바뀌지 않는다.
COMMONS_METRICS = (
    ("detail_entry_rate", "detail_view_sessions", "impression_sessions"),
    ("view_to_cart_rate", "add_to_cart_sessions", "detail_view_sessions"),
    ("information_view_rate", "information_view_sessions", "product_view_sessions"),
)


def _commons_cohort_weekly(
    brand_daily_df: Any,
    brand_cohort_df: Any,
    min_brand_count: int = DEFAULT_MIN_BRAND_COUNT,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    dominance_ratio: float = DEFAULT_DOMINANCE_RATIO,
) -> Any:
    """코호트별 비율 분위. B층이라 다른 브랜드에게 보여도 되는 형태다.

    브랜드 하나의 로그는 표본이 작아 혼자서는 판단이 안 되고, 합치면 판단이 된다.
    그런데 합치는 순간 내 숫자가 경쟁자에게 보인다. 그래서 **비율의 분위만 내고 절대
    건수를 두지 않으며**, 표본이 얇거나 한 브랜드가 지배하는 셀은 값을 지운다
    (``dw-schema.md`` §2.5.1 R1~R4).

    grain 이 주간인 이유는 R2 때문이다. 분모 200 을 일간에 걸면 재생 데이터 336행 중
    5행(1%)만 통과한다. 주간으로 접으면 브랜드 31/56(55%)이 통과한다.

    **브랜드 식별자를 싣지 않는다.** 코호트 단위 집계라 행이 브랜드에 대응하지 않고,
    ``brand_hash`` 조차 두지 않는다 (R5 보다 강하다).
    """

    from pyspark.sql import functions as F

    # 주간 창은 관측 구간의 마지막 날에서 끊는다. 재구매 Mart 의 snapshot 과 같은 방식.
    snapshot = brand_daily_df.agg(
        F.max("event_date_kst").alias("snapshot")
    ).first()["snapshot"]
    window_days = 7

    cohorts = brand_cohort_df.where(
        F.col("cohort_key").isNotNull() & F.col("commons_participating")
    ).select("brand_id", "cohort_key")

    if snapshot is None:
        # 브랜드 행이 없는 실행에서도 스키마는 남긴다.
        weekly = brand_daily_df.withColumn(
            "window_end_date", F.col("event_date_kst")
        ).withColumn("window_start_date", F.col("event_date_kst"))
    else:
        start = F.date_sub(F.lit(snapshot).cast("date"), window_days - 1)
        weekly = (
            brand_daily_df.where(F.col("event_date_kst") >= start)
            .withColumn("window_start_date", start)
            .withColumn("window_end_date", F.lit(snapshot).cast("date"))
        )

    axes = list(EXECUTION_AXES)
    per_brand = weekly.join(cohorts, ["brand_id"], "inner").groupBy(
        "cohort_key", "window_start_date", "window_end_date", "brand_id", *axes
    ).agg(*[
        F.sum(F.col(column)).cast("long").alias(column)
        for column in sorted({
            column
            for _, numerator, denominator in COMMONS_METRICS
            for column in (numerator, denominator)
        })
    ])

    key_columns = [
        "window_start_date", "window_end_date", "cohort_key", "metric_name", *axes
    ]
    frames = []
    for metric_name, numerator, denominator in COMMONS_METRICS:
        scored = per_brand.select(
            "cohort_key", "window_start_date", "window_end_date", *axes,
            F.lit(metric_name).alias("metric_name"),
            F.col(denominator).alias("_denominator"),
            _safe_ratio(F.col(numerator), F.col(denominator)).alias("_value"),
        )
        frames.append(scored)
    metrics = frames[0]
    for extra in frames[1:]:
        metrics = metrics.unionByName(extra)

    aggregated = metrics.groupBy(*key_columns).agg(
        F.countDistinct(
            F.when(F.col("_value").isNotNull(), F.col("cohort_key"))
        ).cast("long").alias("_unused"),
        F.count(F.col("_value")).cast("long").alias("brand_count"),
        F.sum("_denominator").cast("long").alias("_sample"),
        F.max("_denominator").cast("long").alias("_largest"),
        # 근사치가 아닌 정확 percentile. category_price_reference 와 같다.
        F.expr("percentile(_value, 0.25)").cast("double").alias("_p25"),
        F.expr("percentile(_value, 0.5)").cast("double").alias("_p50"),
        F.expr("percentile(_value, 0.75)").cast("double").alias("_p75"),
        F.current_timestamp().alias("mart_processed_at"),
    ).drop("_unused")

    # R1 → R3 → R2 순서로 판정한다. R1·R3 는 값을 지우고 R2 는 플래그만 남긴다 —
    # 표본이 얇은 것과 식별 위험이 있는 것은 다른 문제다.
    too_few_brands = F.col("brand_count") < F.lit(int(min_brand_count))
    dominated = (F.col("_sample") > 0) & (
        F.col("_largest") > F.col("_sample") * F.lit(float(dominance_ratio))
    )
    suppressed = too_few_brands | dominated

    result = (
        aggregated.withColumn("is_dominated", dominated)
        .withColumn("is_suppressed", suppressed)
        .withColumn(
            "is_sample_sufficient", F.col("_sample") >= F.lit(int(min_sample_size))
        )
    )
    for alias, source in (("p25", "_p25"), ("p50", "_p50"), ("p75", "_p75")):
        result = result.withColumn(
            alias, F.when(~F.col("is_suppressed"), F.col(source))
        )
    return (
        result.drop("_sample", "_largest", "_p25", "_p50", "_p75")
        .withColumn("snapshot_week_kst", F.col("window_end_date"))
        .withColumn("min_brand_count", F.lit(int(min_brand_count)).cast("int"))
        .withColumn("min_sample_size", F.lit(int(min_sample_size)).cast("int"))
        .withColumn(
            "dominance_ratio", F.lit(float(dominance_ratio)).cast("double")
        )
    )


def load_trait_contract(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        contract = json.load(stream)
    if set(contract.get("traits", {})) != {"price", "ingredient", "review", "concern", "participate"}:
        raise ValueError("trait contract must define exactly five supported traits")
    if int(contract.get("window_days", 0)) < 1:
        raise ValueError("trait contract window_days must be positive")
    return contract


PURCHASE_REASONS = (
    "ingredient",
    "skin_fit",
    "reviews",
    "review_same_skin",
    "price",
    "brand_trust",
    "texture_finish",
    "clean_claim",
    "recommendation",
    "restock",
)
SUPPORTED_TRAITS = ("price", "ingredient", "review", "concern", "participate")


def load_reason_trait_map(path: str) -> dict[str, Any]:
    """선언 이유 -> 관측 성향 매핑. 이유 10종을 빠짐없이 선언해야 한다."""

    with open(path, encoding="utf-8") as stream:
        contract = json.load(stream)
    mapping = contract.get("reason_to_trait", {})
    if set(mapping) != set(PURCHASE_REASONS):
        raise ValueError("reason contract must map exactly the ten purchase reasons")
    unknown = {
        trait for trait in mapping.values() if trait is not None and trait not in SUPPORTED_TRAITS
    }
    if unknown:
        raise ValueError(f"reason contract maps unsupported traits: {sorted(unknown)}")
    return mapping


def load_banner_values(feature_vocab_path: str, affinity_lift_path: str) -> set[str]:
    """Load source strings; Korean labels are deliberately excluded."""

    with open(feature_vocab_path, encoding="utf-8") as stream:
        feature_vocab = json.load(stream)
    values = {
        str(value)
        for block in feature_vocab.get("blocks", [])
        for value in (block.get("vocab") or [])
        if value is not None and str(value).strip()
    }
    with open(affinity_lift_path, encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            segment = row.get("segment")
            if segment is not None and segment.strip():
                values.add(segment)
    if not values:
        raise ValueError("banner source vocabulary must not be empty")
    return values


def _banner_daily(product_fact_df: Any, allowed_values: set[str]) -> Any:
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    # 실행 축 5종. cross_brand_daily 와 같은 이유로 generator_type 이 필요하다
    # — 커밋 82afffe sweep 잔여분 (dw-schema.md §2, Jira 324).
    group_columns = [
        "event_date_kst", "brand_id", "product_id", "banner_type", "banner_value",
        "banner_slot", "trait_source", "policy_version", *EXECUTION_AXES,
    ]
    banners = product_fact_df.where(
        F.col("event_name").isin("banner_impression", "banner_click")
    )
    result = banners.groupBy(*group_columns).agg(
        F.sum(F.when(F.col("event_name") == "banner_impression", 1).otherwise(0)).cast("long").alias("impression_count"),
        F.sum(F.when(F.col("event_name") == "banner_click", 1).otherwise(0)).cast("long").alias("click_count"),
        F.countDistinct(F.when(F.col("event_name") == "banner_impression", F.col("session_id"))).alias("impression_sessions"),
        F.countDistinct(F.when(F.col("event_name") == "banner_click", F.col("session_id"))).alias("click_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumn("banner_ctr", _safe_ratio(F.col("click_count"), F.col("impression_count")))
        .withColumn("skip_count", (F.col("impression_count") - F.col("click_count")).cast("long"))
        .withColumn(
            "banner_value_is_valid",
            F.when(F.col("banner_type") == "new_brand", F.col("banner_value").isNull())
            .otherwise(F.col("banner_value").isin(*sorted(allowed_values))),
        )
    )


def _non_blank_property(column: Any) -> Any:
    from pyspark.sql import functions as F

    return column.isNotNull() & (F.length(F.trim(column)) > 0)


def _user_trait_daily(sessionized_df: Any, contract: dict[str, Any]) -> Any:
    from functools import reduce
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    signal_frames = []
    properties = F.col("properties_json")
    dwell_rule = contract.get("dwell", {})
    dwell_min = float(dwell_rule.get("min_seconds", 0))
    dwell_cap = float(dwell_rule.get("cap_seconds", 0)) or None

    def prop(name: str) -> Any:
        return F.get_json_object(properties, f"$.{name}")

    for trait, rules in contract["traits"].items():
        for rule in rules:
            condition = F.col("event_name") == F.lit(rule["event_name"])
            property_name = rule.get("property")
            if property_name:
                condition = condition & prop(property_name).isin(*rule["values"])
            # 배열 property 는 원소 포함 여부로 본다 (purchase_reason_select.reasons)
            array_property = rule.get("array_property")
            if array_property:
                values = F.from_json(prop(array_property), "array<string>")
                matched = reduce(
                    lambda left, right: left | right,
                    [F.array_contains(values, F.lit(v)) for v in rule["values"]],
                )
                condition = condition & F.coalesce(matched, F.lit(False))
            # selection_kind 가 안 실리는 화면의 폴백 규칙이다. 값이 있으면 위 규칙이 잡는다.
            require_absent = rule.get("require_absent")
            if require_absent:
                condition = condition & ~_non_blank_property(prop(require_absent))
            minimum = rule.get("property_min_exclusive")
            if minimum:
                condition = condition & (
                    F.coalesce(prop(minimum["name"]).cast("double"), F.lit(0.0))
                    > F.lit(float(minimum["value"]))
                )
            # 펼침만 센다. 접는 동작까지 세면 한 번 본 것이 두 번이 된다.
            excluded_property = rule.get("excluded_property")
            if excluded_property:
                excluded = prop(excluded_property)
                condition = condition & (
                    excluded.isNull() | ~excluded.isin(*rule["excluded_values"])
                )
            if "weight_per_second" in rule:
                seconds = F.coalesce(
                    prop("dwell_ms").cast("double"), F.lit(0.0)
                ) / F.lit(1000.0)
                if dwell_cap:
                    seconds = F.least(seconds, F.lit(dwell_cap))
                score = F.when(
                    seconds < F.lit(dwell_min), F.lit(0.0)
                ).otherwise(seconds * F.lit(float(rule["weight_per_second"])))
            else:
                score = F.lit(float(rule["weight"]))
            signal_frames.append(
                sessionized_df.where(
                    condition
                    & F.col("user_id").isNotNull()
                    & (F.length(F.trim(F.col("user_id"))) > 0)
                ).select(
                    "event_id", "event_date_kst", "user_id", "identity_scope",
                    "actor_type", "source", "scenario_id", "simulation_run_id",
                    F.lit(trait).alias("trait"), score.alias("event_trait_score"),
                )
            )
    signals = reduce(lambda left, right: left.unionByName(right), signal_frames)
    maximum_date = signals.agg(F.max("event_date_kst").alias("date")).first()["date"]
    if maximum_date is None:
        # Preserve a stable schema for empty snapshots.
        return signals.select(
            F.col("event_date_kst").alias("trait_date_kst"), "user_id",
            "identity_scope", "actor_type", "source", "scenario_id",
            "simulation_run_id", "trait",
            F.lit(None).cast("double").alias("trait_score"),
            F.lit(None).cast("int").alias("trait_rank"),
            F.lit(False).alias("is_primary_trait"),
            F.col("event_date_kst").alias("window_start_date"),
            F.col("event_date_kst").alias("window_end_date"),
            F.lit(0).cast("long").alias("contributing_event_count"),
            F.lit(contract["version"]).alias("trait_policy_version"),
            F.current_timestamp().alias("mart_processed_at"),
        )
    window_days = int(contract["window_days"])
    expanded = signals.withColumn(
        "trait_date_kst",
        F.explode(F.sequence(
            F.col("event_date_kst"),
            F.least(F.date_add(F.col("event_date_kst"), window_days - 1), F.lit(maximum_date).cast("date")),
        )),
    )
    # 페르소나와 실계정이 같은 user_id 공간을 쓰지 않도록 식별 축을 grain 에 둔다.
    key_columns = [
        "trait_date_kst", "user_id", "identity_scope",
        "actor_type", "source", "scenario_id", "simulation_run_id",
    ]
    scores = expanded.groupBy(*key_columns, "trait").agg(
        F.sum("event_trait_score").cast("double").alias("trait_score"),
        F.countDistinct("event_id").cast("long").alias("contributing_event_count"),
    )
    rank_window = Window.partitionBy(*key_columns).orderBy(
        F.col("trait_score").desc(), F.col("trait").asc()
    )
    return (
        scores.withColumn("trait_rank", F.row_number().over(rank_window))
        .withColumn("is_primary_trait", F.col("trait_rank") == 1)
        .withColumn("window_start_date", F.date_sub(F.col("trait_date_kst"), window_days - 1))
        .withColumn("window_end_date", F.col("trait_date_kst"))
        .withColumn("trait_policy_version", F.lit(contract["version"]))
        .withColumn("mart_processed_at", F.current_timestamp())
    )


def _cross_brand_daily(sessionized_df: Any) -> Any:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    sessionized_df = _observed_events(sessionized_df)

    views = sessionized_df.where(
        (F.col("event_name") == "product_view") & F.col("brand_id").isNotNull()
    )
    view_order = Window.partitionBy("session_id").orderBy(
        F.col("event_order"), F.col("event_time"), F.col("event_id")
    )
    session_view_order = view_order.rowsBetween(
        Window.unboundedPreceding, Window.unboundedFollowing
    )
    destination_order = Window.partitionBy("session_id", "brand_id").orderBy(
        F.col("event_order"), F.col("event_time"), F.col("event_id")
    )
    first_destination_views = (
        views.withColumn("_first_brand_id", F.first("brand_id").over(session_view_order))
        .withColumn("_destination_rank", F.row_number().over(destination_order))
        .where(F.col("_destination_rank") == 1)
        .select(
            "session_id",
            F.col("brand_id").alias("destination_brand_id"),
            F.col("product_id").alias("destination_product_id"),
            F.col("event_order").alias("destination_event_order"),
            "event_date_kst",
            *EXECUTION_AXES,
            "_first_brand_id",
            F.get_json_object("properties_json", "$.recommendation_id").alias(
                "view_recommendation_id"
            ),
        )
        .withColumn(
            "_is_cross_brand",
            F.col("_first_brand_id") != F.col("destination_brand_id"),
        )
    )

    clicks = sessionized_df.where(
        F.col("event_name").isin("recommendation_click", "banner_click")
    ).select(
        "session_id",
        F.col("product_id").alias("click_product_id"),
        F.col("event_order").alias("click_event_order"),
        "event_name",
        F.get_json_object("properties_json", "$.recommendation_id").alias(
            "click_recommendation_id"
        ),
    )
    destinations = first_destination_views.alias("destination")
    preceding_clicks = destinations.join(
        clicks.alias("click"),
        (F.col("destination.session_id") == F.col("click.session_id"))
        & (F.col("destination.destination_product_id") == F.col("click.click_product_id"))
        & (F.col("click.click_event_order") < F.col("destination.destination_event_order")),
        "left",
    )
    click_flags = preceding_clicks.groupBy(
        F.col("destination.session_id").alias("session_id"),
        F.col("destination.destination_brand_id").alias("destination_brand_id"),
    ).agg(
        F.max(
            F.when(
                (F.col("click.event_name") == "recommendation_click")
                & F.col("click.click_recommendation_id").isNotNull()
                & (F.length(F.trim(F.col("click.click_recommendation_id"))) > 0),
                1,
            ).otherwise(0)
        ).cast("boolean").alias("has_preceding_recommendation_click"),
        F.max(
            F.when(F.col("click.event_name") == "banner_click", 1).otherwise(0)
        ).cast("boolean").alias("has_preceding_banner_click"),
    )
    entries = (
        first_destination_views.join(
            click_flags, ["session_id", "destination_brand_id"], "left"
        )
        .withColumn(
            "_is_recommendation_entry",
            (
                F.col("view_recommendation_id").isNotNull()
                & (F.length(F.trim(F.col("view_recommendation_id"))) > 0)
            )
            | F.coalesce(F.col("has_preceding_recommendation_click"), F.lit(False)),
        )
        .withColumn(
            "_is_banner_entry",
            F.coalesce(F.col("has_preceding_banner_click"), F.lit(False)),
        )
    )
    # 실행 축 5종. generator_type 이 없으면 PC(python_batch)와 PA(agent_llm)의
    # 교차 유입 세션이 한 행에 합쳐진다 — actor_type 은 둘 다 synthetic 이라
    # 구분이 안 된다 (dw-schema.md §2 · persona-schema.md §9).
    group_columns = ["event_date_kst", "destination_brand_id", *EXECUTION_AXES]
    result = entries.groupBy(*group_columns).agg(
        F.countDistinct("session_id").alias("brand_view_sessions"),
        F.countDistinct(F.when(F.col("_is_cross_brand"), F.col("session_id"))).alias("cross_brand_entry_sessions"),
        F.countDistinct(F.when(F.col("_is_cross_brand") & F.col("_is_recommendation_entry"), F.col("session_id"))).alias("recommendation_cross_brand_entry_sessions"),
        F.countDistinct(F.when(F.col("_is_cross_brand") & F.col("_is_banner_entry"), F.col("session_id"))).alias("banner_cross_brand_entry_sessions"),
        F.current_timestamp().alias("mart_processed_at"),
    )
    return (
        result.withColumn("cross_brand_entry_rate", _safe_ratio(F.col("cross_brand_entry_sessions"), F.col("brand_view_sessions")))
        .withColumn("recommendation_cross_brand_entry_rate", _safe_ratio(F.col("recommendation_cross_brand_entry_sessions"), F.col("brand_view_sessions")))
        .withColumn("banner_cross_brand_entry_rate", _safe_ratio(F.col("banner_cross_brand_entry_sessions"), F.col("brand_view_sessions")))
        .withColumn("recommendation_share_of_cross_brand_entries", _safe_ratio(F.col("recommendation_cross_brand_entry_sessions"), F.col("cross_brand_entry_sessions")))
        .withColumn("banner_share_of_cross_brand_entries", _safe_ratio(F.col("banner_cross_brand_entry_sessions"), F.col("cross_brand_entry_sessions")))
    )


def _analytics_baseline(
    product_fact_df: Any,
    cross_brand_daily_df: Any,
    policy_version: str,
    start_date: str,
    end_date: str,
) -> Any:
    from pyspark.sql import functions as F

    # 시드 Event 제외는 Mart 정의의 일부다. 호출부에 두면 경로마다 결과가 달라진다.
    product_fact_df = _observed_events(product_fact_df)

    period = (F.col("event_date_kst") >= F.lit(start_date).cast("date")) & (
        F.col("event_date_kst") <= F.lit(end_date).cast("date")
    )
    recommendations = (
        product_fact_df.where(period & F.col("event_name").isin("recommendation_impression", "recommendation_click"))
        .groupBy("brand_id", "algorithm")
        .agg(
            F.sum(F.when(F.col("event_name") == "recommendation_click", 1).otherwise(0)).cast("long").alias("numerator"),
            F.sum(F.when(F.col("event_name") == "recommendation_impression", 1).otherwise(0)).cast("long").alias("denominator"),
        )
        .withColumn("metric_name", F.lit("recommendation_ctr"))
    )
    cross = (
        cross_brand_daily_df.where(period)
        .groupBy(F.col("destination_brand_id").alias("brand_id"))
        .agg(
            F.sum("cross_brand_entry_sessions").cast("long").alias("numerator"),
            F.sum("brand_view_sessions").cast("long").alias("denominator"),
        )
        .withColumn("algorithm", F.lit(None).cast("string"))
        .withColumn("metric_name", F.lit("cross_brand_entry_rate"))
    )
    return (
        recommendations.unionByName(cross)
        .withColumn("metric_value", _safe_ratio(F.col("numerator"), F.col("denominator")))
        .withColumn("baseline_policy_version", F.lit(policy_version))
        .withColumn("baseline_start_date", F.lit(start_date).cast("date"))
        .withColumn("baseline_end_date", F.lit(end_date).cast("date"))
        .withColumn("mart_processed_at", F.current_timestamp())
    )


def _write_mart(frame: Any, path: str, partition_column: str | None = None) -> None:
    """빈 결과에 partitionBy를 걸면 데이터 파일이 남지 않아 스키마를 다시 읽을 수 없다.

    배너 Event를 아직 아무도 발행하지 않는 기간에는 `banner_daily`가 정상적으로
    0행이다. 그때 파티션 쓰기를 하면 `_SUCCESS`만 남아 검증 Job의 읽기가
    UNABLE_TO_INFER_SCHEMA로 실패한다. 0행이면 파티션 없이 써서 스키마를 남긴다.
    """

    writer = frame.write.mode("overwrite")
    if partition_column is not None and not frame.isEmpty():
        writer.parquet(path, partitionBy=partition_column)
    else:
        writer.parquet(path)


def build_mart_frames(
    sessionized_df: Any,
    product_fact_df: Any,
    time_zone: str,
    event_weights: dict[str, float] | None = None,
    dim_product_df: Any | None = None,
    product_ingredient_df: Any | None = None,
    ingredient_vocab_df: Any | None = None,
    cleansing_category_weight: float = DEFAULT_CLEANSING_CATEGORY_WEIGHT,
    price_min_sample_size: int = DEFAULT_PRICE_MIN_SAMPLE_SIZE,
    trait_contract: dict[str, Any] | None = None,
    allowed_banner_values: set[str] | None = None,
    baseline_policy_version: str | None = None,
    baseline_start_date: str | None = None,
    baseline_end_date: str | None = None,
    purchase_fact_df: Any | None = None,
    purchase_reason_fact_df: Any | None = None,
    reason_trait_map: dict[str, Any] | None = None,
    repurchase_window_days: int = DEFAULT_REPURCHASE_WINDOW_DAYS,
    persona_bridge_df: Any | None = None,
    price_bins: list[tuple[str, float | None]] | None = None,
    dim_brand_df: Any | None = None,
    content_interest_df: Any | None = None,
    section_dwell_df: Any | None = None,
    cleaned_df: Any | None = None,
) -> dict[str, Any]:
    stage_events = _funnel_stage_events(sessionized_df, product_fact_df)
    funnel_session = _build_funnel_session_fact(stage_events, time_zone)
    frames = {
        "funnel_session_fact": funnel_session,
        "product_daily_kpi": _product_daily_kpi(product_fact_df, event_weights),
        "funnel_daily_kpi": _funnel_daily_kpi(funnel_session),
        "brand_daily_kpi": _brand_daily_kpi(
            product_fact_df, funnel_session, time_zone
        ),
        "cross_brand_daily": _cross_brand_daily(sessionized_df),
    }
    if content_interest_df is not None:
        # E3 세 Mart 는 상품 조회 세션을 공통 분모로 쓴다 (dw-schema §4.4·§4.19·§4.20).
        frames["content_daily_kpi"] = _content_daily_kpi(
            content_interest_df, funnel_session, time_zone
        )
        frames["content_conversion_daily"] = _content_conversion_daily(
            content_interest_df, funnel_session, time_zone
        )
        frames["behavior_conversion_daily"] = _behavior_conversion_daily(
            sessionized_df, funnel_session, time_zone
        )
    # E6 는 상세를 연 세션(product_view ∪ quick_look)을 공통 분모로 쓴다.
    frames["friction_daily"] = _friction_daily(
        sessionized_df, funnel_session, time_zone
    )
    frames["exit_daily"] = _exit_daily(sessionized_df, funnel_session, time_zone)
    frames["entry_source_daily"] = _entry_source_daily(
        product_fact_df, funnel_session, time_zone
    )
    frames["product_exit_daily"] = _product_exit_daily(sessionized_df)
    if cleaned_df is not None and dim_product_df is not None:
        # Event 볼륨은 정제 단계 전체를 센다. 다른 Mart 와 달리 Event 를 고르지 않는다.
        frames["event_daily"] = _event_daily(cleaned_df, dim_product_df)
    if section_dwell_df is not None and persona_bridge_df is not None:
        # 고객군 축은 bridge 를 만든 실행에서만 나온다.
        frames["segment_content_daily"] = _segment_content_daily(
            section_dwell_df, sessionized_df, persona_bridge_df
        )
    if persona_bridge_df is not None:
        frames["persona_segment_daily_kpi"] = _persona_segment_daily_kpi(
            product_fact_df, persona_bridge_df, event_weights
        )
    if price_bins is not None and dim_product_df is not None:
        frames["brand_price_band_daily_kpi"] = _brand_price_band_daily_kpi(
            product_fact_df, dim_product_df, price_bins
        )
        if persona_bridge_df is not None:
            # 고객군 × 가격 밴드 교차 (S5). 두 축 Mart 중 어느 쪽에도 축을
            # 얹을 수 없어 별도로 낸다.
            frames["segment_price_band_daily_kpi"] = _segment_price_band_daily_kpi(
                product_fact_df, dim_product_df, persona_bridge_df, price_bins
            )
        if dim_brand_df is not None:
            # 코호트는 카탈로그 파생이고, Commons 는 그 위에 brand_daily_kpi 를 얹는다.
            frames["brand_cohort_dim"] = _brand_cohort_dim(
                dim_product_df, dim_brand_df, price_bins
            )
            frames["commons_cohort_weekly"] = _commons_cohort_weekly(
                frames["brand_daily_kpi"], frames["brand_cohort_dim"]
            )
    if trait_contract is not None:
        # 장기 성향은 주입된 선호도 신호로 본다. 시드를 뺄지는 별도 결정 대기.
        frames["user_trait_daily"] = _user_trait_daily(sessionized_df, trait_contract)
    if allowed_banner_values is not None:
        frames["banner_daily"] = _banner_daily(
            product_fact_df, allowed_banner_values
        )
    # 구매 이유 대조는 user_trait_daily 를 읽으므로 그 뒤에 둔다.
    if purchase_fact_df is not None and purchase_reason_fact_df is not None:
        frames["product_repurchase_daily"] = _product_repurchase_daily(
            purchase_fact_df, repurchase_window_days
        )
        frames["brand_repurchase_daily"] = _brand_repurchase_daily(
            purchase_fact_df, purchase_reason_fact_df, repurchase_window_days
        )
        if reason_trait_map is not None:
            frames["purchase_reason_daily"] = _purchase_reason_daily(
                purchase_reason_fact_df,
                purchase_fact_df,
                frames.get("user_trait_daily"),
                reason_trait_map,
            )
    if (
        event_weights is not None
        and dim_product_df is not None
        and product_ingredient_df is not None
        and ingredient_vocab_df is not None
    ):
        frames["ingredient_weekly_interest"] = _ingredient_weekly_interest(
            sessionized_df,
            dim_product_df,
            product_ingredient_df,
            ingredient_vocab_df,
            time_zone,
            event_weights,
            cleansing_category_weight,
        )
        frames["category_price_reference"] = _category_price_reference(
            dim_product_df, price_min_sample_size
        )
    if baseline_policy_version and baseline_start_date and baseline_end_date:
        frames["analytics_baseline"] = _analytics_baseline(
            product_fact_df,
            frames["cross_brand_daily"],
            baseline_policy_version,
            baseline_start_date,
            baseline_end_date,
        )
    return frames


def run(spark: Any, config: BuildMartsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    try:
        from .behavior_weights import load
    except ImportError:
        from behavior_weights import load

    event_weights = load(config.behavior_weights_path)["event"]
    trait_contract = load_trait_contract(config.trait_weights_path)
    reason_trait_map = load_reason_trait_map(config.reason_trait_map_path)
    allowed_banner_values = load_banner_values(
        config.feature_vocab_path, config.affinity_lift_path
    )
    from pyspark.sql.types import (
        DoubleType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    product_ingredient_schema = StructType(
        [
            StructField("product_id", StringType(), False),
            StructField("ingredient_id", IntegerType(), False),
            StructField("ingredient", StringType(), False),
            StructField("position_weight", DoubleType(), False),
            StructField("source", StringType(), False),
            StructField("vocab_version", StringType(), False),
        ]
    )
    ingredient_vocab_schema = StructType(
        [
            StructField("ingredient_id", IntegerType(), False),
            StructField("ingredient", StringType(), False),
            StructField("label_ko", StringType(), True),
            StructField("doc_freq", IntegerType(), False),
            StructField("vocab_version", StringType(), False),
        ]
    )
    sessionized = spark.read.option("mergeSchema", "true").parquet(
        config.sessionized_path
    )
    product_fact = spark.read.option("mergeSchema", "true").parquet(
        config.product_fact_path
    )
    dim_product = spark.read.option("mergeSchema", "true").parquet(
        config.dim_product_path
    )
    product_ingredient = (
        spark.read.option("header", "true")
        .schema(product_ingredient_schema)
        .csv(config.product_ingredient_path)
    )
    ingredient_vocab = (
        spark.read.option("header", "true")
        .schema(ingredient_vocab_schema)
        .csv(config.ingredient_vocab_path)
    )
    purchase_fact = spark.read.option("mergeSchema", "true").parquet(
        config.purchase_fact_path
    )
    purchase_reason_fact = spark.read.option("mergeSchema", "true").parquet(
        config.purchase_reason_fact_path
    )
    dim_brand = spark.read.option("mergeSchema", "true").parquet(
        config.dim_brand_path
    )
    content_interest = spark.read.option("mergeSchema", "true").parquet(
        config.content_interest_path
    )
    section_dwell = spark.read.option("mergeSchema", "true").parquet(
        config.section_dwell_path
    )
    cleaned = spark.read.option("mergeSchema", "true").parquet(
        config.cleaned_path
    )
    persona_bridge = load_persona_segments(spark, config.persona_bridge_path)
    price_bins = load_price_bins(config.feature_vocab_path)
    frames = build_mart_frames(
        sessionized,
        product_fact,
        config.time_zone,
        event_weights,
        dim_product,
        product_ingredient,
        ingredient_vocab,
        config.cleansing_category_weight,
        config.price_min_sample_size,
        trait_contract,
        allowed_banner_values,
        config.baseline_policy_version,
        config.baseline_start_date,
        config.baseline_end_date,
        purchase_fact,
        purchase_reason_fact,
        reason_trait_map,
        config.repurchase_window_days,
        persona_bridge,
        price_bins,
        dim_brand,
        content_interest,
        section_dwell,
        cleaned,
    )
    _write_mart(
        frames["funnel_session_fact"],
        config.funnel_session_path,
        "funnel_date_kst",
    )
    frames["product_daily_kpi"].write.mode("overwrite").parquet(
        config.product_daily_path,
    )
    frames["funnel_daily_kpi"].write.mode("overwrite").parquet(
        config.funnel_daily_path,
    )
    _write_mart(
        frames["brand_daily_kpi"], config.brand_daily_path, "event_date_kst"
    )
    _write_mart(
        frames["persona_segment_daily_kpi"],
        config.persona_segment_path,
        "event_date_kst",
    )
    _write_mart(
        frames["brand_price_band_daily_kpi"],
        config.price_band_path,
        "event_date_kst",
    )
    frames["brand_cohort_dim"].write.mode("overwrite").parquet(
        config.brand_cohort_path,
    )
    _write_mart(
        frames["commons_cohort_weekly"],
        config.commons_cohort_path,
        "snapshot_week_kst",
    )
    _write_mart(
        frames["content_daily_kpi"], config.content_daily_path, "event_date_kst"
    )
    _write_mart(
        frames["content_conversion_daily"],
        config.content_conversion_path,
        "event_date_kst",
    )
    _write_mart(
        frames["behavior_conversion_daily"],
        config.behavior_conversion_path,
        "event_date_kst",
    )
    _write_mart(
        frames["friction_daily"], config.friction_daily_path, "event_date_kst"
    )
    _write_mart(
        frames["exit_daily"], config.exit_daily_path, "event_date_kst"
    )
    _write_mart(
        frames["entry_source_daily"],
        config.entry_source_daily_path,
        "event_date_kst",
    )
    _write_mart(
        frames["product_exit_daily"],
        config.product_exit_daily_path,
        "event_date_kst",
    )
    _write_mart(
        frames["segment_content_daily"],
        config.segment_content_daily_path,
        "event_date_kst",
    )
    _write_mart(
        frames["event_daily"], config.event_daily_path, "event_date_kst"
    )
    _write_mart(
        frames["segment_price_band_daily_kpi"],
        config.segment_price_band_path,
        "event_date_kst",
    )
    _write_mart(
        frames["product_repurchase_daily"],
        config.product_repurchase_path,
        "snapshot_date_kst",
    )
    _write_mart(
        frames["brand_repurchase_daily"],
        config.brand_repurchase_path,
        "snapshot_date_kst",
    )
    _write_mart(
        frames["purchase_reason_daily"],
        config.purchase_reason_path,
        "event_date_kst",
    )
    _write_mart(
        frames["ingredient_weekly_interest"],
        config.ingredient_weekly_path,
        "interest_week_kst",
    )
    frames["category_price_reference"].write.mode("overwrite").parquet(
        config.category_price_path,
    )
    _write_mart(frames["banner_daily"], config.banner_daily_path, "event_date_kst")
    _write_mart(frames["user_trait_daily"], config.user_trait_daily_path, "trait_date_kst")
    _write_mart(frames["cross_brand_daily"], config.cross_brand_daily_path, "event_date_kst")
    if "analytics_baseline" in frames:
        _write_mart(frames["analytics_baseline"], config.baseline_path)


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("build-analytics-marts")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        run(spark, config)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
