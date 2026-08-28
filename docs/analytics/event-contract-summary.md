# Event Contract Summary

상태: Draft  
목적: Frontend, Backend, Data, Dashboard 팀이 함께 합의할 Event Taxonomy, Trigger, Event Schema 요약본  
상세 문서: `docs/analytics/event-taxonomy-trigger-schema.md`

## 1. 한 줄 정의

테스트 쇼핑몰에서 발생한 사용자/Persona 행동을 `Event`로 수집하고, 이를 Kafka/Spark/DW를 거쳐 B2B Dashboard의 상품 반응, 정보 관심도, Funnel, 고객군별 인사이트로 변환한다.

## 2. Event 설계 원칙

| 원칙 | 결정 |
| --- | --- |
| Event 이름 | `lower_snake_case` 사용 |
| 기본 단위 | 모든 행동은 공통 Envelope + Event별 properties로 전송 |
| 세션 기준 | 하나의 쇼핑 흐름은 `session_id`, 하나의 페이지 방문은 `page_view_id` |
| 상품 기준 | 상품 관련 Event는 `product_id` 필수 |
| 성분/리뷰 기준 | 별도 Event를 늘리기보다 `section_id`, `content_kind`로 구분 |
| 전송 방식 | Front Logger가 batch로 비동기 전송 |
| 중복 제거 | `event_id` 기준. 노출/섹션 조회는 별도 dedupe key 권장 |

## 3. Event Taxonomy

### 3.1 P0 - MVP 필수

Dashboard 핵심 KPI와 Funnel 계산에 반드시 필요한 Event다.

| event_name | 의미 | 주요 활용 |
| --- | --- | --- |
| `session_start` | 쇼핑 세션 시작 | 전체 방문 수, 세션당 행동 수 |
| `page_view` | 페이지 진입 | 페이지별 방문, 이탈 분석 |
| `product_view` | 상품 상세 조회 | 상세 조회 수, Funnel 시작점 |
| `product_impression` | 상품 카드 유효 노출 | 노출 수, CTR 분모 |
| `product_click` | 상품 카드 클릭 | 클릭 수, CTR 분자 |
| `section_view` | 섹션/콘텐츠 유효 조회 | 성분/리뷰 열람률 |
| `section_dwell` | 섹션/콘텐츠 체류시간 | 정보 관심도, 평균 체류시간 |
| `accordion_toggle` | 접힌 상세 정보 펼침/닫힘 | 성분/사용법 검증 행동 |
| `add_to_cart` | 장바구니 담기 | 장바구니 전환율 |
| `view_cart` | 장바구니 화면 진입 | Cart 확인율 |
| `begin_checkout` | 구매 진행 시작 | Checkout 전환율 |
| `purchase` | 테스트 구매 완료 | 구매 전환율 |
| `exit_summary` | 페이지 이탈 요약 | 상세페이지 이탈률 |

### 3.2 P1 - 차별화/해석 강화

화장품 탐색 행동을 더 잘 설명하기 위한 Event다.

| event_name | 의미 | 주요 활용 |
| --- | --- | --- |
| `recommendation_impression` | 추천/유사 상품 노출 | 추천 CTR |
| `recommendation_click` | 추천/유사 상품 클릭 | 추천 반응 |
| `scroll_depth` | 스크롤 깊이 도달 | 탐색 깊이 |
| `scroll_pause` | 스크롤 후 멈춤 | 관심 지점 |
| `scroll_backtrack` | 다시 위로 되돌아봄 | 비교/재확인 |
| `media_view` | 이미지/미디어 조회 | 이미지 관심도 |
| `variant_select` | 색/향/용량 옵션 선택 | 옵션 관심 |
| `quantity_change` | 수량 변경 | 구매 의도 강도 |
| `review_filter_apply` | 리뷰 필터/정렬 적용 | 리뷰 관심도 |
| `review_expand` | 리뷰 상세/리뷰 영역 이동 | 리뷰 확인 행동 |
| `ingredient_view_mode_change` | 성분 보기 방식 변경 | 성분 상세 관심 |
| `wishlist_toggle` | 찜 추가/해제 | 지속 관심 |
| `text_selection` | 텍스트 선택 | 관심 문장/성분 |
| `text_copy` | 텍스트 복사 | 강한 검증 행동 |

### 3.3 P2 - 후순위/확장

