#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
data_root="${PIPELINE_DATA_ROOT:-/opt/project/data}"
kafka_compose="$repo_root/infra/kafka/docker-compose.yml"
spark_compose="$repo_root/infra/spark/docker-compose.yml"

compose=(docker compose)
if [[ -f "$repo_root/infra/spark/.env" ]]; then
  compose+=(--env-file "$repo_root/infra/spark/.env")
fi
compose+=(-f "$kafka_compose" -f "$spark_compose")

invoke_compose() {
  "${compose[@]}" "$@"
}

submit_job() {
  local job_path="$1"
  shift

  invoke_compose exec -T spark-master \
    /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --conf spark.driver.host=spark-master \
    --conf spark.driver.bindAddress=0.0.0.0 \
    "$job_path" "$@"
}

validate_pipeline() {
  submit_job /opt/project/streaming/jobs/validate_pipeline_job.py \
    --raw-path "$data_root/raw_events" \
    --cleaned-path "$data_root/processed/cleaned_events" \
    --bad-path "$data_root/processed/bad_events" \
    --duplicate-path "$data_root/processed/duplicate_events" \
    --sessionized-path "$data_root/processed/sessionized_events" \
    --product-fact-path "$data_root/processed/product_event_fact" \
    --purchase-fact-path "$data_root/processed/purchase_fact" \
    --purchase-reason-fact-path "$data_root/processed/purchase_reason_fact" \
    --review-event-fact-path "$data_root/processed/review_event_fact" \
    --section-dwell-path "$data_root/processed/section_dwell_agg" \
    --content-interest-path "$data_root/processed/content_interest_fact" \
    --dim-product-path "$data_root/processed/dim_product" \
    --dim-brand-path "$data_root/processed/dim_brand" \
    --funnel-session-path "$data_root/processed/funnel_session_fact" \
    --product-daily-path "$data_root/marts/product_daily_kpi" \
    --funnel-daily-path "$data_root/marts/funnel_daily_kpi" \
    --brand-daily-path "$data_root/marts/brand_daily_kpi" \
    --product-repurchase-path "$data_root/marts/product_repurchase_daily" \
    --brand-repurchase-path "$data_root/marts/brand_repurchase_daily" \
    --purchase-reason-path "$data_root/marts/purchase_reason_daily" \
    --reason-trait-map-path /opt/project/contracts/purchase-reason-trait-map.json \
    --behavior-weights-path /opt/project/frontend/src/types/log.ts \
    --ingredient-weekly-path "$data_root/marts/ingredient_weekly_interest" \
    --category-price-path "$data_root/marts/category_price_reference" \
    --banner-daily-path "$data_root/marts/banner_daily" \
    --user-trait-daily-path "$data_root/marts/user_trait_daily" \
    --cross-brand-daily-path "$data_root/marts/cross_brand_daily" \
    --baseline-path "$data_root/marts/analytics_baseline" \
    --report-path "$data_root/validation/pipeline-report.json" \
    --require-events
}

