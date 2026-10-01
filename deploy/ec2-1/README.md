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

## 5. MySQL 백업과 복구

`backup-mysql.sh` 가 `shop_backend` 와 `dw` 를 DB 별로 `mysqldump --single-transaction`
(테이블 잠금 없음, 서비스 중에 돌려도 된다) → gzip 으로 `/var/backups/hwabun/mysql/<db>-<시각>.sql.gz`
에 남기고, 7일 지난 파일은 지운다. `BACKUP_S3_URI` 가 있으면 `aws s3 cp` 로도 올린다.
root 비밀번호는 MySQL 컨테이너 자신의 `MYSQL_ROOT_PASSWORD` 에서 읽으므로 스크립트에 비밀값이 없다.
컨테이너는 `ec2-1-mysql-1` 또는 `shop-backend-mysql` 중 떠 있는 것을 고른다(둘 다/둘 다 아니면 멈춘다 →
`MYSQL_CONTAINER=` 로 지정).

**타이머는 자동으로 켜지지 않는다.** 한 번 손으로 돌려 파일이 생기는지 본 뒤 켠다.

```bash
cd /home/ubuntu/S15P21A306
sudo bash deploy/ec2-1/backup-mysql.sh
sudo ls -lh /var/backups/hwabun/mysql

# (선택) S3 업로드·컨테이너 지정
echo 'BACKUP_S3_URI=s3://<bucket>/hwabun/mysql' | sudo tee /etc/default/hwabun-mysql-backup

# 매일 04:30 KST 실행 등록
sudo cp deploy/ec2-1/hwabun-mysql-backup.service deploy/ec2-1/hwabun-mysql-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hwabun-mysql-backup.timer
systemctl list-timers hwabun-mysql-backup.timer
journalctl -u hwabun-mysql-backup.service -n 50
```

덤프에는 사용자·권한(`mysql` 시스템 DB)이 들어가지 않는다. 새 서버에 복구하면 `dw_reader` · `dw_writer`
계정은 [`streaming/DW_PROJECTION.md`](../../streaming/DW_PROJECTION.md) 절차로 다시 만든다.

### 복구

파일은 `CREATE DATABASE` / `USE` 없이 만들어져 **복구할 DB 를 직접 지정**한다. 각 테이블은
`DROP TABLE IF EXISTS` 후 다시 만들어지므로, 운영 DB 에 바로 붓기 전에 먼저 임시 DB 로 확인한다.

```bash
C=ec2-1-mysql-1            # 또는 shop-backend-mysql
F=/var/backups/hwabun/mysql/shop_backend-20260930T043000.sql.gz

# 1) 임시 DB 에 복구해 내용 확인 (운영 영향 없음)
sudo docker exec $C sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE restore_check"'
gunzip -c "$F" | sudo docker exec -i $C sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot restore_check'
sudo docker exec $C sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SELECT COUNT(*) FROM restore_check.member; SELECT COUNT(*) FROM restore_check.order_item"'

# 2) 운영 DB 로 되돌리기: 쓰는 쪽을 먼저 멈춘다
sudo docker compose -p ec2-1 --env-file deploy/ec2-1/.env -f deploy/ec2-1/docker-compose.yml stop shop-backend
gunzip -c "$F" | sudo docker exec -i $C sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot shop_backend'
sudo docker compose -p ec2-1 --env-file deploy/ec2-1/.env -f deploy/ec2-1/docker-compose.yml start shop-backend

# 3) 정리
sudo docker exec $C sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "DROP DATABASE restore_check"'
```

`dw` 도 같은 방법이다(대상 DB 이름만 `dw`). `dw` 는 EC2-2 의 일일 배치가 다시 발행할 수 있으므로
보통은 `shop_backend` 복구가 우선이다. S3 에서 받을 때는 `aws s3 cp s3://<bucket>/hwabun/mysql/<파일> .`.

## 추천 추론 서버 (AI, Jira 219 · 2026-09-11 EC2-1 최초 배포)

