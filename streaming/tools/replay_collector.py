"""Stream JSONL or gzip JSONL events to the Collector in bounded batches.

The input is never materialized as a whole.  A final report accounts for every
non-empty JSONL record as accepted, rejected, or abandoned after retries.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterator


TRANSIENT_STATUS = {429, 502, 503}


def _open_text(path: str):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def iter_records(path: str) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Yield one parsed object per non-empty line; malformed lines yield None."""

    with _open_text(path) as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                yield line_number, None
                continue
            yield line_number, value if isinstance(value, dict) else None


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inspect_file(path: str) -> dict[str, Any]:
    """Collect bounded-cardinality evidence without posting any events."""

    event_names: collections.Counter[str] = collections.Counter()
    sessions: set[str] = set()
    simulation_runs: set[str] = set()
    algorithms: set[str] = set()
    minimum_date: str | None = None
    maximum_date: str | None = None
    invalid_jsonl = 0
    policy_missing_banner = 0
    banner_impressions: dict[tuple[Any, ...], int] = {}
    banner_clicks: list[tuple[tuple[Any, ...], int]] = []
    new_brand_value_violations = 0
    total = 0
    for _, event in iter_records(path):
        total += 1
        if event is None:
            invalid_jsonl += 1
            continue
        event_name = event.get("event_name")
        if isinstance(event_name, str):
            event_names[event_name] += 1
        session_id = event.get("session_id")
        if isinstance(session_id, str):
            sessions.add(session_id)
        occurred_at = event.get("occurred_at")
        if isinstance(occurred_at, str) and len(occurred_at) >= 10:
            event_date = occurred_at[:10]
            minimum_date = min(minimum_date, event_date) if minimum_date else event_date
            maximum_date = max(maximum_date, event_date) if maximum_date else event_date
        properties = event.get("properties")
        if isinstance(properties, dict):
            simulation_run_id = properties.get("simulation_run_id")
            if isinstance(simulation_run_id, str):
                simulation_runs.add(simulation_run_id)
            algorithm = properties.get("algorithm")
            if isinstance(algorithm, str):
                algorithms.add(algorithm)
            if event_name in {"banner_impression", "banner_click"} and not properties.get(
                "policy_version"
            ):
                policy_missing_banner += 1
            if event_name in {"banner_impression", "banner_click"}:
                key = (
                    session_id,
                    properties.get("recommendation_id"),
                    event.get("product_id"),
                    properties.get("banner_slot"),
                )
                sequence_no = event.get("sequence_no")
                if isinstance(sequence_no, int):
                    if event_name == "banner_impression":
                        previous = banner_impressions.get(key)
                        banner_impressions[key] = (
                            min(previous, sequence_no)
                            if previous is not None
                            else sequence_no
                        )
                    else:
                        banner_clicks.append((key, sequence_no))
                if (
                    properties.get("banner_type") == "new_brand"
                    and properties.get("banner_value") is not None
                ):
                    new_brand_value_violations += 1
    unmatched_banner_clicks = sum(
        1
        for key, click_sequence in banner_clicks
        if key not in banner_impressions
        or banner_impressions[key] >= click_sequence
    )
    return {
        "path": str(Path(path).resolve()),
        "sha256": sha256_file(path),
        "total": total,
        "invalid_jsonl": invalid_jsonl,
        "sessions": len(sessions),
        "date_min": minimum_date,
        "date_max": maximum_date,
        "simulation_run_ids": sorted(simulation_runs),
        "algorithms": sorted(algorithms),
        "event_counts": dict(sorted(event_names.items())),
        "banner_policy_version_missing": policy_missing_banner,
        "banner_clicks_without_preceding_matching_impression": unmatched_banner_clicks,
        "new_brand_non_null_banner_value": new_brand_value_violations,
    }


def _http_sender(url: str, timeout: float) -> Callable[[dict[str, Any]], tuple[int, dict[str, Any], dict[str, str]]]:
    def parse_body(body: str) -> dict[str, Any]:
        try:
            value = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def send(payload: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, str]]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "hwabun-data-replay/1.0",
            },
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, parse_body(body), dict(exc.headers.items())
        with response:
            body = response.read().decode("utf-8")
            return response.status, parse_body(body), dict(response.headers.items())

    return send


def replay(
    path: str,
    sender: Callable[[dict[str, Any]], tuple[int, dict[str, Any], dict[str, str]]],
    *,
    batch_size: int = 100,
    max_retries: int = 5,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")

    result: dict[str, Any] = {
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "abandoned": 0,
        "partial_acceptance_batches": 0,
        "retried_batches": 0,
        "attempts": 0,
        "rejection_codes": collections.Counter(),
    }
    batch: list[dict[str, Any]] = []

    def flush(events: list[dict[str, Any]]) -> None:
        schema_version = events[0].get("schema_version")
        payload = {"schema_version": schema_version, "events": events}
        for attempt in range(max_retries + 1):
            result["attempts"] += 1
            try:
                status, body, headers = sender(payload)
            except (OSError, TimeoutError, urllib.error.URLError):
                status, body, headers = 503, {}, {}

            if status == 202:
                accepted = body.get("accepted")
                rejected = body.get("rejected")
                if (
                    isinstance(accepted, int)
                    and isinstance(rejected, int)
                    and accepted >= 0
                    and rejected >= 0
                    and accepted + rejected == len(events)
                ):
                    result["accepted"] += accepted
                    result["rejected"] += rejected
                    if accepted and rejected:
                        result["partial_acceptance_batches"] += 1
                    for rejection in body.get("rejections", []):
                        code = rejection.get("code", "unknown")
                        result["rejection_codes"][code] += 1
                    return
                status = 503

            if status not in TRANSIENT_STATUS:
                result["rejected"] += len(events)
                result["rejection_codes"][f"http_{status}"] += len(events)
                return
            if attempt == max_retries:
                result["abandoned"] += len(events)
                return
            if attempt == 0:
                result["retried_batches"] += 1
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after is not None else 0.0
            except ValueError:
                delay = 0.0
            delay = max(delay, backoff_seconds * (2**attempt))
            sleep(min(delay, 30.0))

    for _, event in iter_records(path):
        result["total"] += 1
        if event is None:
            result["rejected"] += 1
            result["rejection_codes"]["invalid_jsonl"] += 1
            continue
        batch.append(event)
        if len(batch) == batch_size:
            flush(batch)
            batch = []
    if batch:
        flush(batch)

    result["rejection_codes"] = dict(sorted(result["rejection_codes"].items()))
    accounted = result["accepted"] + result["rejected"] + result["abandoned"]
    result["accounted"] = accounted
    result["accounting_matches_total"] = accounted == result["total"]
    return result


def _write_report(report: dict[str, Any], path: str | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL or .jsonl.gz event file")
    parser.add_argument("--url", default="http://localhost:8080/api/events")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--backoff-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--report-path")
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)

    actual_sha256 = sha256_file(args.path)
    if args.expected_sha256 and actual_sha256 != args.expected_sha256.upper():
        raise SystemExit(
            f"SHA-256 mismatch: expected={args.expected_sha256.upper()} actual={actual_sha256}"
        )
    if args.inspect_only:
        _write_report(inspect_file(args.path), args.report_path)
        return
    report = replay(
        args.path,
        _http_sender(args.url, args.timeout),
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
    )
    report.update({"path": str(Path(args.path).resolve()), "sha256": actual_sha256})
    _write_report(report, args.report_path)
    if report["abandoned"] or not report["accounting_matches_total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
