# Spark Processed 처리 설계

작성일: 2026-09-01
상태: 현재 `dev` 구현 gap 1차 검수 완료, Delta 전환·E2E 검증 대기
계약 원본: [`contracts/processed-schema.md`](../../contracts/processed-schema.md)

## 1. 문서 목적

이 문서는 Collector를 거쳐 Kafka에 들어온 Raw Event를 Spark에서 정제, 중복 제거,
세션화, 집계하는 처리 흐름과 설계 근거를 설명한다. 현재 구현 상태와 목표 계약 사이의
차이 및 E2E 검증 항목도 이 문서에서 추적한다.

Dataset별 grain, key, 컬럼, 타입, nullable 및 partition은
[`contracts/processed-schema.md`](../../contracts/processed-schema.md)를 단일 출처로
사용한다. 이 문서에는 동일한 Schema 표를 복제하지 않는다.

```text
Frontend
→ Collector
→ Kafka raw_events
→ Spark Processed Layer
→ DW/Mart Layer
→ Dashboard
```

## 2. 입력 계약과 확인된 구현

| 항목 | 기준 |
| --- | --- |
| Raw Event 공통 계약 | [`contracts/event-schema.json`](../../contracts/event-schema.json) |
| Event별 properties·Trigger | [`event-taxonomy-trigger-schema.md`](./event-taxonomy-trigger-schema.md), 계약 분리 전 전환 위치 |
| Kafka payload | Front JSON을 유지하고 Collector가 `received_at`, `source`, `request_id`, `event_index` 보강 |
| 수집 API | `POST /api/events`, body는 `{ schema_version, events: [ ...LogEnvelope ] }` |
| Schema version | 현재 E2E 구현은 `0.2.0-draft`; 변경은 Raw 계약과 함께 검토 |
| Kafka message grain | 현재 Backend 구현은 Event 1건 |
| Kafka key | `session_id` |
| Raw 중복 | 수신 원본을 보존하고 Processed에서 `event_id` 기준 제거 |
| Synthetic 식별 | `actor_type`, `source`, `persona_id`, `simulation_run_id`, `generator_type` 사용 |

Event별 properties와 Trigger는 아직 `docs/analytics/`에 남은 전환 예외다. 실행 검증
범위에서는 `contracts/event-schema.json`을 우선하며, 후속 문서 정리에서 계약 부분을
`contracts/`로 분리한다.

## 3. 처리 단계

```text
raw_events
├─ invalid → bad_events
└─ valid
   ├─ duplicate candidate → duplicate_events
   └─ canonical event → cleaned_events
      ├─ sessionized_events
      ├─ product_event_fact
      ├─ search_event_fact
      ├─ section_dwell_agg → content_interest_fact
      ├─ funnel_session_fact
      └─ persona_behavior_feature_delta
```

Raw 저장 계약은 Raw Event Log Draft MR의 `raw-event-storage.md`, Dashboard용 MySQL
Mart 설계는 [`dw-schema.md`](./dw-schema.md)에서 다룬다. Raw MR이 병합되면 이 문서의
직접 링크를 연결한다. Processed Dataset은 Raw와 Mart 사이에서 타입, 중복, 순서 및
분석 grain을 보장한다.

## 4. 핵심 처리 원칙

### 4.1 시간 기준

- `event_time`: 사용자가 행동한 `occurred_at`을 UTC timestamp로 정규화한 값
- `received_at`: Collector 수신 시각
- `processed_at`: Spark 처리 시각
- KPI 순서와 날짜는 `event_time`을 기준으로 한다.
- Dashboard 일간 집계는 `Asia/Seoul` 날짜를 별도로 파생한다.
- timezone이 없는 입력 timestamp는 정상 Event로 보정하지 않고 오류로 분리한다.

행동 시각, 수집 시각, 처리 시각을 분리해야 지연 Event와 처리 지연을 구분할 수 있다.

### 4.2 중복 제거와 재실행

