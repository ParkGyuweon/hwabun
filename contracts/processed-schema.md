# Processed Dataset Schema 계약

작성일: 2026-09-01
최종 계약 갱신: 2026-09-07
대상 작업: `[DATA] Spark 처리 결과 및 DW 저장 구조 확정`
문서 정리 작업: `[DATA] Analytics 계약 및 설계 문서 구조 정리`
상태: 논리 Schema 확정, 현재 Spark 구현·Delta 물리화·E2E 정합성 검증 대기
설계 설명: [`spark-processing-design.md`](../docs/analytics/spark-processing-design.md)

## 1. 범위와 우선순위

이 문서는 Spark가 Raw Event를 정제·파생해 EC2-2의 Delta Lake에 저장하는
Processed Dataset의 계약 원본이다. 각 Dataset의 grain, key, 컬럼, Spark SQL 타입,
nullable, partition과 입력 관계만 정의한다.

처리 배경, 중복 제거 근거, KPI 산식, 현재 구현 gap과 E2E 계획은
`../docs/analytics/spark-processing-design.md`에서 설명한다. 두 문서가 충돌하면 이
문서를 우선한다.
Dashboard 대상 KPI를 Delta `marts`와 MySQL `dw`에 제공하는 Mart 계약은
[`dw-schema.md`](./dw-schema.md), 적재·조회 설계는
[`dw-design.md`](../docs/analytics/dw-design.md)에서 다룬다.

## 2. 공통 물리 규칙

| 항목 | 계약 |
| --- | --- |
| 기준 저장 엔진 | Delta Lake |
| 저장 위치 | EC2-2 로컬 파일시스템의 Processed Delta root |
| 내부 파일 | Parquet + `_delta_log` |
| Timestamp | Spark SQL `timestamp`, UTC 해석 |
| Dashboard 일자 | `Asia/Seoul` 기준 `event_date_kst` 또는 Dataset별 KST 날짜 |
| Decimal | 금액은 `decimal(18,2)` |
| Boolean | 문자열 대신 `boolean` |
| 배열 | `array<string>` 등 원소 타입 명시 |
| 재실행 | 같은 입력 범위 재실행 시 Dataset key 기준 동일 결과로 수렴 |
| 업무 중복 | `cleaned_events` 생성 전에 `event_id` 정본 1건 선택 |
| Schema 확장 | 신규 컬럼은 nullable 추가를 기본으로 하고 기존 컬럼 의미·타입 변경 금지 |
| 통합몰 귀속 | Event와 Processed Dataset에는 `tenant_id`, `business_id`를 두지 않고 상품 Fact가 `brand_id`를 `dim_product`에서 파생한다 |

환경별 Delta root와 checkpoint URI는 Spark 배포 설정에서 주입한다. Dataset 이름과
하위 경로는 환경이 달라도 유지한다.

### 2.1 `brand_id`, `product_id`

통합 쇼핑몰의 상품 행동은 `product_id → dim_product.brand_id` 순서로 귀속한다.
`brand_id`는 Raw Event가 직접 싣지 않고 상품 Dimension에서 파생해 Fact와 Mart에
Join 시점 스냅샷으로 보존한다.

상품이 없는 플랫폼 공통 Event는 `brand_id=NULL`을 유지한다. route, 표시명, 직전 상품
또는 세션 내 다른 상품으로 귀속을 추정하지 않는다. 대시보드 접근 제어는 Backend가
로그인 계정과 연결된 단일 `brand_id`를 검사해 강제하며 Event partition으로 대신하지 않는다.

## 3. Dataset 카탈로그

| Dataset | Layer | Grain / Unique key | Partition | 현재 `dev` |
| --- | --- | --- | --- | --- |
| `bad_events` | Error | Kafka 물리 좌표 1건 | `bad_recorded_date` | 구현, 목표 컬럼 보완 필요 |
| `duplicate_events` | Audit | 중복 후보 Kafka 물리 좌표 1건 | `event_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `cleaned_events` | Processed Base | `event_id` | `event_date_kst` | 구현, Q3 Dimension 결과는 후속 보강 |
| `sessionized_events` | Processed Base | `event_id` | `event_date_kst` | 구현, 통합몰 세션 순서·seed Dimension 조인 동기화 대기 |
| `product_event_fact` | Processed Fact | `event_id + item_index + product_id` | `event_date_kst` | 구현, seed Dimension Join |
| `review_event_fact` | Processed Fact | `event_id + product_id` | `event_date_kst` | 구현, 리뷰 상세 행동 및 Dimension Join |
| `search_event_fact` | Processed Fact | `event_id` | `event_date_kst` | 미구현 |
| `section_dwell_agg` | Processed Aggregate | section dwell grain | `event_date_kst` | 구현, delta 합산 |
| `content_interest_fact` | Processed Fact | content interest grain | `event_date_kst` | 구현, 산식·가중치 연결 |
| `purchase_fact` | Processed Fact | `order_id + product_id` | `event_date_kst` | 구현 |
| `purchase_reason_fact` | Processed Fact | `order_id + reason` | `event_date_kst` | 구현, 설문 건너뛰기 NULL reason 보존 |
| `funnel_session_fact` | Processed Fact | `session_id + product_id` | `funnel_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `persona_behavior_feature_delta` | Feature Input | `event_id + user_id + product_id` | `event_date_kst` | 미구현 |
| `dim_brand` | Dimension | `brand_id` | 없음 | seed 상품 기준 projection 구현 |
| `dim_product` | Dimension | `product_id` | 없음 | seed 원천과 ACTIVE 등록 상품 union 구현. 등록 상품 `brand_id`는 쇼핑몰 상품 export로 보강 |

