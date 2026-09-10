# shop_backend 요청 목록 (프론트 → 백엔드)

작성 2026-09-10 · 프론트 기준 커밋 `f9a75f9` (dev)

프론트에서 붙일 수 있는 건 전부 붙였습니다. 로그인 · 브랜드 · 상품 목록 · 등록 ·
장바구니 · 주문 · 결제 · 고객 피드백 · 판매자 피드백 · 대시보드 실측 · 리뷰 읽기까지
호출은 다 들어가 있고, 8090 에 실제로 대고 확인했습니다.

원칙은 **백엔드가 있으면 쓰고, 없거나 거절하면 기존 목(mock) 경로로 물러난다** 입니다
(`frontend/src/lib/shopApi.ts`). 그래서 아래가 안 고쳐져도 화면은 돌지만, **1·2 번이
없으면 상품 등록은 한 건도 성공하지 않습니다.**

아래 5건은 전부 저장소의 백엔드 코드에서 직접 확인한 것입니다.

---

## 1. `/error` 를 permitAll 에 추가 (한 줄)

`shop_backend/src/main/java/com/cosmetic/shopbackend/security/SecurityConfig.java:39-52`

permitAll 목록이 `/api/auth/**`, actuator, swagger, `GET /api/products*` 뿐이고
나머지는 `.anyRequest().authenticated()` 입니다. `/error` 가 빠져 있어서 **400 이 `/error`
로 포워드되는 순간 그 경로가 인증 필수라 401 로 바뀝니다.**

결과적으로 등록 400, 잘못된 메서드 405 가 전부 `401 {"error":"unauthorized"}` 로 보입니다.
프론트에서는 이것 때문에 등록 실패 한 번에 판매자가 로그아웃되고 있었습니다. 프론트는
인증 확인용 호출에서만 세션을 지우도록 우회해 뒀지만, 원인은 여기입니다.

```java
.requestMatchers("/error").permitAll()
```

## 2. category 시드

`POST /api/products` 가 활성 category 를 검사하는데 `mysql-erd.sql` 에 `INSERT INTO` 가
**한 건도 없습니다** (`CREATE TABLE category` 만 41 행에 있음). 그래서 항상 실패합니다.

`category_id` 를 secondary_category 코드(`Moisturizers`, `Cleansers` …)와 **같은 값**으로
넣어 주시면 프론트는 손댈 게 없습니다. 지금 그 값을 그대로 `categoryId` 로 보내고 있습니다.

## 3. 새 상품 기본 status

`catalog/Product.java:31` — `private Status status = Status.DRAFT;`

목록은 ACTIVE 만 주므로 등록한 상품이 안 보입니다. 기본값을 ACTIVE 로 바꾸시거나,
`PATCH /api/products/{id}/status?value=ACTIVE` (`CatalogController.java:163`) 가 판매자
권한으로 통과하는지 확인해 주세요. 프론트는 등록 직후 이 PATCH 를 한 번 보냅니다.

## 4. 목록 응답에 `salePriceKrw` 한 칸

`CatalogController.java` — `salePriceKrw` 는 `VariantView`(100행, 상세)에만 있고
목록이 쓰는 `ProductSummary`(78-92행)에는 없습니다. 그래서 카드에 할인가를 못 보입니다.

## 5. 시연 계정과 실행 문서

`mysql-erd.sql` 에 INSERT 가 0건이라 시드가 통째로 없습니다.

- `seller_account` · `member` 시드
  프론트가 만들어 쓰고 있는 `seller@hwabun.local` / `member@hwabun.local`,
  비밀번호 `hwabun1234` 를 그대로 넣어 주셔도 됩니다.
- `admin_account` 시드 1건 — 가입 API 가 없어서 **플랫폼 화면에 아무도 못 들어갑니다.**
- README: `SHOP_BACKEND_JWT_SECRET` 필수(32자 이상, 없으면 기동 실패), MySQL `13306`, 실행 순서
- `docker-compose.mysql.yml:17` 이 마운트하는 `contracts-data-dump.sql` 이 저장소에 없습니다.
  파일을 넣거나 그 줄을 지워 주세요.

---

## 참고 — 배포 전 필요

`src/main/java` 전체에 CORS 설정이 없습니다. 지금은 Vite 프록시로만 동작합니다.
프론트를 따로 서빙하는 순간 전부 막힙니다.

## 참고 — 프론트가 이미 우회해 둔 것

| 기능 | 호출 | 안 될 때 |
| --- | --- | --- |
| 상품 목록 · 상세 | `GET /api/products`, `/api/products/{id}` | 백엔드 상품이 목록 맨 앞, 없으면 기존 카탈로그 |
| 상품 등록 | `POST /api/products` → `PATCH status=ACTIVE` | 로컬 저장 + 실패 이유 표시 |
| 장바구니 · 주문 · 결제 | `POST /api/cart/items` → `/api/orders` → `/pay` | 테스트 주문, 완료 화면에 이유 |
| 고객 피드백 | `POST /api/feedback` | 구매 이력 없으면 안내 문구 |
| 판매자 피드백 | `GET /api/seller/feedback` | 로컬 저장본과 합침 |
| 개요 실측 4칸 | `GET /api/seller/dashboard` | 칸 자체가 안 뜸 |
| 상품 리뷰 | `GET /api/products/{id}/reviews` | 샘플 리뷰 |

Vite 프록시에 빠져 있던 `/api/cart` · `/api/settlements` 는 프론트에서 추가했습니다.
