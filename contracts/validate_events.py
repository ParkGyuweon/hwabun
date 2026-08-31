#!/usr/bin/env python3
"""Validate Raw Event files against the canonical JSON Schema.

The validator accepts a single Event object, an array of Event objects, or
newline-delimited JSON (``.jsonl``/``.ndjson``). JSON Schema handles the
per-Event contract, while this module adds stateful duplicate ``event_id``
validation across every input file in one invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


DEFAULT_SCHEMA_PATH = Path(__file__).with_name("event-schema.json")


@dataclass(frozen=True)
class LoadedEvent:
    label: str
    value: Any


def _load_json_lines(path: Path) -> list[LoadedEvent]:
    events: list[LoadedEvent] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            events.append(
                LoadedEvent(
                    label=f"{path}:{line_number}",
                    value=json.loads(line),
                )
            )
    return events


def load_event_file(path: Path) -> list[LoadedEvent]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return _load_json_lines(path)

    with path.open(encoding="utf-8") as stream:
        document = json.load(stream)

    if isinstance(document, list):
        return [
            LoadedEvent(label=f"{path}[{index}]", value=value)
            for index, value in enumerate(document)
        ]
    return [LoadedEvent(label=str(path), value=document)]


def _json_path(parts: Iterable[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_event_files(
    input_paths: Iterable[Path],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> tuple[int, list[str]]:
    """Return the number of loaded Events and every validation error."""

    with schema_path.open(encoding="utf-8") as stream:
        schema = json.load(stream)

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    loaded_events: list[LoadedEvent] = []
    for input_path in input_paths:
        loaded_events.extend(load_event_file(input_path))

    errors: list[str] = []
    first_seen_event_ids: dict[str, str] = {}

    for loaded in loaded_events:
        schema_errors = sorted(
            validator.iter_errors(loaded.value),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        for error in schema_errors:
            errors.append(
                f"{loaded.label}: [{error.validator}] "
                f"{_json_path(error.absolute_path)}: {error.message}"
            )

        if not isinstance(loaded.value, dict):
            continue
        event_id = loaded.value.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        first_label = first_seen_event_ids.get(event_id)
        if first_label is None:
            first_seen_event_ids[event_id] = loaded.label
        else:
            errors.append(
                f"{loaded.label}: [duplicate_event_id] $.event_id: "
                f"'{event_id}' was first seen at {first_label}"
            )

    return len(loaded_events), errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Raw Event JSON/JSONL files."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Raw Event JSON, JSON array, JSONL, or NDJSON file",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"JSON Schema path (default: {DEFAULT_SCHEMA_PATH})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        event_count, errors = validate_event_files(args.inputs, args.schema)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        print(f"Validator setup/input error: {error}", file=sys.stderr)
        return 2

    for error in errors:
        print(error, file=sys.stderr)

    if errors:
        print(
            f"FAILED: {event_count} event(s), {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1

    print(f"PASSED: {event_count} event(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
