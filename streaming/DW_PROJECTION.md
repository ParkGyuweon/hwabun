# DW Mart → MySQL dw

`jobs/publish_user_trait_job.py`는 Spark가 완료한 Mart Parquet을 PyArrow로 최대 1,000행씩
읽는 독립 Python Job이다. Spark 재집계나 JDBC 연결이 필요하지 않다. 현재 projection
allowlist는 `contracts/dw/schema.sql`의 24개 DW Mart와 맞춰져 있으며, `--marts`로
발행 대상을 선택한다. **EC2-2 Compose의 기본 실행은 아직 22종이다** — 시장 비교 2종
(`cross_brand_daily`, `category_price_reference`)은 DDL만 갖춘 상태이고 운영 MySQL에
테이블이 없다. 테이블을 만들기 전에 발행 목록에 넣으면 그 종만 실패한다(발행은 Mart마다
독립이라 나머지는 정상 발행된다).
DDL·grain·NULL 정책은 `contracts/dw/schema.sql`과 `build_ddl.py`에서
읽고 수정하지 않는다.

## 실행 순서

1. EC2-2에서 Q2~Q4를 실행하고 Q5 검증을 통과시킨다.
2. 해당 Mart Parquet을 덮어쓰는 배치가 없는 상태에서 projection을 실행한다.
3. Mart별 staging 적재·검증을 통과하면 각 조회 테이블을 하나의 `RENAME TABLE`로 발행한다.
4. 추천 서버와 Dashboard API가 다음 조회에서 MySQL projection을 사용한다.

`_SUCCESS`와 각 파일의 경로·크기·수정 시각으로 입력 변경을 검사한다. 이것은 배치와의
공유 잠금이 아니므로 **같은 입력의 overwrite와 projection을 동시에 실행하면 안 된다.**
별도 run 디렉터리를 완료 후 보존하고 그 경로를 `--source-root`로 전달하는 것을 권장한다.
Q1의 Raw 수집은 계속 실행할 수 있다.

## 최초 MySQL 준비 (EC2-1, 관리자)

이미 `dw` 테이블이 있으면 재초기화하지 말고 DDL 일치 여부부터 확인한다.
빈 `dw`를 처음 만들 때만 저장소 루트에서 다음 절차를 사용한다.

```bash
sudo docker cp contracts/dw/schema.sql shop-backend-mysql:/tmp/hwabun-dw-schema.sql
sudo docker exec -it shop-backend-mysql mysql -uroot -p
```

MySQL 프롬프트에서:

```sql
SOURCE /tmp/hwabun-dw-schema.sql;
SHOW CREATE TABLE dw.user_trait_daily;
```

기존 MySQL Volume에 init SQL을 추가하는 것만으로는 적용되지 않는다. 관리자에게 실제
접속 출발지 제한과 별도 계정을 요청한다. 비밀번호는 저장소에 넣지 않는다.

기존 `dw`에는 `schema.sql`을 다시 실행하지 않는다. 2026-09-17 Mart 컬럼 변경은
[`deploy/ec2-1/migrations/20260917_dw_mart_columns.sql`](../deploy/ec2-1/migrations/20260917_dw_mart_columns.sql)
마이그레이션으로 적용한다. 세 대상 테이블에 기존 행이 있고 새 컬럼이 일부라도 빠졌으면
의미 없는 0으로 채우지 않고 중단한다. 적용 후에는 발행기의 `MysqlStore.check_target()`으로
실제 테이블이 최신 DDL과 일치하는지 검증한다. 적용 전에는 현재 테이블과 행 수를
확인한다. EC2-1에 이미 수동 적용한 경우 스크립트는 변경 없이 통과하지만, 그 경우에도
검증은 생략하지 않는다. `INIT_DW_SCHEMA`는 신규 DB 전용이므로 기존 DB 마이그레이션에
사용하지 않는다.

```bash
# EC2-1 저장소 루트에서, DB 관리자 검토 후 실행
sudo docker cp deploy/ec2-1/migrations/20260917_dw_mart_columns.sql \
  ec2-1-mysql-1:/tmp/dw-mart-columns.sql
sudo docker exec ec2-1-mysql-1 sh -c \
  'mysql -u root -p"$MYSQL_ROOT_PASSWORD" < /tmp/dw-mart-columns.sql'
sudo docker exec ec2-1-mysql-1 rm -f /tmp/dw-mart-columns.sql
```

