# 판매자 Dashboard API 설계

> 상태: 구현 전 설계 · 2026-09-14
>
> 범위: 주문 → 결제 → 리뷰·피드백 → 정산 흐름을 `shop_backend`의 판매자 권한으로 조회한다.
> 행동 로그/DW 마트 기반 KPI는 이미 작성된 `contracts/dashboard-mart-api-spec.md`의 별도 범위다.

## 1. 결정 사항

- 새 읽기 API는 `/api/seller/dashboard` 아래로 모은다. 기존 `GET /api/seller/dashboard`, `GET /api/seller/feedback`, `GET /api/settlements`는 이미 쓰는 프론트를 깨지 않도록 유지한다.
- 모든 API는 `SELLER` 토큰과 `brand.seller_account_id = actor.accountId()`를 검증한다. 다른 브랜드는 존재 여부를 노출하지 않고 `403`으로 처리한다.
- 금액·판매량·전환의 정본은 이벤트 로그가 아니라 `shop_order.status = PAID`인 `order_item`이다. 취소·환불은 현재 정책상 제외되어 있으며 후속 범위에서 차감 규칙을 추가한다.
- 기간은 KST 날짜의 포함 범위다. 기본값은 최근 30일, 최대 366일이며 `from > to` 또는 범위 초과는 `400`이다.
- 목록은 cursor가 아닌 `page`(0부터)·`size`(기본 20, 최대 100)를 사용한다. 화면 요구와 현재 MySQL 데이터 크기에 충분하고, 정렬 키가 필요한 무한 스크롤이 생기면 cursor로 승격한다.

## 2. 현재 구현과의 경계

| 현재 API | 유지 이유 | 새 설계에서의 위치 |
| --- | --- | --- |
| `GET /api/seller/dashboard?brandId=` | Overview 화면이 이미 `orders`, `revenue`, `reviews`, `feedbacks`를 사용 | 호환용 요약. 새 `summary` 구현 후 내부 쿼리를 공용화 |
| `GET /api/seller/feedback?brandId=` | Feedback 화면이 원문 목록을 읽음 | 호환용. 새 피드백 API는 페이지·집계·기간 필터 제공 |
| `GET /api/settlements?brandId=` | 정산 목록을 제공 | 호환용. 새 API는 판매 성과와 같은 봉투/페이지 규칙 제공 |
| `POST /api/settlements/generate` | 월 정산 생성이라는 상태 변경 | 조회 API와 분리해 유지. 자동 생성 정책은 이번 범위에서 바꾸지 않음 |

## 3. 공통 규칙

### 요청

공통 query는 `brandId`, 선택 `from`, `to`다. `from`/`to`는 `YYYY-MM-DD`이며 `created_at` 또는 `paid_at`을 KST로 변환하여 비교한다.

목록 API는 `page`, `size`와 해당 정렬/필터를 추가로 받는다. 허용하지 않는 enum, 날짜 형식, 음수 page, size 초과는 `400`이다.

### 응답과 오류

새 API의 목록 응답은 다음처럼 일관되게 한다.

```json
{
  "brandId": "brand-1",
  "range": { "from": "2026-08-15", "to": "2026-09-14" },
  "page": { "number": 0, "size": 20, "totalElements": 35, "totalPages": 2 },
  "items": []
}
```

단일 요약 API는 `page` 대신 `range`와 데이터 본문만 둔다. 오류는 기존 `ApiExceptionHandler` 형식인 `{"error":"..."}`를 따른다.

| 상황 | 상태 | error |
| --- | ---: | --- |
| 로그인 안 됨 | 401 | `authentication_required` |
| MEMBER/ADMIN 권한 또는 타 브랜드 | 403 | `brand_access_denied` |
| 날짜·필터·페이지 검증 실패 | 400 | 구체적 안정 코드 (`invalid_date_range` 등) |
| 없는 settlement id | 404 | `settlement_not_found` |

## 4. API 명세

### 4-1. 브랜드 성과 요약

`GET /api/seller/dashboard/summary?brandId={id}&from=&to=`

```json
{
  "brandId": "brand-1",
  "range": { "from": "2026-08-15", "to": "2026-09-14" },
  "sales": { "paidOrderCount": 18, "paidItemCount": 26, "grossSalesAmount": 431000, "currency": "KRW" },
  "reviews": { "count": 11, "averageRating": 4.27, "recommendedCount": 8, "recommendationRate": 0.8 },
  "feedback": { "count": 9, "classifiedCount": 6, "hiddenCount": 1 },
  "settlement": { "pendingAmount": 431000, "completedAmount": 120000 }
}
```

