# Raw Event Log 저장 구조

작성일: 2026-09-01  
대상 Jira: `[DATA] Raw Event Log 저장 구성`  
상태: Raw Event 계약·목표 projection·Delta Lake 저장 구조 확정, 구현 검증 대기

## 1. 목적

Collector가 Kafka에 발행한 Event를 손실 없이 저장하고, 원본 재조회와 재처리가
가능한 Raw Dataset `raw_events`의 저장 구조를 정의한다.

이 문서는 이미 확정된 **Kafka Raw Event Schema 18개 필드**를 변경하거나 다시
합의하기 위한 문서가 아니다. 확정된 payload를 어떤 물리 컬럼과 출처 metadata로
보존할지 정의하고, 현재 Spark Q1 구현과의 정합성을 기록한다.

Raw는 분석용 정제 테이블이 아니다. Kafka에 도달한 record는 JSON 파싱 또는 Spark
semantic validation에 실패하더라도 삭제하지 않고, 같은 `event_id`로 재전송된
Event도 Kafka 원문과 수신 좌표를 모두 보존한다. 반면 Collector가 HTTP 400으로
거절해 Kafka에 발행하지 않은 요청은 Raw 저장 경계에 들어오지 않는다.

## 2. 확정된 입력 계약과 저장 경로

```text
Frontend / Simulator
→ POST /api/events
→ Backend Collector
→ Kafka activity-events
→ Spark Structured Streaming Q1
→ Delta Lake raw_events (EC2-2 목표 구조)
→ Delta Lake cleaned_events / marts
→ MySQL dw KPI Mart
→ Dashboard
```

서비스와 데이터 처리는 두 EC2로 분리한다. EC2-1은 Backend, MySQL의 `app`·`dw`
스키마 및 Redis를 실행하고, EC2-2는 Kafka, Spark 및 Delta Lake를 실행한다. Delta
Lake는 Raw·Processed·Mart의 기준 저장 계층이며, MySQL `dw`에는 Dashboard가 직접
조회할 KPI Mart만 선별 적재한다.

별도 S3, EBS 데이터 볼륨 또는 공유 파일시스템이 없으므로 Delta Table의 Parquet
파일과 `_delta_log`는 EC2-2의 로컬 파일시스템에 함께 둔다. 이 구성은 서비스 영역과
데이터 영역의 분리를 검증하는 MVP이며, EC2-2 장애·교체까지 견디는 HA 저장 구조는
아니다. 여러 EC2에서 Spark를 분산 실행하는 구성은 공유 저장소를 도입한 뒤 검토한다.

아래 항목은 Event 계약 문서, Connector 구현 및 Kafka 문서에서 이미 확정·확인된
기준이다. Raw 저장 구조 검토를 이유로 다시 합의하지 않는다.

| 구간 | 확정 기준 |
| --- | --- |
| HTTP 요청 | `{ schema_version, events[] }`, Event 최대 100건 |
| Collector 입력 Event | Front `LogEnvelope` 14개 필드 |
| Kafka Value | Event 14개 필드 + `received_at`, `source`, `request_id`, `event_index` = 18개 JSON 필드 |
| Kafka 발행 단위 | HTTP batch가 아니라 Event 1건 |
| Kafka Key | `session_id` |
| Kafka Topic | `activity-events` |
| Spark 입력 단위 | Kafka record 1건 |
| 목표 Q1 Raw 출력 단위 | Delta `raw_events` row 1건 |

Collector는 batch에 포함된 Event를 각각 직렬화하여 Kafka에 발행한다. 같은 HTTP
요청의 Event는 같은 `request_id`와 `received_at`을 공유하고 `event_index`로 batch
내 순서를 구분한다. `source`는 `actor_type='synthetic'`이면 `simulator`, 그 외에는
`web`으로 생성한다.

## 3. 현재 Kafka 연동 설정

