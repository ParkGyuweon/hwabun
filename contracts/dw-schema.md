# DW / Mart Schema Contract

작성일: 2026-09-02  
최종 정적 검증: 2026-09-02
상태: 저장 계층·공통 규칙 확정, Tenant 축 추가. Dashboard Mart·KPI 후보는 협의 후 확정

## 1. 범위와 우선순위

이 문서는 [`processed-schema.md`](./processed-schema.md)의 Processed Dataset을
Delta Lake에 보존하고 MySQL `dw`로 제공하는 저장 계층, 책임 경계와 공통 물리
규칙을 확정한다. Dimension과 Mart의 grain, 입력, key, 컬럼, 논리 타입 및 nullable은
현재 Dashboard 후보를 구현 가능성 관점에서 정리한 초안이다.

- Delta Lake의 `marts`는 계산 결과의 기준 저장소다.
- MySQL `dw` schema는 Dashboard API 조회용 serving projection이다.
- 물리 파티션, 인덱스, Delta `MERGE`, MySQL DDL은 구현 단계에서 확정된 저장
  계층과 공통 규칙을 보존하는 범위로 정한다.
- 처리 근거, KPI 화면 연결, 현재 구현 상태와 검증 계획은
  [`../docs/analytics/dw-design.md`](../docs/analytics/dw-design.md)에서 설명한다.

§2의 입력 grain·공통 타입·NULL·집계 원칙과 Delta→MySQL 책임 경계는 이번 Jira의
확정 범위다. §3~§5의 Dimension·Mart·KPI는 저장 가능성을 확인하기 위한 후보이며,
Dashboard에 실제 제공할 지표는 추천·AI 담당과 합의한 뒤 별도 확정한다.

## 2. 공통 계약

### 2.1 입력

| 입력 | grain | 용도 |
| --- | --- | --- |
| `cleaned_events` | `event_id` | 정상 Event 수와 실시간 통계 |
| `product_event_fact` | `event_id + item_index + product_id` | 상품·추천·구매 집계 |
| `search_event_fact` | `event_id` | 검색 집계 |
| `section_dwell_agg` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 체류 검증·재집계 |
| `content_interest_fact` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 콘텐츠 관심 집계 |
| `funnel_session_fact` | `session_id + product_id` | 단계 도달·이탈 집계 |
| `persona_behavior_feature_delta` | `event_id + user_id + product_id` | Persona 관심도 집계 |
| `bad_events` | 격리 Event 1건 | Spark에서 관측한 오류 집계 |

모든 Mart는 `event_id` 중복 제거가 끝난 Processed Dataset만 입력으로 사용한다.
서로 다른 grain의 입력은 목표 Mart grain으로 각각 먼저 집계한 뒤 결합한다.

### 2.2 공통 타입과 NULL

| 필드군 | 논리 타입 | nullable | 규칙 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | KST 일간 집계일 |
| `funnel_date_kst` | date | N | 최초 Funnel 단계 도달 시각의 KST 집계일 |
| `event_minute_kst` | timestamp | N | KST minute truncate |
| `tenant_id` | string | N | Storefront 소유 Tenant. 모든 Mart의 집계 축 |
| `actor_type` | string | N | `user`, `synthetic` |
| `source` | string | N | MVP: `web`, `simulator` |
| `generator_type` | string | Y | `python_batch`, `agent_llm`; Web은 NULL |
| `scenario_id` | string | Y | Web은 NULL 가능 |
| `simulation_run_id` | string | Y | Web은 NULL 가능 |
| `*_count`, `*_sessions` | bigint | N | 집계 결과가 없으면 `0` |
| `*_rate`, `*_score`, 평균·지연 | double | Y | 분모 0 또는 입력 부재면 NULL |
| 금액 | decimal(18,2) | Y | `currency`와 함께 해석 |
| `mart_processed_at` | timestamp | N | Mart 생성·갱신 시각 |

모든 비율은 `numerator / NULLIF(denominator, 0)`으로 계산한다. Kafka payload의
`source`를 우선 사용하며 누락된 과거 데이터만 `synthetic → simulator`, 그 외
`web`으로 보정한다.

