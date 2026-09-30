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

# Freshness signal: every run that got the lock leaves a small JSON with its
# result and the time of the last fully successful run. Alerting only has to
# read one file (check-batch-freshness.sh), and a failed run keeps the previous
# last_success_at so staleness is visible even when nobody reads the journal.
status_path="${DAILY_BATCH_STATUS_PATH:-/opt/hwabun/data/validation/daily-batch-status.json}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
stage="startup"
validate_rc=0
publish_rc=0

write_status() {
  local rc="$1"
  local finished_at last_success status tmp
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  last_success=""
  if [ -f "$status_path" ]; then
    last_success="$(sed -n 's/^  "last_success_at": "\(.*\)",\{0,1\}$/\1/p' "$status_path" | head -n 1)"
  fi
  if [ "$rc" -eq 0 ]; then
    status="success"
    last_success="$finished_at"
  else
    status="failed"
  fi
  mkdir -p "$(dirname "$status_path")"
  tmp="$status_path.tmp.$$"
  cat >"$tmp" <<JSON
{
  "status": "$status",
  "exit_code": $rc,
  "failed_stage": "$([ "$rc" -eq 0 ] && echo "" || echo "$stage")",
  "q5_rc": $validate_rc,
  "publish_rc": $publish_rc,
  "started_at": "$started_at",
  "finished_at": "$finished_at",
  "last_success_at": "$last_success"
}
JSON
  mv -f "$tmp" "$status_path"
}
trap 'write_status $? || echo "WARNING: could not write $status_path" >&2' EXIT

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

stage="spark_startup"
echo "starting Spark services"
"${compose[@]}" up -d --no-build spark-master spark-worker
wait_for_service spark-master 8080
wait_for_service spark-worker 8081

stage="salt_check"
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

# Optional Q1 small-file compaction of yesterday's (UTC) raw_ingest_date
# partition, before Q2 reads Raw. Default OFF: Q1's Parquet file sink keeps a
# _spark_metadata log, and while that log exists Q2 lists Raw files from it,
# so the job detects the log and skips itself (see compact_raw_partition_job.py).
# Turning this on is harmless today but only pays off once Q2 stops relying on
# the sink log. A failure never blocks Q2: the original partition is kept.
if [ "${RAW_COMPACTION_ENABLED:-0}" = "1" ]; then
  stage="raw_compaction"
  echo "compacting previous raw_ingest_date partition"
  submit compact_raw_partition_job \
    || echo "WARNING: raw compaction failed; original partition kept, continuing" >&2
fi

# Q2~Q4 build the Marts. A failure here must stop the run: publishing Marts built
# from a failed stage would put wrong numbers on the dashboard.
echo "running Q2~Q4"
for job in clean_events_job derive_facts_job build_marts_job; do
  stage="$job"
  submit "$job"
done

# Q5 is a report, not a gate. It checks every Mart invariant that
# validate_pipeline_job defines -- 162 of them on 2026-09-18 and 166 on 2026-09-23, and the count grows
# as the data part adds checks, so read that number as a snapshot. A handful of
# bad rows used to abort the run before the publish step below
# (set -e), leaving 22 correct Marts unpublished and the dashboard blank. On
# 2026-09-18 that was 13 failures, 7 of them from one real user on a stale
# frontend bundle. Record the failure, publish anyway, and keep it in the exit
# code so systemd and CI still mark the run as failed.
stage="validate_pipeline_job"
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
stage="dw_projection"
echo "publishing DW marts"
publish_rc=0
"${compose[@]}" --profile dw run --rm --no-deps dw-projection || publish_rc=$?
if [ "$publish_rc" -ne 0 ]; then
  echo "WARNING: DW publish reported failures (rc=$publish_rc)." >&2
  echo "         See the dw-projection report for the per-Mart status." >&2
fi

stage="q5_or_publish"
if [ "$validate_rc" -ne 0 ] || [ "$publish_rc" -ne 0 ]; then
  echo "daily batch completed with failures (Q5=$validate_rc, publish=$publish_rc)" >&2
  exit 1
fi

echo "daily batch completed"
