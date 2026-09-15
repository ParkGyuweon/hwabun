#!/usr/bin/env bash
# Windows(Git Bash) 에서 실행: bash deploy/ec2-1/redeploy-local.sh
# 레지스트리 환경변수 GITLAB_TOKEN 을 읽어 EC2 스크립트의 첫 줄로 넘긴다 (화면·이력에 남기지 않음).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
KEY=${EC2_KEY:-$HOME/Downloads/J15A306T.pem}
T=$(powershell -NoProfile -Command "(Get-ItemProperty HKCU:\Environment).GITLAB_TOKEN" | tr -d '\r\n')
[ -n "$T" ] || { echo "GITLAB_TOKEN 이 레지스트리에 없다 (setx GITLAB_TOKEN ...)"; exit 1; }
{ printf 'GL_TOKEN=%s\n' "$T"; cat "$HERE/redeploy-recommend-from-dev.sh"; } \
  | ssh -i "$KEY" ubuntu@j15a306.p.ssafy.io bash -s