run_batch_pipeline() {
  submit_job /opt/project/streaming/jobs/clean_events_job.py \
    --input-path "$data_root/raw_events" \
    --cleaned-path "$data_root/processed/cleaned_events" \
    --bad-path "$data_root/processed/bad_events" \
    --duplicate-path "$data_root/processed/duplicate_events"

  local derive_args=(
    --input-path "$data_root/processed/cleaned_events"
    --sessionized-path "$data_root/processed/sessionized_events"
    --product-fact-path "$data_root/processed/product_event_fact"
    --purchase-fact-path "$data_root/processed/purchase_fact"
    --purchase-reason-fact-path "$data_root/processed/purchase_reason_fact"
    --review-event-fact-path "$data_root/processed/review_event_fact"
    --section-dwell-path "$data_root/processed/section_dwell_agg"
    --content-interest-path "$data_root/processed/content_interest_fact"
    --dim-product-path "$data_root/processed/dim_product"
    --dim-brand-path "$data_root/processed/dim_brand"
    --product-catalog-path /opt/project/batch/ingest/data/products_200.json
    --registered-product-path /opt/project/batch/ingest/data/serving/registered_products.jsonl
    --behavior-weights-path /opt/project/frontend/src/types/log.ts
  )
  if [[ -n "${REGISTERED_PRODUCT_BRAND_PATH:-}" ]]; then
    derive_args+=(
      --registered-product-brand-path "$REGISTERED_PRODUCT_BRAND_PATH"
    )
  fi
  submit_job /opt/project/streaming/jobs/derive_facts_job.py "${derive_args[@]}"

  local mart_args=(
    --sessionized-path "$data_root/processed/sessionized_events"
    --product-fact-path "$data_root/processed/product_event_fact"
    --purchase-fact-path "$data_root/processed/purchase_fact"
    --purchase-reason-fact-path "$data_root/processed/purchase_reason_fact"
    --dim-product-path "$data_root/processed/dim_product"
    --product-ingredient-path /opt/project/batch/ingest/data/serving/product_ingredient.csv
    --ingredient-vocab-path /opt/project/batch/ingest/data/serving/ingredient_vocab.csv
    --funnel-session-path "$data_root/processed/funnel_session_fact"
    --product-daily-path "$data_root/marts/product_daily_kpi"
    --funnel-daily-path "$data_root/marts/funnel_daily_kpi"
    --brand-daily-path "$data_root/marts/brand_daily_kpi"
    --product-repurchase-path "$data_root/marts/product_repurchase_daily"
    --brand-repurchase-path "$data_root/marts/brand_repurchase_daily"
    --purchase-reason-path "$data_root/marts/purchase_reason_daily"
    --reason-trait-map-path /opt/project/contracts/purchase-reason-trait-map.json
    --ingredient-weekly-path "$data_root/marts/ingredient_weekly_interest"
    --category-price-path "$data_root/marts/category_price_reference"
    --banner-daily-path "$data_root/marts/banner_daily"
    --user-trait-daily-path "$data_root/marts/user_trait_daily"
    --cross-brand-daily-path "$data_root/marts/cross_brand_daily"
    --baseline-path "$data_root/marts/analytics_baseline"
    --trait-weights-path /opt/project/contracts/user-trait-weights.json
    --feature-vocab-path /opt/project/contracts/product-feature-vocab.json
    --affinity-lift-path /opt/project/batch/ingest/data/affinity_lift.csv
    --behavior-weights-path /opt/project/frontend/src/types/log.ts
  )
  if [[ -n "${BASELINE_POLICY_VERSION:-}" && -n "${BASELINE_START_DATE:-}" && -n "${BASELINE_END_DATE:-}" ]]; then
    mart_args+=(
      --baseline-policy-version "$BASELINE_POLICY_VERSION"
      --baseline-start-date "$BASELINE_START_DATE"
      --baseline-end-date "$BASELINE_END_DATE"
    )
  fi
  submit_job /opt/project/streaming/jobs/build_marts_job.py "${mart_args[@]}"

  validate_pipeline
}

case "$action" in
  up)
    bash "$repo_root/infra/create-network.sh"
    invoke_compose up -d --build --wait kafka spark-master spark-worker spark-history
    ;;
  start-q1)
    invoke_compose --profile streaming up -d spark-raw-sink
    ;;
  stop-q1)
    invoke_compose --profile streaming stop spark-raw-sink
    ;;
  run-batch)
    run_batch_pipeline
    ;;
  validate)
    validate_pipeline
    ;;
  status)
    invoke_compose --profile streaming ps
    ;;
  down)
    invoke_compose down
    ;;
  *)
    echo "Usage: $0 {up|start-q1|stop-q1|run-batch|validate|status|down}" >&2
    exit 2
    ;;
esac
