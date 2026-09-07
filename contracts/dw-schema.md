# DW / Mart Schema Contract

작성일: 2026-09-02  
최종 정적 검증: 2026-09-07
상태: 통합 쇼핑몰의 사업자·브랜드·상품 귀속 계약 반영. Dimension·Mart 물리 구현은 후속 Jira에서 확정

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
| `purchase_fact` | `order_id + product_id` | 행동 Event 기반 구매 전환·재구매 집계. 매출·정산에는 사용 금지 |
| `purchase_reason_fact` | `order_id + reason` | 구매 이유 집계, 행동 추론 대조 |
| `funnel_session_fact` | `session_id + product_id` | 단계 도달·이탈 집계 |
| `persona_behavior_feature_delta` | `event_id + user_id + product_id` | Persona 관심도 집계 |
| `bad_events` | 격리 Event 1건 | Spark에서 관측한 오류 집계 |

모든 Mart는 `event_id` 중복 제거가 끝난 Processed Dataset만 입력으로 사용한다.
서로 다른 grain의 입력은 목표 Mart grain으로 각각 먼저 집계한 뒤 결합한다.
`section_dwell_agg`와 `content_interest_fact`의 nullable `product_id`는 상품 목록의
플랫폼 공통 섹션을 보존한다. 이 row는 플랫폼 탐색 분석용이며 상품 Dimension Join이나
상품·브랜드 KPI 입력으로 사용하지 않고, 직전 상품 또는 세션 내 상품으로 보정하지
않는다.

### 2.2 공통 타입과 NULL

| 필드군 | 논리 타입 | nullable | 규칙 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | KST 일간 집계일 |
| `funnel_date_kst` | date | N | 최초 Funnel 단계 도달 시각의 KST 집계일 |
| `event_minute_kst` | timestamp | N | KST minute truncate |
| `business_id` | string | Y | 상품이 귀속된 사업자. 상품 미귀속 Mart는 NULL 가능 |
| `brand_id` | string | Y | Event 대상 상품의 브랜드. 상품 미귀속 Mart는 NULL 가능 |
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

### 2.3 관심도 산식

`*_interest_score` 컬럼은 조회 수가 아니라 **행동 가중 관심도**다. 단순 조회 순위는
"인기 상품이 인기 상품이다"만 말하고 어떤 행동이 관심을 뜻하는지 구분하지 못한다.

| 컬럼 | 정의 |
| --- | --- |
| `content_interest_score` | [`processed-schema.md`](./processed-schema.md) §13.1 결과를 Mart grain으로 합산 |
| `product_interest_score` | `Σ EVENT_WEIGHT[event_name] x 해당 Event 발생 수` (상품 grain) |
| `avg_interest_score`, `avg_product_interest_score`, `avg_content_interest_score` | 위 값을 세션 수로 나눈 평균 |
| `category_interest_score` | segment x 카테고리로 `product_interest_score`를 합산 |

행동 가중치 `EVENT_WEIGHT`의 실행 원본은 `frontend/src/types/log.ts`이며 이 계약에
숫자를 복제하지 않는다. `add_to_cart`가 가장 크고 `remove_from_cart`·`rage_click`
등은 음수이므로 **점수가 음수가 될 수 있다.** 0으로 잘라내지 않는다. 담았다 뺀 상품과
아무 반응 없는 상품은 다른 신호다.

`product_interest_score`는 정규화하지 않은 절대값이라 노출이 많은 상품이 자동으로
높다. Dashboard가 순위로 쓸 때는 노출 수를 함께 제시한다.

### 2.4 표기 정규화

원천 데이터의 표기 변형은 집계 전에 병합한다. Persona 속성과 상품 리뷰 통계가 같은
어휘를 써야 segment Join이 성립하기 때문이다.

| 대상 | 병합 |
| --- | --- |
| `hair_color` | `brunette` → `brown` |
| `eye_color` | `Grey` → `gray` |
| `skin_tone` | 원본 14종을 5버킷으로 |

규칙 원본은 [`persona-schema.md`](./persona-schema.md) §3.2다.

**Persona 쪽은 이미 병합되어 있으나 상품 리뷰 통계에는 남아 있다.**
`products_200.json`의 `_review_stats.segment_counts.hair_color`에 `brunette` 키를
가진 상품이 200개 중 137개다. `dim_product`와 segment Mart를 만들 때 병합하지 않으면
같은 사람이 `brown`과 `brunette`로 나뉘어 집계된다.

## 3. Dimension

### 3.1 `dim_business`

```text
grain/key = business_id
source = Backend 사업자 등록·인증 정보
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `business_id` | string | N | Backend가 발급한 사업자 식별자 |
| `business_name` | string | N | 사업자 표시명 |
| `verification_status` | string | N | `PENDING`, `VERIFIED`, `MISMATCH`, `RETRY_NEEDED`, `INACTIVE` |
| `created_at` | timestamp | N | 사업자 등록 시각 |
| `updated_at` | timestamp | Y | 갱신 시각 |

통합몰 전환으로 기존 Storefront 격리 식별자 규칙은 폐기한다. Event에
`business_id`를 반복하지 않고 상품·브랜드 Dimension에서 사업자 귀속을 파생한다.
대시보드 조회 인가는 Backend의 사업자→브랜드 소유 관계를 기준으로 한다.

### 3.2 `dim_brand`

```text
grain/key = brand_id
source = Backend 브랜드 등록 정보
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `brand_id` | string | N | 브랜드 식별자 |
| `business_id` | string | N | 소유 사업자. `dim_business` FK |
| `brand_name` | string | N | 브랜드 표시명 |
| `brand_hash` | string | N | Commons Mart용 비가역 가명 |
| `commons_participating` | boolean | N | 억제 규칙을 충족한 공유 집계 대상 여부 |
| `created_at` | timestamp | N | 브랜드 등록 시각 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`brand_hash`와 `commons_participating`의 산출·억제 규칙은 Commons Mart Jira에서
확정한다. 원본 `brand_id`는 다른 브랜드에게 노출하지 않는다.

