# DW / Mart 적재 및 Dashboard 설계

작성일: 2026-09-02  
최종 정적 검증: 2026-09-02
상태: Spark 결과와 DW 저장 구조 확정, Dashboard Mart·KPI 후보는 AI·추천 협의 대기

## 1. 문서 역할

DW 저장 계층과 공통 규칙, Dimension·Mart 후보는
[`../../contracts/dw-schema.md`](../../contracts/dw-schema.md)를 단일 출처로 사용한다.
이 문서는 저장 흐름과 책임 경계를 선택한 이유, Dashboard 후보 연결, 구현 상태와
검증 계획을 설명한다.

Processed Dataset 계약은 [`../../contracts/processed-schema.md`](../../contracts/processed-schema.md),
Spark 처리 근거는 [`spark-processing-design.md`](./spark-processing-design.md)를 따른다.

## 2. 저장 및 조회 흐름

```text
Backend → Kafka → Spark
  → Delta raw_events
  → Delta cleaned_events / Processed Dataset
  → Delta marts
  → MySQL dw schema
  → Dashboard API
```

- EC2-1 서비스 영역에는 Backend, MySQL, Redis를 둔다.
- EC2-2 데이터 영역에는 Kafka, Spark, Delta Lake를 둔다.
- Delta Lake의 `marts`는 Spark 계산 결과와 재처리 기준을 보존한다.
- MySQL `dw` schema는 Dashboard가 빠르게 조회할 KPI Mart를 제공한다.
- 별도 S3/EBS/공유 저장소가 없는 현재 구성은 단일 데이터 EC2 장애를 견디는 HA
  구조가 아니다.

현재 Q1은 로컬 Parquet와 checkpoint를 사용하는 PoC 구현이다. Delta 적재,
Delta `MERGE`, MySQL serving projection은 아직 구현·검증되지 않았으므로 현재
Parquet를 최종 저장 방식이나 exactly-once 저장소로 해석하지 않는다.

## 3. 설계 원칙

| 원칙 | 적용 |
| --- | --- |
| 중복 제거 후 집계 | Raw를 직접 집계하지 않고 `cleaned_events`와 파생 Dataset만 사용 |
| grain 우선 | 서로 다른 Processed Dataset은 목표 grain으로 먼저 집계한 뒤 결합 |
| Event일과 Funnel일 분리 | 일반 성과는 Event 발생일, Funnel은 최초 단계 도달일 기준 |
| Tenant 격리 | 모든 Mart가 `tenant_id`를 집계 축으로 가지며 이 값으로만 격리 |
| Web/Synthetic 분리 | `actor_type`, `source`, `simulation_run_id`로 필터 |
| 상품 속성 스냅샷 | Mart에 `category_id`, `brand_id`를 집계 시점 값으로 보존 |
| NULL 의미 보존 | 입력 부재와 분모 0을 숫자 0으로 꾸미지 않음 |
| 관심도는 행동 가중 | 조회 수가 아니라 `EVENT_WEIGHT` 합산. 음수를 절단하지 않음 |
| 표기 병합 선행 | `brunette`→`brown` 등을 집계 전에 적용 |
| 생성 표본 구분 | `simulation_run_id → dim_simulation_run.persona_source`로 구분 |

Raw에서 `scenario_id`, `simulation_run_id`, `generator_type`은 `properties` 안에 있고
Processed에서 분석 컬럼으로 승격된다. PA와 PC는 모두 `source=simulator`이며
`generator_type=agent_llm`, `python_batch`로 구분한다.

## 4. Dashboard Mart 후보

Dashboard에 제공할 정확한 지표와 최종 Mart는 아직 확정하지 않았다. 아래 표와 KPI는
Processed 결과로 산출·저장할 수 있는 후보이며, 추천 품질·AI 평가 결과와 함께
팀에서 우선순위를 정한 뒤 채택한다. 따라서 이 절은 이번 Jira에서 물리 구현을
강제하는 계약이 아니다.

| 화면 | 주요 질문 | Mart / Dimension |
| --- | --- | --- |
| Overview | 방문·조회·장바구니·구매 추이, 수집 상태 | `product_daily_kpi`, `funnel_daily_kpi`, `realtime_event_stats`, `realtime_bad_event_stats` |
| 상품 분석 | 상품별 관심과 전환 | `product_daily_kpi`, `recommendation_daily_kpi`, `dim_product` |
| 사용자 행동 | 단계별 도달과 이탈 | `funnel_daily_kpi` |
| 리뷰·성분 | 콘텐츠 열람·체류·관심 | `content_daily_kpi`, `dim_product` |
| 검색 | 검색량, 결과 품질, 클릭 전환 | `search_daily_kpi` |
| Persona·Scenario | 고객군·실행별 행동 차이 | `persona_segment_daily_kpi`, `scenario_daily_kpi`, Simulation Dimension |

노출률, 실제 구매율, 추천 성과, 콘텐츠 관심도 등 어떤 지표를 최종 채택하더라도
서로 다른 Processed grain을 먼저 목표 grain으로 집계한 뒤 결합하고, Delta Mart를
계산 결과의 기준으로, MySQL `dw`를 조회 projection으로 사용하는 원칙은 유지한다.

