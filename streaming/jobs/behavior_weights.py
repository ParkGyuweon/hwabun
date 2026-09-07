"""Load the single behavior-weight source used by Spark aggregations.

The values intentionally stay in ``frontend/src/types/log.ts``.  This small
adapter lets Spark reuse ``batch/jobs/behavior_weights.py`` in both the local
repository and the Docker-mounted project root without copying the numbers.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    configured_root = os.getenv("PROJECT_ROOT")
    if configured_root and configured_root.strip():
        return Path(configured_root).resolve()
    return Path(__file__).resolve().parents[2]


def load(path: str | None = None) -> dict[str, Any]:
    root = _project_root()
    parser_path = root / "batch" / "jobs" / "behavior_weights.py"
    log_path = Path(path) if path else root / "frontend" / "src" / "types" / "log.ts"
    if not log_path.is_absolute():
        log_path = root / log_path

    spec = importlib.util.spec_from_file_location(
        "hwabun_behavior_weights", parser_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"가중치 파서를 불러올 수 없습니다: {parser_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load(str(log_path))