| 항목 | 현재 로컬 구현 기준 |
| --- | --- |
| Topic 생성 | 기본 자동 생성 비활성화. 인프라에서 명시적으로 생성 |
| local partition 수 | 3 |
| local replication factor | 1 |
| cleanup policy | `delete` |
| retention | 86,400,000ms(24시간) |
| Producer acks | `all` |
| Producer idempotence | 활성화 |
| Producer compression | `lz4` |

Kafka의 24시간 retention은 현재 로컬 기본값이며 Raw 장기 보존 기간이 아니다.
Q1 장애가 retention을 넘으면 Kafka record가 만료될 수 있으므로
`failOnDataLoss=true`로 조용한 누락을 막는다. 목표 구조에서는 Delta
`raw_events`가 Kafka 만료 이후 원문 재처리 입력을 맡는다. Raw 보존 기간은
EC2-2 가용 용량과 데이터 생성량을 측정한 뒤 별도로 확정한다.

Kafka Producer idempotence는 Producer 내부 재시도의 중복을 줄이지만 Front 또는
Simulator가 같은 `event_id`를 다시 HTTP로 제출하는 업무 재전송까지 제거하지 않는다.
따라서 Raw의 `event_id` 중복 보존과 Processed의 정본 선정이 별도로 필요하다.

## 4. Dataset 저장 구조

| 항목 | 기준 | 상태 |
| --- | --- | --- |
| Dataset | `raw_events` | 확정 |
| grain | Kafka record 1건 | 확정 |
| 원본 기준 | `raw_value` + Kafka 출처 좌표 | 확정 |
| 논리 쓰기 방식 | insert-only, `event_id` dedup 미수행 | 확정 |
| 현재 Q1 저장 형식 | Parquet | 로컬 PoC/MVP 임시 방식 |
| Host Raw 저장 경로 | `data/raw_events` | 로컬 확정값 |
| Container Raw 저장 경로 | `/opt/project/data/raw_events` | 로컬 확정값 |
| 목표 저장 엔진 | Delta Lake | 확정 |
| 목표 배치 위치 | EC2-2 로컬 파일시스템 | 확정 |
| 목표 Raw Table | Delta `raw_events` | 확정 |
| partition column | `raw_ingest_date` | 목표 구조 유지값 |
| partition 시간 기준 | UTC | 확정 |
| Host checkpoint 경로 | `data/checkpoints/raw-events` | 로컬 확정값 |
| Container checkpoint 경로 | `/opt/project/data/checkpoints/raw-events` | 로컬 확정값 |
| 기본 Kafka topic | `activity-events` | 확정 |
| 신규 query 시작 offset | `earliest` | 현재 Q1 구현값 |
| Kafka data loss 설정 | `failOnDataLoss=true` | 현재 Q1 구현값 |
| EC2-2 Delta root URI | Spark·Delta 실행 구성과 함께 지정 | 구현 대기 |
| EC2-2 checkpoint URI | Delta root와 분리된 EC2-2 경로로 지정 | 구현 대기 |
| Raw 보존 기간 | EC2-2 용량·이벤트 발생량 확인 후 지정 | 운영값 미정 |

HTTP batch의 크기와 관계없이 Collector가 Kafka에 Event 단위로 발행하므로
Kafka record 1건을 Raw row 1건으로 저장한다.

현재 Q1의 저장 경로는 `RAW_EVENTS_PATH`, checkpoint 경로는
`RAW_EVENTS_CHECKPOINT_PATH`로 override할 수 있다. 위 Host/Container 경로는 현재
로컬 Docker 구성의 확정값이다. EC2-2의 실제 Delta root와 checkpoint URI는
Spark·Scala·`delta-spark` 호환 조합 및 배포 경로를 확인한 뒤 환경변수에 적용한다.
현재 Parquet 경로를 EC2 목표 경로로 간주하지 않는다.

## 5. 물리 식별자

Raw row는 아래 Kafka 좌표 조합으로 식별한다.

```text
kafka_cluster_id
+ kafka_topic
+ kafka_partition
+ kafka_offset
```