> **재배포는 로컬에서 한 줄 (2026-09-15, Jira 305):** `bash deploy/ec2-1/redeploy-local.sh`
> EC2 레포(`/home/ubuntu/S15P21A306`)의 체크아웃은 백엔드가 `ec2-1-deploy` 브랜치로 쓰고 있으므로 **dev 로 옮기지 않는다.**
> 스크립트는 `origin/dev` 를 별도 워크트리 `/home/ubuntu/dev-build` 에 받아 `recommend` 만 빌드·교체한다
> (`redeploy-recommend-from-dev.sh`). EC2 레포에 GitLab 자격증명이 없어 fetch 는 로컬 레지스트리의 `GITLAB_TOKEN`(scope api)을
> 첫 줄로 흘려 보내 그 한 번에만 쓴다 — 어디에도 저장되지 않는다. 끝에 `/health` 와 어휘집 버전이 찍히면 성공.
> 예전 bundle→scp 절차(09-11)는 더 쓰지 않는다.
>
> **같은 폴더의 다른 한 줄들 (09-17):** `reset-registered-local.sh`(등록 상품 8개 되돌리기) · `reset-demo-local.sh`(시연 상태 초기화 — 기본 dry-run, `--apply` 로 demo_live 정지·session_events·demo_live.log 비우기·`.pos` 삭제·재기동, Jira 347) · `build-verbose-local.sh`.
> **.env 에 AI 가 넣는 키 (09-17 실측값):** `DEMO_LIMIT=9900` · `DEMO_CURRENCY=KRW` · `SPARK_MASTER_UI=http://j15a306a.p.ssafy.io:18080` · `DASHBOARD_URL=https://j15a306.p.ssafy.io/dashboard.html` · `USER_TRAIT_MAX_AGE_DAYS=60`(시연용, 뒤에 14). env 만 바뀌면 재빌드 없이 `docker compose --env-file .env up -d --no-deps recommend`.

`recommend` 서비스는 파이썬 FastAPI 추천 서버다 (`deploy/recommend.Dockerfile`, 계약
`contracts/recommendation-io-spec.md` §5). 모델·페르소나·산출물이 이미지 안에 들어가고,
판매자가 등록한 상품은 `/data` 볼륨(`recommend-data`)에 남는다.

함정 두 가지:
- **볼륨은 이미지 갱신으로 안 바뀐다.** `/data/registered_products.jsonl` 은 최초 배포 때 값이 그대로다 (09-15: SB 8개 price_krw 가 옛 1,400 환산값).
  shop-backend 가 떠 있으면 카탈로그 동기화가 백엔드 원화값으로 덮어쓴다. 급하면
  `sudo docker cp /home/ubuntu/dev-build/batch/ingest/data/serving/registered_products.jsonl ec2-1-recommend-1:/data/ && sudo docker restart ec2-1-recommend-1`.
- shop-backend·mysql 은 이제 dev compose 에도 들어 있다. 그 밖에 compose 에 없는 컨테이너가 떠 있어 `Found orphan containers` 경고가 나면 정상이고 건드리지 않는다. `--remove-orphans` 를 붙이지 않는다.

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
| 백엔드 → 추천 | `RECOMMEND_URL=http://recommend:8300` — 읽는 쪽은 shop_backend `RecommendationClient`(프록시 `feat/recommendation-proxy-mvp` dev 머지 완료). dev 의 `backend/`(수집기)는 이 값을 쓰지 않는다 |
| 추천 실시간 현황 | `GET /live`(시연용 페이지)·`/live/stats` — 내부 전용. 밖에 보이려면 nginx `location = /live` · `location /live/` → `http://recommend:8300` 한 블록 추가 (Jira 295) |
| 추천 신규 규칙 | `NEW_BRAND_DAYS=14` · `NEW_BRAND_ALWAYS_PREFIX=SB` — SSAFY Beauty 8개는 09-23 이후에도 신규(히어로 `new_brand` 후보) 로 남는다 (Jira 249) |
| 기동 시간 | 첫 요청 전 모델·페르소나 로드 약 4~10초. `start_period` 40초 뒤 헬스체크 |
| 워커 | **1**. 사용자 상태·등록 상품이 프로세스 메모리라 늘리면 답이 갈린다. 확장은 Redis 도입 뒤 |
| 등록 상품 | `POST /api/products` 가 `/data/registered_products.jsonl` 에 append. 첫 기동에 이미지 시드(SSAFY Beauty 8개) 복사. 볼륨을 지우면 시드로 돌아간다 |
| 모델 교체 | `batch/ingest/data/serving/ltr_model.pkl` 을 바꾸고 이미지를 다시 빌드. `requirements.txt` 의 scikit-learn 버전이 학습 버전과 같아야 한다 |
| 행동 유입 | `KAFKA_BOOTSTRAP_SERVERS`(백엔드와 같은 값)가 있으면 `activity-events` 를 group `recommend-state-v1` 로 구독해 세션 상태를 초 단위로 갱신 (Jira 226). Spark 와 별도 group. `/health.kafka_state` 의 `connected`·`lag`·`last_processed_at` 확인 (Jira 232: `connected` 가 브로커 다운 중에도 true 로 남던 버그 수정, 로컬 실측 소비 약 35,000건/초). 비우면 `POST /api/events` 만 |

