"""Processed Event -> sessionized and product-level fact datasets.

This is a full-snapshot Spark batch job.  It intentionally consumes only
``cleaned_events`` so Raw duplicates cannot leak into downstream facts.

The job restores event order by ``session_id + sequence_no + event_time +
received_at`` and expands ``purchase``/``begin_checkout`` item arrays into
one product row per item.  Event-specific properties stay available through
``properties_json`` while frequently queried fields are typed columns.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_INPUT_PATH = "data/processed/cleaned_events"
DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_TIME_ZONE = "Asia/Seoul"

PRODUCT_EVENT_NAMES = (
    "product_view",
    "product_impression",
    "product_click",
    "recommendation_impression",
    "recommendation_click",
    "wishlist_toggle",
    "add_to_cart",
    "remove_from_cart",
    "quick_look",
    "quick_look_close",
    "begin_checkout",
    "purchase",
    "media_view",
    "variant_select",
    "quantity_change",
)

ITEM_EVENT_NAMES = ("begin_checkout", "purchase")


@dataclass(frozen=True)
class DeriveFactsConfig:
    input_path: str = DEFAULT_INPUT_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        values = {
            "input_path": self.input_path,
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
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
        description="Build sessionized_events and product_event_fact from cleaned_events."
    )
    parser.add_argument(
        "--input-path",
        default=_env("CLEANED_EVENTS_PATH", DEFAULT_INPUT_PATH),
        help="Q2 cleaned_events Parquet path",
    )
    parser.add_argument(
        "--sessionized-path",
        default=_env("SESSIONIZED_EVENTS_PATH", DEFAULT_SESSIONIZED_PATH),
        help="Output path for sessionized_events",
    )
    parser.add_argument(
        "--product-fact-path",
        default=_env("PRODUCT_EVENT_FACT_PATH", DEFAULT_PRODUCT_FACT_PATH),
        help="Output path for product_event_fact",
    )
    parser.add_argument(
        "--time-zone",
        default=_env("ANALYTICS_TIME_ZONE", DEFAULT_TIME_ZONE),
        help="Time zone used for KST date/hour columns",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> DeriveFactsConfig:
    args = build_parser().parse_args(argv)
    return DeriveFactsConfig(
        input_path=args.input_path,
        sessionized_path=args.sessionized_path,
        product_fact_path=args.product_fact_path,
        time_zone=args.time_zone,
    )


def _properties_schema() -> Any:
    from pyspark.sql.types import ArrayType, StringType, StructField, StructType

    item_schema = StructType(
        [
            StructField("product_id", StringType(), True),
            StructField("sku_id", StringType(), True),
            StructField("quantity", StringType(), True),
            StructField("unit_price", StringType(), True),
            StructField("currency", StringType(), True),
        ]
    )
    scalar_names = (
        "context_product_id",
        "section_id",
        "content_kind",
        "content_ref",
        "position",
        "sku_id",
        "list_id",
        "entry_source",
        "recommendation_id",
        "algorithm",
        "search_id",
        "quantity",
        "unit_price",
        "price_usd",
        "order_value",
        "cart_value",
        "cart_size_after",
        "currency",
        "cart_id",
        "order_id",
        "variants_viewed",
        "added_to_cart",
        "wishlisted",
    )
    return StructType(
        [
            *(StructField(name, StringType(), True) for name in scalar_names),
            StructField("items", ArrayType(item_schema), True),
        ]
    )


def _prop(properties: Any, name: str) -> Any:
    return properties.getField(name)


def _typed_properties(cleaned_df: Any) -> Any:
    from pyspark.sql import functions as F

    properties = F.from_json(F.col("properties_json"), _properties_schema())
    return cleaned_df.withColumn("_properties", properties)


def _sessionized_events(cleaned_df: Any) -> Any:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    properties_df = _typed_properties(cleaned_df)
    session_window = Window.partitionBy("session_id").orderBy(
        F.col("sequence_no").asc(),
        F.col("event_time").asc(),
        F.col("received_at").asc(),
        F.col("event_id").asc(),
    )
    previous_sequence = F.lag("sequence_no").over(session_window)
    previous_event = F.lag("event_name").over(session_window)
    next_event = F.lead("event_name").over(session_window)

    return properties_df.select(
        "event_id",
        "session_id",
        "page_view_id",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "product_id",
        _prop(F.col("_properties"), "context_product_id").alias("context_product_id"),
        F.lit(None).cast("string").alias("category_id"),
        F.lit(None).cast("string").alias("brand_id"),
        "event_name",
        "event_time",
        "received_at",
        "processed_at",
        "sequence_no",
        F.row_number().over(session_window).alias("event_order"),
        previous_event.alias("prev_event_name"),
        next_event.alias("next_event_name"),
        # A full snapshot has no Structured Streaming watermark.  Keep the
        # field nullable instead of pretending that batch order is a watermark
        # lateness decision.
        F.lit(None).cast("boolean").alias("is_late_event"),
        F.when(
            previous_sequence.isNotNull()
            & ((F.col("sequence_no") - previous_sequence) > 1),
            F.lit(True),
        )
        .otherwise(F.lit(False))
        .alias("has_sequence_gap"),
        "actor_type",
        "source",
        "environment",
        "properties_json",
    )


def _product_event_fact(cleaned_df: Any, time_zone: str) -> Any:
    from pyspark.sql import functions as F

    base = _typed_properties(cleaned_df).where(
        F.col("event_name").isin(*PRODUCT_EVENT_NAMES)
    )
    item_events = F.col("event_name").isin(*ITEM_EVENT_NAMES)
    exploded = base.select(
        "*",
        F.posexplode_outer(F.col("_properties").getField("items")).alias(
            "_item_index", "_item"
        ),
    )

    item_product_id = F.col("_item").getField("product_id")
    item_sku_id = F.col("_item").getField("sku_id")
    item_quantity = F.col("_item").getField("quantity").cast("int")
    item_unit_price = F.col("_item").getField("unit_price").cast("decimal(18,2)")
    property_unit_price = F.coalesce(
        _prop(F.col("_properties"), "unit_price"),
        _prop(F.col("_properties"), "price_usd"),
    ).cast("decimal(18,2)")
    quantity = F.when(item_events, item_quantity).otherwise(
        _prop(F.col("_properties"), "quantity").cast("int")
    )
    unit_price = F.when(item_events, item_unit_price).otherwise(property_unit_price)
    product_id = F.when(item_events, item_product_id).otherwise(F.col("product_id"))
    item_index = F.when(item_events, F.col("_item_index")).otherwise(F.lit(0)).cast("int")

    fact = exploded.select(
        "event_id",
        F.to_date(F.col("event_time")).alias("event_date"),
        F.date_trunc("hour", F.col("event_time")).alias("event_hour"),
        F.col("event_date_kst"),
        F.from_utc_timestamp(
            F.date_trunc("hour", F.col("event_time")), time_zone
        ).alias("event_hour_kst"),
        "event_time",
        "processed_at",
        "event_name",
        "intent",
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "session_id",
        "page_view_id",
        item_index.alias("item_index"),
        product_id.alias("product_id"),
        _prop(F.col("_properties"), "context_product_id").alias("context_product_id"),
        F.lit(None).cast("string").alias("category_id"),
        F.lit(None).cast("string").alias("brand_id"),
        F.when(item_events, item_sku_id)
        .otherwise(_prop(F.col("_properties"), "sku_id"))
        .alias("sku_id"),
        _prop(F.col("_properties"), "list_id").alias("list_id"),
        _prop(F.col("_properties"), "entry_source").alias("entry_source"),
        _prop(F.col("_properties"), "recommendation_id").alias(
            "recommendation_id"
        ),
        _prop(F.col("_properties"), "algorithm").alias("algorithm"),
        _prop(F.col("_properties"), "search_id").alias("search_id"),
        _prop(F.col("_properties"), "section_id").alias("section_id"),
        _prop(F.col("_properties"), "position").cast("int").alias("position"),
        quantity.alias("quantity"),
        F.when(item_events, quantity).alias("purchase_quantity"),
        _prop(F.col("_properties"), "cart_size_after")
        .cast("int")
        .alias("cart_size_after"),
        unit_price.alias("unit_price"),
        _prop(F.col("_properties"), "order_value")
        .cast("decimal(18,2)")
        .alias("order_value"),
        F.when(
            F.col("event_name") == F.lit("purchase"),
            (quantity * unit_price).cast("decimal(18,2)"),
        ).alias("item_revenue"),
        _prop(F.col("_properties"), "cart_value")
        .cast("decimal(18,2)")
        .alias("cart_value"),
        _prop(F.col("_properties"), "currency").alias("currency"),
        _prop(F.col("_properties"), "cart_id").alias("cart_id"),
        _prop(F.col("_properties"), "order_id").alias("order_id"),
        _prop(F.col("_properties"), "variants_viewed")
        .cast("int")
        .alias("variants_viewed"),
        _prop(F.col("_properties"), "added_to_cart")
        .cast("boolean")
        .alias("added_to_cart"),
        _prop(F.col("_properties"), "wishlisted")
        .cast("boolean")
        .alias("wishlisted"),
        "actor_type",
        "source",
    ).where(F.col("product_id").isNotNull() & (F.length(F.trim(F.col("product_id"))) > 0))

    return fact


def build_derived_frames(cleaned_df: Any, time_zone: str) -> dict[str, Any]:
    return {
        "sessionized_events": _sessionized_events(cleaned_df),
        "product_event_fact": _product_event_fact(cleaned_df, time_zone),
    }


def run(spark: Any, config: DeriveFactsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    frames = build_derived_frames(spark.read.parquet(config.input_path), config.time_zone)
    frames["sessionized_events"].write.mode("overwrite").parquet(
        config.sessionized_path
    )
    frames["product_event_fact"].write.mode("overwrite").parquet(
        config.product_fact_path
    )


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("derive-analytics-facts")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        run(spark, config)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