`event_id`는 업무 Event 식별자이며 Raw row의 물리 식별자가 아니다. 같은 Event를
재전송하면 같은 `event_id`를 가진 서로 다른 Kafka record가 저장될 수 있다.

Delta `raw_events` 적재는 위 조합을 조건으로 한 insert-only `MERGE`를 사용한다.
일치하는 row는 UPDATE하지 않고, 일치하지 않는 row만 INSERT한다. 따라서 동일
checkpoint 재시작뿐 아니라 checkpoint 삭제 후 전체 Replay에서도 같은 Kafka
record의 물리 중복을 줄인다. 서로 다른 Kafka 좌표로 수신된 같은 `event_id`는 Raw에
각각 보존하고 Processed `cleaned_events`에서 업무 중복을 제거한다.

동일 이름의 Kafka Topic을 삭제 후 재생성하면 Partition Offset이 다시 사용될 수
있다. 이 경우 기존 Raw·checkpoint와 섞지 않고 `KAFKA_CLUSTER_ID`를 새 세대 값으로
변경하거나 저장 경로를 분리한다. `kafka_cluster_id`는 실행할 때마다 바꾸는 run ID가
아니라 같은 Kafka Cluster/Topic 세대에서 안정적으로 유지하는 출처 ID다.

## 6. 물리 저장 Projection

Kafka Raw Event Schema는 이미 확정된 18개 필드이며 변경하지 않는다. 아래 표는 그
payload 원문에 Kafka 출처와 적재 metadata를 더해 저장하는 **물리 컬럼
projection**이다.

현재 Spark Q1은 28개 컬럼을 쓴다. 아래 목표 projection 29개 중 `source`만 별도
조회 컬럼으로 추출하지 않지만, 18필드 원문인 `raw_value` 안에는 이미 포함되어
있다. 따라서 이는 Raw Schema 추가·변경 사항이 아니라 확정 계약과 Q1 구현 사이의
정합성 보완 사항이다. 목표 projection을 충족하려면 Q1의 `_event_schema()`,
`RAW_EVENT_FIELDS` 및 `build_raw_events_frame()`에 `source`를 추가하는 후속 구현과
컬럼 계약 테스트 갱신이 필요하다.

### 6.1 Kafka metadata 및 원문

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `kafka_cluster_id` | string | N | Kafka cluster 또는 topic 세대를 구분하는 설정값 |
| `kafka_topic` | string | N | Kafka topic |
| `kafka_partition` | int | N | Kafka partition |
| `kafka_offset` | long | N | partition 내 offset |
| `kafka_timestamp` | timestamp | N | Kafka record timestamp |
| `kafka_timestamp_type` | int | N | Kafka timestamp type |
| `kafka_key` | string | Y | Kafka message key. 현재 Collector 기준 `session_id` |
| `raw_value` | string | Y | Kafka Value 원문 JSON. 원본 보존의 최종 기준 |
| `is_json_parseable` | boolean | N | `raw_value`를 공통 Event 구조로 파싱할 수 있는지 |

Kafka tombstone 또는 비정상 record도 좌표를 잃지 않도록 `raw_value`는 nullable로
저장한다. `raw_value`가 NULL이거나 JSON 파싱에 실패해도 Raw row는 삭제하지 않는다.

### 6.2 Kafka payload 조회 컬럼