## 3. Dimension

### 3.1 `dim_tenant`

```text
grain/key = tenant_id
source = 입점 Tenant 등록 정보
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `tenant_id` | string | N | slug. 생성 후 고정하며 조회 시 재계산하지 않는다 |
| `display_name` | string | N | 화면 표시명 |
| `tenant_hash` | string | N | 익명 집계용 가명. `tenant_id`와 다른 값이어야 한다 |
| `product_count` | int | Y | 진열 상품 수 |
| `commons_participating` | boolean | N | 익명 집계 기여·조회 대상 여부 |
| `created_at` | timestamp | N | 입점 시각 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`tenant_id`는 표시명을 NFKD 정규화해 ASCII로 접고 slug로 바꾼 값이며 생성 규칙은
[`event-properties-schema.md` §1.1.1](./event-properties-schema.md)을 따른다. **한 번
생성한 뒤 이 Dimension에 고정한다.** 조회할 때마다 다시 계산하면 정규화 규칙이나
표시명이 바뀔 때 partition이 조용히 갈라진다. 충돌이 생기면 뒤에 순번을 붙인다.

`tenant_hash`를 따로 두는 이유는 익명 집계에서 다른 Tenant에게 보이는 값이기
때문이다. `tenant_id`를 그대로 쓰면 slug에서 실제 Tenant를 알 수 있어 익명성이
성립하지 않는다. 되돌릴 수 없어야 한다.

`commons_participating`은 진열 상품이 적어 익명 집계에 기여하기 어려운 Tenant를
구분하기 위한 컬럼이다. 어떤 기준으로 이 값을 정할지는 별도 합의 사항이며 이
계약은 컬럼만 정의한다.

### 3.2 `dim_product`

```text
grain/key = product_id
source = batch/ingest/data/products_200.json, Processed dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `product_id` | string | N | 상품 ID |
| `product_name` | string | N | 상품명 |
| `brand_id`, `brand_name` | string | Y | 브랜드 식별자·표시명 |
| `primary_category`, `secondary_category`, `tertiary_category` | string | Y | 카테고리 계층 |
| `category_id` | string | Y | Dashboard 필터 ID |
| `category_path` | array<string> | Y | 카테고리 경로 |
| `base_price` | decimal(18,2) | Y | 기준 가격 |
| `currency` | string | Y | 가격 통화 |
| `rating` | double | Y | 평균 평점 |
| `review_count`, `loves_count` | bigint | Y | 리뷰·관심 수 |
| `skin_type_tags`, `concern_tags`, `ingredient_ids` | array<string> | Y | 상품 속성 |
| `caution_ingredient_count` | int | Y | 주의 성분 수 |
| `updated_at` | timestamp | Y | 갱신 시각 |

### 3.3 `dim_persona_segment`

```text
grain/key = segment_type + segment_value
source = bridge_persona_segment
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `segment_type` | string | N | Persona 계약의 허용 segment type |
| `segment_value` | string | N | segment 값 |
| `display_name`, `source` | string | Y | 표시명·원천 |
| `population_count` | bigint | Y | 해당 표본의 Persona 수 |
| `persona_source` | string | Y | 모집단 계산 표본 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`bridge_persona_segment`의 grain과 컬럼은
[`persona-schema.md`](./persona-schema.md)의 정의를 그대로 사용한다. Attribute
Affinity는 상품 축이 있으므로 이 Dimension에 저장하지 않는다.

### 3.4 `dim_date`

```text
grain/key = event_date_kst
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | 기준일 |
| `day_of_week` | int | N | 월요일 1 |
| `week_start_date`, `month_start_date` | date | N | 주·월 시작일 |
| `quarter` | string | N | 분기 |
| `is_weekend` | boolean | N | 주말 여부 |

### 3.5 `dim_event`

```text
grain/key = event_name
source = event-properties-schema.md
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_name` | string | N | 공식 Event 이름 |
| `intent` | string | N | 공식 intent |
| `priority` | string | N | `P0`, `P1`, `P2` |
| `ga4_event_name` | string | Y | GA4 매핑 |
| `is_dashboard_core` | boolean | N | 핵심 KPI 사용 여부 |
| `description` | string | Y | 설명 |

