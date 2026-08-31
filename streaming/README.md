# Spark Structured Streaming

현재 구현된 Q1은 Kafka `activity-events`를 읽어 Raw Dataset `raw_events`를
Parquet으로 적재한다.

```text
Kafka activity-events
  -> Spark Structured Streaming Q1
  -> data/raw_events/*.parquet
```

## Q1 책임

- Kafka Event 1건을 Raw row 1건으로 저장한다.
- Kafka `topic`, `partition`, `offset`, `timestamp`, `timestampType`, `key`를
  함께 남긴다.
- Collector가 보낸 JSON 전체를 `raw_value`로 보존한다.
- 파싱 가능한 공통 Envelope 필드는 다음 단계가 쓰기 쉽도록 별도 컬럼으로
  추출한다.
- `properties`는 구조를 임의로 잘라내지 않고 `properties_json` 문자열로
  보존한다.
- `event_id` 기준 중복 제거는 하지 않는다. 재전송된 같은 업무 Event는 Raw에
  모두 남기고 Q2에서 정본을 고른다.

Q1에서 `is_json_parseable=false`인 레코드도 Kafka 좌표와 원문을 가진 Raw row로
남는다. `bad_events` 분류와 의미 검증은 Q2의 책임이다.

## Raw 출력 컬럼

| 컬럼 | 설명 |
| --- | --- |
| `kafka_cluster_id` | 저장소를 공유하는 Kafka Cluster/Topic 세대를 구분하는 설정값 |
| `kafka_topic`, `kafka_partition`, `kafka_offset` | Kafka 수신 레코드 좌표 |
| `kafka_timestamp`, `kafka_timestamp_type` | Broker 레코드 timestamp와 타입 |
| `kafka_key` | Collector가 사용한 `session_id` key |
| `raw_value` | Kafka Value 원문 JSON 문자열 |
| `is_json_parseable` | scalar Envelope 파싱 가능 여부 |
| `schema_version` ~ `event_index` | 파싱 가능한 공통 Event 필드 |
| `event_time` | `occurred_at`을 UTC timestamp로 변환한 값 |
| `received_at` | Collector `received_at`을 UTC timestamp로 변환한 값 |
| `properties_json` | Event별 properties 원문 JSON |
| `raw_ingested_at` | Q1이 Raw row를 만든 시각 |
| `raw_ingest_date` | 저장 파티션용 UTC 날짜 |

`raw_value`가 원본 보존의 기준이다. 파싱 컬럼이 null이어도 Raw를 삭제하거나
현재 시각으로 보정하지 않는다.

## 실행

Spark 배포판과 Spark-Kafka connector는 실행 환경의 Spark/Scala 버전에 맞춰
제공해야 한다. Connector 버전을 임의로 고정하지 않고 클러스터 버전과 맞추는
이유는 Spark minor 버전과 Scala binary version이 일치해야 하기 때문이다.

예시는 저장소 루트에서 실행하는 형태다.

```bash
spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_<scala-binary-version>:<spark-version> \
  streaming/jobs/raw_sink_job.py \
  --bootstrap-servers localhost:9092 \
  --topic activity-events \
  --output-path data/raw_events \
  --checkpoint-path data/checkpoints/raw-events \
  --starting-offsets earliest
```

로컬 Kafka는 먼저 아래처럼 실행한다.

```bash
docker compose -f infra/kafka/docker-compose.yml up -d --wait
bash infra/kafka/topics.sh
```

PowerShell에서는 `infra/kafka/topics.ps1`을 사용할 수 있다.

주요 기본값은 다음 환경 변수 또는 CLI 옵션으로 바꿀 수 있다.

| 환경 변수 | 기본값 |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `ACTIVITY_EVENTS_TOPIC` | `activity-events` |
| `RAW_EVENTS_PATH` | `data/raw_events` |
| `RAW_EVENTS_CHECKPOINT_PATH` | `data/checkpoints/raw-events` |
| `RAW_EVENTS_STARTING_OFFSETS` | `earliest` |
| `RAW_EVENTS_TRIGGER_INTERVAL` | `10 seconds` |
| `RAW_EVENTS_MAX_OFFSETS_PER_TRIGGER` | 미설정 |
| `KAFKA_CLUSTER_ID` | `local` |

## 복구와 한계

- 정상 재시작은 같은 `checkpointLocation`을 사용한다. Spark가 checkpoint의
  Kafka offset을 기준으로 다음 범위를 읽는다.
- `startingOffsets`는 새 Query에만 적용된다. 기존 checkpoint를 가진 Query를
  과거로 돌리는 옵션이 아니다.
- `failOnDataLoss=true`를 유지해 보존 기간 만료나 offset 범위 이탈을 조용히
  건너뛰지 않는다.
- Parquet file sink는 일반적인 Structured Streaming 재시작과 checkpoint 흐름을
  검증하는 Q1 MVP다. checkpoint를 삭제한 뒤 같은 Raw 경로로 Replay하면 이미
  저장된 Kafka 좌표와의 원자적 비교·Upsert를 제공하지 않는다.
- 따라서 K03/K16과 같은 checkpoint 유실·전체 Replay 멱등성은 저장 엔진을
  확정한 후 Q1 sink를 transactional table 또는 별도 coordinate index로
  보강해야 한다. 일반 Parquet append를 최종 exactly-once 계약으로 해석하지
  않는다.

## 테스트

Spark가 설치되지 않은 개발 환경에서도 설정·Raw 컬럼 계약 테스트는 실행할 수
있다.

```bash
python -m unittest discover -s streaming/tests -p "test_*.py"
python -m py_compile streaming/jobs/raw_sink_job.py
```

위 테스트는 실제 Broker나 Spark executor를 띄우는 통합 테스트가 아니다. 실제
Kafka → Parquet 연결은 Docker Kafka와 Spark-Kafka connector가 준비된 환경에서
별도로 확인한다.

## Q2 실행

Q2는 Raw 전체 snapshot을 읽어 Processed 결과를 다시 만드는 배치 작업이다.
새로운 후보가 늦게 Raw에 들어오거나 checkpoint를 잃고 Raw가 재생된 경우에도
전체 후보를 다시 비교하므로 `event_id` 정본이 동일한 규칙으로 수렴한다.

```bash
spark-submit streaming/jobs/clean_events_job.py \
  --input-path data/raw_events \
  --cleaned-path data/processed/cleaned_events \
  --bad-path data/processed/bad_events \
  --duplicate-path data/processed/duplicate_events
```

정상적인 후보 중 정본은 다음 순서로 고른다.

```text
received_at ASC
→ kafka_topic ASC
→ kafka_partition ASC
→ kafka_offset ASC
```

Q2는 동일 Kafka 좌표가 Raw에 반복된 경우 먼저 한 row로 축약하고, 그 다음
`event_id` 기준 정본을 고른다. 같은 `event_id`의 나머지 후보는
`duplicate_events`에 보존한다. JSON 파싱·공통 필드·enum·sequence·synthetic
필수 properties 검증에 실패한 row는 원문과 좌표를 `bad_events`에 남긴다.

현재 Q2는 전체 snapshot을 `overwrite`하는 MVP다. 운영 환경에서 Raw가 커지면
날짜/offset 범위 증분 처리와 transactional upsert를 도입하되, 정본 비교 규칙과
출력 grain은 유지한다.
