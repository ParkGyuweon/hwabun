# 로컬 Spark Cluster

Kafka `activity-events`를 읽는 Spark Job을 실제 컨테이너 환경에서 실행하기 위한
단일 호스트 개발용 Cluster다. Spark 처리 로직은 `streaming/jobs/`에 있고, 이
디렉터리는 실행 환경만 담당한다.

## 구성

| Service | 역할 | Host 주소 |
| --- | --- | --- |
| `spark-master` | Standalone Master, Job 배정 | `spark://localhost:7077`, UI `http://localhost:18080` |
| `spark-worker` | Executor 실행 | Master UI에서 상태 확인 |
| `spark-history` | 완료된 Application Event Log 조회 | `http://localhost:18081` |

Kafka와 Spark는 외부 Docker Network `a306-data`에서 통신한다. 컨테이너 안에서
Kafka Bootstrap 주소는 `kafka:19092`이며, 호스트에서 실행하는 Backend는 기존처럼
`localhost:9092`를 사용한다.

## 실행

저장소 루트에서 실행한다. Network는 처음 한 번만 생성하면 된다.

### Windows PowerShell

```powershell
.\infra\create-network.ps1
docker compose `
  -f infra/kafka/docker-compose.yml `
  -f infra/spark/docker-compose.yml `
  up -d --build --wait kafka spark-master spark-worker spark-history
```

### Linux / macOS / Git Bash

```bash
bash infra/create-network.sh
docker compose \
  -f infra/kafka/docker-compose.yml \
  -f infra/spark/docker-compose.yml \
  up -d --build --wait kafka spark-master spark-worker spark-history
```

Spark Version·Worker 자원은 `infra/spark/.env.example`을 `infra/spark/.env`로
복사한 뒤 `--env-file infra/spark/.env`로 전달해 변경할 수 있다.

## Q1 Raw Streaming 실행

Cluster가 정상 상태가 된 뒤 별도 Profile로 Q1을 시작한다.

```powershell
docker compose `
  -f infra/kafka/docker-compose.yml `
  -f infra/spark/docker-compose.yml `
  --profile streaming up -d spark-raw-sink
```

Q1은 `kafka:19092`의 `activity-events`를 읽어
`/opt/project/data/raw_events`에 Parquet을 추가하고,
`/opt/project/data/checkpoints/raw-events`에 Checkpoint를 유지한다. 종료·재시작은
같은 Checkpoint를 사용해야 Kafka offset부터 이어서 처리된다.

로컬 Worker는 기본 2코어이며 Q1은 그중 1코어만 사용한다. 남은 1코어는 Q2~Q4
Batch Pipeline에 남겨 Streaming과 분석 Job을 동시에 실행할 수 있게 한다.

상태와 로그는 아래처럼 확인한다.

```powershell
docker compose `
  -f infra/kafka/docker-compose.yml `
  -f infra/spark/docker-compose.yml `
  ps

docker compose `
  -f infra/kafka/docker-compose.yml `
  -f infra/spark/docker-compose.yml `
  logs -f spark-raw-sink
```

Kafka Connector는 `SPARK_KAFKA_PACKAGE`으로 Spark Version과 함께 고정한다. 최초
기동 때 Connector 의존성을 받아 `spark-ivy-cache` Volume에 저장하므로 이후 기동은
같은 캐시를 사용한다.

## Pipeline Runner

PowerShell에서는 아래 명령으로 인프라와 Pipeline을 관리한다.

```powershell
.\infra\spark\run-pipeline.ps1 up
.\infra\spark\run-pipeline.ps1 start-q1
.\infra\spark\run-pipeline.ps1 run-batch
.\infra\spark\run-pipeline.ps1 status
```

`run-batch`는 `clean_events_job.py` → `derive_facts_job.py` →
`build_marts_job.py` → `validate_pipeline_job.py`를 순서대로 실행한다. 앞선 Job이
실패하면 다음 Job은 실행하지 않는다. Validation Report는
`data/validation/pipeline-report.json`에 저장된다.

Linux/macOS/Git Bash에서는 `bash infra/spark/run-pipeline.sh <action>`을 사용한다.
지원 action은 `up`, `start-q1`, `stop-q1`, `run-batch`, `validate`, `status`, `down`이다.

## E2E·재시작 검증

아래 검증은 매 실행마다 새 `event_id`를 Kafka `activity-events`에 전송한다. Q1이
그 이벤트를 Raw Parquet에 정확히 한 번 적재했는지 확인한 뒤 Q1을 Checkpoint를
유지한 채 재생성하고, Q2~Q4와 불변성 검증까지 실행한다.

```powershell
.\infra\spark\verify-e2e.ps1
```

Raw 적재가 느린 환경에서는 대기 시간을 늘릴 수 있다.

```powershell
.\infra\spark\verify-e2e.ps1 -TimeoutSeconds 150
```

이 스크립트는 `data/`나 Kafka Topic을 삭제하지 않는다. 기존 적재 데이터와 함께
검증되며, 최종 결과는 `data/validation/pipeline-report.json`에서 확인한다.

## 저장소와 한계

`data/`는 컨테이너와 호스트가 공유하는 로컬 개발용 저장소다. Q1의 Raw Output과
Checkpoint, Q2~Q4의 Processed/Mart Output이 이 경로 아래에 생긴다. Git에는
포함하지 않는다.

`spark-events`와 `spark-ivy-cache`는 Docker Named Volume이다. 전자는 History
Server가 조회하는 Application Event Log, 후자는 이후 Kafka Connector 의존성
해결 캐시다.

이 구성은 단일 호스트 PoC다. 여러 호스트 Worker, 고가용성 Master, S3/MinIO 기반
Checkpoint 또는 Parquet Replay의 exactly-once 보장은 별도 운영 설계 범위다.