`section_dwell_agg`와 `content_interest_fact`의 grain은 다음 컬럼 조합이다.

```text
session_id
+ page_view_id
+ product_id
+ section_id
+ content_kind
+ content_ref
```

Nullable grain 컬럼은 집계할 때 NULL-safe equality를 사용한다. NULL을 임의의 실제
ID로 바꿔 저장하지 않는다.

## 4. `bad_events`

입력은 `raw_events`다. JSON 파싱, 필수값, 타입 또는 semantic validation에 실패한
Kafka record를 원문과 함께 보존한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `kafka_cluster_id` | string | N | Raw 물리 좌표 |
| `kafka_topic` | string | N | Raw 물리 좌표 |
| `kafka_partition` | int | N | Raw 물리 좌표 |
| `kafka_offset` | long | N | Raw 물리 좌표 |
| `kafka_timestamp` | timestamp | N | Kafka metadata |
| `kafka_key` | string | Y | Kafka key |
| `raw_value` | string | Y | Kafka Value 원문 |
| `event_id` | string | Y | 파싱 가능한 경우 |
| `event_name` | string | Y | 파싱 가능한 경우 |
| `schema_version` | string | Y | 파싱 가능한 경우 |
| `request_id` | string | Y | 파싱 가능한 경우 |
| `event_index` | int | Y | 파싱 가능한 경우 |
| `event_time` | timestamp | Y | 파싱 가능한 경우 |
| `received_at` | timestamp | Y | 파싱 가능한 경우 |
| `actor_type` | string | Y | 파싱 가능한 경우 |
| `source` | string | Y | payload 우선, 없으면 fallback |
| `error_stage` | string | N | `spark_type_normalization`, `spark_semantic_validation` 등 |
| `error_code` | string | N | 표준 오류 코드 |
| `error_message` | string | Y | 디버깅용 상세 사유 |
| `bad_recorded_at` | timestamp | N | Spark 판정 시각 |
| `bad_recorded_date` | date | N | `bad_recorded_at`의 UTC 날짜 |

