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

## Raw 보존과 배치 증가

**Raw 파티션은 지우지 않는다 (2026-09-21 결정).** Q2가 매일 전체 스냅샷을 다시
읽는 것은 낭비가 아니라 `event_id` 정본 수렴의 조건이다. 날짜 기준으로 잘라내면
정본이 바뀐다.

### 왜 지우면 안 되는가 — 실험

Q2는 같은 `event_id` 후보 중 **`received_at`이 가장 이른 것**을 정본으로 고른다
(`clean_events_job._rank_valid_candidates`). 재전송본이 다음 날 파티션에 떨어지면
먼저 받은 쪽이 오래된 파티션에 있다.

`e2e-336-final`(105만 행)에 재전송 50건을 만들어 Q2를 두 번 돌렸다.

| 입력 | `duplicate_events` | 대상 50건의 정본 |
| --- | ---: | --- |
| 전체 스냅샷 | 50 | 먼저 받은 쪽 (09-17) |
| 옛 파티션 삭제 | **0** | 나중 받은 쪽 (09-18) |

**50건 중 50건의 정본이 바뀌었고 중복 감사 기록이 사라졌다.** 계약이
`duplicate_events`를 Audit으로 정의하고(`processed-schema.md` §5) Q5도 비정본이
거기 있는지 검사한다.

세션 정렬은 영향이 없다. `received_at`은 Q3 `session_window`의 정렬 키지만
`sequence_no`·`event_time`이 앞서고, 그 둘이 같은 행은 105만 중 **0건**이었다.
실질 피해는 감사 기록 소실 하나다.

### 재전송 창 — 지우게 될 때의 경계

재전송은 Kafka에 원본이 남아 있어야 가능하다. **토픽 보존은 24시간이다**
(`deploy/ec2-2/docker-compose.yml` 의 `KAFKA_TOPIC_RETENTION_MS` 기본값 86400000).
운영도 이 기본값으로 돌고 있고 토픽 동적 설정(`retention.ms`)도 같은 값이다
(2026-09-21 확인).

따라서 **24시간이 지난 파티션에는 중복 짝이 새로 생길 수 없다.** 언젠가 지우게 되면
`Kafka 보존 + 여유`가 근거 있는 경계다 — 임의로 정한 숫자가 아니라 Kafka 설정이
정해 주는 자연스러운 경계다. **이 값이 바뀌면 재전송 창도 같이 바뀐다.**

### 배치 시간 모델

야간 배치 실측 3회를 직선으로 맞춘 값이다 (오차 ±0.7분).

```text
배치시간(분) = 18.4 + 11.91 x 원천(M건)

  2.15M -> 44.0분   3.23M -> 57.6분   7.50M -> 107.7분
```

고정비 18.4분은 Spark 기동과 잡 전환이고, 원천 100만 건마다 11.9분이 붙는다.
**점 3개로 선형을 가정한 모델이다.** 원천이 커지면 셔플·스필로 한계 비용이
올라갈 수 있어 경고선 부근에서 다시 재야 한다.

### 마감과 감시 지점

운영 기준은 **03:00 시작 · 05:30 경고 · 06:00 실패**다 (인프라 파트 제안,
2026-09-21 합의). 별도 SLA 계약은 없고 운영 기준이다.

| 선 | 배치 시간 | 원천 |
| --- | ---: | ---: |
| 경고 05:30 | 150분 | 11.05M |
| 실패 06:00 | 180분 | 13.57M |

2026-09-21 기준 원천 7.50M · 배치 107.7분이다. AI 파트가 예고한 코호트 한 벌
(1,092,226건)을 넣으면 8.59M · 약 120.7분으로 **05:01 종료**, 경고선까지 29분
남는다. 같은 규모로 두 번 더 넣어도 경고선 전이다.

디스크는 감시만 한다 — **70%에서 경고**하고 그때 보존 구조와 기간을 다시 정한다.
2026-09-21 기준 309G 중 20G(7%)다.

### 지우게 될 때의 전제

경고선이나 디스크 70%를 넘어 삭제가 필요해지면 아래를 먼저 갖춘다.

- **일일 배치 안에 넣지 않는다.** 별도 systemd 타이머로 분리해 배치 실패와 삭제
  실패를 격리한다 (인프라 파트 방침)
