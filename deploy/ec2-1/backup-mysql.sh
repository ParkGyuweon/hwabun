#!/usr/bin/env bash
# EC2-1 MySQL backup: shop_backend + dw -> gzip -> local dir (7-day retention),
# optionally copied to S3.
#
#   sudo bash deploy/ec2-1/backup-mysql.sh            # one-off run
#   systemd: hwabun-mysql-backup.service / .timer     # NOT enabled by default (README)
#
# Reads the root password from the MySQL container's own environment
# (MYSQL_ROOT_PASSWORD, set by compose from .env), so this script needs no secrets
# and never puts the password on a command line.
#
# Each database is dumped WITHOUT --databases (no CREATE DATABASE / USE), so a file
# can be restored into the original database or into a scratch one for a test.
# --single-transaction takes a consistent InnoDB snapshot without locking tables,
# so it is safe while the site is serving.
#
# Environment (all optional):
#   MYSQL_CONTAINER    container name. Default: auto-detect ec2-1-mysql-1 or
#                      shop-backend-mysql (fails if both or neither are running)
#   BACKUP_DATABASES   space-separated list. Default: "shop_backend dw"
#                      (a database that does not exist is skipped with a warning)
#   BACKUP_DIR         Default: /var/backups/hwabun/mysql
#   RETENTION_DAYS     local files older than this are deleted. Default: 7
#   BACKUP_S3_URI      e.g. s3://bucket/hwabun/mysql . Empty = no upload.
#                      Needs the aws CLI and credentials (instance role) on the host.
set -euo pipefail

BACKUP_DATABASES="${BACKUP_DATABASES:-shop_backend dw}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/hwabun/mysql}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_S3_URI="${BACKUP_S3_URI:-}"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-}"

log() { printf '[backup-mysql %s] %s\n' "$(date '+%F %T')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found"
case "$RETENTION_DAYS" in ''|*[!0-9]*) die "RETENTION_DAYS must be a number" ;; esac

running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" = "true" ]; }

if [ -z "$MYSQL_CONTAINER" ]; then
    found=""
    for c in ec2-1-mysql-1 shop-backend-mysql; do
        if running "$c"; then found="$found $c"; fi
    done
    set -- $found
    [ "$#" -eq 1 ] || die "cannot pick the MySQL container automatically (running:${found:- none}). Set MYSQL_CONTAINER."
    MYSQL_CONTAINER="$1"
fi
running "$MYSQL_CONTAINER" || die "container $MYSQL_CONTAINER is not running"
log "container: $MYSQL_CONTAINER"

# Run a client inside the container as root; the password stays in the container env.
in_mysql() {
    docker exec -i "$MYSQL_CONTAINER" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec "$@"' sh "$@"
}

umask 077
mkdir -p "$BACKUP_DIR"
stamp="$(date '+%Y%m%dT%H%M%S')"
failed=0
made=""

for db in $BACKUP_DATABASES; do
    exists="$(in_mysql mysql -uroot -N -B -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${db}'" || true)"
    if [ "$exists" != "$db" ]; then
        log "WARN: database '$db' does not exist in $MYSQL_CONTAINER - skipped"
        continue
    fi

    out="$BACKUP_DIR/${db}-${stamp}.sql.gz"
    tmp="$out.partial"
    log "dump $db -> $out"
    # pipefail makes a mysqldump failure fail this pipeline; the .partial file is
    # only renamed after gzip finished, so a half-written dump never looks complete.
    if in_mysql mysqldump -uroot \
            --single-transaction --quick \
            --routines --triggers --events \
            --hex-blob --no-tablespaces --set-gtid-purged=OFF \
            --default-character-set=utf8mb4 \
            "$db" | gzip -c > "$tmp" && gzip -t "$tmp"; then
        mv "$tmp" "$out"
        made="$made $out"
        log "ok $db ($(du -h "$out" | cut -f1))"
    else
        rm -f "$tmp"
        log "ERROR: dump of $db failed"
        failed=1
    fi
done

if [ -n "$BACKUP_S3_URI" ] && [ -n "$made" ]; then
    if command -v aws >/dev/null 2>&1; then
        for f in $made; do
            if aws s3 cp --only-show-errors "$f" "${BACKUP_S3_URI%/}/$(basename "$f")"; then
                log "s3 ok $(basename "$f")"
            else
                log "ERROR: s3 upload failed for $f (local copy kept)"
                failed=1
            fi
        done
    else
        log "ERROR: BACKUP_S3_URI is set but the aws CLI is not installed (local copies kept)"
        failed=1
    fi
fi

# Retention: only files this script names, only in BACKUP_DIR (no recursion).
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name '*.sql.gz' -o -name '*.sql.gz.partial' \) \
    -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/[backup-mysql] removed old /' || true

[ -n "$made" ] || { log "ERROR: nothing was backed up"; exit 1; }
exit "$failed"
