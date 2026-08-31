# Processed Event Schema

작성일: 2026-08-28  
상태: Draft, E2E 테스트 전 초안. Kafka payload 서버 메타 필드 계약은 BE 커넥터 담당 확인 완료(2026-08-31)
관련 문서: `event-contract-summary.md`, `event-taxonomy-trigger-schema.md`

## 1. 문서 목적

이 문서는 Collector를 거쳐 Kafka에 들어온 Raw Event를 Spark에서 정제, 중복 제거, 세션화, 집계할 때 사용할 Processed Schema 초안이다.

Processed Schema는 DW Schema와 같지 않다. 역할은 Raw Event와 Dashboard/DW 사이의 중간 처리 기준을 정하는 것이다.

```text
Frontend
→ Collector
→ Kafka raw_events
→ Spark Processed Layer
→ DW/Mart Layer
→ Dashboard
```

## 2. 반영된 합의 내용

프론트/백 확인 및 BE 커넥터 담당 확인(2026-08-31) 결과 아래 기준을 반영한다.

| 항목 | 반영 내용 |
| --- | --- |
| Raw 전달 방식 | Front JSON 구조를 유지하고 Backend는 큰 가공 없이 검증과 서버 메타 필드만 추가 |
| 수집 API | `POST /api/events`, body는 `{ schema_version, events: [ ...LogEnvelope ] }` |
| E2E Schema Version | 현재 구현 기준 `0.2.0-draft` 사용. `1.0.0-draft`는 추후 계약 확정 후 전환 |
| batch 크기 | 프론트 기본값 20건 기준, 추후 부하 테스트로 조정 |
| 서버 메타 필드 | Kafka payload에는 `received_at`, `source`, `request_id`, `event_index` 포함. Spark는 수집 시각, 유입 경로, 요청 단위 추적, batch 내 Event 순서 식별 기준으로 사용 |
| 계층별 중복 처리 | Raw는 수신 Event를 그대로 보존하고, Processed `cleaned_events` 생성 단계에서 `event_id` 기준으로 중복 제거 |
| 대표 Event 선정 | 동일 `event_id`는 `received_at ASC`, 동률이면 `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 기준 최초 1건을 정본으로 사용 |
| 검증 실패 Event | 전체 batch 실패보다 실패 Event만 분리 처리 |
| `product_view` | MR !24가 `dev`에 반영됨. 상세 진입 시 `page_view` 직후 별도 Event로 직접 전송하며, 목록 클릭 진입과 URL 직접 진입을 모두 포함하고 `product_id` 필수 |
| `product_view.navigation_source` | `page_view`와 같은 값을 유지. 상품 URL 직접 진입은 `session_start`로 기록 |
| Event 명세 단일 출처 | Data 문서(`event-contract-summary.md`, `event-taxonomy-trigger-schema.md`)를 계약 원본으로 둔다. `frontend/src/types/log.ts`는 구현 미러로 관리한다 |
| `SCHEMA_VERSION` | 현재 E2E는 `0.2.0-draft` 유지. `product_view` 추가는 draft 내 하위 호환 확장으로 보고 이번에는 올리지 않는다 |
| `section_dwell` | Front는 여러 건을 보내고 Spark/DW에서 합산 |
| Synthetic/Web 구분 | 같은 Schema를 쓰고 `actor_type`, `source`, `simulation_run_id`로 구분 |
| 텍스트 선택/복사 | `text_snippet` 제거, `text_length`, `matched_ingredients`, `vocab_version` 중심 |

## 3. 분석 목표에서 역산한 필수 축

Processed Schema는 최종 Dashboard와 실험 분석에 필요한 지표를 만들 수 있어야 한다.

| 분석 목표 | 필요한 Event | Processed에 살아 있어야 하는 필드 |
| --- | --- | --- |
| 상품 CTR | `product_impression`, `product_click` | `event_name`, `event_time`, `product_id`, `category_id`, `brand_id`, `list_id`, `position`, `session_id` |
| 추천 영역 CTR | `recommendation_impression`, `recommendation_click` | `recommendation_id`, `list_id`, `position`, `algorithm`, `product_id`, `session_id`, `event_time`. `section_id`는 있으면 보조 분석에 사용 |
| 검색 → 상품 클릭 전환율 | `search`, `product_click` | `search_id` 또는 session fallback, `search_query`, `result_count`, `product_id`, `position`, `session_id` |
| 상품 조회 → 장바구니 전환율 | `product_view`, `add_to_cart` | `session_id`, `product_id`, `event_time`, `category_id`, `brand_id` |
| 장바구니 → 구매 전환율 | `add_to_cart`, `begin_checkout`, `purchase` | `session_id`, `cart_id` 또는 session fallback, `order_id`, `product_id`, `quantity`, `item_revenue`, `order_value`, `currency` |
| 사용자별 관심 카테고리 | 조회/체류/장바구니/구매 Event | `user_id`, `persona_id`, `category_id`, `event_weight`, `event_time` |
| 상품별 관심도 | 조회/정보 열람/체류/찜/장바구니/구매 Event | `product_id`, `section_id`, `content_kind`, `dwell_ms`, `event_weight` |
| 시나리오별 행동 차이 | 모든 주요 Event | `scenario_id`, `simulation_run_id`, `user_id`, `persona_id`, `actor_type`, `source` |

따라서 Processed 공통 축은 최소한 아래 필드를 보존한다.

```text
user_id
persona_id
event_id
event_name
event_time
received_at
processed_at
product_id
category_id
brand_id
section_id
position
session_id
scenario_id
simulation_run_id
actor_type
source
```

`user_id`는 분석용 사용자 식별자다. Synthetic Event에서는 `persona_id`를 `user_id`로 복사한다. 실제 Web Event는 아직 원천 ID 정책이 없으므로 `user_id`를 nullable로 두고, 로그인 사용자 ID 또는 익명 방문자 ID가 확정되면 채운다.

## 4. 시간 필드 기준

Kafka/Spark 처리에서는 사용자가 실제 행동한 시간과 시스템이 받은/처리한 시간을 분리해야 한다.

| 필드 | 생성 위치 | 의미 | 주요 사용처 |
| --- | --- | --- | --- |
| `event_time` | Front 값 `occurred_at` 정규화 | 사용자가 실제 행동한 시각 | KPI 집계, Funnel 순서, Window 집계 |
| `received_at` | Collector | Backend가 Event를 받은 시각 | 수집 지연, 클라이언트 시계 오류 탐지 |
| `processed_at` | Spark | Spark가 Processed Dataset으로 처리한 시각 | 처리 지연, 모니터링, 재처리 구분 |

예시:

```text
event_time   = 12:00:01
received_at  = 12:00:02
processed_at = 12:00:05
```

기본 집계 기준은 `event_time`이다. `received_at`, `processed_at`은 데이터 품질과 처리 지연을 보기 위한 보조 기준이다.

시간대 기준:

| 항목 | 기준 |
| --- | --- |
| 저장 기준 | 모든 timestamp는 UTC로 저장 |
| Dashboard 일간 기준 | `Asia/Seoul` 기준으로 `event_date_kst`, `event_hour_kst` 파생 |
| `event_hour` 타입 | `timestamp`, hour truncate 값 |
| late event 판정 | Spark watermark 기준. 정확한 허용 지연은 E2E 후 조정 |

## 5. Processed Layer 원칙

| 원칙 | 내용 |
| --- | --- |
| Raw 보존 | 원본 Event는 `raw_events`에 그대로 남긴다 |
| Base Event grain | `cleaned_events`, `sessionized_events`의 논리 단위는 Event 1건이다 |
| Derived grain | `funnel_session_fact`, `content_interest_fact` 등 파생 Dataset은 각 목적에 맞는 grain을 가진다 |
| Kafka message 단위 | 현재 Backend 구현은 Event 1건 단위 발행이다. 후속에 batch message로 바뀌면 Spark 초입에서 Event 단위로 펼친다 |
| 중복 제거 책임 | Backend Collector는 Redis/DB로 중복 차단하지 않아도 된다. Raw는 중복 수신을 허용하고, Processed 단계에서 `event_id` 기준으로 최초 1건만 사용한다 |
| 재시도 전제 | Front가 같은 Event를 재전송할 때는 같은 `event_id`를 유지해야 한다 |
| 순서 복원 | `session_id + sequence_no`, 보조로 `event_time`을 사용한다 |
| 시간 분리 | `event_time`, `received_at`, `processed_at`을 분리 저장한다 |
| 타입 정규화 | Processed부터 timestamp, int, decimal, boolean, array 타입을 강하게 보장한다 |
| Event별 필수값 | Event마다 `NULL`이 정상인지 오류인지 별도 규칙을 둔다 |
| JSON properties | Raw에서는 JSON으로 유지하고, Processed에서 자주 쓰는 필드만 컬럼으로 승격한다 |
| Synthetic 분리 | 모든 집계는 `actor_type`, `source`, `simulation_run_id` 필터가 가능해야 한다 |
| 상품 차원 | `product_id`는 필수 축으로 두고, `category_id`, `brand_id`, `unit_price`는 Fact에 스냅샷으로 승격한다 |
| Mart 입력 규칙 | 서로 다른 grain의 Processed Dataset은 row-level로 직접 Join하지 않고 목표 Mart grain으로 먼저 집계한 뒤 Join한다 |

### 5.1 중복 Event 처리 계약

프론트는 이탈 시점에 `sendBeacon` 또는 keepalive 전송을 사용할 수 있고, 이 방식은 성공 여부를 확실히 알 수 없다. 따라서 유실을 줄이기 위해 같은 batch/Event를 재시도할 수 있으며, 이때 Raw 단계에는 같은 `event_id`가 2건 이상 들어올 수 있다.

중복 처리는 아래 기준으로 확정한다.

| 항목 | 처리 기준 |
| --- | --- |
| Backend Collector | Redis/DB를 붙여 실시간 중복 차단하지 않아도 된다 |
| Kafka/Raw | 같은 `event_id` 중복 수신을 정상 가능성으로 본다 |
| Data/Spark | `cleaned_events` 생성 전 `event_id` 기준으로 deduplication 한다 |
| Dedup 기준 | 같은 `event_id` 중 가장 먼저 수신된 1건을 대표 Event로 사용한다 |
| 대표 Event 선택 정렬 | `received_at ASC`, 동률이면 `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 순으로 정렬한다 |
| Fact/Mart 입력 | `product_event_fact`, `content_interest_fact`, `funnel_session_fact`, DW Mart는 중복 제거 후 Dataset만 입력으로 사용한다 |
| 중복 원본 | `raw_events`에는 보존한다. 필요하면 후속으로 `duplicate_events` 또는 audit view를 만들 수 있다 |
| Front 필수 전제 | 같은 행동을 재전송할 때 `event_id`를 새로 만들면 안 된다 |

