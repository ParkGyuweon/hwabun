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
import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_INPUT_PATH = "data/processed/cleaned_events"
DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_PURCHASE_FACT_PATH = "data/processed/purchase_fact"
DEFAULT_PURCHASE_REASON_FACT_PATH = "data/processed/purchase_reason_fact"
DEFAULT_REVIEW_EVENT_FACT_PATH = "data/processed/review_event_fact"
DEFAULT_TIME_ZONE = "Asia/Seoul"
DEFAULT_SECTION_DWELL_PATH = "data/processed/section_dwell_agg"
DEFAULT_CONTENT_INTEREST_PATH = "data/processed/content_interest_fact"
DEFAULT_DIM_PRODUCT_PATH = "data/processed/dim_product"
DEFAULT_DIM_BRAND_PATH = "data/processed/dim_brand"
DEFAULT_PRODUCT_CATALOG_PATH = "batch/ingest/data/products_200.json"
DEFAULT_REGISTERED_PRODUCT_PATH = (
    "batch/ingest/data/serving/registered_products.jsonl"
)
DEFAULT_BEHAVIOR_WEIGHTS_PATH = "frontend/src/types/log.ts"

PRODUCT_EVENT_NAMES = (
    "product_view",
    "product_impression",
    "product_click",
    "recommendation_impression",
    "recommendation_click",
    "banner_impression",
    "banner_click",
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
REVIEW_EVENT_NAMES = (
    "section_view",
    "section_dwell",
    "review_expand",
    "review_filter_apply",
)
REVIEW_CONTENT_KINDS = ("user_review", "review_stats", "review_filter")
REVIEW_EXPAND_TARGETS = ("review_text", "jump_to_reviews")


@dataclass(frozen=True)
class DeriveFactsConfig:
    input_path: str = DEFAULT_INPUT_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    purchase_fact_path: str = DEFAULT_PURCHASE_FACT_PATH
    purchase_reason_fact_path: str = DEFAULT_PURCHASE_REASON_FACT_PATH
    review_event_fact_path: str = DEFAULT_REVIEW_EVENT_FACT_PATH
    section_dwell_path: str = DEFAULT_SECTION_DWELL_PATH
    content_interest_path: str = DEFAULT_CONTENT_INTEREST_PATH
    dim_product_path: str = DEFAULT_DIM_PRODUCT_PATH
    dim_brand_path: str = DEFAULT_DIM_BRAND_PATH
    product_catalog_path: str = DEFAULT_PRODUCT_CATALOG_PATH
    registered_product_path: str = DEFAULT_REGISTERED_PRODUCT_PATH
    registered_product_brand_path: str | None = None
    behavior_weights_path: str = DEFAULT_BEHAVIOR_WEIGHTS_PATH
    commons_hash_salt: str = ""
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        values = {
            "input_path": self.input_path,
            "sessionized_path": self.sessionized_path,
            "product_fact_path": self.product_fact_path,
            "purchase_fact_path": self.purchase_fact_path,
            "purchase_reason_fact_path": self.purchase_reason_fact_path,
            "review_event_fact_path": self.review_event_fact_path,
            "section_dwell_path": self.section_dwell_path,
            "content_interest_path": self.content_interest_path,
            "dim_product_path": self.dim_product_path,
            "dim_brand_path": self.dim_brand_path,
            "product_catalog_path": self.product_catalog_path,
            "registered_product_path": self.registered_product_path,
            "behavior_weights_path": self.behavior_weights_path,
            "time_zone": self.time_zone,
        }
        for name, value in values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not self.commons_hash_salt.strip():
            # 소금 없는 해시를 조용히 만들면 보호가 있는 것처럼 보인다
            # (dw-schema.md §2.5.1 R5).
            raise ValueError(
                "commons_hash_salt must be set — COMMONS_HASH_SALT 환경 변수나 "
                "--commons-hash-salt 로 준다. 저장소에 두지 않는다"
            )


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
        "--purchase-fact-path",
        default=_env("PURCHASE_FACT_PATH", DEFAULT_PURCHASE_FACT_PATH),
        help="Output path for purchase_fact",
    )
    parser.add_argument(
        "--purchase-reason-fact-path",
        default=_env("PURCHASE_REASON_FACT_PATH", DEFAULT_PURCHASE_REASON_FACT_PATH),
        help="Output path for purchase_reason_fact",
    )
    parser.add_argument(
        "--review-event-fact-path",
        default=_env("REVIEW_EVENT_FACT_PATH", DEFAULT_REVIEW_EVENT_FACT_PATH),
        help="Output path for review_event_fact",
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
        "--commons-hash-salt",
        default=_env("COMMONS_HASH_SALT", ""),
        help="brand_hash 소금값. 저장소에 두지 않고 환경 변수로 준다 (dw-schema §2.5.1 R5)",
    )
    parser.add_argument(
        "--product-catalog-path",
        default=_env("PRODUCT_CATALOG_PATH", DEFAULT_PRODUCT_CATALOG_PATH),
        help="Seed product catalog JSON used to build dim_product",
    )
    parser.add_argument(
        "--registered-product-path",
        default=_env("REGISTERED_PRODUCT_PATH", DEFAULT_REGISTERED_PRODUCT_PATH),
        help="Append-only registered product JSONL used to extend dim_product",
    )
    parser.add_argument(
        "--registered-product-brand-path",
        default=os.getenv("REGISTERED_PRODUCT_BRAND_PATH"),
        help=(
            "Optional ACTIVE shop product export (JSONL with product_id and brand_id); "
            "its authoritative brand_id overrides the registered product value"
        ),
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
        purchase_fact_path=args.purchase_fact_path,
        purchase_reason_fact_path=args.purchase_reason_fact_path,
        review_event_fact_path=args.review_event_fact_path,
        section_dwell_path=args.section_dwell_path,
        content_interest_path=args.content_interest_path,
        dim_product_path=args.dim_product_path,
        dim_brand_path=args.dim_brand_path,
        product_catalog_path=args.product_catalog_path,
        registered_product_path=args.registered_product_path,
        registered_product_brand_path=args.registered_product_brand_path,
        commons_hash_salt=args.commons_hash_salt,
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
        "paid_value",
        "payment_method",
        "order_channel",
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
        "navigation_source",
        "vocab_version",
        "banner_type",
        "banner_value",
        "banner_slot",
        "trait_source",
        "policy_version",
        "primary_reason",
        "free_text_kind",
        "skipped",
        "target",
        "review_id",
        "revealed_count",
        "filter",
        "sort",
        "result_count",
        "persona_skin_type",
        "persona_skin_tone",
    )
    array_names = ("matched_ingredients", "matched_keywords", "reasons")
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
        "identity_scope",
        "is_seeded",
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
        "identity_scope",
        "is_seeded",
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
        _prop(F.col("_properties"), "banner_type").alias("banner_type"),
        _prop(F.col("_properties"), "banner_value").alias("banner_value"),
        _prop(F.col("_properties"), "banner_slot").cast("int").alias("banner_slot"),
        _prop(F.col("_properties"), "trait_source").alias("trait_source"),
        _prop(F.col("_properties"), "policy_version").alias("policy_version"),
        quantity.alias("quantity"),
        F.when(item_events, quantity).alias("purchase_quantity"),
        _prop(F.col("_properties"), "cart_size_after")
        .cast("int")
        .alias("cart_size_after"),
        unit_price.alias("unit_price"),
        _prop(F.col("_properties"), "order_value")
        .cast("decimal(18,2)")
        .alias("order_value"),
        _prop(F.col("_properties"), "paid_value")
        .cast("decimal(18,2)")
        .alias("paid_value"),
        _prop(F.col("_properties"), "payment_method").alias("payment_method"),
        _prop(F.col("_properties"), "order_channel").alias("order_channel"),
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
        # 퀵룩을 왜 닫았는지. "상세로 넘어갔다"(open_detail)를 세려면 필요하다
        # (dw-schema §4.1 quick_look_close_open_detail_count).
        _prop(F.col("_properties"), "close_reason").alias("close_reason"),
        # 찜은 토글이라 추가와 해제가 같은 Event 다. 가르지 않으면
        # wishlist_count 가 "관심"이 아니라 "누른 횟수"가 된다 (§4.1).
        _prop(F.col("_properties"), "action").alias("action"),
        # 뒤로가기로 돌아오면 프론트가 product_view 를 다시 낸다
        # (navigation_source="history_back", 프론트 확인 2026-09-17).
        # 새 진입이 아니라 재조회라 건수 기준 집계에서 빼야 한다 (§4.1).
        _prop(F.col("_properties"), "navigation_source").alias("navigation_source"),
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


