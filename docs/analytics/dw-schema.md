# DW Schema

작성일: 2026-08-28  
상태: Draft, E2E 테스트 전 논리 Mart 초안. Kafka payload 서버 메타 필드 계약은 BE 커넥터 담당 확인 완료(2026-08-31)
관련 문서: `../../contracts/event-schema.json`, `event-taxonomy-trigger-schema.md`,
`../../contracts/processed-schema.md`, `spark-processing-design.md`, `persona-schema.md`

## 1. 문서 목적

이 문서는 `../../contracts/processed-schema.md`의 Processed Dataset을 B2B Dashboard
조회용 DW/Mart로 변환하는 기준을 정의한다.

여기서 DW Schema는 MySQL, ClickHouse, Parquet, BigQuery 같은 물리 저장소의 DDL이 아니다. 저장소 확정 전에도 Front/Backend/Data/Dashboard 팀이 같은 KPI 기준으로 논의할 수 있도록 Fact, Dimension, Mart의 논리 구조를 정리한다.

Processed Schema와 DW Schema의 차이는 다음과 같다.

| 구분 | 목적 | 예시 |
| --- | --- | --- |
| Processed Schema | Raw Event를 Spark 등에서 정제, 중복 제거, 타입 정규화, 세션화하는 중간 처리 기준 | `cleaned_events`, `product_event_fact`, `content_interest_fact` |
| DW Schema | Dashboard API가 빠르게 조회할 수 있도록 집계/차원 형태로 재구성한 분석 기준 | `product_daily_kpi`, `funnel_daily_kpi`, `dim_product` |

## 2. 현재 구현 및 문서 전제

백엔드 현재 구현 기준으로 Event 수집 경로와 주요 Event 필드는 문서 계약과 대부분 맞춰졌다. BE 커넥터 담당 확인 결과(2026-08-31), Collector가 Kafka payload에 추가하는 `received_at`, `source`, `request_id`, `event_index` 구조를 최종 Raw Kafka 계약으로 사용한다. `scenario_id`, `simulation_run_id`는 E2E 기준 Raw payload의 top-level이 아니라 `properties` 내부 값으로 보고, Processed/DW에서 컬럼으로 승격한다.