`event_id`가 없거나 파싱 불가능한 Event는 deduplication 자체가 불가능하므로 `bad_events.error_code='missing_required_field'` 또는 `invalid_properties`로 격리한다.

현재 Kafka key는 `session_id`이므로, Front가 재시도 시 같은 `event_id`와 `session_id`를 유지하면 동일 Event의 중복본은 보통 같은 partition에 들어간다. 이 구조에서는 `received_at`이 같은 극단적인 경우에도 partition 내부 offset으로 최초 적재 record를 안정적으로 고를 수 있다. 만약 잘못된 key 변경 등으로 중복본이 서로 다른 partition에 들어오면 Kafka offset만으로 전역 시간 순서를 보장할 수 없으므로, `received_at`을 1차 기준으로 유지하고 partition/offset은 결정론적 tie-breaker로만 사용한다.

## 6. 전체 처리 흐름

```text
raw_events
→ bad_events
→ cleaned_events
→ sessionized_events
→ product_event_fact
→ search_event_fact
→ section_dwell_agg
→ content_interest_fact
→ funnel_session_fact
→ persona_behavior_feature_delta
→ DW/Mart
```

상품/카테고리/브랜드 속성은 `dim_product`와 Join할 수 있도록 분리한다.

## 7. Dataset 목록

| dataset | layer | grain | 목적 |
| --- | --- | --- | --- |
| `raw_events` | Raw | received event record | Collector가 검증/보강한 원본 Event. 중복 수신 가능 |
| `bad_events` | Raw/Error | error record 또는 Kafka metadata | Schema 검증 실패 Event 격리 |
| `cleaned_events` | Processed | `event_id` | 유효 Event, 중복 제거, 기본 타입 정리 |
| `sessionized_events` | Processed | `event_id` | 세션 내 순서 복원, late/sequence 품질 표시 |
| `product_event_fact` | Processed/Derived | `event_id + item_index + product_id` | 상품별 Event 분석 기준 |
| `search_event_fact` | Processed/Derived | `event_id` | 검색 Event 자체의 검색어/결과 수 분석 |
| `section_dwell_agg` | Processed/Derived | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 섹션/콘텐츠 체류시간 합산 |
| `content_interest_fact` | Processed/Derived | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 성분/리뷰/콘텐츠 관심도 계산 |
| `funnel_session_fact` | Processed/Derived | `session_id + product_id` | Funnel 단계 도달 여부 |
| `persona_behavior_feature_delta` | Processed/Derived | `event_id + user_id + product_id` | User Behavior Vector/CBF 입력용 delta |
| `dim_product` | Dimension | `product_id` | 상품, 브랜드, 카테고리, 가격, 성분 속성 참조 |

Base Dataset과 Derived Dataset:

| 구분 | Dataset | 의미 |
| --- | --- | --- |
| Base | `raw_events`, `cleaned_events`, `sessionized_events` | 원본 Event를 보존하거나 Event 단위로 정제/정렬한 데이터 |
| Derived | `product_event_fact`, `search_event_fact`, `section_dwell_agg`, `content_interest_fact`, `funnel_session_fact`, `persona_behavior_feature_delta` | KPI와 Feature 생성을 위해 grain을 바꾼 데이터 |
| Dimension | `dim_product` | Event에 반복 저장하지 않는 참조 데이터 |

## 8. 공통 정규화 필드