- 매출은 `order_item`을 `shop_order`에 조인해 `PAID`와 `paid_at` 범위를 적용한다.
- 리뷰는 브랜드 상품에 연결된 `review` 중 `PUBLISHED`만 센다. 평점/추천 비율의 분모는 각각 평점 행/`is_recommended IS NOT NULL` 행이다.
- 피드백은 브랜드 `order_item`에 연결된 전체 상태를 수치로 보되, 목록 원문에서는 `VISIBLE`만 기본 노출한다.
- 정산 금액은 기간 내 결제액을 다시 합산하지 않고 `settlement`의 상태별 금액을 표시한다. 기간은 `settlement_month` 기준이다.

### 4-2. 상품별 성과

`GET /api/seller/dashboard/products?brandId={id}&from=&to=&sort=revenue|quantity|reviewCount&page=&size=`

`product`를 기준으로 `order_item`과 PAID 주문을 left join한다. 상품이 기간 동안 팔리지 않아도 브랜드 상품 목록에는 포함한다.

```json
{
  "productId": "product-1",
  "productName": "수분 크림",
  "status": "ACTIVE",
  "paidOrderCount": 12,
  "paidQuantity": 17,
  "grossSalesAmount": 255000,
  "reviewCount": 7,
  "averageRating": 4.43,
  "feedbackCount": 5
}
```

동일 주문에서 같은 상품 SKU가 한 번만 등장한다는 DB 제약을 이용해 `paidOrderCount`는 `COUNT(DISTINCT oi.order_id)`로 계산한다. 수량은 `SUM(oi.quantity)`다. 정렬은 null 평점과 0 판매를 마지막에 두며, 동률은 `product_id ASC`로 안정화한다.

> 조회수·장바구니·구매 전환율은 주문 DB만으로 만들 수 없다. 이 값은 `contracts/dashboard-mart-api-spec.md` E1/E2의 마트 API가 준비된 뒤 합친다. 이번 API에 추정값을 넣지 않는다.

### 4-3. 리뷰 조회·집계

`GET /api/seller/dashboard/reviews?brandId={id}&from=&to=&productId=&rating=&page=&size=`

응답은 `summary`와 `items`를 함께 준다. `summary`는 `count`, `averageRating`, `recommendationRate`, `ratingDistribution(1~5)`이며, `items`에는 review id, product id/name, rating, recommendation, title/body, createdAt, 구매자 속성 snapshot을 담는다. 목록은 `PUBLISHED`만, 최신순(`created_at DESC, review_id DESC`)이다.

리뷰의 브랜드 귀속은 현재 쿼리처럼 `review.order_item_id → order_item.brand_id`만으로 판단하지 않는다. 시드 카탈로그 리뷰에는 `order_item_id`가 없으므로 `review.product_id → product.brand_id`로 귀속한다. 따라서 두 종류를 모두 보여 주되 `source`를 응답에 명시한다.

### 4-4. 피드백 조회·분석

`GET /api/seller/dashboard/feedback?brandId={id}&from=&to=&productId=&axisId=&categoryId=&classificationStatus=&includeHidden=false&page=&size=`

`summary`는 축별 건수와 다중 라벨 기준 카테고리 언급 수를 준다. 한 피드백에 라벨이 여러 개면 각 카테고리에 1건씩 센다. 목록은 `feedback`, `feedback_classification`, `feedback_classification_label`, `order_item`, `product`를 조인한다.

- `includeHidden`은 기본 `false`이고 관리자가 아닌 판매자는 `HIDDEN`/`DELETED` 원문을 조회할 수 없다.
- `classificationStatus=PENDING|COMPLETED|FAILED`와 `axisId`는 정확 일치 필터다.
- 분류가 안 된 행은 labels가 빈 배열이며 `PENDING`을 명시한다. 요약의 라벨 언급 수와 피드백 건수는 서로 다를 수 있다.

기존 `/api/seller/feedback`의 원문 반환과 동일한 필드/분류 결과를 재사용해 프론트 전환 위험을 낮춘다.

### 4-5. 매출 추이

`GET /api/seller/dashboard/sales?brandId={id}&from=&to=&granularity=day|month`

```json
{
  "brandId": "brand-1",
  "range": { "from": "2026-08-15", "to": "2026-09-14" },
  "granularity": "day",
  "totals": { "paidOrderCount": 18, "paidQuantity": 26, "grossSalesAmount": 431000, "currency": "KRW" },
  "series": [{ "period": "2026-09-01", "paidOrderCount": 2, "paidQuantity": 3, "grossSalesAmount": 48000 }]
}
```

일 단위는 KST `paid_at` 날짜, 월 단위는 KST 월을 쓴다. 시계열에 데이터가 없는 날/월도 프론트가 연속 축을 만들 수 있도록 서버가 0행을 채운다. 최대 기간은 day 366일, month 36개월로 제한한다.

### 4-6. 정산 조회·상세

- `GET /api/seller/dashboard/settlements?brandId={id}&status=PENDING|COMPLETED&page=&size=`
- `GET /api/seller/dashboard/settlements/{settlementId}?brandId={id}`

