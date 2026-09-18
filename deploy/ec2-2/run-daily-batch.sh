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

submit() {
  # One spark-submit inside spark-master. $1 = job module, rest = job args.
  local job="$1"; shift
  "${compose[@]}" exec -T spark-master bash -ec '
    set -Eeuo pipefail
    job="$1"; shift
    /opt/spark/bin/spark-submit \
      --master spark://spark-master:7077 \
      --deploy-mode client \
      --conf spark.driver.host=spark-master \
      --conf spark.driver.bindAddress=0.0.0.0 \
      --conf spark.cores.max=2 \
      /opt/project/streaming/jobs/${job}.py "$@"
  ' _ "$job" "$@"
}

# Q2~Q4 build the Marts. A failure here must stop the run: publishing Marts built
# from a failed stage would put wrong numbers on the dashboard.
echo "running Q2~Q4"
for job in clean_events_job derive_facts_job build_marts_job; do
  submit "$job"
done

# Q5 is a report, not a gate. It checks 159 conditions across the Marts, and a
# handful of bad rows used to abort the run before the publish step below
# (set -e), leaving 22 correct Marts unpublished and the dashboard blank. On
# 2026-09-18 that was 13 of 159 checks, 7 of them from one real user on a stale
# frontend bundle. Record the failure, publish anyway, and keep it in the exit
# code so systemd and CI still mark the run as failed.
echo "running Q5 (validation)"
validate_rc=0
submit validate_pipeline_job \
  --require-events \
  --report-path /opt/project/data/validation/pipeline-report.json || validate_rc=$?
if [ "$validate_rc" -ne 0 ]; then
  echo "WARNING: Q5 validation failed (rc=$validate_rc); publishing anyway." >&2
  echo "         See data/validation/pipeline-report.json for the failing checks." >&2
fi

# The projection publishes each Mart atomically (staging table + RENAME) and keeps
# going when one Mart fails, so a single bad Mart no longer blocks the others.
echo "publishing DW marts"
publish_rc=0
"${compose[@]}" --profile dw run --rm --no-deps dw-projection || publish_rc=$?
if [ "$publish_rc" -ne 0 ]; then
  echo "WARNING: DW publish reported failures (rc=$publish_rc)." >&2
  echo "         See the dw-projection report for the per-Mart status." >&2
fi

if [ "$validate_rc" -ne 0 ] || [ "$publish_rc" -ne 0 ]; then
  echo "daily batch completed with failures (Q5=$validate_rc, publish=$publish_rc)" >&2
  exit 1
fi

echo "daily batch completed"
