# Event Contract Summary

상태: Draft. Kafka payload 서버 메타 필드 계약은 BE 커넥터 담당 확인 완료(2026-08-31)
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
| 상품 상세 조회 기준 | 상세 진입 시 `page_view(page_type=product_detail)` 직후 `product_view`를 별도 전송하고, 두 Event는 같은 `page_view_id`를 공유 |
| 명세 단일 출처 | Event 계약(이름, 필수 필드, properties, enum)의 원본은 이 문서와 상세 문서(`event-taxonomy-trigger-schema.md`)다. `frontend/src/types/log.ts`는 프론트 구현 기준 미러로 관리한다 |
| 가중치 단일 출처 | 가중치 **상수**는 예외로 `frontend/src/types/log.ts`가 원본이다. `batch/jobs/behavior_weights.py`가 이 파일을 파싱해 쓰고 파싱 실패 시 예외로 죽으므로, 문서에 숫자를 복사하면 조용히 어긋난다. 문서는 근거와 척도만 적는다 |
| 성분/리뷰 기준 | 별도 Event를 늘리기보다 `section_id`, `content_kind`로 구분 |
| 전송 방식 | Front Logger가 batch로 비동기 전송 |
| 중복 제거 책임 | Backend Collector는 Redis/DB로 중복 차단하지 않아도 된다. Raw는 중복 수신을 허용하고, Data/Spark Processed 단계에서 `event_id` 기준으로 중복 제거한다 |
| 대표 Event 선정 | 같은 `event_id`가 여러 건이면 `received_at ASC`, 동률이면 `kafka_partition ASC`, `kafka_offset ASC` 기준의 최초 1건을 정본으로 사용한다 |
| 재시도 조건 | Front가 같은 Event를 재전송할 때는 반드시 같은 `event_id`를 유지한다 |
| 노출 중복 | 노출/섹션 조회는 `event_id` 외에 별도 `dedupe_key`를 함께 둘 수 있다 |

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
| `quick_look` | 목록 상품 요약 창 열림 | 상세 진입 전 관심 |
| `quick_look_close` | 목록 상품 요약 창 닫힘 | 요약 창 체류/행동 요약 |
| `wishlist_toggle` | 찜 추가/해제 | 지속 관심 |
| `remove_from_cart` | 장바구니 제거 | 장바구니 단계 마찰 |
| `text_selection` | 텍스트 선택 | 관심 문장/성분 |
| `text_copy` | 텍스트 복사 | 강한 검증 행동 |

### 3.3 P2 - 후순위/확장

| event_name | 의미 | 비고 |
| --- | --- | --- |
| `search` | 검색 실행 | 상품 목록 구현 후 Trigger 확정 |
| `filter_change` | 상품 필터 적용/해제 | 상품 목록 구현 후 Trigger 확정 |
| `sort_change` | 정렬 변경 | 확장 |
| `compare_products` | 상품 비교 | 확장 |
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
| `recommendation_impression` | 추천/유사 상품 카드가 viewport 50% 이상에서 1초 이상 노출될 때 |
| `recommendation_click` | 추천/유사 상품 카드 클릭 시 |
| `section_view` | 섹션/콘텐츠가 유효 노출 기준을 만족하고 400ms 이상 유지될 때 |
| `section_dwell` | 섹션/콘텐츠가 화면을 벗어나거나 페이지 이탈/15초 checkpoint 도달 시 |
| `accordion_toggle` | Accordion 펼침/닫힘 클릭 시 |
| `scroll_depth` | 상세 페이지에서 10% 단위 milestone 최초 도달 시 |
| `scroll_pause` | 스크롤 이동 후 320ms 이상 멈추고 이동거리 24px 이상일 때 |
| `scroll_backtrack` | 아래로 탐색하다가 240px 이상 위로 되돌아볼 때 |
| `media_view` | 이미지 썸네일 또는 미디어 항목 선택 시 |
| `quick_look` | 목록/기획전 상품 요약 창이 열릴 때 |
| `quick_look_close` | 요약 창이 닫힐 때 |
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