def _purchase_fact(product_event_fact_df: Any) -> Any:
    """Project purchase item rows without turning behavior revenue into finance truth.

    ``paid_value`` · ``payment_method`` · ``order_channel`` 은 주문 단위 값이라
    한 주문의 상품 row 마다 같은 값이 반복된다. 합산하려면 ``order_id`` 로 먼저
    접어야 한다 — 그냥 더하면 상품 수만큼 부풀어 오른다.

    ``pg_provider`` · ``payment_id`` · ``paid_at`` 은 Fact 로 내리지 않는다.
    PG 대사(對査)용 식별자라 행동 집계에 쓰는 축이 아니고, 필요하면
    ``cleaned_events.properties`` 에 그대로 남아 있다.
    """

    from pyspark.sql import functions as F

    return product_event_fact_df.where(F.col("event_name") == "purchase").select(
        "order_id",
        "product_id",
        "event_id",
        "event_date_kst",
        "event_time",
        "processed_at",
        "user_id",
        "identity_scope",
        "is_seeded",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "session_id",
        "category_id",
        "brand_id",
        "sku_id",
        F.col("purchase_quantity").alias("quantity"),
        "unit_price",
        "item_revenue",
        "order_value",
        "paid_value",
        "payment_method",
        "order_channel",
        "currency",
        "actor_type",
        "source",
    )


