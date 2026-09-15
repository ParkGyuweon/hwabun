#!/usr/bin/env bash
# 진단용: dev 워크트리에서 recommend 이미지를 캐시 없이 빌드하고 출력을 전부 보여준다 (컨테이너는 건드리지 않는다).
# 실행: bash deploy/ec2-1/build-verbose-local.sh
set -euo pipefail
KEY=${EC2_KEY:-$HOME/Downloads/J15A306T.pem}
ssh -i "$KEY" ubuntu@j15a306.p.ssafy.io bash -s <<'REMOTE'
set -uo pipefail
cd /home/ubuntu/dev-build && echo "tree: $(git log --oneline -1)" && ls -la batch/serving/user_trait.py
cd deploy/ec2-1
echo "== compose config (build block)"
sudo docker compose --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env config 2>/dev/null | sed -n '/^  recommend:/,/^  [a-z]/p' | grep -E "context|dockerfile|image" || true
echo "== build --no-cache --progress=plain"
sudo DOCKER_BUILDKIT=1 docker compose --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env build --no-cache --progress=plain recommend 2>&1 | grep -vE "^#[0-9]+ (sha256|extracting|DONE 0\.0s)" | tail -60
echo "== images"
sudo docker images -a --format "{{.ID}} {{.Repository}}:{{.Tag}} {{.CreatedAt}}" | grep -i "recommend\|<none>" | head -5
REMOTE
