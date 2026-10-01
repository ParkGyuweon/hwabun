# 서비스 API 명세서 (현재 코드 기준)

작성 기준: `frontend/src`, `backend/src`, `shop_backend/src` 전체 대조

## 서비스 구분

| 서비스 | 역할 | 주요 API |
|---|---|---|
| `backend` | 사용자 행동 이벤트 수집 | `POST /api/events` |
| `shop_backend` | 인증·상품·주문·리뷰·판매자·관리자 | 대부분의 `/api/*` |
| `batch/serving` | 추천·대시보드 처방 | `GET /api/recommend`, `POST /api/prescription` |

Shop backend 인증 요청은 `Authorization: Bearer <JWT>`를 사용합니다. 회원·판매자·관리자 역할은 JWT 및 서버 계정 상태로 검증됩니다.

## 1. Collector backend — 행동 이벤트

### `POST /api/events`

페이지뷰, 상품조회, 장바구니, 구매, 추천 노출·클릭, 대시보드 행동 등을 최대 100건까지 배치 수집합니다. 요청 DTO는 `EventBatchRequest`이며 `schema_version`은 `0.2.0-draft`입니다.

```json
{
  "schema_version": "0.2.0-draft",
  "events": [{
    "event_name": "product_view",
    "event_time": "2026-09-18T10:00:00Z",
    "session_id": "session-id",
    "user_id": "member-id",
    "properties": { "product_id": "P001" }
  }]
}
```

`events`는 비어 있을 수 없고 최대 100건입니다. 각 이벤트명과 properties 계약은 `backend/.../event/api/validation` 및 `contracts`를 따릅니다.

## 2. 인증 — Shop backend

| Method | Path | 권한 | 요청 |
|---|---|---|---|
| POST | `/api/auth/members` | 공개 | `email`, `password(8자 이상)`, `nickname`, `agreeTerms`·`agreePrivacy`(필수, true 아니면 400 `consent_required`), 선택 `agreeSkinInfo`(false면 프로필 코드 4개 저장 안 함)·`agreeBehaviorLink`, 선택 프로필 코드 |
| POST | `/api/auth/sellers` | 공개 | `email`, `password(8자 이상)`, `name` |
| POST | `/api/auth/login` | 공개 | `email`, `password`, `role: MEMBER\|SELLER\|ADMIN` |

성공 응답:

```json
{ "id": "...", "email": "...", "name": "...", "role": "MEMBER", "status": "ACTIVE", "token": "<JWT>" }
```

중복 가입은 `409`, 로그인 실패·비활성 계정은 `401`입니다.