nginx(`deploy/nginx/default.conf`) 경로: `= /api/events` → `backend`(수집기) 8080, `= /api/prescription` · `= /api/headline` → `recommend` 8300
(대시보드 문장, IP 당 분당 6회 제한, Jira 365), 나머지 `/api/` → `shop-backend` 8090. 추천(`/api/recommend`)은 shop_backend 가 프록시하므로
nginx 에 따로 열지 않는다(요청서 §5). 처방 LLM 스위치 `/api/prescription/llm` 과 `/live` · `/pipeline` 은 열려 있지 않다.
로컬 개발은 Vite 프록시(`frontend/vite.config.ts`)가 8300 으로 직결한다. 임시로 직접 열어야 하면 `location /api/recommend { proxy_pass http://recommend:8300; }`
를 `/api/` 앞에 두면 된다.

## 배포 확인과 되돌리기 (Jenkins)

Jenkins `EC2 배포` 단계는 `up -d --build` 앞뒤로 `deploy-helpers.sh` 를 부른다.

1. **배포 전** `tag-previous`: 지금 돌고 있는 컨테이너의 이미지를 `ec2-1-<서비스>:previous` 로 남긴다.
2. **배포 후** `tag-commit`: 새 이미지를 `ec2-1-<서비스>:<커밋 SHA 12자리>` 로 태그한다. 서비스별 최근 5개만 남긴다(`KEEP_IMAGE_TAGS`).
3. **헬스 체크** `health`: 배포한 서비스마다 최대 180초(5초 × 36회) 기다린다. 하나라도 응답이 없으면 로그 80줄을 찍고 **빌드를 실패로 표시한다.**
   - `backend` → `http://backend:8080/actuator/health`, `shop-backend` → `http://shop-backend:8090/actuator/health`,
     `recommend` → `http://recommend:8300/health` (nginx 컨테이너 안에서 `wget`, 앱 포트는 호스트에 안 열려 있다)
   - `nginx` → `nginx -t` + Jenkins 컨테이너에서 `https://j15a306.p.ssafy.io/` 를 EC2 주소(`NGINX_HEALTH_RESOLVE_IP`)로 고정해 호출. EC2 호스트에서 직접 실행할 때는 기본값 127.0.0.1 사용
   - prometheus·grafana 는 확인하지 않는다
   - 수집기 헬스는 Kafka 상태를 따라갈 수 있다. EC2-2 Kafka 가 꺼져 있으면 코드 문제 없이도 빨간 빌드가 된다.

태그 단계는 실패해도 배포를 멈추지 않는다. **헬스 체크 실패 시 자동 롤백은 하지 않는다** — 컨테이너는 새 버전 그대로다.
판단 후 아래처럼 직전 이미지로 되돌린다 (EC2-1, Jenkins 작업공간에서).

```bash
cd /home/ubuntu/S15P21A306/deploy-workspace
DC="docker compose -p ec2-1 --env-file /home/ubuntu/S15P21A306/deploy/ec2-1/.env -f deploy/ec2-1/docker-compose.yml"
SVC=shop-backend                          # backend | shop-backend | recommend | nginx

docker image ls ec2-1-$SVC                 # previous / 커밋 SHA 태그 확인

# 직전 이미지로 (또는 :<SHA> 로 특정 커밋)
docker tag ec2-1-$SVC:previous ec2-1-$SVC:latest
$DC up -d --no-deps --no-build --force-recreate $SVC
bash deploy/ec2-1/deploy-helpers.sh health $SVC   # EC2_ENV_FILE 을 export 해 두고
```

