# 통합몰 Event 귀속 계약

작성일: 2026-09-07
상태: 계약 확정, Producer·Spark·DW 물리 반영 대기

## 1. 결정

서비스는 하나의 통합 쇼핑몰이며 사업자별 독립 Storefront가 아니다.
따라서 소비자 행동 Event에 `tenant_id`를 격리 key로 두지 않는다.

```text
business 1 ─ N brand 1 ─ N product

Event.product_id
→ dim_product.brand_id
→ dim_brand.business_id
```

- Event는 상품 대상 행동의 `product_id`를 직접 기록한다.
- `brand_id`, `business_id`는 Processed에서 Dimension Join으로 파생한다.
- Fact·Mart는 집계 시점의 `brand_id`, `business_id`를 스냅샷으로 보존한다.
- 사업자 대시보드 접근은 Backend의 `business_id → brand_id` 소유 인가로
  격리한다.
- 행동 `purchase` Event는 전환 분석용이며 매출·정산은 Backend PAID
  주문 상품 Fact만 정본으로 사용한다.

## 2. Event 귀속 분류

| 분류 | 예 | `product_id` | 사업자·브랜드 귀속 |
| --- | --- | --- | --- |
| 상품 자체가 대상인 Event | 상품 노출·클릭·상세·장바구니 | 필수 | Dimension Join으로 파생 |
| 상품 상세 페이지·콘텐츠 Event | `page_view`, `section_view`, `section_dwell` + `page_type=product_detail` | 필수 | Dimension Join으로 파생 |
| 플랫폼 공통 페이지 Event | 홈·검색·장바구니 화면 진입 | NULL 허용 | 미귀속 |
| 플랫폼 목록 섹션 Event | 목록의 프로모션·필터·상품 그리드 전체 `section_view`, `section_dwell` | NULL 허용 | 미귀속 |
| 브랜드 자체 대상 Event | 향후 브랜드관 도입 시 | 선택 | 명시적 `brand_id` 계약을 먼저 추가 |

상품 미귀속은 JSON `null`로 표현하며 빈 문자열은 허용하지 않는다. route, 표시명,
직전 Event, 세션의 첫 상품 또는 세션 내 다른 상품으로 사업자·브랜드를 임의 추정하지
않는다. 교차 브랜드 유입은 세션 내 상품 Event의 실제 `brand_id` 순서로 계산한다.

## 3. Schema version

- 현재 Producer의 `0.2.0-draft`를 유지한다.
- `tenant_id`를 필수로 하려던 `0.3.0-draft`는 Producer 반영 전 철회한다.
- `0.3.0-draft` Event와 top-level `tenant_id`는 현재 JSON Schema에서 거부한다.
- 향후 Envelope 변경이 필요하면 새 schema version과 이전 계약을 먼저 확정한다.

## 4. 영향 범위와 담당 경계

| 범위 | 후속 조치 | 권장 담당 |
| --- | --- | --- |
| `contracts/` | Event·Raw·Processed·DW 논리 계약 반영 | Data |
| Producer·Collector | 0.3 tenant 반영 보류, 0.2 계약 유지 | Backend/Infra |
| `streaming/jobs/raw_sink_job.py` | tenant Raw projection 제거 | Spark/Infra |
| `streaming/jobs/clean_events_job.py` | tenant 필수·형식 검증 제거 | Spark/Infra |
| `streaming/jobs/derive_facts_job.py` | tenant 세션 경계 제거, Dimension 계약 연결 | Spark/Infra 후 Data Fact Jira |
| `streaming/jobs/build_marts_job.py` | tenant 필터·group·partition 제거 | Spark/Infra 후 Data Mart Jira |
| Dimension·Fact·Mart 물리 구현 | business·brand·product 귀속과 품질 검증 | Data 후속 Jira |

물리 Delta partition을 `business_id` 또는 `brand_id`로 즉시 바꾸지 않는다.
집계·조회 key와 물리 partition은 다르며, 파일 수·카디널리티·조회 패턴을
Delta 구현 Jira에서 검증해 확정한다.

## 5. 검증 조건

1. `event-schema.json`은 `0.2.0-draft`만 허용하고 top-level `tenant_id`를
   거부한다.
2. 상품 자체가 대상인 Event와 상품 상세의 `page_view`, `section_view`,
   `section_dwell`은 `product_id`가 비어 있지 않은 string이다.
3. 플랫폼 공통 `page_view`와 상품 목록의 `section_view`, `section_dwell`은
   `product_id=NULL`을 허용한다. 빈 문자열은 허용하지 않는다.
4. 상품 Dimension Join 전후 row 수가 의도하지 않게 증가하지 않는다.
5. 모든 판매 상품은 하나의 `brand_id`에, 모든 브랜드는 하나의
   `business_id`에 귀속한다.
6. `product_id=NULL`인 플랫폼 공통 Event의 `business_id`, `brand_id`는 NULL을
   유지하고 상품 Dimension Join 대상으로 처리하지 않는다.
7. 사업자 A의 인증으로 사업자 B 소유 브랜드 Mart를 조회할 수 없다.
8. 행동 `purchase` Event의 금액을 매출·정산 입력으로 사용하지 않는다.