## 3. 상품·브랜드

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/api/products` | 공개 | 활성 상품 목록 (`Accept-Language: ko` 지원) |
| GET | `/api/products/{productId}` | 공개 | 상품 상세·옵션·이미지·성분 |
| POST | `/api/products` | SELLER | 본인 브랜드 상품 생성 |
| PUT | `/api/products/{productId}` | SELLER | 본인 브랜드 상품 수정 |
| DELETE | `/api/products/{productId}` | SELLER | INACTIVE 처리 |
| PATCH | `/api/products/{productId}/status?value=ACTIVE` | SELLER | 상품 상태 변경 |
| GET | `/api/brands` | SELLER/ADMIN | 본인 브랜드 또는 전체 브랜드 |
| GET | `/api/brands/{brandId}` | SELLER/ADMIN | 브랜드 상세 |
| POST | `/api/brands` | SELLER | 브랜드 생성 |
| PUT | `/api/brands/{brandId}` | SELLER/ADMIN | 브랜드 수정 |
| PATCH | `/api/brands/{brandId}/status?status=ACTIVE` | SELLER/ADMIN | 브랜드 상태 변경 |

상품 생성·수정 요청:

```json
{
  "brandId": "brand-id", "categoryId": "category-id",
  "productName": "수분 크림", "secondaryCategory": "SKINCARE",
  "tertiaryCategory": "CREAM", "highlights": ["hydration"],
  "ingredients": "water,...", "priceKrw": 25000,
  "size": "50ml", "primaryImageUrl": "https://...",
  "description": { "what_it_is": "...", "suggested_usage": "..." }
}
```

브랜드 요청은 `{ name, description?, logoUrl? }`입니다. 상품 목록은 `ProductSummary[]`, 상세는 `product`, `variants`, `images`, 성분·다국어 설명을 포함합니다. 프론트는 `variants[].variantId`를 장바구니 식별자로 사용합니다.

## 4. 추천

### `GET /api/recommend`

로그인한 MEMBER의 프로필을 Shop backend가 서버에서 읽어 추천 서버로 전달합니다. 프론트에서 보내는 회원 식별·프로필 query는 현재 Shop backend에서 정본으로 사용하지 않습니다.

| Query | 기본값 | 설명 |
|---|---:|---|
| `size` | `10` | 추천 상품 수 |
| `reserved` | `2` | 예약 슬롯 수 |
| `banner_slots` | `0` | 배너 슬롯 수 |
| `axes` | `concern,segment` | `concern,ingredient,clean,price_bin,category,segment` |
| `hero` | `top` | `top` 또는 `new_brand` |

응답 필드: `persona_id`, `recommendation_id`, `list_id`, `algorithm`, `items`, 선택적 `hero`, `banners`, `long_term_trait`. 비로그인 `401`, MEMBER 외 역할 `403`입니다.

## 5. 장바구니·주문·결제

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/api/cart` | MEMBER | 장바구니 조회 |
| POST | `/api/cart/items` | MEMBER | 옵션 추가·수량 누적 |
| PATCH | `/api/cart/items/{itemId}` | MEMBER | 항목 수량 변경 (1~99) |
| DELETE | `/api/cart/items/{itemId}` | MEMBER | 항목 삭제 |
| POST | `/api/orders` | MEMBER | `items`가 있으면 지정 품목, 없으면 서버 장바구니 전체로 주문 생성. `clearCart`는 PAID 전환 때 주문에 포함된 수량을 장바구니에서 제거할지 지정 |
| GET | `/api/orders` | MEMBER | 결제 완료 주문 목록 |
| POST | `/api/orders/{orderId}/pay` | MEMBER* | 테스트 결제 완료 |
| POST | `/api/orders/{orderId}/confirm` | MEMBER | PortOne 결제 확인 |

```json
// POST /api/cart/items
{ "variantId": "variant-id", "quantity": 2 }

// POST /api/orders — legacy cart checkout
{ "idempotencyKey": "client-generated-unique-key" }

// POST /api/orders — selected items / buy now
{ "idempotencyKey": "client-generated-unique-key", "items": [{ "variantId": "variant-id", "quantity": 1 }], "clearCart": false }

// POST /api/orders/{orderId}/confirm
{ "paymentId": "portone-payment-id" }
```

주문 응답은 `orderId`, `status`, `totalAmount`, `paidAmount`, `currency`, `paymentId`, `paymentProvider`, `paidAt`, `createdAt`, `itemCount`를 포함합니다. 같은 idempotency key를 다른 품목이나 `clearCart` 값으로 재사용하면 `409`입니다. `clearCart`가 적용된 주문은 결제 확정(`/confirm`, 웹훅·대조 포함) 또는 테스트 결제(`/pay`)로 CREATED→PAID 전환에 성공하면 주문 품목 수량만 장바구니에서 차감합니다. 주문 수량보다 장바구니 수량이 많으면 차감 후 초과 수량이 남습니다. 미지정 시 장바구니 전체 주문은 `true`, 지정 품목 주문은 `false`입니다. `/pay`는 테스트 계정 prefix 설정에 따라 제한됩니다.

### 5.1 결제 대조(confirm 누락 복구)와 웹훅

