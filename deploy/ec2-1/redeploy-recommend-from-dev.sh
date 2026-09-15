#!/usr/bin/env bash
# EC2-1 에서 추천 컨테이너만 origin/dev 기준으로 재빌드·교체한다.
# 레포의 체크아웃 브랜치(백엔드가 ec2-1-deploy 로 쓰는 중)는 건드리지 않고 별도 워크트리 /home/ubuntu/dev-build 에서 빌드한다.
# 로컬에서:  bash deploy/ec2-1/redeploy-local.sh   (Windows 레지스트리의 GITLAB_TOKEN 을 읽어 이 스크립트를 EC2 로 흘려 보낸다)
# EC2 레포에는 GitLab 자격증명이 없다. 첫 줄로 GL_TOKEN=... 이 들어오면 그 fetch 한 번에만 쓰고 어디에도 저장하지 않는다.
set -euo pipefail
REPO=/home/ubuntu/S15P21A306
TREE=/home/ubuntu/dev-build
ENVF=$REPO/deploy/ec2-1/.env
GL_URL=https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A306.git

cd "$REPO"
if [ -n "${GL_TOKEN:-}" ]; then
  git fetch -q "https://oauth2:${GL_TOKEN}@${GL_URL#https://}" "+refs/heads/dev:refs/remotes/origin/dev"
else
  git fetch -q origin dev
fi
if [ -d "$TREE/.git" ] || [ -f "$TREE/.git" ]; then
  (cd "$TREE" && git checkout -q --detach origin/dev)
else
  git worktree add -f "$TREE" origin/dev >/dev/null
fi
cd "$TREE" && echo "build tree: $(git log --oneline -1)"

cd "$TREE/deploy/ec2-1"
# --no-cache: 09-15 11:00 빌드가 워크트리 파일이 바뀌었는데도 전 레이어를 캐시로 재사용해 옛 이미지를 그대로 냈다
# (COPY batch/serving/ 에 새 파일이 있었는데도). 전체 빌드가 1분 남짓이라 매번 새로 만든다.
sudo DOCKER_BUILDKIT=1 docker compose --env-file "$ENVF" build --no-cache recommend 2>&1 | tail -2
sudo docker compose --env-file "$ENVF" up -d --no-deps recommend
sleep 25
LATEST=$(sudo docker images --no-trunc -q ec2-1-recommend:latest | head -1)
RUNNING=$(sudo docker inspect ec2-1-recommend-1 --format '{{.Image}}')
echo "image latest=${LATEST:7:12} running=${RUNNING:7:12} $([ "$LATEST" = "$RUNNING" ] && echo OK || echo MISMATCH)"
sudo docker compose --env-file "$ENVF" exec -T recommend python - <<'PY'
import json, os, urllib.request
h = json.load(urllib.request.urlopen("http://127.0.0.1:8300/health"))
print("health: ok", h["ok"], "products", h["products"], "registered", h["registered_products"],
      "new_now", h["new_brand_rule"]["new_now"], "user_trait", (h.get("user_trait") or {}).get("source"))
v = json.load(open("/app/contracts/product-feature-vocab.json"))
print("vocab", v["version"], v["price_bin_edges"])
print("code:", "user_trait.py" if os.path.exists("/app/batch/serving/user_trait.py") else "NO user_trait.py",
      "| git tree:", open("/app/BUILD_TREE").read().strip() if os.path.exists("/app/BUILD_TREE") else "-")
PY
