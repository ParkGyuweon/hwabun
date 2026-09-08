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

`occurred_at`과 `received_at`은 RFC 3339의 명시적 timezone offset(`Z`, `+09:00`
등)을 허용한다. timezone 없는 timestamp는 Q2에서 invalid record로 분류하며,
Raw 원문은 유지하고 파싱된 `event_time`·`received_at`은 UTC timestamp로 저장한다.

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

파이프라인 검증 Job은 synthetic 세션의 Persona 혼합, 세션 내
`sequence_no` 충돌, `simulation_run_id`별 `scenario_id`·`generator_type` 불일치를
실패로 판정한다. Raw의 동일 `event_id` 중복은 재전송 가능성을 고려해 warning으로
기록하고, `cleaned_events`의 중복은 오류로 판정한다.

현재 Q2는 전체 snapshot을 `overwrite`하는 MVP다. 운영 환경에서 Raw가 커지면
날짜/offset 범위 증분 처리와 transactional upsert를 도입하되, 정본 비교 규칙과
출력 grain은 유지한다.

## Q3 세션·상품 Fact

Q3는 Q2의 `cleaned_events`만 입력으로 사용한다. 따라서 Raw의 재전송 중복은
Q2 정본 선택 이후 downstream fact에 들어오지 않는다.

```bash
spark-submit streaming/jobs/derive_facts_job.py \
  --input-path data/processed/cleaned_events \
  --sessionized-path data/processed/sessionized_events \
  --product-fact-path data/processed/product_event_fact \
  --dim-product-path data/processed/dim_product \
  --dim-brand-path data/processed/dim_brand
```

`sessionized_events`는 `session_id → sequence_no → event_time → received_at →
event_id` 순으로 `event_order`를 만들고 앞뒤 Event 이름과 sequence gap을
기록한다. 이 배치 작업은 Structured Streaming watermark를 사용하지 않으므로
`is_late_event`는 NULL로 남긴다.

`product_event_fact`는 상품 대상 Event만 남긴다. 일반 Event는
`item_index=0`으로 저장하고, `purchase`와 `begin_checkout`의 `items[]`는
`items[].product_id` 기준으로 explode한다. 구매 매출은 `quantity * unit_price`
인 `item_revenue`만 합산하며 주문 전체 금액 `order_value`를 상품별로 합산하지
않는다.

상품 Fact와 콘텐츠 Fact의 `brand_id`는 `product_id → dim_product.brand_id` left
join으로 보강한다. `dim_brand` grain은 `brand_id`, `dim_product` grain은
`product_id`다. 매칭되지 않는 상품과 `product_id=NULL`인 플랫폼 Event는 row를
버리거나 세션의 다른 상품을 참조하지 않고 `brand_id=NULL`로 유지한다.

## Q4 Funnel·DW Mart

Processed Fact에서 Dashboard용 세션 Funnel과 일간 KPI Mart를 만든다.

```bash
spark-submit streaming/jobs/build_marts_job.py \
  --sessionized-path data/processed/sessionized_events \
  --product-fact-path data/processed/product_event_fact \
  --dim-product-path data/processed/dim_product \
  --product-ingredient-path batch/ingest/data/serving/product_ingredient.csv \
  --ingredient-vocab-path batch/ingest/data/serving/ingredient_vocab.csv \
  --funnel-session-path data/processed/funnel_session_fact \
  --product-daily-path data/marts/product_daily_kpi \
  --funnel-daily-path data/marts/funnel_daily_kpi \
  --ingredient-weekly-path data/marts/ingredient_weekly_interest \
  --category-price-path data/marts/category_price_reference \
  --banner-daily-path data/marts/banner_daily \
  --user-trait-daily-path data/marts/user_trait_daily \
  --cross-brand-daily-path data/marts/cross_brand_daily
```

생성 결과는 다음과 같다.

| Dataset | Grain | 역할 |
| --- | --- | --- |
| `funnel_session_fact` | `session_id + product_id` | 노출 → 클릭 → 상세 → 정보 확인 → 장바구니 → Checkout → 구매 도달 시각 |
| `product_daily_kpi` | `event_date_kst + product_id + actor/source/run 축` | 상품 Event 수, 세션 수, CTR, 상세 진입률, 매출 |
| `funnel_daily_kpi` | `funnel_date_kst + product_id + actor/source/run 축` | 세션 기반 Funnel 전환·이탈률 |
| `ingredient_weekly_interest` | `interest_week_kst + ingredient + actor/source/run 축` | 위치가중 성분 관심도와 주간 비중 |
| `category_price_reference` | `secondary_category + currency` | 카테고리 가격 중앙값과 표본 부족 fallback |
| `banner_daily` | 일자 + 브랜드/상품 + 배너 축/값/slot/성향 출처 + 정책 버전 + 실행 축 | 배너 노출·클릭·CTR과 어휘 유효성 |
| `user_trait_daily` | `trait_date_kst + user_id + trait` | 버전 가중치 기반 최근 30일 장기 성향 |
| `cross_brand_daily` | 일자 + 도착 브랜드 + 실행 축 | 실제 상품 조회 순서 기반 교차 브랜드 유입률 |
| `analytics_baseline` | `baseline_policy_version + metric_name + brand_id + algorithm` | 배너·정렬 적용 전 추천 CTR과 교차 유입률 기준선 |

