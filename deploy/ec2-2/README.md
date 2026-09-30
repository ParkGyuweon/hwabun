# EC2-2 Kafka / Spark 배포

단일 EC2에서 Kafka와 Spark Master·Worker·History·Q1 Raw Sink를 실행한다.
Spark 3.5.6과 Kafka Connector 3.5.6을 함께 고정했다. Q1은 기본 10초 간격으로
Raw Parquet을 추가하며, Q2~Q5는 별도 배치 실행이다. Delta Lake나 다중 서버
분산 저장·고가용성 구성은 포함하지 않는다.

## 최초 실행

저장소 전체를 EC2-2에 받아 두고 아래 명령을 실행한다. Docker Compose v2 이상이
필요하다. 네트워크는 이 Compose가 자동 생성하므로 `a306-data`를 별도로 만들지 않는다.

```bash
cd ~/S15P21A306/deploy/ec2-2
cp .env.example .env
nano .env
```

`KAFKA_ADVERTISED_HOST`에 **EC2-1에서 도달 가능한 EC2-2 IP 또는 DNS**를 입력한다.
`http://`, 포트, `localhost`, Docker 서비스명은 넣지 않는다. 두 서버 사이에 사설망
연결이 있으면 사설 주소를 사용한다. 값이 비어 있으면 Compose 검증부터 실패한다.

기본 데이터 경로를 사용할 때:

```bash
sudo mkdir -p /opt/hwabun/data
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=100 kafka-init spark-raw-sink
```

`kafka-init`은 Kafka가 준비되면 `activity-events`를 3 Partition / RF1 / 보존 24시간으로
생성하고 정상 종료한다. `Exited (0)`이 정상이다. 토픽 생성이 성공한 뒤 Q1이 시작된다.
기존 토픽은 `--if-not-exists`로 보존하므로 `.env`를 바꾸고 재실행해도 기존 토픽의
Partition·보존 정책을 변경하지 않는다.

Kafka Connector는 최초 Q1 시작 시 Maven 저장소에서 다운로드해 Ivy Volume에 캐시한다.
EC2-2의 외부 다운로드 연결이 필요하다. Worker 기본 자원은 Executor용 2코어·2GB이며,
Kafka·Master·History·Driver·OS 메모리는 별도이므로 EC2 전체 메모리를 2GB로 계산하지 않는다.

## EC2-1 연결

EC2-1의 `deploy/ec2-1/.env`에서 아래 값을 EC2-2와 맞춘 뒤 Backend·추천 컨테이너를 재생성한다.

```dotenv
KAFKA_BOOTSTRAP_SERVERS=<EC2-2의 KAFKA_ADVERTISED_HOST 값>:9092
ACTIVITY_EVENTS_TOPIC=activity-events
```

```bash
# EC2-1의 deploy/ec2-1 폴더에서 실행
docker compose up -d backend recommend
```

- 서버 간 Kafka는 `9092`, EC2-2 내부 Spark는 `kafka:19092`로 접속한다.
- 현재 Kafka는 인증 없는 PLAINTEXT다. EC2-2의 보안 그룹/방화벽에서 TCP 9092는
  EC2-1의 실제 접속 출발지에만 허용한다. 인터넷 전체에 개방하지 않는다.
- Controller 9093, 내부 Kafka 19092, Spark RPC 7077은 호스트에 공개하지 않는다.
- Spark UI는 기본적으로 `127.0.0.1:18080`, History UI는 `127.0.0.1:18081`이다.
  EC2-1의 `/pipeline`에서 Spark Master의 `/json`을 읽어야 할 때만 `.env`의
  `SPARK_MASTER_UI_BIND_IP`를 EC2-2 사설 IP로 바꾼다. 외부 인터넷에 공개하지 않는다.

개발 PC에서 SSH 터널을 열고 브라우저로 `http://localhost:18080` 또는 `18081`에 접속한다.

```bash
ssh -N -L 18080:127.0.0.1:18080 -L 18081:127.0.0.1:18081 ubuntu@<EC2-2-SSH주소>
```

EC2-1에서 Spark UI를 읽는 배포 설정은 다음과 같이 둔다.

```dotenv
# EC2-2 .env
SPARK_MASTER_UI_BIND_IP=172.26.1.194
```

EC2-2의 AWS 보안 그룹과 UFW에는 EC2-1 사설 IP만 TCP 18080으로 허용한다.
Spark RPC 7077, Worker UI 8081, History UI 18081은 이 연동에 필요하지 않다.