Frontend의 `sendBeacon` 또는 keepalive 재시도 때문에 같은 `event_id`가 여러 Kafka
record로 들어올 수 있다. Raw에는 모두 보존하고 `cleaned_events` 전에 정본 1건을
선택한다.

정본 정렬 기준은 다음과 같다.

```text
received_at ASC
→ kafka_topic ASC
→ kafka_partition ASC
→ kafka_offset ASC
```

선택되지 않은 후보는 `duplicate_events`에 물리 좌표와 함께 남긴다. 서로 다른
`event_id`로 발행된 동일 행동은 이 규칙으로 판별할 수 없으므로 Producer가 재전송 시
같은 `event_id`를 유지해야 한다.

Delta 저장 시 같은 처리 범위를 다시 실행해도 Dataset key 기준 동일 결과로 수렴해야
한다. Kafka 좌표 중복과 `event_id` 업무 중복은 서로 다른 문제로 검증한다.

### 4.3 Raw에서 승격하는 값

Processed에서는 조회·조인·필터에 반복 사용되는 값만 typed column으로 승격하고 전체
`properties`는 JSON으로 보존한다.

- 공통 Envelope: Event, 사용자, 세션, 페이지, 시간 축
- Collector metadata: `received_at`, `source`, `request_id`, `event_index`
- Synthetic metadata: `scenario_id`, `simulation_run_id`, `generator_type`
- 상품·콘텐츠 축: `product_id`, `section_id`, `content_kind`, `position` 등
- Kafka 추적 축: topic, partition, offset, timestamp, key

정확한 컬럼과 nullable은 Processed 계약을 따른다. Event별 필수 properties가 없거나
타입 변환이 불가능하면 `bad_events`로 분리한다.

### 4.4 `source`와 Synthetic 처리

`source`는 Collector가 보강한 Kafka payload 값을 우선 사용한다. 이전 데이터 등에서
누락된 경우에만 `actor_type='synthetic'`이면 `simulator`, 그 외에는 `web`으로
fallback하고 사용 건수를 품질 지표로 남긴다.

Synthetic Event는 다음 조건을 만족해야 한다.

- `actor_type='synthetic'`
- `persona_id`, `scenario_id`, `simulation_run_id`, `generator_type` 존재
- `generator_type`은 `python_batch` 또는 `agent_llm`
- 분석용 `user_id`는 `persona_id`로 파생
- 같은 `(simulation_run_id, session_id)` 안에서 `persona_id`가 하나로 유지
- 같은 `(simulation_run_id, session_id, sequence_no)` 충돌 없음

PA 경로는 FE logger를 바꾸지 않고 runner가 Collector 전송 시점에 metadata를 보강한다.
persona 선택 전 발생한 Event는 Synthetic 필수값을 만족하지 않으므로 PA Event로
전송하지 않는다.

### 4.5 세션 순서와 Fact grain

세션 순서는 `sequence_no → event_time → received_at → event_id`로 복원한다.
`sequence_no` gap은 품질 표시 대상이지 자동 Event 생성 근거가 아니다.

Base Dataset은 Event 1건 grain을 유지한다. 상품 배열이 있는 Event만
`product_event_fact`에서 item 단위로 펼친다. 서로 다른 grain의 Fact를 row-level로
직접 Join하지 않고, 목표 Mart grain으로 먼저 집계한 뒤 결합한다.

Quick Look은 정규 Funnel 단계가 아니라 `product_impression` 이후의 비교 분기로
분석한다. `section_dwell`은 Front에서 여러 delta Event가 들어오므로 Spark에서 동일
콘텐츠 grain으로 합산한다.

## 5. 분석 목표와 Dataset 연결

| 분석 목표 | 주 입력 Dataset |
| --- | --- |
| 상품·추천 CTR | `product_event_fact` |
| 검색 후 상품 클릭 | `search_event_fact`, `product_event_fact` |
| 상품 조회→장바구니→구매 | `funnel_session_fact` |
| 성분·리뷰·콘텐츠 관심 | `section_dwell_agg`, `content_interest_fact` |
| Persona 행동 Feature | `persona_behavior_feature_delta` |
| 처리 실패·중복 감사 | `bad_events`, `duplicate_events` |

