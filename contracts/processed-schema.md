# Processed Dataset Schema 계약

작성일: 2026-09-01
최종 정적 검증: 2026-09-02
대상 Jira: `[DATA] Spark 처리 결과 및 DW 저장 구조 확정`
문서 정리 Jira: `[DATA] Analytics 계약 및 설계 문서 구조 정리`
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
| Tenant 격리 | 모든 Dataset은 `tenant_id`를 보유하고 소비자는 이 값으로만 격리한다 |

환경별 Delta root와 checkpoint URI는 Spark 배포 설정에서 주입한다. Dataset 이름과
하위 경로는 환경이 달라도 유지한다.

### 2.1 `tenant_id`와 `brand_id`

두 값은 뜻이 다르므로 서로 대체하지 않는다.

| 컬럼 | 뜻 | 원천 |
| --- | --- | --- |
| `tenant_id` | 그 Event가 발생한 Storefront의 소유 Tenant | Raw Envelope에서 승격 |
| `brand_id` | 그 Event가 대상으로 한 상품의 브랜드 | `product_id` → `dim_product` Join 파생 |

격리, partition, Mart 집계 key는 `tenant_id`만 사용한다. `brand_id`는 상품 속성이며
`page_view`처럼 상품이 없는 Event에서는 NULL이다.

`schema_version = 0.2.0-draft` Event에는 `tenant_id`가 없다. 이 경우 컬럼은 NULL이며
Tenant 격리가 필요한 소비자는 해당 row를 제외한다. 값을 임의로 추정해 채우지 않는다.

## 3. Dataset 카탈로그

| Dataset | Layer | Grain / Unique key | Partition | 현재 `dev` |
| --- | --- | --- | --- | --- |
| `bad_events` | Error | Kafka 물리 좌표 1건 | `bad_recorded_date` | 구현, 목표 컬럼 보완 필요 |
| `duplicate_events` | Audit | 중복 후보 Kafka 물리 좌표 1건 | `event_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `cleaned_events` | Processed Base | `event_id` | `event_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `sessionized_events` | Processed Base | `event_id` | `event_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `product_event_fact` | Processed Fact | `event_id + item_index + product_id` | `event_date_kst` | 구현, Dimension Join 필요 |
| `search_event_fact` | Processed Fact | `event_id` | `event_date_kst` | 미구현 |
| `section_dwell_agg` | Processed Aggregate | section dwell grain | `event_date_kst` | 미구현 |
| `content_interest_fact` | Processed Fact | content interest grain | `event_date_kst` | 미구현 |
| `funnel_session_fact` | Processed Fact | `session_id + product_id` | `funnel_date_kst` | 구현, 목표 컬럼 보완 필요 |
| `persona_behavior_feature_delta` | Feature Input | `event_id + user_id + product_id` | `event_date_kst` | 미구현 |
| `dim_product` | Dimension | `product_id` | 없음 | 원천·Join 구현 대기 |

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
| `tenant_id` | string | Y | Storefront 소유 Tenant. `0.2.0-draft` Event는 NULL |
| `actor_type` | string | N | `user`, `synthetic` |
| `is_synthetic` | boolean | N | synthetic 판정 결과 |
| `user_id` | string | Y | synthetic이면 `persona_id`; Web 정책 확정 전 NULL |
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

## 7. `sessionized_events`

입력은 `cleaned_events`다. grain과 unique key는 `event_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `event_date_kst` | date | N | Partition |
| `session_id` | string | N | 세션 ID |
| `page_view_id` | string | N | 페이지 방문 ID |
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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

세션 정렬은 `session_id` 안에서 `sequence_no → event_time → received_at → event_id`
순으로 수행한다.

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
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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
| `quantity` | int | Y | 수량 |
| `purchase_quantity` | int | Y | Checkout/구매 item 수량 |
| `cart_size_after` | int | Y | 변경 후 장바구니 크기 |
| `unit_price` | decimal(18,2) | Y | 상품 단가 |
| `order_value` | decimal(18,2) | Y | 주문 전체 금액, 상품 매출 합산 금지 |
| `item_revenue` | decimal(18,2) | Y | 구매 row의 `quantity * unit_price` |
| `cart_value` | decimal(18,2) | Y | 장바구니 금액 |
| `currency` | string | Y | 통화 |
| `cart_id` | string | Y | 장바구니 ID |
| `order_id` | string | Y | 주문 ID |
| `variants_viewed` | int | Y | Quick Look 옵션 조회 수 |
| `added_to_cart` | boolean | Y | Quick Look 장바구니 행동 |
| `wishlisted` | boolean | Y | Quick Look 찜 행동 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