Collector는 Event 구조를 바꾸지 않고 검증, 서버 메타 필드 추가, Kafka 전송을 담당한다. BE 커넥터 담당 확인 결과(2026-08-31), 현재 Kafka payload에 포함되는 `received_at`, `source`, `request_id`, `event_index` 구조를 최종 Raw Kafka 계약으로 사용한다. `source`는 Collector가 `actor_type=synthetic`이면 `simulator`, 그 외에는 `web`으로 기록한다. Raw 계층은 중복 수신 Event까지 그대로 보존하고, 분석용 테이블 구조와 중복 제거는 Spark 이후에 적용한다.

### 5.2 Raw Event Schema

Collector가 Kafka에 넣는 최종 Raw Event는 아래 flat 구조를 기준으로 한다. 프론트는 서버 메타 필드를 제외한 LogEnvelope를 보내고, Collector가 Kafka payload에 서버 메타 필드를 추가한다.

```json
{
  "schema_version": "0.2.0-draft",
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
  "request_id": "req_20260828_001",
  "event_index": 0,
  "properties": {
    "sku_id": "SKU342-01",
    "quantity": 1,
    "price_usd": 32
  }
}
```

E2E 기준 `schema_version`은 현재 프론트 구현과 맞춰 `0.2.0-draft`로 둔다. `1.0.0-draft`는 JSON Schema와 구현 계약을 확정한 뒤 올릴 후보 버전이다. 요청 body의 top-level `schema_version`과 각 Event의 `schema_version`이 함께 존재하면 값은 같아야 한다.

같은 `event_id`가 Raw에 여러 건 있으면 Processed의 `cleaned_events` 생성 단계에서만 중복 제거한다. 대표 Event는 `received_at ASC`, `kafka_partition ASC`, `kafka_offset ASC` 순으로 정렬했을 때 첫 번째 row다. 현재 Kafka key가 `session_id`이고 재시도 시 같은 `event_id`와 `session_id`를 유지하는 전제라 중복 Event는 보통 같은 partition에 들어가며, offset이 안정적인 tie-breaker가 된다. DW/Mart는 이 중복 제거가 끝난 Dataset만 입력으로 사용한다.

### 5.3 필수 공통 필드

| field | 필수 | 설명 |
| --- | --- | --- |
| `schema_version` | Y | Schema 버전 |
| `event_id` | Y | Event 고유 ID |
| `event_name` | Y | Event 이름 |
| `intent` | Y | Event의 마케팅 의미 |
| `occurred_at` | Y | 클라이언트 발생 시각. RFC 3339 offset(`Z`, `+09:00` 등) 허용 |
| `received_at` | Server | Collector 수신 시각. RFC 3339 offset 허용, Kafka payload 포함, Processed에서 UTC로 정규화 |
| `source` | Server | `web`, `simulator`, `server` 등. 현재 Collector는 `actor_type=synthetic`이면 `simulator`, 그 외에는 `web`으로 Kafka payload에 포함 |
| `request_id` | Server | 한 번의 batch 요청을 묶는 ID. Kafka payload와 HTTP 응답에 포함 |
| `event_index` | Server | batch 안 Event 순서. Kafka payload 포함 |
| `persona_id` | 조건부 | Persona 기반 행동이면 필요 |
| `session_id` | Y | 쇼핑 세션 ID |
| `page_view_id` | Y | 페이지 방문 ID. `session_start`와 첫 `page_view`는 같은 값을 공유 |
| `sequence_no` | Y | 세션 내 Event 순서 |
| `page_type` | Y | MVP 기준 `product_detail`, `product_list`, `cart` |
| `product_id` | 조건부 | 상품 관련 Event이면 필요. 값은 보고 있는 상품이 아니라 Event 대상 상품 기준 |
| `actor_type` | Y | `user` 또는 `synthetic` |
| `environment` | Y | `local`, `dev`, `loadtest` 등 |
| `properties` | Y | Event별 세부 값 |

`scenario_id`, `simulation_run_id`는 분석 논리 필드다. 현재 API DTO에는 top-level 필드가 없으므로 E2E 기준 물리 위치는 `properties.scenario_id`, `properties.simulation_run_id`로 보고, Processed 단계에서 컬럼으로 승격한다.

`actor_type='synthetic'`인 Event는 아래 3개를 `properties`에 반드시 포함한다. 실제 Web Event(`actor_type='user'`)에는 적용하지 않으므로 프론트 구현에는 영향이 없다.

