"""Build Funnel facts and dashboard marts from Processed datasets.

The job is a full-snapshot batch MVP.  Its inputs are the deduplicated
``sessionized_events`` and ``product_event_fact`` datasets only; Raw is never
read directly by a Mart job.

Outputs:

* ``funnel_session_fact``: one row per session and product
* ``product_daily_kpi``: product/event-date KPI counts and rates
* ``funnel_daily_kpi``: session-based funnel reach and conversion rates
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_FUNNEL_SESSION_PATH = "data/processed/funnel_session_fact"
DEFAULT_PRODUCT_DAILY_PATH = "data/marts/product_daily_kpi"
DEFAULT_FUNNEL_DAILY_PATH = "data/marts/funnel_daily_kpi"
DEFAULT_TIME_ZONE = "Asia/Seoul"
DEFAULT_BEHAVIOR_WEIGHTS_PATH = "frontend/src/types/log.ts"

FUNNEL_PRODUCT_EVENTS = (
    "product_impression",
    "product_click",
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
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        values = {
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
            "funnel_session_path": self.funnel_session_path,
            "product_daily_path": self.product_daily_path,
            "funnel_daily_path": self.funnel_daily_path,
            "behavior_weights_path": self.behavior_weights_path,
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
        "--behavior-weights-path",
        default=_env("BEHAVIOR_WEIGHTS_PATH", DEFAULT_BEHAVIOR_WEIGHTS_PATH),
        help="Execution source for EVENT_WEIGHT",
    )
    parser.add_argument(
        "--time-zone",
        default=_env("ANALYTICS_TIME_ZONE", DEFAULT_TIME_ZONE),
        help="Time zone used for KST date columns",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> BuildMartsConfig:
    args = build_parser().parse_args(argv)
    return BuildMartsConfig(
        sessionized_path=args.sessionized_path,
        product_fact_path=args.product_fact_path,
        funnel_session_path=args.funnel_session_path,
        product_daily_path=args.product_daily_path,
        funnel_daily_path=args.funnel_daily_path,
        behavior_weights_path=args.behavior_weights_path,
        time_zone=args.time_zone,
    )


def _funnel_stage_events(sessionized_df: Any, product_fact_df: Any) -> Any:
    """Return one product-scoped Event stream for Funnel aggregation."""

    from pyspark.sql import functions as F

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
        "tenant_id",
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
        "tenant_id",
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
        "tenant_id",
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
        F.col("first_product_view_at"),
        F.col("first_information_view_at"),
        F.col("first_add_to_cart_at"),
        F.col("first_checkout_at"),
        F.col("first_purchase_at"),
    )
    reached = {
        "impression": F.col("first_impression_at").isNotNull(),
        "click": F.col("first_click_at").isNotNull(),
        "product_view": F.col("first_product_view_at").isNotNull(),
        "information_view": F.col("first_information_view_at").isNotNull(),
        "add_to_cart": F.col("first_add_to_cart_at").isNotNull(),
        "checkout": F.col("first_checkout_at").isNotNull(),
        "purchase": F.col("first_purchase_at").isNotNull(),
    }
    dropoff_step = (
        F.when(reached["purchase"], F.lit(None).cast("string"))
        .when(reached["checkout"], F.lit("checkout"))
        .when(reached["add_to_cart"], F.lit("add_to_cart"))
        .when(reached["information_view"], F.lit("information_view"))
        .when(reached["product_view"], F.lit("product_view"))
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
        "tenant_id",
        "category_id",
        "brand_id",
        "actor_type",
        "source",
        "first_impression_at",
        "first_click_at",
        "first_product_view_at",
        "first_information_view_at",
        "first_add_to_cart_at",
        "first_checkout_at",
        "first_purchase_at",
        reached["impression"].alias("reached_impression"),
        reached["click"].alias("reached_click"),
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

    group_columns = [
        "event_date_kst",
        "tenant_id",
        "product_id",
        "actor_type",
        "source",
        "scenario_id",
        "simulation_run_id",
    ]

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
        .withColumn("add_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("product_view_sessions")))
        .withColumn("purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("product_view_sessions")))
    )


def _funnel_daily_kpi(funnel_session_df: Any) -> Any:
    from pyspark.sql import functions as F

    group_columns = [
        "funnel_date_kst",
        "tenant_id",
        "product_id",
        "actor_type",
        "source",
        "scenario_id",
        "simulation_run_id",
    ]
    result = funnel_session_df.groupBy(*group_columns).agg(
        F.first("category_id", ignorenulls=True).alias("category_id"),
        F.first("brand_id", ignorenulls=True).alias("brand_id"),
        F.sum(F.col("reached_impression").cast("int")).cast("long").alias("impression_sessions"),
        F.sum(F.col("reached_click").cast("int")).cast("long").alias("click_sessions"),
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
        .withColumn("view_to_cart_rate", _safe_ratio(F.col("add_to_cart_sessions"), F.col("product_view_sessions")))
        .withColumn("cart_to_purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("add_to_cart_sessions")))
        .withColumn("view_to_purchase_rate", _safe_ratio(F.col("purchase_sessions"), F.col("product_view_sessions")))
        .withColumn(
            "dropoff_after_impression_rate",
            F.when(
                F.col("impression_sessions") > 0,
                F.lit(1.0) - F.col("click_sessions") / F.col("impression_sessions"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "dropoff_after_view_rate",
            F.when(
                F.col("product_view_sessions") > 0,
                F.lit(1.0) - F.col("add_to_cart_sessions") / F.col("product_view_sessions"),
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


def build_mart_frames(
    sessionized_df: Any,
    product_fact_df: Any,
    time_zone: str,
    event_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    from pyspark.sql import functions as F

    stage_events = _funnel_stage_events(sessionized_df, product_fact_df)
    funnel_session = _build_funnel_session_fact(stage_events, time_zone)
    tenant_product_fact = product_fact_df.where(F.col("tenant_id").isNotNull())
    tenant_funnel_session = funnel_session.where(F.col("tenant_id").isNotNull())
    return {
        "funnel_session_fact": funnel_session,
        "product_daily_kpi": _product_daily_kpi(tenant_product_fact, event_weights),
        "funnel_daily_kpi": _funnel_daily_kpi(tenant_funnel_session),
    }


def run(spark: Any, config: BuildMartsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    try:
        from .behavior_weights import load
    except ImportError:
        from behavior_weights import load

    event_weights = load(config.behavior_weights_path)["event"]
    frames = build_mart_frames(
        spark.read.option("mergeSchema", "true").parquet(config.sessionized_path),
        spark.read.option("mergeSchema", "true").parquet(config.product_fact_path),
        config.time_zone,
        event_weights,
    )
    frames["funnel_session_fact"].write.mode("overwrite").parquet(
        config.funnel_session_path,
        partitionBy="funnel_date_kst",
    )
    frames["product_daily_kpi"].write.mode("overwrite").parquet(
        config.product_daily_path,
        partitionBy="tenant_id",
    )
    frames["funnel_daily_kpi"].write.mode("overwrite").parquet(
        config.funnel_daily_path,
        partitionBy="tenant_id",
    )


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