| 항목 | 현재 확인 내용 | DW 문서 반영 |
| --- | --- | --- |
| 프로젝트 구조 | `frontend`, `backend`, `batch`, `simulator`, `contracts`, `docs/analytics` 폴더 존재 | 데이터 원천과 Event 문서가 분리되어 있음 |
| Backend Collector | `S15P21A306-29-be-post-events-api-v0-1` 기준 API는 `POST /api/events`, batch 최대 100건 | Event 수집 경로는 현재 구현 기준으로 확정 |
| Backend 브랜치 상태 | 위 필드 정렬은 `S15P21A306-29-be-post-events-api-v0-1`에만 있고 `dev`에는 아직 병합되지 않았다. `dev`의 Collector는 `event_type`/`event_time` 기준 구버전이다 | E2E 전에 병합이 선행되어야 한다. 이 문서의 필드 전제는 정렬된 브랜치 기준이다 |
| Kafka topic | 기본값 `activity-events` | 실제 Spark 입력 topic으로 사용할 수 있음. 환경별 override 가능성은 Kafka/Spark 담당자와 확인 |
| Backend Event 필드 | `schema_version`, `event_id`, `event_name`, `intent`, `occurred_at`, `persona_id`, `session_id`, `page_view_id`, `sequence_no`, `page_type`, `product_id`, `actor_type`, `environment`, `properties`, `received_at` | 주요 Event 필드는 문서 계약과 맞음. `event_id`는 dedup 기준 |
| Backend Kafka message | Event 단위 발행, key는 `session_id`, payload에는 `received_at`, `source`, `request_id`, `event_index` 포함 | Raw 중복 수신은 가능하며, dedup은 Data/Spark `cleaned_events` 생성 단계에서 수행 |
| 중복 처리 계약 | Raw는 수신 Event를 그대로 보존하고, Processed `cleaned_events` 생성 단계에서 `event_id` 기준 dedup | 동일 `event_id`의 대표 Event는 `received_at ASC`, 동률이면 `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 기준 최초 1건 |
| 상품 원천 데이터 | `batch/ingest/data/products_200.json`, `batch/ingest/data/affinity_lift.csv` | `dim_product`, `dim_persona_segment` 후보 원천 |
| Dashboard 구현 | 별도 Dashboard 구현 폴더는 아직 명확하지 않음 | 화면 구현체가 아니라 기획 KPI와 Processed Schema 기준으로 설계 |

## 3. 설계 원칙

| 원칙 | 내용 |
| --- | --- |
| 논리 Mart 중심 | 물리 DB 제품에 종속되지 않는 Fact/Dimension/Mart 구조로 정의한다 |
| KPI 조회 최적화 | Dashboard에서 반복 조회하는 지표는 일간 Mart로 미리 집계한다 |
| 기본 집계 축 | `event_date_kst`, `product_id`, `actor_type`, `source`, `scenario_id`를 우선 축으로 사용한다 |
| Synthetic/Web 분리 | 실제 Web Event와 synthetic Event는 같은 Mart에서 조회하되 `actor_type`, `source`, `simulation_run_id`로 필터링한다 |
| 시간 기준 분리 | 원본 `event_time`은 UTC로 저장하고, Dashboard 일간 집계는 KST 파생일인 `event_date_kst`를 사용한다 |
| 중복 제거 후 집계 | DW/Mart는 `event_id` 기준 deduplication이 끝난 `cleaned_events` 및 파생 Processed Dataset만 입력으로 사용한다. Raw의 중복 원본을 직접 집계하지 않는다 |
| 서로 다른 grain Join 금지 | 서로 다른 Processed Dataset은 row-level로 직접 Join하지 않고, 각 Dataset을 목표 Mart grain으로 먼저 집계한 뒤 집계 결과를 Join한다 |
| 상품 속성 관리 | 상품명, 브랜드, 카테고리, 성분/피부 태그는 `dim_product`에서 관리한다 |
| 상품 속성 스냅샷 | 조회 성능과 당시 상태 보존을 위해 주요 Mart에는 `category_id`, `brand_id`를 스냅샷 컬럼으로 둔다 |
| 상품 대상 기준 | top-level `product_id`는 Event 대상 상품이다. 추천 클릭처럼 보고 있던 상품과 대상이 다르면 `context_product_id`로 배경 상품을 보존한다 |
| source 기준 | Kafka payload의 `source`를 우선 사용한다. 누락 시 MVP fallback은 `actor_type='synthetic' → simulator`, 그 외 → `web`으로 둔다. 서버 내부 Event는 별도 경로 확인 시 `server`로 둔다 |
| 미구현 Event 표시 | `search`, `begin_checkout`, `purchase`는 화면 구현 전까지 provisional로 표시한다 |
| NULL 의미 보존 | 원천이 없는 값은 억지 생성하지 않고 nullable로 둔다. 정상 NULL과 오류 NULL은 Processed validation 규칙에서 구분한다 |
| 비율 산식 | 분모가 0이면 비율은 `0`이 아니라 `NULL`로 둔다 |

## 4. DW 입력 Dataset / Dimension

DW/Mart는 아래 Processed Dataset과 Dimension/Bridge를 입력으로 한다.

| Processed Dataset | Grain | DW 활용 |
| --- | --- | --- |
| `cleaned_events` | `event_id` | 실시간 Event 통계, 원본 추적, dedup 이후 Event 수 |
| `product_event_fact` | `event_id + item_index + product_id` | 상품 노출/클릭/조회/장바구니/구매 집계 |
| `search_event_fact` | `event_id` | 검색 Event 자체의 검색어/결과 수 분석 |
| `section_dwell_agg` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 섹션별 체류시간 집계 |
| `content_interest_fact` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 성분/리뷰/텍스트 선택/복사 관심도 |
| `funnel_session_fact` | `session_id + product_id` | Funnel 단계 도달/이탈 |
| `persona_behavior_feature_delta` | `event_id + user_id + product_id` | Persona별 관심 feature 변화 |
| `dim_product` | `product_id` | 상품/브랜드/카테고리/가격/성분 속성 Join |
| `bridge_persona_segment` | `persona_id + segment_type + segment_value` | Persona와 segment 연결 |
| `dim_scenario` | `scenario_id` | 시나리오 메타데이터 |
| `dim_simulation_run` | `simulation_run_id` | 실행 단위 메타데이터. `persona_source`, 재현 version 필터 |

`bridge_persona_segment`, `dim_scenario`, `dim_simulation_run`의 원천 정의는 `persona-schema.md`다. 세 테이블의 컬럼과 허용값은 그 문서와 동일하게 유지한다.

## 5. 공통 필드 규칙

| 필드 | 타입 초안 | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | Dashboard 일간 기준일 |
| `event_hour_kst` | timestamp | KST 기준 시간 단위 집계. hour truncate timestamp |
| `event_minute_kst` | timestamp | 실시간 모니터링용 minute truncate timestamp |
| `actor_type` | string | `user`, `synthetic` |
| `source` | string | MVP 기준 `web`, `simulator` |
| `generator_type` | string/null | synthetic 생성 방식. 예: `python_batch`, `agent_llm` |
| `scenario_id` | string/null | 시나리오 ID. 실제 Web Event는 NULL 가능 |
| `simulation_run_id` | string/null | synthetic 실행 단위 ID. 실제 Web Event는 NULL 가능 |
| `count` 계열 | bigint | Event 수, 세션 수, 사용자 수 |
| `rate` 계열 | double/null | 분모가 0이면 NULL |
| `amount` 계열 | decimal(18,2)/null | 금액 지표. currency와 함께 해석 |
| `mart_processed_at` | timestamp | Mart 생성/갱신 시각 |

`simulation_run_id`는 synthetic 분석에서는 분리에 가깝게 필수지만, 실제 Web Event에서는 NULL이 정상이다. Dashboard 기본 조회에서는 전체 합산을 보여줄 수 있고, 실험 분석에서는 `scenario_id`, `simulation_run_id`로 필터링한다.

100명 agent 기반 생성과 9,900명 Python batch 생성을 구분해야 하면 `source`를 늘리지 않는다. 생성 방식은 `generator_type`, 표본 구분은 `simulation_run_id → dim_simulation_run.persona_source`로 본다. E2E MVP에서는 모든 synthetic Event를 `source='simulator'`로 둔다.

## 6. Dimension 초안

### 6.1 `dim_product`

상품 속성 Dimension이다. Event마다 상품명/브랜드/성분 정보를 반복 저장하지 않고 `product_id` 기준으로 Join한다.

```text
grain = product_id
source = batch/ingest/data/products_200.json, Processed dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `product_id` | string | N | 상품 ID |
| `product_name` | string | N | 상품명 |
| `brand_id` | string/null | Y | 브랜드 ID |
| `brand_name` | string/null | Y | 브랜드명 |
| `primary_category` | string/null | Y | 대분류 |
| `secondary_category` | string/null | Y | 중분류 |
| `tertiary_category` | string/null | Y | 소분류 |
| `category_id` | string/null | Y | Dashboard 필터용 카테고리 ID. 원천에 없으면 카테고리 경로에서 파생 |
| `category_path` | array<string> | Y | 카테고리 계층 |
| `base_price` | decimal(18,2)/null | Y | 기준 가격 |
| `currency` | string/null | Y | 가격 통화 |
| `rating` | double/null | Y | 평균 평점 |
| `review_count` | bigint/null | Y | 리뷰 수 |
| `loves_count` | bigint/null | Y | 좋아요/관심 수 |
| `skin_type_tags` | array<string> | Y | 관련 피부 타입 |
| `concern_tags` | array<string> | Y | 피부 고민 태그 |
| `ingredient_ids` | array<string> | Y | 성분 ID 목록 |
| `caution_ingredient_count` | int/null | Y | 주의 성분 수 |
| `updated_at` | timestamp | Y | Dimension 갱신 시각 |

### 6.2 `dim_persona_segment`

Persona를 개별 사용자 단위가 아니라 Dashboard 분석용 segment로 묶는 Dimension이다. segment 값 자체의 표시명과 모집단 크기만 관리한다. 상세 Persona 정의는 `persona-schema.md`를 따른다.