| property | 설명 |
| --- | --- |
| `scenario_id` | 시뮬레이션 상황 ID. 예: `normal_day`, `sale_burst` |
| `simulation_run_id` | 실행 1회 식별자. 같은 시나리오를 여러 번 돌린 결과를 분리 |
| `generator_type` | 생성 방식. `python_batch`, `agent_realtime` |

강제 지점은 Simulator(생성 시)와 Spark semantic validation이다. Collector는 `properties`를 구조 변경 없이 통과시키므로 별도 검증 구현은 선택 사항이다.

`persona_source`(`agent_sample`/`batch_sample`)는 Persona의 정적 속성이라 **Event에 싣지 않는다.** Dashboard에서 표본을 나눠 봐야 하면 `simulation_run_id → dim_simulation_run.persona_source`로 Join한다.

`session_start.page_view_id`는 첫 `page_view`와 같은 값을 공유한다. 세션의 첫 `page_view`는 `properties.navigation_source='session_start'`로 구분한다. 상품 상세 URL로 직접 진입한 경우에도 첫 `page_view` 직후 같은 `page_view_id`로 `product_view`를 남긴다.

### 5.4 Event별 주요 properties

`product_id`는 상품 대상 Event에서 공통 top-level 필드로 보내며, 값은 Event 대상 상품을 기준으로 한다. 예를 들어 A 상품 상세에서 추천 상품 B를 클릭하면 top-level `product_id`는 B이고, A는 `properties.context_product_id`로 보낸다. 컨텍스트가 없거나 대상과 같으면 `context_product_id`는 생략한다. 섹션 체류·스크롤처럼 화면 자체를 대상으로 하는 Event는 보고 있는 상품을 `product_id`로 둔다.

아래 표는 `properties` 객체에 들어가는 주요 세부 값이다.

| event_name | 주요 properties |
| --- | --- |
| `session_start` | `entry_page`, `referrer`, `utm_source`, `utm_medium`, `utm_campaign` |
| `page_view` | `navigation_source`, `referrer`, `route` |
| `product_view` | `navigation_source`, `list_id`, `position`, `recommendation_id`, `context_product_id` |
| `product_impression` | `list_id`, `position`, `visible_ratio` |
| `product_click` | `list_id`, `position`, `entry_source`, `impression_event_id`, `context_product_id` |
| `recommendation_impression` | `recommendation_id`, `list_id`, `position`, `algorithm`, `visible_ratio`, `context_product_id` |
| `recommendation_click` | `recommendation_id`, `list_id`, `position`, `algorithm`, `impression_event_id`, `context_product_id` |
| `impression_dwell` | `list_id`, `position`, `visible_ms`, `recommendation_id`, `algorithm` |
| `recommendation_snapshot` | `recommendation_id`, `list_id`, `algorithm`, `size`, `ranking[]` |
| `quick_look` | `list_id`, `position`, `entry_source`, `recommendation_id`, `context_product_id` |
| `quick_look_close` | `close_reason`(`backdrop`/`escape`/`close_button`/`open_detail`), `dwell_ms`, `variants_viewed`, `added_to_cart`, `wishlisted` |
| `search` | `query_text`, `result_count`, `normalized_query` |
| `filter_change` | `filter_kind`, `filter_value`, `from`, `result_count` |
| `sort_change` | `sort_key`, `sort_direction`, `result_count` |
| `section_view` | `section_id`, `content_kind`, `content_ref`, `visible_duration_ms` |
| `section_dwell` | `section_id`, `content_kind`, `content_ref`, `dwell_ms`, `co_visible_blocks` |
| `scroll_depth` | `depth_percent`, `section_id`, `content_kind` |
| `accordion_toggle` | `section_id`, `content_kind`, `action` |
| `review_filter_apply` | `filter`, `sort`, `result_count` |
| `variant_select` | `sku_id`, `label`, `previous_sku_id`, `variant_group` |
| `wishlist_toggle` | `action` |
| `add_to_cart` | `sku_id`, `quantity`, `price_usd`, `entry_source`, `context_product_id` |
| `view_cart` | `item_count`, `distinct_products`, `cart_value` |
| `remove_from_cart` | `sku_id`, `quantity`, `cart_size_after`, `reason` |
| `begin_checkout` | `items`, `cart_value` |
| `purchase` | `order_id`, `items`, `order_value` |
| `exit_summary` | `dwell_ms`, `max_scroll_percent`, `last_section_id`, `last_content_kind`, `reason` |