| event_name | 의미 | 비고 |
| --- | --- | --- |
| `search` | 검색 실행 | 상품 목록 구현 후 Trigger 확정 |
| `filter_change` | 상품 필터 적용/해제 | 상품 목록 구현 후 Trigger 확정 |
| `sort_change` | 정렬 변경 | 확장 |
| `compare_products` | 상품 비교 | 확장 |
| `remove_from_cart` | 장바구니 제거 | 장바구니 구현 후 Trigger 확정 |
| `hover_dwell` | CTA 위 망설임 | 보조 신호 |
| `rage_click` | 반복 클릭 | UX 마찰 |
| `dead_click` | 클릭 불가 영역 클릭 | UX 마찰 |

`wishlist_toggle`은 `action=add/remove`로 찜 추가와 해제를 함께 표현한다. 별도 `remove_from_wishlist` Event는 두지 않는다.

## 4. Trigger 요약

| event_name | Trigger 기준 |
| --- | --- |
| `session_start` | Persona/User가 새 쇼핑 세션을 시작하거나 Persona가 변경될 때 |
| `page_view` | 라우트 진입 또는 상품 변경 완료 시 |
| `product_view` | 상품 상세 데이터 렌더링 완료 및 `product_id` 확정 시 |
| `product_impression` | 상품 카드가 viewport 50% 이상에서 1초 이상 노출될 때 |
| `product_click` | 상품 카드 클릭 후 상세 이동이 시작될 때 |
| `section_view` | 섹션/콘텐츠가 유효 노출 기준을 만족하고 400ms 이상 유지될 때 |
| `section_dwell` | 섹션/콘텐츠가 화면을 벗어나거나 페이지 이탈/15초 checkpoint 도달 시 |
| `accordion_toggle` | Accordion 펼침/닫힘 클릭 시 |
| `scroll_depth` | 상세 페이지에서 10% 단위 milestone 최초 도달 시 |
| `scroll_pause` | 스크롤 이동 후 320ms 이상 멈추고 이동거리 24px 이상일 때 |
| `scroll_backtrack` | 아래로 탐색하다가 240px 이상 위로 되돌아볼 때 |
| `media_view` | 이미지 썸네일 또는 미디어 항목 선택 시 |
| `review_filter_apply` | 리뷰 필터 또는 정렬 조건 변경 완료 시 |
| `text_selection` | 페이지 텍스트 선택 후 350ms 안정화 시 |
| `text_copy` | 페이지 텍스트 복사 시 |
| `wishlist_toggle` | 찜 추가/해제 성공 시 |
| `add_to_cart` | 장바구니 추가 성공 시 |
| `view_cart` | 장바구니 페이지 진입 시 |
| `begin_checkout` | 구매 진행 시작 성공 시 |
| `purchase` | 테스트 주문 완료 확정 시 |
| `exit_summary` | 탭 숨김, pagehide, 페이지/상품 이동 시 |

## 5. Event Schema

### 5.1 Schema 흐름

Front → Collector → Kafka 구간에서는 같은 Raw Event Schema를 유지한다.

```text
Frontend LogEnvelope
→ Collector 검증 + 서버 메타 필드 추가
→ Kafka raw_events topic
→ Spark 처리
→ Processed/DW 테이블
```

Collector는 Event 구조를 바꾸지 않고, `received_at`, `source`, `ingest_id`처럼 서버에서만 알 수 있는 필드만 추가한다. 분석용 테이블 구조는 Spark 이후에 바뀐다.

### 5.2 Raw Event Schema

프론트가 Collector로 보내고, Collector가 Kafka에 넣는 Raw Event는 아래 flat 구조를 기준으로 한다.

```json
{
  "schema_version": "1.0.0-draft",
  "event_id": "uuid",
  "event_name": "add_to_cart",
  "intent": "conversion",
  "occurred_at": "2026-08-28T01:13:12.123Z",
  "persona_id": "persona_1024",
  "session_id": "session_923",
  "page_view_id": "pv_1001",
  "sequence_no": 12,
  "page_type": "product_detail",
  "product_id": "P342",
  "actor_type": "user",
  "environment": "local",
  "received_at": "2026-08-28T01:13:12.420Z",
  "source": "web",
  "properties": {
    "sku_id": "SKU342-01",
    "quantity": 1,
    "price_usd": 32
  }
}
```

현재 프론트 구현은 `schema_version=0.2.0-draft`이며, 팀 합의 후 확정 버전으로 올린다.

### 5.3 필수 공통 필드

