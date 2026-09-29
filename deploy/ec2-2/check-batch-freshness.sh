#!/usr/bin/env bash
set -Euo pipefail

# Staleness check for the daily batch, for any monitor/cron that alerts on a
# non-zero exit. Reads the status JSON written by run-daily-batch.sh.
#
#   exit 0  last success is within DAILY_BATCH_MAX_AGE_HOURS (default 26h =
#           one 24h cycle + 2h slack, so a missed night alerts by ~07:00 KST)
#   exit 1  stale, or no successful run recorded
#   exit 2  status file missing/unreadable

status_path="${DAILY_BATCH_STATUS_PATH:-/opt/hwabun/data/validation/daily-batch-status.json}"
max_age_hours="${DAILY_BATCH_MAX_AGE_HOURS:-26}"

if [ ! -r "$status_path" ]; then
  echo "STALE: no daily batch status at $status_path" >&2
  exit 2
fi

last_success="$(sed -n 's/^  "last_success_at": "\(.*\)",\{0,1\}$/\1/p' "$status_path" | head -n 1)"
if [ -z "$last_success" ]; then
  echo "STALE: no successful daily batch recorded in $status_path" >&2
  exit 1
fi

now="$(date -u +%s)"
then_s="$(date -u -d "$last_success" +%s)"
age_hours=$(( (now - then_s) / 3600 ))
if [ "$age_hours" -ge "$max_age_hours" ]; then
  echo "STALE: last successful daily batch $last_success (${age_hours}h ago, limit ${max_age_hours}h)" >&2
  exit 1
fi
echo "OK: last successful daily batch $last_success (${age_hours}h ago)"