결제창에서 돈은 빠졌는데 브라우저가 `/confirm`을 못 부르고 끊긴 경우를 서버가 스스로 맞춥니다. 결제 id는 주문마다 `hwabun-{orderId}`로 고정이라 주문번호만으로 PortOne을 다시 조회할 수 있습니다.

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/api/payments/portone/webhook` | 없음 | PortOne 웹훅. 본문의 paymentId만 꺼내 해당 주문을 즉시 대조 |

- **스케줄 대조**: `shop.payment.reconcile.interval-ms`(기본 5분)마다 생성 2분~24시간 사이 `CREATED` 주문을 최근 것부터 최대 `batch-size`(기본 50)건 PortOne에 조회합니다. `PAID`이고 `/confirm`과 같은 검증(결제 id·상태·통화·금액·`customData.orderId`)을 통과하면 조건부 update(`status='CREATED'`일 때만)로 `PAID` 처리합니다. `/confirm`과 동시에 돌아도 한 번만 반영됩니다.
- **끄기**: `SHOP_PAYMENT_RECONCILE_ENABLED=false`. `PORTONE_API_SECRET`이 비어 있으면 켜져 있어도 돌지 않습니다.
- **웹훅**: V2 `{"type":"Transaction.Paid","data":{"paymentId":"hwabun-..."}}`와 구버전 `{"payment_id":"hwabun-..."}`를 받습니다. 본문의 상태·금액은 믿지 않고 PortOne을 다시 조회해 위와 같은 검증을 거칩니다. 응답 `{"result":"RECOVERED|ALREADY_PAID|NO_PAYMENT|NOT_PAID|MISMATCH|NOT_PAYABLE|ORDER_NOT_FOUND|IGNORED"}`. PortOne 조회 실패 시 5xx로 답해 PortOne이 재전송합니다.
- **MISMATCH**(PortOne은 PAID인데 금액·주문번호가 다름)는 자동 처리하지 않고 `WARN` 로그만 남깁니다.

**다음 단계(미구현) — 환불·취소**: 지금은 PortOne 결제 취소 API(`POST /payments/{paymentId}/cancel`)를 부르지 않습니다. 필요한 작업은 ① `MISMATCH`나 24시간 넘게 `CREATED`로 남은 결제 완료 건의 자동/수동 취소, ② 판매자·운영자용 주문 취소·환불 엔드포인트와 `CANCELLED`/`REFUNDED` 상태 전이, `payment.status` 갱신, ③ 웹훅 `Transaction.Cancelled` 반영, ④ 웹훅 서명(Standard Webhooks, 웹훅 시크릿) 검증입니다. 그전까지 불일치·미확인 결제는 로그를 보고 PortOne 콘솔에서 수동으로 취소합니다.

## 6. 리뷰·피드백

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/api/reviews` | MEMBER | 결제 완료 주문 품목 리뷰 |
| GET | `/api/products/{productId}/reviews` | 공개 | 상품 리뷰 목록 |
| GET | `/api/seller/reviews?brandId={id}` | SELLER/ADMIN | 판매자 리뷰 목록 |
| POST | `/api/feedback` | MEMBER | 제품 축별 피드백 |
| GET | `/api/feedback/mine?productId=` | MEMBER | 내가 보낸 피드백 + 판매자 응답 이력 `responses[]` (2026-10-01 요청 — 없으면 화면은 빈 목록) |
| GET | `/api/seller/feedback?brandId={id}` | SELLER | 판매자 피드백 |
| POST | `/api/seller/feedback/{feedbackId}/responses` | SELLER | 피드백 확인·답변·반영 처리 |
| POST | `/api/seller/feedback/classify` | 내부/SELLER | 피드백 분류 |
| GET | `/api/notifications?limit={1..50}` | MEMBER/SELLER | 내 인앱 알림 목록 |
| GET | `/api/notifications/unread-count` | MEMBER/SELLER | 읽지 않은 알림 수 |
| PATCH | `/api/notifications/{notificationId}/read` | MEMBER/SELLER | 알림 하나 읽음 처리 |
| PATCH | `/api/notifications/read-all` | MEMBER/SELLER | 내 알림 전체 읽음 처리 |

```json
// POST /api/reviews
{ "orderItemId": "order-item-id", "rating": 5, "isRecommended": true, "title": "좋아요", "body": "사용 후기" }

// POST /api/feedback
{ "productId": "product-id", "axisId": "efficacy", "body": "효과가 좋았습니다" }

// POST /api/seller/feedback/{feedbackId}/responses
{ "action": "REPLIED", "body": "소중한 의견 감사합니다. 개선하겠습니다." }
```

피드백 축은 `efficacy`, `texture`, `scent`, `packaging`, `value`입니다. 비구매자도 피드백을 남길 수 있으며, 회원·상품·축 조합이 중복되면 `409`입니다.
판매자 응답의 `action`은 `ACKNOWLEDGED`, `REPLIED`, `IMPLEMENTED` 중 하나입니다. `REPLIED`일 때만 `body`가 필수이고, 판매자가 소유한 브랜드의 공개 피드백에만 응답할 수 있습니다.

알림 목록은 `{ "items": [...] }`, 읽지 않은 수는 `{ "count": 0 }` 형식입니다. 알림은 JWT의 회원 또는 판매자 계정에 귀속되며 다른 수신자의 알림을 읽음 처리할 수 없습니다.