`section_dwell.dwell_ms`는 누적값이 아니라 구간 체류시간(delta)이다.

`entry_source`는 상품 진입/장바구니 담기 경로를 나타낸다. 현재 값 후보는 `list_grid`, `promo_pick`, `similar_products`, `quick_look`, `cart` 등이다.

`product_view.navigation_source`는 같은 상세 진입의 `page_view.navigation_source`와 동일한 값을 싣는다. 직접 URL 진입처럼 `session_start`가 첫 `page_view`를 남기는 경로는 `product_view.navigation_source='session_start'`로 둔다. 이 값은 유입 경로별 상세 조회 수를 나눌 수 있게 하므로 현재 계약에서는 유지한다.

`recommendation_impression/click`은 상세 유사 상품뿐 아니라 목록/기획전의 `promo_pick` 리스트에서도 발생할 수 있다. `promo_pick`이 `skin_match_v0` 기반이어도 추천 CTR 산식은 동일하다.

`recommendation_impression` 중복 판단은 `page_view_id + list_id + recommendation_id + product_id + position` 기준으로 본다.

`begin_checkout`, `purchase`의 `items[]`는 Processed 단계에서 상품별 row로 펼쳐서 집계한다.

## 6. 주요 Enum

### 6.1 intent

| intent | 의미 | 예시 |
| --- | --- | --- |
| `session` | 세션/페이지 경계 | `session_start`, `page_view` |
| `exposure` | 화면에 노출됨 | `product_impression`, `scroll_depth` |
| `interest` | 관심 있게 봄 | `product_view`, `section_view`, `section_dwell`, `media_view`, `quick_look` |
| `comparison` | 비교/탐색 | `product_click`, `variant_select`, `scroll_backtrack` |
| `validation` | 구매 판단 근거 확인 | `accordion_toggle`, `review_filter_apply`, `text_selection` |
| `hesitation` | 전환 전 망설임 | `hover_dwell`, `remove_from_cart` |
| `conversion` | 전환 행동 | `wishlist_toggle`, `add_to_cart`, `view_cart`, `purchase` |
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
| `promo_row` | 목록 상단 기획전/추천 상품 행 |
| `list_controls` | 목록 필터/정렬 조작 영역 |
| `product_grid` | 상품 목록 그리드 |
| `cart_items` | 장바구니 상품 목록 |

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
| `product_card` | 목록/기획전 상품 카드 |

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
| `dev` 구현 완료(MR !24 포함, 35종) | `session_start`, `page_view`, `product_view`, `product_impression`, `product_click`, `section_view`, `section_dwell`, `accordion_toggle`, `recommendation_impression`, `recommendation_click`, `wishlist_toggle`, `add_to_cart`, `view_cart`, `exit_summary`, `scroll_depth`, `impression_dwell`, `recommendation_snapshot`, `media_view`, `quick_look`, `quick_look_close`, `remove_from_cart`, `variant_select`, `quantity_change`, `review_filter_apply`, `review_expand`, `ingredient_view_mode_change`, `sort_change`, `filter_change`, `scroll_pause`, `scroll_backtrack`, `text_selection`, `text_copy`, `hover_dwell`, `rage_click`, `dead_click` |
| 시뮬레이터 정책상 제외(1종) | `dead_click` |
| 후속 화면 구현 후 확정 | `search`, `compare_products`, `begin_checkout`, `purchase` |

최신 `dev` 생성기는 FE 35종 중 34종을 만든다. `ingredient_view_mode_change`, `text_copy`, `hover_dwell`, `impression_dwell`, `recommendation_snapshot`은 `bcc9c51`에서 반영됐다. 남은 `dead_click`은 실제 UI 오작동에서만 나오는 신호라 의도적으로 생성하지 않는다.

## 10. 팀 합의 현황

프론트/백 확인 결과, 공식 Raw Event Schema 작성에 필요한 핵심 방향은 아래처럼 정리한다.

