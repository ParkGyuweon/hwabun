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
  # --env-file 은 compose 서비스 환경에만 닿는다. --commons-hash-salt 는 이
  # 스크립트를 실행한 셸의 변수를 읽으므로 여기서 따로 들여온다. 이미 셸에
  # 설정돼 있으면 그쪽을 쓴다.
  if [[ -z "${COMMONS_HASH_SALT:-}" ]]; then
    COMMONS_HASH_SALT="$(
      sed -n 's/^COMMONS_HASH_SALT=//p' "$repo_root/infra/spark/.env" | tail -n 1
    )"
    export COMMONS_HASH_SALT
  fi
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
    --persona-segment-path "$data_root/marts/persona_segment_daily_kpi" \
    --price-band-path "$data_root/marts/brand_price_band_daily_kpi" \
    --brand-cohort-path "$data_root/marts/brand_cohort_dim" \
    --commons-cohort-path "$data_root/marts/commons_cohort_weekly" \
    --banner-daily-path "$data_root/marts/banner_daily" \
    --user-trait-daily-path "$data_root/marts/user_trait_daily" \
    --cross-brand-daily-path "$data_root/marts/cross_brand_daily" \
    --baseline-path "$data_root/marts/analytics_baseline" \
    --content-daily-path "$data_root/marts/content_daily_kpi" \
    --content-conversion-path "$data_root/marts/content_conversion_daily" \
    --behavior-conversion-path "$data_root/marts/behavior_conversion_daily" \
    --friction-daily-path "$data_root/marts/friction_daily" \
    --exit-daily-path "$data_root/marts/exit_daily" \
    --entry-source-daily-path "$data_root/marts/entry_source_daily" \
    --product-exit-daily-path "$data_root/marts/product_exit_daily" \
    --segment-content-daily-path "$data_root/marts/segment_content_daily" \
    --report-path "$data_root/validation/pipeline-report.json" \
    --require-events
}

# 시작 단계를 고른다. Q2 는 cleaned_events 를 통째로 다시 만들어 오래 걸리므로,
# Fact·Mart 만 고쳤을 때 되돌릴 이유가 없다 (Jira 277 에서 81분을 버렸다).
#   run-batch      Q2~Q5 (기본)
#   run-batch q3   Q3~Q5 — cleaned_events 를 그대로 쓴다
#   run-batch q4   Q4~Q5 — Fact 까지 그대로 쓴다
run_batch_pipeline() {
  local from_stage="${1:-q2}"
  case "$from_stage" in
    q2|q3|q4) ;;
    *)
      echo "run-batch: 시작 단계는 q2|q3|q4 중 하나다 (받은 값: $from_stage)" >&2
      exit 2
      ;;
  esac

  if [[ "$from_stage" == "q2" ]]; then
  submit_job /opt/project/streaming/jobs/clean_events_job.py \
    --input-path "$data_root/raw_events" \
    --cleaned-path "$data_root/processed/cleaned_events" \
    --bad-path "$data_root/processed/bad_events" \
    --duplicate-path "$data_root/processed/duplicate_events"
  fi

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
    --commons-hash-salt "${COMMONS_HASH_SALT:-}"
  )
  if [[ -n "${REGISTERED_PRODUCT_BRAND_PATH:-}" ]]; then
    derive_args+=(
      --registered-product-brand-path "$REGISTERED_PRODUCT_BRAND_PATH"
    )
  fi
  if [[ "$from_stage" != "q4" ]]; then
    submit_job /opt/project/streaming/jobs/derive_facts_job.py "${derive_args[@]}"
  fi

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
    --persona-segment-path "$data_root/marts/persona_segment_daily_kpi"
    --persona-bridge-path /opt/project/contracts/persona/data/pcall/bridge_persona_segment.jsonl
    --price-band-path "$data_root/marts/brand_price_band_daily_kpi"
    --banner-daily-path "$data_root/marts/banner_daily"
    --user-trait-daily-path "$data_root/marts/user_trait_daily"
    --cross-brand-daily-path "$data_root/marts/cross_brand_daily"
    --baseline-path "$data_root/marts/analytics_baseline"
    --trait-weights-path /opt/project/contracts/user-trait-weights.json
    --feature-vocab-path /opt/project/contracts/product-feature-vocab.json
    --affinity-lift-path /opt/project/batch/ingest/data/affinity_lift.csv
    --behavior-weights-path /opt/project/frontend/src/types/log.ts
    --dim-brand-path "$data_root/processed/dim_brand"
    --brand-cohort-path "$data_root/marts/brand_cohort_dim"
    --commons-cohort-path "$data_root/marts/commons_cohort_weekly"
    --content-interest-path "$data_root/processed/content_interest_fact"
    --section-dwell-path "$data_root/processed/section_dwell_agg"
    --content-daily-path "$data_root/marts/content_daily_kpi"
    --content-conversion-path "$data_root/marts/content_conversion_daily"
    --behavior-conversion-path "$data_root/marts/behavior_conversion_daily"
    --friction-daily-path "$data_root/marts/friction_daily"
    --exit-daily-path "$data_root/marts/exit_daily"
    --entry-source-daily-path "$data_root/marts/entry_source_daily"
    --product-exit-daily-path "$data_root/marts/product_exit_daily"
    --segment-content-daily-path "$data_root/marts/segment_content_daily"
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
    run_batch_pipeline "${2:-q2}"
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
    echo "Usage: $0 {up|start-q1|stop-q1|run-batch [q2|q3|q4]|validate|status|down}" >&2
    exit 2
    ;;
esac