def _purchase_reason_fact(cleaned_df: Any) -> Any:
    """Expand declared purchase reasons and preserve skipped surveys as one NULL row."""

    from pyspark.sql import functions as F

    events = _typed_properties(cleaned_df).where(
        F.col("event_name") == "purchase_reason_select"
    )
    exploded = events.select(
        "*",
        F.posexplode_outer(_prop(F.col("_properties"), "reasons")).alias(
            "_reason_index", "_reason"
        ),
    )
    reason = F.trim(F.col("_reason"))
    primary_reason = F.trim(_prop(F.col("_properties"), "primary_reason"))
    return exploded.select(
        _prop(F.col("_properties"), "order_id").alias("order_id"),
        F.when(F.length(reason) > 0, reason).alias("reason"),
        "event_id",
        "event_date_kst",
        "event_time",
        "processed_at",
        "user_id",
        "identity_scope",
        "is_seeded",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "session_id",
        F.coalesce(reason == primary_reason, F.lit(False)).alias("is_primary"),
        F.when(F.col("_reason_index").isNotNull(), F.col("_reason_index") + 1)
        .cast("int")
        .alias("reason_rank"),
        _prop(F.col("_properties"), "free_text_kind").alias("free_text_kind"),
        F.coalesce(
            _prop(F.col("_properties"), "skipped").cast("boolean"), F.lit(False)
        ).alias("skipped"),
        "actor_type",
        "source",
    )