| 상태 | 안건 | 결정 내용 |
| --- | --- | --- |
| 합의 | Event 명세 단일 출처 | Data 문서(`event-contract-summary.md`, `event-taxonomy-trigger-schema.md`)를 계약 원본으로 둔다. `frontend/src/types/log.ts`는 구현 미러이며 변경 MR에서 문서 동기화 여부를 함께 확인한다 |
| 합의 | Raw Event Schema 기준 | Front JSON 구조를 유지하고, Backend는 큰 가공 없이 검증과 서버 메타 필드만 추가 |
| 합의 | Event 수집 API | `POST /api/events`, body는 `{ schema_version, events: [ ...LogEnvelope ] }` |
| 합의 | E2E Schema Version | 계약 확정 전인 현재는 `0.2.0-draft` 유지. 이후 payload 변경 없는 설명 수정은 patch, Event/optional property 추가는 minor, 필드 삭제·이름/타입 변경·필수 전환·enum 의미 변경은 major 후보 |
| 합의 | batch 크기 | 프론트 기본값 20건 기준, 추후 부하 테스트 결과로 조정 |
| 합의 | 서버 메타 필드 | BE 커넥터 담당 확인 완료(2026-08-31). Kafka payload에는 `received_at`, `source`, `request_id`, `event_index` 포함 |
| 합의 | 계층별 중복 처리 | Raw는 수신 Event를 그대로 보존하고, Processed `cleaned_events` 생성 단계에서 `event_id` 기준으로 중복 제거 |
| 합의 | 대표 Event 선정 | 동일 `event_id`는 `received_at ASC`, 동률이면 `kafka_partition ASC`, `kafka_offset ASC` 기준 최초 1건을 정본으로 사용 |
| 합의 | `source` 기준 | 현재 Collector는 `actor_type=synthetic → simulator`, 그 외 → `web`으로 기록. 서버 내부 Event는 후속 필요 시 `server` |
| 합의 | 검증 실패 Event | 전체 batch 실패보다 실패 Event만 분리 처리하는 방향 |
| 합의 | `product_view` 생성 위치 | MR !24가 `dev`에 반영됨. 상세 진입 시 `page_view` 직후 별도 Event로 직접 전송하며, 목록 클릭 진입과 URL 직접 진입을 모두 포함하고 `product_id` 필수 |
| 합의 | `product_view.navigation_source` | `page_view`와 같은 값을 유지한다. URL 직접 진입은 `session_start`로 기록 |
| 합의/AI 보강 필요 | `product_view` 가중치 | `EVENT_WEIGHT.product_view=1.0`을 유지한다. 상품 벡터에는 `product_view`만 반영해야 하나 현재 `user_vector.py`가 `page_view=1.0`도 함께 누적하므로 AI 집계 수정이 필요하다 |
| 합의 | 가중치 상수 단일 출처 | Event **명세**의 원본은 Data 문서지만, **가중치 상수**의 원본은 `frontend/src/types/log.ts`다. `batch/jobs/behavior_weights.py`가 이 파일을 직접 파싱하므로 문서에 숫자를 복사하지 않는다 |
| 현행 구현 | `close_reason` 값 | `backdrop`, `escape`, `close_button`, `open_detail` 4종 |
| 합의 | `quick_look` 가중치 | 현재 1.5를 유지한다. `added_to_cart`는 별도 Event로 이미 가산되므로 상향 조건으로 쓰지 않고, `variants_viewed`/짧은 체류 기반 조건부 가중치는 실측 후 별도 합의한다 |
| 분석 초안 | Quick Look 존치 판단 | 같은 목록에 노출된 `(session_id, product_id)`를 Quick Look 사용/비사용+클릭으로 나눠 장바구니 전환율, 상세 이동률, 짧은 무상호작용 종료율, 창 안 완결률을 비교한다. 실제 사용자 로그의 기술 통계로 판단한다 |
| 합의 | `product_view` 집계 분모 | 전환율 분모는 `product_view_sessions`(distinct `session_id`+`product_id`). `product_view_count`는 장바구니 왕복 시 재발화한다 |
| 현행 구현 | 시뮬레이터 최신 Event | FE 35종 중 34종 생성. 남은 `dead_click`은 실제 UI 오작동 신호라 정책상 생성하지 않음 |
| 보강 필요 | 시뮬레이터 properties/enum | 10개 Event가 필수 property 또는 enum 계약과 다르다. Collector가 `properties`를 검증하지 않아 수집 단계에서 안 걸린다 |
| 확인 요청 | `view_cart` 뒤로가기 경로 | popstate 경로에도 `item_count`, `distinct_products`, `cart_value`를 동일하게 실어 달라고 FE에 요청 |
| 확인 요청 | breadcrumb 홈 이동 | `product_click(product_id=null)`은 상품 대상 Event 계약에 어긋난다. 상품 클릭 로그에서 제거하거나 navigation Event로 분리 요청 |
| 확인 요청 | `text_snippet` 전송 | 선택 원문이 Raw Kafka payload에 남으므로 FE에서 제거 요청. Raw 저장이 꼭 필요하면 별도 합의 후 계약을 변경한다 |
| 합의 | `section_dwell` 합산 | Front는 여러 건을 보내고 Spark/DW에서 합산 |
| 합의 | Synthetic/Web Event 분리 | 같은 Schema를 사용하고 `actor_type`, `source`, `simulation_run_id`로 구분 |
| 초안 | synthetic 공통 필수 properties | `actor_type='synthetic'`이면 `scenario_id`, `simulation_run_id`, `generator_type` 필수. Web Event에는 미적용 |
| 초안 | `persona_source` 위치 | Event 미포함. `simulation_run_id → dim_simulation_run` Join으로 표본 필터 |
| 합의 | `text_snippet` 저장 | 원문 제거, `text_length`, `matched_ingredients`, `vocab_version` 중심 |
| 합의 | `session_start.page_view_id` | `session_start` 발생 시점에 첫 `page_view_id`를 발급하고 첫 `page_view`와 공유 |
| 초안 | Dashboard 기본 산식 | session/product 기준 우선 |
| 초안 | 집계 기간 | 일간 + 최근 7일 우선 |
| 초안 | DW 집계 방식 | 서로 다른 grain의 Fact는 목표 Mart grain으로 먼저 집계한 뒤 Join |
| 초안 | 상품별 매출 | `items[]` explode 후 상품별 매출은 `item_revenue`, 주문 총액 검증은 `order_value` |
| 구현 후 재검증 | 목록/구매 Trigger | 후속 화면 구현 직후 재검증 |
| 합의 | Kafka 기본값 | topic 기본값은 `activity-events`, message는 Event 1건 단위, key는 `session_id` |
| 합의 | Kafka key 최종 기준 | `persona_id`가 null일 수 있는 Web Event까지 고려해 `session_id`를 partition key 기준으로 사용 |
| 확장 | 관심도 가중치/비정상 행동 | MVP 이후 샘플 데이터와 QA 결과로 조정 |

