#!/usr/bin/env python3
"""Validate Event files against the canonical Raw Event JSON Schema.

This tool currently validates the common Event envelope. Event-specific
``properties`` contracts are intentionally out of scope until those contracts
are reconciled with Frontend and Simulator implementations.

The validator accepts a single Event object, an array of Event objects, an API
batch body (``{"schema_version": ..., "events": [...]}``), or newline-delimited
JSON (``.jsonl``/``.ndjson``). JSONL input is streamed one Event at a time.
Duplicate ``event_id`` checking is optional because Raw storage intentionally
preserves at-least-once delivery duplicates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


DEFAULT_SCHEMA_PATH = Path(__file__).with_name("event-schema.json")
DEFAULT_MAX_ERRORS = 100
DuplicatePolicy = Literal["ignore", "warn", "error"]


class ValidatorInputError(ValueError):
    """The schema or input cannot be read safely enough to validate."""


@dataclass(frozen=True)
class LoadedEvent:
    label: str
    value: Any
    batch_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    event_count: int
    errors: list[str]
    warnings: list[str]
    stopped_early: bool = False


def _read_json_document(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream)
    except UnicodeError as error:
        raise ValidatorInputError(f"{path}: input must be UTF-8: {error}") from error
    except json.JSONDecodeError as error:
        raise ValidatorInputError(
            f"{path}:{error.lineno}:{error.colno}: invalid JSON: {error.msg}"
        ) from error


def _iter_json_lines(path: Path) -> Iterator[LoadedEvent]:
    try:
        with path.open(encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValidatorInputError(
                        f"{path}:{line_number}:{error.colno}: "
                        f"invalid JSON: {error.msg}"
                    ) from error
                yield LoadedEvent(label=f"{path}:{line_number}", value=value)
    except UnicodeError as error:
        raise ValidatorInputError(f"{path}: input must be UTF-8: {error}") from error


def iter_event_file(
    path: Path,
    supported_schema_versions: tuple[str, ...],
) -> Iterator[LoadedEvent]:
    """Yield Events without materializing JSONL input in memory."""

    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        yield from _iter_json_lines(path)
        return

    document = _read_json_document(path)
    if isinstance(document, list):
        for index, value in enumerate(document):
            yield LoadedEvent(label=f"{path}[{index}]", value=value)
        return

    if (
        isinstance(document, dict)
        and "events" in document
        and "event_id" not in document
    ):
        events = document["events"]
        if not isinstance(events, list):
            raise ValidatorInputError(f"{path}: $.events must be an array")

        batch_version = document.get("schema_version")
        batch_errors: list[str] = []
        if "schema_version" not in document:
            batch_errors.append(
                f"{path}: [required] $.schema_version: "
                "API batch schema_version is required"
            )
        elif not isinstance(batch_version, str):
            batch_errors.append(
                f"{path}: [type] $.schema_version: "
                "API batch schema_version must be a string"
            )
        elif batch_version not in supported_schema_versions:
            batch_errors.append(
                f"{path}: [enum] $.schema_version: {batch_version!r} is not one of "
                f"{list(supported_schema_versions)!r}"
            )

        for index, value in enumerate(events):
            event_errors = list(batch_errors) if index == 0 else []
            if (
                isinstance(batch_version, str)
                and isinstance(value, dict)
                and value.get("schema_version") != batch_version
            ):
                event_errors.append(
                    f"{path}.events[{index}]: [schema_version_mismatch] "
                    "$.schema_version: Event schema_version "
                    f"{value.get('schema_version')!r} does not match API batch "
                    f"schema_version {batch_version!r}"
                )
            yield LoadedEvent(
                label=f"{path}.events[{index}]",
                value=value,
                batch_errors=tuple(event_errors),
            )
        return

    yield LoadedEvent(label=str(path), value=document)


def _json_path(parts: Iterable[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _build_validator(schema_path: Path) -> Draft202012Validator:
    schema = _read_json_document(schema_path)
    Draft202012Validator.check_schema(schema)

    format_checker = FormatChecker()
    if "date-time" not in format_checker.checkers:
        raise ValidatorInputError(
            "date-time format checking is unavailable; install dependencies with "
            "contracts/requirements-validator.txt"
        )
    return Draft202012Validator(schema, format_checker=format_checker)


def _supported_schema_versions(
    validator: Draft202012Validator,
) -> tuple[str, ...]:
    versions = (
        validator.schema.get("properties", {})
        .get("schema_version", {})
        .get("enum")
    )
    if (
        not isinstance(versions, list)
        or not versions
        or any(not isinstance(version, str) for version in versions)
    ):
        raise ValidatorInputError(
            "schema properties.schema_version.enum must contain supported strings"
        )
    return tuple(versions)


def _unique_paths(input_paths: Iterable[Path]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    warnings: list[str] = []
    seen: set[Path] = set()
    for input_path in input_paths:
        resolved = input_path.resolve()
        if resolved in seen:
            warnings.append(
                f"{input_path}: [duplicate_input_path] already selected as {resolved}"
            )
            continue
        seen.add(resolved)
        paths.append(resolved)
    return paths, warnings


def validate_event_files(
    input_paths: Iterable[Path],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    *,
    duplicate_policy: DuplicatePolicy = "warn",
    max_errors: int = DEFAULT_MAX_ERRORS,
) -> ValidationResult:
    """Validate inputs with bounded error memory and optional duplicate checks."""

    if max_errors < 1:
        raise ValidatorInputError("max_errors must be at least 1")
    validator = _build_validator(schema_path)
    supported_schema_versions = _supported_schema_versions(validator)
    paths, warnings = _unique_paths(input_paths)

    errors: list[str] = []
    first_seen_event_ids: dict[str, str] | None = (
        {} if duplicate_policy != "ignore" else None
    )
    event_count = 0
    stopped_early = False

    for input_path in paths:
        for loaded in iter_event_file(input_path, supported_schema_versions):
            event_count += 1
            for batch_error in loaded.batch_errors:
                errors.append(batch_error)
                if len(errors) >= max_errors:
                    stopped_early = True
                    break
            if stopped_early:
                break

            schema_errors = sorted(
                validator.iter_errors(loaded.value),
                key=lambda error: (
                    tuple(str(part) for part in error.absolute_path),
                    error.message,
                ),
            )
            for error in schema_errors:
                errors.append(
                    f"{loaded.label}: [{error.validator}] "
                    f"{_json_path(error.absolute_path)}: {error.message}"
                )
                if len(errors) >= max_errors:
                    stopped_early = True
                    break
            if stopped_early:
                break

            if first_seen_event_ids is None or not isinstance(loaded.value, dict):
                continue
            event_id = loaded.value.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                continue
            first_label = first_seen_event_ids.get(event_id)
            if first_label is None:
                first_seen_event_ids[event_id] = loaded.label
                continue

            duplicate_message = (
                f"{loaded.label}: [duplicate_event_id] $.event_id: "
                f"'{event_id}' was first seen at {first_label}"
            )
            if duplicate_policy == "warn":
                if len(warnings) < max_errors:
                    warnings.append(duplicate_message)
            else:
                errors.append(duplicate_message)
                if len(errors) >= max_errors:
                    stopped_early = True
                    break
        if stopped_early:
            break

    if event_count == 0:
        raise ValidatorInputError("no Events were found in the selected input files")

    return ValidationResult(
        event_count=event_count,
        errors=errors,
        warnings=warnings,
        stopped_early=stopped_early,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Event JSON/JSONL files against the Raw Event Schema."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Event JSON, JSON array, API batch body, JSONL, or NDJSON file",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"JSON Schema path (default: {DEFAULT_SCHEMA_PATH})",
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=("ignore", "warn", "error"),
        default="warn",
        help="event_id duplicate handling (default: warn for Raw validation)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=DEFAULT_MAX_ERRORS,
        help=f"stop after this many errors (default: {DEFAULT_MAX_ERRORS})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = validate_event_files(
            args.inputs,
            args.schema,
            duplicate_policy=args.duplicate_policy,
            max_errors=args.max_errors,
        )
    except (OSError, SchemaError, ValidatorInputError) as error:
        print(f"Validator setup/input error: {error}", file=sys.stderr)
        return 2

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.errors:
        print(error, file=sys.stderr)

    if result.errors:
        suffix = " (stopped at max-errors)" if result.stopped_early else ""
        print(
            f"FAILED: {result.event_count} event(s) checked, "
            f"{len(result.errors)} error(s){suffix}",
            file=sys.stderr,
        )
        return 1

    warning_suffix = (
        f", {len(result.warnings)} warning(s)" if result.warnings else ""
    )
    print(f"PASSED: {result.event_count} event(s){warning_suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
