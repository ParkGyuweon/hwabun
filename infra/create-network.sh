#!/usr/bin/env bash
set -euo pipefail

network_name="a306-data"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI를 찾을 수 없습니다. Docker Engine을 먼저 실행하세요." >&2
  exit 1
fi

if ! docker network inspect "$network_name" >/dev/null 2>&1; then
  docker network create "$network_name" >/dev/null
fi

echo "Docker network '$network_name' is ready."