- **재전송 창 안쪽은 지우지 않는다.** 창 밖만 지우면 정본이 바뀔 수 없어 정본·감사
  기록을 따로 보존할 필요가 없다. 창 안쪽까지 지우려면 그 보존 구조를 먼저 갖춘다
  (인프라 파트 전제)
- **`duplicate_events`가 0이 되는 것은 실패가 아니다.** 중복이 아예 없으면
  `cleaned_events`에도 중복이 없고 `duplicate_events`도 비어 Q5가 통과한다. 잃는 것은
  "중복이 있었다"는 이력이고 검사는 깨지지 않는다
- **과거 재생 능력을 잃는다.** Raw를 지우면 그 기간 Mart를 다시 만들 수 없다.
  압축 보관을 둘지 함께 정한다

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
`duplicate_events`에 보존한다. JSON 파싱·공통 필드·42종 Event 등록 여부와
Event-intent 조합·sequence/event index·actor-source 조합·상품 대상 Event의
`product_id`·synthetic 필수 properties 검증에 실패한 row는 원문과 좌표를
`bad_events`에 남긴다. `banner_impression`과 `banner_click`은 배너 타입·값·slot·
성향 출처와 각 intent까지 추가로 검사한다.

`user_id`는 `identity_scope`에 따라 정해진다 — 합성 로그는 `persona_id`, 로그인 사용자는
Collector가 JWT에서 뽑은 `account_id`, 비로그인 사용자는 NULL이며 `session_id`로만 본다.
합성 로그에 `account_id`가 실려 오면 `invalid_identity_scope`로 격리한다.

파이프라인 검증 Job은 synthetic 세션의 Persona 혼합, 세션 내
`sequence_no` 충돌, `simulation_run_id`별 `scenario_id`·`generator_type` 불일치를
실패로 판정한다. Raw의 동일 `event_id` 중복은 재전송 가능성을 고려해 warning으로
기록하고, `cleaned_events`의 중복은 오류로 판정한다.

현재 Q2는 전체 snapshot을 `overwrite`하는 MVP다. 운영 환경에서 Raw가 커지면
날짜/offset 범위 증분 처리와 transactional upsert를 도입하되, 정본 비교 규칙과
출력 grain은 유지한다.

Raw→Cleaned Spark 계약 테스트는 Spark 런타임에서 다음처럼 실행한다.

```bash
PYTHONPATH=. spark-submit --master local[1] \
  streaming/tests/test_raw_cleaned_spark.py
```

이 테스트는 Kafka source 형태의 입력을 사용해 Raw 원문·좌표 보존, 배너 2종 통과,
업무 중복의 정본/감사 분리, 미등록 Event·잘못된 intent·상품 누락·배너 속성 오류의
격리를 함께 확인한다. 실제 Broker와 checkpoint 재시작은 위 테스트와 별도로
로컬 Kafka/Spark Compose에서 확인한다.

## Q3 세션·상품 Fact

Q3는 Q2의 `cleaned_events`만 입력으로 사용한다. 따라서 Raw의 재전송 중복은
Q2 정본 선택 이후 downstream fact에 들어오지 않는다.

