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
FUNNEL_PRODUCT_EVENTS = (
    "product_impression",
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
        F.min(F.when(F.col("event_name") == "product_impression", F.col("event_time"))).alias(
            "first_impression_at"
        ),
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
        count_events("product_click"),
        count_events("quick_look"),
        count_events("product_view"),
        count_events("add_to_cart"),
        count_events("remove_from_cart"),
        count_events("purchase"),
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
        F.first("currency", ignorenulls=True).alias("currency"),
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
        .withColumn("product_ctr", _safe_ratio(F.col("product_click_count"), F.col("product_impression_count")))
        .withColumn("detail_entry_rate", _safe_ratio(F.col("product_view_count"), F.col("product_impression_count")))
        .withColumn("add_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("detail_view_sessions")))
        .withColumn("purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("detail_view_sessions")))
    )


def _funnel_daily_kpi(funnel_session_df: Any) -> Any:
    from pyspark.sql import functions as F

    group_columns = ["funnel_date_kst", "product_id", *EXECUTION_AXES]
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
            (F.col("detail_entry_path") == F.lit("direct_click")).cast("int")
        ).cast("long").alias("direct_click_sessions"),
        F.sum(
            (
                (F.col("detail_entry_path") == F.lit("direct_click"))
                & F.col("reached_add_to_cart")
            ).cast("int")
        ).cast("long").alias("direct_click_cart_sessions"),
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
        .withColumn("click_to_view_rate", _safe_ratio(F.col("product_view_sessions"), F.col("click_sessions")))
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
            "product_impression", "product_click", "product_view",
            "quick_look", "add_to_cart",
        )
    ).select(
        *key_columns,
        "session_id",
        "user_id",
        "product_id",
        (F.col("event_name") == "product_impression").alias("_impression"),
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
        stage_sessions(F.col("event_name") == "product_impression", "impression_sessions"),
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

    group_columns = [
        "event_date_kst", "brand_id", "product_id", "banner_type", "banner_value",
        "banner_slot", "trait_source", "policy_version", "actor_type", "source",
        "scenario_id", "simulation_run_id",
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
            "actor_type",
            "source",
            "scenario_id",
            "simulation_run_id",
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
    group_columns = [
        "event_date_kst", "destination_brand_id",
        "actor_type", "source", "scenario_id", "simulation_run_id",
    ]
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
    if persona_bridge_df is not None:
        frames["persona_segment_daily_kpi"] = _persona_segment_daily_kpi(
            product_fact_df, persona_bridge_df, event_weights
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
    persona_bridge = load_persona_segments(spark, config.persona_bridge_path)
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
