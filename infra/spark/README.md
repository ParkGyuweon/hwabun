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

## 저장소와 한계

`data/`는 컨테이너와 호스트가 공유하는 로컬 개발용 저장소다. Q1의 Raw Output과
Checkpoint, Q2~Q4의 Processed/Mart Output이 이 경로 아래에 생긴다. Git에는
포함하지 않는다.

`spark-events`와 `spark-ivy-cache`는 Docker Named Volume이다. 전자는 History
Server가 조회하는 Application Event Log, 후자는 이후 Kafka Connector 의존성
해결 캐시다.

이 구성은 단일 호스트 PoC다. 여러 호스트 Worker, 고가용성 Master, S3/MinIO 기반
Checkpoint 또는 Parquet Replay의 exactly-once 보장은 별도 운영 설계 범위다.
