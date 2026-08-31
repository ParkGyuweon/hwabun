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
from typing import Any


DEFAULT_RAW_PATH = "data/raw_events"
DEFAULT_CLEANED_PATH = "data/processed/cleaned_events"
DEFAULT_BAD_PATH = "data/processed/bad_events"
DEFAULT_DUPLICATE_PATH = "data/processed/duplicate_events"
DEFAULT_SESSIONIZED_PATH = "data/processed/sessionized_events"
DEFAULT_PRODUCT_FACT_PATH = "data/processed/product_event_fact"
DEFAULT_FUNNEL_SESSION_PATH = "data/processed/funnel_session_fact"
DEFAULT_PRODUCT_DAILY_PATH = "data/marts/product_daily_kpi"
DEFAULT_FUNNEL_DAILY_PATH = "data/marts/funnel_daily_kpi"


@dataclass(frozen=True)
class ValidatePipelineConfig:
    raw_path: str = DEFAULT_RAW_PATH
    cleaned_path: str = DEFAULT_CLEANED_PATH
    bad_path: str = DEFAULT_BAD_PATH
    duplicate_path: str = DEFAULT_DUPLICATE_PATH
    sessionized_path: str = DEFAULT_SESSIONIZED_PATH
    product_fact_path: str = DEFAULT_PRODUCT_FACT_PATH
    funnel_session_path: str = DEFAULT_FUNNEL_SESSION_PATH
    product_daily_path: str = DEFAULT_PRODUCT_DAILY_PATH
    funnel_daily_path: str = DEFAULT_FUNNEL_DAILY_PATH
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
            "funnel_session_path": self.funnel_session_path,
            "product_daily_path": self.product_daily_path,
            "funnel_daily_path": self.funnel_daily_path,
        }
        for name, value in paths.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
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
        funnel_session_path=args.funnel_session_path,
        product_daily_path=args.product_daily_path,
        funnel_daily_path=args.funnel_daily_path,
        report_path=args.report_path,
        require_events=args.require_events,
    )


def _duplicate_count(df: Any, columns: list[str]) -> int:
    from pyspark.sql import functions as F

    return df.groupBy(*columns).count().where(F.col("count") > 1).count()


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def validate_frames(frames: dict[str, Any], require_events: bool = False) -> dict[str, Any]:
    """Run cross-dataset checks and return a JSON-serializable report."""

    from pyspark.sql import functions as F

    raw = frames["raw"]
    cleaned = frames["cleaned"]
    bad = frames["bad"]
    duplicates = frames["duplicates"]
    sessionized = frames["sessionized"]
    product_fact = frames["product_fact"]
    funnel_session = frames["funnel_session"]
    product_daily = frames["product_daily"]
    funnel_daily = frames["funnel_daily"]

    counts = {
        "raw": raw.count(),
        "cleaned": cleaned.count(),
        "bad": bad.count(),
        "duplicates": duplicates.count(),
        "sessionized": sessionized.count(),
        "product_fact": product_fact.count(),
        "funnel_session": funnel_session.count(),
        "product_daily": product_daily.count(),
        "funnel_daily": funnel_daily.count(),
    }
    checks: list[dict[str, Any]] = []

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
            "funnel_session_grain_is_unique",
            _duplicate_count(funnel_session, ["session_id", "product_id"]) == 0,
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

    failures = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failures else "failed",
        "counts": counts,
        "checks": checks,
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
        "funnel_session": config.funnel_session_path,
        "product_daily": config.product_daily_path,
        "funnel_daily": config.funnel_daily_path,
    }
    frames = {name: spark.read.parquet(path) for name, path in paths.items()}
    return validate_frames(frames, config.require_events)


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
        with open(config.report_path, "w", encoding="utf-8") as report_file:
            report_file.write(rendered + "\n")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
