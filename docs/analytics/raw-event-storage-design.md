# Raw Event 저장 설계

작성일: 2026-09-02

대상 작업: `[DATA] Raw Event Log 저장 구성`

상태: 계약 분리 완료, 현재 Parquet PoC와 목표 Delta 구조 검증 대기

계약 원본: [`../../contracts/raw-event-schema.md`](../../contracts/raw-event-schema.md)

## 1. 문서 목적

이 문서는 Collector가 Kafka에 발행한 Event를 손실 없이 저장하고 재처리할 수 있도록
Raw 저장 방식을 선택한 이유, 배포 구조, 현재 구현 차이와 검증 계획을 설명한다.

`raw_events`의 grain, key, 컬럼, 타입, nullable, partition과 원본 보존 규칙은
[`contracts/raw-event-schema.md`](../../contracts/raw-event-schema.md)를 단일 출처로
사용한다. 이 문서는 동일한 컬럼 표를 복제하지 않는다.

## 2. 저장 흐름과 책임 경계

```text
Frontend / Simulator
→ POST /api/events
→ Backend Collector
→ Kafka activity-events
→ Spark Structured Streaming Q1
→ Delta Lake raw_events
→ Delta Lake cleaned_events / marts
→ MySQL dw KPI Mart
→ Dashboard
```

Raw는 분석용 정제 테이블이 아니다. Kafka에 도달한 record를 재조회·재처리할 수 있게
보존하며, Collector가 HTTP 단계에서 거절한 요청은 Backend metric 또는 별도 error
sink의 책임이다. 업무 Event 중복 제거와 semantic validation은 Processed 단계에서
수행한다.

## 3. 배포 및 저장소 선택

- EC2-1 서비스 영역에는 Backend, MySQL의 `app`·`dw` schema와 Redis를 둔다.
- EC2-2 데이터 영역에는 Kafka, Spark와 Delta Lake를 둔다.
- Delta Lake는 Raw·Processed·Mart의 재처리 기준을 보존한다.
- MySQL `dw`에는 Dashboard가 직접 조회할 KPI Mart만 선별 적재한다.

별도 S3, EBS 데이터 볼륨 또는 공유 파일시스템이 없는 현재 구성에서는 Delta 파일과
`_delta_log`를 EC2-2 로컬 파일시스템에 함께 둔다. 이는 서비스와 데이터 영역을
분리하는 MVP 구조이며 EC2-2 장애·교체를 견디는 HA 구성은 아니다. 공유 저장소를
도입하기 전에는 여러 EC2에서 하나의 Delta Table을 분산 운영하지 않는다.

## 4. 현재 Kafka 연동 기준

| 항목 | 현재 로컬 구현 |
| --- | --- |
| Topic | `activity-events` |
| Partition | 3 |
| Replication factor | 1 |
| Cleanup policy | `delete` |
| Retention | 86,400,000ms, 24시간 |
| Producer acks | `all` |
| Producer idempotence | 활성화 |
| Compression | `lz4` |

Kafka retention은 Raw 보존 기간이 아니다. Q1 장애가 retention보다 길어지면 record가
만료될 수 있으므로 현재 `failOnDataLoss=true`로 조용한 누락을 막는다. Producer
idempotence는 Producer 내부 재시도 중복을 줄이지만 같은 `event_id`를 다시 HTTP로
제출하는 업무 재전송은 제거하지 않는다.

## 5. 현재 구현과 목표 구조

| 항목 | 현재 Q1 | 목표 |
| --- | --- | --- |
| 저장 엔진 | Parquet | Delta Lake |
| Raw 경로 | `data/raw_events` | EC2-2 Delta root 아래 `raw_events` |
| Container 경로 | `/opt/project/data/raw_events` | 배포 환경에서 확정 |
| Checkpoint | `data/checkpoints/raw-events` | Delta root와 분리된 EC2-2 경로 |
| 쓰기 | append Stream | 물리 key 기준 insert-only `MERGE` |
| Projection | 목표 계약 중 `source` 조회 컬럼 누락 | Raw 계약 전체 컬럼 |
| 시작 Offset | `earliest` | 신규 query에만 적용 |
| Data loss | `failOnDataLoss=true` | 유지 |

