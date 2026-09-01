"""Assert that one event_id is present in the Q1 Raw Parquet output.

This lives beside the Docker infrastructure rather than in the streaming
implementation because it is an E2E probe used only by the local stack.
"""

from __future__ import annotations

import argparse
import json
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assert a Kafka event was persisted by the Q1 Raw sink."
    )
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--expected-count", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from pyspark.sql import SparkSession, functions as F

    spark = SparkSession.builder.appName("assert-raw-event").getOrCreate()
    try:
        count = (
            spark.read.parquet(args.raw_path)
            .where(F.col("event_id") == args.event_id)
            .count()
        )
        result = {
            "event_id": args.event_id,
            "expected_count": args.expected_count,
            "actual_count": count,
            "status": "passed" if count == args.expected_count else "failed",
        }
        print(json.dumps(result))
        if count != args.expected_count:
            raise SystemExit(1)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