```text
grain = segment_type + segment_value
source = simulator persona data (persona_profile / bridge_persona_segment)
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `segment_type` | string | N | `skin_type`, `skin_tone`, `hair_color`, `eye_color`, `review_bucket`, `persona_source` |
| `segment_value` | string | N | segment 값 |
| `display_name` | string | Y | Dashboard 표시명 |
| `source` | string | Y | segment 원천 |
| `population_count` | bigint/null | Y | 해당 segment Persona 수 |
| `persona_source` | string/null | Y | `population_count`를 계산한 표본. 기본 `batch_sample` |
| `updated_at` | timestamp | Y | Dimension 갱신 시각 |

주의사항:

- **Attribute Affinity는 이 Dimension에 넣지 않는다.** `affinity_lift.csv`의 grain은 `attribute + segment + product_id`(4,000행 = 200상품 × 20세그먼트)이므로, segment 단위 Dimension에 `affinity`/`lift`를 담으면 상품 축이 사라져 값이 뭉개진다. 상품×segment 친화도가 Dashboard에 필요하면 `product_segment_affinity`(grain `product_id + segment_type + segment_value`)를 별도 Fact/Dimension으로 둔다.
- `population_count`는 표본에 따라 값이 달라진다. agent 100명은 균등배분이라 모집단 분포가 아니므로, 기본값은 `persona_source='batch_sample'` 기준으로 계산하고 어떤 표본인지 컬럼으로 남긴다.
- 상품 단위 segment 집계를 `products_200.json`의 `_review_stats.segment_counts`에서 가져올 경우, 해당 필드의 `hair_color`에는 `brunette`가 병합되지 않은 채 남아 있다. 읽는 쪽에서 `brown`에 합산해야 한다. 근거는 `persona-attribute-preprocessing.md` §11.1.
- `segment_type` 목록은 `persona-schema.md`의 `bridge_persona_segment`와 동일해야 한다. 현재 Persona 원천(`simulator/personas/data/personas_*.json`)에는 피부 고민 필드가 없으므로 **`concern`은 segment_type에서 제외한다.** 상품 속성인 `dim_product.concern_tags`는 다른 축이므로 그대로 유지한다.
- Persona 생성기에 고민 속성이 추가되면 Persona Schema와 이 Dimension에 동시에 다시 넣는다.

### 6.3 `bridge_persona_segment`

개별 Persona와 Dashboard segment를 연결하는 bridge table이다. `dim_persona_segment`는 segment 값 자체만 관리하므로, Persona별 피부 타입/리뷰 활동량/생성 원천을 분석하려면 이 연결 테이블이 필요하다.

```text
grain = persona_id + segment_type + segment_value
source = Persona Schema, simulator persona data
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `segment_type` | string | N | `skin_type`, `skin_tone`, `hair_color`, `eye_color`, `review_bucket`, `persona_source` |
| `segment_value` | string | N | segment 값 |
| `valid_from` | date/null | Y | segment 적용 시작일 |
| `valid_to` | date/null | Y | segment 적용 종료일 |
| `updated_at` | timestamp | Y | bridge 갱신 시각 |

### 6.4 `dim_date`

KST 기준 날짜 Dimension이다.

```text
grain = event_date_kst
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | 기준일 |
| `day_of_week` | int | N | 요일. 월요일 1 기준 |
| `week_start_date` | date | N | 주 시작일 |
| `month_start_date` | date | N | 월 시작일 |
| `quarter` | string | N | 분기 |
| `is_weekend` | boolean | N | 주말 여부 |

### 6.5 `dim_event`

Event 의미와 Dashboard 활용 우선순위를 관리한다.

```text
grain = event_name
source = event-taxonomy-trigger-schema.md
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_name` | string | N | 공식 Event 이름 |
| `intent` | string | N | `session`, `exposure`, `interest`, `comparison`, `validation`, `hesitation`, `conversion`, `friction` 중 하나 |
| `priority` | string | N | `P0`, `P1`, `P2` |
| `ga4_event_name` | string/null | Y | GA4 매핑 이름 |
| `is_dashboard_core` | boolean | N | 핵심 KPI 사용 여부 |
| `description` | string | Y | Event 설명 |

### 6.6 `dim_scenario`

시나리오 자체의 메타데이터를 관리한다. 같은 시나리오를 여러 번 실행할 수 있으므로 실행 단위는 §6.7의 `dim_simulation_run`으로 분리한다. `persona-schema.md`의 `scenario` 구조와 같은 grain이다.

```text
grain = scenario_id
source = persona-schema.md scenario
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `scenario_id` | string | N | 시나리오 ID. 예: `normal_day`, `sale_burst` |
| `scenario_name` | string/null | Y | 표시명 |
| `description` | string/null | Y | 시나리오 설명 |
| `traffic_pattern` | string/null | Y | 평시, 급증, 감쇠 등 트래픽 형태 |
| `recommendation_policy` | string/null | Y | 기본 추천/기획전 정책. 예: `skin_match_v0` |
| `created_at` | timestamp/null | Y | 생성 시각 |
| `updated_at` | timestamp/null | Y | Dimension 갱신 시각 |

`scenario_id`는 트래픽/프로모션/상황 조건이다. 추천 로직 자체를 뜻하는 값은 `recommendation_policy` 또는 Event의 `properties.algorithm`으로 기록한다.

### 6.7 `dim_simulation_run`

시뮬레이션 실행 1회의 메타데이터를 관리한다. `persona-schema.md`의 `simulation_run`과 같은 grain이며, Dashboard의 표본/버전 필터가 이 Dimension을 통해 이루어진다.

