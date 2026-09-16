# EC2-1 deployment

EC2-1은 Docker Compose로 Backend, Nginx, Prometheus, Grafana를 실행한다. Certbot은
EC2 호스트에서 실행하고, Nginx 컨테이너는 호스트의 Webroot와 인증서를 읽기 전용으로
마운트한다.

## 1. 사전 준비

Docker Engine이 이미 설치된 Ubuntu에서는 Compose 플러그인을 설치한다.

```bash
sudo apt-get update
sudo apt-get install docker-compose-plugin
docker compose version
```

환경 변수와 Certbot Webroot를 준비한다.

```bash
cd deploy/ec2-1
cp .env.example .env
sudo mkdir -p /opt/hwabun/certbot/www/.well-known/acme-challenge
```

`.env`의 `KAFKA_BOOTSTRAP_SERVERS`와 Grafana 비밀번호를 실제 값으로 변경한다. DNS의
`j15a306.p.ssafy.io`는 EC2-1 공인 IP를 가리켜야 하며 보안 그룹에서 80, 443 포트를
허용해야 한다.

추천 서버가 읽는 `dw`는 EC2-1의 `shop-backend-mysql` 안에 둔다. MySQL Compose가
먼저 만든 `shop-backend-db` 네트워크에 추천 컨테이너를 연결하므로 `.env`의
`DW_MYSQL_HOST=shop-backend-mysql`, `DW_MYSQL_PORT=3306`을 유지한다. 최초 기동
순서는 다음과 같다.

```bash
cd ~/S15P21A306/shop_backend
sudo docker compose -f docker-compose.mysql.yml up -d
sudo docker network inspect shop-backend-db

cd ~/S15P21A306/deploy/ec2-1
sudo docker compose up -d --build
```

`shop-backend-db`가 없는 상태에서는 EC2-1 Compose가 external network 오류로 시작하지
않는다. `dw` 스키마 생성과 `dw_reader` 계정 발급은
[`streaming/DW_PROJECTION.md`](../../streaming/DW_PROJECTION.md)의 관리자 절차를
따른다.

## 2. 최초 인증서 발급

기본 Nginx 설정은 HTTPS 인증서 파일을 참조하므로, Compose를 처음 실행하기 전에
호스트의 Certbot standalone 서버로 인증서를 발급한다. 이때 80 포트를 사용하는 다른
프로세스가 없어야 한다.

```bash
sudo certbot certonly --standalone \
  -d j15a306.p.ssafy.io \
  --email YOUR_EMAIL@example.com \
  --agree-tos \
  --no-eff-email
```

## 3. HTTPS 실행

인증서 발급 후 단일 Compose 파일로 전체 서비스를 실행한다.

```bash
sudo docker compose up -d --build
```

적용된 설정과 외부 응답을 확인한다.

```bash
sudo docker compose exec nginx nginx -t
curl -I http://j15a306.p.ssafy.io
curl -I https://j15a306.p.ssafy.io
```

## MySQL 점검용 SSH 터널

MySQL은 EC2의 loopback(`127.0.0.1:3306`)에만 열어 둔다. 보안 그룹에 3306 포트를
추가하지 않는다. IntelliJ Database 도구에서는 MySQL host를 `127.0.0.1`, port를 `3306`으로
두고 SSH tunnel을 켠 뒤 EC2의 `ubuntu` 계정과 private key를 지정한다.

Compose 변경을 반영할 때는 다음처럼 MySQL만 다시 만든다.

```bash
cd /home/ubuntu/S15P21A306/deploy/ec2-1
sudo docker compose up -d mysql
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

출력에 `127.0.0.1:3306->3306/tcp`가 보이면 정상이다.

HTTP는 HTTPS로 리다이렉트되고, ACME 경로는 갱신을 위해 HTTP로 계속 제공된다.

## 4. 인증서 갱신

최초 발급에는 standalone을 사용했으므로, Nginx 실행 후 갱신 방식을 Webroot로
변경한다. Certbot 2.3 이상에서 `reconfigure`는 테스트 갱신에 성공한 설정만 저장한다.

```bash
sudo certbot reconfigure \
  --cert-name j15a306.p.ssafy.io \
  --webroot \
  -w /opt/hwabun/certbot/www
