"""Kafka activity-events -> Raw Parquet Structured Streaming job.

The job deliberately keeps the Kafka value as ``raw_value``.  Parsed fields
are convenience columns for the next processing stage; they are not a
replacement for the original event.  Q1 does not deduplicate by ``event_id``.
Business-event deduplication belongs to Q2, while Kafka record identity is the
``kafka_cluster_id + kafka_topic + kafka_partition + kafka_offset`` tuple.

PySpark imports stay inside the functions that need them.  This keeps the
configuration parser and its tests runnable on a machine that does not have a
Spark distribution installed.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_BOOTSTRAP_SERVERS = "localhost:9092"
DEFAULT_TOPIC = "activity-events"
DEFAULT_OUTPUT_PATH = "data/raw_events"
DEFAULT_CHECKPOINT_PATH = "data/checkpoints/raw-events"
DEFAULT_STARTING_OFFSETS = "earliest"
DEFAULT_TRIGGER_INTERVAL = "10 seconds"
DEFAULT_CLUSTER_ID = "local"

# This is the output contract of Q1, independent of Spark's internal Kafka
# source schema.  Keeping the list here also makes accidental removal of
# source coordinates visible in a lightweight unit test.
RAW_EVENT_FIELDS = (
    "kafka_cluster_id",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
    "kafka_timestamp",
    "kafka_timestamp_type",
    "kafka_key",
    "raw_value",
    "is_json_parseable",
    "schema_version",
    "event_id",
    "event_name",
    "intent",
    "event_time",
    "received_at",
    "persona_id",
    "session_id",
    "page_view_id",
    "sequence_no",
    "page_type",
    "product_id",
    "actor_type",
    "environment",
    "request_id",
    "event_index",
    "properties_json",
    "raw_ingested_at",
    "raw_ingest_date",
)


@dataclass(frozen=True)
class RawSinkConfig:
    """Runtime configuration for one Q1 query."""

    bootstrap_servers: str = DEFAULT_BOOTSTRAP_SERVERS
    topic: str = DEFAULT_TOPIC
    output_path: str = DEFAULT_OUTPUT_PATH
    checkpoint_path: str = DEFAULT_CHECKPOINT_PATH
    starting_offsets: str = DEFAULT_STARTING_OFFSETS
    trigger_interval: str = DEFAULT_TRIGGER_INTERVAL
    cluster_id: str = DEFAULT_CLUSTER_ID
    max_offsets_per_trigger: int | None = None
    query_name: str = "raw-events-ingest"

    def __post_init__(self) -> None:
        required = {
            "bootstrap_servers": self.bootstrap_servers,
            "topic": self.topic,
            "output_path": self.output_path,
            "checkpoint_path": self.checkpoint_path,
            "starting_offsets": self.starting_offsets,
            "trigger_interval": self.trigger_interval,
            "cluster_id": self.cluster_id,
            "query_name": self.query_name,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        if self.max_offsets_per_trigger is not None and self.max_offsets_per_trigger <= 0:
            raise ValueError("max_offsets_per_trigger must be greater than zero")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consume Kafka activity events and persist raw_events as Parquet."
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=_env("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP_SERVERS),
        help="Kafka bootstrap servers, e.g. localhost:9092",
    )
    parser.add_argument(
        "--topic",
        default=_env("ACTIVITY_EVENTS_TOPIC", DEFAULT_TOPIC),
        help="Input Kafka topic",
    )
    parser.add_argument(
        "--output-path",
        default=_env("RAW_EVENTS_PATH", DEFAULT_OUTPUT_PATH),
        help="Parquet output path for raw_events",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=_env("RAW_EVENTS_CHECKPOINT_PATH", DEFAULT_CHECKPOINT_PATH),
        help="Persistent checkpoint path for this query",
    )
    parser.add_argument(
        "--starting-offsets",
        default=_env("RAW_EVENTS_STARTING_OFFSETS", DEFAULT_STARTING_OFFSETS),
        help="Kafka starting offsets for a new query: earliest/latest or JSON ranges",
    )
    parser.add_argument(
        "--trigger-interval",
        default=_env("RAW_EVENTS_TRIGGER_INTERVAL", DEFAULT_TRIGGER_INTERVAL),
        help="Structured Streaming processing trigger, e.g. '10 seconds'",
    )
    parser.add_argument(
        "--cluster-id",
        default=_env("KAFKA_CLUSTER_ID", DEFAULT_CLUSTER_ID),
        help="Stable source-cluster identifier stored with Kafka coordinates",
    )
    parser.add_argument(
        "--max-offsets-per-trigger",
        type=int,
        default=(
            int(os.environ["RAW_EVENTS_MAX_OFFSETS_PER_TRIGGER"])
            if os.getenv("RAW_EVENTS_MAX_OFFSETS_PER_TRIGGER")
            else None
        ),
        help="Optional Kafka read limit per micro-batch",
    )
    parser.add_argument(
        "--query-name",
        default=_env("RAW_EVENTS_QUERY_NAME", "raw-events-ingest"),
        help="Spark query name",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> RawSinkConfig:
    args = build_parser().parse_args(argv)
    return RawSinkConfig(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        output_path=args.output_path,
        checkpoint_path=args.checkpoint_path,
        starting_offsets=args.starting_offsets,
        trigger_interval=args.trigger_interval,
        cluster_id=args.cluster_id,
        max_offsets_per_trigger=args.max_offsets_per_trigger,
        query_name=args.query_name,
    )


def _event_schema() -> Any:
    """Return the scalar portion of the Collector Kafka value schema."""

    from pyspark.sql.types import (
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    return StructType(
        [
            StructField("schema_version", StringType(), True),
            StructField("event_id", StringType(), True),
            StructField("event_name", StringType(), True),
            StructField("intent", StringType(), True),
            StructField("occurred_at", StringType(), True),
            StructField("received_at", StringType(), True),
            StructField("persona_id", StringType(), True),
            StructField("session_id", StringType(), True),
            StructField("page_view_id", StringType(), True),
            StructField("sequence_no", IntegerType(), True),
            StructField("page_type", StringType(), True),
            StructField("product_id", StringType(), True),
            StructField("actor_type", StringType(), True),
            StructField("environment", StringType(), True),
            StructField("request_id", StringType(), True),
            StructField("event_index", IntegerType(), True),
        ]
    )


def build_raw_events_frame(kafka_df: Any, cluster_id: str) -> Any:
    """Project a Kafka source DataFrame into the Q1 Raw schema.

    ``from_json`` only parses scalar envelope fields.  ``properties`` remains
    a JSON string so arbitrary nested event-specific values survive unchanged.
    A malformed JSON value therefore still produces a Raw row with Kafka
    metadata and ``is_json_parseable = false``; Q2 decides how to route it.
    """

    from pyspark.sql import functions as F

    raw_value = F.col("value").cast("string")
    parsed = F.from_json(raw_value, _event_schema())
    parsed_field = parsed.getField

    raw_events = kafka_df.select(
        F.lit(cluster_id).alias("kafka_cluster_id"),
        F.col("topic").alias("kafka_topic"),
        F.col("partition").cast("int").alias("kafka_partition"),
        F.col("offset").cast("long").alias("kafka_offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("timestampType").cast("int").alias("kafka_timestamp_type"),
        F.col("key").cast("string").alias("kafka_key"),
        raw_value.alias("raw_value"),
        parsed.isNotNull().alias("is_json_parseable"),
        parsed_field("schema_version").alias("schema_version"),
        parsed_field("event_id").alias("event_id"),
        parsed_field("event_name").alias("event_name"),
        parsed_field("intent").alias("intent"),
        F.to_timestamp(parsed_field("occurred_at")).alias("event_time"),
        F.to_timestamp(parsed_field("received_at")).alias("received_at"),
        parsed_field("persona_id").alias("persona_id"),
        parsed_field("session_id").alias("session_id"),
        parsed_field("page_view_id").alias("page_view_id"),
        parsed_field("sequence_no").alias("sequence_no"),
        parsed_field("page_type").alias("page_type"),
        parsed_field("product_id").alias("product_id"),
        parsed_field("actor_type").alias("actor_type"),
        parsed_field("environment").alias("environment"),
        parsed_field("request_id").alias("request_id"),
        parsed_field("event_index").alias("event_index"),
        F.get_json_object(raw_value, "$.properties").alias("properties_json"),
        F.current_timestamp().alias("raw_ingested_at"),
    )
    return raw_events.withColumn(
        "raw_ingest_date", F.to_date(F.col("raw_ingested_at"))
    )


def read_kafka_stream(spark: Any, config: RawSinkConfig) -> Any:
    reader = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", config.bootstrap_servers)
        .option("subscribe", config.topic)
        .option("startingOffsets", config.starting_offsets)
        .option("failOnDataLoss", "true")
    )
    if config.max_offsets_per_trigger is not None:
        reader = reader.option(
            "maxOffsetsPerTrigger", str(config.max_offsets_per_trigger)
        )
    return reader.load()


def start_query(spark: Any, config: RawSinkConfig) -> Any:
    kafka_df = read_kafka_stream(spark, config)
    raw_events = build_raw_events_frame(kafka_df, config.cluster_id)
    return (
        raw_events.writeStream.format("parquet")
        .outputMode("append")
        .option("path", config.output_path)
        .option("checkpointLocation", config.checkpoint_path)
        .queryName(config.query_name)
        .partitionBy("raw_ingest_date")
        .trigger(processingTime=config.trigger_interval)
        .start()
    )


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName(config.query_name)
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        start_query(spark, config).awaitTermination()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