```text
grain = simulation_run_id
source = persona-schema.md simulation_run
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `simulation_run_id` | string | N | 시뮬레이션 실행 ID |
| `scenario_id` | string | N | 시나리오 ID. `dim_scenario` Join key |
| `source` | string | Y | MVP 기준 `simulator` |
| `generator_type` | string/null | Y | `python_batch`, `agent_llm` 등 synthetic 생성 방식 |
| `persona_source` | string/null | Y | `batch_sample`, `agent_sample`. Dashboard 모집단 필터 기준 |
| `started_at` | timestamp | Y | 실행 시작 시각 |
| `ended_at` | timestamp | Y | 실행 종료 시각 |
| `persona_count` | bigint/null | Y | 실행 대상 Persona 수 |
| `event_count` | bigint/null | Y | 실행 Event 수 |
| `seed` | int/null | Y | 재현용 난수 seed |
| `persona_profile_version` | string/null | Y | 사용한 Persona `profile_version` |
| `product_feature_version` | string/null | Y | 사용한 Product Vector `vocab_version` |
| `affinity_version` | string/null | Y | 사용한 Attribute Affinity 버전 |
| `recommendation_policy` | string/null | Y | 실제 실행에 사용한 추천 정책 버전 |
| `event_schema_version` | string/null | Y | 생성 Event의 `schema_version` |
| `note` | string/null | Y | 실행 조건 메모 |

주의사항:

- **`persona_source`는 Event payload에 넣지 않는다.** Persona 정적 속성을 Event마다 반복 저장하면 값이 어긋날 위험이 있으므로, Mart의 `simulation_run_id`로 이 Dimension을 Join해 필터한다.

```text
product_daily_kpi / funnel_daily_kpi / persona_segment_daily_kpi / scenario_daily_kpi
→ simulation_run_id
→ dim_simulation_run
→ persona_source = 'batch_sample'
```

- Dashboard 모집단 통계 기본값은 `persona_source='batch_sample'`이다. agent 100명은 분포가 의도적으로 왜곡된 표본이라 무보정 합산을 금지한다.
- 한 run 안의 Persona는 모두 같은 `persona_source`여야 이 필터가 성립한다. 섞어야 하면 run을 나누거나 `persona_source='mixed'`로 두고 `analysis_weight` 정의 후에만 합산한다.
- 실제 Web Event는 `simulation_run_id=NULL`이므로 이 Dimension의 대상이 아니다. `actor_type='user'`로 먼저 분리한다.
- version 컬럼은 E2E에서 NULL이어도 동작한다. 운영/실험 비교 단계에서는 "왜 지난 run과 결과가 다른가"를 추적하기 위해 채운다.

## 7. Fact / Mart 초안

### 7.1 `product_daily_kpi`

상품별 노출, 클릭, 상세 조회, 장바구니, 구매 성과를 Dashboard에서 조회하기 위한 일간 Mart다.

```text
grain = event_date_kst + product_id + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact, persona_behavior_feature_delta, dim_product
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | `dim_product` Join 스냅샷 |
| `brand_id` | string/null | `dim_product` Join 스냅샷 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `product_impression_count` | bigint | 상품 노출 수 |
| `product_click_count` | bigint | 상품 클릭 수 |
| `quick_look_count` | bigint | 목록/기획전 상품 요약 창 열림 수 |
| `product_view_count` | bigint | 상품 상세 조회 수 |
| `add_to_cart_count` | bigint | 장바구니 담기 Event 수 |
| `remove_from_cart_count` | bigint | 장바구니 제거 Event 수 |
| `purchase_count` | bigint | 상품별 구매 주문 수. `count(distinct order_id)` 기준 |
| `purchase_quantity` | bigint | 구매 수량 합계. `sum(purchase_quantity)` 또는 `sum(quantity)` |
| `quick_look_sessions` | bigint | 요약 창을 연 세션 수 |
| `product_view_sessions` | bigint | 상품 상세 조회 세션 수 |
| `add_to_cart_sessions` | bigint | 장바구니 담기 세션 수 |
| `remove_from_cart_sessions` | bigint | 장바구니 제거 세션 수 |
| `purchase_sessions` | bigint | 구매 완료 세션 수 |
| `revenue_amount` | decimal(18,2)/null | 상품별 매출 합계. `sum(item_revenue)` 기준 |
| `currency` | string/null | 통화 |
| `product_ctr` | double/null | `product_click_count / product_impression_count` |
| `detail_entry_rate` | double/null | `product_view_count / product_impression_count` |
| `add_to_cart_rate` | double/null | `add_to_cart_sessions / product_view_sessions` |
| `purchase_rate` | double/null | `purchase_sessions / product_view_sessions` |
| `product_interest_score` | double/null | Event weight 기반 상품 관심도 |
| `unique_user_count` | bigint | `user_id` 기준. 실제 user_id가 없으면 synthetic 중심 |
| `session_count` | bigint | 관련 세션 수 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- `view_cart`는 product_id가 없는 Event이므로 이 Mart의 상품 단위 집계 대상에서 제외한다.
- `quick_look`은 상품 대상 Event이므로 상품 관심도와 상세 진입 전 관심 신호에 반영한다.
- `product_view_count`와 `product_view_sessions`를 구분해서 쓴다. 상세 → 장바구니 → 뒤로가기로 같은 상세에 돌아오면 새 `page_view_id`가 발급되고 `product_view`가 한 건 더 나가므로, `product_view_count`는 화면이 그려진 횟수이고 `product_view_sessions`가 실제로 본 사람 수에 가깝다. **`add_to_cart_rate`, `purchase_rate`의 분모는 이미 `product_view_sessions`이며 그대로 유지한다.** `product_view_count`를 분모로 바꾸면 장바구니를 자주 여닫는 사용자일수록 전환율이 낮게 나온다. `detail_entry_rate`는 분자가 `product_view_count`라 같은 이유로 부풀 수 있으므로, 발표용 지표로는 `product_view_sessions / product_impression_count` 쪽을 병기한다.
- `remove_from_cart`는 `add_to_cart` 과대평가를 보정하는 부정/망설임 신호로 집계한다.
- `purchase`, `begin_checkout`의 `items[]`는 `product_event_fact`에서 `items explode` 후 상품별 row로 집계한다.
- `order_value`는 주문 전체 금액이므로 상품 row에서 직접 합산하지 않는다. 상품별 매출은 `item_revenue`만 합산한다.
- `revenue_amount`는 `event_name='purchase'`인 row의 `item_revenue`만 합산한다. 장바구니/Checkout 단계의 금액은 잠재 금액으로 별도 해석한다.
- `product_daily_kpi`는 실제 Event 발생일인 `event_date_kst` 기준의 상품 일간 성과 Mart다. Funnel 전환/이탈은 최초 Funnel 진입일 기준인 `funnel_daily_kpi`에서 별도로 계산한다.
- `add_to_cart_rate`, `purchase_rate`를 이 Mart에서 제공할 경우 같은 `event_date_kst` 안의 상품별 세션 지표로만 해석한다. 단계 순서 기반 Funnel 전환율은 `funnel_daily_kpi`를 우선 사용한다.
- `product_interest_score`는 `persona_behavior_feature_delta.final_weight`를 상품/일자 grain으로 먼저 집계한 뒤 Join한다.
- `category_id`, `brand_id`는 Raw Event가 아니라 `dim_product` Join으로 보강한다.

### 7.2 `recommendation_daily_kpi`

추천 영역의 노출, 클릭, 위치별 CTR을 계산하는 Mart다. 상세 페이지 추천처럼 추천이 특정 상품 화면 안에서 발생하면 `context_product_id`로 배경 상품을 함께 볼 수 있다.