`SCHEMA_VERSION`은 Data가 계약 문서에서 기준을 정하고 해당 변경 MR 담당자가 문서와 `frontend/src/types/log.ts`를 함께 갱신한다. 이번 `product_view`는 계약 확정 전에 병합된 변경이라 `0.2.0-draft`를 유지한다. 이후에는 payload 변경 없는 설명/오탈자 수정은 patch, Event 또는 optional property 추가는 minor, 필드 삭제·이름/타입 변경·필수 전환·enum 의미 변경처럼 하위 호환되지 않는 변경은 major 후보로 본다.

## 11. 현재 문서와 추후 분리 기준

현재 작성된 Analytics 관련 문서는 6개다.

| 현재 문서 | 목적 |
| --- | --- |
| `event-contract-summary.md` | 팀 공유 및 합의용 요약 |
| `event-taxonomy-trigger-schema.md` | Event Taxonomy, Trigger, Schema 상세 초안 |
| `processed-schema.md` | Raw Event 이후 Spark 처리/Processed Dataset 초안 |
| `dw-schema.md` | Processed Dataset 이후 Dashboard 조회용 DW/Mart 초안 |
| `persona-schema.md` | Persona 원천, seed/holdout, segment, simulation run 규칙 |
| `persona-attribute-preprocessing.md` | 사용자 속성 4종의 정규화·결측 처리·허용값 기준 |

추후 구현이 진행되면 아래 문서를 별도로 분리할 수 있다.

| 추후 문서 | 담을 내용 |
| --- | --- |
| `contracts/event-schema.json` | Backend Collector가 검증할 실제 JSON Schema |
| 물리 DW DDL 문서 | 선택한 저장소 기준 파티션, 인덱스, 타입, DDL |
| Dashboard 산식 문서 | 화면별 KPI, 필터, 집계 기준 |
| Front 구현 문서 | 실제 컴포넌트/훅별 Trigger 위치 |

회의에서는 이 요약 문서로 합의하고, 합의 결과를 상세 문서, Processed Schema 문서, DW Schema 문서, 추후 `contracts/event-schema.json`에 반영한다.
