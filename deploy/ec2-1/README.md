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

## 추천 추론 서버 (AI, Jira 219)

`recommend` 서비스는 파이썬 FastAPI 추천 서버다 (`deploy/recommend.Dockerfile`, 계약
`contracts/recommendation-io-spec.md` §5). 모델·페르소나·산출물이 이미지 안에 들어가고,
판매자가 등록한 상품은 `/data` 볼륨(`recommend-data`)에 남는다.

```bash
# 빌드는 BuildKit 이어야 한다 — Dockerfile 옆의 recommend.Dockerfile.dockerignore 를 쓴다
DOCKER_BUILDKIT=1 docker compose build recommend
docker compose up -d recommend
docker compose exec recommend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8300/health').read()[:200])"
```

| 항목 | 값 |
| --- | --- |
| 포트 | 8300, 컨테이너 네트워크 안에서만 (`expose`). 인증이 없어 외부에 열지 않는다 |
| 백엔드 → 추천 | `RECOMMEND_URL=http://recommend:8300` (백엔드 프록시 컨트롤러가 읽는다, 요청서 §5) |
| 기동 시간 | 첫 요청 전 모델·페르소나 로드 약 4~10초. `start_period` 40초 뒤 헬스체크 |
| 워커 | **1**. 사용자 상태·등록 상품이 프로세스 메모리라 늘리면 답이 갈린다. 확장은 Redis 도입 뒤 |
| 등록 상품 | `POST /api/products` 가 `/data/registered_products.jsonl` 에 append. 첫 기동에 이미지 시드(SSAFY Beauty 8개) 복사. 볼륨을 지우면 시드로 돌아간다 |
| 모델 교체 | `batch/ingest/data/serving/ltr_model.pkl` 을 바꾸고 이미지를 다시 빌드. `requirements.txt` 의 scikit-learn 버전이 학습 버전과 같아야 한다 |

nginx 는 `/api/` 를 백엔드 8080 으로만 보낸다. 추천 경로는 백엔드가 프록시하는 형태로 확정되기 전까지
nginx 에 따로 열지 않는다. 임시로 직접 열어야 하면 `location /api/recommend { proxy_pass http://recommend:8300; }`
를 `/api/` 앞에 두면 된다.