```text
grain = event_date_kst + recommendation_id + list_id + algorithm + product_id + context_product_id + position + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `recommendation_id` | string | 추천 영역/실험 ID |
| `algorithm` | string | 추천 알고리즘 또는 룰 ID |
| `list_id` | string/null | 추천 목록 ID |
| `product_id` | string | 추천된 상품 ID |
| `context_product_id` | string/null | 추천이 발생한 배경 상품 ID. 목록/기획전처럼 컨텍스트가 없으면 NULL |
| `position` | int | 추천 목록 내 위치 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `recommendation_impression_count` | bigint | 추천 노출 수 |
| `recommendation_click_count` | bigint | 추천 클릭 수 |
| `recommendation_ctr` | double/null | `recommendation_click_count / recommendation_impression_count` |
| `unique_session_count` | bigint | 추천을 본 세션 수 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- `algorithm`은 Raw 계약에 존재하므로 DW에서도 보존한다.
- `list_id`는 추천 목록/영역이 섞이지 않도록 grain에 포함한다.
- `section_id`는 추천 위치 해석에 도움이 되지만 필수 grain은 아니다.
- `promo_pick` 리스트에서 발생한 `recommendation_impression/click`도 같은 Mart에 포함한다.
- top-level `product_id`는 추천 대상 상품이고, `context_product_id`는 그 추천이 노출된 상품 화면이다.

### 7.3 `search_daily_kpi`

검색량과 검색 이후 상품 클릭 전환을 계산하는 Mart다.

```text
grain = event_date_kst + search_query_hash + actor_type + source + scenario_id + simulation_run_id
input = search_event_fact, product_event_fact
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `search_query_hash` | string | 검색어 hash. 원문 저장 정책에 따라 필수 |
| `normalized_query` | string/null | 정규화 검색어. 원문 보관 허용 시에만 사용 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `search_count` | bigint | 검색 Event 수 |
| `search_session_count` | bigint | 검색 세션 수 |
| `avg_result_count` | double/null | 평균 검색 결과 수 |
| `zero_result_count` | bigint | 결과 0건 검색 수 |
| `search_click_session_count` | bigint | 검색 후 상품 클릭이 발생한 세션 수 |
| `search_to_click_rate` | double/null | `search_click_session_count / search_session_count` |
| `clicked_product_count` | bigint | 검색 후 클릭된 상품 종류 수 |
| `top_clicked_product_id` | string/null | 최다 클릭 상품 ID |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- Raw `search` Event의 검색어 필드는 `query_text`이고, Processed에서는 `search_query`로 정규화한다.
- `search_event_fact`는 검색 Event 자체만 담고, 검색 후 상품 클릭은 `product_event_fact.search_id`로 연결한다. 검색 하나 뒤 여러 상품 클릭이 발생해도 클릭 row는 `product_event_fact`에 여러 건으로 남는다.
- `search_query_hash`는 `normalized_query`가 있으면 이를 기준으로, 없으면 최소 정규화한 `search_query`를 기준으로 생성한다.
- `result_count`는 Raw에서 optional이므로 `avg_result_count`는 NULL 가능하다.
- 검색 화면 구현 전까지 이 Mart는 provisional이다.

### 7.4 `content_daily_kpi`

성분, 리뷰, 상세 설명 등 콘텐츠 관심도를 계산하는 Mart다.

```text
grain = event_date_kst + product_id + section_id + content_kind + actor_type + source + scenario_id + simulation_run_id
input = content_interest_fact, section_dwell_agg, funnel_session_fact
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | `dim_product` Join 스냅샷 |
| `brand_id` | string/null | `dim_product` Join 스냅샷 |
| `section_id` | string/null | 화면 섹션. Raw에서 `content_kind`만 있는 정상 Event면 NULL 가능 |
| `content_kind` | string/null | 콘텐츠 종류 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `section_view_count` | bigint | 섹션 노출/진입 수 |
| `section_view_sessions` | bigint | 섹션 진입 세션 수 |
| `dwell_ms_sum` | bigint | `section_dwell.dwell_ms` delta 합계 |
| `avg_dwell_ms_per_session` | double/null | `dwell_ms_sum / section_view_sessions` |
| `accordion_expand_count` | bigint | 아코디언 펼침 수 |
| `text_selection_count` | bigint | 텍스트 선택 수 |
| `text_copy_count` | bigint | 텍스트 복사 수 |
| `matched_ingredient_count` | bigint | 매칭된 성분 언급 수 |
| `ingredient_view_sessions` | bigint | 성분 관련 섹션/콘텐츠 열람 세션 수 |
| `review_view_sessions` | bigint | 리뷰 관련 섹션/콘텐츠 열람 세션 수 |
| `product_view_sessions` | bigint | 상품 상세 조회 세션 수 |
| `ingredient_view_rate` | double/null | `ingredient_view_sessions / product_view_sessions` |
| `review_view_rate` | double/null | `review_view_sessions / product_view_sessions` |
| `content_interest_score` | double/null | 체류/열람/선택/복사 가중합 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- `content_ref` 단위 상세 분석이 필요하면 별도 상세 Mart를 추가한다. 기본 Dashboard Mart의 grain에는 포함하지 않는다.
- `section_dwell.dwell_ms`는 누적값이 아니라 구간값(delta)으로 합산한다.
- `content_daily_kpi.dwell_ms_sum`의 기본 Source는 `content_interest_fact.dwell_ms_sum`으로 둔다. `section_dwell_agg`는 상세 검증 또는 재집계용 Source로 사용하며, 두 값을 동시에 합산하지 않는다.
- 입력 Dataset인 `content_interest_fact`, `section_dwell_agg`는 `event_date_kst`, `actor_type`, `source`를 보존해야 한다.

### 7.5 `funnel_daily_kpi`

상품별 Funnel 단계 도달과 이탈률을 계산하는 Mart다.

```text
grain = event_date_kst + product_id + actor_type + source + scenario_id + simulation_run_id
input = funnel_session_fact
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일. `funnel_session_fact.funnel_date_kst`에서 파생 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | `dim_product` Join 스냅샷 |
| `brand_id` | string/null | `dim_product` Join 스냅샷 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `impression_sessions` | bigint | 상품 노출 도달 세션 |
| `quick_look_sessions` | bigint | 상품 노출 후 Quick Look을 사용한 세션 |
| `quick_look_cart_sessions` | bigint | Quick Look 사용 후 장바구니에 도달한 세션 |
| `direct_click_sessions` | bigint | Quick Look 없이 상품을 클릭한 세션 |
| `direct_click_cart_sessions` | bigint | Quick Look 없이 상품 클릭 후 장바구니에 도달한 세션 |
| `click_sessions` | bigint | 상품 클릭 도달 세션 |
| `product_view_sessions` | bigint | 상세 조회 도달 세션 |
| `information_view_sessions` | bigint | 성분/리뷰 등 정보 확인 도달 세션 |
| `add_to_cart_sessions` | bigint | 장바구니 도달 세션 |
| `checkout_sessions` | bigint | 결제 시작 도달 세션 |
| `purchase_sessions` | bigint | 구매 완료 도달 세션 |
| `impression_to_click_rate` | double/null | `click_sessions / impression_sessions` |
| `click_to_view_rate` | double/null | `product_view_sessions / click_sessions` |
| `view_to_information_rate` | double/null | `information_view_sessions / product_view_sessions` |
| `view_to_cart_rate` | double/null | `add_to_cart_sessions / product_view_sessions` |
| `cart_to_purchase_rate` | double/null | `purchase_sessions / add_to_cart_sessions` |
| `view_to_purchase_rate` | double/null | `purchase_sessions / product_view_sessions` |
| `dropoff_after_impression_rate` | double/null | `1 - click_sessions / impression_sessions` |
| `dropoff_after_view_rate` | double/null | `1 - add_to_cart_sessions / product_view_sessions` |
| `dropoff_after_cart_rate` | double/null | `1 - purchase_sessions / add_to_cart_sessions` |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- Funnel 산식은 Event 수보다 세션 수를 우선 사용한다.
- `funnel_date_kst`는 최초 non-null Funnel 단계 시각 기준이다.
- 상세 이탈률은 `product_view_sessions` 이후 관심/전환 Event가 없는 세션 기준으로 별도 파생할 수 있다.
- Quick Look 지표는 Funnel 단계가 아니라 `product_impression` 이후 비교 분기다. 기능 존치 판단에는 `actor_type='user'`의 arm별 표본 수와 장바구니 전환율을 함께 제시한다.
### 7.6 `persona_segment_daily_kpi`