Processed Dataset에서 반복적으로 사용하는 공통 필드는 아래 기준을 따른다.

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_id` | string | N | Event 고유 ID, dedup 기준 |
| `schema_version` | string | N | Event Schema 버전 |
| `event_name` | string | N | Event 이름 |
| `intent` | string | N | Event 의미 |
| `event_time` | timestamp | N | `occurred_at`을 정규화한 행동 발생 시각 |
| `received_at` | timestamp | N | Collector 수신 시각 |
| `processed_at` | timestamp | N | Spark 처리 시각 |
| `request_id` | string/null | Y | batch 요청 ID. 현재 Backend Kafka payload 포함. 과거 Raw/누락 Event는 NULL 가능 |
| `event_index` | int/null | Y | batch 안 Event 순서. 현재 Backend Kafka payload 포함. 과거 Raw/누락 Event는 NULL 가능 |
| `source` | string | N | Kafka payload 값을 우선 사용. 누락 시 `actor_type`, `environment`, ingest 경로로 fallback 파생 |
| `actor_type` | string | N | `user`, `synthetic` |
| `is_synthetic` | boolean | N | `actor_type='synthetic'` 또는 `source='simulator'` |
| `user_id` | string/null | Y | 분석용 사용자 ID. synthetic이면 `persona_id`와 동일, 실제 Web은 ID 정책 확정 전까지 NULL 가능 |
| `persona_id` | string/null | Y | Persona ID. 실제 사용자 Event에서는 NULL 가능 |
| `session_id` | string | N | 쇼핑 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID. `session_start`와 첫 `page_view`는 같은 값을 공유 |
| `sequence_no` | int | N | 세션 내 Event 순서 |
| `page_type` | string | N | 화면 유형 |
| `scenario_id` | string/null | Y | 시나리오 ID. 시뮬레이션 분석에서는 필수 |
| `simulation_run_id` | string/null | Y | 시뮬레이션 실행 ID. synthetic에서는 필수 |
| `generator_type` | string/null | Y | synthetic 생성 방식. 예: `python_batch`, `agent_llm` |
| `environment` | string | N | `local`, `dev`, `loadtest` 등 |
| `product_id` | string/null | Y | 상품 대상 Event에서 필수 |
| `category_id` | string/null | Y | 상품 카테고리. 상품 대상 Event에서는 권장 |
| `brand_id` | string/null | Y | 브랜드. 상품 대상 Event에서는 권장 |
| `section_id` | string/null | Y | 화면 섹션 |
| `content_kind` | string/null | Y | 콘텐츠 종류 |
| `position` | int/null | Y | 목록/추천/검색 결과 내 노출 위치 |
| `properties_json` | string | Y | 원본 Event별 properties JSON 문자열 |
| `quality_flags` | array<string> | Y | `duplicate`, `late_event`, `sequence_gap` 등 |

### 8.1 Raw → Processed 컬럼 승격 규칙

Raw Event는 공통 Envelope와 Event별 `properties`로 들어온다. Processed에서는 KPI에 자주 쓰는 값을 컬럼으로 승격한다.

| Processed column | Raw source | 비고 |
| --- | --- | --- |
| `event_time` | `occurred_at` | timestamp 정규화 |
| `request_id` | Backend payload | Kafka payload에 포함. 과거 Raw/누락 Event는 NULL 가능 |
| `event_index` | Backend payload | Kafka payload에 포함. batch 안 Event 순서 |
| `source` | Backend payload 또는 fallback 파생 | Kafka payload 값을 우선 사용. 누락 시 현재 Collector 기준과 맞춰 `actor_type='synthetic' → simulator`, 그 외 → `web`으로 fallback 파생한다. 서버 생성 Event는 후속 도입 시 schema version을 올려 확장한다 |
| `scenario_id`, `simulation_run_id` | `properties.scenario_id`, `properties.simulation_run_id` | E2E 기준 Raw 물리 위치는 `properties` 내부이고, Processed에서 컬럼으로 승격한다. `actor_type='synthetic'`이면 필수 |
| `generator_type` | `properties.generator_type` | `actor_type='synthetic'`이면 필수 승격 대상이다. 100명 agent와 9,900명 Python batch의 생성 방식 구분은 `source`가 아니라 이 필드로 한다. Producer가 값을 보내지 않으면 `simulation_run_id`로 run 메타데이터를 Join해 보정하고, 그것도 없으면 NULL로 두고 품질 flag를 남긴다 |
| `persona_source` | Raw에 없음. `persona_id → persona_profile` 또는 `simulation_run_id → dim_simulation_run` Join | Persona 정적 속성이므로 Event에 반복 저장하지 않는다. Processed Fact에도 승격하지 않고 DW Dimension Join으로 해석한다 |
| `user_id` | `persona_id` 또는 추후 실제 사용자 ID | synthetic은 `persona_id`, 실제 Web은 ID 정책 확정 전까지 NULL 가능 |
| `product_id` | top-level `product_id` | 상품 대상 Event의 공통 대상 ID. 보고 있는 상품이 아니라 Event 대상 상품 |
| `context_product_id` | `properties.context_product_id` | 대상 상품과 이벤트 발생 배경 상품이 다를 때의 배경 상품 ID |
| `section_id` | `properties.section_id` | 없으면 `content_kind`로 보조 해석 가능 |
| `content_kind` | `properties.content_kind` | section 기반 Event에서 사용 |
| `content_ref` | `properties.content_ref` | 리뷰 ID, 추천 상품 ID 등 |
| `navigation_source` | `properties.navigation_source` | 세션 첫 `page_view`는 `session_start` 값으로 구분 |
| `position` | `properties.position` | 목록/추천/검색 결과 위치 |
| `entry_source` | `properties.entry_source` | 목록, 추천, quick look, 장바구니 등 진입/행동 경로 |
| `list_id` | `properties.list_id` | 상품 목록/추천/검색 결과 영역 |
| `recommendation_id` | `properties.recommendation_id` | 추천 영역 식별자 |
| `algorithm` | `properties.algorithm` | 추천 알고리즘/룰 식별자 |
| `sku_id` | `properties.sku_id` | 옵션/상품 단위 세부 ID |
| `quantity` | `properties.quantity` | int 정규화 |
| `unit_price` | `properties.unit_price` 또는 `properties.price_usd` | decimal 정규화 |
| `order_value` | `properties.order_value` 또는 `sum(items.quantity * items.unit_price)` | purchase에서 없으면 items로 파생 가능 |
| `item_revenue` | `items[].quantity * items[].unit_price` 또는 `quantity * unit_price` | `items[]` explode 이후 상품별 매출 합산 기준 |
| `currency` | `properties.currency` | 없으면 주문 금액 확정 KPI에서는 제외 |
| `cart_id` | `properties.cart_id` | Raw에 없으면 NULL. 구현 전 필수 아님 |
| `cart_value` | `properties.cart_value` | 장바구니/Checkout 금액. decimal 정규화 |
| `item_count` | `properties.item_count` | 장바구니 전체 item 수. int 정규화 |
| `distinct_products` | `properties.distinct_products` | 장바구니 내 서로 다른 상품 수. int 정규화 |
| `cart_size_after` | `properties.cart_size_after` | 장바구니 제거 후 item 또는 상품 수. int 정규화 |
| `order_id` | `properties.order_id` | purchase에서는 필수 |
| `search_id` | `properties.search_id` 또는 Spark 파생 | 검색 구현 전에는 NULL/provisional |
| `search_query` | `properties.query_text` | Raw 검색어를 Processed에서 `search_query`로 정규화. 저장 정책에 따라 hash만 보관 가능 |
| `result_count` | `properties.result_count` | int 정규화 |
| `filter_kind` | `properties.filter_kind` | 현재 FE 구현 기준 필터 축. 예: `category`, `concern`, `price` |
| `filter_value` | `properties.filter_value` | 현재 FE 구현 기준 필터 값. 예: `all`, category name, price band |
| `filter_action` | `properties.filter_action` | 후속 확장. 적용/해제/초기화 구분이 필요할 때 사용 |
| `filter_values` | `properties.filter_values` | 후속 확장. 복수 선택 필터는 array<string>으로 정규화 |
| `review_filter` | `properties.filter` | `review_filter_apply`에서 사용 |
| `review_sort` | `properties.sort` | `review_filter_apply`에서 사용 |
| `sort_key` | `properties.sort_key` 또는 `properties.sort` | sort Event에서 사용 |
| `sort_direction` | `properties.sort_direction` | `sort_change`에서 사용. 예: `asc`, `desc` |
| `category_id` | `dim_product.product_id` Join | 상품 속성 보강 |
| `brand_id` | `dim_product.product_id` Join | 상품 속성 보강 |
| `matched_ingredients` | `properties.matched_ingredients` | array<string> |
| `matched_keywords` | `properties.matched_keywords` | array<string> |
| `vocab_version` | `properties.vocab_version` | 텍스트/성분 매칭 기준 버전 |
| `variants_viewed` | `properties.variants_viewed` | quick look 창 안에서 옵션을 본 횟수 또는 목록 |
| `added_to_cart` | `properties.added_to_cart` | quick look 창 안에서 장바구니 담기가 발생했는지 |
| `wishlisted` | `properties.wishlisted` | quick look 창 안에서 찜이 발생했는지 |

### 8.2 `source` 파생 규칙

현재 Raw payload에는 Collector가 `source`를 포함한다. Processed는 payload 값을 우선 사용하고, 과거 Raw나 누락 Event를 처리할 때만 아래 규칙으로 fallback 파생한다.

| 조건 | source |
| --- | --- |
| Backend 또는 Batch가 서버 내부 Event를 생성 | `server` |
| `actor_type='synthetic'` | `simulator` |
| 그 외 | `web` |

100명 agent 기반 생성과 9,900명 Python batch 생성은 `source`로 나누지 않는다. 생성 방식은 `properties.generator_type`, Persona 표본 구분은 `simulation_run_id → dim_simulation_run.persona_source`를 기준으로 한다.

### 8.3 synthetic Event 검증 규칙

`actor_type='synthetic'`인 Event는 실행 단위 메타데이터가 있어야 Dimension Join과 표본 필터가 성립한다. Collector는 누락을 Kafka 전송 전에 거절하고, Spark는 방어적으로 같은 검증을 유지한다.

| 조건 | 처리 | error_code |
| --- | --- | --- |
| `actor_type='synthetic'`이고 `properties.scenario_id`, `properties.simulation_run_id`, `properties.generator_type` 중 하나라도 누락 | `bad_events`로 격리 | `invalid_properties` |
| `actor_type='user'`인데 위 값이 들어옴 | 승격하지 않고 무시. 품질 flag만 남김 | 없음 |
| `actor_type='synthetic'`이고 `persona_id`가 NULL | `bad_events`로 격리. synthetic Event는 Persona 기반이므로 `persona_id`가 반드시 있다 | `missing_required_field` |

`error_stage`는 `spark_semantic_validation`이다. 이 규칙은 실제 Web Event에는 적용하지 않으므로 프론트 구현에 영향을 주지 않는다.

## 9. `raw_events`

Collector가 Front Event를 검증하고 서버 메타 필드를 추가한 원본이다. Raw는 분석 편의보다 원본 보존이 우선이다.

Raw는 중복 제거 전 데이터이므로 같은 `event_id`가 재전송으로 여러 번 들어올 수 있다.

```text
grain = received event record
unique key 후보 = kafka_topic + kafka_partition + kafka_offset
event_id = business dedup key
```

현재 Backend는 batch 요청을 받더라도 Event를 Kafka에 한 건씩 발행한다. Kafka key는 `session_id`를 사용하며, `request_id`, `event_index`, `source`는 Kafka payload에 포함된다. Raw record의 물리 식별은 Kafka metadata를 우선 사용한다.

| column | type | 설명 |
| --- | --- | --- |
| `kafka_topic` | string/null | Kafka topic. Raw 저장 시 metadata로 보강 |
| `kafka_partition` | int/null | Kafka partition. Raw 저장 시 metadata로 보강 |
| `kafka_offset` | bigint/null | Kafka offset. Raw 저장 시 metadata로 보강 |
| `request_id` | string/null | batch 요청 ID. Kafka payload 포함 |
| `event_index` | int/null | batch 안 Event 순서. Kafka payload 포함 |
| `schema_version` | string | Event Schema 버전 |
| `event_id` | string | Event 고유 ID |
| `event_name` | string | Event 이름 |
| `intent` | string | Event 의미 |
| `occurred_at` | timestamp/string | 클라이언트 행동 발생 시각 원본 |
| `received_at` | timestamp | Collector 수신 시각 |
| `source` | string/null | `web`, `simulator`. 현재 Kafka payload 포함, 누락 시 Processed에서 fallback 파생 |
| `persona_id` | string/null | Persona ID |
| `session_id` | string | 쇼핑 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `sequence_no` | int/string | 세션 내 Event 순서 원본 |
| `page_type` | string | MVP 기준 `product_detail`, `product_list`, `cart` |
| `product_id` | string/null | 상품 대상 Event의 상품 ID |
| `actor_type` | string | `user`, `synthetic` |
| `environment` | string | `local`, `dev`, `loadtest` 등 |
| `scenario_id` | string/null | 시나리오 ID. E2E 기준 Raw 물리 위치는 `properties.scenario_id` |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID. E2E 기준 Raw 물리 위치는 `properties.simulation_run_id` |
| `generator_type` | string/null | synthetic 생성 방식. 있으면 `properties.generator_type`에서 승격 |
| `properties` | json | Event별 원본 properties |

## 10. `bad_events`

검증 실패 Event를 버리지 않고 격리한다. 전체 batch를 실패시키기보다 실패 Event만 분리하는 방향을 기준으로 한다.

| column | type | 설명 |
| --- | --- | --- |
| `request_id` | string/null | batch 요청 ID. Kafka payload 포함 |
| `event_index` | int/null | batch 안 Event 순서. Kafka payload 포함 |
| `kafka_topic` | string/null | Kafka topic. Spark에서 판정한 bad event면 metadata 보강 가능 |
| `kafka_partition` | int/null | Kafka partition |
| `kafka_offset` | bigint/null | Kafka offset |
| `event_id` | string/null | 파싱 가능한 경우 저장 |
| `received_at` | timestamp | 서버 수신 시각 |
| `processed_at` | timestamp | 오류 판정 시각 |
| `raw_payload_json` | string | 실패 원본 JSON 문자열 |
| `error_code` | string | 실패 유형 |
| `error_message` | string | 실패 사유 |
| `schema_version` | string/null | 파싱 가능한 경우 저장 |
| `error_stage` | string | `collector_validation`, `spark_type_normalization`, `spark_semantic_validation` |

주요 `error_code`:

| error_code | 설명 |
| --- | --- |
| `missing_required_field` | 필수 공통 필드 누락 |
| `unknown_event_name` | Taxonomy에 없는 Event |
| `invalid_timestamp` | timestamp 파싱 실패 |
| `invalid_type` | Spark 타입 정규화 실패 |
| `invalid_properties` | Event별 필수 properties 누락 |
| `unsupported_schema_version` | 지원하지 않는 Schema 버전 |

오류 발생 위치:

| error_stage | 의미 |
| --- | --- |
| `collector_validation` | Collector가 Kafka 전송 전에 발견한 기본 Schema 오류 |
| `spark_type_normalization` | Spark가 타입 변환 중 발견한 오류 |
| `spark_semantic_validation` | Spark가 Event별 필수값/의미 규칙 검사 중 발견한 오류 |

## 11. `cleaned_events`

Raw Event 중 유효한 Event만 남긴 기본 정제 테이블이다.

| column | type | 설명 |
| --- | --- | --- |
| `event_id` | string | PK |
| `schema_version` | string | Event Schema 버전 |
| `event_name` | string | Event 이름 |
| `intent` | string | Event 의미 |
| `event_time` | timestamp | `occurred_at` 정규화 값 |
| `received_at` | timestamp | 수신 시각 |
| `processed_at` | timestamp | Spark 처리 시각 |
| `latency_ms` | bigint | `received_at - event_time` |
| `processing_lag_ms` | bigint | `processed_at - received_at` |
| `request_id` | string/null | batch 요청 ID. Kafka payload 포함 |
| `event_index` | int/null | batch 안 Event 순서. Kafka payload 포함 |
| `source` | string | 유입 경로. Kafka payload 값을 우선 사용하고, 누락 시 `actor_type`, `environment`, ingest 경로로 fallback 파생 |
| `actor_type` | string | `user`, `synthetic` |
| `is_synthetic` | boolean | `actor_type='synthetic'` 또는 `source='simulator'` |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `sequence_no` | int | 세션 내 순서 |
| `page_type` | string | 화면 유형 |
| `product_id` | string/null | 상품 ID |
| `category_id` | string/null | 상품 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `section_id` | string/null | 섹션 ID |
| `content_kind` | string/null | 콘텐츠 종류 |
| `position` | int/null | 노출/클릭 위치 |
| `properties_json` | string | 원본 properties JSON 문자열 |
| `quality_flags` | array<string> | `duplicate`, `late_event` 등 |

생성 규칙:

| 처리 | 기준 |
| --- | --- |
| 중복 제거 | 같은 `event_id`는 `received_at ASC`, `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 기준 최초 1건만 사용. 중복 원본은 `raw_events`에만 남고, downstream Fact/Mart에는 전달하지 않음 |
| 타입 정리 | timestamp, int, decimal, boolean 파싱 |
| 사용자 ID 생성 | synthetic이면 `user_id=persona_id`, 실제 Web은 로그인/익명 ID 정책 확정 전까지 NULL 허용 |
| 지연 계산 | `latency_ms = received_at - event_time` |
| 처리 지연 계산 | `processing_lag_ms = processed_at - received_at` |
| synthetic 표시 | `actor_type/source/simulation_run_id` 기준 |
| 상품 속성 보강 | `product_id` 기준 `dim_product` Join 또는 Event snapshot에서 `category_id`, `brand_id`, `unit_price` 승격 |
| 구현 전 Event 처리 | `search`, `begin_checkout`, `purchase`는 후속 화면 구현 전까지 provisional로 두고 semantic validation을 느슨하게 적용 |