| column | type | nullable | Raw 원천 | 설명 |
| --- | --- | --- | --- | --- |
| `schema_version` | string | Y | `schema_version` | Event Schema 버전 |
| `event_id` | string | Y | `event_id` | 업무 Event 식별자 |
| `event_name` | string | Y | `event_name` | Event 이름 |
| `intent` | string | Y | `intent` | Event 의미 분류 |
| `event_time` | timestamp | Y | `occurred_at` | RFC 3339 값을 UTC timestamp로 정규화 |
| `received_at` | timestamp | Y | `received_at` | Collector 수신 시각을 UTC로 정규화 |
| `source` | string | Y | `source` | Collector가 기록한 유입 경로. `web`, `simulator` |
| `persona_id` | string | Y | `persona_id` | Persona ID |
| `session_id` | string | Y | `session_id` | 세션 ID |
| `page_view_id` | string | Y | `page_view_id` | 페이지 방문 ID |
| `sequence_no` | int | Y | `sequence_no` | 세션 내 Event 순서 |
| `page_type` | string | Y | `page_type` | 화면 유형 |
| `product_id` | string | Y | `product_id` | Event 대상 상품 ID |
| `actor_type` | string | Y | `actor_type` | `user`, `synthetic` |
| `environment` | string | Y | `environment` | 실행 환경 |
| `request_id` | string | Y | `request_id` | Collector batch 요청 ID |
| `event_index` | int | Y | `event_index` | batch 내부 Event 순서 |
| `properties_json` | string | Y | `properties` | Event별 properties를 추출한 조회용 JSON 문자열 |

Kafka payload는 Front `LogEnvelope` 14개 필드와 Collector 부가 필드
`received_at`, `source`, `request_id`, `event_index` 4개를 합친 총 18개 필드다.
18개 필드는 `raw_value`에 원형 그대로 보존하고, 위 조회 컬럼으로도 제공한다.

Raw 조회 컬럼은 payload가 유효하지 않아도 row를 보존하기 위해 모두 nullable로
둔다. required field 판정, enum 검증, timestamp 원문 형식 검증은 Processed 단계의
책임이다.

`occurred_at`은 `event_time`, `properties`는 `properties_json`이라는 저장 컬럼명을
사용한다. 이름과 타입을 정규화하더라도 원래 문자열과 JSON 구조는 `raw_value`에서
재조회할 수 있어야 한다.

### 6.3 Raw 적재 metadata

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `raw_ingested_at` | timestamp | N | Raw row를 생성한 UTC 시각 |
| `raw_ingest_date` | date | N | `raw_ingested_at`의 UTC 날짜. Delta partition column |

## 7. 원본 보존 규칙

1. `raw_value`는 Kafka Value를 UTF-8 문자열로 변환한 값이며 내용 일부를 제거하거나
   다시 직렬화하지 않는다.
2. `properties`는 임의의 고정 Struct로 축소하지 않고 `properties_json` 조회
   컬럼으로 추출한다. 공백·키 순서를 포함한 정확한 Kafka 원문은 `raw_value`만을
   기준으로 한다.
3. JSON 파싱 실패, 필수 필드 누락, enum 오류가 있어도 Raw row는 보존한다.
4. 같은 `event_id`가 여러 번 들어와도 Raw에서 제거하지 않는다.
5. Raw를 수정하거나 overwrite하지 않는다. 재처리 결과는 Processed Dataset에 쓴다.

## 8. 중복 처리 책임

| 단계 | 기준 | 처리 |
| --- | --- | --- |
| Raw Q1 | Kafka record | Kafka 좌표 기반 insert-only `MERGE`. `event_id` dedup 미수행 |
| Processed Q2 좌표 방어 | `kafka_cluster_id + kafka_topic + kafka_partition + kafka_offset` | 기존 Parquet 또는 비정상 적재에서 같은 좌표가 반복된 경우 1건 선택 |
| Processed Q2 업무 dedup | `event_id` | 정본 1건을 `cleaned_events`에 저장 |
| Processed Q2 감사 | 정본이 아닌 유효 후보 | `duplicate_events`에 저장 |
| Processed Q2 오류 | 파싱·필수값·semantic validation 실패 | `bad_events`에 원문과 Kafka 좌표를 저장 |

동일 `event_id`의 정본 선정 순서는 아래로 고정한다.

```text
received_at ASC
→ kafka_topic ASC
→ kafka_partition ASC
→ kafka_offset ASC
```

Fact, Mart, Dashboard는 Raw를 직접 집계하지 않고 `cleaned_events` 또는 그 파생
Dataset만 사용한다.

## 9. 목표 Q1 Partition, MERGE 및 checkpoint 규칙