```bash
sudo ufw allow from 172.26.8.48 to any port 18080 proto tcp
sudo ufw reload
sudo docker compose up -d --no-deps spark-master
```

EC2-1에서 연결을 확인한다.

```bash
curl -sS --max-time 4 http://172.26.1.194:18080/json
```

연결 확인 후 EC2-1의 `.env`에 `SPARK_MASTER_UI=http://172.26.1.194:18080`을
넣고 추천 컨테이너만 재생성한다.

```bash
sudo docker compose up -d recommend
```

## 적재 확인 및 배치 실행

```bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:19092 --describe --topic activity-events
docker compose logs --tail=100 spark-raw-sink
```

EC2-1에서 실제 행동 이벤트를 전송한 뒤 Raw Parquet이 생성되는지 확인한다.
기본 호스트 경로는 `/opt/hwabun/data/raw_events`이다. Kafka 프로세스가 healthy라는 것만으로
EC2-1 → Kafka → Spark 적재가 검증된 것은 아니다.

아래 배치는 `deploy/ec2-2/hwabun-daily-batch.timer`가 하루 한 번 실행한다.
Q2~Q5가 순서대로 성공한 뒤 같은 실행에서 `dw-projection`까지 이어서 수행하므로,
Parquet Mart와 MySQL `dw`가 함께 갱신된다. Q1 Raw Sink는 계속 실행되고, 배치는 동시에
두 번 실행되지 않도록 lock을 사용한다.

Q3의 Commons `brand_hash`를 만들려면 EC2-2의 gitignore된 `.env`에
`COMMONS_HASH_SALT`를 **비어 있지 않은 고정 값**으로 설정해야 한다. 이 값은 저장소에
커밋하지 않고, 한 번 정한 뒤 바꾸지 않는다. 설정 후 `spark-master`와 `spark-worker`를
재생성해 컨테이너에 반영한다. 배치 시작 시 Master에 값이 없으면 Q2 실행 전에 중단한다.

```bash
sudo docker compose up -d --no-build spark-master spark-worker
```

처음 한 번만 EC2-2 호스트에 timer를 설치한다.

```bash
cd ~/S15P21A306/deploy/ec2-2
sudo docker compose --profile dw build dw-projection
sudo cp hwabun-daily-batch.service /etc/systemd/system/
sudo cp hwabun-daily-batch.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hwabun-daily-batch.timer
systemctl list-timers hwabun-daily-batch.timer
```

즉시 한 번 실행해 보거나 시연 직전에 수동 실행할 때는 같은 service를 호출한다.

```bash
sudo systemctl start hwabun-daily-batch.service
sudo journalctl -u hwabun-daily-batch.service -n 100 --no-pager
```

기본 실행 시각은 호스트 시간대와 무관하게 매일 **03:00 KST**(전날 18:00 UTC)이다.
Q1 Raw Sink가 1코어를 쓰므로 Worker가 기본 2코어라면 배치의 `spark.cores.max=2`는
상한일 뿐 실제로는 1코어만 남을 수 있다. Q1을 유지하면서 배치에 2코어를 주려면
EC2 자원을 확인하고 `SPARK_WORKER_CORES`를 최소 3으로 설정해야 한다. Q5는 현재 전체
결정성 검사를 수행하므로 완료까지 시간이 걸릴 수 있다.

timer나 service 파일을 수정한 뒤에는 다시 `/etc/systemd/system/`에 복사하고
`sudo systemctl daemon-reload` 및 `sudo systemctl restart hwabun-daily-batch.timer`를
실행한다.

결과는 `/opt/hwabun/data/processed`, `/opt/hwabun/data/marts`,
`/opt/hwabun/data/validation/pipeline-report.json`에서 확인한다.
기존 `infra/spark/run-pipeline.sh` 및 `verify-e2e.ps1`은 **로컬 Compose 전용**이므로
이 배포 스택을 관리하는 명령으로 사용하지 않는다.

상품·브랜드 매핑 등 최신 분석 입력은 EC2-2의 `batch/`, `contracts/`, `frontend/`를 사용한다.
EC2-1의 추천 데이터 Volume은 이 서버에 자동 공유되지 않는다. 신규 상품 입력 등은 별도
동기화가 필요하며, 이 Compose가 상품 동기화를 수행하지는 않는다.