```bash
spark-submit streaming/jobs/derive_facts_job.py \
  --input-path data/processed/cleaned_events \
  --sessionized-path data/processed/sessionized_events \
  --product-fact-path data/processed/product_event_fact \
  --purchase-fact-path data/processed/purchase_fact \
  --purchase-reason-fact-path data/processed/purchase_reason_fact \
  --review-event-fact-path data/processed/review_event_fact \
  --registered-product-path batch/ingest/data/serving/registered_products.jsonl \
  --registered-product-brand-path data/reference/shop-product-brand.jsonl \
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

`purchase_fact`는 행동 `purchase`의 상품 행을 `order_id + product_id` grain으로
보존하며 Backend PAID 주문 매출·정산 Fact와 구분한다. `purchase_reason_fact`는
선택 이유를 행으로 펼치고 설문 건너뛰기는 `reason=NULL`, `skipped=true` 한 행으로
남긴다. 추천 노출·클릭의 정본은 `product_event_fact`이며 별도 중복 Fact를 만들지
않는다. `review_event_fact`는 리뷰 펼침·필터·정렬·리뷰 영역 체류의 상세 속성을
`event_id + product_id` grain으로 보존하고 성분 펼침은 제외한다.

상품 Fact와 콘텐츠 Fact의 `brand_id`는 `product_id → dim_product.brand_id` left
join으로 보강한다. `dim_brand` grain은 `brand_id`, `dim_product` grain은
`product_id`다. 매칭되지 않는 상품과 `product_id=NULL`인 플랫폼 Event는 row를
버리거나 세션의 다른 상품을 참조하지 않고 `brand_id=NULL`로 유지한다.

등록 상품은 append-only `registered_products.jsonl`에서 상품별 마지막 행을 읽고,
마지막 행이 `_op=deactivate`인 상품은 제외한다.
`--registered-product-brand-path`로 전달한 ACTIVE 쇼핑몰 상품 export의
`product_id → brand_id`를 권위 값으로 우선 사용하고, 매핑이 없는 상품만 등록 원문의
비어 있지 않은 `brand_id`를 사용한다. 브랜드 이름을 Join key나 ID로 대신 쓰지 않고
임의 ID도 만들지 않는다. 매핑 파일은 JSONL이며 각 행은
`{"product_id":"SB000001","brand_id":"쇼핑몰 DB 실제 UUID"}` 형식이다.
매핑이 없으면 NULL을 유지하고 통합 검증의 `dim_product_has_valid_brand_id`가 실패한다.

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
  --brand-daily-path data/marts/brand_daily_kpi \
  --product-repurchase-path data/marts/product_repurchase_daily \
  --brand-repurchase-path data/marts/brand_repurchase_daily \
  --purchase-reason-path data/marts/purchase_reason_daily \
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
| `brand_daily_kpi` | `event_date_kst + brand_id + actor/source/run 축` | 브랜드별 중복 제거 세션, 사용자·조회 상품 수, 상세·정보·담기 전환율 |
| `product_repurchase_daily` | `snapshot_date_kst + brand_id + product_id + actor/source/run 축` | 상품 재구매율과 재구매 간격 |
| `brand_repurchase_daily` | `snapshot_date_kst + brand_id + actor/source/run 축` | 브랜드 재구매율과 선언 restock 교차 검증 |
| `purchase_reason_daily` | `event_date_kst + brand_id + reason + actor/source/run 축` | 구매 이유 분포와 행동 추론 대조 |
| `ingredient_weekly_interest` | `interest_week_kst + ingredient + actor/source/run 축` | 위치가중 성분 관심도와 주간 비중 |
| `category_price_reference` | `secondary_category + currency` | 카테고리 가격 중앙값과 표본 부족 fallback |
| `banner_daily` | 일자 + 브랜드/상품 + 배너 축/값/slot/성향 출처 + 정책 버전 + 실행 축 | 배너 노출·클릭·CTR과 어휘 유효성 |
| `user_trait_daily` | `trait_date_kst + user_id + trait` | 버전 가중치 기반 최근 30일 장기 성향 |
| `cross_brand_daily` | 일자 + 도착 브랜드 + 실행 축 | 실제 상품 조회 순서 기반 교차 브랜드 유입률 |
| `persona_segment_daily_kpi` | `event_date_kst + brand_id + segment_type + segment_value + 실행 축` | 피부 타입·톤·교차 세그먼트별 전환 |
| `brand_price_band_daily_kpi` | `event_date_kst + brand_id + price_bin + currency + 실행 축` | 가격대별 노출·상세·담기·구매 세션 |
| `brand_cohort_dim` | `brand_id` | 브랜드를 상품 수 밴드 × 가격 구간 코호트에 배정 |
| `commons_cohort_weekly` | `snapshot_week_kst + cohort_key + metric_name + 실행 축` | **B층** 코호트별 비율 분위. 소표본·지배 셀은 억제 |
| `content_daily_kpi` | `event_date_kst + brand_id + product_id + section_id + content_kind + 실행 축` | 상품 상세 콘텐츠별 조회·체류·성분/리뷰 열람 |
| `content_conversion_daily` | `event_date_kst + brand_id + product_id + content_kind + 실행 축` | 그 콘텐츠를 본 세션의 담기율 |
| `behavior_conversion_daily` | `event_date_kst + brand_id + product_id + event_name + 실행 축` | 행동을 한 세션과 안 한 세션의 담기율 대조 |
| `friction_daily` | `event_date_kst + brand_id + product_id + section_id + content_kind + event_name + 실행 축` | 위치별 UI 마찰 Event·세션과 마찰률 |
| `exit_daily` | `event_date_kst + brand_id + product_id + 실행 축` | 체류 3초 미만 조기 이탈 세션 비율 |
| `entry_source_daily` | `event_date_kst + brand_id + entry_source + 실행 축` | 유입 경로별 상세·담기 전환 |
| `product_exit_daily` | `event_date_kst + brand_id + product_id + last_content_kind + 실행 축` | 마지막으로 본 콘텐츠 기준 이탈 지점 |
| `segment_content_daily` | `event_date_kst + brand_id + skin_type + content_kind + 실행 축` | 피부 타입별 콘텐츠 체류와 비중 |
| `segment_price_band_daily_kpi` | `event_date_kst + brand_id + segment_type + segment_value + price_bin + currency + 실행 축` | 고객군 × 가격 밴드 담기율 (S5 히트맵) |
| `event_daily` | `event_date_kst + brand_id + event_name + 실행 축` | 브랜드별 Event 볼륨. E6 event_volumes |
| `analytics_baseline` | `baseline_policy_version + metric_name + brand_id + algorithm` | 배너·정렬 적용 전 추천 CTR과 교차 유입률 기준선 |

재구매는 **서로 다른 `order_id`** 기준이다. 한 주문에 같은 상품이 여러 개 있어도 구매는
한 번이며, 브랜드 재구매는 상품이 달라도 성립하므로 상품 Mart를 합산해서 구할 수 없다.
구매 이유는 주문 단위 선언이라 다브랜드 주문에서는 각 브랜드에 한 번씩만 계상하고,
비중의 분모는 건너뛴 주문을 뺀 **응답한 주문**뿐이다.

`commons_cohort_weekly`만 **브랜드 밖으로 나가도 되는 Mart**다. 나머지는 전부 그 브랜드만
보는 A층이고, 여러 브랜드 행이 한 테이블에 있는 것은 저장 구조일 뿐 공개 범위가 아니다.
브랜드 격리는 Backend 인가가 한다. 층 경계와 억제 규칙 R1~R9는
[`../contracts/dw-schema.md`](../contracts/dw-schema.md) §2.5가 정본이다.

`brand_cohort_dim`과 `dim_brand`의 `brand_hash`를 만들려면 `COMMONS_HASH_SALT` 환경 변수가
필요하다. 비어 있으면 Q3가 시작 단계에서 실패한다 — 소금 없는 해시를 조용히 만들면 보호가
있는 것처럼 보이기 때문이다. `infra/spark/.env.example`을 참고한다.

매출·정산 금액은 이 Mart들의 범위가 아니다. Backend의 PAID 주문 상품이 정본이며
DW는 금액을 복제하지 않는다.

콘텐츠 Mart 3종은 **상품 조회 세션을 공통 분모**로 쓴다. `content_daily_kpi`의
`product_view_sessions`·`ingredient_view_sessions`·`review_view_sessions`는 상품 단위라
`content_kind`마다 같은 값이 반복되며, 그 축으로 합산하면 같은 세션을 여러 번 센다.
`content_conversion_daily`는 분모가 "그 콘텐츠를 본 세션"이라 분리된 Mart다.
`behavior_conversion_daily`는 `done_sessions + not_done_sessions`가 상품 조회 세션과
같아야 하고, 네 행동 Event는 `product_event_fact`에 없어 `sessionized_events`에서 읽는다.

E6 마트 3종은 **상세를 연 세션(상세 ∪ 퀵룩)** 을 공통 분모로 쓴다. `friction_daily`는
`event_name`을 key에 두는 롱 포맷이라 마찰 Event가 0건이어도 행이 남는다 —
`dead_click`은 생성기가 만들지 않아 항상 0이고, `rage_click`은 부정 시드만 내므로
시드를 빼면 0이 된다. `exit_daily`의 `exit_summary`는 세션 단위 Event라 상품이 없어
그 세션이 상세를 연 상품 전부에 귀속하며, **상품 축으로 합산하면 세션이 부푼다.**
`entry_source_daily`는 브랜드 단위라 `product_id`가 key에 없다 — `product_impression`에
`entry_source`가 없어 노출 단계는 이 축으로 가를 수 없다.

`product_exit_daily`는 `exit_daily`와 다른 Mart다. 그쪽은 "얼마나 빨리 나갔나",
이쪽은 "어디에서 멈췄나"를 잰다. `exit_summary.last_content_kind`가 값을 싣지 않아
(실측 0/1,000) 콘텐츠 Event의 마지막 시각으로 판정하며, 세션·상품마다 행이 하나다.

`segment_content_daily`의 `dwell_share` 분모는 **그 피부 타입의 총합**이라 한 타입
안에서만 합이 1이다. 입력 `section_dwell_agg`에 `is_seeded`가 없어
`sessionized_events`에서 시드 세션 목록을 만들어 `session_id`로 뺀다 — 재생 데이터에
시드 세션 행이 993건 있다.

`product_daily_kpi`의 `quick_look_close_open_detail_count`는 `product_event_fact`의
`close_reason` 컬럼에서 나온다. **Q3를 다시 돌려야 그 컬럼이 생긴다.**

`segment_price_band_daily_kpi`는 `persona_segment_daily_kpi`·
`brand_price_band_daily_kpi` 중 어느 쪽에도 축을 얹을 수 없어 나눈 Mart다. 세션 하나가
여러 가격대를 밟고 동시에 `skin_type` 행과 `skin_tone` 행에 들어가므로, **축을 걷어낸
합계가 세션을 중복으로 센다.** 세 Mart를 서로 대체하지 않는다.

표본 미달 셀을 Mart가 지우지 않는다 — 화면이 `n<50`을 비우고 `n<200`을 흐리게 한다.
`commons_cohort_weekly`의 억제와 다르다. 그쪽은 다른 브랜드에게 보이는 B층이고
이것은 자기 브랜드만 보는 A층이다.

`event_daily`는 다른 Mart와 달리 **Event를 고르지 않고 전부 센다.** "어제 로그가
정상적으로 들어왔나"를 보는 진단 지표라서, `event_count`의 합이 `cleaned_events`의 관측
Event 수와 정확히 같아야 한다 — Q5가 이것을 검사한다.

**`brand_id`가 NULL인 행을 지우지 않는다.** `section_dwell`·`page_view`·`session_start`처럼
상품에 귀속되지 않는 Event가 재생 데이터 기준 전체의 59%다. 지우면 볼륨 진단이 성립하지
않고 합계 검사도 깨진다. 화면이 브랜드로 거르면 자연히 빠진다.

`banner_daily`는 `policy_version`을 key에 둬서 배너·정렬 정책 배포 전후를 같은 Mart에서
가른다. `cross_brand_daily`는 세션 단위 중복 제거가 기준이라 정책 버전으로 쪼개지 않고
`analytics_baseline` 기간으로 가른다.

탐색 배정 비중(`banner_explore_impression_share_is_near_twenty_percent`)은 **실사용자
(`actor_type='user'`) 노출만** 모집단으로 쓴다. `trait_source='explore'`를 만드는 주체가
화면뿐이기 때문이다 — 추천 서버는 `explore`를 아예 내보내지 않고(`batch/serving/banners.py`의
trait_source 계약: "프론트 플랜의 무작위 탐색은 서버가 아니라 화면 몫"), 합성 로그의
`explore`는 생성기가 정한 값이라 검증 대상이 아니다. 합성 로그만 재생한 실행에서는
실사용자 표본이 0이라 이 검사가 면제되고, 프론트가 탐색 배너를 내보내기 시작하면
자동으로 다시 평가된다. `coldstart`는 분모에서 빼는 규칙을 그대로 유지한다.

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
`frontend/src/types/log.ts`의 `EVENT_WEIGHT`를 원본으로 삼아 Event 가중합으로
낸다. 가중치를 주지 않고 부르면 NULL이다 — 단순 Event count를 관심도 점수로
오해하지 않게 하기 위해서다.

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
- `purchase_fact`, `purchase_reason_fact`, `review_event_fact` grain과 필수값
- 추천 Fact 식별자와 위치, 행동 구매 `item_revenue` 계산 일치
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

## 행동 로그 생성과 재생

### 1. 로그 생성

생성기 입력은 전부 저장소 안에 있다. EC2에서 받아올 필요 없이 로컬에서 만든다.

| 입력 | 위치 |
| --- | --- |
| 페르소나 PC 9,900 · PA 100 · 성향 | `simulator/personas/data/` |
| 상품 카탈로그 200 | `batch/ingest/data/products_200.json` |
| 등록 상품 · 시연 상품 | `batch/ingest/data/serving/registered_products.jsonl`, `frontend/src/mocks/` |

```bash
py -3 simulator/generator/gen_behavior_logs.py \
  --limit 1000 --currency KRW \
  --scenario-id normal_day --simulation-run-id e2e_336 \
  --out data/replay/behavior_logs_e2e_336.jsonl