def _review_event_fact(
    cleaned_df: Any, dim_product_df: Any | None = None
) -> Any:
    """Keep typed review interactions while excluding ingredient-only expands."""

    from pyspark.sql import functions as F

    events = _typed_properties(cleaned_df)
    properties = F.col("_properties")
    event_name = F.col("event_name")
    section_id = _prop(properties, "section_id")
    content_kind = _prop(properties, "content_kind")
    target = _prop(properties, "target")
    is_review_event = event_name.isin(*REVIEW_EVENT_NAMES) & (
        (event_name == "review_filter_apply")
        | ((event_name == "review_expand") & target.isin(*REVIEW_EXPAND_TARGETS))
        | (
            event_name.isin("section_view", "section_dwell")
            & (
                (section_id == "reviews")
                | content_kind.isin(*REVIEW_CONTENT_KINDS)
            )
        )
    )
    fact = events.where(is_review_event).select(
        "event_id",
        "event_date_kst",
        "event_time",
        "processed_at",
        "event_name",
        "intent",
        "user_id",
        "identity_scope",
        "persona_id",
        "scenario_id",
        "simulation_run_id",
        "generator_type",
        "session_id",
        "page_view_id",
        "product_id",
        F.lit(None).cast("string").alias("category_id"),
        F.lit(None).cast("string").alias("brand_id"),
        section_id.alias("section_id"),
        content_kind.alias("content_kind"),
        _prop(properties, "review_id").alias("review_id"),
        target.alias("target"),
        _prop(properties, "revealed_count").cast("int").alias("revealed_count"),
        _prop(properties, "filter").alias("filter"),
        _prop(properties, "sort").alias("sort"),
        _prop(properties, "result_count").cast("int").alias("result_count"),
        _prop(properties, "persona_skin_type").alias("persona_skin_type"),
        _prop(properties, "persona_skin_tone").alias("persona_skin_tone"),
        _prop(properties, "dwell_ms").cast("long").alias("dwell_ms"),
        "actor_type",
        "source",
    ).where(
        F.col("product_id").isNotNull()
        & (F.length(F.trim(F.col("product_id"))) > 0)
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
            _base_price_krw(
                F.col("price_krw") if "price_krw" in catalog_df.columns else None,
                F.col("price_usd"),
            ).alias("base_price"),
            F.col("price_usd").cast("decimal(18,2)").alias("source_price_usd"),
            F.lit("KRW").alias("currency"),
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


# 가격 정본은 원화다. 추천 어휘집 0.7 의 price_bin 경계가 원화라
# 카탈로그도 같은 단위여야 Mart 가 환율을 다시 들고 있지 않아도 된다.
# 규칙은 ``batch/jobs/product_encoder.price_krw_of`` 와 같아야 한다 — 두 곳이
# 갈리면 같은 상품이 추천과 대시보드에서 다른 가격대로 잡힌다.
USD_KRW_SOURCE = 1340.86
KRW_ROUNDING = 100


def _base_price_krw(krw_column: Any | None, usd_column: Any) -> Any:
    """``price_krw`` 가 정본. 없으면 원천 환율로 환산하고 100원 단위로 반올림한다.

    ``krw_column`` 이 ``None`` 인 경우는 그 키가 아예 없는 옛 형식이다 (시연 시드·
    테스트 픽스처). 반올림 단위까지 ``products-ko.json`` 의 표시 가격과 같아야
    화면과 Mart 의 가격대가 어긋나지 않는다.
    """

    from pyspark.sql import functions as F

    converted = (
        F.round(usd_column.cast("double") * F.lit(USD_KRW_SOURCE) / F.lit(KRW_ROUNDING))
        * F.lit(KRW_ROUNDING)
    ).cast("decimal(18,2)")
    if krw_column is None:
        return converted
    return F.coalesce(krw_column.cast("decimal(18,2)"), converted)


def _active_registered_product_records(path: str) -> list[dict[str, Any]]:
    """Return the last active record for each product in an append-only registry.

    The recommendation registry uses a final ``_op=deactivate`` row as a tombstone.
    Reading it line by line keeps this control input bounded and preserves its
    last-write-wins semantics without relying on Spark input partition ordering.
    """

    latest: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid registered product JSON at {path}:{line_number}: {exc}"
                ) from exc
            product_id = record.get("product_id")
            if not isinstance(product_id, str) or not product_id.strip():
                raise ValueError(
                    f"missing product_id in registered product at {path}:{line_number}"
                )
            latest[product_id.strip()] = record
    return [
        record
        for record in latest.values()
        if record.get("_op") != "deactivate"
    ]


