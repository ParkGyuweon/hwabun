# Local monitoring

Prometheus와 Grafana는 호스트에서 실행 중인 서비스에 Docker Desktop의
`host.docker.internal`로 접근한다. Shop Backend의 기본 포트는 **8090**이다.

## Shop Backend 성능 측정

1. Shop Backend를 8090 포트에서 실행한다.
2. 모니터링 설정을 반영한다.

```bash
cd monitoring
docker compose up -d --force-recreate prometheus
docker compose up -d grafana
```

3. Prometheus Targets에서 `shop-backend`가 `UP`인지 확인한다.
   `http://localhost:9090/targets`
4. Grafana의 **Shop Backend Performance** 대시보드에서 최근 15분을 선택한 뒤,
   브라우저 캐시를 비우고 상품 상세 페이지를 한 번 연다.

`Detail / list ratio (5m)`는 `/api/products/{id}` 요청 수를 `/api/products` 목록 요청 수로
나눈 값이다. 단일 테스트를 실행한 깨끗한 시간 창에서 이 값이 카탈로그 상품 수에 가깝게
커지면, 상세 페이지 진입 중 클라이언트 N+1 요청이 발생했다는 뜻이다.

HTTP 요청 수·p50/p95/p99·JVM·Hikari 지표는 Actuator Prometheus endpoint에서 나온다.
DB 쿼리 통계도 함께 볼 때만 Shop Backend 실행 환경에 아래 값을 주고 재시작한다.

```dotenv
SHOP_BACKEND_HIBERNATE_STATISTICS=true
```

이 통계 수집은 측정 기간에만 켜고, 종료 후에는 제거하거나 `false`로 되돌린다.