`banner_daily`는 `policy_version`을 key에 둬서 배너·정렬 정책 배포 전후를 같은 Mart에서
가른다. `cross_brand_daily`는 세션 단위 중복 제거가 기준이라 정책 버전으로 쪼개지 않고
`analytics_baseline` 기간으로 가른다.

`cross_brand_daily`는 `sessionized_events.event_order`로 정렬한 `product_view`만 사용한다.
세션 최초 브랜드와 목적 브랜드가 다르면 교차 유입으로 판정하며, 같은 세션·목적 브랜드는
한 번만 센다. 추천 귀속은 목적 조회의 `recommendation_id`를 우선하고 없으면 같은
세션·상품의 선행 `recommendation_click`을 사용한다. 배너 귀속은 같은 세션·상품의 모든
선행 `banner_click`을 대상으로 한다. 추천·배너 비율은 브랜드 조회 세션 분모와 전체 교차
유입 세션 분모를 각각 보존한다.

### 적용 전 기준선

배너·정렬 정책을 켜기 전에 `analytics_baseline`을 한 번 남긴다. 세 값을 모두 주면
생성하고, 하나라도 빠지면 Job이 실패한다.

```bash
BASELINE_POLICY_VERSION=pre_banner_sort_v1 \
BASELINE_START_DATE=2026-09-01 \
BASELINE_END_DATE=2026-09-07 \
bash infra/spark/run-pipeline.sh run-batch
```

남는 값은 `recommendation_ctr`과 `cross_brand_entry_rate` 둘뿐이고 각각 분자·분모를
함께 저장한다. 배너가 없던 기간의 배너 CTR은 존재하지 않는 값이므로 만들지 않으며,
기준선에 배너 지표가 들어오면 검증 Job이 실패한다. 기준선을 만들지 않은 실행에서는
검증 Job이 경고만 남기고 통과한다.

정보 확인 단계는 성분/리뷰 Section·Content, Accordion 펼침, 리뷰 필터/상세,
매칭 성분·키워드가 있는 텍스트 선택/복사 Event로 파생한다. 상품 매출은
`purchase`의 `item_revenue`만 합산한다. `product_interest_score`는
`persona_behavior_feature_delta` 연결 전까지 NULL로 두어 단순 Event count를
최종 관심도 점수로 오해하지 않도록 했다.

Q4도 전체 snapshot `overwrite` 방식의 MVP다. 실제 운영에서는 입력 변경 범위와
Mart 재계산 범위를 함께 관리하는 증분 전략을 추가한다.

성분 Mart는 AI 벡터를 읽지 않고 `product_ingredient.csv.position_weight`를 사용한다.
성분이 없는 시드 상품 12개의 상품 전체 Event는 성분 점수와 비중 분모에서 모두
제외하며, `matched_ingredients[]` 직접 지목은 상품 연결 없이도 반영한다. 세정 상품의
기본 가중치 `0.5`는 `CLEANSING_CATEGORY_WEIGHT` 또는
`--cleansing-category-weight`로 변경할 수 있다.

가격 기준 Mart는 `dim_product.base_price`만 사용하고 할인가는 사용하지 않는다.
`secondary_category + currency`별 유효 상품이 기본 3개 미만이면 같은 통화 전체 중앙값을
사용한다. 기준은 `PRICE_MIN_SAMPLE_SIZE` 또는 `--price-min-sample-size`로 변경한다.

## 통합 검증과 관측

Spark 실행 환경에서 각 Job을 순서대로 완료한 뒤 파이프라인 불변식을 검사한다.

```bash
spark-submit streaming/jobs/validate_pipeline_job.py --require-events \
  --report-path data/validation/pipeline-report.json
```

검증 Job은 다음을 확인하고 실패 시 종료 코드 1을 반환한다.

- `cleaned_events`의 `event_id` 유일성과 null 여부
- Raw 건수가 Processed 정상/오류 결과를 수용하는지
- `duplicate_events`가 실제 canonical Event를 가리키는지
- `sessionized_events`가 cleaned Event의 1:1 투영인지
- `product_event_fact`의 product ID와 cleaned Event 참조 무결성
- `dim_brand`/`dim_product` grain과 모든 상품의 브랜드 참조 무결성
- 상품 Dimension Join 전후 row 수, 미등록 상품 ID 표본, 브랜드 스냅샷 일치
- 상품 미귀속 Event가 `brand_id=NULL`을 유지하는지
- Processed Fact·Mart에 상위 소유 주체 식별 축이 없는지
- Funnel Session, 상품 일간 Mart, Funnel 일간 Mart의 grain 유일성

K01~K16 시나리오에서 예상 Event ID·Kafka 좌표·정본 ID를 먼저 기록하고 이
검증 결과와 Kafka offset/lag를 함께 보관한다. Q1 Streaming Query의 실시간
처리율·입력 행 수·batch duration은 Spark UI 또는 `StreamingQuery` progress에서
확인하고, Collector HTTP 성공/실패와 Kafka Broker 상태는 기존
`monitoring/` Prometheus/Grafana 구성 및 Kafka 관리 명령으로 별도 확인한다.
현재 저장소에는 Spark progress를 Prometheus로 변환하는 Exporter가 없으므로
Spark 지표를 수집했다고 주장하지 않는다.
