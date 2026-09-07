# 통합몰 Event 브랜드 귀속 계약

작성일: 2026-09-07
상태: 브랜드 기준 귀속 계약 및 물리 구현 반영

## 1. 결정

브랜드 운영자는 브랜드별 계정을 가지며, 하나의 브랜드 계정은 정확히 하나의
`brand_id`에 연결된다. 계정·로그인·조회 인가는 Backend 책임이고, 행동 분석 DW에는
인증 계정 식별자를 복제하지 않는다.

```text
brand_account 1 ─ 1 brand 1 ─ N product

Event.product_id
→ dim_product.brand_id
→ 브랜드 Fact·Mart
```

- Event는 상품 대상 행동의 `product_id`를 직접 기록한다.
- `brand_id`는 Processed에서 `dim_product` Join으로 파생한다.
- Fact·Mart는 Join 시점의 `brand_id`를 스냅샷으로 보존한다.
- 브랜드 대시보드는 로그인 계정에 연결된 단일 `brand_id`만 조회한다.
- 행동 `purchase` Event는 전환 분석용이며 매출·정산은 Backend PAID 주문 상품
  Fact만 정본으로 사용한다.

## 2. Event 귀속 분류

| 분류 | 예 | `product_id` | 브랜드 귀속 |
| --- | --- | --- | --- |
| 상품 자체가 대상인 Event | 상품 노출·클릭·상세·장바구니 | 필수 | Dimension Join으로 파생 |
| 상품 상세 페이지·콘텐츠 Event | `page_view`, `section_view`, `section_dwell` + `page_type=product_detail` | 필수 | Dimension Join으로 파생 |
| 플랫폼 공통 페이지 Event | 홈·검색·장바구니 화면 진입 | NULL 허용 | 미귀속 |
| 플랫폼 목록 섹션 Event | 목록 프로모션·필터·상품 그리드 전체 | NULL 허용 | 미귀속 |
| 브랜드 자체 대상 Event | 향후 브랜드관 도입 시 | 선택 | 명시적 `brand_id` 계약을 먼저 추가 |

상품 미귀속은 JSON `null`로 표현하며 빈 문자열은 허용하지 않는다. route, 표시명,
직전 Event, 세션의 첫 상품 또는 세션 내 다른 상품으로 브랜드를 추정하지 않는다.
교차 브랜드 유입은 세션 내 상품 Event의 실제 `brand_id` 순서로 계산한다.

## 3. Dimension 및 스냅샷 규칙

- `dim_brand` grain/key는 `brand_id`다.
- `dim_product` grain/key는 `product_id`이고 모든 판매 상품은 비어 있지 않은
  `brand_id` 하나를 가진다.
- Join은 `Event.product_id = dim_product.product_id`의 left join이다.
- Dimension에 없는 `product_id`는 Fact에서 제거하지 않고 `brand_id=NULL`로
  보존하며 품질 보고서에 건수와 표본 ID를 기록한다.
- 중복 또는 충돌 Dimension 값으로 임의 브랜드를 선택하지 않는다.
- `brand_id` 스냅샷은 후속 Dimension 변경 시 자동으로 다시 해석하지 않는다.

## 4. 검증 조건

1. `dim_brand.brand_id`와 `dim_product.product_id`는 각각 유일하다.
2. `dim_product`의 모든 판매 상품은 유효한 `dim_brand.brand_id`를 참조한다.
3. 상품 Dimension Join 전후 row 수가 같다.
4. 매칭 상품의 Fact `brand_id`가 Dimension 값과 같다.
5. 미등록 상품 ID는 품질 결과에 기록되고 `brand_id`는 NULL이다.
6. `product_id=NULL`인 Event의 `brand_id`는 NULL이다.
7. 세션 정렬과 Funnel grain은 `session_id`를 기준으로 한다.
8. 같은 입력을 다시 실행하면 row 수와 `(Fact key, product_id, brand_id)` 결과가 같다.
9. Processed Fact·Mart 및 DW 계약에는 `brand_id`보다 상위인 소유 주체 식별 축을 두지 않는다.
10. 행동 `purchase` Event의 금액을 매출·정산 입력으로 사용하지 않는다.
