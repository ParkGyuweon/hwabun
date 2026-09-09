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
