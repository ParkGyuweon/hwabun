#!/usr/bin/env bash
# Helpers the Jenkinsfile calls around `docker compose up -d --build` on EC2-1.
#
#   bash deploy/ec2-1/deploy-helpers.sh tag-previous <service...>
#       Before the build: tag the image each running service uses as <image>:previous,
#       so the last working image survives the rebuild (one-command rollback).
#   bash deploy/ec2-1/deploy-helpers.sh tag-commit <sha> <service...>
#       After the build: tag the new image as <image>:<sha> and keep only the newest
#       KEEP_IMAGE_TAGS (default 5) commit tags per image.
#   bash deploy/ec2-1/deploy-helpers.sh health <service...>
#       Wait until every deployed service answers its health endpoint. Exit 1 if one
#       never does. This does NOT roll back - the containers stay as they are.
#
# Tagging never fails the deploy (a warning at most). Rollback steps: README "배포 확인과 되돌리기".
#
# Environment:
#   COMPOSE_PROJECT (ec2-1), COMPOSE_FILE_PATH (deploy/ec2-1/docker-compose.yml),
#   EC2_ENV_FILE (required for compose), HEALTH_RETRIES (36), HEALTH_INTERVAL (5 s),
#   KEEP_IMAGE_TAGS (5)
set -uo pipefail

COMPOSE_PROJECT="${COMPOSE_PROJECT:-ec2-1}"
COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-deploy/ec2-1/docker-compose.yml}"
HEALTH_RETRIES="${HEALTH_RETRIES:-36}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
KEEP_IMAGE_TAGS="${KEEP_IMAGE_TAGS:-5}"

dc() {
    docker compose -p "$COMPOSE_PROJECT" --env-file "${EC2_ENV_FILE:?EC2_ENV_FILE is not set}" \
        -f "$COMPOSE_FILE_PATH" "$@"
}

log() { printf '[deploy] %s\n' "$*"; }

# Services built from this repo (the others use a pinned upstream image).
is_built() {
    case "$1" in backend|shop-backend|recommend|nginx) return 0 ;; *) return 1 ;; esac
}

# Prints "<image id> <image name without tag>" for the running container of a service.
service_image() {
    local cid ref id
    cid="$(dc ps -q "$1" 2>/dev/null | head -n1)"
    [ -n "$cid" ] || return 1
    id="$(docker inspect -f '{{.Image}}' "$cid" 2>/dev/null)" || return 1
    ref="$(docker inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null)" || return 1
    printf '%s %s\n' "$id" "${ref%:*}"
}

tag_previous() {
    local svc id name
    for svc in "$@"; do
        is_built "$svc" || continue
        if read -r id name < <(service_image "$svc"); then
            if docker tag "$id" "$name:previous"; then
                log "$svc: current image kept as $name:previous"
            else
                log "WARN: $svc: could not tag $name:previous"
            fi
        else
            log "$svc: no running container, nothing to keep as :previous"
        fi
    done
    return 0
}

tag_commit() {
    local sha="$1"; shift
    local svc id name tag
    for svc in "$@"; do
        is_built "$svc" || continue
        if ! read -r id name < <(service_image "$svc"); then
            log "WARN: $svc: no running container, not tagged"
            continue
        fi
        if docker tag "$id" "$name:$sha"; then
            log "$svc: image tagged $name:$sha"
        else
            log "WARN: $svc: could not tag $name:$sha"
            continue
        fi
        # `docker image ls` lists newest first. Untag old commit tags only; an image
        # still used by a container is never deleted (no -f), only the tag goes.
        docker image ls "$name" --format '{{.Tag}}' \
            | grep -Ev '^(latest|previous|<none>)$' \
            | tail -n +"$((KEEP_IMAGE_TAGS + 1))" \
            | while read -r tag; do
                docker rmi "$name:$tag" >/dev/null 2>&1 && log "$svc: pruned old tag $name:$tag"
            done
    done
    return 0
}

# One probe. HTTP checks run inside the nginx container (busybox wget), because the
# app ports are `expose` only and never reach the host. wget exits non-zero on 4xx/5xx.
probe() {
    local svc="$1" url
    case "$svc" in
        backend)      url="http://backend:8080/actuator/health" ;;
        shop-backend) url="http://shop-backend:8090/actuator/health" ;;
        recommend)    url="http://recommend:8300/health" ;;
        nginx)
            dc exec -T nginx nginx -t >/dev/null 2>&1 || return 1
            # Real TLS path on the host port, pinned to loopback (no hairpin to the public IP).
            if command -v curl >/dev/null 2>&1; then
                curl -fsS -o /dev/null --max-time 5 \
                    --resolve j15a306.p.ssafy.io:443:127.0.0.1 https://j15a306.p.ssafy.io/
            fi
            return
            ;;
        *) return 0 ;;   # prometheus, grafana: not checked
    esac
    dc exec -T nginx wget -q -T 5 -O /dev/null "$url" >/dev/null 2>&1
}

health() {
    local failed="" svc i state
    for svc in "$@"; do
        case "$svc" in backend|shop-backend|recommend|nginx) ;; *) continue ;; esac
        i=1
        while :; do
            state="$(dc ps --format '{{.State}}' "$svc" 2>/dev/null | head -n1)"
            if [ "$state" = "running" ] && probe "$svc"; then
                log "$svc: healthy (attempt $i)"
                break
            fi
            if [ "$i" -ge "$HEALTH_RETRIES" ]; then
                log "ERROR: $svc not healthy after $((HEALTH_RETRIES * HEALTH_INTERVAL))s (state: ${state:-missing})"
                dc logs --tail=80 "$svc" 2>&1 | sed "s/^/[$svc] /"
                failed="$failed $svc"
                break
            fi
            i=$((i + 1))
            sleep "$HEALTH_INTERVAL"
        done
    done
    if [ -n "$failed" ]; then
        log "ERROR: health check failed:$failed - see README '배포 확인과 되돌리기' to roll back"
        return 1
    fi
    return 0
}

cmd="${1:-}"; shift || true
case "$cmd" in
    tag-previous) tag_previous "$@" ;;
    tag-commit)   [ "$#" -ge 1 ] || { echo "usage: tag-commit <sha> <service...>" >&2; exit 2; }; tag_commit "$@" ;;
    health)       health "$@" ;;
    *) echo "usage: $0 {tag-previous|tag-commit <sha>|health} <service...>" >&2; exit 2 ;;
esac