`--no-build` 를 빼면 Compose 가 작업공간 코드로 다시 빌드해 되돌린 이미지를 덮어쓴다. 되돌린 뒤 Jenkins 로
다시 배포하면 그 시점 코드가 새로 올라간다. `:previous` 는 배포 때마다 덮어써지므로 두 단계 이상 전으로 갈 때는
커밋 SHA 태그를 쓴다(이 변경이 들어간 뒤 배포한 이미지부터 생긴다). MySQL 데이터는 이미지와 무관하다 — 데이터는 위 5장 백업으로 되돌린다.

## 발표 기간 배포 순서 (2026-09-30 ~ 발표 끝)

라이브 사이트(`https://j15a306.p.ssafy.io`)로 사흘 내리 발표한다. 배포는 전처럼 Jenkins 수동 빌드이고,
바뀐 것은 **shop-backend 를 다시 띄우기 전에 마이그레이션이 자동으로 돈다**는 것 하나다.

### 가. 언제·어떻게

- **발표와 발표 사이 쉬는 시간에만.** 발표 중에는 누르지 않는다.
- **한 번에 한 서비스.** `DEPLOY_FRONTEND` / `DEPLOY_BACKEND` / `DEPLOY_SHOP_BACKEND` / `DEPLOY_RECOMMEND` 중 하나만 켠다.
  아래 "라. 배포 후 5분 점검" 이 통과하면 다음 것.
- **`DEPLOY_TO_EC2`(자동 판별)는 쓰지 않는다.** 최근 머지에서 `Jenkinsfile` 이나 `deploy/ec2-1/docker-compose.yml` 이
  바뀌었으면 backend·shop-backend·recommend·prometheus·grafana·nginx **전부**를 한꺼번에 다시 만든다.
  이 변경도 `Jenkinsfile` 을 바꾸므로 머지 뒤 첫 자동 판별은 전부 재기동이다.
- shop-backend 배포 전에는 백업을 한 번 떠 둔다: `sudo bash deploy/ec2-1/backup-mysql.sh` (서비스 중에 돌려도 된다, 5장).

### 나. 파라미터별로 무엇이 다시 뜨나

어느 경우든 Jenkins 는 테스트/빌드 검증 → `tag-previous` → (shop-backend 가 대상이면 마이그레이션) →
`docker compose up -d --build --no-deps <서비스>` → `tag-commit` → `health` 순서로 돈다. `--no-deps` 라
**MySQL 은 재시작하지 않는다.** 이미지를 빌드하는 동안은 옛 컨테이너가 그대로 서비스한다.

| 켜는 파라미터 | 다시 만드는 컨테이너 | 사용자에게 보이는 영향 |
| --- | --- | --- |
| `DEPLOY_FRONTEND` | `nginx` — 프론트 번들과 `deploy/nginx/default.conf` 가 한 이미지에 구워진다 | 정적 파일만 바뀌는 게 아니라 **nginx 컨테이너 자체가 교체**된다. 교체 순간 몇 초 동안 사이트 전체(화면과 `/api` 전부)가 끊기고, 진행 중인 요청·결제창 복귀가 끊길 수 있다. 백엔드들은 그대로 |
| `DEPLOY_BACKEND` | `backend` (행동 로그 수집기) | 기동 20~40초 동안 `POST /api/events` 가 502. 그 사이 행동 로그 일부가 빠질 수 있다. 쇼핑·로그인·대시보드는 영향 없음 |
| `DEPLOY_SHOP_BACKEND` | `shop-backend` | 먼저 마이그레이션(다). 그 뒤 기동 20~40초 동안 `/api/*`(상품·로그인·주문·결제·대시보드 데이터)가 502. 화면 파일은 뜬다 |
| `DEPLOY_RECOMMEND` | `recommend` | 모델·페르소나를 읽는 동안 추천·처방 문장·`/api/headline` 이 실패하거나 비어 보인다. 세션 상태는 `session_events.jsonl` 재생으로 돌아온다 |

nginx 설정만 바꾼 경우도 `DEPLOY_FRONTEND` 로 반영된다(이미지에 들어 있으므로). 발표용 요청 제한 완화
(로그인 60r/m·burst 150, `/api/events` 300r/s·burst 1500 — PA 러너 100명 동시 로그인과 헤드리스 브라우저
20~100개, 한 NAT 뒤 청중까지 제한 없던 때처럼 통과)도 `DEPLOY_FRONTEND` 를 한 번 돌려야 적용된다.

### 다. shop-backend 배포와 마이그레이션