| field | 필수 | 설명 |
| --- | --- | --- |
| `schema_version` | Y | Schema 버전 |
| `event_id` | Y | Event 고유 ID |
| `event_name` | Y | Event 이름 |
| `intent` | Y | Event의 마케팅 의미 |
| `occurred_at` | Y | 클라이언트 발생 시각 |
| `received_at` | Server | Collector 수신 시각 |
| `source` | Server | `web`, `simulator`, `server` 등 |
| `persona_id` | 조건부 | Persona 기반 행동이면 필요 |
| `session_id` | Y | 쇼핑 세션 ID |
| `page_view_id` | Y | 페이지 방문 ID |
| `sequence_no` | Y | 세션 내 Event 순서 |
| `page_type` | Y | `product_detail`, `product_list`, `cart`, `checkout` 등 |
| `product_id` | 조건부 | 상품 관련 Event이면 필요 |
| `actor_type` | Y | `user` 또는 `synthetic` |
| `environment` | Y | `local`, `dev`, `loadtest` 등 |
| `properties` | Y | Event별 세부 값 |

### 5.4 Event별 주요 properties

| event_name | 주요 properties |
| --- | --- |
| `product_view` | `product_id`, `entry_source`, `list_id`, `position` |
| `product_impression` | `product_id`, `list_id`, `position`, `visible_ratio` |
| `product_click` | `product_id`, `list_id`, `position`, `impression_event_id` |
| `section_view` | `section_id`, `content_kind`, `content_ref`, `visible_duration_ms` |
| `section_dwell` | `section_id`, `content_kind`, `content_ref`, `dwell_ms`, `co_visible_blocks` |
| `scroll_depth` | `depth_percent`, `section_id`, `content_kind` |
| `accordion_toggle` | `section_id`, `content_kind`, `action` |
| `review_filter_apply` | `filter`, `sort`, `result_count` |
| `wishlist_toggle` | `product_id`, `action` |
| `add_to_cart` | `product_id`, `sku_id`, `quantity`, `price_usd` |
| `begin_checkout` | `items`, `cart_value` |
| `purchase` | `order_id`, `items`, `order_value` |
| `exit_summary` | `dwell_ms`, `max_scroll_percent`, `last_section_id`, `last_content_kind`, `reason` |

## 6. 주요 Enum

### 6.1 intent

| intent | 의미 | 예시 |
| --- | --- | --- |
| `session` | 세션/페이지 경계 | `session_start`, `page_view`, `product_view` |
| `exposure` | 화면에 노출됨 | `product_impression`, `scroll_depth` |
| `interest` | 관심 있게 봄 | `section_view`, `section_dwell`, `media_view` |
| `comparison` | 비교/탐색 | `product_click`, `variant_select`, `scroll_backtrack` |
| `validation` | 구매 판단 근거 확인 | `accordion_toggle`, `review_filter_apply`, `text_selection` |
| `hesitation` | 전환 전 망설임 | `hover_dwell` |
| `conversion` | 전환 행동 | `wishlist_toggle`, `add_to_cart`, `purchase` |
| `friction` | 사용성 마찰 | `rage_click`, `dead_click` |

### 6.2 section_id

| section_id | 설명 |
| --- | --- |
| `product_hero` | 이미지, 가격, 옵션, CTA |
| `highlights` | 상품 주요 특징 |
| `about_product` | 상품 설명 |
| `ingredients` | 성분 정보 |
| `how_to_use` | 사용법 |
| `similar_products` | 유사/추천 상품 |
| `reviews` | 리뷰 |

### 6.3 content_kind

| content_kind | 설명 |
| --- | --- |
| `product_image` | 상품 이미지 |
| `price` | 가격 |
| `variant_option` | 옵션 |
| `cta` | 장바구니/찜 CTA |
| `ingredient_list` | 전체 성분 |
| `ingredient_callout` | 주요/주의 성분 |
| `clinical_claim` | 임상 근거 |
| `usage_guide` | 사용법 |
| `persona_match` | 피부 타입/고민 매칭 |
| `user_review` | 개별 리뷰 |
| `review_stats` | 리뷰 요약 |
| `review_filter` | 리뷰 필터/정렬 |
| `recommendation_card` | 추천 상품 카드 |

## 7. GA4 매핑

| GA4 Event | 우리 Event |
| --- | --- |
| `view_item` | `product_view` |
| `view_item_list` | `product_impression` |
| `select_item` | `product_click` |
| `add_to_wishlist` | `wishlist_toggle(action=add)` |
| `add_to_cart` | `add_to_cart` |
| `view_cart` | `view_cart` |
| `remove_from_cart` | `remove_from_cart` |
| `begin_checkout` | `begin_checkout` |
| `purchase` | `purchase` |

## 8. Dashboard KPI 연결