### KPI 후보

| KPI | 산식 | Mart |
| --- | --- | --- |
| 상품 CTR | `product_click_count / product_impression_count` | `product_daily_kpi` |
| 추천 CTR | `recommendation_click_count / recommendation_impression_count` | `recommendation_daily_kpi` |
| 상세 진입률 | `product_view_count / product_impression_count` | `product_daily_kpi` |
| 장바구니 전환율 | `add_to_cart_sessions / product_view_sessions` | `funnel_daily_kpi` |
| 구매 전환율 | `purchase_sessions / product_view_sessions` | `funnel_daily_kpi` |
| 장바구니→구매 | `purchase_sessions / add_to_cart_sessions` | `funnel_daily_kpi` |
| 성분·리뷰 열람률 | 각 콘텐츠 열람 세션 / 상품 조회 세션 | `content_daily_kpi` |
| 단계별 이탈률 | `1 - next_step_sessions / current_step_sessions` | `funnel_daily_kpi` |
| 검색→클릭 | `search_click_session_count / search_session_count` | `search_daily_kpi` |
| 평균 체류시간 | `dwell_ms_sum / section_view_sessions` | `content_daily_kpi` |
| 콘텐츠 관심도 | `processed-schema.md` §13.1 | `content_daily_kpi` |
| 상품 관심도 | `Σ EVENT_WEIGHT x 발생 수` | `product_daily_kpi` |

Quick Look은 Funnel 단계가 아니라 상품 노출 뒤 비교 분기다. 기능 판단 시
`actor_type=user`에서 Quick Look 사용/미사용 arm의 표본 수와 장바구니 전환율을
함께 제시한다.

## 5. 구현 상태와 미확정 항목

| 항목 | 현재 상태 | 후속 확인 |
| --- | --- | --- |
| Collector payload | 관련 구현 병합 완료. Event 단위, `received_at`, `source`, `request_id`, `event_index` 보강과 Kafka key=`session_id`를 코드에서 재확인 | 실제 Kafka payload E2E 캡처 |
| Kafka | 기본 topic `activity-events`, key `session_id` | 환경별 설정 확인 |
| Raw Q1 | 로컬 Parquet + checkpoint, `source`는 `raw_value` 내부 | Raw projection에 `source` 반영 필요 |
| Processed | 논리 계약 작성 및 현재 Spark projection 정적 대조 완료 | Delta `printSchema()`와 row-level E2E 대조 |
| Delta marts | 저장 방향 합의 | Spark/Scala/delta-spark 호환성과 MERGE 검증 |
| MySQL `dw` | Dashboard serving 역할 합의 | DDL, 인덱스, 적재 주기, upsert 방식 결정 |
| 검색·결제 Event | 일부 provisional | 화면·Collector 구현 후 key와 optional 값 재검증 |
| bad event | Spark 격리분만 관측 가능 | Collector reject 관측은 Backend metric 또는 별도 저장 필요 |
| Dashboard Mart·KPI | 저장 가능한 후보 Schema 작성 | 추천·AI 담당과 지표 우선순위·최종 grain 합의 후 확정 |

`search_query_hash`의 정규화·hash 규칙, 실제 Web의 안정적인 `user_id`, `cart_id`,
운영 저장 경로는 구현 전 확정이 필요하다. 이 항목들은 이미 정한 Schema를 다시
묻는 것이 아니라 아직 물리 구현에 없는 값과 책임을 정하기 위한 후속 사항이다.

## 6. E2E 검증

1. 확정 Collector 구현이 병합된 상태에서 `POST /api/events → Kafka` payload를
   캡처하고 Event 단위·key·서버 metadata를 확인한다.
2. 같은 `event_id`를 재입력해 `cleaned_events`가 계약의 대표 1건만 남기는지 본다.
3. `source`와 synthetic runtime metadata가 Processed 컬럼으로 승격되는지 본다.
4. `items[]`가 상품 row로 explode되고 `order_value`가 상품 수만큼 중복 합산되지
   않는지 본다.
5. 각 Processed Dataset을 목표 Mart grain으로 먼저 집계해 row 증폭이 없는지 본다.
6. Delta `marts`와 MySQL `dw`의 key별 row 수·count·rate·amount를 대조한다.
7. 분모 0인 비율이 NULL이고, count 부재는 0인지 확인한다.
8. Dashboard API에서 일자·상품·actor/source·simulation run 필터 결과를 대조한다.
9. checkpoint 삭제와 Kafka replay 후 Delta key 중복 및 KPI 변화 여부를 검증한다.
10. PA `agent_llm`과 PC `python_batch`가 같은 run 차원 규칙으로 분리되는지 본다.

## 7. 구현 문서 분리 기준

- 논리 grain·key·컬럼 변경: `contracts/dw-schema.md`
- Delta table property·partition·MERGE 구현: Spark/Delta 구현 문서 또는 코드
- MySQL DDL·인덱스·upsert: Backend/인프라 구현 문서 또는 migration
- 화면별 기간 비교·정렬·랭킹: Dashboard API/화면 명세