## 9. `search_event_fact`

입력은 `cleaned_events`의 `search` Event이며 unique key는 `event_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `event_id` | string | N | Unique key |
| `event_date_kst` | date | N | Partition |
| `search_id` | string | Y | 검색 1회 ID |
| `event_time` | timestamp | N | 검색 시각 |
| `processed_at` | timestamp | N | 처리 시각 |
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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

## 10. `section_dwell_agg`

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
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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

## 11. `content_interest_fact`

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
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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
| `content_interest_score` | double | N | 확정 산식 결과 |
| `processed_at` | timestamp | N | 처리 시각 |
| `actor_type` | string | N | 사용자 유형 |
| `source` | string | N | 유입 경로 |

## 12. `funnel_session_fact`

입력은 `sessionized_events`와 `product_event_fact`다. unique key는
`session_id + product_id`다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `funnel_date_kst` | date | N | 최초 non-null Funnel 단계의 KST 날짜 |
| `session_id` | string | N | Unique key |
| `product_id` | string | N | Unique key |
| `tenant_id` | string | Y | Storefront 소유 Tenant |
| `user_id` | string | Y | 분석 사용자 ID |
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
| `used_quick_look` | boolean | N | Quick Look 사용 |
| `quick_look_close_reason` | string | Y | 마지막 닫힘 사유 |
| `quick_look_dwell_ms` | long | Y | Quick Look 체류 합계 |
| `quick_look_variants_viewed` | int | Y | 선택한 옵션 수 최댓값 |
| `reached_click` | boolean | N | 클릭 도달 |
| `reached_product_view` | boolean | N | 상세 조회 도달 |
| `reached_information_view` | boolean | N | 정보 확인 도달 |
| `reached_add_to_cart` | boolean | N | 장바구니 도달 |
| `reached_checkout` | boolean | N | Checkout 도달 |
| `reached_purchase` | boolean | N | 구매 도달 |
| `dropoff_step` | string | Y | 마지막 도달 후 이탈 단계 |
| `processed_at` | timestamp | N | 처리 시각 |

## 13. `persona_behavior_feature_delta`

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

## 14. `dim_product`

`dim_product`는 Processed Fact의 상품 속성 보강 입력이다. unique key는
`product_id`이며 partition하지 않는다.

| column | type | nullable | source / rule |
| --- | --- | --- | --- |
| `product_id` | string | N | Unique key |
| `product_name` | string | N | 상품명 |
| `brand_id` | string | N | 브랜드 ID |
| `brand_name` | string | N | 브랜드명 |
| `category_id` | string | N | 카테고리 ID |
| `category_name` | string | N | 카테고리명 |
| `base_price` | decimal(18,2) | N | 기준 가격 |
| `currency` | string | N | 통화 |
| `skin_type_tags` | array<string> | N | 피부 타입 태그 |
| `concern_tags` | array<string> | N | 고민 태그 |
| `ingredient_ids` | array<string> | N | 성분 ID 목록 |
| `caution_ingredient_count` | int | N | 주의 성분 수 |
| `updated_at` | timestamp | N | 상품 속성 갱신 시각 |

## 15. 구현 정합성 완료 조건

2026-09-02 기준 최신 Raw/Event/Persona 계약과 현재 `streaming/` 구현을 정적으로
대조했다. Dataset의 grain, key, partition, 컬럼과 nullable에 새 논리 변경은
필요하지 않았다. 아래 조건은 논리 Schema 작성 완료 조건이 아니라, 구현 결과가 이
계약을 충족했다고 판정하기 위한 물리 구현·E2E 완료 조건이다.

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
10. `schema_version = 0.3.0-draft` row는 `tenant_id`가 NULL이 아니다.
11. `tenant_id`와 `brand_id`가 같은 값을 담지 않는다. 후자는 상품 Dimension 파생이다.
