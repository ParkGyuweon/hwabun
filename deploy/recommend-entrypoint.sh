#!/bin/sh
# 추천 서버 진입점 (Jira 219).
# /data 볼륨에 등록 상품 파일이 없으면 이미지 안의 시드(SSAFY Beauty 8개)를 한 번 복사한다.
# 이미 있으면 건드리지 않는다 — 운영 중 POST /api/products 로 쌓인 것이 우선이다.
set -eu

DATA_FILE="${REGISTERED_PRODUCTS_PATH:-/data/registered_products.jsonl}"
SEED_FILE="/app/batch/ingest/data/serving/registered_products.jsonl"

mkdir -p "$(dirname "$DATA_FILE")"
if [ ! -s "$DATA_FILE" ] && [ -s "$SEED_FILE" ]; then
  cp "$SEED_FILE" "$DATA_FILE"
  echo "[entrypoint] seeded $DATA_FILE from image ($(wc -l < "$SEED_FILE") products)"
fi

exec python -m uvicorn batch.serving.recommend_server:app \
  --host 0.0.0.0 --port "${PORT:-8300}" \
  --workers "${WORKERS:-1}" \
  --no-access-log
