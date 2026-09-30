#!/usr/bin/env bash
# shop_backend 스키마 마이그레이션을 shop-backend (재)기동 직전에 적용한다.
#
#   bash deploy/ec2-1/apply-shop-migrations.sh          # Jenkins "EC2 배포" 단계가 부른다
#   EC2_ENV_FILE=/home/ubuntu/S15P21A306/deploy/ec2-1/.env \
#     sudo -E bash deploy/ec2-1/apply-shop-migrations.sh # 손으로 돌릴 때 (repo 루트에서)
#
# 왜: shop-backend 는 JPA ddl-auto: validate 라서, 엔티티에 있는 컬럼이 DB 에 없으면
# 앱이 뜨지 않는다. 마이그레이션을 잊고 배포하면 사이트가 멈춘다. 그래서 배포가 직접 돌린다.
#
# 규칙:
#   - 아래 MIGRATIONS 목록만, 적힌 순서대로 돌린다. 폴더를 통째로 돌리지 않는다.
#   - 목록에는 "다시 돌려도 아무 일 없는" 파일만 넣는다 (information_schema 로 있는지 보고
#     없을 때만 PREPARE/EXECUTE 로 ALTER). 새 파일을 넣기 전에 그 점을 먼저 확인한다.
#   - 하나라도 실패하면 즉시 멈추고 exit 1 → Jenkins 는 shop-backend 를 다시 띄우지 않는다.
#
# 대상 DB: 이 compose(-p ec2-1)의 mysql 서비스 — shop-backend 가 jdbc:mysql://mysql:3306 으로 붙는 그 DB.
# DB 이름(MYSQL_DATABASE)과 root 비밀번호(MYSQL_ROOT_PASSWORD)는 컨테이너 자신의 환경에서 읽는다
# (backup-mysql.sh 와 같은 방식). 비밀번호는 명령줄·로그에 나오지 않는다.
#
# Environment (all optional):
#   COMPOSE_PROJECT (ec2-1), COMPOSE_FILE_PATH (deploy/ec2-1/docker-compose.yml),
#   EC2_ENV_FILE (compose 에 필요, Jenkins 가 넣어 준다),
#   MYSQL_CONTAINER  컨테이너 이름을 직접 지정 (지정하면 compose 대신 docker exec 로 붙는다)
set -euo pipefail

cd "$(dirname "$0")/../.."    # repo 루트

MIGRATIONS=(
    shop_backend/migrations/20260929_add_member_signup_consent.sql   # member 가입 동의 5칸 (NULL 허용)
    shop_backend/migrations/20260929_add_member_withdrawal.sql       # member.status 에 WITHDRAWN, withdrawn_at (NULL 허용)
)

COMPOSE_PROJECT="${COMPOSE_PROJECT:-ec2-1}"
COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-deploy/ec2-1/docker-compose.yml}"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-}"

log() { printf '[shop-migrate] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# 컨테이너 안에서 root 로 mysql 클라이언트를 돌린다. DB·비밀번호는 컨테이너 env 에서만 쓴다.
in_mysql() {
    local inner='MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 "$@" "$MYSQL_DATABASE"'
    if [ -n "$MYSQL_CONTAINER" ]; then
        docker exec -i "$MYSQL_CONTAINER" sh -c "$inner" sh "$@"
    else
        docker compose -p "$COMPOSE_PROJECT" --env-file "${EC2_ENV_FILE:?EC2_ENV_FILE is not set}" \
            -f "$COMPOSE_FILE_PATH" exec -T mysql sh -c "$inner" sh "$@"
    fi
}

for f in "${MIGRATIONS[@]}"; do
    [ -f "$f" ] || die "migration file missing: $f"
done

db="$(in_mysql -N -B -e 'SELECT DATABASE()')" || die "cannot reach the shop_backend MySQL (is the mysql service running?)"
log "target database: $db"

for f in "${MIGRATIONS[@]}"; do
    log "apply $f"
    in_mysql < "$f" || die "failed: $f - shop-backend is NOT restarted"
done

# 확인: 앱(validate)이 요구하는 컬럼이 실제로 있는지 본다.
cols="$(in_mysql -N -B -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'member' AND column_name IN ('terms_agreed_at','privacy_agreed_at','skin_info_agreed_at','behavior_link_agreed_at','consent_version','withdrawn_at')")"
[ "$cols" = "6" ] || die "member columns check failed (found $cols of 6)"
log "ok: member has all 6 columns"