Event별 Properties 위반의 `error_code`와 우선순위는
[`event-properties-schema.md` §7](./event-properties-schema.md#7-semantic-validation)을
따른다. 이 표에서 오류 코드를 다시 정의하지 않는다.

Collector가 Kafka 발행 전에 거절한 요청은 이 Dataset에 들어오지 않는다. 해당 건수는
Backend metric 또는 후속 별도 error sink의 책임이다.

## 5. `duplicate_events`

입력은 유효한 Raw 후보다. 같은 `event_id`에서 정본으로 선택되지 않은 후보를 감사
목적으로 저장한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | 업무 중복 key |
| `canonical_rank` | int | N | 정본 정렬 기준의 후보 순위, 2 이상 |
| `candidate_count` | long | N | 같은 `event_id`의 유효 후보 수 |
| `received_at` | timestamp | N | Collector 수신 시각 |
| `event_date_kst` | date | N | `event_time`의 KST 날짜 |
| `kafka_cluster_id` | string | N | 중복 후보 물리 좌표 |
| `kafka_topic` | string | N | 중복 후보 물리 좌표 |
| `kafka_partition` | int | N | 중복 후보 물리 좌표 |
| `kafka_offset` | long | N | 중복 후보 물리 좌표 |
| `raw_value` | string | Y | 중복 후보 원문 |
| `audit_code` | string | N | `event_id_duplicate` |
| `audited_at` | timestamp | N | 감사 row 생성 시각 |

정본은 `received_at ASC → kafka_topic ASC → kafka_partition ASC → kafka_offset ASC`
순서의 첫 row다. 정본 자체는 `cleaned_events`에서 같은 `event_id`로 조회한다.

## 6. `cleaned_events`

입력은 `raw_events`다. 유효 Event를 타입 정규화하고 `event_id` 기준으로 중복을
제거한 Processed 기준 테이블이다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `schema_version` | string | N | Raw payload |
| `event_name` | string | N | Raw payload |
| `intent` | string | N | Raw payload |
| `event_time` | timestamp | N | `occurred_at` UTC 정규화 |
| `event_date_kst` | date | N | `event_time`의 KST 날짜 |
| `received_at` | timestamp | N | Collector 수신 시각 |
| `processed_at` | timestamp | N | Spark 처리 시각 |
| `latency_ms` | long | N | `received_at - event_time` |
| `processing_lag_ms` | long | N | `processed_at - received_at` |
| `request_id` | string | Y | Collector batch ID |
| `event_index` | int | Y | batch 내부 순서 |
| `source` | string | N | Raw payload 우선, 누락 시 fallback |
| `actor_type` | string | N | `user`, `synthetic` |
| `is_synthetic` | boolean | N | synthetic 판정 결과 |
| `user_id` | string | Y | 분석 식별자. `identity_scope`에 따라 `persona_id` 또는 `account_id` |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `is_seeded` | boolean | N | 생성기가 주입한 시드 Event면 `true` (event-properties-schema.md §3.14). 행동 Mart 집계에서 제외한다 |
| `account_id` | string | Y | Collector가 JWT `sub`에서 뽑은 값. 비로그인·synthetic은 NULL |
| `persona_id` | string | Y | synthetic 필수, Web NULL 허용 |
| `scenario_id` | string | Y | synthetic 필수 |
| `simulation_run_id` | string | Y | synthetic 필수 |
| `generator_type` | string | Y | synthetic 필수 |
| `session_id` | string | N | 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID |
| `sequence_no` | int | N | Front 발생 순서 |
| `page_type` | string | N | 화면 유형 |
| `environment` | string | N | 실행 환경 |
| `product_id` | string | Y | 상품 대상 Event 필수 |
| `category_id` | string | Y | `dim_product` Join 결과 |
| `brand_id` | string | Y | `dim_product` Join 결과 |
| `section_id` | string | Y | properties 승격 |
| `content_kind` | string | Y | properties 승격 |
| `position` | int | Y | properties 승격 |
| `properties_json` | string | N | properties 원문 JSON |
| `quality_flags` | array<string> | N | 품질 표시, 없으면 빈 배열 |
| `raw_candidate_count` | long | N | 같은 `event_id` 유효 후보 수 |
| `kafka_cluster_id` | string | N | 선택된 정본 물리 좌표 |
| `kafka_topic` | string | N | 선택된 정본 물리 좌표 |
| `kafka_partition` | int | N | 선택된 정본 물리 좌표 |
| `kafka_offset` | long | N | 선택된 정본 물리 좌표 |
| `kafka_timestamp` | timestamp | N | 선택된 정본 Kafka 시각 |
| `kafka_key` | string | Y | 선택된 정본 Kafka key |
| `raw_ingested_at` | timestamp | N | 선택된 Raw 적재 시각 |
| `raw_value` | string | Y | 선택된 Kafka Value 원문 |

### 6.1 분석 식별자

`user_id`는 세 갈래 중 하나에서 온다. 어느 축에서 왔는지는 `identity_scope`가 말한다.

| `identity_scope` | 조건 | `user_id` |
| --- | --- | --- |
| `persona` | `actor_type=synthetic` | `persona_id` |
| `account` | `account_id`가 비어 있지 않음 | `account_id` |
| `session` | 그 외 | NULL. `session_id`로만 분석한다 |

`account_id`는 Front가 아니라 Collector가 JWT `sub`에서 뽑아 넣는다. 두 곳에서 채우면
어긋났을 때 어느 쪽이 맞는지 알 수 없기 때문이다.

합성 로그에 `account_id`가 실려 오면 페르소나 축과 계정 축이 한 row에서 섞이므로
`invalid_identity_scope`로 격리한다.

브랜드 담당자·운영자 트래픽은 Front가 회원 토큰만 실어 원천에서 제외한다. Event에
계정 롤을 두지 않으므로 DATA는 이를 사후에 가려낼 수 없다.

`is_seeded`는 `properties.seeded`가 `true`인지로 판정한다
([`event-properties-schema.md` §3.14](./event-properties-schema.md)). 시드 Event는
생성기가 Persona의 사전 선호를 추천기에 주입하려고 만든 것이라 관측된 행동이 아니다.
`cleaned_events`에는 그대로 보존하고 행동 Mart 집계에서 제외한다. 어느 Mart가 제외
대상인지는 [`dw-schema.md`](./dw-schema.md)가 정본이다.

시드 Event의 `session_id`는 `seed:{simulation_run_id}:{persona_id}:{product_id}`
형식이라 세션 네임스페이스로도 갈라지지만 판정에는 쓰지 않는다. 그쪽은 파생이고
생성기가 먼저 찍는 표식이 `properties.seeded`다.

`actor_type=user`에 `seeded`가 실려 오면 실사용자 행동에 주입 표식이 섞인 것이므로
`invalid_seed_scope`로 격리한다.

## 7. `sessionized_events`

입력은 `cleaned_events`다. grain과 unique key는 `event_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `event_date_kst` | date | N | Partition |
| `session_id` | string | N | 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `is_seeded` | boolean | N | 생성기가 주입한 시드 Event면 `true` (event-properties-schema.md §3.14). 행동 Mart 집계에서 제외한다 |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `product_id` | string | Y | 대상 상품 |
| `context_product_id` | string | Y | 배경 상품 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `event_name` | string | N | Event 이름 |
| `event_time` | timestamp | N | 발생 시각 |
| `received_at` | timestamp | N | 수신 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `sequence_no` | int | N | Front 발생 순서 |
| `event_order` | int | N | Spark 복원 순서 |
| `prev_event_name` | string | Y | 이전 Event |
| `next_event_name` | string | Y | 다음 Event |
| `is_late_event` | boolean | Y | Batch 구현에서는 NULL, watermark 도입 시 판정 |
| `has_sequence_gap` | boolean | N | sequence gap 여부 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |
| `environment` | string | N | 실행 환경 |
| `properties_json` | string | N | properties 원문 JSON |

세션 정렬은 통합몰의 `session_id` 경계 안에서
`sequence_no → event_time → received_at → event_id` 순으로 수행한다.
`session_id`는 통합몰 전체에서 충돌하지 않는 ID여야 한다.

## 8. `product_event_fact`

입력은 `cleaned_events`다. 단일 상품 Event는 `item_index=0`, `items[]` Event는
상품별로 explode한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Grain |
| `item_index` | int | N | Grain |
| `product_id` | string | N | Grain |
| `event_date` | date | N | UTC 발생일 |
| `event_hour` | timestamp | N | UTC hour |
| `event_date_kst` | date | N | Partition |
| `event_hour_kst` | timestamp | N | KST hour |
| `event_time` | timestamp | N | 발생 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `event_name` | string | N | Event 이름 |
| `intent` | string | N | Event 의미 |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `is_seeded` | boolean | N | 생성기가 주입한 시드 Event면 `true` (event-properties-schema.md §3.14). 행동 Mart 집계에서 제외한다 |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `session_id` | string | N | 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID |
| `context_product_id` | string | Y | 배경 상품 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `sku_id` | string | Y | 상품 옵션 |
| `list_id` | string | Y | 목록 ID |
| `entry_source` | string | Y | 진입 경로 |
| `recommendation_id` | string | Y | 추천 식별자 |
| `algorithm` | string | Y | 추천 알고리즘 |
| `search_id` | string | Y | 검색 연결 ID |
| `section_id` | string | Y | 섹션 ID |
| `position` | int | Y | 목록 위치 |
| `banner_type` | string | Y | 배너 축 enum. 배너 Event에서 필수 |
| `banner_value` | string | Y | 어휘집 원문. `new_brand` 배너만 NULL |
| `banner_slot` | int | Y | 추천 API `slot`을 Event 발행 시 변환한 양의 정수 |
| `trait_source` | string | Y | `session`, `profile`, `coldstart`, `explore` |
| `policy_version` | string | Y | 배너·정렬 정책 귀속 버전 |
| `quantity` | int | Y | 수량 |
| `purchase_quantity` | int | Y | Checkout/구매 item 수량 |
| `cart_size_after` | int | Y | 변경 후 장바구니 크기 |
| `unit_price` | decimal(18,2) | Y | 상품 단가 |
| `order_value` | decimal(18,2) | Y | 전환 시점 주문 표시 금액. 매출·정산 합산 금지 |
| `item_revenue` | decimal(18,2) | Y | 행동 분석용 `quantity * unit_price`. 매출·정산 합산 금지 |
| `cart_value` | decimal(18,2) | Y | 장바구니 금액 |
| `currency` | string | Y | 통화 |
| `cart_id` | string | Y | 장바구니 ID |
| `order_id` | string | Y | 주문 ID |
| `variants_viewed` | int | Y | Quick Look 옵션 조회 수 |
| `added_to_cart` | boolean | Y | Quick Look 장바구니 행동 |
| `wishlisted` | boolean | Y | Quick Look 찜 행동 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

## 9. `purchase_fact`

입력은 `cleaned_events`의 `purchase` Event다. `items[]`를 상품 단위로 explode한다.
unique key는 `order_id + product_id`다.

일간 Mart만으로는 "두 번째 구매"를 셀 수 없다. 집계 과정에서 사용자 축이 사라지기
때문이다. 이 Dataset은 사용자·주문·상품을 함께 보존해 재구매 분석의 입력이 된다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `order_id` | string | N | Grain |
| `product_id` | string | N | Grain |
| `event_id` | string | N | 원천 `purchase` Event |
| `event_date_kst` | date | N | Partition |
| `event_time` | timestamp | N | 주문 완료 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `is_seeded` | boolean | N | 생성기가 주입한 시드 Event면 `true` (event-properties-schema.md §3.14). 행동 Mart 집계에서 제외한다 |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `session_id` | string | N | 세션 ID |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `sku_id` | string | Y | `items[].sku_id` |
| `quantity` | int | N | `items[].quantity` |
| `unit_price` | decimal(18,2) | N | `items[].unit_price` |
| `item_revenue` | decimal(18,2) | N | `quantity * unit_price` 파생 |
| `order_value` | decimal(18,2) | Y | 주문 전체 금액. 상품 row에서 합산 금지 |
| `currency` | string | Y | 통화 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

`item_revenue`는 Event가 운반하지 않고 여기서 파생한다. `order_value`는 주문 단위
값이므로 explode된 상품 row를 합산하면 상품 수만큼 중복된다. 두 금액은
행동 분석용이며, 매출·정산은 Backend PAID 주문 상품 Fact만 사용한다.

같은 `order_id`가 여러 번 수신되면 `cleaned_events` 단계에서 이미 `event_id` 정본
1건으로 정리된다. 이 Dataset에서 다시 중복 제거하지 않는다.

## 10. `purchase_reason_fact`

입력은 `cleaned_events`의 `purchase_reason_select` Event다. `reasons[]`를 이유
단위로 explode하며 unique key는 `order_id + reason`이다.

건너뛴 응답은 `reasons`가 빈 배열이라 explode 결과가 없다. 응답률을 세려면 row가
없는 주문도 알아야 하므로, 건너뛴 주문은 `reason = NULL`, `skipped = true`인 row
1건으로 보존한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `order_id` | string | N | Grain |
| `reason` | string | Y | Grain. `reasons[]` 원소. 건너뛰면 NULL |
| `event_id` | string | N | 원천 Event |
| `event_date_kst` | date | N | Partition |
| `event_time` | timestamp | N | 응답 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `is_seeded` | boolean | N | 생성기가 주입한 시드 Event면 `true` (event-properties-schema.md §3.14). 행동 Mart 집계에서 제외한다 |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `session_id` | string | N | 세션 ID |
| `is_primary` | boolean | N | `primary_reason`과 일치하는지 |
| `reason_rank` | int | Y | `reasons[]` 내 순서, 1부터 |
| `free_text_kind` | string | Y | 자유 입력 분류값. 원문은 저장하지 않는다 |
| `skipped` | boolean | N | 설문 건너뛰기 여부 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

Grain이 `order_id + reason`이므로 NULL-safe equality를 사용한다. 한 주문에서 같은
이유가 두 번 선택되는 경우는 없다고 보고, 들어오면 품질 표시 대상이다.

선언한 이유와 행동에서 추론한 관심을 대조하는 집계는 Mart 단계에서 수행한다.
이 Dataset은 선언 쪽 입력만 보존한다.

### 10.1 `review_event_fact`

입력은 `cleaned_events`의 리뷰 상세 행동이다. unique key는
`event_id + product_id`다. `review_expand`는 `target`이 `review_text` 또는
`jump_to_reviews`인 Event만 포함하며 `target=ingredients`는 리뷰 Fact에서 제외한다.
`section_view`와 `section_dwell`은 `section_id=reviews` 또는 `content_kind`가
`user_review`, `review_stats`, `review_filter`일 때 포함한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Grain |
| `product_id` | string | N | Grain |
| `event_date_kst` | date | N | Partition |
| `event_time`, `processed_at` | timestamp | N | 발생·처리 시각 |
| `event_name`, `intent` | string | N | 리뷰 행동 Event와 의미 |
| `user_id`, `persona_id` | string | Y | 분석 사용자·Persona |
| `scenario_id`, `simulation_run_id`, `generator_type` | string | Y | synthetic 실행 축 |
| `session_id`, `page_view_id` | string | N | 세션·페이지 방문 ID |
| `category_id`, `brand_id` | string | Y | 상품 Dimension 스냅샷 |
| `section_id`, `content_kind` | string | Y | 리뷰 영역 분류 |
| `review_id` | string | Y | 펼친 리뷰 식별자 |
| `target` | string | Y | `review_text`, `jump_to_reviews` |
| `revealed_count` | int | Y | 펼침으로 추가 노출된 리뷰 수 |
| `filter`, `sort` | string | Y | 적용한 필터 또는 정렬 |
| `result_count` | int | Y | 적용 후 결과 수 |
| `persona_skin_type`, `persona_skin_tone` | string | Y | 필터 적용 시점 Persona 조건 |
| `dwell_ms` | long | Y | 리뷰 영역 체류 Event 값 |
| `actor_type`, `source` | string | N | 사용자 유형·유입 경로 |

추천 행동은 별도 중복 Dataset을 만들지 않고 §8 `product_event_fact`의
`recommendation_impression`, `recommendation_click` 행을 정본으로 사용한다.
두 Event의 `recommendation_id`, `list_id`, `algorithm`, `position`은 검증 Job에서
필수값으로 검사한다.

## 11. `search_event_fact`

입력은 `cleaned_events`의 `search` Event이며 unique key는 `event_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `event_date_kst` | date | N | Partition |
| `search_id` | string | Y | 검색 1회 ID |
| `event_time` | timestamp | N | 검색 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `session_id` | string | N | 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID |
| `search_query` | string | Y | 정규화 검색어, 원문 정책 적용 |
| `search_query_hash` | string | Y | 정규화 검색어 hash |
| `result_count` | int | Y | 검색 결과 수 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

## 12. `section_dwell_agg`

입력은 `cleaned_events`의 `section_dwell` Event다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | Partition |
| `session_id` | string | N | Grain |
| `page_view_id` | string | N | Grain |
| `product_id` | string | Y | Grain |
| `section_id` | string | Y | Grain |
| `content_kind` | string | Y | Grain |
| `content_ref` | string | Y | Grain |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `dwell_ms_sum` | long | N | delta `dwell_ms` 합계 |
| `dwell_event_count` | long | N | 합산 Event 수 |
| `max_co_visible_blocks` | int | Y | 동시 노출 블록 최댓값 |
| `first_seen_at` | timestamp | N | 최초 dwell 시각 |
| `last_seen_at` | timestamp | N | 마지막 dwell 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

## 13. `content_interest_fact`

입력은 `cleaned_events`와 `section_dwell_agg`다. grain은 §3의 content interest
조합이다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | Partition |
| `session_id` | string | N | Grain |
| `page_view_id` | string | N | Grain |
| `product_id` | string | Y | Grain |
| `section_id` | string | Y | Grain |
| `content_kind` | string | Y | Grain |
| `content_ref` | string | Y | Grain |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `view_count` | long | N | section/content 조회 수 |
| `dwell_ms_sum` | long | N | 체류시간 합계 |
| `accordion_expand_count` | long | N | 펼침 수 |
| `review_filter_count` | long | N | 리뷰 필터 수 |
| `text_select_count` | long | N | 텍스트 선택 수 |
| `text_copy_count` | long | N | 텍스트 복사 수 |
| `matched_ingredients` | array<string> | N | 매칭 성분, 없으면 빈 배열 |
| `matched_keywords` | array<string> | N | 매칭 키워드, 없으면 빈 배열 |
| `vocab_version` | string | Y | 어휘집 버전 |
| `quality_flags` | array<string> | N | 섹션 가중치 기본값 적용 등 품질 표시 |
| `content_interest_score` | double | N | §13.1 산식 결과 |
| `processed_at` | timestamp | N | 처리 시각 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

### 13.1 `content_interest_score` 산식

```text
content_interest_score
  = SECTION_DWELL_WEIGHT[section_id]
    x ( ln(1 + dwell_ms_sum / 1000)
        + Σ EVENT_WEIGHT[event_name] x 해당 Event 발생 수 )
```

행동 가중치 `EVENT_WEIGHT`와 섹션 가중치 `SECTION_DWELL_WEIGHT`의 실행 원본은
`frontend/src/types/log.ts`다. 이 계약에 숫자를 복제하지 않는다.
`batch/jobs/behavior_weights.py`가 그 파일을 직접 파싱하므로 Front가 값을 고치면
집계도 따라간다.

체류시간에 `ln(1 + x)`를 쓰는 이유는 선형 합산이면 오래 켜 둔 탭 하나가 다른 모든
행동을 압도하기 때문이다. 초 단위로 환산한 뒤 로그를 취해 긴 체류의 기여를 눌러 둔다.

집계 대상 Event는 이 grain에서 관측되는 것으로 한정한다 — `accordion_toggle`,
`review_filter_apply`, `text_selection`, `text_copy`. `remove_from_cart`처럼 음수
가중치를 가진 Event는 콘텐츠 grain에 속하지 않으므로 여기 들어오지 않는다.

`section_id`가 NULL이면 섹션 가중치를 곱할 수 없다. 이 경우 가중치 `1.0`을 사용하고
`quality_flags`에 표시한다. 임의의 섹션으로 추정해 채우지 않는다.

점수는 정규화하지 않은 절대값이다. Mart에서 브랜드 간 비교에 쓸 때는 분모를 함께
제시해야 한다. 조회 수가 많은 상품이 자동으로 높은 점수를 받기 때문이다.

## 14. `funnel_session_fact`

입력은 `sessionized_events`와 `product_event_fact`다. unique key는
`session_id + product_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `funnel_date_kst` | date | N | 최초 non-null Funnel 단계의 KST 날짜 |
| `session_id` | string | N | Unique key |
| `product_id` | string | N | Unique key |
| `user_id` | string | Y | 분석 사용자 ID |
| `identity_scope` | string | N | `persona`, `account`, `session` |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |
| `first_impression_at` | timestamp | Y | 최초 노출 |
| `first_quick_look_at` | timestamp | Y | 최초 Quick Look |
| `first_click_at` | timestamp | Y | 최초 클릭 |
| `first_product_view_at` | timestamp | Y | 최초 상세 조회 |
| `first_information_view_at` | timestamp | Y | 최초 정보 확인 |
| `first_add_to_cart_at` | timestamp | Y | 최초 장바구니 |
| `first_checkout_at` | timestamp | Y | 최초 Checkout |
| `first_purchase_at` | timestamp | Y | 최초 구매 |
| `reached_impression` | boolean | N | 노출 도달 |
| `reached_quick_look` | boolean | N | Quick Look 도달 |
| `quick_look_close_reason` | string | Y | 마지막 닫힘 사유 (미구현) |
| `quick_look_dwell_ms` | long | Y | Quick Look 체류 합계 (미구현) |
| `quick_look_variants_viewed` | int | Y | 선택한 옵션 수 최댓값 (미구현) |
| `reached_click` | boolean | N | 클릭 도달 |
| `reached_detail_view` | boolean | N | 상세 조회 도달. `reached_product_view` 또는 `reached_quick_look` |
| `detail_entry_path` | string | Y | 상세를 연 경로. `quick_look`, `direct_click`. 상세를 안 열었으면 NULL |
| `reached_product_view` | boolean | N | 상품 상세 조회 도달 |
| `reached_information_view` | boolean | N | 정보 확인 도달 |
| `reached_add_to_cart` | boolean | N | 장바구니 도달 |
| `reached_checkout` | boolean | N | Checkout 도달 |
| `reached_purchase` | boolean | N | 구매 도달 |
| `dropoff_step` | string | Y | 마지막 도달 후 이탈 단계 |
| `processed_at` | timestamp | N | 처리 시각 |

Quick Look은 목록에서 상세를 여는 화면 동선이라 퍼널 단계로 센다. 거기서 바로
장바구니에 담을 수 있어서 빼면 담기 세션이 상세 조회 세션보다 많아진다.
`dropoff_step`은 `purchase → checkout → add_to_cart → information_view →
product_view → quick_look → click → impression` 순으로 마지막 도달 단계를 고른다.

`detail_entry_path`는 상세를 **어느 경로로 열었는지**를 세션·상품마다 하나만 고른다.
Quick Look과 상품 상세를 둘 다 열었으면 `first_quick_look_at`과
`first_product_view_at`을 비교해 **먼저 일어난 쪽**으로 귀속한다. 한 컬럼에 한 값이라
두 경로가 겹쳐 세어질 수 없다. `reached_quick_look`은 이와 별개로 "Quick Look을
썼나"라서 두 경로 모두에서 참일 수 있다.

`quick_look_close_reason`·`quick_look_dwell_ms`·`quick_look_variants_viewed`는 아직
만들지 않는다. 닫힘 사유와 체류는 `quick_look_close` Event에 있으므로 필요해지면
같은 Fact에 붙인다.

## 15. `persona_behavior_feature_delta`

입력은 상품과 연결되는 `cleaned_events`다. unique key는
`event_id + user_id + product_id`다. `user_id`가 NULL인 Web Event는 사용자 Feature
갱신 대상에서 제외한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `event_date_kst` | date | N | Partition |
| `user_id` | string | N | Feature 대상 사용자 |
| `product_id` | string | N | Feature 대상 상품 |
| `persona_id` | string | Y | Persona ID |
| `scenario_id` | string | Y | synthetic 실행 축 |
| `simulation_run_id` | string | Y | synthetic 실행 축 |
| `generator_type` | string | Y | synthetic 생성 방식 |
| `category_id` | string | Y | 상품 Dimension |
| `brand_id` | string | Y | 상품 Dimension |
| `event_name` | string | N | Event 이름 |
| `event_time` | timestamp | N | 발생 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `event_weight` | double | N | 행동 가중치 |
| `decay_weight` | double | N | 시간 감쇠 |
| `final_weight` | double | N | `event_weight * decay_weight` |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

가중치 값과 Product/User Vector 결합 방식은
`../docs/analytics/spark-processing-design.md` 및 추천 계약을 따른다. 이 Dataset은
Vector 자체를 저장하지 않는다.

## 16. `dim_brand`

`dim_brand`는 브랜드 조회와 `dim_product.brand_id` 참조 무결성의 기준 Dimension이다.
unique key는 `brand_id`이며 partition하지 않는다. 브랜드 계정과의 1:1 인증 매핑은
Backend가 소유하고 분석 DW에 복제하지 않는다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `brand_id` | string | N | Unique key |
| `brand_name` | string | N | 브랜드 표시명 |
| `created_at` | timestamp | Y | 원천에서 제공할 때의 브랜드 등록 시각 |
| `updated_at` | timestamp | N | Dimension 생성·갱신 시각 |

## 17. `dim_product`

`dim_product`는 Processed Fact의 상품 속성 보강 입력이다. unique key는
`product_id`이며 partition하지 않는다.

Sephora 원천 카탈로그와 입점 브랜드가 직접 등록한 상품을 **같은 Dimension에 둔다.** Fact가
`product_id`로 Join하는데 Dimension을 나누면 모든 소비자가 두 번 Join해 합쳐야 하고,
합치는 규칙이 소비자마다 갈린다. 출처는 `product_source` 컬럼으로 구분한다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `product_id` | string | N | Unique key |
| `product_name` | string | N | 상품명 |
| `product_source` | string | N | `seed_catalog`, `brand_registered` |
| `brand_id` | string | N | 브랜드 ID |
| `brand_name` | string | N | 브랜드명 |
| `category_id` | string | N | 카테고리 ID |
| `category_name` | string | N | 카테고리명 |
| `secondary_category` | string | Y | 어휘 8종. Product Feature 인코딩 축 |
| `tertiary_category` | string | Y | 어휘 19종. Product Feature 인코딩 축 |
| `base_price` | decimal(18,2) | N | 기준 가격 |
| `currency` | string | N | 통화 |
| `price_krw` | decimal(18,2) | Y | 입점 브랜드 입력 가격. 등록 상품만 |
| `skin_type_tags` | array<string> | N | 피부 타입 태그 |
| `concern_tags` | array<string> | N | 고민 태그 |
| `ingredient_ids` | array<string> | N | 성분 ID 목록 |
| `caution_ingredient_count` | int | N | 주의 성분 수 |
| `rating` | double | Y | 평균 평점 |
| `rating_source` | string | N | `observed`, `injected` |
| `loves_count` | bigint | Y | 관심 수 |
| `registered_at` | timestamp | Y | 등록 시각. 등록 상품만 |
| `updated_at` | timestamp | N | 상품 속성 갱신 시각 |

`rating_source`가 필요한 이유는 등록 상품의 `rating`이 실측이 아니라 카테고리 중앙값을
주입한 값이기 때문이다([`product-registration-spec.md`](./product-registration-spec.md) §4.2).
Dashboard가 두 값을 섞어 "평균 평점"으로 보여주면 신규 상품이 실제로 좋은 평가를 받은
것처럼 읽힌다. 리뷰가 쌓이면 `observed`로 바뀐다.

`product_source`는 상품이 seed 카탈로그에서 왔는지 입점 브랜드 등록에서 왔는지를
구분한다. 모든 판매 상품은 `brand_id`가 필수이며 유효한 `dim_brand.brand_id`를
참조한다.

## 18. 구현 정합성 완료 조건

2026-09-07 통합몰 귀속 계약과 브랜드 Dimension Join 구현을 반영했다.
아래 조건은 물리 구현·E2E 완료 판정 기준이다.

1. 각 Delta Table의 실제 `printSchema()`가 이 문서의 컬럼·타입·nullable과 일치한다.
2. §3의 unique key 중복이 0건이다.
3. Partition column이 NULL인 row가 0건이다.
4. `cleaned_events.event_id` 중복이 0건이고 비정본은 `duplicate_events`에서
   추적된다.
5. synthetic row는 `persona_id`, `scenario_id`, `simulation_run_id`,
   `generator_type`이 NULL이 아니다.
6. `source`는 Raw payload 값을 우선하며 fallback 사용 건수를 품질 지표로 확인한다.
7. 상품 Dimension Join 전후 row 수가 의도하지 않게 증가하지 않는다.
8. 같은 입력 범위 재실행 후 Dataset key와 집계값이 변하지 않는다.
9. 현재 미구현 Dataset은 구현 전까지 소비자가 존재하는 것으로 가정하지 않는다.
10. 상품 대상 Event의 `product_id`는 NULL이 아니며 Dimension에서 `brand_id`를
    파생할 수 있다.
11. 플랫폼 공통 Event의 브랜드 귀속을 임의로 추정하지 않는다.
12. `dim_product.rating_source`가 `injected`인 row는 Dashboard 평균 평점 집계에서
     제외하거나 별도로 표시한다.
13. `dim_product.product_source`가 `brand_registered`인 row는 유효한 `brand_id`를
    가지며 해당 브랜드는 `dim_brand`에 존재한다.