행동 가중치의 실행 원본은 `frontend/src/types/log.ts`이며, Product/User Vector 결합은
[`recommendation-io-spec.md`](../../contracts/recommendation-io-spec.md)를 따른다.
Processed에서는 행동 Feature 입력 delta만 만들고 Vector 자체를 저장하지 않는다.

## 6. 현재 `dev` 구현과 목표 계약의 차이

2026-09-01 `dev`의 `streaming/` 구현을 기준으로 확인한 결과다. 이 표는 구현 현황이며
계약을 대체하지 않는다.

| Dataset | 현재 구현 | 남은 차이 |
| --- | --- | --- |
| `raw_events` | Kafka 원문과 metadata를 Parquet로 저장 | Delta 전환, 확정 Raw 컬럼 projection |
| `bad_events` | Q2에서 생성 | 목표 오류·추적 컬럼 정렬 |
| `duplicate_events` | Q2에서 생성 | Delta key 기반 재실행 검증 |
| `cleaned_events` | Q2에서 생성 | payload `source` 우선, Dimension·품질 컬럼 보완 |
| `sessionized_events` | Q3에서 생성 | 목표 순서·late Event 규칙 검증 |
| `product_event_fact` | Q3에서 생성 | item grain과 상품 Dimension 보강 |
| `funnel_session_fact` | Q4에서 생성 | 목표 Funnel 단계·컬럼 보완 |
| `search_event_fact` | 미구현 | Trigger와 원천 필드 확인 후 구현 |
| `section_dwell_agg` | 미구현 | delta 합산 grain 구현 |
| `content_interest_fact` | 미구현 | 관심도 산식과 vocab 연결 |
| `persona_behavior_feature_delta` | 미구현 | 추천 계약 기준 delta 구현 |

현재 Q1~Q4는 주로 Parquet output을 사용한다. 목표 저장 엔진은 Delta Lake이며 실제
Spark·Scala·delta-spark 호환성과 Kafka→Delta→MySQL 흐름을 검증해야 한다.

## 7. 구현 전에 닫아야 하는 의존성

| 항목 | 필요한 결정 또는 입력 |
| --- | --- |
| Delta 실행 환경 | Spark·Scala·delta-spark 호환 버전과 EC2-2 경로 |
| 상품 Dimension | 상품 데이터 원천과 갱신 방식 |
| 실제 사용자 ID | 로그인·비로그인 식별 정책 |
| 검색·구매 Event | 실제 UI Trigger와 `search_id`, `cart_id`, `order_id` 생성 정책 |
| Mart 적재 | Delta 결과를 MySQL `dw`에 반영하는 주기와 책임 경계 |

이 항목은 계약에 임의의 값을 채우지 않는다. 담당 구현이 정해지거나 실제 원천을
확인한 뒤 계약과 설계에 함께 반영한다.

## 8. 구현·E2E 검증 체크리스트

1. 실제 Delta Table의 `printSchema()`가 Processed 계약과 일치한다.
2. Dataset별 unique key 중복과 partition NULL이 0건인지 확인한다.
3. Raw 중복 후보가 정본 1건과 `duplicate_events`로 결정론적으로 나뉜다.
4. 재실행 전후 Dataset key와 집계값이 동일하다.
5. 오류 Event가 원문과 Kafka 좌표를 포함해 `bad_events`에 남는다.
6. `source` payload 우선과 fallback 건수를 확인한다.
7. PA와 PC Event가 Synthetic 필수 metadata를 유지한다.
8. 세션 순서, sequence gap, late Event 판정이 샘플 시나리오와 일치한다.
9. 상품 Dimension Join 전후 row 수가 의도치 않게 증가하지 않는다.
10. Delta 결과에서 MySQL `dw` Mart와 Dashboard KPI까지 추적 가능하다.

위 검증이 끝나기 전까지 `contracts/processed-schema.md`의 상태는 Draft로 유지한다.