### 3.6 Simulation Dimension projection

`dim_scenario`와 `dim_simulation_run`의 grain, 필수 필드와 허용값은
[`persona-schema.md`](./persona-schema.md)의 `scenario`, `simulation_run` 계약을
따른다. DW에는 해당 구조를 같은 key로 projection하며 `updated_at`을 선택적으로
추가할 수 있다. Event payload에는 `persona_source`를 반복 저장하지 않고
`simulation_run_id → dim_simulation_run.persona_source`로 조회한다.

## 4. 일간 Mart 후보

아래 Mart는 현재 Dashboard 요구를 저장 구조에 투영한 후보안이다. 지표 채택 전에는
물리 Table 생성 계약으로 해석하지 않는다. 채택 시 표의 `key` 전체를 복합 key로
사용하고, `scenario_id`, `simulation_run_id`가 NULL인 Web 행도 같은 grain 규칙으로
집계한다.

### 4.1 `product_daily_kpi`

```text
key = event_date_kst + tenant_id + product_id + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact, persona_behavior_feature_delta, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통 계약 | key 규칙 | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `purchase_count`, `purchase_quantity` | bigint | N | Event·수량 집계. `purchase_count`는 `order_id` 기준 고유 주문 수 |
| `quick_look_sessions`, `product_view_sessions`, `add_to_cart_sessions`, `remove_from_cart_sessions`, `purchase_sessions`, `unique_user_count`, `session_count` | bigint | N | 세션·사용자 집계 |
| `revenue_amount` | decimal(18,2) | Y | `purchase`의 `item_revenue` 합계 |
| `currency` | string | Y | 통화 |
| `product_ctr`, `detail_entry_rate`, `add_to_cart_rate`, `purchase_rate`, `product_interest_score` | double | Y | 비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.2 `recommendation_daily_kpi`

```text
key = event_date_kst + tenant_id + recommendation_id + list_id + algorithm + product_id + context_product_id + position + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string/int | `list_id`, `context_product_id`, scenario/run만 Y | 집계 축 |
| `recommendation_impression_count`, `recommendation_click_count`, `unique_session_count` | bigint | N | 추천 성과 |
| `recommendation_ctr` | double | Y | 클릭/노출 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.3 `search_daily_kpi`

```text
key = event_date_kst + tenant_id + search_query_hash + actor_type + source + scenario_id + simulation_run_id
input = search_event_fact, product_event_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | 집계 축 |
| `normalized_query` | string | Y | 저장 정책이 허용할 때만 보존 |
| `search_count`, `search_session_count`, `zero_result_count`, `search_click_session_count`, `clicked_product_count` | bigint | N | 검색 성과 |
| `avg_result_count`, `search_to_click_rate` | double | Y | 평균·전환율 |
| `top_clicked_product_id` | string | Y | 최다 클릭 상품 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.4 `content_daily_kpi`

```text
key = event_date_kst + tenant_id + product_id + section_id + content_kind + actor_type + source + scenario_id + simulation_run_id
input = content_interest_fact, section_dwell_agg, funnel_session_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | section/content/scenario/run만 Y | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `section_view_count`, `section_view_sessions`, `dwell_ms_sum`, `accordion_expand_count`, `text_selection_count`, `text_copy_count`, `matched_ingredient_count`, `ingredient_view_sessions`, `review_view_sessions`, `product_view_sessions` | bigint | N | 콘텐츠 행동 집계 |
| `avg_dwell_ms_per_session`, `ingredient_view_rate`, `review_view_rate`, `content_interest_score` | double | Y | 평균·비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`dwell_ms_sum`은 `content_interest_fact`를 기본 원천으로 사용한다.
`section_dwell_agg`와 동시에 합산하지 않는다.

### 4.5 `funnel_daily_kpi`