- 발행 계정: `dw.*`의 `SELECT, INSERT, CREATE, DROP, ALTER` 권한.
- 추천 계정: `dw.user_trait_daily`의 `SELECT` 권한만.
- JDBC/MySQL 외부 포트 기본은 호스트 13306 → 컨테이너 3306이다. 실제 설정을 확인한다.
- TCP 13306은 EC2-2 및 승인된 소비자 출발지에만 허용한다.

추천 컨테이너는 EC2-1 Compose에서 MySQL의 외부 `shop-backend-db` 네트워크에도
연결한다. 따라서 EC2-1의 `deploy/ec2-1/.env`는 공개 포트가 아니라 Docker DNS를
사용해 다음처럼 설정한다.

```dotenv
DW_MYSQL_HOST=shop-backend-mysql
DW_MYSQL_PORT=3306
DW_MYSQL_DB=dw
DW_MYSQL_USER=dw_reader
DW_MYSQL_PASSWORD=<조회 전용 계정 비밀번호>
```

`shop-backend-db`는 `shop_backend/docker-compose.mysql.yml`을 먼저 실행해야 생긴다.
반대로 EC2-2의 발행 컨테이너는 다른 호스트에 있으므로 EC2-1의 사설 IP와 공개 포트
`13306`으로 접근한다. `localhost`는 각 컨테이너 자신을 뜻하므로 어느 쪽에도 쓰지
않는다.

## 발행 (EC2-2)

`deploy/ec2-2/.env`에 발행 계정으로 설정한다.

```dotenv
DW_MYSQL_HOST=<EC2-2에서 접근 가능한 EC2-1 MySQL 호스트>
DW_MYSQL_PORT=13306
DW_MYSQL_DB=dw
DW_MYSQL_USER=dw_writer
DW_MYSQL_PASSWORD=<발행 계정 비밀번호>
```

```bash
cd ~/S15P21A306/deploy/ec2-2
sudo docker compose --profile dw build dw-projection
sudo docker compose --profile dw run --rm dw-projection
```

기본 실행은 Compose가 넘기는 목록(현재 22종)을 순서대로 발행한다.
stdout의 전체 `status=published`, 각 Mart의 `published=true`와
`source_rows=inserted_rows`를 확인한다. JSON 보고서는 `dw-projection-reports` Volume의
`/reports/dw-projection.json`에도 Mart별로 남는다.
실행마다 같은 보고서 파일이 갱신되므로 이력 보존이 필요하면 별도 파일명을 지정한다.
Mart 사이의 `RENAME TABLE`은 하나의 트랜잭션으로 묶지 않는다. 중간 Mart에서 실패하면
앞에서 성공한 Mart만 새 값으로 발행될 수 있으므로, 보고서의 실패 Mart만 원인 해결 후
재실행한다.

기존 EC2-2 `.env`에 7종의 `DW_PROJECTION_MARTS`가 지정돼 있으면 아래 목록으로
갱신한다. `.env` 값은 Compose 기본값보다 우선한다. 특정 Mart만 발행할 때도 이 변수를
사용할 수 있다.

**발행 목록에 Mart를 새로 넣을 때는 두 가지가 선행한다.**

1. **MySQL에 그 Mart의 테이블을 먼저 만든다.** 발행은 staging 적재 후
   `RENAME TABLE dw.<mart> TO dw.<mart>__old, dw.<staging> TO dw.<mart>`로 교체하므로
   (`publish_user_trait_job.py`) 대상 테이블이 없으면 그 RENAME이 실패한다.
2. **`dw-projection` 이미지를 다시 빌드한다.**

   ```bash
   sudo docker compose --profile dw build dw-projection
   ```

   `streaming/Dockerfile.dw`가 `COPY jobs/ /app/streaming/jobs/`로 **Job 코드를 빌드 시점에
   이미지 안으로 복사한다.** Spark 컨테이너와 달리 bind mount가 아니다(`contracts/`만
   마운트한다). 그래서
   `git pull`만으로는 새 Mart의 파티션 축이 컨테이너에 반영되지 않고,
   `MART_PARTITION_COLUMNS[mart]`가 직접 색인이라(`dw_projection_source.py`) 옛 이미지에서는
   **그 Mart만 `KeyError`로 실패한다.**

