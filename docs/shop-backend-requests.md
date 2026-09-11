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

## 6. `/api/events` 를 토큰 없이도 받아 주세요 (2026-09-10 추가)

JWT 식별 적용 회신 잘 받았습니다. 프론트는 붙였습니다 (dev `bc8b1b9`).
로그인(MEMBER)이면 `Authorization: Bearer <token>` 을 얹고, 봉투에 `account_id` 는
넣지 않습니다. `sendBeacon` 이 헤더를 못 실는 문제도 지적하신 대로
로그인 상태에서는 `fetch(..., { keepalive: true })` 로 바꿨습니다.

비로그인 수집 여부는 **계속 받는 것으로 정리됐습니다.** 그래서 두 가지 부탁드립니다.

- **토큰 없는 요청에 200** — 지금 명세대로 401 이면 시뮬레이터(PA 100명)가 통째로
  막힙니다. `simulator/agents/agent_runner.py:1875` 는 `X-Actor-Type`·
  `X-Simulation-Run-Id` 만 보내고 `Authorization` 이 없으며,
  `simulator/generator/gen_behavior_logs.py:787` 은 헤더가 아예 없습니다.
  PA 는 로그인 계정이 없어 붙일 토큰도 없습니다.
- **만료·손상 토큰도 401 대신 익명으로 강등** — JWT 가 15분이라 조금만 긴 세션이면
  반드시 만료됩니다. 프론트는 401 을 받으면 헤더 없이 한 번 더 보내도록 해
  뒀지만(dev `9b526af`), 서버가 익명으로 받아주면 이 왕복이 아예 없어집니다.

### 확인 부탁 — 요청 본문 상한

`fetch` 의 `keepalive` 는 브라우저가 본문을 64KB 로 제한합니다(모든 keepalive 요청
합산). 프론트는 한 요청에 최대 100건을 보내는데, 이벤트 하나가 평균 600바이트만
넘어도 걸립니다. 수집 서버의 본문 상한을 알려주시면 배치 건수를 맞추겠습니다.
지금은 413 을 받으면 배치를 반으로 줄이는 동작이 있어 당장 유실은 없습니다.

## 7. 브랜드 대시보드 마트 조회 API 6개 (2026-09-10 추가 · 계약 초안)

`contracts/dashboard-mart-api-spec.md` 초안 0.1 을 올렸습니다. 대시보드 행동 지표(개요 KPI·상세 콘텐츠·
고객군·성분 관심·상품 진단·막히는 곳)가 지금 전부 프론트 모의값인데, 데이터 파트의 Spark 마트를 MySQL `dw`
로 옮긴 뒤 shop_backend 가 읽어 주면 실측으로 바뀝니다.

- 경로 `GET /api/seller/dashboard/{overview|products|content|segments|ingredients|friction}?brandId=&from=&to=&actorType=`
- 인증·소유 확인은 기존 `GET /api/seller/dashboard` 와 같게. 응답 필드는 마트 컬럼 이름 그대로(snake_case).
- 마트 테이블이 없으면 503 `{"error":"mart_unavailable"}`, 브랜드 행이 0건이면 200 + `coverage: none`.
- 프론트는 붙여 뒀습니다 (`frontend/src/dashboard/lib/martApi.ts`). 응답이 없으면 지금처럼 모의로 돌고, 오는
  블록만 "실측" 배지로 바뀝니다. 그래서 여섯 개 중 `overview` 하나만 먼저 열어도 화면에 바로 보입니다.
- 데이터 파트에 걸린 것: MySQL projection (계약 §5) 과 신규 마트 5건 (계약 §6). 그중 §6-2 (콘텐츠별 담기율)가
  상세 콘텐츠 화면의 핵심 열이라 우선입니다.
- 세포라 카탈로그 브랜드(행동 로그가 있는 55개)는 `brand` 테이블에 행이 없어 시연 판매자 계정으로 조회할 수
  없습니다. 5번 시드에 `seed_catalog` 상품의 브랜드 행을 함께 넣어 주셔야 행동 화면이 실측으로 뜹니다.

## 8. 회원 피부 프로필 4개 · 프로필 조회/수정 · 주문 목록 (2026-09-11 추가)

AI 파트 요청(고객 가입에서 피부 속성 4개를 받아야 추천의 속성 친화도가 산다)에 따라 프론트 가입 폼과
마이페이지를 붙였습니다. `member` 테이블에 컬럼은 이미 있습니다 (`skin_type_code` · `skin_tone_code` ·
`hair_color_code` · `eye_color_code`, 전부 NULL 허용). 받는 쪽만 없습니다.

- **`POST /api/auth/members` 본문에 4개 추가** (전부 nullable): `skinTypeCode` · `skinToneCode` · `hairColorCode` · `eyeColorCode`.
  값은 `skin_type` 등 코드 테이블의 `code` 그대로 (`dry` · `fair` · `black` · `brown` …). 프론트는 지금부터 이 이름으로
  보내고 있습니다. `IdentityController.RegisterMember` 레코드에 필드 4개를 더하고 `Member` 세터로 넣어 주시면 됩니다.
  없는 코드가 오면 400 으로 거절해 주세요 (프론트는 어휘 밖 값을 보내지 않습니다).
- **`GET /api/members/me`** · **`PATCH /api/members/me`** (MEMBER 토큰): `{ memberId, email, nickname, skinTypeCode, skinToneCode,
  hairColorCode, eyeColorCode }`. PATCH 는 4개 코드만 바꿉니다(null 로 지우기 허용). 프론트 마이페이지가 지금은 이
  브라우저에만 저장하는데, 이 둘이 생기면 서버 값을 우선으로 바꿉니다.
- **`GET /api/orders`** (MEMBER 토큰, 내 주문 목록): `[{ orderId, status, totalAmount, paidAmount, createdAt,
  items: [{ productId, productNameSnapshot, quantity, unitPrice }] }]`, 최신순. 마이페이지 주문 내역이 지금은 이 브라우저에서
  한 주문만 보입니다.
- `hair_color` 코드 테이블에 `gray` 가 있는지 확인 부탁드립니다 (`persona-schema.md` §3.1 은 6종, `product-form-labels-ko.json` 에는 5종).
- 페르소나 100명을 회원으로 일괄 가입시키는 스크립트를 두었습니다 (`frontend/scripts/register-personas.ts`).
  이메일은 `{persona_id 소문자}@persona.hwabun.local`, 비밀번호 `hwabun1234`. 위 4개 필드를 함께 보냅니다.

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