shop-backend 는 `ddl-auto: validate` 라 엔티티에 있는 컬럼이 DB 에 없으면 **아예 뜨지 않는다.** 그래서 배포 대상에
shop-backend 가 있으면(`DEPLOY_SHOP_BACKEND` 또는 자동 판별) Jenkins 가 `compose up` 전에
`deploy/ec2-1/apply-shop-migrations.sh` 를 돌린다.

- 스크립트의 `MIGRATIONS` 목록만 순서대로: `20260929_add_member_signup_consent.sql`(가입 동의 5칸) →
  `20260929_add_member_withdrawal.sql`(`status` ENUM 에 `WITHDRAWN`, `withdrawn_at`). 둘 다 `information_schema` 로 본 뒤
  없을 때만 `ALTER` 하므로 **매 배포마다 다시 돌아도 아무 일 없다.** 모두 NULL 허용 컬럼 추가·ENUM 끝에 값 추가라
  옛 이미지와 지금 dev 코드 모두 validate 를 통과한다.
- 대상은 이 compose 의 `mysql` 서비스(shop-backend 가 `mysql:3306` 으로 붙는 DB). DB 이름·root 비밀번호는 컨테이너
  env(`MYSQL_DATABASE`, `MYSQL_ROOT_PASSWORD`)에서 읽고 출력하지 않는다.
- **실패하면 빌드가 빨갛게 멈추고 어떤 서비스도 다시 만들지 않는다** — 옛 shop-backend 가 계속 서비스한다.
  Jenkins 로그의 `[shop-migrate]` 줄을 본다.
- 새 마이그레이션을 추가할 때는 재실행해도 안전한지 먼저 확인하고 `MIGRATIONS` 목록 끝에 넣는다.

손으로 돌리기·확인 (EC2-1, Jenkins 작업공간에서):

```bash
cd /home/ubuntu/S15P21A306/deploy-workspace
export EC2_ENV_FILE=/home/ubuntu/S15P21A306/deploy/ec2-1/.env
bash deploy/ec2-1/apply-shop-migrations.sh        # 마지막 줄: ok: member has all 6 columns

DC="docker compose -p ec2-1 --env-file $EC2_ENV_FILE -f deploy/ec2-1/docker-compose.yml"
$DC exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' <<'SQL'
SHOW COLUMNS FROM member LIKE 'terms_agreed_at';
SHOW COLUMNS FROM member LIKE 'consent_version';
SHOW COLUMNS FROM member LIKE 'withdrawn_at';
SHOW COLUMNS FROM member LIKE 'status';
SQL
```

앞 세 줄이 한 줄씩 나오고 `status` 의 Type 에 `'WITHDRAWN'` 이 있으면 정상.

### 라. 배포 후 5분 점검

자격 증명 없이 어디서나(노트북에서):

```bash
S=https://j15a306.p.ssafy.io
curl -sS -o /dev/null -w '/               %{http_code}\n' $S/                        # 200
curl -sS -o /dev/null -w '/dashboard.html %{http_code}\n' $S/dashboard.html          # 200
curl -sS -o /dev/null -w '/platform.html  %{http_code}\n' $S/platform.html           # 200
curl -sS -o /dev/null -w 'products        %{http_code} %{size_download}B\n' $S/api/products    # 200, 수백 KB
curl -sS -o /dev/null -w 'product SB      %{http_code}\n' $S/api/products/SB000001   # 200
# 아래 둘은 일부러 빈 요청이다. 400/401 = 서버가 살아서 거절한 것.
# 502/504 = 컨테이너가 안 떠 있음, 429 = 요청 제한, events 가 503 = 수집기는 살았고 Kafka 가 문제
curl -sS -o /dev/null -w 'login(empty)    %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' $S/api/auth/login
curl -sS -o /dev/null -w 'events(empty)   %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' $S/api/events
curl -sSI $S/ | grep -i strict-transport-security                                    # 헤더 1줄
```

`https://…/actuator/health` 는 nginx 가 앱으로 넘기지 않아 **index.html 이 200 으로 온다 — 헬스로 쓰지 않는다.**
앱 헬스는 EC2-1 에서 `bash deploy/ec2-1/deploy-helpers.sh health shop-backend backend recommend nginx`
(`EC2_ENV_FILE` export 후).