둘 중 하나라도 빠지면 발행은 그 Mart에서만 실패하고 나머지는 정상 발행된다(Jira 359).
보고서에서 실패한 Mart를 확인한 뒤 원인을 해결하고 그 Mart만 재실행하면 된다.

아래 목록 끝의 `cross_brand_daily`·`category_price_reference`가 지금 이 조건에 해당한다 —
`contracts/dw/schema.sql`에 DDL은 있으나 운영 MySQL에는 테이블이 없다.

```dotenv
DW_PROJECTION_MARTS=user_trait_daily,brand_daily_kpi,product_daily_kpi,funnel_daily_kpi,brand_repurchase_daily,product_repurchase_daily,purchase_reason_daily,persona_segment_daily_kpi,brand_price_band_daily_kpi,segment_price_band_daily_kpi,brand_cohort_dim,commons_cohort_weekly,ingredient_weekly_interest,product_exit_daily,segment_content_daily,friction_daily,exit_daily,entry_source_daily,content_daily_kpi,content_conversion_daily,behavior_conversion_daily,event_daily,cross_brand_daily,category_price_reference
```

특정 Mart 하나만 재발행할 때는 다음처럼 실행한다.

```bash
sudo docker compose --profile dw run --rm dw-projection \
  --mart brand_daily_kpi \
  --source /data/marts/brand_daily_kpi \
  --report-path /reports/brand-daily-projection.json
```

완료된 특정 run 디렉터리를 발행할 때:

```bash
sudo docker compose --profile dw run --rm dw-projection \
  --source-root /data/<run>/marts \
  --report-path /reports/user-trait-<run>.json
```

기본적으로 0행은 발행을 막아 기존 조회 결과를 보존한다. **정상적인 빈 결과로 교체할
의도가 확인된 경우에만** 위 명령에 `--allow-empty`를 추가한다. `_SUCCESS`만 있고
스키마를 가진 Parquet 파일이 없는 경로는 정상적인 빈 결과로 인정하지 않는다.

## 추천 폴백 JSONL

MySQL 연결을 준비하기 전 시연용 최소 경로가 필요하면 같은 Job에서 추천 서버가 읽는
7개 컬럼 JSONL을 생성한다. 최신 `trait_date_kst`의 `actor_type='user'` 행만 남기며,
`identity_scope + user_id + trait`가 중복되면 임의의 실행 행을 고르지 않고 실패한다.
출력은 임시 파일을 만든 뒤 rename하므로 기존 스냅샷을 부분 파일로 덮어쓰지 않는다.

```bash
sudo mkdir -p /opt/hwabun/export
sudo docker compose --profile dw run --rm \
  -v /opt/hwabun/export:/export \
  dw-projection \
  --mart user_trait_daily \
  --emit-jsonl /export/user_trait_snapshot.jsonl \
  --jsonl-only
```

`--jsonl-only`는 MySQL에 연결하지 않는다. MySQL 발행과 JSONL 생성을 한 번에 하려면
`--jsonl-only`만 빼면 되며, 두 결과가 같은 Parquet 읽기·필터 경로를 사용한다.
EC2-2의 `/opt/hwabun/export/user_trait_snapshot.jsonl`을 EC2-1로 전달한 뒤 추천
컨테이너의 `/data/user_trait_snapshot.jsonl`에 임시 파일로 복사하고 `mv`로 교체한다.
추천 서버는 기본 300초 주기로 재읽기 때문에 컨테이너 재시작은 필요하지 않다.

```bash
scp /opt/hwabun/export/user_trait_snapshot.jsonl \
  ubuntu@<EC2-1-사설주소>:/tmp/user_trait_snapshot.jsonl
sudo docker cp /tmp/user_trait_snapshot.jsonl \
  ec2-1-recommend-1:/data/user_trait_snapshot.jsonl.tmp
sudo docker exec ec2-1-recommend-1 \
  mv /data/user_trait_snapshot.jsonl.tmp /data/user_trait_snapshot.jsonl
```

## 추천 연결 (EC2-1)

`deploy/ec2-1/.env`에 조회 전용 계정으로 `DW_MYSQL_HOST`, `DW_MYSQL_PORT`,
`DW_MYSQL_DB=dw`, `DW_MYSQL_USER`, `DW_MYSQL_PASSWORD`를 설정한다. 발행 계정은 사용하지 않는다.