## 12. `sessionized_events`

세션 내 행동 순서를 복원한 테이블이다. Funnel과 이탈 분석의 기반이다.

| column | type | 설명 |
| --- | --- | --- |
| `event_id` | string | Event ID |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `product_id` | string/null | 상품 ID |
| `context_product_id` | string/null | 이벤트 발생 배경 상품 ID. 대상 상품과 같거나 없으면 NULL |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `event_name` | string | Event 이름 |
| `event_time` | timestamp | 발생 시각 |
| `received_at` | timestamp | 수신 시각 |
| `processed_at` | timestamp | 처리 시각 |
| `sequence_no` | int | 프론트 발생 순서 |
| `event_order` | int | Spark가 복원한 세션 내 순서 |
| `prev_event_name` | string/null | 이전 Event |
| `next_event_name` | string/null | 다음 Event |
| `is_late_event` | boolean | watermark 기준 late 여부 |
| `has_sequence_gap` | boolean | sequence_no 누락 가능성 |

정렬 기준:

```text
session_id
→ sequence_no
→ event_time
→ received_at
```

## 13. `product_event_fact`

상품과 직접 연결되는 Event를 상품 단위로 분석하기 위한 fact다.

| column | type | 설명 |
| --- | --- | --- |
| `event_id` | string | Event ID |
| `event_date` | date | `event_time` 기준 발생일 |
| `event_hour` | timestamp | `event_time`을 UTC 기준 hour truncate한 값 |
| `event_date_kst` | date | `Asia/Seoul` 기준 발생일 |
| `event_hour_kst` | timestamp | `Asia/Seoul` 기준 hour truncate 값 |
| `event_time` | timestamp | 행동 발생 시각 |
| `processed_at` | timestamp | 처리 시각 |
| `event_name` | string | Event 이름 |
| `intent` | string | Event 의미 |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `item_index` | int | `items[]` explode 시 item 순서. 단일 상품 Event는 0 |
| `product_id` | string | 상품 ID |
| `context_product_id` | string/null | 이벤트 발생 배경 상품 ID. 추천 클릭 등에서 사용 |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `sku_id` | string/null | `properties.sku_id` |
| `list_id` | string/null | 목록/추천/검색 결과 영역 ID |
| `entry_source` | string/null | 상품 진입 또는 장바구니 행동 경로 |
| `recommendation_id` | string/null | 추천 영역/실험 식별자 |
| `algorithm` | string/null | 추천 알고리즘/룰 식별자 |
| `search_id` | string/null | 검색 결과 클릭과 검색 Event 연결용 |
| `section_id` | string/null | 섹션 ID |
| `position` | int/null | 노출/클릭 위치 |
| `quantity` | int/null | 수량 |
| `purchase_quantity` | int/null | 구매/Checkout item 수량. `purchase` 상품별 수량 집계용 |
| `cart_size_after` | int/null | 장바구니 제거 후 크기. `remove_from_cart`에서 사용 |
| `unit_price` | decimal(18,2)/null | 단가 |
| `order_value` | decimal(18,2)/null | 주문 전체 금액. 상품별 매출 합산에는 직접 사용하지 않음 |
| `item_revenue` | decimal(18,2)/null | 상품 row 기준 매출. `quantity * unit_price` |
| `cart_value` | decimal(18,2)/null | 장바구니 금액 |
| `currency` | string/null | 통화 |
| `cart_id` | string/null | 장바구니 ID |
| `order_id` | string/null | 주문 ID |
| `variants_viewed` | int/null | quick look 창 안에서 옵션을 본 횟수. 배열로 오면 집계 수로 정규화 |
| `added_to_cart` | boolean/null | quick look 창 안에서 장바구니 담기가 발생했는지 |
| `wishlisted` | boolean/null | quick look 창 안에서 찜이 발생했는지 |
| `actor_type` | string | user/synthetic |
| `source` | string | 유입 경로 |

