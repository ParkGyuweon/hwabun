# Raw Event Dataset 계약

작성일: 2026-09-02

상태: Draft, Delta 구현·E2E 검증 대기

설계 설명: [`../docs/analytics/raw-event-storage-design.md`](../docs/analytics/raw-event-storage-design.md)

## 1. 범위와 입력 계약

이 문서는 Kafka record를 원본 그대로 보존하는 Raw Dataset `raw_events`의 grain,
물리 key, 컬럼, 타입, nullable, partition과 보존 규칙을 정의하는 계약 원본이다.

Kafka Value의 공통 Envelope와 Event enum은 [`event-schema.json`](./event-schema.json),
Event별 properties와 enum은
[`event-properties-schema.md`](./event-properties-schema.md)를 따른다. 이 문서는 그
입력 계약을 복제하거나 변경하지 않는다.

Collector가 HTTP 단계에서 거절해 Kafka에 발행하지 않은 요청은 Raw 저장 범위가
아니다. Kafka에 도달한 record는 JSON 파싱이나 semantic validation에 실패해도 Raw에
보존한다.

## 2. Dataset grain과 key

| 항목 | 계약 |
| --- | --- |
| Dataset | `raw_events` |
| Grain | Kafka record 1건 |
| 물리 unique key | `kafka_cluster_id + kafka_topic + kafka_partition + kafka_offset` |
| 업무 Event key | `event_id`; Raw unique key가 아니며 중복 허용 |
| 쓰기 의미 | insert-only, `event_id` dedup 미수행 |
| 원본 기준 | `raw_value`와 Kafka 물리 좌표 |
| Partition | `raw_ingest_date`, UTC |

같은 `event_id`가 서로 다른 Kafka 좌표로 수신되면 모두 저장한다. 동일 Topic을 삭제한
뒤 재생성해 offset이 재사용될 수 있으면 `kafka_cluster_id`를 새 세대 값으로 바꾸거나
저장 경로를 분리해야 한다.

## 3. 컬럼 계약

### 3.1 Kafka metadata와 원문

| Column | Type | Nullable | 설명 |
| --- | --- | --- | --- |
| `kafka_cluster_id` | string | N | Kafka cluster 또는 Topic 세대 식별자 |
| `kafka_topic` | string | N | Kafka Topic |
| `kafka_partition` | int | N | Kafka Partition |
| `kafka_offset` | long | N | Partition 내 Offset |
| `kafka_timestamp` | timestamp | N | Kafka record timestamp |
| `kafka_timestamp_type` | int | N | Kafka timestamp type |
| `kafka_key` | string | Y | Kafka message key. 현재 Collector 기준 `session_id` |
| `raw_value` | string | Y | Kafka Value 원문 JSON. 원본 보존의 최종 기준 |
| `is_json_parseable` | boolean | N | `raw_value`를 공통 Event 구조로 파싱할 수 있는지 |

Kafka tombstone이나 비정상 record도 좌표를 잃지 않도록 `raw_value`는 nullable이다.
`raw_value`가 NULL이거나 JSON 파싱에 실패해도 Raw row는 제거하지 않는다.

### 3.2 Payload 조회 projection

| Column | Type | Nullable | Raw 원천 | 설명 |
| --- | --- | --- | --- | --- |
| `schema_version` | string | Y | `schema_version` | Event Schema 버전 |
| `event_id` | string | Y | `event_id` | 업무 Event 식별자 |
| `event_name` | string | Y | `event_name` | Event 이름 |
| `intent` | string | Y | `intent` | Event 의미 분류 |
| `event_time` | timestamp | Y | `occurred_at` | RFC 3339 값을 UTC timestamp로 정규화 |
| `received_at` | timestamp | Y | `received_at` | Collector 수신 시각을 UTC로 정규화 |
| `source` | string | Y | `source` | Collector가 기록한 유입 경로 |
| `persona_id` | string | Y | `persona_id` | Persona ID |
| `session_id` | string | Y | `session_id` | 세션 ID |
| `page_view_id` | string | Y | `page_view_id` | 페이지 방문 ID |
| `sequence_no` | int | Y | `sequence_no` | 세션 내 Event 순서 |
| `page_type` | string | Y | `page_type` | 화면 유형 |
| `product_id` | string | Y | `product_id` | Event 대상 상품 ID |
| `tenant_id` | string | Y | `tenant_id` | Storefront 소유 Tenant. `0.3.0-draft`부터 필수 |
| `actor_type` | string | Y | `actor_type` | `user`, `synthetic` |
| `environment` | string | Y | `environment` | 실행 환경 |
| `request_id` | string | Y | `request_id` | Collector batch 요청 ID |
| `event_index` | int | Y | `event_index` | Batch 내부 Event 순서 |
| `properties_json` | string | Y | `properties` | Event별 properties 조회용 JSON 문자열 |