def _build_registered_dim_product(
    registered_df: Any, product_brand_df: Any | None = None
) -> Any:
    """Project ACTIVE registered products using authoritative brand IDs only."""

    from pyspark.sql import functions as F

    registered = registered_df.alias("registered")
    if product_brand_df is not None:
        product_brand = (
            product_brand_df.select(
                F.trim(F.col("product_id").cast("string")).alias(
                    "_mapped_product_id"
                ),
                F.trim(F.col("brand_id").cast("string")).alias("_mapped_brand_id"),
            )
            .where(
                F.col("_mapped_product_id").isNotNull()
                & (F.length(F.col("_mapped_product_id")) > 0)
                & F.col("_mapped_brand_id").isNotNull()
                & (F.length(F.col("_mapped_brand_id")) > 0)
            )
            .groupBy("_mapped_product_id")
            .agg(
                F.when(
                    F.countDistinct("_mapped_brand_id") == 1,
                    F.min("_mapped_brand_id"),
                ).alias("_mapped_brand_id")
            )
        )
        registered = registered.join(
            product_brand,
            F.trim(F.col("registered.product_id").cast("string"))
            == F.col("_mapped_product_id"),
            "left",
        )
        mapped_brand_id = F.col("_mapped_brand_id")
    else:
        mapped_brand_id = F.lit(None).cast("string")

    product_id = F.trim(F.col("registered.product_id").cast("string"))
    source_brand_id = F.trim(F.col("registered.brand_id").cast("string"))
    brand_id = F.coalesce(
        mapped_brand_id, F.when(F.length(source_brand_id) > 0, source_brand_id)
    )
    return (
        registered.select(
            product_id.alias("product_id"),
            F.col("registered.product_name").cast("string").alias("product_name"),
            F.lit("brand_registered").alias("product_source"),
            brand_id.alias("brand_id"),
            F.trim(F.col("registered.brand_name").cast("string")).alias("brand_name"),
            F.lit(None).cast("string").alias("primary_category"),
            F.col("registered.secondary_category")
            .cast("string")
            .alias("secondary_category"),
            F.col("registered.tertiary_category")
            .cast("string")
            .alias("tertiary_category"),
            F.lit(None).cast("string").alias("category_id"),
            F.array(
                F.lit(None).cast("string"),
                F.col("registered.secondary_category").cast("string"),
                F.col("registered.tertiary_category").cast("string"),
            ).alias("category_path"),
            _base_price_krw(
                F.col("registered.price_krw")
                if "price_krw" in registered_df.columns
                else None,
                F.col("registered.price_usd"),
            ).alias("base_price"),
            F.col("registered.price_usd")
            .cast("decimal(18,2)")
            .alias("source_price_usd"),
            F.lit("KRW").alias("currency"),
            F.array().cast("array<string>").alias("skin_type_tags"),
            F.array().cast("array<string>").alias("concern_tags"),
            F.array().cast("array<string>").alias("ingredient_ids"),
            F.lit(0).cast("int").alias("caution_ingredient_count"),
            F.col("registered.rating").cast("double").alias("rating"),
            F.col("registered.rating_source").cast("string").alias("rating_source"),
            F.col("registered.loves_count").cast("long").alias("loves_count"),
            F.to_timestamp(F.col("registered.registered_at")).alias("registered_at"),
            F.current_timestamp().alias("updated_at"),
        )
        .where(F.col("product_id").isNotNull() & (F.length(F.col("product_id")) > 0))
        .dropDuplicates(["product_id"])
    )


