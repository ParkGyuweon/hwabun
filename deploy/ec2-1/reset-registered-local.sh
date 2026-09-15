#!/usr/bin/env bash
# EC2-1 추천 컨테이너의 /data/registered_products.jsonl 을 dev 워크트리의 파일(시연 시드 8개)로 되돌리고 재시작한다.
# 쓸 때: 카탈로그 동기화가 원천 200개를 append 해 버린 뒤(Jira 308 이전 이미지), 또는 시드 가격이 옛 환율값일 때.
# 실행: bash deploy/ec2-1/reset-registered-local.sh   (redeploy-local.sh 뒤에)
set -euo pipefail
KEY=${EC2_KEY:-$HOME/Downloads/J15A306T.pem}
ssh -i "$KEY" ubuntu@j15a306.p.ssafy.io bash -s <<'REMOTE'
set -euo pipefail
SRC=/home/ubuntu/dev-build/batch/ingest/data/serving/registered_products.jsonl
echo "before: $(sudo docker exec ec2-1-recommend-1 sh -c 'wc -l < /data/registered_products.jsonl') rows"
sudo docker cp "$SRC" ec2-1-recommend-1:/data/registered_products.jsonl
sudo docker restart ec2-1-recommend-1 >/dev/null
sleep 20
sudo docker exec ec2-1-recommend-1 python - <<'PY'
import json, urllib.request
rows = [json.loads(l) for l in open("/data/registered_products.jsonl", encoding="utf-8") if l.strip()]
print("after:", len(rows), "rows", [(r["product_id"], r.get("price_krw")) for r in rows[:8]])
h = json.load(urllib.request.urlopen("http://127.0.0.1:8300/health"))
print("health: products", h["products"], "registered", h["registered_products"], "new_now", h["new_brand_rule"]["new_now"])
PY
REMOTE