조회 projection은 비정상 payload도 row로 보존하기 위해 모두 nullable이다. required
field, enum과 timestamp 원문 검증은 Processed 단계가 담당한다. `occurred_at`은
`event_time`, `properties`는 `properties_json`으로 정규화하지만 원형은 반드시
`raw_value`에 남아야 한다.

### 3.3 Raw 적재 metadata

| Column | Type | Nullable | 설명 |
| --- | --- | --- | --- |
| `raw_ingested_at` | timestamp | N | Raw row를 생성한 UTC 시각 |
| `raw_ingest_date` | date | N | `raw_ingested_at`의 UTC 날짜, partition column |

## 4. 원본 보존 규칙

1. `raw_value`는 Kafka Value를 UTF-8 문자열로 변환한 값이며 일부를 제거하거나 다시
   직렬화하지 않는다.
2. `properties_json`은 조회용이다. 공백과 key 순서를 포함한 정확한 원문은
   `raw_value`를 기준으로 한다.
3. JSON 파싱 실패, 필수 필드 누락과 enum 오류가 있어도 Raw row는 보존한다.
4. 같은 `event_id`가 여러 번 들어와도 Raw에서 제거하지 않는다.
5. Raw를 update하거나 overwrite하지 않는다. 정제 결과는 Processed Dataset에 쓴다.
6. Kafka payload에 새 필드가 추가되어도 전체 JSON은 `raw_value`에 보존한다.

## 5. 중복과 오류 처리 경계

| 단계 | 기준 | 처리 |
| --- | --- | --- |
| Raw Q1 | Kafka record | 물리 key 기반 insert-only 적재, `event_id` dedup 없음 |
| Processed Q2 좌표 방어 | Raw 물리 key | 같은 좌표가 반복되면 대표 1건 선택 |
| Processed Q2 업무 dedup | `event_id` | 정본 1건을 `cleaned_events`에 저장 |
| Processed Q2 감사 | 정본이 아닌 유효 후보 | `duplicate_events`에 저장 |
| Processed Q2 오류 | 파싱·필수값·semantic validation 실패 | `bad_events`에 원문과 Kafka 좌표 저장 |

동일 `event_id`의 정본 선정 순서는 다음과 같다.

```text
received_at ASC
→ kafka_topic ASC
→ kafka_partition ASC
→ kafka_offset ASC
```

Fact, Mart와 Dashboard는 Raw를 직접 집계하지 않고 `cleaned_events` 또는 그 파생
Dataset만 사용한다. Processed Dataset의 상세 계약은
[`processed-schema.md`](./processed-schema.md)를 따른다.

## 6. Schema 호환 규칙

- 조회 projection에 컬럼을 추가할 때는 기존 row에 값이 없음을 고려해 nullable하게
  확장한다.
- 필드 이름·타입·의미 변경은 기존 Raw를 덮어쓰지 않고 `schema_version`으로 구분한다.
- 알 수 없는 신규 필드나 projection 파싱 실패 때문에 Kafka record를 버리지 않는다.
- 계약 변경 시 실제 Delta Schema와 컬럼 drift 검증을 함께 갱신한다.

## 7. 계약 검증 조건

1. Kafka record 1건이 Raw row 1건으로 저장된다.
2. Kafka Value와 `raw_value`가 같고 Topic·Partition·Offset·Key가 함께 저장된다.
3. 조회 projection의 컬럼 이름·타입·nullable이 §3과 일치한다.
4. 같은 `event_id`의 서로 다른 Kafka record가 모두 보존된다.
5. JSON 파싱 실패 record도 `raw_value`와 Kafka 좌표를 가진다.
6. 같은 물리 key가 Replay로 다시 들어와도 Raw row가 중복되지 않는다.
7. `raw_ingest_date`가 UTC 기준이며 NULL이 아니다.