- Delta partition은 Event 발생일이 아니라 적재 시각의 UTC 날짜인
  `raw_ingest_date`를 사용한다.
- 늦게 도착한 Event도 실제 Raw 적재 날짜 partition에 저장한다.
- 각 micro-batch 내부에서 Kafka 물리 식별자 중복을 먼저 제거한다.
- Delta `raw_events`와 Kafka 물리 식별자를 비교하고 matched row에는 UPDATE를
  수행하지 않으며, unmatched row만 INSERT한다.
- 정상 재시작은 동일한 checkpoint 경로를 사용한다.
- 환경·Kafka cluster·topic 세대가 다르면 checkpoint를 공유하지 않는다.
- 출력 경로와 checkpoint 경로는 서로 다른 위치를 사용하며, 하나의 checkpoint를
  서로 다른 Streaming Query가 공유하지 않는다.
- `startingOffsets`는 checkpoint가 없는 신규 query에만 적용한다.
- checkpoint를 삭제하고 전체 Replay해도 insert-only `MERGE`가 같은 Kafka 좌표를
  다시 INSERT하지 않아야 한다. Processed Q2의 좌표 중복 정리는 방어 로직으로
  유지한다.

## 10. 조회 기준

| 조회 목적 | 조건 |
| --- | --- |
| 특정 Kafka 원본 1건 | `kafka_cluster_id`, `kafka_topic`, `kafka_partition`, `kafka_offset` |
| 같은 업무 Event의 모든 수신본 | `event_id` |
| 특정 Collector 요청 재구성 | `request_id`, `event_index` |
| 세션 Event 조회 | `session_id`, `sequence_no` |
| 실제/합성 유입 분리 | `actor_type`, `source` |
| 적재 일자 범위 pruning | `raw_ingest_date` |
| payload 원문 재처리 | `raw_value` |

Raw의 조회 결과는 원본 확인과 재처리를 위한 것이며 KPI 계산 결과로 사용하지 않는다.

## 11. Schema 변경 호환 원칙

- Kafka payload 필드가 추가되어도 `raw_value`에는 전체 JSON을 그대로 저장한다.
- 조회용 projection에 새 컬럼을 추가할 때는 기존 Delta 파일에 해당 컬럼이 없음을
  전제로 nullable하게 확장하고, Schema evolution 이후 기존·신규 row의 동시 조회를
  검증한다.
- 필드명·타입·의미 변경은 기존 Raw를 덮어쓰지 않고 `schema_version`으로 구분한다.
- projection 파싱 실패나 알 수 없는 신규 필드 때문에 Kafka record 자체를 버리지
  않는다.

## 12. 구조 확정 후 검증 조건

현재 저장소의 단위 테스트는 Parquet Q1 설정과 컬럼 목록을 확인하지만 실제
Kafka → Spark → Delta 저장을 실행한 통합 검증 결과는 아니다. Spark·Scala·
`delta-spark` 호환 버전과 EC2-2 경로를 적용한 뒤 아래 결과를 남긴다.

1. 유효 Event를 전송해 Kafka record 1건이 Raw row 1건으로 저장되는지 확인한다.
2. Kafka `value`와 Raw `raw_value`가 동일하고 Topic·Partition·Offset·Key가 함께
   저장되는지 확인한다.
3. 18개 payload 필드 중 조회 projection 대상이 예상 타입으로 조회되는지 확인한다.
4. 같은 `event_id`를 재전송해 Raw에는 모두 보존되는지 확인한다.
5. 같은 checkpoint로 Q1을 재시작했을 때 처리 완료 record를 다시 쓰지 않는지
   확인한다.
6. JSON 파싱 실패 record도 `raw_value`와 Kafka 좌표를 가진 Raw row로 남는지
   확인한다.
7. checkpoint를 새로 만들고 전체 Replay해도 같은 Kafka 좌표가 중복 INSERT되지
   않는지 확인한다.
8. EC2-2 프로세스 재시작 후 Delta Table과 checkpoint가 유지되는지 확인한다.