**Jenkins 헬스는 초록인데 사이트의 `/api` 만 502 이면** nginx 가 옛 컨테이너 IP 를 들고 있는 것이다. nginx 는
`proxy_pass` 의 호스트 이름을 기동 때 한 번만 풀고, 헬스 체크는 nginx 안에서 `wget` 으로 새로 풀어서 이 경우를 못 잡는다.
`$DC exec -T nginx nginx -s reload` 한 줄이면 끊김 없이 풀린다.

브라우저로:
- 쇼핑몰 첫 화면·상품 상세가 뜨고, PA 계정 하나로 로그인된다
- 대시보드(`/dashboard.html`) 로그인 후 첫 화면 숫자·문장이 뜬다
- 테스트 결제 1건이 주문 완료까지 간다
- shop-backend 를 배포했으면 신규 가입 1건(동의 화면)까지

### 마. 되돌리기

위 "배포 확인과 되돌리기" 그대로다: `docker tag ec2-1-$SVC:previous ec2-1-$SVC:latest` →
`$DC up -d --no-deps --no-build --force-recreate $SVC` → `deploy-helpers.sh health $SVC`. `--no-build` 를 빼지 않는다.
shop-backend 를 되돌려도 **마이그레이션은 되돌리지 않는다** — 추가된 칸은 모두 NULL 허용이고 옛 코드는 그 칸을
모르므로 옛 이미지가 그대로 뜬다. 데이터 자체를 되돌려야 할 때만 5장 백업 복구.

### 바. EC2-2 (Kafka/Spark) — 발표 기간에는 건드리지 않는다

dev 에 들어온 EC2-2 변경(!506: `activity-events` 보존 24h→72h 재적용, raw sink 트리거 10s→60s,
`restart: unless-stopped`)은 EC2-2 에서 누군가 `docker compose up -d kafka-init spark-raw-sink` 를 돌려야만 적용된다.
Jenkins 는 EC2-2 를 배포하지 않는다. **사흘 동안은 돌리지 않는다.** 안 돌리면 지금처럼 24시간 보존·10초 트리거로
계속 돈다 = 발표 전과 똑같다. spark-raw-sink 를 다시 만들면 스트리밍 잡이 재시작돼 그동안 적재가 밀린다.
꼭 필요할 때(예: 72시간 보존이 당장 필요)만, 쉬는 시간에.

### 사. 호환성 확인 (09-28 → 09-30 dev 의 환경 변수)

`.env` 에 값이 없어도 뜨는지 확인했다. 없으면 compose 가 멈추는 `:?` 값은 예전과 같은 7개
(`KAFKA_BOOTSTRAP_SERVERS` · `ALLOWED_ORIGINS` · `SHOP_BACKEND_JWT_SECRET` · `MYSQL_PASSWORD` · `MYSQL_ROOT_PASSWORD` ·
`PORTONE_API_SECRET` · `GRAFANA_ADMIN_PASSWORD`)뿐이고, 새로 생긴 필수 값은 없다.

| 변수 | 어디 | 비어 있을 때 |
| --- | --- | --- |
| `LTR_MODEL_DIR` | compose recommend, `/data/ltr` 고정 | 폴더가 비어 있으면 이미지 안 모델을 쓴다(재학습 전과 같음) |
| `KAFKA_TOPIC_RETENTION_MS` | backend application.yml 기본값 24h→72h | compose 가 `CREATE_ACTIVITY_EVENTS_TOPIC=false` 라 수집기는 토픽을 만들지도 바꾸지도 않는다. 영향 없음 |
| `TEST_PAY_ALLOWED_MEMBER_PREFIX` | compose `:-PA` (yml 기본은 빈 값) | compose 기본값 `PA` — PA 러너만 테스트 결제 |
| `RECOMMEND_TIMEOUT_MS`, `RECOMMEND_FEEDBACK_TIMEOUT_MS` | shop-backend application.yml | 300ms, 30s. compose 에 없으므로 늘 이 기본값 |
| `SERVING_ADMIN_TOKEN` | recommend_server.py | compose 가 넘기지 않아 빈 값 → 관리자 `force` 요청만 무시된다(의도된 기본) |
| `SHOP_PAYMENT_RECONCILE_*` | **dev 에 아직 없음** (브랜치 `S15P21A306-be-payment-reconcile`) | 그 브랜치는 모두 기본값을 둔다(`enabled=true`, 5분 간격 등). 머지되면 결제 대조 작업이 **기본으로 켜진다** — 발표 기간 머지 여부는 따로 판단 |