### 3.3 `dim_product`

```text
grain/key = product_id
source = batch/ingest/data/products_200.json, 입점 브랜드 등록 상품, Processed dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `product_id` | string | N | 상품 ID |
| `product_name` | string | N | 상품명 |
| `product_source` | string | N | `seed_catalog`, `brand_registered` |
| `brand_id`, `brand_name` | string | N | 브랜드 식별자·표시명 |
| `primary_category`, `secondary_category`, `tertiary_category` | string | Y | 카테고리 계층 |
| `category_id` | string | Y | Dashboard 필터 ID |
| `category_path` | array<string> | Y | 카테고리 경로 |
| `base_price` | decimal(18,2) | Y | 기준 가격 |
| `currency` | string | Y | 가격 통화 |
| `rating` | double | Y | 평균 평점 |
| `rating_source` | string | Y | `observed`, `injected`. 주입값을 실측과 섞지 않는다 |
| `review_count`, `loves_count` | bigint | Y | 리뷰·관심 수 |
| `skin_type_tags`, `concern_tags`, `ingredient_ids` | array<string> | Y | 상품 속성 |
| `caution_ingredient_count` | int | Y | 주의 성분 수 |
| `updated_at` | timestamp | Y | 갱신 시각 |

### 3.4 `dim_persona_segment`

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

### 3.5 `dim_date`

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

### 3.6 `dim_event`

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

### 3.7 Simulation Dimension projection

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
key = event_date_kst + business_id + brand_id + product_id + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact, purchase_fact, persona_behavior_feature_delta, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통 계약 | key 규칙 | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `purchase_count`, `purchase_quantity` | bigint | N | Event·수량 집계. `purchase_count`는 `order_id` 기준 고유 주문 수 |
| `quick_look_sessions`, `product_view_sessions`, `add_to_cart_sessions`, `remove_from_cart_sessions`, `purchase_sessions`, `unique_user_count`, `session_count` | bigint | N | 세션·사용자 집계 |
| `product_ctr`, `detail_entry_rate`, `add_to_cart_rate`, `purchase_rate`, `product_interest_score` | double | Y | 비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.2 `recommendation_daily_kpi`

```text
key = event_date_kst + business_id + brand_id + recommendation_id + list_id + algorithm + product_id + context_product_id + position + actor_type + source + scenario_id + simulation_run_id
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
key = event_date_kst + search_query_hash + actor_type + source + scenario_id + simulation_run_id
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
key = event_date_kst + business_id + brand_id + product_id + section_id + content_kind + actor_type + source + scenario_id + simulation_run_id
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
이 Mart는 `product_id`가 있는 상품 상세 콘텐츠만 입력으로 사용한다.
`product_id = NULL`인 플랫폼 목록 섹션은 상품·브랜드 KPI에 포함하지 않는다. 플랫폼
공통 콘텐츠 Mart가 필요해지면 `product_id` 없는 별도 grain과 key를 계약한 뒤
집계한다.

### 4.5 `funnel_daily_kpi`

```text
key = funnel_date_kst + business_id + brand_id + product_id + actor_type + source + scenario_id + simulation_run_id
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
key = event_date_kst + business_id + brand_id + segment_type + segment_value + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
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
key = event_date_kst + scenario_id + simulation_run_id + actor_type + source + generator_type
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
key = event_minute_kst + event_name + source + actor_type + scenario_id + simulation_run_id
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
key = event_minute_kst + error_stage + error_code + event_name + source + actor_type
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
4. 행동 `purchase` Event와 `purchase_fact`는 전환·재구매 분석에만 사용한다.
   매출·정산은 Backend의 PAID 주문 상품 Fact만 정본으로 사용한다.
   행동 `purchase_count`는 `order_id` 기준 고유 전환 수이며 상품 row 수가 아니다.
5. `generator_type`, `scenario_id`, `simulation_run_id`는 Processed에서 승격된
   synthetic metadata를 사용한다.
6. 상품 대상 Mart는 `product_id`에서 파생한 `brand_id`, `business_id`를
   집계 시점 스냅샷으로 보존한다.
7. 상품이 없는 플랫폼 공통 Event를 특정 상품·사업자·브랜드에 임의 귀속하거나
   상품·브랜드 KPI에 포함하지 않는다. 플랫폼 공통 콘텐츠는 필요할 때 별도 grain으로
   집계한다. 대시보드 접근 격리는 Backend 인가가 담당한다.
8. `*_interest_score`를 0으로 하한 절단하지 않는다. 음수는 부정 행동의 신호다.
9. §2.4의 표기 병합을 집계 전에 적용한다. 특히 상품 리뷰 통계의 `brunette`를
   `brown`으로 합치지 않으면 segment Join이 같은 사람을 둘로 나눈다.
