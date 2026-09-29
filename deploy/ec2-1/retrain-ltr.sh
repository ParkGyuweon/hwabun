#!/usr/bin/env bash
# LTR 재학습 한 번 — 컨테이너 안에서 학습·holdout_a 비교·교체·리로드 (batch/jobs/retrain_ltr.py).
# hwabun-ltr-retrain.timer 가 주 1회 부른다. 손으로: bash ~/S15P21A306/deploy/ec2-1/retrain-ltr.sh
# 산출물은 볼륨 /data/ltr (LTR_MODEL_DIR). 비어 있으면 서버는 이미지 안 모델을 쓴다.
set -euo pipefail
C=${RECOMMEND_CONTAINER:-ec2-1-recommend-1}
sudo docker exec "$C" python /app/batch/jobs/retrain_ltr.py \
  --out-dir /data/ltr --reload-url http://127.0.0.1:8300/api/model/reload "$@"