피부 타입, 피부 톤, 리뷰 활동량 등 Persona segment별 상품 반응을 계산하는 Mart다. segment 종류는 `bridge_persona_segment`의 `segment_type` 목록을 그대로 따른다.

```text
grain = event_date_kst + segment_type + segment_value + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = funnel_session_fact, persona_behavior_feature_delta, bridge_persona_segment, dim_persona_segment, dim_product
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `segment_type` | string | segment 종류 |
| `segment_value` | string | segment 값 |
| `product_id` | string | 상품 ID |
| `category_id` | string/null | `dim_product` Join 스냅샷 |
| `brand_id` | string/null | `dim_product` Join 스냅샷 |
| `actor_type` | string | 실제/합성 구분 |
| `source` | string | Event 원천 |
| `generator_type` | string/null | synthetic 생성 방식 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `segment_user_count` | bigint | 해당 segment 사용자/Persona 수 |
| `session_count` | bigint | 세션 수 |
| `product_view_sessions` | bigint | 상세 조회 세션 수 |
| `add_to_cart_sessions` | bigint | 장바구니 세션 수 |
| `purchase_sessions` | bigint | 구매 세션 수 |
| `avg_interest_score` | double/null | 평균 상품 관심도 |
| `category_interest_score` | double/null | 카테고리 관심도 |
| `affinity_lift` | double/null | segment별 평균 대비 반응 lift |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- 실제 Web Event에서 segment 원천이 없으면 이 Mart는 synthetic 중심으로 먼저 만든다.
- Persona와 segment는 `bridge_persona_segment`를 통해 연결한다.
- 약 100명의 실시간 agent 로그와 9,900명의 Python 생성 로그를 함께 볼 경우 `generator_type`, `simulation_run_id`로 분리한다. 표본 기준 필터는 `simulation_run_id → dim_simulation_run.persona_source`를 사용하며 기본값은 `batch_sample`이다.
- `segment_type='concern'`은 현재 Persona 원천에 고민 필드가 없어 생성되지 않는다. 고민 축 분석은 상품 속성인 `dim_product.concern_tags` 기준으로만 가능하다.
- 이 Mart의 `affinity_lift`는 **행동 로그에서 계산한 값**이다. `batch/ingest/data/affinity_lift.csv`(리뷰 구성비 기반, 추천 입력)와 이름은 같지만 원천과 의미가 다르므로 같은 지표로 비교하지 않는다.

### 7.7 `scenario_daily_kpi`

시나리오별 행동 차이와 시뮬레이션 실행별 결과를 비교하는 Mart다.

```text
grain = event_date_kst + scenario_id + simulation_run_id + actor_type + source + generator_type
input = cleaned_events, product_event_fact, funnel_session_fact, content_interest_fact, persona_behavior_feature_delta
```

| column | type | 설명 |
| --- | --- | --- |
| `event_date_kst` | date | 집계일 |
| `scenario_id` | string | 시나리오 ID |
| `simulation_run_id` | string | 실행 ID |
| `actor_type` | string | 대부분 `synthetic` |
| `source` | string | MVP 기준 `simulator` |
| `generator_type` | string/null | synthetic 생성 방식 |
| `event_count` | bigint | 전체 Event 수 |
| `session_count` | bigint | 세션 수 |
| `persona_count` | bigint | 참여 Persona 수 |
| `product_view_count` | bigint | 상품 상세 조회 수 |
| `add_to_cart_count` | bigint | 장바구니 수 |
| `purchase_count` | bigint | 구매 주문 수. 가능하면 `count(distinct order_id)` 기준 |
| `avg_event_count_per_session` | double/null | 세션당 평균 Event 수 |
| `avg_product_interest_score` | double/null | 평균 상품 관심도 |
| `avg_content_interest_score` | double/null | 평균 콘텐츠 관심도 |
| `view_to_cart_rate` | double/null | 상품 조회 후 장바구니 전환율 |
| `view_to_purchase_rate` | double/null | 상품 조회 후 구매 전환율 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- 실제 Web Event는 `scenario_id`, `simulation_run_id`가 NULL일 수 있으므로 이 Mart의 주 대상은 synthetic 실행이다.
- 시나리오 표시명/설명은 `dim_scenario`, 실행 조건(`persona_source`, seed, version)은 `dim_simulation_run`에서 Join한다. 같은 `scenario_id`를 여러 run으로 돌린 결과 비교가 이 Mart의 기본 사용 방식이다.

### 7.8 `realtime_event_stats`

실시간 정상 Event 수집 상태, TPS, 지연시간을 확인하는 운영/검증용 Mart다.

```text
grain = event_minute_kst + event_name + source + actor_type + scenario_id + simulation_run_id
input = cleaned_events
```

| column | type | 설명 |
| --- | --- | --- |
| `event_minute_kst` | timestamp | KST 기준 minute truncate |
| `event_name` | string | Event 이름 |
| `source` | string | Event 원천 |
| `actor_type` | string | 실제/합성 구분 |
| `scenario_id` | string/null | 시나리오 ID |
| `simulation_run_id` | string/null | 실행 ID |
| `event_count` | bigint | 정상 Event 수 |
| `unique_session_count` | bigint | 세션 수 |
| `avg_ingest_latency_ms` | double/null | `received_at - event_time` 평균 |
| `p95_ingest_latency_ms` | double/null | `received_at - event_time` p95 |
| `avg_processing_lag_ms` | double/null | `processed_at - received_at` 평균 |
| `p95_processing_lag_ms` | double/null | `processed_at - received_at` p95 |
| `events_per_second` | double/null | 분당 Event 수 / 60 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- Backend가 batch 단위로 받더라도 Spark 초입에서는 Event 단위로 explode한 뒤 집계한다.

### 7.9 `realtime_bad_event_stats`

Spark에서 확인 가능한 bad event를 별도로 집계하는 운영/검증용 Mart다. Collector가 Kafka 전송 전에 거부한 Event는 Spark가 직접 볼 수 없으므로, 별도 bad-event topic/storage가 없으면 이 Mart에 포함되지 않는다.

```text
grain = event_minute_kst + error_stage + error_code + event_name + source + actor_type
input = bad_events
```

| column | type | 설명 |
| --- | --- | --- |
| `event_minute_kst` | timestamp | KST 기준 minute truncate |
| `error_stage` | string | `collector_validation`, `spark_type_normalization`, `spark_semantic_validation` |
| `error_code` | string | 실패 유형 |
| `event_name` | string/null | 파싱 가능한 경우의 Event 이름 |
| `source` | string/null | 파생 가능한 경우의 Event 원천 |
| `actor_type` | string/null | 파싱 가능한 경우의 actor type |
| `bad_event_count` | bigint | 격리된 Event 수 |
| `mart_processed_at` | timestamp | Mart 갱신 시각 |

주의사항:

- Collector reject를 DW에서 함께 보려면 Backend가 reject Event를 별도 topic/storage에 남겨야 한다.
- MVP에서는 Spark가 확인 가능한 bad event만 DW `bad_event_count`로 집계하고, Collector reject는 Backend metric으로 별도 관리할 수 있다.

## 8. Dashboard 화면별 Mart 연결

| Dashboard 화면 | 주요 질문 | 사용 Mart/Dimension |
| --- | --- | --- |
| Overview | 전체 방문/상품 조회/장바구니/구매 추이와 핵심 KPI는 어떤가 | `product_daily_kpi`, `funnel_daily_kpi`, `realtime_event_stats`, `realtime_bad_event_stats` |
| 상품 분석 | 어떤 상품이 관심과 전환을 많이 얻는가 | `product_daily_kpi`, `recommendation_daily_kpi`, `dim_product` |
| 사용자 행동 분석 | 사용자가 어느 단계에서 이탈하는가 | `funnel_daily_kpi`, `realtime_event_stats` |
| 리뷰 분석 | 리뷰 콘텐츠 관심도와 자극/트러블 관련 반응은 어떤가 | `content_daily_kpi`, `dim_product` |
| 성분 분석 | 성분 정보가 얼마나 열람되고 어떤 상품에서 관심이 높은가 | `content_daily_kpi`, `dim_product` |
| Persona/Scenario 분석 | 고객군/시나리오별 행동 차이는 어떤가 | `persona_segment_daily_kpi`, `scenario_daily_kpi`, `dim_persona_segment`, `dim_scenario`, `dim_simulation_run` |

## 9. KPI 산식

모든 비율 산식은 아래 규칙을 따른다.

```text
rate = numerator / NULLIF(denominator, 0)
```

| KPI | 산식 | 기본 Mart |
| --- | --- | --- |
| 상품 CTR | `product_click_count / product_impression_count` | `product_daily_kpi` |
| 추천 CTR | `recommendation_click_count / recommendation_impression_count` | `recommendation_daily_kpi` |
| 상세 진입률 | `product_view_count / product_impression_count` | `product_daily_kpi` |
| 장바구니 전환율 | `add_to_cart_sessions / product_view_sessions` | `funnel_daily_kpi` |
| 구매 전환율 | `purchase_sessions / product_view_sessions` | `funnel_daily_kpi` |
| 장바구니→구매 전환율 | `purchase_sessions / add_to_cart_sessions` | `funnel_daily_kpi` |
| 성분 정보 열람률 | `ingredient_view_sessions / product_view_sessions` | `content_daily_kpi` |
| 리뷰 정보 열람률 | `review_view_sessions / product_view_sessions` | `content_daily_kpi` |
| 단계별 이탈률 | `1 - next_step_sessions / current_step_sessions` | `funnel_daily_kpi` |
| 검색→상품 클릭 전환율 | `search_click_session_count / search_session_count` | `search_daily_kpi` |
| 평균 섹션 체류시간 | `dwell_ms_sum / section_view_sessions` | `content_daily_kpi` |
| 상품별 관심도 | Event weight, 체류, 정보 열람, 장바구니, 구매의 가중합 | `product_daily_kpi`, `content_daily_kpi` |

## 10. Raw/Processed와 DW 연결 주의사항

| 주의사항 | 영향 | 대응 |
| --- | --- | --- |
| Kafka key 기준 | 현재 구현처럼 `session_id`를 partition key로 사용 | Web Event의 `persona_id`가 null일 수 있으므로 `session_id` 유지 |
| Raw 중복 직접 집계 | Raw는 at-least-once 수신 원본이라 같은 `event_id`가 여러 건 있을 수 있음 | KPI, Fact, Mart 산식에는 Raw를 직접 넣지 않고 `cleaned_events` 또는 그 파생 Dataset만 사용 |
| 대표 Event 선정 기준 불일치 | Processed와 DW 재처리 결과가 달라질 수 있음 | 동일 `event_id`는 `received_at ASC`, `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 기준으로 선택한 1건만 DW 입력으로 사용 |
| source fallback 필요 | 현재 Raw에는 `source`가 있으나 과거 Raw/누락 Event 처리 시 source별 Mart가 흔들릴 수 있음 | Kafka payload 값을 우선 사용하고, 누락 시 `actor_type=synthetic → simulator`, 그 외 → `web`으로 fallback 파생. 서버 내부 Event는 별도 경로 확인 시 `server` |
| `scenario_id`, `simulation_run_id` 물리 위치 | top-level 필드로 오해하면 E2E 파싱이 어긋날 수 있음 | Raw에서는 `properties.scenario_id`, `properties.simulation_run_id`, Processed/DW에서는 승격 컬럼으로 사용 |
| 서로 다른 grain Fact 직접 Join | COUNT/SUM이 중복되어 KPI가 과대계산될 수 있음 | 각 Processed Dataset을 목표 Mart grain으로 먼저 집계한 뒤 집계 결과끼리 Join |
| `user_id` 원천 불완전 | 실제 Web Event의 사용자 단위 지표가 NULL 가능 | synthetic은 `persona_id → user_id`, 실제 Web은 로그인/익명 ID 정책 확정 전까지 nullable |
| `search_id` 미확정 | 검색 후 클릭 연결이 약해질 수 있음 | 검색 화면 구현 전에는 nullable, 구현 후 Raw 추가 또는 Spark 파생 |
| `search_query_hash` 생성 기준 미확정 | 같은 검색어가 다른 값으로 집계될 수 있음 | 검색 구현 전까지 provisional. 구현 시 normalized query 기준 hash 생성 규칙 확정 |
| `cart_id` 미확정 | 장바구니 단계 추적이 세션 기준으로 제한됨 | 장바구니 구현 후 Raw 추가 여부 결정 |
| `purchase` 금액 optional | 매출 KPI가 일부 NULL 가능 | 상품별 매출은 `event_name='purchase'`인 row의 `item_revenue = quantity * unit_price`로 파생 가능할 때만 집계 |
| `order_value` 상품 row 복제 | explode된 상품 row에서 주문 총액을 합산하면 매출이 N배가 될 수 있음 | `order_value`는 주문 총액 검증용, 상품별 매출은 `item_revenue`만 SUM |
| 상품 속성 원천 | Raw에 `category_id`, `brand_id`가 없을 수 있음 | `dim_product` Join을 기본으로 사용 |
| synthetic/Web 혼합 | 실제 사용자 KPI와 부하 테스트 KPI가 섞일 수 있음 | Dashboard 기본 필터에 `actor_type`, `source`, `simulation_run_id` 포함 |
| Persona segment 연결 누락 | `persona_id`에서 segment로 Join할 수 없음 | `bridge_persona_segment`를 통해 `dim_persona_segment`와 연결 |
| Event에 `persona_source` 없음 | agent 100명/batch 9,900명을 Mart에서 직접 구분할 수 없음 | Event에 추가하지 않고 `simulation_run_id → dim_simulation_run.persona_source`로 필터. 이를 위해 synthetic Event는 `simulation_run_id`가 항상 있어야 한다 |
| Persona 원천에 `concern` 없음 | 존재하지 않는 segment를 Mart가 기대하게 됨 | `segment_type`에서 `concern` 제외. 상품 축 고민 분석은 `dim_product.concern_tags` 사용 |
| synthetic runtime metadata 누락 | `scenario_id`, `simulation_run_id`, `generator_type`이 없으면 실행 단위 Dimension Join이 끊김 | Simulator 생성 시 필수 포함, Spark semantic validation에서 누락 Event를 `invalid_properties`로 격리 |
| Collector reject 관측 불가 | Kafka 전송 전 거부된 Event는 Spark/DW에서 볼 수 없음 | Backend metric으로 관리하거나 별도 bad-event topic/storage가 있을 때만 DW에 포함 |
| 물리 저장소 미정 | 타입, 파티션, 인덱스 전략 확정 불가 | 이 문서에서는 논리 타입만 정의하고 DDL은 작성하지 않음 |

