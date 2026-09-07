"""Processed Event -> sessionized and product-level fact datasets.

This is a full-snapshot Spark batch job.  It intentionally consumes only
``cleaned_events`` so Raw duplicates cannot leak into downstream facts.

The job restores event order by ``session_id + sequence_no + event_time +
received_at`` and expands ``purchase``/``begin_checkout`` item
arrays into one product row per item.  Event-specific properties stay
available through ``properties_json`` while frequently queried fields are
typed columns.
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
DEFAULT_SECTION_DWELL_PATH = "data/processed/section_dwell_agg"
DEFAULT_CONTENT_INTEREST_PATH = "data/processed/content_interest_fact"
DEFAULT_DIM_PRODUCT_PATH = "data/processed/dim_product"
DEFAULT_DIM_BRAND_PATH = "data/processed/dim_brand"
DEFAULT_PRODUCT_CATALOG_PATH = "batch/ingest/data/products_200.json"
DEFAULT_BEHAVIOR_WEIGHTS_PATH = "frontend/src/types/log.ts"

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
CONTENT_INTEREST_EVENTS = (
    "accordion_toggle",
    "review_filter_apply",
    "text_selection",
    "text_copy",
)


@dataclass(frozen=True)
class DeriveFactsConfig:
    input_path: str = DEFAULT_INPUT_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    section_dwell_path: str = DEFAULT_SECTION_DWELL_PATH
    content_interest_path: str = DEFAULT_CONTENT_INTEREST_PATH
    dim_product_path: str = DEFAULT_DIM_PRODUCT_PATH
    dim_brand_path: str = DEFAULT_DIM_BRAND_PATH
    product_catalog_path: str = DEFAULT_PRODUCT_CATALOG_PATH
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        values = {
            "input_path": self.input_path,
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
            "section_dwell_path": self.section_dwell_path,
            "content_interest_path": self.content_interest_path,
            "dim_product_path": self.dim_product_path,
            "dim_brand_path": self.dim_brand_path,
            "product_catalog_path": self.product_catalog_path,
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
        "--section-dwell-path",
        default=_env("SECTION_DWELL_PATH", DEFAULT_SECTION_DWELL_PATH),
        help="Output path for section_dwell_agg",
    )
    parser.add_argument(
        "--content-interest-path",
        default=_env("CONTENT_INTEREST_PATH", DEFAULT_CONTENT_INTEREST_PATH),
        help="Output path for content_interest_fact",
    )
    parser.add_argument(
        "--dim-product-path",
        default=_env("DIM_PRODUCT_PATH", DEFAULT_DIM_PRODUCT_PATH),
        help="Output path for the seed dim_product projection",
    )
    parser.add_argument(
        "--dim-brand-path",
        default=_env("DIM_BRAND_PATH", DEFAULT_DIM_BRAND_PATH),
        help="Output path for dim_brand (grain=brand_id)",
    )
    parser.add_argument(
        "--product-catalog-path",
        default=_env("PRODUCT_CATALOG_PATH", DEFAULT_PRODUCT_CATALOG_PATH),
        help="Seed product catalog JSON used to build dim_product",
    )
    parser.add_argument(
        "--behavior-weights-path",
        default=_env("BEHAVIOR_WEIGHTS_PATH", DEFAULT_BEHAVIOR_WEIGHTS_PATH),
        help="Execution source for EVENT_WEIGHT and SECTION_DWELL_WEIGHT",
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
        section_dwell_path=args.section_dwell_path,
        content_interest_path=args.content_interest_path,
        dim_product_path=args.dim_product_path,
        dim_brand_path=args.dim_brand_path,
        product_catalog_path=args.product_catalog_path,
        behavior_weights_path=args.behavior_weights_path,
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
        "dwell_ms",
        "co_visible_blocks",
        "action",
        "open",
        "close_reason",
        "vocab_version",
    )
    array_names = ("matched_ingredients", "matched_keywords")
    return StructType(
        [
            *(StructField(name, StringType(), True) for name in scalar_names),
            *(StructField(name, ArrayType(StringType()), True) for name in array_names),
            StructField("items", ArrayType(item_schema), True),
        ]
    )


def _prop(properties: Any, name: str) -> Any:
    return properties.getField(name)


def _typed_properties(cleaned_df: Any) -> Any:
    from pyspark.sql import functions as F

    properties = F.from_json(F.col("properties_json"), _properties_schema())
    return cleaned_df.withColumn("_properties", properties)


def _attach_product_dimension(df: Any, dim_product_df: Any | None) -> Any:
    """Attach a product snapshot while preserving exactly one output row per input row.

    The dimension is collapsed to one deterministic row per ``product_id`` before
    the left join. Conflicting duplicate attributes become NULL and are surfaced by
    the validation job instead of multiplying Fact rows or picking an arbitrary
    brand.
    """

    from pyspark.sql import functions as F

    if dim_product_df is None:
        return df

    base_columns = [name for name in df.columns if name not in {"category_id", "brand_id"}]
    base = df.select(*base_columns)
    dimension_values = dim_product_df.select(
        F.trim(F.col("product_id").cast("string")).alias("_dim_product_id"),
        F.col("category_id").cast("string").alias("_category_id"),
        F.trim(F.col("brand_id").cast("string")).alias("_brand_id"),
    ).where(
        F.col("_dim_product_id").isNotNull()
        & (F.length(F.col("_dim_product_id")) > 0)
    )
    dimension = dimension_values.groupBy("_dim_product_id").agg(
        F.when(
            F.countDistinct("_category_id") <= 1,
            F.first("_category_id", ignorenulls=True),
        ).alias("_dim_category_id"),
        F.when(
            F.countDistinct("_brand_id") <= 1,
            F.first("_brand_id", ignorenulls=True),
        ).alias("_dim_brand_id"),
    )
    joined = base.join(
        dimension,
        base["product_id"] == dimension["_dim_product_id"],
        "left",
    )
    return joined.select(
        *[base[name] for name in base_columns],
        F.col("_dim_category_id").alias("category_id"),
        F.col("_dim_brand_id").alias("brand_id"),
    )


def _sessionized_events(cleaned_df: Any, dim_product_df: Any | None = None) -> Any:
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

    result = properties_df.select(
        "event_id",
        "session_id",
        "page_view_id",
        "event_date_kst",
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
    return _attach_product_dimension(result, dim_product_df)


def _product_event_fact(
    cleaned_df: Any, time_zone: str, dim_product_df: Any | None = None
) -> Any:
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

    if dim_product_df is None:
        return fact.withColumn("category_id", F.lit(None).cast("string")).withColumn(
            "brand_id", F.lit(None).cast("string")
        )
    return _attach_product_dimension(fact, dim_product_df)


def _build_seed_dim_product(catalog_df: Any) -> Any:
    """Project the checked-in seed catalog into the common product dimension.

    Brand-registered products are a separate input owned by the catalog flow.
    Until that input exists, this projection covers the seed catalog only.
    """

    from pyspark.sql import functions as F

    product_id = F.trim(F.col("product_id").cast("string"))
    return (
        catalog_df.select(
            product_id.alias("product_id"),
            F.col("product_name").cast("string").alias("product_name"),
            F.lit("seed_catalog").alias("product_source"),
            F.trim(F.col("brand_id").cast("string")).alias("brand_id"),
            F.trim(F.col("brand_name").cast("string")).alias("brand_name"),
            F.col("primary_category").cast("string").alias("primary_category"),
            F.col("secondary_category").cast("string").alias("secondary_category"),
            F.col("tertiary_category").cast("string").alias("tertiary_category"),
            F.lit(None).cast("string").alias("category_id"),
            F.array(
                F.col("primary_category").cast("string"),
                F.col("secondary_category").cast("string"),
                F.col("tertiary_category").cast("string"),
            ).alias("category_path"),
            F.col("price_usd").cast("decimal(18,2)").alias("base_price"),
            F.lit("USD").alias("currency"),
            F.array().cast("array<string>").alias("skin_type_tags"),
            F.array().cast("array<string>").alias("concern_tags"),
            F.array().cast("array<string>").alias("ingredient_ids"),
            F.lit(0).cast("int").alias("caution_ingredient_count"),
            F.col("rating").cast("double").alias("rating"),
            F.lit("observed").alias("rating_source"),
            F.col("loves_count").cast("long").alias("loves_count"),
            F.lit(None).cast("timestamp").alias("registered_at"),
            F.current_timestamp().alias("updated_at"),
        )
        .where(F.col("product_id").isNotNull() & (F.length(F.col("product_id")) > 0))
        .dropDuplicates(["product_id"])
    )


def _build_dim_brand(dim_product_df: Any) -> Any:
    """Build the analytics brand dimension at grain ``brand_id``.

    Account-to-brand authentication is owned by Backend and deliberately is not
    copied into the DW dimension. Conflicting names resolve deterministically and
    remain detectable from ``dim_product`` by the validation job.
    """

    from pyspark.sql import functions as F

    return (
        dim_product_df.select(
            F.trim(F.col("brand_id").cast("string")).alias("brand_id"),
            F.trim(F.col("brand_name").cast("string")).alias("brand_name"),
        )
        .where(
            F.col("brand_id").isNotNull()
            & (F.length(F.col("brand_id")) > 0)
        )
        .groupBy("brand_id")
        .agg(F.min("brand_name").alias("brand_name"))
        .withColumn("created_at", F.lit(None).cast("timestamp"))
        .withColumn("updated_at", F.current_timestamp())
    )


CONTENT_GROUP_COLUMNS = (
    "event_date_kst",
    "session_id",
    "page_view_id",
    "product_id",
    "section_id",
    "content_kind",
    "content_ref",
    "user_id",
    "persona_id",
    "scenario_id",
    "simulation_run_id",
    "generator_type",
    "actor_type",
    "source",
)


def _null_safe_left_join(
    left_df: Any,
    right_df: Any,
    key_columns: tuple[str, ...] | list[str],
    value_columns: tuple[str, ...] | list[str],
) -> Any:
    """Left-join aggregate values while matching nullable grain columns."""

    from pyspark.sql import functions as F

    left = left_df.alias("_left")
    right = right_df.select(*key_columns, *value_columns).alias("_right")
    condition = F.lit(True)
    for name in key_columns:
        condition = condition & F.col(f"_left.{name}").eqNullSafe(
            F.col(f"_right.{name}")
        )
    joined = left.join(right, condition, "left")
    return joined.select(
        *[F.col(f"_left.{name}") for name in left_df.columns],
        *[F.col(f"_right.{name}") for name in value_columns],
    )


def _content_events(cleaned_df: Any, event_names: tuple[str, ...]) -> Any:
    from pyspark.sql import functions as F

    typed = _typed_properties(cleaned_df).where(
        F.col("event_name").isin(*event_names)
    )
    return typed.select(
        "event_date_kst",
        "session_id",
        "page_view_id",
        "product_id",
        _prop(F.col("_properties"), "section_id").alias("section_id"),
        _prop(F.col("_properties"), "content_kind").alias("content_kind"),
        _prop(F.col("_properties"), "content_ref").alias("content_ref"),
        "user_id",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "event_name",
        "event_time",
        "actor_type",
        "source",
        _prop(F.col("_properties"), "dwell_ms").cast("long").alias("dwell_ms"),
        _prop(F.col("_properties"), "co_visible_blocks")
        .cast("int")
        .alias("co_visible_blocks"),
        _prop(F.col("_properties"), "action").alias("action"),
        _prop(F.col("_properties"), "open").alias("open"),
        _prop(F.col("_properties"), "matched_ingredients").alias(
            "_matched_ingredients"
        ),
        _prop(F.col("_properties"), "matched_keywords").alias("_matched_keywords"),
        _prop(F.col("_properties"), "vocab_version").alias("vocab_version"),
    )


def _section_dwell_agg(
    cleaned_df: Any, dim_product_df: Any | None = None
) -> Any:
    from pyspark.sql import functions as F

    events = _content_events(cleaned_df, ("section_dwell",)).withColumn(
        "_dwell_ms", F.col("dwell_ms").cast("long")
    )
    grouped = events.groupBy(*CONTENT_GROUP_COLUMNS).agg(
        F.coalesce(F.sum("_dwell_ms"), F.lit(0)).cast("long").alias("dwell_ms_sum"),
        F.count(F.lit(1)).cast("long").alias("dwell_event_count"),
        F.max("co_visible_blocks").cast("int").alias("max_co_visible_blocks"),
        F.min("event_time").alias("first_seen_at"),
        F.max("event_time").alias("last_seen_at"),
        F.current_timestamp().alias("processed_at"),
    )
    return _attach_product_dimension(
        grouped.withColumn("category_id", F.lit(None).cast("string")).withColumn(
            "brand_id", F.lit(None).cast("string")
        ),
        dim_product_df,
    )


def _create_map(values: dict[str, float]) -> Any:
    from pyspark.sql import functions as F

    if not values:
        raise ValueError("behavior weight table must not be empty")
    entries: list[Any] = []
    for name, value in values.items():
        entries.extend((F.lit(name), F.lit(float(value))))
    return F.create_map(*entries)


def _load_behavior_weights(path: str | None = None) -> dict[str, Any]:
    try:
        from .behavior_weights import load
    except ImportError:
        from behavior_weights import load

    return load(path)


def _content_interest_fact(
    cleaned_df: Any,
    section_dwell_df: Any,
    weights: dict[str, Any],
    dim_product_df: Any | None = None,
) -> Any:
    from pyspark.sql import functions as F

    event_names = ("section_view",) + CONTENT_INTEREST_EVENTS
    events = _content_events(cleaned_df, event_names)
    event_keys = events.select(*CONTENT_GROUP_COLUMNS)
    section_keys = section_dwell_df.select(*CONTENT_GROUP_COLUMNS)
    keys = event_keys.unionByName(section_keys).distinct()

    expands = (F.col("event_name") == F.lit("accordion_toggle")) & (
        (F.col("action") == F.lit("expand"))
        | (F.col("open") == F.lit("true"))
    )
    counts = events.groupBy(*CONTENT_GROUP_COLUMNS).agg(
        F.sum(
            F.when(F.col("event_name") == F.lit("section_view"), 1).otherwise(0)
        )
        .cast("long")
        .alias("view_count"),
        F.sum(F.when(expands, 1).otherwise(0)).cast("long").alias(
            "accordion_expand_count"
        ),
        F.sum(
            F.when(F.col("event_name") == F.lit("review_filter_apply"), 1).otherwise(0)
        )
        .cast("long")
        .alias("review_filter_count"),
        F.sum(
            F.when(F.col("event_name") == F.lit("text_selection"), 1).otherwise(0)
        )
        .cast("long")
        .alias("text_select_count"),
        F.sum(
            F.when(F.col("event_name") == F.lit("text_copy"), 1).otherwise(0)
        )
        .cast("long")
        .alias("text_copy_count"),
        F.array_distinct(
            F.flatten(
                F.collect_list(
                    F.coalesce(
                        F.col("_matched_ingredients"),
                        F.array().cast("array<string>"),
                    )
                )
            )
        ).alias("matched_ingredients"),
        F.array_distinct(
            F.flatten(
                F.collect_list(
                    F.coalesce(
                        F.col("_matched_keywords"),
                        F.array().cast("array<string>"),
                    )
                )
            )
        ).alias("matched_keywords"),
        F.first("vocab_version", ignorenulls=True).alias("vocab_version"),
    )

    result = _null_safe_left_join(
        keys,
        section_dwell_df,
        CONTENT_GROUP_COLUMNS,
        ("dwell_ms_sum",),
    )
    result = _null_safe_left_join(
        result,
        counts,
        CONTENT_GROUP_COLUMNS,
        (
            "view_count",
            "accordion_expand_count",
            "review_filter_count",
            "text_select_count",
            "text_copy_count",
            "matched_ingredients",
            "matched_keywords",
            "vocab_version",
        ),
    )
    result = (
        result.withColumn("view_count", F.coalesce(F.col("view_count"), F.lit(0)).cast("long"))
        .withColumn(
            "dwell_ms_sum", F.coalesce(F.col("dwell_ms_sum"), F.lit(0)).cast("long")
        )
        .withColumn(
            "accordion_expand_count",
            F.coalesce(F.col("accordion_expand_count"), F.lit(0)).cast("long"),
        )
        .withColumn(
            "review_filter_count",
            F.coalesce(F.col("review_filter_count"), F.lit(0)).cast("long"),
        )
        .withColumn(
            "text_select_count",
            F.coalesce(F.col("text_select_count"), F.lit(0)).cast("long"),
        )
        .withColumn(
            "text_copy_count",
            F.coalesce(F.col("text_copy_count"), F.lit(0)).cast("long"),
        )
        .withColumn(
            "matched_ingredients",
            F.coalesce(
                F.col("matched_ingredients"), F.array().cast("array<string>")
            ),
        )
        .withColumn(
            "matched_keywords",
            F.coalesce(F.col("matched_keywords"), F.array().cast("array<string>")),
        )
    )

    event_weights = weights["event"]
    section_weights = weights["section"]
    missing_events = set(CONTENT_INTEREST_EVENTS) - set(event_weights)
    if missing_events:
        raise ValueError(f"content interest weights missing: {sorted(missing_events)}")

    section_map = _create_map(section_weights)
    resolved_section_weight = F.when(
        F.col("section_id").isNull(), F.lit(1.0)
    ).otherwise(
        F.coalesce(
            F.element_at(section_map, F.col("section_id")),
            F.lit(1.0),
        )
    )
    unknown_section = F.col("section_id").isNotNull() & F.element_at(
        section_map, F.col("section_id")
    ).isNull()
    event_score = F.lit(0.0)
    event_count_columns = {
        "accordion_toggle": "accordion_expand_count",
        "review_filter_apply": "review_filter_count",
        "text_selection": "text_select_count",
        "text_copy": "text_copy_count",
    }
    for event_name in CONTENT_INTEREST_EVENTS:
        event_score = event_score + (
            F.col(event_count_columns[event_name])
            * F.lit(float(event_weights[event_name]))
        )
    quality_flags = F.when(
        F.col("section_id").isNull(),
        F.array(F.lit("section_id_null_weight_defaulted")),
    ).when(
        unknown_section,
        F.array(F.lit("unknown_section_weight_defaulted")),
    ).otherwise(F.array().cast("array<string>"))

    result = (
        result.withColumn(
            "content_interest_score",
            resolved_section_weight
            * (
                F.log1p(F.col("dwell_ms_sum").cast("double") / F.lit(1000.0))
                + event_score
            ),
        )
        .withColumn("quality_flags", quality_flags)
        .withColumn("processed_at", F.current_timestamp())
        .withColumn("category_id", F.lit(None).cast("string"))
        .withColumn("brand_id", F.lit(None).cast("string"))
    )
    return _attach_product_dimension(result, dim_product_df)


def build_derived_frames(
    cleaned_df: Any,
    time_zone: str,
    dim_product_df: Any | None = None,
    weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    section_dwell = _section_dwell_agg(cleaned_df, dim_product_df)
    if weights is None:
        weights = _load_behavior_weights()
    return {
        "sessionized_events": _sessionized_events(cleaned_df, dim_product_df),
        "product_event_fact": _product_event_fact(
            cleaned_df, time_zone, dim_product_df
        ),
        "section_dwell_agg": section_dwell,
        "content_interest_fact": _content_interest_fact(
            cleaned_df, section_dwell, weights, dim_product_df
        ),
    }


def run(spark: Any, config: DeriveFactsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    catalog_df = spark.read.option("multiLine", "true").json(
        config.product_catalog_path
    )
    dim_product = _build_seed_dim_product(catalog_df)
    dim_brand = _build_dim_brand(dim_product)
    weights = _load_behavior_weights(config.behavior_weights_path)
    frames = build_derived_frames(
        spark.read.option("mergeSchema", "true").parquet(config.input_path),
        config.time_zone,
        dim_product,
        weights,
    )
    frames["sessionized_events"].write.mode("overwrite").parquet(
        config.sessionized_path,
        partitionBy="event_date_kst",
    )
    frames["product_event_fact"].write.mode("overwrite").parquet(
        config.product_fact_path,
        partitionBy="event_date_kst",
    )
    frames["section_dwell_agg"].write.mode("overwrite").parquet(
        config.section_dwell_path,
        partitionBy="event_date_kst",
    )
    frames["content_interest_fact"].write.mode("overwrite").parquet(
        config.content_interest_path,
        partitionBy="event_date_kst",
    )
    dim_product.write.mode("overwrite").parquet(
        config.dim_product_path,
    )
    dim_brand.write.mode("overwrite").parquet(
        config.dim_brand_path,
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