```

`--currency KRW`가 금액의 정본 형식이다 (`dw-schema.md` §3.2). 붙이지 않으면 기본이
USD라 `add_to_cart`가 deprecated 입력인 `price_usd`를 싣고, `view_cart`·
`begin_checkout`·`purchase`의 `currency`가 `"KRW"`가 아니어서 계약 검사에 걸린다.

`--limit`은 페르소나 수다. 1,000명이 약 104만 Event · 635MB다 (2026-09-11 실측).
표본은 기본이 층화(`--sample stratified`)라 적은 수로도 stratum 분포가 유지된다.
`--include-agents`는 PA 100명을 넣는 스위치인데, PA는 정성 축이라 정량 지표 실행에는
넣지 않는다.

### 2. Collector를 거쳐야 하는 이유

**생성기 출력을 Kafka에 직접 넣으면 Q2가 전량 격리한다.** 생성기가 내지 않고
Collector만 찍는 필수 필드가 둘 있다.

| 필드 | 누가 넣나 |
| --- | --- |
| `received_at` | Collector — `KafkaEventPublisher.java`의 `clock.instant()` |
| `event_index` | Collector — 배치 안에서의 순번 |

둘 다 Q2의 판정에 쓰인다. `received_at`은 `REQUIRED_FIELDS`(`clean_events_job.py:129`)
이자 `timestamp_ok`·`timestamp_format_ok`의 대상이고, `event_index`는
`event_index_ok`(`:288`)가 non-null과 0 이상을 요구한다. 없으면 모든 Event가
`bad_events`로 간다.

`kafka_cluster_id`·`kafka_topic`·`kafka_partition`·`kafka_offset` 넷도 필수지만
이쪽은 Q1이 Kafka 메타데이터에서 읽으므로 payload에 없어도 된다. `source`는
생성기가 안 싣지만 Q2가 `actor_type`으로 보정한다(`:272`).

과거 로그를 재생하면 `received_at`이 "지금"이라 `latency_ms`가 크게 나온다. Q5에
지연 상한 검사가 없으므로 검증에는 영향이 없고, 값은 기록만 된다.

### 3. Collector 재생

`streaming/tools/replay_collector.py`는 `.jsonl` 또는 `.jsonl.gz`를 한 줄씩 읽어
Collector 상한인 100건 이하로 전송한다. 429/502/503과 전송 오류는 지수 백오프로
재시도하며, 최종 보고서의 `accepted + rejected + abandoned = total`을 검사한다.
202 부분 수락은 건수와 거부 코드로 따로 기록한다. 503은 일부 Kafka ACK 뒤에도
발생할 수 있으므로 전체 배치를 재시도하고, Q2의 `event_id` 중복 제거를 최종
멱등성 경계로 둔다.

전송 전 파일 검증:

```bash
py -3 -m streaming.tools.replay_collector data/replay/behavior_logs_e2e_336.jsonl \
  --inspect-only \
  --report-path data/validation/e2e-336-inspection.json
