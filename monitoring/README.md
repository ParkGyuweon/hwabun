# Backend monitoring

Spring Boot Actuator의 Prometheus endpoint를 수집하고 Grafana 대시보드로 시각화하는 로컬 개발 구성입니다.

## 실행

1. Kafka와 Spring Boot 백엔드를 먼저 실행합니다.
2. `http://localhost:8080/actuator/prometheus`가 열리는지 확인합니다.
3. 이 디렉터리에서 모니터링 스택을 실행합니다.

```powershell
docker compose up -d
```

접속 주소:

- Prometheus targets: http://localhost:9090/targets
- Prometheus query: http://localhost:9090
- Grafana: http://localhost:3000

Grafana의 로컬 기본 계정은 `admin` / `admin`입니다. 데이터소스와 `Cosmetic / Backend Overview` 대시보드는 자동 등록됩니다.

기본 비밀번호를 바꾸려면 실행 전에 환경변수를 설정합니다.

```powershell
$env:GRAFANA_ADMIN_PASSWORD='원하는-비밀번호'
docker compose up -d
```

## 종료

```powershell
docker compose down
```

데이터 볼륨까지 삭제하려면 명시적으로 `docker compose down -v`를 실행해야 합니다.

## 연결 문제

Prometheus 컨테이너는 Windows 호스트에서 실행 중인 백엔드에 `host.docker.internal:8080`으로 접근합니다. `/targets`에서 `log-connector`가 `DOWN`이면 백엔드와 `/actuator/prometheus` endpoint를 먼저 확인합니다.

이 구성은 로컬 개발용입니다. 운영 환경에서는 Actuator endpoint 접근 제어와 Grafana 관리자 비밀번호를 별도로 구성해야 합니다.