def _merge_dim_products(seed_df: Any, registered_df: Any) -> Any:
    """Union product sources, preferring a registered snapshot on ID collision."""

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    combined = seed_df.unionByName(registered_df).withColumn(
        "_source_priority",
        F.when(F.col("product_source") == "brand_registered", F.lit(1)).otherwise(
            F.lit(0)
        ),
    )
    window = Window.partitionBy("product_id").orderBy(F.col("_source_priority").desc())
    return (
        combined.withColumn("_source_rank", F.row_number().over(window))
        .where(F.col("_source_rank") == 1)
        .drop("_source_priority", "_source_rank")
    )


# Commons Mart 가명. 길이를 줄이는 이유는 코호트 키에 섞여 로그·파일명에 남기 때문이다.
BRAND_HASH_LENGTH = 16


def _brand_hash_column(salt: str) -> Any:
    """``sha256(salt + brand_id)`` 앞 16자.

    **해시가 익명화를 보장하지 않는다.** 브랜드가 수십 개고 목록이 공개돼 있으면 전수
    대입으로 뒤집힌다. 실제 보호는 R1(브랜드 5 미만 억제)과 R3(지배 50% 억제)가 한다
    (``dw-schema.md`` §2.5.1). 이 값은 "원 brand_id 를 공유 Mart 에 싣지 않는다"는
    표기 규칙일 뿐이다.

    소금값은 저장소에 두지 않는다. 없으면 부르는 쪽이 먼저 실패한다.
    """

    from pyspark.sql import functions as F

    return F.substring(
        F.sha2(F.concat(F.lit(salt), F.col("brand_id")), 256), 1, BRAND_HASH_LENGTH
    )