## 7. 판매자·대시보드

| Method | Path | 권한 | Query |
|---|---|---|---|
| GET | `/api/seller/orders` | SELLER | `brandId`, `status` 선택 |
| GET | `/api/seller/dashboard` | SELLER | `brandId` 필수 |
| GET | `/api/seller/dashboard/overview` | SELLER | `brandId`, `from`, `to`, `actorType`, `generatorType` |
| GET | `/api/seller/dashboard/products` | SELLER | 동일 |
| GET | `/api/seller/dashboard/content` | SELLER | 동일 |
| GET | `/api/seller/dashboard/segments` | SELLER | 동일 |
| GET | `/api/seller/dashboard/ingredients` | SELLER | 동일 |
| GET | `/api/seller/dashboard/friction` | SELLER | 동일 |
| GET | `/api/seller/dashboard/purchase` | SELLER | 동일 |
| GET | `/api/seller/dashboard/cross-brand` | SELLER | `brandId`, `from`, `to`, `actorType`, `generatorType` |
| GET | `/api/seller/dashboard/price-position` | SELLER | 로그인한 판매자의 브랜드 |
| GET | `/api/seller/dashboard/cohort-position` | SELLER | `from`, `to`, `actorType` (프론트 미사용) |

마트 API 는 10개입니다(`DashboardController`). 프론트 `martApi.ts`는 그중 7개를 병렬 호출하고, `cross-brand`·`price-position` 은 해당 화면에서 따로 부릅니다. 날짜는 KST `YYYY-MM-DD`, `actorType`·`generatorType` 기본값은 `all`입니다. 응답은 마트별 동적 JSON이며 `source`, `coverage`를 포함합니다.

## 8. 관리자·정산

| Method | Path | 권한 | 상태/설명 |
|---|---|---|---|
| PATCH | `/api/admin/products/{id}/approval?status=ACTIVE` | ADMIN | `DRAFT`, `PENDING_APPROVAL`, `ACTIVE`, `INACTIVE`, `REJECTED` |
| PATCH | `/api/admin/brands/{id}/status?status=ACTIVE` | ADMIN | `ACTIVE`, `INACTIVE` |
| PATCH | `/api/admin/feedback/{id}/status?status=VISIBLE` | ADMIN | `VISIBLE`, `HIDDEN`, `DELETED` |
| POST | `/api/admin/settlements/{id}/complete` | ADMIN | 정산 완료 |
| GET | `/api/settlements` | SELLER/ADMIN | 정산 목록 |
| POST | `/api/settlements/generate` | ADMIN | 정산 생성 |

## 9. 대시보드 처방

### `POST /api/prescription`

`batch/serving` 처방 서버로 전달하는 별도 API입니다. 프론트는 신호가 2개 이상일 때만 호출합니다.

요청 최상위 필드: `brand`, `target`, `page_context`, `cross_screen_signals`. 응답은 `rejected_by`, `needs_evidence`, `model` 및 처방 내용을 포함하는 `PrescriptionEnvelope`입니다. 서버 오류·거부 시 프론트는 규칙 기반 처방으로 fallback합니다.

## 구현 대조 시 확인된 주의사항

1. 이벤트 수집(`/api/events`)과 쇼핑 API(`/api/products`, `/api/orders`)는 서로 다른 Spring 애플리케이션입니다.
2. 프론트 추천 클라이언트는 `persona_id`·profile을 구성하지만 현재 `shop_backend/RecommendationController`는 토큰의 회원 ID와 DB 프로필을 정본으로 씁니다.
3. 프론트 상품 타입은 `createdAt`, 상세 `images`를 선택 필드로 지원하며, 현재 응답 버전에 따라 없을 수 있습니다.
4. `/api/seller/reviews`와 `/api/seller/feedback/classify`는 기존 문서에 누락되어 있던 현재 Controller 엔드포인트입니다.

## 정본 소스

- Collector: `backend/src/main/java/com/cosmetic/collector/event/api/EventController.java`
- Shop API: `shop_backend/src/main/java/com/cosmetic/shopbackend/**/**Controller.java`
- Frontend 호출 계약: `frontend/src/lib/shopApi.ts`, `frontend/src/lib/recommendApi.ts`, `frontend/src/dashboard/lib/martApi.ts`
- 이벤트·대시보드 계약: `contracts/`