목록은 settlement month, status, gross/fee/net amount, currency, completedAt을 반환한다. 상세는 이를 포함하고 `settlement_item`을 페이지로 제공한다. 상세의 브랜드 조건은 URL id만으로 찾지 않고 반드시 `settlement_id AND brand_id`로 조회한다.

`generate`는 멱등적으로 같은 월의 PENDING 정산을 갱신하지만, 완료된 정산은 변경하지 않는 기존 규칙을 유지한다. 생성은 데이터가 바뀌는 별도 작업이므로 대시보드 화면의 단순 조회에서 자동 호출하지 않는다.

## 5. 구현 구조

`dashboard` 패키지에 Controller 하나를 계속 비대하게 두지 않고 다음처럼 나눈다.

```text
dashboard/
  SellerDashboardController       # 경로·검증·응답
  SellerDashboardService          # 기간/권한/집계 조합
  SellerDashboardRepository       # JdbcTemplate SQL, RowMapper
  DashboardQuery                  # brandId·기간·page/size 검증
  DashboardDtos                   # API 응답 record
```

- 브랜드 권한 확인은 `SellerDashboardService.requireOwnedBrand` 한 곳에 둬 feedback/settlement의 중복 SQL을 단계적으로 제거한다.
- SQL은 파라미터 바인딩만 사용하고, `sort`, `granularity`처럼 SQL 식별자에 영향을 주는 값은 enum으로 화이트리스트 처리한다.
- 집계 SQL은 N+1을 피한다. 상품 목록은 상품별 상관 서브쿼리 대신 리뷰·피드백·판매를 각각 집계한 derived table로 join한다.
- 인덱스 검증 후 부족하면 `shop_order(status, paid_at, order_id)`, `order_item(brand_id, product_id, order_id)`, `review(product_id, status, created_at)`, `feedback(product_id, status, created_at)`를 migration으로 추가한다. 기존 스키마와 seed 모두에 반영한다.

## 6. 검증 계획

### 단위/통합 테스트

1. SELLER가 자기 브랜드의 각 엔드포인트를 200으로 읽고, MEMBER·타 브랜드 SELLER는 각각 403인지 검증한다.
2. `PAID`만 매출·수량·주문 수에 포함되고 CREATED/CANCELLED/REFUNDED는 제외되는지 검증한다.
3. 기간 경계(KST 00:00 포함), 잘못된 날짜, 최대 범위를 검증한다.
4. 상품 성과의 판매 0 상품, null 추천 여부, 다중 피드백 라벨, 시드 카탈로그 리뷰 귀속을 검증한다.
5. 정산 상세에서 다른 브랜드 settlement id를 지정해도 403/404 정보가 새지 않는지 검증한다.
6. page/size·안정 정렬·합계가 일관적인지 검증하고, 기존 세 API의 회귀 테스트를 추가한다.

### QA Acceptance 시나리오

테스트 데이터로 주문 생성 → PAID 처리 → 리뷰/피드백 작성 → 정산 생성 순서를 수행한다. 이후 판매자 토큰으로 각 API를 호출해 다음을 확인한다.

- 상품·브랜드 성과: PAID 주문 상품의 수량·매출·리뷰·피드백이 정확히 합산된다.
- 리뷰/피드백: 작성한 원문과 분류 상태·축/카테고리 집계가 조회되고, 숨김 행은 기본 목록에 나타나지 않는다.
- 매출: 일/월 합계와 총계가 같은 결제 완료 주문을 기준으로 일치한다.
- 정산: 생성된 월 정산의 gross/net 금액과 settlement item 합계가 일치하고, 완료 상태도 조회된다.

## 7. 작업 순서

1. DTO·공통 기간/권한·Repository 기반을 만들고 기존 summary/feedback/settlement 쿼리를 공용화한다.
2. summary·sales·products를 구현한다. 주문 DB 기반 지표를 먼저 완성한다.
3. reviews·feedback을 페이지/집계 형태로 확장한다.
4. settlements 목록·상세를 추가하고 기존 generate와 관리자 complete의 회귀를 확인한다.
5. MockMvc + MySQL 통합 테스트, OpenAPI 설명, 프론트 API adapter를 붙인다.
6. 위 QA 시나리오를 실행해 Acceptance Criteria 결과를 Jira에 남긴다.

## 8. 후속 결정이 필요한 항목

- 월 정산을 배치로 자동 생성할지, 판매자/관리자 조작으로 둘지는 제품 정책 결정이 필요하다.
- REFUNDED 주문과 완료 정산의 상계 방식은 현재 스키마/정책에 없다. 환불 기능을 시작할 때 정산 조정 전표 또는 다음 달 차감 규칙을 확정해야 한다.
- 행동 이벤트의 조회·장바구니·전환 지표는 DW projection 준비 후 마트 API와 병합한다. 주문 DB API의 매출과 이벤트 기반 전환을 동일한 지표로 섞지 않는다.
