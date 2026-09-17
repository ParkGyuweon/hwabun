#!/usr/bin/env bash
set -Eeuo pipefail

# EC2-2 daily batch entrypoint.
# Q1 stays running as a Compose service. This job rebuilds Q2~Q5 outputs and
# publishes the completed marts to MySQL through the dw projection container.

repo_root="${HWABUN_REPO_ROOT:-/home/ubuntu/S15P21A306}"
compose_dir="$repo_root/deploy/ec2-2"
lock_path="${DAILY_BATCH_LOCK_PATH:-/opt/hwabun/data/.hwabun-daily-batch.lock}"

mkdir -p "$(dirname "$lock_path")"
exec 9>"$lock_path"
if ! flock -n 9; then
  echo "daily batch is already running; skip this invocation" >&2
  exit 0
fi

cd "$compose_dir"
compose=(docker compose --project-directory "$compose_dir")

wait_for_service() {
  local service="$1"
  local port="$2"
  local attempt

  for attempt in $(seq 1 60); do
    if "${compose[@]}" exec -T "$service" bash -ec "bash -c '</dev/tcp/127.0.0.1/$port'" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done

  echo "$service did not become ready on port $port" >&2
  return 1
}

echo "starting Spark services"
"${compose[@]}" up -d --no-build spark-master spark-worker
wait_for_service spark-master 8080
wait_for_service spark-worker 8081

if ! "${compose[@]}" exec -T spark-master bash -ec '
  test -n "${COMMONS_HASH_SALT//[[:space:]]/}"
'; then
  echo "COMMONS_HASH_SALT is missing in spark-master; set it in .env and recreate spark-master before running Q2~Q5" >&2
  exit 1
fi

echo "running Q2~Q5"
"${compose[@]}" exec -T spark-master bash -ec '
  set -Eeuo pipefail
  for job in clean_events_job derive_facts_job build_marts_job validate_pipeline_job; do
    args=()
    if [ "$job" = validate_pipeline_job ]; then
      args=(--require-events --report-path /opt/project/data/validation/pipeline-report.json)
    fi
    /opt/spark/bin/spark-submit \
      --master spark://spark-master:7077 \
      --deploy-mode client \
      --conf spark.driver.host=spark-master \
      --conf spark.driver.bindAddress=0.0.0.0 \
      --conf spark.cores.max=2 \
      /opt/project/streaming/jobs/${job}.py "${args[@]}"
  done
'

echo "publishing DW marts"
"${compose[@]}" --profile dw run --rm --no-deps dw-projection

echo "daily batch completed"