```text
key = funnel_date_kst + tenant_id + product_id + actor_type + source + scenario_id + simulation_run_id
input = funnel_session_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | `funnel_date_kst`는 최초 Funnel 진입일 기준 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `impression_sessions`, `quick_look_sessions`, `quick_look_cart_sessions`, `direct_click_sessions`, `direct_click_cart_sessions`, `click_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `checkout_sessions`, `purchase_sessions` | bigint | N | 단계 도달 세션 |
| `impression_to_click_rate`, `click_to_view_rate`, `view_to_information_rate`, `view_to_cart_rate`, `cart_to_purchase_rate`, `view_to_purchase_rate`, `dropoff_after_impression_rate`, `dropoff_after_view_rate`, `dropoff_after_cart_rate` | double | Y | 전환·이탈률 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.6 `persona_segment_daily_kpi`

```text
key = event_date_kst + tenant_id + segment_type + segment_value + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = funnel_session_fact, persona_behavior_feature_delta, bridge_persona_segment, dim_persona_segment, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | segment 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `segment_user_count`, `session_count`, `product_view_sessions`, `add_to_cart_sessions`, `purchase_sessions` | bigint | N | 행동 집계 |
| `avg_interest_score`, `category_interest_score`, `affinity_lift` | double | Y | 행동 로그 기반 지표 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.7 `scenario_daily_kpi`

```text
key = event_date_kst + tenant_id + scenario_id + simulation_run_id + actor_type + source + generator_type
input = cleaned_events, product_event_fact, funnel_session_fact, content_interest_fact, persona_behavior_feature_delta
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator만 Y | synthetic 실행 비교 축 |
| `event_count`, `session_count`, `persona_count`, `product_view_count`, `add_to_cart_count`, `purchase_count` | bigint | N | 실행 성과 |
| `avg_event_count_per_session`, `avg_product_interest_score`, `avg_content_interest_score`, `view_to_cart_rate`, `view_to_purchase_rate` | double | Y | 평균·전환율 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

## 5. 실시간 Mart 후보

### 5.1 `realtime_event_stats`

```text
key = event_minute_kst + tenant_id + event_name + source + actor_type + scenario_id + simulation_run_id
input = cleaned_events
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | 분 단위 축 |
| `event_count`, `unique_session_count` | bigint | N | 정상 Event·세션 수 |
| `avg_ingest_latency_ms`, `p95_ingest_latency_ms`, `avg_processing_lag_ms`, `p95_processing_lag_ms`, `events_per_second` | double | Y | 지연·처리량 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 5.2 `realtime_bad_event_stats`

```text
key = event_minute_kst + tenant_id + error_stage + error_code + event_name + source + actor_type
input = bad_events
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_minute_kst`, `error_stage`, `error_code` | timestamp/string | N | 오류 집계 축 |
| `event_name`, `source`, `actor_type` | string | Y | 파싱 가능한 경우의 Event 정보 |
| `bad_event_count` | bigint | N | 격리 Event 수 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

Collector가 Kafka 전송 전에 거부한 Event는 별도 topic/storage가 없는 한 이 Mart에
포함하지 않는다.

## 6. 후보 Mart 물리화 시 보존할 조건

1. Delta `marts`와 MySQL `dw` projection은 같은 grain과 KPI 값을 가져야 한다.
2. MySQL serving table은 API 조회에 불필요한 상세 컬럼을 생략할 수 있지만 key와
   KPI 의미를 바꾸지 않는다.
3. `category_id`, `brand_id`는 `dim_product`에서 보강한 집계 시점 스냅샷이다.
4. 주문 총액 `order_value`를 explode된 상품 row에서 합산하지 않는다. 상품 매출은
   `purchase` Event의 `item_revenue`만 합산한다.
5. `generator_type`, `scenario_id`, `simulation_run_id`는 Processed에서 승격된
   synthetic metadata를 사용한다.
6. 모든 Mart는 `tenant_id`를 집계 축으로 포함하고 소비자는 이 값으로만 격리한다.
   상품 브랜드 `brand_id`를 격리 키로 사용하지 않는다.
7. `tenant_id`가 NULL인 row는 Tenant 격리가 필요한 Mart에 넣지 않는다.
   `schema_version = 0.2.0-draft` Event가 여기 해당한다.