sudo certbot renew --dry-run
```

실제 갱신 후에는 Compose를 실행한 디렉터리에서 Nginx를 다시 불러온다.

```bash
sudo docker compose exec -T nginx nginx -s reload
```

## 추천 추론 서버 (AI, Jira 219 · 2026-09-11 EC2-1 최초 배포)

> **재배포는 로컬에서 한 줄 (2026-09-15, Jira 305):** `bash deploy/ec2-1/redeploy-local.sh`
> EC2 레포(`/home/ubuntu/S15P21A306`)의 체크아웃은 백엔드가 `ec2-1-deploy` 브랜치로 쓰고 있으므로 **dev 로 옮기지 않는다.**
> 스크립트는 `origin/dev` 를 별도 워크트리 `/home/ubuntu/dev-build` 에 받아 `recommend` 만 빌드·교체한다
> (`redeploy-recommend-from-dev.sh`). EC2 레포에 GitLab 자격증명이 없어 fetch 는 로컬 레지스트리의 `GITLAB_TOKEN`(scope api)을
> 첫 줄로 흘려 보내 그 한 번에만 쓴다 — 어디에도 저장되지 않는다. 끝에 `/health` 와 어휘집 버전이 찍히면 성공.
> 예전 bundle→scp 절차(09-11)는 더 쓰지 않는다.

`recommend` 서비스는 파이썬 FastAPI 추천 서버다 (`deploy/recommend.Dockerfile`, 계약
`contracts/recommendation-io-spec.md` §5). 모델·페르소나·산출물이 이미지 안에 들어가고,
판매자가 등록한 상품은 `/data` 볼륨(`recommend-data`)에 남는다.

함정 두 가지:
- **볼륨은 이미지 갱신으로 안 바뀐다.** `/data/registered_products.jsonl` 은 최초 배포 때 값이 그대로다 (09-15: SB 8개 price_krw 가 옛 1,400 환산값).
  shop-backend 가 떠 있으면 카탈로그 동기화가 백엔드 원화값으로 덮어쓴다. 급하면
  `sudo docker cp /home/ubuntu/dev-build/batch/ingest/data/serving/registered_products.jsonl ec2-1-recommend-1:/data/ && sudo docker restart ec2-1-recommend-1`.
- dev 의 compose 에 없는 서비스(shop-backend·mysql, `ec2-1-deploy` 브랜치)가 떠 있으면 `Found orphan containers` 경고가 난다. 정상이고 건드리지 않는다. `--remove-orphans` 를 붙이지 않는다.

수동으로 할 때 (EC2 안에서):

```bash
# 빌드는 BuildKit 이어야 한다 — Dockerfile 옆의 recommend.Dockerfile.dockerignore 를 쓴다
cd /home/ubuntu/dev-build/deploy/ec2-1     # dev 워크트리. .env 는 원 레포 것을 쓴다
sudo DOCKER_BUILDKIT=1 docker compose --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env build recommend
sudo docker compose --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env up -d --no-deps recommend
sudo docker compose --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env exec recommend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8300/health').read()[:200])"
```

| 항목 | 값 |
| --- | --- |
| 포트 | 8300, 컨테이너 네트워크 안에서만 (`expose`). 인증이 없어 외부에 열지 않는다 |
| 백엔드 → 추천 | `RECOMMEND_URL=http://recommend:8300` — 읽는 쪽은 백엔드 프록시 브랜치 `feat/recommendation-proxy-mvp`(dev 미머지, 2026-09-14). dev 의 `backend/`(수집기)는 이 값을 쓰지 않는다 |
| 추천 실시간 현황 | `GET /live`(시연용 페이지)·`/live/stats` — 내부 전용. 밖에 보이려면 nginx `location = /live` · `location /live/` → `http://recommend:8300` 한 블록 추가 (Jira 295) |
| 추천 신규 규칙 | `NEW_BRAND_DAYS=14` · `NEW_BRAND_ALWAYS_PREFIX=SB` — SSAFY Beauty 8개는 09-23 이후에도 신규(히어로 `new_brand` 후보) 로 남는다 (Jira 249) |
| 기동 시간 | 첫 요청 전 모델·페르소나 로드 약 4~10초. `start_period` 40초 뒤 헬스체크 |
| 워커 | **1**. 사용자 상태·등록 상품이 프로세스 메모리라 늘리면 답이 갈린다. 확장은 Redis 도입 뒤 |
| 등록 상품 | `POST /api/products` 가 `/data/registered_products.jsonl` 에 append. 첫 기동에 이미지 시드(SSAFY Beauty 8개) 복사. 볼륨을 지우면 시드로 돌아간다 |
| 모델 교체 | `batch/ingest/data/serving/ltr_model.pkl` 을 바꾸고 이미지를 다시 빌드. `requirements.txt` 의 scikit-learn 버전이 학습 버전과 같아야 한다 |
| 행동 유입 | `KAFKA_BOOTSTRAP_SERVERS`(백엔드와 같은 값)가 있으면 `activity-events` 를 group `recommend-state-v1` 로 구독해 세션 상태를 초 단위로 갱신 (Jira 226). Spark 와 별도 group. `/health.kafka_state` 의 `connected`·`lag`·`last_processed_at` 확인 (Jira 232: `connected` 가 브로커 다운 중에도 true 로 남던 버그 수정, 로컬 실측 소비 약 35,000건/초). 비우면 `POST /api/events` 만 |

nginx 는 `/api/` 를 `backend`(수집기) 8080 으로만 보낸다. 추천 경로는 쇼핑몰 백엔드(shop_backend)가 프록시하는 형태로
확정됐고(요청서 §5, 프록시 브랜치 `feat/recommendation-proxy-mvp` 는 2026-09-11 기준 dev 미머지) nginx 에는 따로 열지 않는다.
로컬 개발은 Vite 프록시(`frontend/vite.config.ts`)가 8300 으로 직결한다. 임시로 직접 열어야 하면 `location /api/recommend { proxy_pass http://recommend:8300; }`
를 `/api/` 앞에 두면 된다.