```bash
cd ~/S15P21A306/deploy/ec2-1
sudo docker compose up -d recommend
sudo docker compose logs --tail=100 recommend
```

기존 `batch/serving/user_trait.py`의 `read_mysql()`이 사용하는 경로다. 실제 연결 확인 시
단순히 추천 HTTP 200만 보지 말고 **장기 성향 로더의 source가 MySQL인지**와 알려진 사용자에
대한 `long_term_trait` 값을 확인한다. 파일 fallback으로도 HTTP 200이 나올 수 있다.

적재기는 모든 identity/실행 축을 보존한다. 현재 추천 쿼리는 최신 `trait_date_kst`와
`actor_type='user'`를 선택하지만 `source`와 실행 축을 합치지 않는다. 같은 사용자·trait에
여러 source/run이 존재할 때 어떤 값을 소비할지는 추천 담당과 확정해야 하며, 적재기에서
임의 합산·덮어쓰기로 해결하지 않는다. 이 연결 설정은 추천 로직을 변경하지 않는다.

## 검증과 실패 처리

- DB 대리키 `dw_row_id`는 INSERT에서 생략하여 AUTO_INCREMENT가 생성한다.
- 키 중복은 `ix_user_trait_daily__grain`의 **전체 컬럼**으로 `GROUP BY ... HAVING COUNT(*) > 1`을
  실행한다. NULL 축도 같은 그룹으로 묶는다. 계약 §7.1의 "PRIMARY KEY" 표기는 §7.6과
  충돌하므로 §7.6 및 실제 DDL의 grain 기준을 따른다.
- DB collation 기준으로도 유일해야 한다. 대소문자·악센트 동등 키가 충돌하면 발행을 중단한다.
- 필수 NULL, VARCHAR 초과, 정수 범위 초과, NaN/Infinity를 거부한다. SQL strict mode도 켠다.
- Spark UTC timestamp는 UTC `DATETIME(3)`로 저장한다. 마이크로초의 밀리초 미만은 절삭한다.
- DB `GET_LOCK`으로 같은 Mart 발행을 하나로 제한한다. 프로세스가 종료되면 연결 잠금이 풀린다.
- 실패한 staging은 남긴다. 다음 성공 발행이 이 Job 형식의 과거 staging과 `__old`를 정리한다.
- `status=publication_unknown`은 RENAME 응답이 끊긴 경우 등을 뜻한다. DB에서 조회 테이블과
  해당 run의 staging·`__old`를 먼저 확인한다. 이 상태를 "기존 결과 보존 확정"으로 보고하지 않는다.
- RENAME 성공 후 정리 실패는 `published`와 warning으로 보고한다. 이미 발행된 데이터를 되돌리지 않는다.

입력·DB 컬럼이 계약과 다르면 자동 ALTER하지 않고 실패한다. 데이터 파트의 생성기/DDL을
먼저 정합화하고 승인된 DB migration을 적용한다. Job은 DB 자체를 생성하지 않는다.

## 테스트

Python 3.12 환경에서:

```bash
python -m pip install -r streaming/requirements-dw.txt
python -m unittest streaming.tests.test_dw_projection_source streaming.tests.test_dw_projection_publish streaming.tests.test_dw_projection_marts
python -m unittest discover -s contracts/dw -p test_build_ddl.py
```

MySQL 8.4 통합 테스트는 **전용 테스트 서버**의 `DW_TEST_MYSQL_HOST`, `DW_TEST_MYSQL_PORT`,
`DW_TEST_MYSQL_USER`, `DW_TEST_MYSQL_PASSWORD`가 있을 때만 실행한다. 운영 DB 설정을 재사용하지 않는다.
테스트는 임의 이름의 `dw_projection_test_<id>` DB를 만들고 종료 시 그 DB만 삭제한다.

```bash
python -m unittest streaming.tests.test_dw_projection_mysql -v
```

NULL grain 중복·문자 비교 중복 거부, 기존 결과 보존, 반복 발행, 동시 실행 차단, 빈 결과 교체,
실제 추천 `read_mysql` 조회를 검증한다. 실행 환경이 없으면 skip되며, skip을 적재 성공으로 보지 않는다.

참고: [Arrow batch reader](https://arrow.apache.org/docs/python/dataset.html),
[MySQL atomic DDL](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html),
[PyMySQL connection](https://pymysql.readthedocs.io/en/latest/modules/connections.html).
