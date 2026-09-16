# user_trait_daily → MySQL dw

`jobs/publish_user_trait_job.py`는 Spark가 완료한 Parquet을 PyArrow로 최대 1,000행씩
읽는 독립 Python Job이다. Spark 재집계나 JDBC 연결이 필요하지 않다. 현재 발행 대상은
`user_trait_daily` 하나다. DDL·grain·NULL 정책은 `contracts/dw/schema.sql`과
`build_ddl.py`에서 읽고 수정하지 않는다.

## 실행 순서

1. EC2-2에서 Q2~Q4를 실행하고 Q5 검증을 통과시킨다.
2. 해당 Parquet을 덮어쓰는 배치가 없는 상태에서 projection을 실행한다.
3. 실행별 staging 적재·검증을 모두 통과하면 하나의 `RENAME TABLE`로 발행한다.
4. 추천 서버가 다음 reload에서 조회한다. 기본 reload 간격은 300초다.

`_SUCCESS`와 각 파일의 경로·크기·수정 시각으로 입력 변경을 검사한다. 이것은 배치와의
공유 잠금이 아니므로 **같은 입력의 overwrite와 projection을 동시에 실행하면 안 된다.**
별도 run 디렉터리를 완료 후 보존하고 그 경로를 `--source`로 전달하는 것을 권장한다.
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

- 발행 계정: `dw.*`의 `SELECT, INSERT, CREATE, DROP, ALTER` 권한.
- 추천 계정: `dw.user_trait_daily`의 `SELECT` 권한만.
- JDBC/MySQL 외부 포트 기본은 호스트 13306 → 컨테이너 3306이다. 실제 설정을 확인한다.
- TCP 13306은 EC2-2 및 승인된 소비자 출발지에만 허용한다.

같은 서버여도 추천 컨테이너는 기본적으로 MySQL의 `shop-backend-db` 네트워크에 없다.
이번 설정은 **추천 컨테이너에서 접근 가능한 호스트 주소와 공개 포트**를 사용한다.
`localhost`는 추천 컨테이너 자신이다. 별도로 같은 Docker 네트워크에 연결했을 때만
`shop-backend-mysql:3306`을 사용할 수 있다.

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

stdout의 `status=published`, `published=true`와 `source_rows=inserted_rows`를 확인한다.
JSON 보고서는 `dw-projection-reports` Volume의 `/reports/user-trait-projection.json`에도 남는다.
실행마다 같은 보고서 파일이 갱신되므로 이력 보존이 필요하면 별도 파일명을 지정한다.

완료된 특정 run 디렉터리를 발행할 때:

```bash
sudo docker compose --profile dw run --rm dw-projection \
  --source /data/<run>/marts/user_trait_daily \
  --report-path /reports/user-trait-<run>.json
```

기본적으로 0행은 발행을 막아 기존 조회 결과를 보존한다. **정상적인 빈 결과로 교체할
의도가 확인된 경우에만** 위 명령에 `--allow-empty`를 추가한다. `_SUCCESS`만 있고
스키마를 가진 Parquet 파일이 없는 경로는 정상적인 빈 결과로 인정하지 않는다.

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
python -m unittest streaming.tests.test_dw_projection_source streaming.tests.test_dw_projection_publish
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