```

`--expected-sha256`을 주면 파일이 만든 그대로인지 함께 본다. 다른 사람이 만든
로그를 받아 돌릴 때 쓴다.

Collector 재생:

```bash
py -3 -m streaming.tools.replay_collector data/replay/behavior_logs_e2e_336.jsonl \
  --url http://localhost:8080/api/events --batch-size 100 \
  --report-path data/validation/e2e-336-replay.json
```

보고서의 `accepted`가 생성 로그의 Event 수와 같아야 한다. 다르면 Q1을 시작하기
전에 원인을 본다 — 적재가 덜 된 채로 Mart를 만들면 어느 단계에서 샜는지
Q5로는 구분되지 않는다.

기존 적재 결과와 섞지 않고 검증하려면 Q1 시작 전에 Raw와 checkpoint, Q2~Q5의
공통 루트를 함께 분리한다. `run-pipeline.ps1`과 `run-pipeline.sh`는
`PIPELINE_DATA_ROOT`를 Q2~Q5 공통 루트로 사용한다. Q1은 같은 하위 경로를
`RAW_EVENTS_PATH`, `RAW_EVENTS_CHECKPOINT_PATH`에 지정한다.

경로만 나누면 충분하지 않다. Q1은 Kafka Topic을 처음부터 다시 읽으므로
**공용 `activity-events`에 남아 있던 Event가 그대로 섞인다.** 검증 실행에는
Topic도 따로 만들고 Collector와 Q1에 같은 이름을 준다.

```powershell
$env:PIPELINE_DATA_ROOT='/opt/project/data/recommend-validation'
$env:RAW_EVENTS_PATH='/opt/project/data/recommend-validation/raw_events'
$env:RAW_EVENTS_CHECKPOINT_PATH='/opt/project/data/recommend-validation/checkpoints/raw-events'
$env:REGISTERED_PRODUCT_BRAND_PATH='/opt/project/data/reference/shop-product-brand.jsonl'
$env:ACTIVITY_EVENTS_TOPIC='activity-events-validation'
./infra/spark/run-pipeline.ps1 start-q1
```

#### 실행 순서

Collector는 compose에 없다. Host에서 따로 띄우고, Q1과 **같은 Topic**을 준다.
`SHOP_BACKEND_JWT_SECRET`이 없으면 Collector가 기동 자체를 못 한다(32자 이상).
재생은 토큰 없이 보내므로 `account_id`는 NULL이고 합성 로그는 `identity_scope=persona`가 된다.

```powershell
$env:SHOP_BACKEND_JWT_SECRET='<32자 이상>'
$env:ACTIVITY_EVENTS_TOPIC='activity-events-validation'
cd backend; ./gradlew.bat bootRun
```

1. `gen_behavior_logs.py`로 로그 생성 (§1)
2. `run-pipeline.ps1 up` — Kafka·Spark
3. Topic 생성 (위 이름으로)
4. `run-pipeline.ps1 start-q1`
5. Collector 기동
6. `replay_collector.py`로 재생 (§3)
7. Q1이 빈 배치에 도달하면 `run-pipeline.ps1 stop-q1`
8. `run-pipeline.ps1 run-batch` — Q2~Q5
9. `build_ddl.py --marts <루트>/marts`로 `contracts/dw/schema.sql` 재생성

9번을 빠뜨리면 Mart에 컬럼이 늘어도 MySQL 테이블 정의가 따라오지 않는다.
`schema.sql`은 Mart Parquet에서 컬럼을 읽는 생성물이라 실행이 끝나야 뽑힌다.
`--check`를 주면 파일을 고치지 않고 차이만 본다.

> **Windows에서는 `run-pipeline.ps1`을 쓴다.** Git Bash로 `run-pipeline.sh`를 돌리면
> 컨테이너 안 경로(`/opt/spark/bin/spark-submit`)를 Windows 경로로 바꿔 버려 실패하고,
> `MSYS_NO_PATHCONV=1`로 끄면 이번에는 Host쪽 compose 파일 경로가 깨진다.
> 그리고 `run-batch`에 `*>&1`이나 `2>&1`을 붙이면 안 된다. PowerShell 5.1이 네이티브
> 명령의 stderr를 ErrorRecord로 감싸서 Spark의 첫 INFO 로그에 스크립트가 멈춘다.
> Q2만 돌고 Q3~Q5가 조용히 빠진다.

검증·재생 보고서는 `.gitignore`의 `data/` 아래에 생성되므로 로컬/Jira 증빙으로만
사용하고 저장소에는 커밋하지 않는다.

이번 파일은 배너 24,441건 모두 `policy_version`이 없다. NULL 그룹으로
`banner_daily`를 생성하는 것은 허용하되 정책 전후 비교에는 사용하지 않는다.
추천 응답의 `algorithm`은 원문 그대로 보존하며 `policy_version`으로 복사하지 않는다.