| KPI | 계산 기준 |
| --- | --- |
| 상품 상세 조회 수 | `count(product_view)` |
| 상품 상세 진입률 | `product_view / product_impression` |
| CTR | `product_click / product_impression` |
| 성분 정보 열람률 | 성분 관련 `section_view` 발생 page_view / `product_view` |
| 리뷰 정보 열람률 | 리뷰 관련 `section_view` 발생 page_view / `product_view` |
| 장바구니 전환율 | `add_to_cart` 발생 session/product / `product_view` 발생 session/product |
| 구매 전환율 | `purchase` 발생 session/product / `product_view` 발생 session/product |
| 단계별 이탈률 | `1 - 다음 단계 도달 수 / 현재 단계 도달 수` |

MVP Funnel:

```text
product_impression
→ product_click
→ product_view
→ information_view
→ add_to_cart
→ begin_checkout
→ purchase
```

`information_view`는 성분/리뷰 관련 `section_view`, `accordion_toggle`, `review_filter_apply`, `review_expand` 등으로 파생한다.

## 9. 구현 상태

| 상태 | Event |
| --- | --- |
| 현재 구현됨 | `session_start`, `page_view`, `section_view`, `section_dwell`, `accordion_toggle`, `recommendation_impression`, `recommendation_click`, `product_click`, `wishlist_toggle`, `add_to_cart`, `exit_summary`, `scroll_depth`, `media_view`, `variant_select`, `quantity_change`, `review_filter_apply`, `review_expand`, `scroll_pause`, `scroll_backtrack`, `text_selection`, `text_copy`, `hover_dwell`, `rage_click`, `dead_click` |
| 보강 필요 | `product_view`, `ingredient_view_mode_change` |
| 후속 화면 구현 후 확정 | `product_impression`, `search`, `filter_change`, `sort_change`, `compare_products`, `view_cart`, `remove_from_cart`, `begin_checkout`, `purchase` |

## 10. 팀 합의 필요 사항

합의사항은 모두 같은 급이 아니다. 아래 `필수` 항목은 공식 Raw Event Schema 확정 전에 먼저 정해야 한다.

| 우선순위 | 안건 | 결정 필요 내용 | 추천안 |
| --- | --- | --- | --- |
| 필수 | Raw Event Schema 기준 | Front → Collector → Kafka 구간에서 flat Raw Schema를 공식으로 둘지 | flat Raw Schema 유지 |
| 필수 | `product_view` 생성 위치 | Front가 직접 보낼지, Collector/Spark가 `page_view`에서 파생할지 | Front에서 직접 전송 권장 |
| 필수 | `section_dwell` 합산 | Front에서 합산할지, Spark/DW에서 합산할지 | Spark/DW 합산 권장 |
| 필수 | Synthetic/Web Event 분리 | 같은 Raw 테이블에 둘지 물리 분리할지 | 같은 테이블 + `actor_type/source` 분리 |
| 필수 | `text_snippet` 저장 | 선택/복사 텍스트 원문 저장 여부 | MVP는 원문보다 해시/성분 매칭 결과 권장 |
| MVP 범위 | Dashboard 기본 산식 | session/product 기준으로 먼저 만들지 | session/product 기준 우선 |
| MVP 범위 | 집계 기간 | 실시간/일간/최근 7일 중 MVP 범위 | 일간 + 최근 7일 우선 |
| 구현 후 재검증 | 목록/장바구니/구매 Trigger | 후속 화면 구현 후 Trigger 확정 | 화면 구현 직후 재검증 |
| 확장 | 관심도 가중치 | 초기 가중치 확정 여부 | `[추정]`으로 두고 샘플 데이터로 조정 |
| 확장 | 비정상 행동 | 감점할지 별도 UX 지표로 둘지 | MVP는 별도 품질 지표, 이후 감점 |

## 11. 현재 문서와 추후 분리 기준

현재 작성된 Event 관련 문서는 2개다.

| 현재 문서 | 목적 |
| --- | --- |
| `event-contract-summary.md` | 팀 공유 및 합의용 요약 |
| `event-taxonomy-trigger-schema.md` | Event Taxonomy, Trigger, Schema 상세 초안 |

추후 구현이 진행되면 아래 문서를 별도로 분리할 수 있다.

| 추후 문서 | 담을 내용 |
| --- | --- |
| `contracts/event-schema.json` | Backend Collector가 검증할 실제 JSON Schema |
| DW 설계 문서 | `raw_events`, `product_daily_kpi`, `content_interest_fact`, `funnel_session_fact` 등 테이블 정의 |
| Dashboard 산식 문서 | 화면별 KPI, 필터, 집계 기준 |
| Front 구현 문서 | 실제 컴포넌트/훅별 Trigger 위치 |

회의에서는 이 요약 문서로 합의하고, 합의 결과를 상세 문서와 추후 `contracts/event-schema.json`에 반영한다.