def _build_dim_brand(dim_product_df: Any, commons_hash_salt: str) -> Any:
    """Build the analytics brand dimension at grain ``brand_id``.

    Account-to-brand authentication is owned by Backend and deliberately is not
    copied into the DW dimension. Conflicting names resolve deterministically and
    remain detectable from ``dim_product`` by the validation job.

    ``brand_hash`` 와 ``commons_participating`` 은 Commons Mart 가 읽는다. 여기서 한 번만
    만들고 ``brand_cohort_dim`` 은 Join 으로 가져간다 — 두 곳에서 따로 계산하면 조용히
    갈라진다 (``dw-schema.md`` §3.1).
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
        .withColumn("brand_hash", _brand_hash_column(commons_hash_salt))
        # 옵트인을 받을 온보딩 단계가 없다. 동의 UI 가 생기면 여기서 갈린다 (R7·R8).
        .withColumn("commons_participating", F.lit(True))
        .withColumn("created_at", F.lit(None).cast("timestamp"))
        .withColumn("updated_at", F.current_timestamp())
    )


# 겹쳐 보인 체류로 보지 않는 동시 노출 블록 수의 상한.
# 값의 뜻은 생성기·프론트가 정한다 — 재생 데이터에서는 한 섹션에서 펼친
# 블록 수라서 2 가 나오지 않고 사실상 1 만 걸린다.
CO_VISIBLE_CLEAN_MAX = 2

CONTENT_GROUP_COLUMNS = (
    "event_date_kst",
    "session_id",
    "page_view_id",
    "product_id",
    "section_id",
    "content_kind",
    "content_ref",
    "user_id",
    "identity_scope",
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


def _content_events(
    cleaned_df: Any,
    event_names: tuple[str, ...],
    section_kind_df: Any | None = None,
) -> Any:
    from pyspark.sql import functions as F

    typed = _typed_properties(cleaned_df).where(
        F.col("event_name").isin(*event_names)
    )
    selected = typed.select(
        "event_date_kst",
        "session_id",
        "page_view_id",
        "product_id",
        _prop(F.col("_properties"), "section_id").alias("section_id"),
        _prop(F.col("_properties"), "content_kind").alias("content_kind"),
        _prop(F.col("_properties"), "content_ref").alias("content_ref"),
        "user_id",
        "identity_scope",
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
    if section_kind_df is None:
        return selected

    # 라벨 없는 Event 를 섹션 정본으로 채운다. 채우지 않으면 같은 섹션이
    # content_kind 로 두 그룹으로 갈려 한쪽은 조회만, 다른 쪽은 드래그만 갖는다.
    # 컬럼 순서는 보존한다 — join 이 키를 맨 앞으로 옮긴다.
    columns = selected.columns
    return (
        selected.join(F.broadcast(section_kind_df), ["section_id"], "left")
        .withColumn(
            "content_kind",
            F.coalesce(F.col("content_kind"), F.col("_section_content_kind")),
        )
        .select(*columns)
    )


def _section_content_kind_map(cleaned_df: Any) -> Any:
    """섹션 하나가 content_kind 한 종류로만 나타나면 그 값을 그 섹션의 정본으로 본다.

    성분 섹션은 화면이 `section_view` 에 `content_kind` 를 싣지 않는데 같은 섹션의
    `text_selection` 은 싣는다. `content_kind` 가 그룹 키(`CONTENT_GROUP_COLUMNS`)라
    한 섹션이 두 행으로 갈리고, 드래그만 있는 쪽은 조회 0 에 세션만 남아
    `section_view_sessions > section_view_count` 가 된다 (dw-schema.md §4.4).
    `how_to_use` 도 같은 모양이다.

    라벨이 둘 이상인 섹션(`about_product`·`product_hero`·`reviews`)은 어느 것으로
    채울지 정할 근거가 없어 건드리지 않는다. 관측된 라벨이 하나뿐일 때만 쓰므로
    없는 사실을 만들지 않는다.
    """

    from pyspark.sql import functions as F

    labelled = _content_events(
        cleaned_df, ("section_view", "section_dwell") + CONTENT_INTEREST_EVENTS
    ).where(
        F.col("section_id").isNotNull()
        & (F.length(F.trim(F.col("section_id"))) > 0)
        & F.col("content_kind").isNotNull()
        & (F.length(F.trim(F.col("content_kind"))) > 0)
    )
    return (
        labelled.groupBy("section_id")
        .agg(
            F.countDistinct("content_kind").alias("_kind_count"),
            # 라벨이 하나뿐일 때만 쓰므로 min 이 곧 그 하나다. F.first 는 셔플
            # 순서를 타서 재계산 결정성이 깨진다.
            F.min("content_kind").alias("_section_content_kind"),
        )
        .where(F.col("_kind_count") == 1)
        .select("section_id", "_section_content_kind")
    )


def _section_dwell_agg(
    cleaned_df: Any,
    dim_product_df: Any | None = None,
    section_kind_df: Any | None = None,
) -> Any:
    from pyspark.sql import functions as F

    if section_kind_df is None:
        section_kind_df = _section_content_kind_map(cleaned_df)
    events = _content_events(
        cleaned_df, ("section_dwell",), section_kind_df
    ).withColumn(
        "_dwell_ms", F.col("dwell_ms").cast("long")
    )
    grouped = events.groupBy(*CONTENT_GROUP_COLUMNS).agg(
        F.coalesce(F.sum("_dwell_ms"), F.lit(0)).cast("long").alias("dwell_ms_sum"),
        # 겹쳐 보인 체류를 뺀 합계. 한 화면에 블록이 여러 개 보이면 같은
        # 시간이 블록마다 중복 귀속되므로, 귀속이 깨끗한 몫만 따로 센다
        # (dashboard-mart-api-spec §354). NULL 은 "깨끗했다"고 볼 근거가
        # 없어서 빼고, 건당으로 거른다 — 그룹 최댓값으로 거르면 큰 값
        # 하나 때문에 그룹 전체가 빠진다.
        F.coalesce(
            F.sum(
                F.when(F.col("co_visible_blocks") <= F.lit(CO_VISIBLE_CLEAN_MAX), F.col("_dwell_ms"))
            ),
            F.lit(0),
        ).cast("long").alias("co_visible_le2_dwell_ms_sum"),
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
    section_kind_df: Any | None = None,
) -> Any:
    from pyspark.sql import functions as F

    if section_kind_df is None:
        section_kind_df = _section_content_kind_map(cleaned_df)
    event_names = ("section_view",) + CONTENT_INTEREST_EVENTS
    events = _content_events(cleaned_df, event_names, section_kind_df)
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
        ("dwell_ms_sum", "co_visible_le2_dwell_ms_sum"),
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
            "co_visible_le2_dwell_ms_sum",
            F.coalesce(F.col("co_visible_le2_dwell_ms_sum"), F.lit(0)).cast("long"),
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
    # 섹션 정본 라벨은 한 번만 만들어 두 Fact 에 같이 넘긴다. 따로 만들면
    # 같은 입력에서도 두 갈래가 어긋날 여지가 남는다.
    section_kind = _section_content_kind_map(cleaned_df)
    section_dwell = _section_dwell_agg(cleaned_df, dim_product_df, section_kind)
    product_event_fact = _product_event_fact(
        cleaned_df, time_zone, dim_product_df
    )
    if weights is None:
        weights = _load_behavior_weights()
    return {
        "sessionized_events": _sessionized_events(cleaned_df, dim_product_df),
        "product_event_fact": product_event_fact,
        "purchase_fact": _purchase_fact(product_event_fact),
        "purchase_reason_fact": _purchase_reason_fact(cleaned_df),
        "review_event_fact": _review_event_fact(cleaned_df, dim_product_df),
        "section_dwell_agg": section_dwell,
        "content_interest_fact": _content_interest_fact(
            cleaned_df, section_dwell, weights, dim_product_df, section_kind
        ),
    }


def _write_processed_dataset(
    frame: Any,
    path: str,
    partition_column: str | None = None,
) -> None:
    """Write empty data without partitioning so its Parquet schema stays readable."""

    writer = frame.write.mode("overwrite")
    if partition_column is not None and not frame.isEmpty():
        writer.parquet(path, partitionBy=partition_column)
    else:
        writer.parquet(path)


def run(spark: Any, config: DeriveFactsConfig) -> None:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    catalog_df = spark.read.option("multiLine", "true").json(
        config.product_catalog_path
    )
    seed_dim_product = _build_seed_dim_product(catalog_df)
    registered_records = _active_registered_product_records(
        config.registered_product_path
    )
    registered_json = [
        json.dumps(record, ensure_ascii=False) for record in registered_records
    ]
    if registered_json:
        registered_catalog = spark.read.json(
            spark.sparkContext.parallelize(registered_json)
        )
        product_brand = None
        if config.registered_product_brand_path:
            product_brand = spark.read.json(config.registered_product_brand_path)
        registered_dim_product = _build_registered_dim_product(
            registered_catalog, product_brand
        )
    else:
        registered_dim_product = seed_dim_product.limit(0)
    dim_product = _merge_dim_products(seed_dim_product, registered_dim_product)
    dim_brand = _build_dim_brand(dim_product, config.commons_hash_salt)
    weights = _load_behavior_weights(config.behavior_weights_path)
    frames = build_derived_frames(
        spark.read.option("mergeSchema", "true").parquet(config.input_path),
        config.time_zone,
        dim_product,
        weights,
    )
    _write_processed_dataset(
        frames["sessionized_events"],
        config.sessionized_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["product_event_fact"],
        config.product_fact_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["purchase_fact"],
        config.purchase_fact_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["purchase_reason_fact"],
        config.purchase_reason_fact_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["review_event_fact"],
        config.review_event_fact_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["section_dwell_agg"],
        config.section_dwell_path,
        "event_date_kst",
    )
    _write_processed_dataset(
        frames["content_interest_fact"],
        config.content_interest_path,
        "event_date_kst",
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