## 11. E2E 전 확인 체크리스트

1. Event 수집 API 경로는 `POST /api/events`로 사용하고, body 형태가 Front/Backend 사이에서 동일한지 확인한다.
2. Kafka message는 백엔드 확정 브랜치 기준 Event 단위다. Spark Raw 적재에서 이 전제를 확인한다.
3. Kafka partition key는 `session_id`를 최종 기준으로 사용한다.
4. 동일 `event_id` 중복 입력 시 `cleaned_events`가 `received_at ASC`, `kafka_topic ASC`, `kafka_partition ASC`, `kafka_offset ASC` 기준 최초 1건만 남기는지 확인한다.
5. DW/Mart 입력이 Raw가 아니라 `cleaned_events` 및 파생 Processed Dataset으로 제한되는지 확인한다.
6. E2E 기준 `schema_version`은 `0.2.0-draft`로 맞추고, `1.0.0-draft` 전환 시 Front/Backend/Spark를 동시에 갱신한다.
7. `session_start`와 세션 첫 `page_view`는 같은 `page_view_id`를 공유하고, 첫 `page_view`는 `properties.navigation_source='session_start'`로 들어오는지 확인한다.
8. `product_view`, `product_impression`, `product_click`, `section_view`, `section_dwell`, `add_to_cart`가 실제 화면에서 들어오는지 확인한다.
9. `search`, `begin_checkout`, `purchase`는 구현 후 Trigger와 required field를 재검증한다.
10. Checkout이 별도 화면이면 `page_type=checkout`을 Backend enum에 추가할지 확인한다.
11. `section_dwell.dwell_ms`가 delta로 들어오고 `content_daily_kpi`에서 이중합산 없이 집계되는지 확인한다.
12. `purchase`, `begin_checkout`의 `items[]`가 `product_event_fact`에서 상품별 row로 explode되는지 확인한다.
13. `category_id`, `brand_id`가 `dim_product` Join으로 보강되는지 확인한다.
14. `bad_events`에서 Collector validation error와 Spark semantic/type error를 구분할 수 있는지 확인한다. Collector reject가 Kafka 전에 끝난다면 Backend metric 또는 별도 저장소 필요 여부를 확인한다.
15. Dashboard 비율 산식에서 분모 0이 `0`이 아니라 `NULL`로 처리되는지 확인한다.
16. 상품별 매출 집계가 `order_value`가 아니라 `event_name='purchase'`의 `item_revenue` 기준으로 계산되는지 확인한다.
17. Collector 필드 정렬 브랜치가 `dev`에 병합되었는지 확인한다. 병합 전에는 `event_name`, `actor_type`, `page_view_id`, `sequence_no`가 Kafka payload에 없다.
18. synthetic Event에 `properties.scenario_id`, `properties.simulation_run_id`, `properties.generator_type`이 모두 들어오는지 확인한다.
19. `dim_simulation_run`에 run별 `persona_source`가 채워지고, Dashboard 기본 필터가 `batch_sample`로 동작하는지 확인한다.
20. `dim_persona_segment`/`bridge_persona_segment`에 `segment_type='concern'` row가 생성되지 않는지 확인한다.

## 12. 후속 문서 분리 기준

| 문서 | 담을 내용 |
| --- | --- |
| `contracts/event-schema.json` | Backend Collector가 검증할 실제 JSON Schema |
| 물리 DW DDL 문서 | 선택한 저장소 기준 파티션, 인덱스, 타입, DDL |
| Dashboard 산식 문서 | 화면별 필터, 기간 비교, 정렬/랭킹 기준 |
| Persona Schema 문서 | `persona-schema.md`로 작성됨. Persona 원천, seed/holdout, segment, simulation run 규칙은 그 문서가 원천이다 |
| Front 구현 문서 | 실제 컴포넌트/훅별 Trigger 위치 |

이 문서는 E2E 테스트 전 Draft다. 다음 주 E2E에서는 구조 실패를 찾기보다 API 경로, 필드명, nullable, Trigger 발생 여부, 집계 grain이 실제 로그와 맞는지를 검증한다.