## DW Mart MySQL 발행

자동 배치를 사용하면 Q4·Q5 성공 뒤 선택 profile `dw`의 `dw-projection`이 자동 실행된다.
수동으로 projection만 다시 실행할 수도 있다.
기본 실행은 DW 계약 24종 중 22종 Mart Parquet을 순서대로 읽어
MySQL staging에 적재하고, 건수·NULL 축을 포함한 grain 중복·필수값을 검증한 뒤
Mart별 조회 테이블을 교체한다. 일반 `up`은 이 Job을 실행하지 않는다.
자세한 최초 DB 준비·계정 권한·추천 서버 연결·실패 복구는
[DW projection 실행 안내](../../streaming/DW_PROJECTION.md)를 따른다.

```bash
# 이 서버의 .env에 DW_MYSQL_HOST/PORT/DB/USER/PASSWORD 설정 후
docker compose --profile dw build dw-projection
docker compose --profile dw run --rm dw-projection
```

기본 입력은 `SPARK_DATA_PATH/marts/<mart>`이고, 읽기 전용으로 마운트된다.
발행 결과는 `/reports/dw-projection.json`에서 Mart별로 확인한다. 기존 EC2-2 `.env`에
7종의 `DW_PROJECTION_MARTS`가 있으면 Compose 기본값보다 우선하므로, 전체 발행을
원할 때는 `streaming/DW_PROJECTION.md`의 22종(운영 기본) 목록으로 그 값을 갱신한다.
0행이거나 Parquet 파일이 없는 Mart는 발행이 중단되고 앞서 발행한 Mart는 교체된 상태로
남을 수 있다. Q4가 같은 입력 경로를 overwrite하는 동안에는 실행하지 않는다.
EC2-1 `/pipeline` 화면의 표시 목록은 별도 추천 서버 설정이므로 이 값을 바꿔도
자동으로 늘어나지 않는다.

MySQL 준비 전 추천 폴백 파일만 만들 때는 별도 출력 폴더를 바인드하고 JSONL 전용 모드로
실행한다. 생성된 파일은 EC2-1 추천 컨테이너의 `/data/user_trait_snapshot.jsonl`로
전달해야 한다.

```bash
sudo mkdir -p /opt/hwabun/export
sudo docker compose --profile dw run --rm \
  -v /opt/hwabun/export:/export \
  dw-projection \
  --mart user_trait_daily \
  --emit-jsonl /export/user_trait_snapshot.jsonl \
  --jsonl-only
```

`--jsonl-only`는 MySQL 연결 없이 최신 `trait_date_kst`와 `actor_type=user` 행을
추천 서버의 7개 컬럼 형식으로 출력한다. 빈 결과와 소비자 grain 중복은 기존 파일을
보호하기 위해 기본 거부한다.

## 데이터 보존과 재시작

- Kafka 데이터: 기본 Named Volume `hwabun-ec2-2-kafka-data`.
- Raw / Processed / Mart / 체크포인트: `SPARK_DATA_PATH` 호스트 폴더.
- Spark 실행 로그 / Connector 캐시: Compose Named Volume.
- `docker compose restart spark-raw-sink`는 기존 체크포인트에서 이어서 처리한다.
- `RAW_EVENTS_STARTING_OFFSETS`는 새 체크포인트를 사용하는 최초 시작에만 적용된다.
- `docker compose down`은 데이터를 보존한다. `down -v`는 Kafka 데이터와 Named Volume을
  삭제하므로 일반 배포·재시작에는 사용하지 않는다.

기존 로컬 Compose를 EC2-2에서 사용했다면 새 스택과 동시에 실행하지 않는다.
기존 컨테이너의 `docker inspect`로 Kafka Volume 이름과 데이터 마운트 경로를 확인한 뒤,
동일 이력을 이어 쓸 경우 `.env`의 `KAFKA_DATA_VOLUME`, `SPARK_DATA_PATH`,
`KAFKA_KRAFT_CLUSTER_ID`, `KAFKA_SOURCE_CLUSTER_ID`를 기존 값에 맞춘다.
기존 스택을 종료한 뒤 새 스택을 시작하며 Kafka Volume과 Raw·체크포인트를 함께 보존한다.
기본값으로 새 Volume을 만들면 기존 데이터가 삭제되지는 않지만 새 Kafka로 시작한다.

기동 순서 참고: [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/).
