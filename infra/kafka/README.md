# 로컬 Kafka 환경

Kafka 이벤트 수집과 이후 Spark Job을 로컬에서 연결하기 위한 개발 환경이다. 운영용 Kafka Cluster나 고가용성 구성을 정의하지 않는다.

## 구성

| 항목 | 로컬 기준 |
| --- | --- |
| 이미지 | `apache/kafka:4.2.0` |
| 모드 | KRaft 단일 combined Broker/Controller |
| 호스트 Client 주소 | `localhost:9092` |
| 컨테이너 Client 주소 | `kafka:19092` |
| Controller 주소 | `kafka:9093` |
| 기본 Topic | `activity-events` |
| Partition | 3개 |
| Replication Factor | 1 |
| Topic 보존 기간(생성 시) | 24시간 |
| 자동 Topic 생성 | 비활성화 |
| 데이터 볼륨 | `kafka-data` |
| 공용 Docker Network | `a306-data` |

호스트에서 실행하는 Backend는 `localhost:9092`를 사용하고, Spark 컨테이너는 공용 Network에서 `kafka:19092`를 사용한다. `raw_events`, `cleaned_events`, `bad_events`는 Kafka Topic이 아니라 Spark가 저장할 Dataset 이름이다.

`a306-data`는 Kafka Compose가 만들거나 지우지 않는 외부 Network다. Spark Compose도 같은 Network에 참여하므로, Kafka와 Spark를 실행하기 전에 한 번 생성한다.

단일 Broker와 RF1은 로컬 PoC를 위한 설정이다. Broker 장애를 견디는 운영 환경은 Broker 3대 이상, RF3, `min.insync.replicas=2` 구성을 별도로 검증해야 한다.

## 실행

저장소 루트에서 실행한다.

### Windows PowerShell

```powershell
.\infra\create-network.ps1
docker compose -f infra/kafka/docker-compose.yml up -d
.\infra\kafka\topics.ps1
```

### Linux / macOS / Git Bash

```bash
bash infra/create-network.sh
docker compose -f infra/kafka/docker-compose.yml up -d
bash infra/kafka/topics.sh
```

Topic 생성 스크립트는 `activity-events`를 이미 생성한 경우에도 실패하지 않으며, 마지막에 Partition과 설정을 조회한다.

## Backend 연결

Backend를 호스트에서 실행할 때는 기본값이 이미 로컬 Kafka 주소를 가리킨다.

```powershell
$env:KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
$env:ACTIVITY_EVENTS_TOPIC = 'activity-events'
```

Backend의 Topic 자동 생성은 사용하지 않고 이 디렉터리의 Topic 생성 스크립트를 사용한다. 필요한 경우 아래 환경변수로 생성 값을 바꿀 수 있다.

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `ACTIVITY_EVENTS_TOPIC` | `activity-events` | 생성할 Topic 이름 |
| `ACTIVITY_EVENTS_PARTITIONS` | `3` | 신규 Topic Partition 수 |
| `KAFKA_TOPIC_REPLICATION_FACTOR` | `1` | 신규 Topic Replication Factor |
| `KAFKA_TOPIC_RETENTION_MS` | `259200000` (72시간) | 신규 Topic 보존 시간(ms) |

이미 존재하는 Topic에는 `--if-not-exists`가 적용되므로 스크립트를 다시 실행해도 Partition 수를 변경하지 않는다. Partition 확장은 별도의 영향 분석과 전환 절차가 필요한 작업이다.

## 확인 및 종료

```powershell
docker compose -f infra/kafka/docker-compose.yml ps
docker compose -f infra/kafka/docker-compose.yml exec kafka `
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 `
  --describe --topic activity-events
```

컨테이너만 종료하면 Kafka 데이터 볼륨은 유지된다.

```powershell
docker compose -f infra/kafka/docker-compose.yml down
```

`down`은 외부 Network `a306-data`를 지우지 않는다. Spark 컨테이너가 모두 종료된 뒤에만 필요에 따라 직접 제거한다.

로컬 Kafka 이력을 초기화할 때만 `down -v`를 사용한다. 이 명령은 저장된 Kafka 이벤트와 Topic 메타데이터를 삭제한다.

## 다음 연결 단계

1. Backend에서 `POST /api/events`를 호출해 `activity-events`에 이벤트가 기록되는지 확인한다.
2. Spark Q1이 `activity-events`를 읽어 `raw_events`에 Kafka Topic/Partition/Offset과 원본 Value를 저장한다.
3. Spark Q2가 `event_id` 기준 정본을 선정해 `cleaned_events`와 `bad_events`를 만든다.