현재 Q1 경로는 `RAW_EVENTS_PATH`, checkpoint는
`RAW_EVENTS_CHECKPOINT_PATH`로 override할 수 있다. 현재 로컬 Parquet 경로를 EC2
목표 저장 방식으로 해석하지 않는다. EC2-2 Delta root와 checkpoint URI는
Spark·Scala·`delta-spark` 호환 조합 및 실제 배포 경로를 확인한 뒤 적용한다.

현재 `streaming/jobs/raw_sink_job.py`는 Raw 계약의 조회 projection 중 `source`를
별도 컬럼으로 추출하지 않는다. `raw_value`에는 값이 보존되므로 원문 손실은 없지만,
계약과 실제 출력 Schema의 drift다. `_event_schema()`, `RAW_EVENT_FIELDS`,
`build_raw_events_frame()`과 컬럼 계약 테스트를 함께 보완해야 한다.

## 6. Delta 적재와 checkpoint 설계

- Partition은 Event 발생일이 아니라 적재 UTC 날짜인 `raw_ingest_date`를 사용한다.
- 늦게 도착한 Event도 실제 Raw 적재 날짜 partition에 저장한다.
- `foreachBatch`에서 micro-batch 내부 물리 key 중복을 먼저 제거한다.
- Delta Table과 물리 key를 비교해 matched row는 수정하지 않고 unmatched row만 넣는다.
- 정상 재시작은 동일한 checkpoint를 사용한다.
- 환경·Kafka cluster·Topic 세대가 다르면 checkpoint를 공유하지 않는다.
- 출력과 checkpoint 경로를 분리하며 하나의 checkpoint를 여러 query가 공유하지 않는다.
- `startingOffsets`는 checkpoint가 없는 신규 query에만 적용한다.

같은 이름의 Topic을 재생성해 Offset이 재사용되면 기존 Raw와 섞지 않는다.
`KAFKA_CLUSTER_ID`를 새 세대 값으로 바꾸거나 저장 경로를 분리한다.

## 7. 조회 및 운영 원칙

- Kafka 원본 추적은 cluster·Topic·Partition·Offset으로 수행한다.
- Collector batch 재구성은 `request_id`, `event_index`를 사용한다.
- 같은 업무 Event의 수신 이력은 `event_id`로 조회한다.
- 실제 사용자와 합성 유입은 `actor_type`, `source`로 구분한다.
- Raw는 원본 확인과 재처리에만 사용하며 KPI를 직접 계산하지 않는다.
- Raw 보존 기간은 EC2-2 가용 용량과 실제 Event 발생량을 측정한 뒤 정한다.

## 8. 구현 및 E2E 검증 계획

1. `raw_sink_job.py` 출력 Schema를 Raw 계약과 대조한다.
2. 유효 Event를 Collector로 보내 Kafka record와 Raw row를 비교한다.
3. Kafka Value와 `raw_value`, 물리 좌표와 key가 동일한지 확인한다.
4. `source`를 포함한 조회 projection의 타입과 값을 확인한다.
5. 같은 `event_id` 재전송이 Raw에 모두 남는지 확인한다.
6. JSON 파싱 실패 record도 원문과 Kafka 좌표를 가진 채 저장되는지 확인한다.
7. 동일 checkpoint 재시작 시 처리 완료 record를 다시 쓰지 않는지 확인한다.
8. checkpoint 삭제 후 Replay에서 물리 key 중복이 생기지 않는지 확인한다.
9. EC2-2 프로세스 재시작 후 Delta Table과 checkpoint가 유지되는지 확인한다.

위 검증이 끝나기 전까지 Raw 계약은 Draft로 유지한다.