grain:

```text
event_id + item_index + product_id
```

`product_view`, `product_click`, `add_to_cart`처럼 단일 상품 Event는 `item_index=0`으로 둔다. `begin_checkout`, `purchase`처럼 `items[]`를 가진 Event는 Spark에서 `items explode`를 수행해 상품별 row를 만든다.

예시:

```text
purchase event 1건
items[0], items[1], items[2]
→ product_event_fact 3 rows
```

`order_value`는 주문 전체 금액이므로 `items[]` explode 후 상품 row마다 그대로 합산하면 매출이 과대계산된다. 상품별 매출은 `item_revenue = quantity * unit_price`를 사용하고, `order_value`는 주문 총액 검증/참고값으로만 사용한다.

DW의 매출 KPI는 `event_name='purchase'`인 row의 `item_revenue`만 합산한다. `add_to_cart`나 `begin_checkout`에도 수량과 가격이 있을 수 있지만, 해당 단계의 `item_revenue`는 잠재 금액 또는 검증용으로만 본다.

대상 Event:

```text
product_view
product_impression
product_click
recommendation_impression
recommendation_click
wishlist_toggle
add_to_cart
remove_from_cart
quick_look
quick_look_close
begin_checkout
purchase
media_view
variant_select
quantity_change
```

`view_cart`는 장바구니 화면 진입 Event이지만 `product_id/items`가 없는 cart-level Event이므로 `product_event_fact` 대상에서 제외한다. 장바구니 열람 수는 `cleaned_events` 또는 별도 cart-level Mart에서 집계한다.

## 14. `search_event_fact`

검색 Event 자체의 검색어와 결과 수를 분석하기 위한 fact다. 검색 후 상품 클릭은 이 fact에 직접 저장하지 않고, `product_event_fact.search_id` 또는 같은 세션의 최근 검색 fallback으로 연결한다.

| column | type | 설명 |
| --- | --- | --- |
| `event_id` | string | Event ID |
| `event_date_kst` | date | KST 기준 집계일 |
| `search_id` | string/null | 검색 1회를 식별하는 ID. 검색 구현 전에는 NULL/provisional |
| `event_time` | timestamp | 검색 발생 시각 |
| `processed_at` | timestamp | 처리 시각 |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `search_query` | string/null | Raw `properties.query_text`를 정규화한 검색어. 개인정보/원문 저장 정책에 따라 hash로 대체 가능 |
| `search_query_hash` | string/null | 검색어 해시 |
| `result_count` | int/null | 검색 결과 수 |
| `actor_type` | string | user/synthetic |
| `source` | string | 유입 경로 |

검색 → 상품 클릭 전환율은 같은 `session_id + search_id` 안에서 `search` 이후 `product_event_fact.event_name='product_click'`이 발생했는지로 계산한다. 검색 구현 전 또는 `search_id`가 없는 로그는 같은 `session_id`에서 가장 최근 `search` 이후 발생한 `product_click`으로 임시 연결하고, E2E 후 `search_id` 필수 여부를 재검토한다.

`search_query_hash`는 검색 구현 전까지 provisional이다. 구현 시에는 `normalized_query`가 있으면 이를 기준으로, 없으면 trim/lowercase 등 최소 정규화한 `search_query`를 기준으로 hash를 생성한다.

## 15. `section_dwell_agg`

프론트에서 여러 건 발생하는 `section_dwell`을 합산한 테이블이다.

Raw `section_dwell.dwell_ms`는 누적 체류시간이 아니라 각 Event가 나타내는 구간 체류시간(delta)이다. 따라서 Processed에서는 같은 grain의 delta를 더해 `dwell_ms_sum`을 만든다.

집계 grain:

```text
session_id + page_view_id + product_id + section_id + content_kind + content_ref
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | KST 기준 집계일 |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `product_id` | string/null | 상품 ID |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `section_id` | string/null | 섹션 ID |
| `content_kind` | string/null | 콘텐츠 종류 |
| `content_ref` | string/null | 리뷰 ID, 추천 상품 ID 등 |
| `dwell_ms_sum` | bigint | 체류시간 합 |
| `dwell_event_count` | int | 합산된 dwell Event 수 |
| `max_co_visible_blocks` | int/null | 함께 보인 콘텐츠 블록 최대 수 |
| `first_seen_at` | timestamp | 최초 dwell 발생 시각 |
| `last_seen_at` | timestamp | 마지막 dwell 발생 시각 |
| `processed_at` | timestamp | 집계 처리 시각 |
| `actor_type` | string | user/synthetic |
| `source` | string | 유입 경로 |

주의:

- 최대값이 아니라 합계를 사용한다.
- 700ms 미만 체류는 프론트에서 이미 제외된다.
- 같은 세션에서 상품 A → B → A로 이동할 수 있으므로 `page_view_id`를 반드시 포함한다.

## 16. `content_interest_fact`

성분/리뷰/이미지/CTA 등 콘텐츠 관심도를 계산하기 위한 fact다.

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | KST 기준 집계일 |
| `session_id` | string | 세션 ID |
| `page_view_id` | string | 페이지 방문 ID |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `product_id` | string/null | 상품 ID |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `section_id` | string/null | 섹션 ID |
| `content_kind` | string/null | 콘텐츠 종류 |
| `content_ref` | string/null | 리뷰/추천/성분 참조 ID |
| `view_count` | int | `section_view` 수 |
| `dwell_ms_sum` | bigint | 합산 체류시간 |
| `accordion_expand_count` | int | 펼침 횟수 |
| `review_filter_count` | int | 리뷰 필터 사용 횟수 |
| `text_select_count` | int | 텍스트 선택 횟수 |
| `text_copy_count` | int | 텍스트 복사 횟수 |
| `matched_ingredients` | array<string> | 매칭 성분명 |
| `matched_keywords` | array<string> | 매칭 키워드 |
| `vocab_version` | string/null | 매칭 어휘집 버전 |
| `content_interest_score` | double | 콘텐츠 관심도 초안 점수 |
| `processed_at` | timestamp | 처리 시각 |
| `actor_type` | string | user/synthetic |
| `source` | string | 유입 경로 |

주요 파생 조건:

| 파생 지표 | 조건 |
| --- | --- |
| 성분 관심 | `section_id='ingredients'` 또는 `content_kind in ('ingredient_list', 'ingredient_callout')` |
| 리뷰 관심 | `section_id='reviews'` 또는 `content_kind in ('user_review', 'review_stats', 'review_filter')` |
| 정보 확인 | `accordion_toggle(action='expand')`, `review_filter_apply`, `review_expand`, `text_selection`, `text_copy` |

## 17. `funnel_session_fact`

동일 `session_id + product_id` 기준으로 Funnel 단계 도달 여부를 저장한다.

| column | type | 설명 |
| --- | --- | --- |
| `funnel_date_kst` | date | Funnel 일간 귀속일. 최초 non-null Funnel 단계 시각의 KST 날짜 |
| `session_id` | string | 세션 ID |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `actor_type` | string | user/synthetic |
| `source` | string | 유입 경로 |
| `first_impression_at` | timestamp/null | 최초 상품 노출 |
| `first_quick_look_at` | timestamp/null | 최초 Quick Look 열림. Funnel 단계가 아닌 비교 분기 |
| `first_click_at` | timestamp/null | 최초 상품 클릭 |
| `first_product_view_at` | timestamp/null | 최초 상세 조회 |
| `first_information_view_at` | timestamp/null | 최초 정보 확인 |
| `first_add_to_cart_at` | timestamp/null | 최초 장바구니 |
| `first_checkout_at` | timestamp/null | 최초 Checkout |
| `first_purchase_at` | timestamp/null | 최초 구매 |
| `reached_impression` | boolean | 노출 도달 |
| `used_quick_look` | boolean | 같은 session/product에서 Quick Look 사용 여부 |
| `quick_look_close_reason` | string/null | 마지막 닫힘 사유. `backdrop`/`escape`/`close_button`/`open_detail` |
| `quick_look_dwell_ms` | bigint/null | 같은 session/product의 Quick Look 체류시간 합계 |
| `quick_look_variants_viewed` | integer/null | 선택한 서로 다른 SKU 수의 최댓값. 기본 SKU는 제외 |
| `reached_click` | boolean | 클릭 도달 |
| `reached_product_view` | boolean | 상세 조회 도달 |
| `reached_information_view` | boolean | 정보 확인 도달 |
| `reached_add_to_cart` | boolean | 장바구니 도달 |
| `reached_checkout` | boolean | Checkout 도달 |
| `reached_purchase` | boolean | 구매 도달 |
| `dropoff_step` | string/null | 마지막 도달 후 이탈 단계 |
| `processed_at` | timestamp | 처리 시각 |

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

`information_view` 파생 조건:

```text
section_view where section_id in ('ingredients', 'reviews')
or section_view where content_kind in ('ingredient_list', 'ingredient_callout', 'user_review', 'review_stats', 'review_filter')
or accordion_toggle action='expand'
or review_filter_apply
or review_expand
or text_selection/text_copy with matched_ingredients or matched_keywords
```

`funnel_date_kst`는 아래 순서로 최초 non-null timestamp를 찾아 `Asia/Seoul` 날짜로 변환한다.

```text
first_impression_at
→ first_click_at
→ first_product_view_at
→ first_information_view_at
→ first_add_to_cart_at
→ first_checkout_at
→ first_purchase_at
```

이 기준은 Funnel 전체를 최초 진입일에 귀속한다. 구매 발생일 기준 매출 분석이 필요하면 `product_event_fact.event_date_kst` 기반 Mart를 별도로 사용한다.

### 17.1 Quick Look 비교 분기

Quick Look은 Funnel 단계에 넣지 않고 `product_impression`에서 갈라지는 비교 분기로 다룬다.

```text
대상 = reached_impression=true 인 (session_id, product_id)
arm_quick_look = used_quick_look=true
arm_direct = used_quick_look=false AND reached_click=true
전환 = reached_add_to_cart=true
```

`quick_look`과 `quick_look_close`는 `session_id + product_id`와 발생 순서로 연결한다. 닫힘 Event가 없으면 닫힘 관련 필드는 null로 남기며 임의로 보정하지 않는다. 분석 결과는 선택 편향이 있는 기술 통계로 보고, 실제 기능 존치 판단에는 `actor_type='user'`만 사용한다.

## 18. `persona_behavior_feature_delta`

Event를 User Behavior Vector 또는 Persona 행동 Feature로 업데이트하기 위한 입력 delta다. Product Vector 생성 자체는 AI/Product Feature 담당 범위이며, 이 테이블은 Event와 Product Vector를 연결하기 위한 행동 가중치만 만든다.

| column | type | 설명 |
| --- | --- | --- |
| `event_id` | string | Event ID |
| `event_date_kst` | date | KST 기준 집계일 |
| `user_id` | string/null | 분석용 사용자 ID |
| `persona_id` | string/null | Persona ID |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 시뮬레이션 실행 ID |
| `generator_type` | string/null | synthetic 생성 방식 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | 카테고리 ID |
| `brand_id` | string/null | 브랜드 ID |
| `event_name` | string | Event 이름 |
| `event_time` | timestamp | 발생 시각 |
| `processed_at` | timestamp | 처리 시각 |
| `event_weight` | double | 행동 가중치 |
| `decay_weight` | double | 시간 감쇠 |
| `final_weight` | double | `event_weight * decay_weight` |
| `actor_type` | string | user/synthetic |
| `source` | string | web/simulator/server |

초기 Event Weight `[추정]`의 실행 원본은 `frontend/src/types/log.ts`다. 상품 상세 조회 기준은 `product_view=1.0`이며 상품 관심도/추천 feature에는 `product_view`만 반영해야 한다. 현재 `batch/jobs/user_vector.py`는 `page_view=1.0`도 함께 누적하므로 이중 가산 방지 수정 전까지 계약 미준수 상태다.

| 조건 | event_weight |
| --- | ---: |
| `add_to_cart` | 4.0 |
| `wishlist_toggle(action='add')` | 3.0 |
| `quantity_change`, `variant_select` | 2.0 |
| `recommendation_click`, `media_view`, `review_expand`, `accordion_toggle`, `ingredient_view_mode_change` | 1.5 |
| `product_view`, `product_click`, `review_filter_apply`, `filter_change`, `text_copy`, `view_cart` | 1.0 |
| `section_dwell` | 1.0 x section 계수 |
| `sort_change`, `text_selection` | 0.5 |
| `scroll_pause`, `hover_dwell`, `section_view` | 0.3 |
| `product_impression`, `recommendation_impression`, `impression_dwell`, `recommendation_snapshot`, `scroll_depth`, `quick_look_close`, `session_start`, `exit_summary` | 0 |
| `remove_from_cart` | -2.0 |
| `rage_click` | -2.0 |
| `dead_click` | -1.5 |
| `scroll_backtrack` | -1.0 |

주의:

- 이 가중치는 외부 플랫폼 공식값이 아니라 프로젝트용 초기값이다. 실행 상수의 원본은 `frontend/src/types/log.ts`의 `EVENT_WEIGHT`, `SECTION_DWELL_WEIGHT`, `scrollDepthWeight()`이며 Data 문서는 의미와 근거를 관리한다.
- 추천 품질 검증은 synthetic 행동 로그가 아니라 실제 리뷰 데이터 holdout 기준으로 해야 한다. holdout 판정 순서와 누수 방지 규칙은 `persona-schema.md` §6.1, §5.2를 따른다.
- `product_id`가 필수이므로, 상품과 연결되지 않는 friction Event(`rage_click`, `dead_click` 등)는 이 Dataset에 들어오지 않는다. 해당 Event는 UX/Dashboard 지표로만 사용한다.
- User Behavior Vector는 row의 부호만으로 축을 정하지 않는다. 상품별 가중치를 모은 뒤 전환 상품의 양수 가중치만 positive 축으로 보내고, 미전환 접촉 상품의 양수 가중치와 모든 감점 가중치는 negative 축으로 보낸다. 감점 가중치는 절대값으로 누적하고 최종 추천 점수에서 한 번만 적용한다. canonical 집계 공식은 `contracts/recommendation-io-spec.md` §2를 따르며 `persona-schema.md` §12.1은 그 계약을 참조한다.
- Product Vector는 `contracts/product-feature-spec.md`, 추천 입출력은 `contracts/recommendation-io-spec.md`를 따른다.

## 19. `dim_product`

상품 속성은 Event마다 모두 반복 저장하지 않고 Dimension으로 분리한다. 다만 Dashboard 성능과 시점 보존을 위해 Processed Fact에는 `product_id`, `category_id`, `brand_id`, `unit_price` 정도를 스냅샷 컬럼으로도 둔다.

| column | type | 설명 |
| --- | --- | --- |
| `product_id` | string | 상품 ID |
| `product_name` | string | 상품명 |
| `brand_id` | string | 브랜드 ID |
| `brand_name` | string | 브랜드명 |
| `category_id` | string | 카테고리 ID |
| `category_name` | string | 카테고리명 |
| `base_price` | decimal(18,2) | 기준 가격 |
| `currency` | string | 통화 |
| `skin_type_tags` | array<string> | 지성/건성/민감성 등 |
| `concern_tags` | array<string> | 보습, 진정, 미백 등 |
| `ingredient_ids` | array<string> | 성분 ID 목록 |
| `caution_ingredient_count` | int | 주의 성분 수 |
| `updated_at` | timestamp | 상품 속성 갱신 시각 |

초기 프로젝트 권장안:

| 선택지 | 적용 |
| --- | --- |
| Fact에 상품 속성 펼치기 | `product_event_fact`에 `category_id`, `brand_id`, `unit_price`를 둔다 |
| Dimension 분리 | `dim_product`를 별도로 두고 상세 상품 속성은 Join한다 |
| 최종 권장 | 두 방식을 함께 사용한다. Fact에는 자주 쓰는 ID/가격 스냅샷만 두고, 이름/성분/피부타입은 Dimension에서 관리한다 |

## 20. Event별 필수 컬럼과 NULL 규칙

Processed에서는 단순히 nullable 여부만 보지 않고 Event별로 정상 NULL과 오류 NULL을 구분한다.

| Event | 필수 컬럼 | 정상적으로 NULL 가능 |
| --- | --- | --- |
| `session_start` | `session_id`, `page_view_id`, `event_time` | `user_id`는 실제 Web에서 NULL 가능. `product_id`, `order_id`, `order_value` |
| `page_view` | `page_view_id`, `page_type`, `session_id`, `event_time` | 세션 첫 `page_view`는 `navigation_source=session_start`. `product_id`는 목록/홈/장바구니에서 NULL 가능 |
| `product_impression` | `product_id`, `list_id`, `position`, `session_id` | `order_id`, `order_value` |
| `product_click` | `product_id`, `session_id` | `context_product_id`, `list_id`, `position`, `order_id`, `order_value` |
| `recommendation_impression` | `recommendation_id`, `product_id`, `list_id`, `position`, `algorithm` | `context_product_id`, `section_id`, `order_id`, `order_value` |
| `recommendation_click` | `recommendation_id`, `product_id`, `list_id`, `position`, `algorithm` | `context_product_id`, `section_id`, `order_id`, `order_value` |
| `quick_look` | `product_id`, `session_id` | `context_product_id`, `list_id`, `position`, `entry_source`, `recommendation_id`, `algorithm`, `order_id`, `order_value` |
| `quick_look_close` | `product_id`, `close_reason`, `dwell_ms`, `session_id` | `variants_viewed`, `added_to_cart`, `wishlisted`, `list_id`, `position`, `entry_source`, `order_id`, `order_value` |
| `search` | `search_query`, `session_id` | `result_count`, `search_id`는 구현 전 NULL 가능. `product_id`, `position`, `order_value` |
| `filter_change` | `filter_kind`, `filter_value`, `session_id` | `from`, `result_count`, `filter_action`, `filter_values`, `product_id`, `order_value` |
| `sort_change` | `sort_key`, `session_id` | `sort_direction`, `result_count`, `product_id`, `order_value` |
| `product_view` | `product_id`, `navigation_source`, `session_id`, `page_view_id` | `list_id`, `position`, `recommendation_id`, `context_product_id`, `order_id`, `order_value` |
| `section_view` | `section_id` 또는 `content_kind`, `session_id`, `page_view_id` | `order_id`, `order_value` |
| `section_dwell` | `section_id` 또는 `content_kind`, `dwell_ms`, `session_id`, `page_view_id` | `order_id`, `order_value` |
| `accordion_toggle` | `section_id`, `action`, `session_id` | `order_id`, `order_value` |
| `review_filter_apply` | `filter` 또는 `sort`, `session_id` | `result_count`, `order_id`, `order_value` |
| `text_selection` | `text_length`, `session_id` | `section_id`, `content_kind`, `product_id`는 공통 페이지에서는 NULL 가능 |
| `text_copy` | `text_length`, `session_id` | `section_id`, `content_kind`, `product_id`는 공통 페이지에서는 NULL 가능 |
| `add_to_cart` | `product_id`, `quantity`, `session_id` | `order_id`, `order_value` |
| `remove_from_cart` | `product_id`, `quantity`, `cart_size_after`, `session_id` | `order_id`, `order_value` |
| `variant_select` | `product_id`, `sku_id`, `label`, `session_id` | `previous_sku_id`, `variant_group` |
| `view_cart` | `session_id` | `cart_id`는 Raw에 없으면 NULL 가능. `product_id`, `order_value`, `item_count`, `distinct_products`, `cart_value` |
| `begin_checkout` | `items`, `session_id` | `cart_id`, `product_id`, `order_value`는 NULL 가능 |
| `purchase` | `order_id`, `items`, `session_id` | `order_value`, `currency`는 Raw 선택값. 없으면 items 합산 또는 unknown 처리 |

판정 예시:

| 상황 | 처리 |
| --- | --- |
| `product_click.product_id`가 NULL | 잘못된 로그로 보고 `bad_events` 격리 |
| `context_product_id`가 NULL | 정상. 컨텍스트가 없거나 대상 상품과 같으면 생략될 수 있음 |
| `search.product_id`가 NULL | 정상. 검색 자체는 상품 대상 Event가 아님 |
| `search.search_id`가 NULL | 검색 구현 전에는 정상. 구현 후에는 경고 또는 Spark 파생 |
| `add_to_cart.order_value`가 NULL | 정상. 구매 전 단계라 주문 금액 없음 |
| `purchase.order_value`가 NULL | Raw 기준으로는 정상 가능. `items[]`에서 합산 가능하면 파생, 불가능하면 금액 KPI에서 제외 |
| `page_view.product_id`가 NULL | 목록/홈/장바구니면 정상, 상세페이지면 오류 또는 경고 |
| `view_cart.cart_id`가 NULL | 현재 Raw 계약에서는 정상. 장바구니 구현 후 재검토 |
| `quick_look_close.dwell_ms`만 있음 | 정상. 단독 구매 의도 대신 창 내부 행동 요약과 함께 해석 |

## 21. 타입 정규화 규칙

Frontend JSON에서는 같은 값이 문자열/숫자로 섞일 수 있으므로 Processed부터 타입을 확정한다.

| 필드 | Processed type | 변환 예시 |
| --- | --- | --- |
| `event_time` | timestamp | `occurred_at` ISO string → timestamp |
| `received_at` | timestamp | Collector timestamp |
| `processed_at` | timestamp | Spark current timestamp |
| `sequence_no` | int | `"12"` → `12` |
| `position` | int | `"3"` → `3` |
| `quantity` | int | `"2"` → `2` |
| `purchase_quantity` | int | `items[].quantity` 또는 `quantity` |
| `cart_size_after` | int | `"3"` → `3` |
| `item_count` | int | `"5"` → `5` |
| `distinct_products` | int | `"4"` → `4` |
| `result_count` | int | `"42"` → `42` |
| `dwell_ms` | bigint | `"1200"` → `1200` |
| `unit_price` | decimal(18,2) | `"20000"` → `20000.00` |
| `order_value` | decimal(18,2) | `"58000"` → `58000.00` |
| `item_revenue` | decimal(18,2) | `quantity * unit_price` |
| `cart_value` | decimal(18,2) | `"58000"` → `58000.00` |
| `currency` | string | `"KRW"` |
| `is_synthetic` | boolean | actor/source 기준 파생 |
| `added_to_cart` | boolean | `"true"` → `true` |
| `wishlisted` | boolean | `"false"` → `false` |
| `quality_flags` | array<string> | `["late_event", "sequence_gap"]` |
| `matched_ingredients` | array<string> | `["Niacinamide", "Squalane"]` |
| `matched_keywords` | array<string> | `["trouble", "hydration"]` |
| `variants_viewed` | int | 배열로 들어오면 길이, 숫자로 들어오면 int로 정규화 |
| `properties_json` | string | Raw `properties`를 JSON 문자열로 보존 |
| `items` | array<struct> | `purchase`, `begin_checkout`의 상품 목록 |

`items` struct 초안:

| field | type | 비고 |
| --- | --- | --- |
| `product_id` | string | item 단위 필수 |
| `sku_id` | string/null | 옵션이 없으면 NULL |
| `quantity` | int | item 단위 수량 |
| `unit_price` | decimal(18,2)/null | 없으면 금액 KPI 일부 제외 |
| `currency` | string/null | 주문 공통 currency가 있으면 보강 가능 |

타입 변환 실패는 `bad_events.error_code='invalid_type'`으로 격리한다.

## 22. KPI 산식과 입력 Dataset

| KPI | 산식 초안 | 입력 Dataset |
| --- | --- | --- |
| 상품 CTR | `product_click / product_impression` | `product_event_fact` |
| 추천 영역 CTR | `recommendation_click / recommendation_impression` | `product_event_fact` |
| 검색 → 상품 클릭 전환율 | 검색 후 클릭 세션 수 / 검색 세션 수 | `search_event_fact`, `product_event_fact` |
| 상품 조회 → 장바구니 전환율 | `add_to_cart / product_view` | `funnel_session_fact`, `product_event_fact` |
| 장바구니 → 구매 전환율 | `purchase / add_to_cart` | `funnel_session_fact` |
| 성분 정보 열람률 | 성분 정보 확인 세션 수 / 상품 상세 조회 세션 수 | `content_interest_fact`, `funnel_session_fact` |
| 리뷰 정보 열람률 | 리뷰 정보 확인 세션 수 / 상품 상세 조회 세션 수 | `content_interest_fact`, `funnel_session_fact` |
| 사용자별 관심 카테고리 | 카테고리별 `final_weight` 합 | `persona_behavior_feature_delta` |
| 상품별 관심도 | 조회/정보/체류/장바구니/구매 가중합 | `product_event_fact`, `content_interest_fact` |
| 시나리오별 행동 차이 | `scenario_id`별 KPI 비교 | 모든 Processed Dataset |

## 23. DW/Mart로 넘길 후보

Processed Layer에서 아래 Mart/DW 테이블을 만들 수 있다.
각 Mart의 grain, 입력 Dataset, 주요 컬럼, nullable 주의사항은 `dw-schema.md`에 상세 분리한다.

| DW/Mart 후보 | 입력 Processed Dataset | Dashboard 활용 |
| --- | --- | --- |
| `product_daily_kpi` | `product_event_fact`, `persona_behavior_feature_delta` | 상품별 조회/장바구니/구매/CTR/관심도. Funnel 전환/이탈은 `funnel_daily_kpi`에서 별도 관리 |
| `recommendation_daily_kpi` | `product_event_fact` | 추천 영역 CTR, 추천 위치별 성과 |
| `search_daily_kpi` | `search_event_fact`, `product_event_fact` | 검색량, 검색 후 클릭 전환율 |
| `content_daily_kpi` | `content_interest_fact` | 성분/리뷰 열람률, 콘텐츠 관심도 |
| `funnel_daily_kpi` | `funnel_session_fact` | 단계별 전환율/이탈률 |
| `persona_segment_daily_kpi` | `funnel_session_fact`, Persona dimension | 고객군별 상품 반응 |
| `scenario_daily_kpi` | 전체 Processed Dataset | 시나리오별 행동 차이 |
| `realtime_event_stats` | `cleaned_events` | 실시간 Event 수, TPS, 처리 지연 |

## 24. 남은 미확정 사항

| 항목 | 영향 |
| --- | --- |
| Kafka topic 이름 | 현재 Backend 기본값은 `activity-events`. 환경별 override 가능성은 Kafka/Spark 담당자와 확인 |
| Kafka message 단위 | 현재 Backend 구현은 Event 1건 단위 발행 |
| Kafka partition key | 최종 기준은 `session_id`. 실제 Web Event에서 `persona_id`가 NULL일 수 있으므로 세션 단위 key를 사용 |
| 물리 저장소 | Parquet/MySQL/ClickHouse 등에 따라 타입과 파티션 방식 변경 |
| bad event 응답 포맷 | 프론트 재시도/디버깅 방식 |
| 목록/구매 화면 Trigger | `product_impression`, `begin_checkout`, `purchase` 생성 기준 |
| 상품 Dimension 원천 | 상품 데이터가 어떤 테이블/파일에서 들어오는지 확정 필요 |
| 실제 사용자 ID 정책 | 로그인/비로그인 사용자를 `user_id`로 어떻게 식별할지 확정 필요 |
| `search_id` 생성 정책 | 검색 구현 전에는 nullable/session fallback, 구현 후 Raw 추가 또는 Spark 파생 중 선택 |
| `cart_id` 생성 정책 | Raw에 없으므로 현재는 nullable, 장바구니 구현 후 Raw 추가 여부 결정 |
| Event weight 단일 출처 | 실행 상수는 `frontend/src/types/log.ts`, 의미와 근거는 Data 문서를 기준으로 관리한다 |
| 시뮬레이터 최신 Event | 최신 `dev` 기준 FE 35종 중 34종 생성. 남은 `dead_click`은 실제 UI 오작동 신호라 정책상 생성하지 않음 |
| Collector 필드 정렬 브랜치 병합 | `event_name`, `actor_type`, `page_view_id`, `sequence_no` 승격은 정렬 브랜치가 `dev`에 병합된 뒤에만 성립 |

## 25. E2E 이후 확인할 것

이 문서는 E2E 테스트 전 Draft다. 오늘 기준 목표는 구현 검증이 아니라 Raw Event를 어떤 Processed Dataset으로 바꿀지에 대한 초안 작성이다.

E2E 이후 확인할 것:

1. `dev` 반영본의 `product_view`가 E2E 환경에서도 목록 클릭 진입과 URL 직접 진입 모두에서 실제로 들어오는지
2. `product_impression`, `search`, `begin_checkout`, `purchase` Trigger가 실제 화면에서 발생하는지
3. `section_dwell` 합산 grain이 맞는지
4. batch 실패 Event 분리가 실제로 가능한지
5. `actor_type/source/scenario_id/simulation_run_id` 필터가 정상 동작하는지
6. `event_time/received_at/processed_at` 지연 측정이 가능한지
7. `category_id`, `brand_id`, `position`, `search_id`가 KPI 산식에 충분히 남는지
8. Event별 필수 컬럼 규칙이 실제 로그와 충돌하지 않는지
