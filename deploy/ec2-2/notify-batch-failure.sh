#!/usr/bin/env bash
set -Euo pipefail

# systemd OnFailure= target for hwabun-daily-batch.service (via
# hwabun-batch-notify@.service). Posts one Mattermost-compatible message
# ({"text": ...}; Slack incoming webhooks accept the same shape) to
# HWABUN_ALERT_WEBHOOK_URL. Unset URL -> print and exit 0, so installing the
# hook without a webhook is harmless.
#
#   $1 = failed unit name (systemd passes %i)
#   HWABUN_ALERT_WEBHOOK_URL   webhook URL (put it in /etc/hwabun/alert.env, not in git)
#   DAILY_BATCH_STATUS_PATH    status JSON written by run-daily-batch.sh

unit="${1:-hwabun-daily-batch.service}"
status_path="${DAILY_BATCH_STATUS_PATH:-/opt/hwabun/data/validation/daily-batch-status.json}"
webhook="${HWABUN_ALERT_WEBHOOK_URL:-}"

status_json="(no status file at $status_path)"
if [ -r "$status_path" ]; then
  status_json="$(cat "$status_path")"
fi

text="$(printf ':rotating_light: **%s failed** on %s\n```json\n%s\n```\nsudo journalctl -u %s -n 100 --no-pager' \
  "$unit" "$(hostname)" "$status_json" "$unit")"

if [ -z "${webhook//[[:space:]]/}" ]; then
  echo "HWABUN_ALERT_WEBHOOK_URL is not set; not sending. Message was:" >&2
  echo "$text" >&2
  exit 0
fi

# JSON-escape backslash, double quote, tab and newline for the payload.
escaped="$(printf '%s' "$text" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' | awk 'BEGIN{ORS="\\n"} {print}')"
payload="{\"username\": \"hwabun-batch\", \"text\": \"${escaped}\"}"

if ! curl -fsS -m 10 -H 'Content-Type: application/json' -d "$payload" "$webhook" >/dev/null; then
  echo "failed to post batch failure alert to webhook" >&2
  exit 1
fi
echo "batch failure alert sent for $unit"
