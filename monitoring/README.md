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

## 서버 측 N+1 수치화

Shop Backend를 재시작한 뒤, Grafana에서 시간 범위를 짧게 설정하고 `GET /api/products`를
한 번만 호출한다. 다음 두 패널을 함께 확인한다.

- `Products returned per list request`: 목록 한 번이 돌려준 상품 수 `N`
- `DB reads per product-list request`: 목록 처리 중의 Repository/JDBC 조회 수

개선 전 구현은 목록 조회 1회에 `2 + (3 × N)`번의 DB 조회가 발생했다.
처음의 상품 목록 조회와 하이라이트 일괄 조회가 각각 1번이고, 상품마다 브랜드 확인,
브랜드 표시, 옵션 조회가 각각 1번씩 발생하기 때문이다. 예를 들어 상품 120개를 반환하면
`2 + (3 × 120) = 362`번이었다. 개선 후에는 `list · catalog_projection`과
`list · highlights`가 각각 1회씩 증가해야 한다.

이 메트릭은 Hibernate 통계에만 의존하지 않는다. Hibernate Repository와 JdbcTemplate 조인을
모두 포함한 카탈로그 읽기 경로의 DB 조회 호출을 계수한다.
