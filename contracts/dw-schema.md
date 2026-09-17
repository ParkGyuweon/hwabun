# DW / Mart Schema Contract

작성일: 2026-09-02  
최종 정적 검증: 2026-09-07
상태: 통합 쇼핑몰의 브랜드·상품 귀속 계약 및 물리 구현 반영

## 1. 범위와 우선순위

이 문서는 [`processed-schema.md`](./processed-schema.md)의 Processed Dataset을
**Parquet**으로 보존하고 MySQL `dw`로 제공하는 저장 계층, 책임 경계와 공통 물리
규칙을 확정한다. Dimension과 Mart의 grain, 입력, key, 컬럼, 논리 타입 및 nullable은
현재 Dashboard 후보를 구현 가능성 관점에서 정리한 초안이다.

- **Parquet `marts`가 계산 결과의 기준 저장소다.** `build_marts_job.py`가
  `mode("overwrite")`로 전체를 다시 쓰고, 파티션 컬럼은 Mart마다 §4가 정한다.
- MySQL `dw` schema는 Dashboard API 조회용 serving projection이다.
- 물리 파티션, 인덱스, MySQL DDL은 구현 단계에서 확정된 저장 계층과 공통 규칙을
  보존하는 범위로 정한다.
- 처리 근거, KPI 화면 연결, 현재 구현 상태와 검증 계획은
  [`../docs/analytics/dw-design.md`](../docs/analytics/dw-design.md)에서 설명한다.

§2의 입력 grain·공통 타입·NULL·집계 원칙과 Parquet→MySQL 책임 경계는 이번 작업의
확정 범위다. §3~§5의 Dimension·Mart·KPI는 저장 가능성을 확인하기 위한 후보이며,
Dashboard에 실제 제공할 지표는 추천·AI 담당과 합의한 뒤 별도 확정한다.

**Delta Lake는 이번 MVP의 범위가 아니다.** 매 실행이 전체 재계산·전체 덮어쓰기라
Delta의 `MERGE`(증분 갱신)와 스키마 진화를 쓸 일이 없고, 트랜잭션 로그·타임 트래블이
주는 이득보다 의존성과 운용 비용이 크다. `deploy/ec2-2/README`도 "Delta Lake나 다중
서버 분산 저장·고가용성 구성은 포함하지 않는다"로 같은 범위를 적고 있다. 증분 적재가
필요해지는 시점에 다시 판단한다 (2026-09-15 결정).

## 2. 공통 계약

### 2.1 입력

| 입력 | grain | 용도 |
| --- | --- | --- |
| `cleaned_events` | `event_id` | 정상 Event 수와 실시간 통계 |
| `product_event_fact` | `event_id + item_index + product_id` | 상품·추천·구매 집계 |
| `review_event_fact` | `event_id + product_id` | 리뷰 펼침·필터·정렬·리뷰 영역 체류 상세. **현재 이 Fact를 읽는 Mart가 없다** — 아래 |
| `section_dwell_agg` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 체류 검증·재집계 |
| `content_interest_fact` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 콘텐츠 관심 집계 |
| `purchase_fact` | `order_id + product_id` | 행동 Event 기반 구매 전환·재구매 집계. 매출·정산에는 사용 금지 |
| `purchase_reason_fact` | `order_id + reason` | 구매 이유 집계, 행동 추론 대조 |
| `funnel_session_fact` | `session_id + product_id` | 단계 도달·이탈 집계 |
| `bad_events` | 격리 Event 1건 | Spark에서 관측한 오류 집계 |

모든 Mart는 `event_id` 중복 제거가 끝난 Processed Dataset만 입력으로 사용한다.

**`review_event_fact`는 소비자가 없는 Fact다** (2026-09-16). Q3가 만들고 Q5가
검증하지만 읽는 Mart가 없다. 원래 소비자로 예정됐던 구매자 리뷰 Mart
(S15P21A306-168)가 데이터 파트 범위에서 빠졌기 때문이다 — 리뷰 원문과 분류 결과는
`shop_backend`가 관리하고 Spark는 리뷰 **행동 Event**만 집계한다. 그 집계는 이미
§4.4 `review_view_sessions`·§4.19·§4.20 `review_filter_apply`에 들어가 있고,
그쪽은 `review_event_fact`가 아니라 `content_interest_fact`와 `sessionized_events`를
읽는다.

**지우지 않고 두는 이유**는 이미 만들어져 있고 Q5가 검증하고 있어서, 되살리는
비용이 두는 비용보다 크기 때문이다. 리뷰 행동을 따로 보는 Mart가 필요해지면
재료가 이미 있다. **보호 장치나 소비 중인 입력으로 오해하지 않는다.**
서로 다른 grain의 입력은 목표 Mart grain으로 각각 먼저 집계한 뒤 결합한다.
`section_dwell_agg`와 `content_interest_fact`의 nullable `product_id`는 상품 목록의
플랫폼 공통 섹션을 보존한다. 이 row는 플랫폼 탐색 분석용이며 상품 Dimension Join이나
상품·브랜드 KPI 입력으로 사용하지 않고, 직전 상품 또는 세션 내 상품으로 보정하지
않는다.

### 2.2 공통 타입과 NULL

| 필드군 | 논리 타입 | nullable | 규칙 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | KST 일간 집계일 |
| `funnel_date_kst` | date | N | 최초 Funnel 단계 도달 시각의 KST 집계일 |
| `event_minute_kst` | timestamp | N | KST minute truncate |
| `brand_id` | string | Y | Event 대상 상품의 브랜드. 상품 미귀속 Mart는 NULL 가능 |
| `actor_type` | string | N | `user`, `synthetic` |
| `source` | string | N | MVP: `web`, `simulator` |
| `generator_type` | string | Y | `python_batch`, `agent_llm`; Web은 NULL |
| `scenario_id` | string | Y | Web은 NULL 가능 |
| `simulation_run_id` | string | Y | Web은 NULL 가능 |
| `*_count`, `*_sessions` | bigint | N | 집계 결과가 없으면 `0` |
| `*_rate`, `*_score`, 평균·지연 | double | Y | 분모 0 또는 입력 부재면 NULL |
| 금액 | decimal(18,2) | Y | `currency`와 함께 해석 |
| `mart_processed_at` | timestamp | N | Mart 생성·갱신 시각 |

**Persona Agent(PA)와 프로그램 생성(PC)은 `generator_type`으로 가른다.** 둘 다
`actor_type = synthetic`이라 그 축으로는 갈리지 않는다. PA가 `agent_llm`,
PC가 `python_batch`다. `actor_type`에 값을 더하지 않는 이유는 그 축이 모든 Mart의
key에 있어서, enum이 바뀌면 전 Mart의 grain이 같이 바뀌기 때문이다.
`generator_type`도 2026-09-16부터 모든 Mart의 key에 있으므로(Jira 324) 화면은
이 축으로 PA를 걸러낼 수 있다.

모든 비율은 `numerator / NULLIF(denominator, 0)`으로 계산한다. Kafka payload의
`source`를 우선 사용하며 누락된 과거 데이터만 `synthetic → simulator`, 그 외
`web`으로 보정한다.

### 2.3 관심도 산식

`*_interest_score` 컬럼은 조회 수가 아니라 **행동 가중 관심도**다. 단순 조회 순위는
"인기 상품이 인기 상품이다"만 말하고 어떤 행동이 관심을 뜻하는지 구분하지 못한다.

| 컬럼 | 정의 |
| --- | --- |
| `content_interest_score` | [`processed-schema.md`](./processed-schema.md) §13.1 결과를 Mart grain으로 합산 |
| `product_interest_score` | `Σ EVENT_WEIGHT[event_name] x 해당 Event 발생 수` (상품 grain) |
| `avg_interest_score`, `avg_product_interest_score`, `avg_content_interest_score` | 위 값을 세션 수로 나눈 평균 |
| `category_interest_score` | segment x 카테고리로 `product_interest_score`를 합산 |

행동 가중치 `EVENT_WEIGHT`의 실행 원본은 `frontend/src/types/log.ts`이며 이 계약에
숫자를 복제하지 않는다. `add_to_cart`가 가장 크고 `remove_from_cart`·`rage_click`
등은 음수이므로 **점수가 음수가 될 수 있다.** 0으로 잘라내지 않는다. 담았다 뺀 상품과
아무 반응 없는 상품은 다른 신호다.

`product_interest_score`는 정규화하지 않은 절대값이라 노출이 많은 상품이 자동으로
높다. Dashboard가 순위로 쓸 때는 노출 수를 함께 제시한다.

### 2.4 표기 정규화

원천 데이터의 표기 변형은 집계 전에 병합한다. Persona 속성과 상품 리뷰 통계가 같은
어휘를 써야 segment Join이 성립하기 때문이다.

| 대상 | 병합 |
| --- | --- |
| `hair_color` | `brunette` → `brown` |
| `eye_color` | `Grey` → `gray` |
| `skin_tone` | 원본 14종을 5버킷으로 |

규칙 원본은 [`persona-schema.md`](./persona-schema.md) §3.2다.

**Persona 쪽은 이미 병합되어 있으나 상품 리뷰 통계에는 남아 있다.**
`products_200.json`의 `_review_stats.segment_counts.hair_color`에 `brunette` 키를
가진 상품이 200개 중 137개다. `dim_product`와 segment Mart를 만들 때 병합하지 않으면
같은 사람이 `brown`과 `brunette`로 나뉘어 집계된다.

### 2.5 공개 층위와 공유 규칙

브랜드 50개가 한 인프라를 나눠 쓴다. 브랜드 하나의 로그는 표본이 작아 혼자서는 판단이
안 되고, 합치면 판단이 된다. 그런데 합치는 순간 내 숫자가 경쟁자에게 보인다.

그래서 데이터를 한 덩어리로 보지 않고 **세 층**으로 가른다. 근거와 화면 설계는
[`../docs/dashboard/collective-insight-data-boundary.md`](../docs/dashboard/collective-insight-data-boundary.md)에
있고, 이 절은 그중 **Mart가 지켜야 하는 것**만 계약으로 옮긴 것이다.

| 층 | 누가 보나 | 담는 것 | 담지 않는 것 |
| --- | --- | --- | --- |
| **A** 내부 자산 | 그 브랜드만 | 절대 건수·상품 단위 수치·세션 | — |
| **B** 벤치마크 | 그 브랜드 (자기 위치만) | 코호트 분위(중앙값·25·75) | 절대 건수, 다른 브랜드 식별자, 상품 단위 |
| **C** 커먼즈 | 모든 브랜드가 같은 것을 | 시장 전체 집계 | 브랜드 축 자체 |

Mart를 이 층에 배정한다.

| 층 | Mart |
| --- | --- |
| A | `product_daily_kpi`, `brand_daily_kpi`, `funnel_daily_kpi`, `persona_segment_daily_kpi`, `brand_price_band_daily_kpi`, 재구매 2종, `purchase_reason_daily`, `banner_daily`, `cross_brand_daily`, `user_trait_daily` |
| B | `commons_cohort_weekly` (§4.18) |
| C | `ingredient_weekly_interest` — 브랜드 축이 없고 주 단위다 |

A층 Mart가 한 테이블에 여러 브랜드 행을 담는 것은 **저장 구조일 뿐 공개 범위가 아니다.**
브랜드 격리는 Backend 인가가 한다(§6-7). B·C층은 그와 달리 **Mart 자체가 다른 브랜드에게
보여도 되는 형태**여야 한다.

#### 2.5.1 공유 규칙 R1~R9

사람이 판단하지 않는다. `build_marts` 단계에서 규칙으로 건다.

| # | 규칙 | 값 | 상태 |
| --- | --- | --- | --- |
| R1 | 최소 브랜드 수 | 셀에 브랜드 **5 미만**이면 억제 | 적용 |
| R2 | 최소 표본 | 비율 분모 **200 미만**이면 `is_sample_sufficient=false` | 적용 (아래 근거) |
| R3 | 지배 억제 | 한 브랜드가 셀 분모의 **50% 초과**면 억제 | 적용 |
| R4 | 비율·분위만 | 절대 건수·합계 컬럼을 B·C층 Mart에 두지 않는다 | 적용 |
| R5 | 해시 코호트 | 원 `brand_id`를 B·C층 Mart에 두지 않는다 | 적용 (아래 주의) |
| R6 | 지연 발행 | C층은 주 단위 | 적용 — B층도 주 단위다 |
| R7 | 기여 조건 | 옵트아웃 브랜드는 B·C층을 보지 못한다 | **미구현** |
| R8 | 축별 동의 | 옵트인을 지표 묶음 단위로 | **미구현** |
| R9 | 대체 상품 익명화 | 이름을 지우고 성분·가격대·카테고리 차이만 | 해당 Mart 없음 |

**R1·R3는 값을 NULL로 만들고 행은 남긴다.** 행이 사라지면 "억제됐다"와 "코호트가 없다"를
구분할 수 없다. 빈칸으로 보여주는 것이 정직하다.

**R2의 200은 주간 분모 기준이다.** 일간에 걸면 재생 데이터 336행 중 5행(1%)만 통과한다.
주간으로 접으면 브랜드 31/56(55%)이 통과한다. 그래서 B층 Mart의 grain을 일간이 아니라
주간으로 잡았다 (2026-09-15 실측).

**R7·R8은 동의를 받을 곳이 없어 구현하지 않는다.** 온보딩에 동의 단계가 없다.
`commons_participating`은 전원 `true`로 채우고, 동의 UI가 생기면 그 값이 갈린다.
없는 동의를 있는 것처럼 두지 않는다.

**R5 주의 — 해시는 익명화가 아니다.** 브랜드가 56개고 목록이 공개돼 있으면 어떤 해시든
전수 대입으로 뒤집힌다. `brand_hash`는 표기 규칙이고 **실제 보호는 R1과 R3가 한다.**
소금값은 `COMMONS_HASH_SALT` 환경 변수로 받고 저장소에 두지 않는다. 값이 없으면 Job이
실패한다 — 소금 없는 해시를 조용히 만들면 보호가 있는 것처럼 보인다.

## 3. Dimension

### 3.1 `dim_brand`

```text
grain/key = brand_id
source = Backend 브랜드 등록 정보
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `brand_id` | string | N | 브랜드 식별자 |
| `brand_name` | string | N | 브랜드 표시명 |
| `brand_hash` | string | N | Commons Mart용 비가역 가명 |
| `commons_participating` | boolean | N | 억제 규칙을 충족한 공유 집계 대상 여부 |
| `created_at` | timestamp | N | 브랜드 등록 시각 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`brand_hash`는 `sha256(COMMONS_HASH_SALT + brand_id)`의 앞 16자다. 소금값은 환경 변수로
받고 저장소에 두지 않으며, 없으면 Job이 실패한다. **해시가 익명화를 보장하지는 않는다** —
브랜드 목록이 공개돼 있으면 전수 대입으로 뒤집힌다. 실제 보호는 R1·R3 억제가 한다(§2.5.1).

**이 컬럼은 현재 읽는 소비자가 없다.** R5가 요구하는 "B·C층에 원 `brand_id`를 두지
않는다"는 유일한 B층 Mart인 `commons_cohort_weekly`(§4.18)가 브랜드 식별자를 아예
싣지 않는 것으로 이미 충족된다. `brand_hash`가 있는 곳은 이 표와 `brand_cohort_dim`
(§3.7)뿐이고 **둘 다 같은 행에 `brand_id`를 싣는 A층 테이블**이라, 해시가 그 자리에서
가리는 것은 없다. MySQL projection 대상도 아니다.

그런데도 컬럼과 소금 요구를 남겨 둔 이유는, C층 지표가 붙으면 브랜드 단위 B층 행이
생길 수 있고 그때 소금이 이미 고정돼 있는 편이 낫기 때문이다. **보호 장치로 오해하지
않는다** — 지금 이것은 표기 규칙이다. 존치 여부는 기획 문서(프론트 작성)의 R5 문구와
함께 재검토 대상이다.

`commons_participating`은 현재 전원 `true`다. 옵트인을 받을 온보딩 단계가 없어서
R7·R8을 구현하지 않았다. 동의 UI가 생기면 이 값이 갈린다.

산출 규칙은 `brand_cohort_dim`(§3.7)과 같아야 한다. 두 곳에서 따로 계산하면 조용히
갈라진다.

브랜드 계정과의 1:1 인증 매핑은 Backend가 소유하고 DW에 복제하지 않는다.
원본 `brand_id`는 다른 브랜드에게 노출하지 않는다.

### 3.2 `dim_product`

```text
grain/key = product_id
source = batch/ingest/data/products_200.json, 입점 브랜드 등록 상품, Processed dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `product_id` | string | N | 상품 ID |
| `product_name` | string | N | 상품명 |
| `product_source` | string | N | `seed_catalog`, `brand_registered` |
| `brand_id`, `brand_name` | string | N | 브랜드 식별자·표시명 |
| `primary_category`, `secondary_category`, `tertiary_category` | string | Y | 카테고리 계층 |
| `category_id` | string | Y | Dashboard 필터 ID |
| `category_path` | array<string> | Y | 카테고리 경로 |
| `base_price` | decimal(18,2) | Y | 기준 가격. **원화**다 |
| `source_price_usd` | decimal(18,2) | Y | 세포라 원천 가격. 정본이 아니라 출처 보존용 |
| `currency` | string | Y | 가격 통화. 현재 `KRW` |
| `rating` | double | Y | 평균 평점 |
| `rating_source` | string | Y | `observed`, `injected`. 주입값을 실측과 섞지 않는다 |
| `review_count`, `loves_count` | bigint | Y | 리뷰·관심 수 |
| `skin_type_tags`, `concern_tags`, `ingredient_ids` | array<string> | Y | 상품 속성 |
| `caution_ingredient_count` | int | Y | 주의 성분 수 |
| `updated_at` | timestamp | Y | 갱신 시각 |

가격 정본은 **원화**다 (Jira 302). 추천 어휘집 0.7의 `price_bin` 경계가 원화이므로
카탈로그가 달러로 남으면 가격대 Mart가 환율을 다시 들고 있어야 한다. 환율이 여러 곳에
흩어지면 같은 상품이 화면·추천·대시보드에서 다른 가격대로 잡힌다.

산출 규칙은 `batch/jobs/product_encoder.price_krw_of`와 **같아야 한다.** `price_krw`가
있으면 그 값이고, 없으면 `price_usd × 1340.86`을 100원 단위로 반올림한다. 환율과 반올림
단위는 `contracts/localization/products-ko.json`의 `_meta`와 같다 — 화면 표시 가격과
어긋나지 않게 하기 위해서다. 두 곳이 갈리면 조용히 다른 구간이 된다.

`source_price_usd`는 세포라 원천값 보존용이다. 정본이 아니므로 집계에 쓰지 않는다.

**행동 Event의 금액 정본도 원화로 확정했다** (S15P21A306-303, 2026-09-16 프론트
합의). 신규 Event는 담기·빼기에 `unit_price` + `currency='KRW'`를 쓰고,
`cart_value`·`order_value`·`paid_value`·`items[].unit_price`도 원화로 싣는다.
생성기는 `--currency KRW`에서 이 형식을 지원하며(Jira 334), 환산은 이 Dimension과
같은 `price_krw_of` 규칙을 쓴다. 생성기의 기본 통화 전환은 AI 파트와 별도로 합의한다.

**Fact·Mart는 금액을 환산하지 않는다.** 받은 값을 그대로 싣고 `currency`를 함께
보존한다. Mart에서 다시 환산하면 환율이 또 한 곳에 생겨 화면과 갈라진다.
`product_event_fact.unit_price`는 Event의 `unit_price`를 먼저 보고 없으면 deprecated
입력 `price_usd`로 떨어진다. 이 폴백은 과거 로그 전환 기간에만 유지하며, Fact 컬럼은
`unit_price` 하나로 유지된다.

**통화가 섞이는 것은 grain이 막는다.** 금액을 합산하는 Mart는 전부 `actor_type`·
`source`·`generator_type`을 key에 둬서, 프론트(`user`/`web`)와 생성기
(`synthetic`/`simulator`) 행이 같은 칸에 들어가지 않는다. 그래도 같은 실행 축
안에서 두 통화가 나오면 합계가 조용히 망가지므로 Q5가 혼합을 검사한다 —
조회·담기 쪽은 `product_daily_currency_is_unambiguous`, 결제 쪽은
`purchase_fact_currency_is_unambiguous`가 본다. 후자는 `purchase_fact`를 보는데,
그 Fact가 §4.15·§4.16·§4.17 셋의 공통 입력이라 한 번 검사하면 셋이 다 덮인다.

**기존 2026-09-11 재생 데이터는 `currency`가 전부 NULL이다.** 당시 생성기가
`add_to_cart`에 `price_usd`만 싣고 `currency`를 보내지 않았기 때문이다. Jira 336에서
원화 로그를 전체 재생성해 `unit_price` + `currency='KRW'`로 교체한다. 재생성 전까지
통화 검사는 **NULL을 통과시키고 값이 둘 이상일 때만 실패**한다 — 값이 없는 것과
섞인 것은 다르다.

### 3.3 `dim_persona_segment`

```text
grain/key = segment_type + segment_value
source = bridge_persona_segment
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `segment_type` | string | N | Persona 계약의 허용 segment type |
| `segment_value` | string | N | segment 값 |
| `display_name`, `source` | string | Y | 표시명·원천 |
| `population_count` | bigint | Y | 해당 표본의 Persona 수 |
| `persona_source` | string | Y | 모집단 계산 표본 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`bridge_persona_segment`의 grain과 컬럼은
[`persona-schema.md`](./persona-schema.md)의 정의를 그대로 사용한다. Attribute
Affinity는 상품 축이 있으므로 이 Dimension에 저장하지 않는다.

### 3.4 `dim_date`

```text
grain/key = event_date_kst
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_date_kst` | date | N | 기준일 |
| `day_of_week` | int | N | 월요일 1 |
| `week_start_date`, `month_start_date` | date | N | 주·월 시작일 |
| `quarter` | string | N | 분기 |
| `is_weekend` | boolean | N | 주말 여부 |

### 3.5 `dim_event`

```text
grain/key = event_name
source = event-properties-schema.md
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_name` | string | N | 공식 Event 이름 |
| `intent` | string | N | 공식 intent |
| `priority` | string | N | `P0`, `P1`, `P2` |
| `ga4_event_name` | string | Y | GA4 매핑 |
| `is_dashboard_core` | boolean | N | 핵심 KPI 사용 여부 |
| `description` | string | Y | 설명 |

### 3.6 Simulation Dimension projection

`dim_scenario`와 `dim_simulation_run`의 grain, 필수 필드와 허용값은
[`persona-schema.md`](./persona-schema.md)의 `scenario`, `simulation_run` 계약을
따른다. DW에는 해당 구조를 같은 key로 projection하며 `updated_at`을 선택적으로
추가할 수 있다. Event payload에는 `persona_source`를 반복 저장하지 않고
`simulation_run_id → dim_simulation_run.persona_source`로 조회한다.

### 3.7 `brand_cohort_dim`

```text
grain/key = brand_id
source = dim_product, contracts/product-feature-vocab.json
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `brand_id` | string | N | 브랜드 식별자 |
| `brand_hash` | string | N | §3.1과 같은 산출 규칙 |
| `product_count` | bigint | N | 카탈로그의 상품 수 |
| `product_count_band` | string | N | `1` · `2-3` · `4-10` · `11+` |
| `dominant_price_bin` | string | Y | 상품이 가장 많은 가격 구간. 전 상품의 가격이 결측이면 NULL |
| `dominant_secondary_category` | string | Y | 상품이 가장 많은 2차 카테고리 |
| `cohort_key` | string | Y | `{product_count_band}\|{dominant_price_bin}`. 구간이 NULL이면 NULL |
| `commons_participating` | boolean | N | §3.1과 같다. 현재 전원 `true` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**코호트는 "비슷한 처지의 브랜드"다.** 상품 16개짜리 브랜드와 1개짜리 브랜드를 같은
잣대로 재면 비교가 의미를 잃는다. 그래서 규모와 가격대로 묶고, 그 안에서만 분위를 낸다.

**축은 상품 수 밴드 × 가격 구간 두 개다.**

`collective-insight-data-boundary.md` L190은 `product_count_band`를 `1–15 / 16–50 / 51+`로
제안했으나 **이 카탈로그에서는 축이 상수가 된다** — 브랜드 56개 중 55개가 1–15에 들어가고
최대 상품 수가 16개다. 실측 분포로 다시 잡았다 (2026-09-15).

| band | 브랜드 수 |
| --- | --- |
| `1` | 19 |
| `2-3` | 17 |
| `4-10` | 17 |
| `11+` | 3 |

**카테고리를 축에 넣지 않는다.** 3축으로 가면 R1(브랜드 5 미만 억제)에서 56개 중 21개
(37%)만 살아남아, 억제 규칙이 이 기능의 대상인 소규모 브랜드를 정확히 지운다. 2축이면
**31개(55%)다** — 구현 후 실측값이고, 3축의 21개는 착수 전 추정이다. 코호트 17개 중
브랜드 5개 이상인 것이 5개이고 그 코호트에 속한 브랜드가 31개다.
`dominant_secondary_category`는 화면 설명용으로 남기되 `cohort_key`에는 넣지 않는다.

가격 구간은 [`product-feature-vocab.json`](./product-feature-vocab.json)의
`price_bin_edges`를 읽는다. 숫자를 여기에 복제하지 않는다 — 추천 CBF 피처·배너 축·상품
등록 화면이 같은 값을 쓰므로 갈라지면 같은 이름의 가격대가 두 벌이 된다.

**동률이면 낮은 구간을 고른다.** 상품 2개가 각각 다른 구간이면 판정이 흔들리지 않게
규칙 하나로 고정한다.

`dim_product`에서만 파생하고 Event를 읽지 않는다. `category_price_reference`와 같은
성격이라 Mart 단계(Q4)가 만든다.

**상위 코호트 롤업은 구현하지 않는다.** R1이 "상위 코호트로 롤업"을 말하지만, 롤업 계층을
정의하려면 어느 축을 먼저 버릴지 정해야 하고 그 판단은 화면이 붙어 실제 빈칸 비율을 본
뒤가 낫다. 후속으로 둔다.

## 4. 일간 Mart 후보

아래 Mart는 현재 Dashboard 요구를 저장 구조에 투영한 후보안이다. 지표 채택 전에는
물리 Table 생성 계약으로 해석하지 않는다. 채택 시 표의 `key` 전체를 복합 key로
사용하고, `scenario_id`, `simulation_run_id`가 NULL인 Web 행도 같은 grain 규칙으로
집계한다.

### 4.0 시드 Event 제외 범위

`is_seeded=true`인 Event는 생성기가 Persona의 사전 선호를 주입한 표식이라 관측된
행동이 아니다(`processed-schema.md`, `event-properties-schema.md` §3.14·§7-8). 아래가
제외 여부의 정본이다.

| Mart | 시드 | 근거 |
| --- | --- | --- |
| `funnel_session_fact`, `product_daily_kpi`, `funnel_daily_kpi`, `brand_daily_kpi`, `cross_brand_daily` | 제외 | 전환 퍼널. 긍정 시드는 조회 없는 담기를, 부정 시드는 담기 없는 조회를 내서 분자·분모를 양방향으로 왜곡한다 |
| `product_repurchase_daily`, `brand_repurchase_daily`, `purchase_reason_daily` | 제외 | 구매 행동. 같은 원칙 |
| `banner_daily` | 제외 | 노출·클릭 행동. 시드는 배너 Event를 내지 않아 실제 차이는 없다 |
| `ingredient_weekly_interest` | 제외 | 탐색으로 드러난 관심을 재는 지표다 |
| `analytics_baseline` | 제외 | 위 Mart의 기준선이라 같은 모집단을 써야 한다 |
| `event_daily` | 제외 | 관측된 로그 볼륨을 재는 진단 지표다. 시드는 생성기가 주입한 표식이지 방문이 아니다 |
| `persona_segment_daily_kpi`, `brand_price_band_daily_kpi`, `segment_price_band_daily_kpi` | 제외 | 세그먼트·가격대 전환 지표. 퍼널과 같은 원칙 |
| `content_daily_kpi`, `content_conversion_daily`, `behavior_conversion_daily` | 제외 | 콘텐츠를 읽고 담았는지를 재는 지표. 시드는 조회 없이 담기를 내서 "콘텐츠를 안 봐도 담는다"를 만든다 |
| `friction_daily` | 제외 | **부정 시드가 `scroll_backtrack`·`rage_click`을 직접 낸다**(§3.14). 재생 데이터의 `rage_click` 43건이 전부 시드라, 빼지 않으면 마찰이 생성기 산물로만 채워진다 |
| `exit_daily`, `entry_source_daily` | 제외 | 이탈·유입 경로 전환. 퍼널과 같은 원칙 |
| `product_exit_daily` | 제외 | 이탈 지점. 부정 시드는 담기 없는 조회를 내서 읽지 않은 콘텐츠를 이탈 지점으로 만든다 |
| `segment_content_daily` | 제외 | **입력 `section_dwell_agg`에 `is_seeded`가 없다.** `sessionized_events`에서 시드 세션 목록을 만들어 `session_id`로 뺀다 |
| `user_trait_daily` | **유지** | 장기 성향이 재려는 것이 바로 주입된 선호다. 서빙은 scope로 가른다 — 아래 |
| `category_price_reference`, `brand_cohort_dim` | 해당 없음 | 카탈로그 파생이라 Event를 읽지 않는다 |
| `commons_cohort_weekly` | 해당 없음 | 시드를 이미 뺀 `brand_daily_kpi`를 입력으로 쓴다 |

`user_trait_daily`의 시드 유지는 **결정됐다** (2026-09-15, Jira 306). 실회원에게는
시드가 없고, Persona 응답에 주입된 선호가 드러나는 것은 시연에서 보여주려는 바이므로
Mart에서 빼지 않는다. **대신 서빙에서 `actor_type`으로 가른다** — 추천 서버는
`actor_type='user'` 행만 읽고 `identity_scope`를 `account` → `persona` 순으로 찾는다
(`recommendation-io-spec.md` 장기 성향 절).

따라서 이 Mart를 읽는 쪽은 **반드시 `actor_type`으로 좁혀야 한다.** 좁히지 않으면
합성 Persona 행이 실회원 응답에 섞인다. MySQL projection이 `actor_type`을 포함한
전체 컬럼을 싣는 이유도 이것이다 (§7.2.1).

#### 4.0.1 `hist:` 세션 — 시드가 아닌 과거 구매

생성기는 재구매 마트를 채우려고 **과거 구매 이력 세션**을 따로 만든다. `session_id`가
`hist:{run}:{persona}:{product}` 형태이고, restock은 `#restock{n}`이 붙는다
(`gen_behavior_logs.py` `history_session_id`).

**이 세션은 `is_seeded=false`다** (2026-09-16, Jira 327). 시드로 두면 위 표의 제외
규칙에 걸려 `product_repurchase_daily`·`brand_repurchase_daily`·`purchase_reason_daily`가
다시 0행이 되기 때문이다. 데이터 파트 요청으로 그렇게 정했다.

**그래서 이 세션도 퍼널 불변식을 지켜야 한다.** 관측으로 세는 이상 `상세 조회 ≥ 담기 ≥
구매`가 성립해야 한다. 2026-09-17 스모크에서 이 전제가 깨져 있는 것이 드러났다 — 당시
`hist:` 세션은 `page_view`·`add_to_cart`·`begin_checkout`·`purchase`·
`purchase_reason_select`만 내고 **`product_view`를 내지 않았다.** 상세를 열지 않고 담고
산 것이 되어 `add_to_cart_sessions > detail_view_sessions`가 됐다.

| 실측 (페르소나 20명, 21,258 Event) | |
| --- | --- |
| `hist:` 세션 | 26개 · Event 129건 |
| 비시드 `purchase` 중 `hist:` 비중 | 25 / 36 (69%) |
| 불변식이 깨진 Mart | `funnel_daily_kpi` 26 · `brand_daily_kpi` 24 · `product_daily_kpi` 28 · `persona_segment_daily_kpi` 74 · `brand_price_band_daily_kpi` 26 · `segment_price_band_daily_kpi` 52 |

**Mart에서 `hist:`를 걸러내는 방식은 쓰지 않는다.** 걸러내면 재구매 마트가 0으로
돌아가 327이 되돌아간다. 이력 세션이 최소 퍼널(`product_view` → `add_to_cart` →
`purchase`)을 갖추는 것이 정본이고, 그 책임은 생성기에 있다.

Q5의 `*_counts_are_bounded` 계열이 이것을 검사한다. 이력 세션을 새로 만들거나 형태를
바꿀 때 이 검사가 먼저 걸린다 — 생성기 쪽 자가검사는 properties 층만 보므로 퍼널
불변식은 여기서만 걸린다.


### 4.1 `product_daily_kpi`

```text
key = event_date_kst + brand_id + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, purchase_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통 계약 | key 규칙 | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `purchase_count`, `purchase_quantity` | bigint | N | Event·수량 집계. `purchase_count`는 `order_id` 기준 고유 주문 수 |
| `variant_select_count`, `quick_look_close_open_detail_count` | bigint | N | 옵션 왕복과 퀵룩 → 상세 전환. 상품 진단용 |
| `wishlist_count` | bigint | N | 찜 **추가** 수. `wishlist_toggle`의 `action = add`만 |
| `quick_look_sessions`, `product_view_sessions`, `detail_view_sessions`, `add_to_cart_sessions`, `remove_from_cart_sessions`, `purchase_sessions`, `unique_user_count`, `session_count` | bigint | N | 세션·사용자 집계 |
| `product_ctr`, `detail_entry_rate`, `add_to_cart_rate`, `purchase_rate`, `product_interest_score` | double | Y | 비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`detail_view_sessions`는 상품 상세(`product_view`)와 Quick Look(`quick_look`) 중 하나
이상을 연 고유 세션이다. 둘 다 연 세션도 한 번만 센다. §4.14와 같은 정의다.

`wishlist_count`는 토글 횟수가 아니라 **추가 횟수**다. `wishlist_toggle` 하나가
추가와 해제를 모두 싣기 때문에 가르지 않으면 관심 신호가 아니라 버튼을 누른
횟수가 된다. `action`이 없는 옛 로그는 해제를 보낸 적이 없어 추가로 본다.

`variant_select_count`와 `quick_look_close_open_detail_count`는 **세션이 아니라
횟수**다. 같은 세션이 옵션을 다섯 번 고르면 5다 — 옵션 왕복이 많다는 것 자체가
진단 신호라서 세션으로 접으면 뜻이 사라진다. `quick_look_close_open_detail_count`는
`quick_look_close.close_reason = 'open_detail'`인 Event 수이고 `quick_look_count`를
넘을 수 없다. `close_reason`은 `product_event_fact`가 싣는다 — Mart가 properties를
다시 파싱하면 원천이 둘이 된다.

**`add_to_cart_rate`와 `purchase_rate`의 분모는 `detail_view_sessions`다.**
`product_view_sessions`를 분모로 두면 Quick Look에서 담은 세션이 분자에만 들어가
비율이 1.0을 넘는다. 실제로 그랬다 — 데이터 235 재생에서 1,248행 중 323행(26%)이
1.0을 초과했고 최댓값이 6.0이었다. 브랜드·퍼널 Mart는 235에서 고쳤는데 상품 Mart가
빠져 있었고, 검증 Job에 이 Mart의 비율 검사가 없어 드러나지 않았다 (Jira 277).

`product_ctr`와 `detail_entry_rate`의 분모는 `product_impression_count`로 **Event 수**다.
세션 수가 아니다. 노출 대비 클릭·상세 진입은 노출 하나하나를 모수로 보는 지표이고,
이름이 §4.14의 `detail_entry_rate`(세션 기준)와 같지만 분모가 다르다. 두 Mart의 값을
같은 지표로 나란히 놓지 않는다.

`currency`는 key가 아니라 대표값 하나다. Event의 `currency`는 담기·결제 Event에만 붙고
조회 Event에는 없어서, key에 올리면 통화 없는 조회 행과 결제 행이 갈려 세션 집계가
무너진다. 대신 한 상품·하루에 통화가 둘 이상 섞이지 않는 것을 검증 Job이 막는다
(`product_daily_currency_is_unambiguous`). 섞이면 `revenue_amount`가 두 통화를 더한다.

### 4.2 `recommendation_daily_kpi`

**미구현이고 현재 소비자가 없다** (2026-09-16). 재료(`product_event_fact`)는 다
있어 만들 수는 있지만 `dashboard-mart-api-spec.md`의 어느 엔드포인트도 읽지 않는다.
추천 성과 중 화면이 쓰는 것은 `analytics_baseline`(§4.13)의 `recommendation_ctr`
뿐이고, 그것은 배너 도입 전후를 비교하는 기준선 스냅샷이다. 일간 추이가 필요해지면
그때 만든다.

```text
key = event_date_kst + brand_id + recommendation_id + list_id + algorithm + product_id + context_product_id + position + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string/int | `list_id`, `context_product_id`, scenario/run만 Y | 집계 축 |
| `recommendation_impression_count`, `recommendation_click_count`, `unique_session_count` | bigint | N | 추천 성과 |
| `recommendation_ctr` | double | Y | 클릭/노출 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.4 `content_daily_kpi`

```text
key = event_date_kst + brand_id + product_id + section_id + content_kind + actor_type + source + generator_type + scenario_id + simulation_run_id
input = content_interest_fact, section_dwell_agg, funnel_session_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | section/content/scenario/run만 Y | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `co_visible_le2_dwell_ms_sum` | bigint | N | 겹쳐 보인 체류를 뺀 합계. 항상 `dwell_ms_sum` 이하 |
| `section_view_count`, `section_view_sessions`, `dwell_ms_sum`, `accordion_expand_count`, `text_selection_count`, `text_copy_count`, `matched_ingredient_count`, `ingredient_view_sessions`, `review_view_sessions`, `product_view_sessions` | bigint | N | 콘텐츠 행동 집계 |
| `avg_dwell_ms_per_session`, `ingredient_view_rate`, `review_view_rate`, `content_interest_score` | double | Y | 평균·비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`dwell_ms_sum`은 `content_interest_fact`를 기본 원천으로 사용한다.

`co_visible_le2_dwell_ms_sum`은 같은 원천의 같은 이름 컬럼을 그대로 합산한다.
한 화면에 블록이 여러 개 보이면 같은 시간이 블록마다 중복 귀속되는데, 그 몫을
걷어낸 값이다. 산출 규칙과 상한 2의 한계는 `processed-schema.md` §12에 있다 —
**여기서 다시 거르지 않는다.** 두 곳에서 걸면 기준이 갈린다.
`section_dwell_agg`와 동시에 합산하지 않는다. `content_interest_fact`가
`section_dwell_agg`를 이미 병합한 결과라 둘을 더하면 같은 체류가 두 번 들어간다.

**`product_view_sessions`·`ingredient_view_sessions`·`review_view_sessions`는
상품 단위다.** key에 `content_kind`가 있어도 이 셋은 `content_kind`마다 같은 값이
반복된다. 분모가 "이 상품을 본 세션"이라서다. 행 단위로 세면 `user_review` 행이
`ingredient_view_sessions = 0`을 달고 나와 "아무도 성분을 안 봤다"로 읽힌다.
따라서 **이 세 컬럼을 `content_kind` 축으로 합산하면 안 된다** — 같은 세션을
콘텐츠 종류 수만큼 센다. `avg_dwell_ms_per_session`·`ingredient_view_rate`·
`review_view_rate`가 전부 이 분모를 쓴다.

`ingredient_view_sessions`는 `content_kind`가 `ingredient_list`·`ingredient_callout`인
세션, `review_view_sessions`는 `user_review`·`review_stats`·`review_filter`인 세션을
센다. 둘의 합집합이 §4.14가 쓰는 `INFORMATION_CONTENT_KINDS`와 같다.

**두 분자는 분모의 모집단으로 제한한다.** 상품 조회 세션에 없는 콘텐츠 열람 세션은
세지 않는다 — Quick Look으로 상세를 연 세션이 그렇게 될 수 있고, 제한하지 않으면
`ingredient_view_rate`가 1.0을 넘는다. 분자와 분모가 같은 모집단이어야 한다는 것은
§4.1이 `add_to_cart_rate`에서 이미 밟은 규칙이다.

`product_view_sessions`의 날짜는 `funnel_session_fact.first_product_view_at`의 KST
일자다. `funnel_date_kst`는 퍼널 첫 단계(대개 노출)의 날짜라 자정을 넘긴 세션에서
콘텐츠를 읽은 날과 어긋난다. §4.14의 정보 확인 세션이 같은 방식을 쓴다.
이 Mart는 `product_id`가 있는 상품 상세 콘텐츠만 입력으로 사용한다.
`product_id = NULL`인 플랫폼 목록 섹션은 상품·브랜드 KPI에 포함하지 않는다. 플랫폼
공통 콘텐츠 Mart가 필요해지면 `product_id` 없는 별도 grain과 key를 계약한 뒤
집계한다.

### 4.5 `funnel_daily_kpi`

```text
key = funnel_date_kst + brand_id + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = funnel_session_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | `funnel_date_kst`는 최초 Funnel 진입일 기준 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `impression_sessions`, `click_sessions`, `quick_look_sessions`, `quick_look_cart_sessions`, `direct_click_sessions`, `direct_click_cart_sessions`, `detail_view_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `checkout_sessions`, `purchase_sessions` | bigint | N | 단계 도달 세션 |
| `impression_to_click_rate`, `click_to_view_rate`, `view_to_information_rate`, `view_to_cart_rate`, `cart_to_purchase_rate`, `view_to_purchase_rate`, `dropoff_after_impression_rate`, `dropoff_after_view_rate`, `dropoff_after_cart_rate` | double | Y | 전환·이탈률 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`detail_view_sessions`의 정의와 분모 규칙은 §4.14와 같다. `view_to_cart_rate`,
`view_to_purchase_rate`, `dropoff_after_view_rate`는 `detail_view_sessions`를 분모로
쓰고, `view_to_information_rate`는 상품 상세에서만 일어나므로 `product_view_sessions`를
유지한다. `dropoff_after_view_rate`는 `view_to_cart_rate`의 여집합이라 같은 분모여야 한다.

퀵룩 계열과 직접 클릭 계열은 **성격이 다르다.**

| 컬럼 | 성격 | 정의 |
| --- | --- | --- |
| `quick_look_sessions` | 비배타 | Quick Look을 쓴 세션. 상품 상세도 열었든 아니든 센다 |
| `quick_look_cart_sessions` | 비배타 | 그중 `add_to_cart`까지 간 세션 |
| `direct_click_sessions` | **배타** | Quick Look 없이 상품 상세로 직행한 세션. 둘 다 열었으면 **먼저 일어난 쪽**으로 귀속한다 |
| `direct_click_cart_sessions` | **배타** | 그중 `add_to_cart`까지 간 세션 |

`quick_look_sessions`를 배타로 바꾸면 안 된다. `product_daily_kpi.quick_look_sessions`와
같은 뜻이어야 하고, 대시보드의 "퀵룩 후 상세를 연 비율" 분모가 이 값이다.

그래서 **`quick_look_sessions + direct_click_sessions ≠ detail_view_sessions`다.**
둘 다 연 세션이 양쪽에 잡히기 때문이다. 배타 검산은 진입 경로로 한다.

```text
Quick Look 선진입 세션 + direct_click_sessions = detail_view_sessions
```

진입 경로는 `funnel_session_fact.detail_entry_path`(`quick_look` · `direct_click` · NULL)에
있다. Quick Look 선진입 세션 수는 소비자가 없어 Mart 컬럼으로 두지 않고 검증 Job이
그 Fact에서 직접 세어 위 등식을 확인한다.

### 4.6 `persona_segment_daily_kpi`

```text
key = event_date_kst + brand_id + segment_type + segment_value + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, bridge_persona_segment
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | segment 집계 축 |
| `segment_user_count`, `session_count` | bigint | N | 세그먼트 규모 |
| `impression_sessions`, `quick_look_sessions`, `product_view_sessions`, `detail_view_sessions`, `add_to_cart_sessions`, `purchase_sessions` | bigint | N | 단계별 고유 세션 수 |
| `product_count_viewed` | bigint | N | 상세를 연 고유 상품 수 |
| `detail_entry_rate` | double | Y | 상세 조회 세션 / 노출 세션 |
| `view_to_cart_rate` | double | Y | 장바구니 세션 / 상세 조회 세션 |
| `view_to_purchase_rate` | double | Y | 구매 세션 / 상세 조회 세션 |
| `avg_interest_score` | double | Y | 관심도 합 / 세션 수 (§2.3). 음수일 수 있다 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`segment_type`은 세 종류다.

| segment_type | segment_value | 비고 |
| --- | --- | --- |
| `skin_type` | `combination`, `dry`, `normal`, `oily` | `persona-schema.md` §3 |
| `skin_tone` | `fair`, `light`, `medium`, `tan`, `deep` | 〃 |
| `skin_type_x_skin_tone` | `dry|fair` 형식 | 교차 축 |

**세 축을 합산하지 않는다.** 한 세션이 `skin_type` 행과 `skin_tone` 행에 동시에
들어가므로 더하면 같은 세션을 두 번 센다. 교차 축도 단일 축의 분해가 아니라 별도
집계다 — 건성 담기율 0.5는 `dry|fair` 1.0과 `dry|deep` 0.0으로 갈릴 수 있고, 그
차이를 보는 것이 이 Mart의 목적이다. 교차 축끼리는 배타라 그 안에서만 합이 성립한다.

`bridge_persona_segment`에는 7종의 `segment_type`이 있지만 `hair_color`·`eye_color`·
`review_bucket`·`persona_source`는 내지 않는다. 대시보드 고객군 화면이 피부 축만
쓴다(`docs/dashboard/dashboard-redesign-spec.md` §2-3). 필요해지면 축을 늘리면 되고
Mart 구조는 그대로다.

**`product_id`는 key가 아니다.** 브랜드 grain이라 한 세션이 같은 브랜드 상품 여러 개를
봐도 세션은 한 번만 센다. `product_id`를 key에 두면 대시보드가 그것을 합산할 때 세션이
상품 수만큼 부푼다 — `brand_daily_kpi`를 `product_daily_kpi` 합산으로 만들 수 없는 것과
같은 이유다(§4.14). `product_count_viewed`가 상품 축의 대체값이다.

**`persona_id`가 없는 세션은 어느 행에도 들어가지 않는다.** 실제 사용자의 피부 정보는
이벤트 경로에 없다. 임의 세그먼트에 귀속하면 없는 사실을 만들어 내므로 제외한다.
그래서 **세그먼트 세션 합은 `brand_daily_kpi` 전체보다 작고, 작은 것이 정상이다.**
`skin_tone='notSureST'`도 값이 아니라 결측이라(`persona-schema.md` §3) segment_value가
되지 않으며, 톤이 결측인 Persona는 교차 축에서도 빠지고 `skin_type` 축에는 남는다.

담기·구매 분모는 `detail_view_sessions`(상품 상세 ∪ Quick Look)로 §4.1·§4.14와 같다.
모든 비율은 분모가 0이면 NULL이다. 시드 Event는 제외한다(§4.0).

`bridge_persona_segment`는 저장소에 없는 생성물이다(`.gitignore`의 `data/`). 실행 전에
`py contracts/persona/build_persona_tables.py --sample PC:all`로 만든다. 없으면 이 Mart를
만들지 않고 검증 Job은 경고만 남긴다.

**계약에서 뺀 컬럼이 셋 있다.** `persona_behavior_feature_delta`도 input에서 뺐고,
그 Fact는 2026-09-16에 계약에서 아예 지웠다 — 구현된 적이 없고 이 Mart 말고는
읽으려던 곳도 없었다.

| 뺀 것 | 이유 |
| --- | --- |
| `category_interest_score` | 브랜드 grain이라 카테고리 축이 없다. 상품 축이 필요하면 `product_daily_kpi.product_interest_score`를 쓴다 |
| `affinity_lift` | 행동 로그 파생이 아니라 AI 파트 `batch/ingest/data/affinity_lift.csv` 조인이다. 대시보드 E4 응답에도 없다 |
| `category_id` | 위와 같다. 브랜드 grain에 단일 카테고리가 없다 |
| `persona_behavior_feature_delta` (input) | §2.3의 `avg_interest_score` 산식은 `product_interest_score`만 요구하고 그것은 `product_event_fact`와 `EVENT_WEIGHT`로 낸다. 이 Fact의 시간 감쇠는 추천 피처용이라 KPI 산식에 없다 |


### 4.6-1 `brand_price_band_daily_kpi`

```text
key = event_date_kst + brand_id + price_bin + currency + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, dim_product, contracts/product-feature-vocab.json
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | `price_bin`·generator/scenario/run만 Y | 가격대 집계 축 |
| `session_count`, `unique_user_count` | bigint | N | 구간 규모 |
| `impression_sessions`, `quick_look_sessions`, `product_view_sessions`, `detail_view_sessions`, `add_to_cart_sessions`, `purchase_sessions` | bigint | N | 단계별 고유 세션 수 |
| `product_count` | bigint | N | 이 구간에서 관측된 고유 상품 수 |
| `detail_entry_rate` | double | Y | 상세 조회 세션 / 노출 세션 |
| `view_to_cart_rate` | double | Y | 장바구니 세션 / 상세 조회 세션 |
| `view_to_purchase_rate` | double | Y | 구매 세션 / 상세 조회 세션 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**구간은 여기서 정의하지 않는다.** `contracts/product-feature-vocab.json`의
`price_bin_edges`와 `blocks[].vocab`을 읽는다. 추천 CBF 피처 벡터·배너 축·상품 등록
화면이 이미 그 축을 쓰므로(`product-feature-spec.md` §4.1), 대시보드가 다른 구간을
정의하면 같은 이름의 가격대가 두 벌이 되어 "이 가격대 반응"이 어느 쪽 구간인지 알 수
없게 된다. 어휘집 0.7 기준 원화 5구간이다.

| price_bin | 구간 |
| --- | --- |
| `~26k` | 26,000원 미만 |
| `26k-46k` | 26,000 이상 46,000 미만 |
| `46k-66k` | 46,000 이상 66,000 미만 |
| `66k-105k` | 66,000 이상 105,000 미만 |
| `105k+` | 105,000원 이상 |

구간은 **반열린** `[하한, 상한)`이다. 26,000원짜리 상품은 `26k-46k`에 들어가고, 한 상품이
두 구간에 동시에 속할 수 없다 — 검사가 아니라 구조로 막는다.

`base_price`가 NULL이거나 0 이하인 상품은 **`price_bin = NULL` 행으로 보존한다.** 빼면
그 상품들의 반응을 볼 수 없고, 임의 구간에 넣으면 그 구간 수치가 오염된다. Dimension에
없는 상품은 가격을 모르므로 이 Mart에 넣지 않는다.

**`currency`는 key다.** 통화가 다른 가격을 환산 규칙 없이 한 구간으로 합치지 않는 것을
필터가 아니라 grain으로 지킨다. 카탈로그가 전부 원화인 지금은 행 수에 차이가 없지만,
다른 통화가 들어와도 조용히 섞이지 않는다.

담기·구매 분모는 `detail_view_sessions`(상품 상세 ∪ Quick Look)로 §4.1·§4.14와 같다.
브랜드 grain이라 한 세션이 같은 구간의 상품 여러 개를 봐도 세션은 한 번만 센다.
모든 비율은 분모가 0이면 NULL이다. 시드 Event는 제외한다(§4.0).

`price_bin`을 걷어낸 합계는 `brand_daily_kpi`와 같지 않다. 한 세션이 여러 구간의 상품을
밟으면 구간마다 한 번씩 세어지기 때문이다. **두 Mart를 서로 대체하지 않는다.**

고객군 축(피부 타입)과의 교차는 이 Mart로 낼 수 없다. 축을 하나 더 얹으면 그 축을 걷어낸
합계가 무너지므로 별도 Mart로 낸다 — §4.26 `segment_price_band_daily_kpi`
(S15P21A306-301).


### 4.8 `ingredient_weekly_interest`

```text
key = interest_week_kst + ingredient_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events, dim_product, product_ingredient.csv, ingredient_vocab.csv
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `interest_week_kst` | date | N | KST 기준 월요일 |
| `ingredient_id`, `ingredient`, `label_ko`, `vocab_version` | int/string | 표시명만 Y | 성분 어휘 Dimension |
| `actor_type`, `source`, `scenario_id`, `simulation_run_id` | 공통 계약 | scenario/run만 Y | Web/Synthetic 및 실행 분리 축 |
| `ingredient_interest_score` | double | N | 직접 지목 점수 + 상품 귀속 점수 |
| `direct_match_score` | double | N | `matched_ingredients[]`로 직접 지목된 성분 점수 |
| `product_attributed_score` | double | N | 행동 가중치 × `position_weight` × 카테고리 가중치 |
| `contributing_event_count` | bigint | N | 해당 성분에 기여한 고유 Event 수 |
| `ingredient_interest_share` | double | Y | 같은 주·실행 축 점수 합 대비 비중. 분모 0이면 NULL |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

성분 관심 계산은 AI 사용자 벡터의 ingredient 슬라이스를 읽지 않는다.
`product_ingredient.csv.position_weight`를 직접 사용하며, 이 값은 함량이 아니라 원본 태그
또는 전성분 배합 순서 기반 가중치다. `text_selection`·`text_copy`의
`matched_ingredients[]`는 직접 지목한 성분에만 귀속하고 위치가중을 다시 곱하지 않는다.
상품 전체 신호는 성분표 체류(최대 60초), 성분 표시 전환, 성분 Accordion 펼침,
장바구니 담기를 상품의 각 성분으로 확장한다. 행동 가중치는 `EVENT_WEIGHT` 단일 원본을
사용한다.

`secondary_category=Cleansers`의 상품 전체 신호에는 기본 `0.5`를 곱한다. 이 값은
`CLEANSING_CATEGORY_WEIGHT` 또는 `--cleansing-category-weight` 실행 설정으로 관리하며
코드의 고정 상수로 산식에 삽입하지 않는다. 직접 지목 신호에는 세정 가중치를 적용하지
않는다.

현재 200개 시드 상품 중 188개만 `product_ingredient.csv`에 연결되고 12개는 성분 행이
없다. 이 12개 상품의 상품 전체 Event는 성분별 numerator와
`ingredient_interest_share` denominator에서 모두 제외한다. 성분 관심 0으로 채우지
않는다. 단, Event가 `matched_ingredients[]`로 성분을 직접 지목했다면 상품 연결 여부와
무관하게 해당 성분에 반영한다.

### 4.9 `category_price_reference`

```text
key = secondary_category + currency
input = dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `secondary_category`, `currency` | string | N | 카테고리·통화 기준 축 |
| `product_count` | bigint | N | 유효 기준 가격을 가진 카테고리 상품 수 |
| `observed_median_price` | decimal(18,2) | N | 해당 카테고리의 실제 중앙값 |
| `global_product_count`, `global_median_price` | bigint/decimal(18,2) | N | 같은 통화 전체 기준 |
| `is_sample_sufficient` | boolean | N | `product_count >= min_sample_size` |
| `reference_median_price` | decimal(18,2) | N | 화면·추천에서 사용할 최종 기준값 |
| `reference_source` | string | N | `category`, `global_fallback` |
| `min_sample_size` | int | N | 실행 당시 표본 기준, 기본 3 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

가격은 `secondary_category`와 `currency`별 `base_price`의 정확한 중앙값으로 집계한다.
NULL과 0 이하 가격은 제외한다. 표본이 3개 미만이면 같은 통화 전체 상품 중앙값을
`reference_median_price`로 사용한다. 기준은 `PRICE_MIN_SAMPLE_SIZE` 또는
`--price-min-sample-size` 설정으로 관리한다. `sale_price`, `sale_price_usd`, 할인율은
결측이 많고 `dim_product` 기준 가격 계약에도 없으므로 입력·집계·산출에서 사용하지 않는다.

### 4.10 `banner_daily`

```text
key = event_date_kst + brand_id + product_id + banner_type + banner_value + banner_slot
      + trait_source + policy_version + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact
```

`impression_count`, `click_count`, `impression_sessions`, `click_sessions`, `skip_count`,
`banner_ctr`를 저장한다. `banner_ctr`은 `click_count / impression_count`이며 분모 0은
NULL이다. `banner_skip` Event는 만들지 않는다. `banner_value_is_valid`는 원문
어휘집 검증 결과이고 `new_brand`만 NULL을 허용한다.

`policy_version`을 key에 두는 이유는 배너·정렬 정책 배포 전후를 같은 Mart 안에서
가르기 위해서다. Event에 값이 없으면 NULL 그룹으로 남고 사전/사후 구분은
`analytics_baseline` 기간으로만 가능하다. 축별 CTR은 `banner_type`, `banner_value`,
`banner_slot`, `trait_source`로 잘라서 본다.

`cross_brand_daily`에는 `policy_version`을 두지 않는다. 교차 유입은 세션 단위 중복
제거가 기준이라 정책 버전으로 다시 쪼개면 같은 세션이 여러 행에 걸린다. 그쪽 사전/사후는
`analytics_baseline`의 기준선 기간으로 가른다.

**실데이터 검증 범위** — 현재 화면이 히어로 1칸(`hero=new_brand`)이라 실행 로그의
`banner_type`이 `new_brand` 한 종류뿐이다. `new_brand`는 `banner_value=NULL`이 허용되는
유일한 타입이므로, 다른 축(`concern`·`ingredient`·`clean`·`price_bin`·`category`·`segment`)의
`banner_value` 규칙은 실데이터가 아니라 단위 테스트로만 검증된다. 배너 행이 복구되면
재검증 대상이다. `trait_source`는 세 값(`profile`·`explore`·`coldstart`)이 실행 로그에
모두 나타난다.

### 4.11 `user_trait_daily`

```text
key = trait_date_kst + user_id + identity_scope
      + actor_type + source + scenario_id + simulation_run_id + trait
input = sessionized_events
```

합성 로그의 페르소나와 실사용자 계정이 같은 `user_id` 공간을 쓰지 않도록 `identity_scope`와
실행 축을 key에 둔다. 축이 없으면 두 축의 사용자가 한 행으로 합쳐진다.

trait은 `price`, `ingredient`, `review`, `concern`, `participate` 5종이다. 최근 30일
행동의 `trait_score`, `trait_rank`, `is_primary_trait`, `window_start_date`,
`window_end_date`, `contributing_event_count`, `trait_policy_version`을 저장한다.
가중치와 기간은 `contracts/user-trait-weights.json`을 실행 원본으로 사용한다. 이 파일은
Front의 세션 성향 계산기(`frontend/src/lib/trait.ts`)와 같은 규칙이어야 하며, 어긋나면
같은 사용자가 화면과 Mart에서 다른 성향으로 잡힌다.

체류는 2초 미만이면 0점이고 건당 60초가 상한이다. `accordion_toggle`은 펼칠 때만 센다.
`selection_kind`가 실리지 않는 화면에서는 `content_kind`와 성분 매칭 수로 대신 본다.
구매 이유는 선언한 이유별로 해당 trait에 넣는다 — 전부 `participate`로 보내면 가격 때문에
산 사람도 참여 성향으로 잡힌다.

Front는 세션 점수에 이 Mart 값을 ×0.5로 섞는다. Mart 점수를 그대로 화면 성향으로 읽지
않는다. 페르소나 `skin_type` 상수와 세션 감쇠는 Event가 아니므로 Mart에 넣지 않는다.

### 4.12 `cross_brand_daily`

```text
key = event_date_kst + destination_brand_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events
```

`sessionized_events.event_order`로 정렬한 `product_view`만 사용하며, 세션 최초 브랜드와
목적 브랜드가 다를 때 교차 유입으로 판정한다. Front의 `cross_brand` boolean은 입력으로
사용하지 않고, 한 세션의 같은 목적 브랜드는 각 지표에서 한 번만 센다.

추천 귀속은 목적 `product_view.properties.recommendation_id`를 우선 사용하고, 값이 없으면
같은 세션·상품의 선행 `recommendation_click`을 사용한다. 배너 귀속은 같은 세션·상품의
선행 `banner_click`을 사용하며 직전 Event만으로 제한하지 않는다.

선행 `recommendation_click`은 **`recommendation_id`가 비어 있지 않을 때만** 추천 귀속으로
센다. Front가 이 Event를 내는 세 지점(목록 맞춤 기획전 `promo_pick`, 히어로 배너, 상세
유사 상품)이 모두 값을 채우므로 누락이 없다. 형식은 서버 응답의 uuid hex 또는 Front가
만든 `rec-{product_id}-{persona}` 두 가지이며 둘 다 비어 있지 않다(프론트 확인
2026-09-14). 유사 상품이 추천 API로 넘어가면 형식만 uuid로 바뀌고 조건은 그대로다.

`brand_view_sessions`를 공통 분모로 `cross_brand_entry_rate`,
`recommendation_cross_brand_entry_rate`, `banner_cross_brand_entry_rate`를 저장한다. 또한
전체 교차 유입 세션을 분모로 `recommendation_share_of_cross_brand_entries`,
`banner_share_of_cross_brand_entries`를 저장한다. `top_source_brand_id`는 공개 임계값과
정책 버전이 확정될 때까지 산출하지 않는다.

추천과 배너는 **동시에 귀속될 수 있다.** 두 기여 세션 수를 더해 전체 교차 유입과
비교하지 않는다. 교차 유입이 0인 행의 두 share는 0이 아니라 NULL이다.

브랜드를 모르는 조회(`brand_id`가 NULL이거나 Dimension에 없는 상품)는 어느 브랜드에도
귀속하지 않는다. 직전 상품이나 세션의 첫 상품으로 추정하지 않는다

`generator_type`은 2026-09-16(Jira 324)에 grain에 들어갔다. 커밋 82afffe가 실행 축을
정리할 때 구현된 Mart 7종만 갱신해 이 Mart가 4축으로 남아 있었고, PC(`python_batch`)와
PA(`agent_llm`)의 교차 유입 세션이 한 행에 합쳐지고 있었다 — `actor_type`은 둘 다
`synthetic`이라 구분이 안 된다(§2).

**축을 늘려도 합계는 보존된다.** `generator_type`은 세션 속성이라 한 세션이 두 값을
가질 수 없고, 따라서 셀이 갈려도 세션이 중복되지 않는다. 재생 데이터 실측에서
`brand_view_sessions` 4,308 · `cross_brand_entry_sessions` 2,365가 변경 전후 같았다.
이 Mart를 입력으로 쓰는 `analytics_baseline`(§4.13)이 축을 걷어내고 합산하므로
중요한 성질이다.
([`event-attribution-contract.md`](./event-attribution-contract.md) §2).

이 Mart만 실행 축에 `generator_type`이 없다. 대시보드 엔드포인트가 쓰지 않아 제외했다
(프론트 확인 2026-09-14). 필요해지면 다른 Mart와 같은 방식으로 추가한다.

### 4.13 `analytics_baseline`

```text
key = baseline_policy_version + metric_name + brand_id + algorithm
input = product_event_fact, cross_brand_daily
```

`metric_name`은 `recommendation_ctr`과 `cross_brand_entry_rate` 둘뿐이다. 각각
`numerator`, `denominator`, `metric_value`와 `baseline_start_date`,
`baseline_end_date`를 함께 저장해 나중에 분모를 다시 검증할 수 있게 한다. 분모 0이면
`metric_value`는 NULL이다.

`BASELINE_POLICY_VERSION`, `BASELINE_START_DATE`, `BASELINE_END_DATE` 세 값을 모두
지정한 실행에서만 생성한다. 셋 중 일부만 주면 Job이 실패한다. 검증 Job은 이 Mart가
없으면 경고만 남기고 통과한다.

배너가 없던 기간의 배너 CTR은 존재하지 않는 값이므로 0으로 만들지 않는다. 기준선에
배너 지표를 넣으면 검증이 실패한다. 사전 기준선은 기존 추천 CTR과 브랜드별 교차 유입률
두 가지로만 남긴다.

### 4.14 `brand_daily_kpi`

```text
key = event_date_kst + brand_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통 계약 | scenario/run만 Y | 브랜드·일자·실행 분리 축 |
| `impression_sessions`, `click_sessions`, `quick_look_sessions`, `detail_view_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions` | bigint | N | 브랜드 단계별 고유 세션 수 |
| `unique_user_count` | bigint | N | 브랜드 KPI에 기여한 고유 사용자 수 |
| `product_count_viewed` | bigint | N | 조회된 고유 상품 수 |
| `detail_entry_rate` | double | Y | 상세 조회 세션 / 노출 세션 |
| `information_view_rate` | double | Y | 정보 확인 세션 / 상품 상세 조회 세션 |
| `view_to_cart_rate` | double | Y | 장바구니 세션 / 상세 조회 세션 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`detail_view_sessions`는 상품 상세(`product_view`)와 Quick Look(`quick_look`) 중 하나
이상을 연 고유 세션이다. 둘 다 연 세션도 한 번만 센다. Quick Look은 목록에서 상세를
여는 화면 동선이고 거기서 바로 담을 수 있어서, 담기 세션을 `product_view_sessions`로
나누면 분자와 분모가 다른 모집단을 세어 비율이 1.0을 넘는다. 그래서 담기·전환 분모는
`detail_view_sessions`를 쓰고, 정보 확인만 상품 상세에서 일어나므로
`product_view_sessions`를 유지한다. `quick_look_sessions`와 `product_view_sessions`는
겹칠 수 있어 더해서 `detail_view_sessions`를 만들 수 없다.

`click_sessions`는 `product_click`을 낸 고유 세션이다. 브랜드 퍼널의 노출 → 클릭 →
상세 단계를 상품 Mart 합산 없이 브랜드 단위로 보기 위해 둔다
([`dashboard-mart-api-spec.md`](./dashboard-mart-api-spec.md) §6-1). 이 Mart는 비율을
노출 → 상세로 바로 잇고(`detail_entry_rate`) 클릭을 분모로 쓰지 않는다. Quick Look은
클릭 없이 상세를 여는 경로라 클릭을 분모에 두면 그 세션이 빠지기 때문이다.

상품 grain Mart의 세션 수를 합산하지 않고 Fact에서 `session_id`를 브랜드별로 직접
중복 제거한다. 따라서 한 세션이 같은 브랜드 상품 여러 개를 보더라도 각 단계 세션은
한 번만 집계된다. `brand_id`가 NULL이거나 빈 문자열인 Event는 제외한다. 정보 확인은
`funnel_session_fact.first_information_view_at`의 KST 일자를 사용하며, 같은 일자·브랜드의
상품 조회가 확인된 세션에만 귀속한다. 모든 비율은 분모가 0이면 NULL이다. 구매·매출
지표는 이 Mart의 범위가 아니다.

### 4.15 `product_repurchase_daily`

```text
key = snapshot_date_kst + brand_id + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = purchase_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `buyer_count` | bigint | N | 창 안에서 이 상품을 산 고유 사용자 수 |
| `repeat_buyer_count` | bigint | N | 서로 다른 주문으로 두 번 이상 산 사용자 수 |
| `purchase_order_count` | bigint | N | 고유 주문 수 |
| `repurchase_rate` | double | Y | `repeat_buyer_count / buyer_count` |
| `median_days_between_purchases` | double | Y | 재구매 사용자의 평균 간격의 중앙값 |
| `backend_order_count`, `local_order_count` | bigint | N | 주문 경로별 고유 주문 수 |
| `kakaopay_order_count`, `card_order_count`, `test_order_count` | bigint | N | 결제수단별 고유 주문 수 |
| `backend_paid_value` | decimal(18,2) | Y | `backend` 주문의 실결제액 합. 주문 단위로 접은 뒤 합산 |
| `window_days`, `window_start_date`, `window_end_date` | int, date, date | N | 관측 창 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

재구매는 **서로 다른 `order_id`** 기준이다. 한 주문에 같은 상품 row가 여러 개 있어도
구매는 한 번이며, 주문 단위로 먼저 접은 뒤 센다. 재구매 간격은 첫 구매와 마지막 구매의
간격을 구매 횟수로 나눈 사용자별 평균이고, 1회 구매자는 NULL이라 중앙값에 들어가지 않는다.
`snapshot_date_kst`는 입력의 최대 `event_date_kst`이며 창은 그 날부터 `window_days`일
직전까지다. `brand_id`·`user_id`·`order_id`가 비어 있는 row는 제외한다.

결제수단·주문 경로는 **행을 버리지 않고 축으로만 가른다.** `order_channel='local'`은
브라우저에서만 만든 시연 주문이라 Backend 주문과 대사(對査)할 수 없지만
([`event-properties-schema.md`](./event-properties-schema.md) §3.16), 여기서 걸러내면
재구매율이 왜 달라졌는지 되짚을 근거가 사라진다. `buyer_count`·`repurchase_rate`는
`local` 주문을 포함하고, 읽는 쪽이 필요하면 `backend_order_count`로 좁힌다.

`backend_paid_value`만 예외다. 시연 주문의 금액을 섞으면 실결제액 축이 시연 횟수에
따라 흔들리므로 `backend` 주문만 센다. 결제 계약(§3.15·§3.16) 이전에 쌓인 주문은
분포가 모두 0이고 NULL이 아니다 — 0건과 "아직 안 들어왔다"를 구분해야 하기 때문이다.
값 자체가 없는 `backend_paid_value`만 NULL로 남는다.

### 4.16 `brand_repurchase_daily`

```text
key = snapshot_date_kst + brand_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = purchase_fact, purchase_reason_fact
```

컬럼은 §4.15와 같고(결제수단·주문 경로 분포 포함) `declared_restock_order_count`(bigint, N)가 추가된다.

브랜드 재구매는 상품이 달라도 같은 브랜드를 다시 사면 성립한다. 따라서 §4.15를 합산해서
구할 수 없다. 한 사용자가 같은 브랜드의 다른 상품 두 개를 사면 상품 단위로는 1회 구매가
둘이지만 브랜드 단위로는 재구매다.

`declared_restock_order_count`는 `purchase_reason_fact`의 `restock` 선언 주문 수다.
관측 재구매와 선언 재구매가 갈리는 구간이 행동 추론의 한계를 보여준다
([`event-properties-schema.md`](./event-properties-schema.md) §3.9). 매칭이 없으면 0이며
NULL로 두지 않는다.

### 4.17 `purchase_reason_daily`

```text
key = event_date_kst + brand_id + reason + actor_type + source + generator_type + scenario_id + simulation_run_id
input = purchase_reason_fact, purchase_fact, user_trait_daily
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `reason` | string | Y | Grain. 건너뛴 응답은 NULL |
| `order_count` | bigint | N | 해당 이유가 달린 고유 주문 수 |
| `primary_order_count` | bigint | N | 대표 이유로 고른 주문 수 |
| `skipped_order_count` | bigint | N | 설문을 건너뛴 주문 수 |
| `reason_share` | double | Y | 응답한 주문 중 비중. `reason`이 NULL이면 NULL |
| `trait_compared_order_count` | bigint | N | 성향 대조가 가능했던 주문 수 |
| `trait_matched_order_count` | bigint | N | 선언과 관측 성향이 일치한 주문 수 |
| `trait_match_rate` | double | Y | `matched / compared` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`purchase_reason_fact`의 grain은 `order_id + reason`이라 브랜드 축이 없다. 이유는 주문
단위 선언이므로 다브랜드 주문에서 어느 브랜드 때문인지 알 수 없다. **한 주문은 그 주문에
포함된 각 브랜드에 한 번씩만 계상한다.** 집계를 `countDistinct(order_id)`로 하는 이유도
상품 수만큼 부풀지 않게 하기 위해서다.

`reason_share`의 분모는 **응답한 주문**뿐이다. 건너뛴 주문을 분모에 넣으면 비중이 실제보다
낮아진다. 건너뛴 주문은 `reason = NULL` 행의 `skipped_order_count`로만 센다.

선언 이유와 관측 성향의 매핑은
[`purchase-reason-trait-map.json`](./purchase-reason-trait-map.json)을 실행 원본으로
사용한다. 매핑이 없는 이유(`texture_finish`, `recommendation`, `restock`)는 대조 분모에서
제외한다. 이 매핑은 `purchase_reason_daily`만 읽는 DATA 계약이며 값이 바뀌면 파일과
버전을 함께 올린다.

매출·정산 금액은 이 Mart들의 범위가 아니다. §6.4를 따라 Backend의 PAID 주문 상품이
정본이며 DW는 금액을 복제하지 않는다.

### 4.18 `commons_cohort_weekly`

```text
key = snapshot_week_kst + cohort_key + metric_name + actor_type + source + generator_type + scenario_id + simulation_run_id
input = brand_daily_kpi, brand_cohort_dim
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 코호트 집계 축 |
| `metric_name` | string | N | `detail_entry_rate`, `view_to_cart_rate`, `information_view_rate` |
| `p25`, `p50`, `p75` | double | Y | 코호트 안 브랜드들의 주간 비율 분위. 억제되면 NULL |
| `brand_count` | bigint | N | 셀 안 브랜드 수. R1 판정 근거 |
| `is_sample_sufficient` | boolean | N | R2 — 코호트 주간 분모가 `min_sample_size` 이상 |
| `is_dominated` | boolean | N | R3 — 한 브랜드가 셀 분모의 50% 초과 |
| `is_suppressed` | boolean | N | R1 또는 R3 위반. `true`면 분위 3종이 NULL |
| `min_brand_count`, `min_sample_size`, `dominance_ratio` | int, int, double | N | 실행 당시 임계값 |
| `window_start_date`, `window_end_date` | date | N | 관측 창 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**이 Mart는 B층이다** (§2.5). 다른 브랜드에게 보여도 되는 형태여야 한다.

**브랜드 식별자가 없다.** 코호트 단위 집계라 행이 브랜드에 대응하지 않는다. R5는
"원 `brand_id`를 두지 않는다"를 요구하는데 이 Mart는 `brand_hash`조차 없다. 내 위치는
`brand_cohort_dim`에서 내 `cohort_key`를 찾아 이 Mart와 맞춰 보는 방식으로 읽는다.

**절대 건수를 두지 않는다 (R4).** `brand_count`는 브랜드 수이지 매출·조회 건수가 아니고,
R1 판정과 화면의 표본 병기에 필요하다. 세션 분모는 `is_sample_sufficient` 불리언으로만
전달한다 — 숫자를 실으면 코호트가 작을 때 역산이 가능해진다.

**억제는 행을 지우지 않고 값을 NULL로 만든다.** 행이 사라지면 "억제됐다"와 "코호트가
아예 없다"를 구분할 수 없다. 빈칸으로 보여주는 것이 정직하다.

**grain이 주간이다.** R2의 분모 200을 일간에 걸면 재생 데이터 336행 중 5행(1%)만
통과한다. 주간으로 접으면 브랜드 31/56(55%)이 통과한다 (§2.5.1).

`metric_name` 롱 포맷을 쓰는 이유는 지표를 더할 때 grain이 바뀌지 않게 하기 위해서다.
`analytics_baseline`(§4.13)이 같은 형태다. 지금 세 지표는 전부 `brand_daily_kpi`에서
나오며, 다른 Mart의 비율을 더하려면 그 Mart를 입력에 추가하고 `metric_name`만 늘린다.

억제 판정 순서는 R1 → R3 → R2다. R1·R3는 값을 지우고 R2는 플래그만 남긴다 — 표본이
얇은 것과 식별 위험이 있는 것은 다른 문제라서다.

시드 Event는 입력 단계(`brand_daily_kpi`)에서 이미 빠져 있다(§4.0).

### 4.19 `content_conversion_daily`

```text
key = event_date_kst + brand_id + product_id + content_kind + actor_type + source + generator_type + scenario_id + simulation_run_id
input = content_interest_fact, funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 콘텐츠 집계 축 |
| `category_id` | string | Y | 상품 차원 스냅샷 |
| `viewed_sessions` | bigint | N | 그 콘텐츠를 본 고유 세션 수 |
| `viewed_cart_sessions` | bigint | N | 그중 같은 상품을 담기까지 간 세션 수 |
| `viewed_cart_rate` | double | Y | `viewed_cart_sessions / viewed_sessions` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**§4.4와 분리한 이유는 분모가 다르기 때문이다.** §4.4의 비율은 상품 조회 세션을
분모로 쓰고, 이 Mart는 **그 콘텐츠를 본 세션**을 분모로 쓴다. 한 Mart에 두 분모를
섞으면 같은 행의 비율끼리 더하거나 비교할 수 없게 된다.

**대시보드가 만들 수 없는 값이다.** "그 콘텐츠를 본 세션"과 "그 세션이 담았는가"를
맞추려면 세션 단위 조인이 필요한데, 집계된 Mart 두 개를 받아서는 복원되지 않는다.
`docs/dashboard/dashboard-mart-api-spec.md` §6-2가 이 Mart를 요구하는 근거다.

**cart_lift를 미리 계산하지 않는다.** 기준이 되는 브랜드 담기율(§4.14
`view_to_cart_rate`, 분모 `detail_view_sessions`)과 나누면 "본 사람의 담기율 배수"가
나오지만, 그 나눗셈을 여기서 하면 어느 브랜드·어느 기간의 비율을 썼는지가 행에 박혀
다른 기준으로 다시 볼 수 없다. 나눗셈은 읽는 쪽 몫이다.

`content_kind`가 NULL인 행은 제외한다. 어떤 콘텐츠인지 모르면 대조가 성립하지 않는다.
`product_id`가 NULL인 플랫폼 목록 섹션도 §4.4와 같은 이유로 제외한다.

담기 도달 여부는 `funnel_session_fact.reached_add_to_cart`에서 가져오고, **같은 상품**에
대한 담기만 센다. 세션이 다른 상품을 담은 것은 이 콘텐츠의 효과가 아니다.

### 4.20 `behavior_conversion_daily`

```text
key = event_date_kst + brand_id + product_id + event_name + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events, funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 행동 집계 축 |
| `event_name` | string | N | `ingredient_view_mode_change`, `review_filter_apply`, `accordion_toggle`, `text_copy` |
| `done_sessions` | bigint | N | 그 행동을 한 세션 수 |
| `done_cart_sessions` | bigint | N | 그중 담기까지 간 세션 수 |
| `not_done_sessions` | bigint | N | 그 행동을 **안 한** 세션 수 |
| `not_done_cart_sessions` | bigint | N | 그중 담기까지 간 세션 수 |
| `done_cart_rate`, `not_done_cart_rate` | double | Y | 각 모집단의 담기율 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**두 모집단의 합이 전체다.** `done_sessions + not_done_sessions`는 같은 key의 상품
조회 세션 수(§4.4 `product_view_sessions`)와 같아야 한다. 한쪽만 세면 "안 한 사람"의
담기율이 비어 대조가 성립하지 않는데, 이 Mart의 존재 이유가 바로 그 대조다.

**모집단은 상품 조회 세션이고 `funnel_session_fact`에서 온다.** 행동 Event만으로
모집단을 만들면 행동을 한 세션만 남아 `not_done_*`이 전부 0이 된다.

**입력이 `sessionized_events`다.** 네 Event는 `PRODUCT_EVENT_NAMES` 밖이라
`product_event_fact`에 없다. `sessionized_events`는 `is_seeded`·`brand_id`·실행 축을
모두 갖고 있어 §4.12·§4.11과 같은 방식으로 읽을 수 있다.

**한 건도 일어나지 않은 `event_name`도 행을 남긴다.** 모집단 × Event 4종을 교차해
만들기 때문이다. 행이 없으면 "아무도 안 했다"와 "그 Event를 집계하지 않는다"를
구분할 수 없다. 재생 데이터에서 `text_copy`는 128세션뿐이라 실제로 밟는 경우다.

행동 Event는 세션·상품·Event 단위로 중복을 제거한 뒤 판정한다. 같은 세션에서 아코디언을
열 번 열어도 "한 세션"이다 — 이 Mart가 재는 것은 빈도가 아니라 여부다.

### 4.21 `friction_daily`

```text
key = event_date_kst + brand_id + product_id + section_id + content_kind + event_name + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events, funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | section/content/generator/scenario/run만 Y | 마찰 집계 축 |
| `event_name` | string | N | `rage_click`, `dead_click`, `scroll_backtrack` |
| `event_count` | bigint | N | 그 위치에서 일어난 마찰 Event 수 |
| `friction_sessions` | bigint | N | 마찰을 겪은 고유 세션 수 |
| `detail_view_sessions` | bigint | N | 분모. 그 상품의 상세를 연 세션 수 |
| `friction_rate` | double | Y | `friction_sessions / detail_view_sessions` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**UI 마찰이지 상품 선호가 아니다.** "이 상품이 별로다"가 아니라 "이 화면이 불편하다"를
재는 지표라 전환 Mart와 grain을 따로 두고 분모만 공유한다.

**`event_name`을 key에 두는 롱 포맷이다.** 마찰 Event를 나중에 더해도 grain이 바뀌지
않는다. `commons_cohort_weekly`(§4.18)의 `metric_name`과 같은 형태다. E6의
`by_location` 블록이 `section_id` + `event_name`을 그대로 읽고, `counts` 블록은
`event_name`으로 합산해 만든다.

**마찰이 0건인 `event_name`도 행을 남긴다.** `dead_click`은 생성기가 만들지 않아 PC
로그에서 항상 0인데, 행이 없으면 화면이 "0이다"와 "집계하지 않는다"를 구분할 수 없다.
같은 이유로 `rage_click`도 시드 제외 후 0이 되지만 행은 남는다.

**입력이 `sessionized_events`다.** 세 Event는 `PRODUCT_EVENT_NAMES` 밖이라
`product_event_fact`에 없고, `cleaned_events`는 `brand_id`가 비어 있다(실측 0%).
`section_id`·`content_kind`는 `properties_json`에서 읽는다 — `content_kind`는 결측이
있어 nullable이다(실측 67% 적재).

분모는 상세를 연 세션이다(§7 spec §6-6). 마찰은 상세 안에서 일어나므로 노출 세션을
분모로 두면 비율이 실제보다 작게 나온다.

### 4.22 `exit_daily`

```text
key = event_date_kst + brand_id + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events(exit_summary), funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 이탈 집계 축 |
| `detail_view_sessions` | bigint | N | 분모. 그 상품의 상세를 연 세션 수 |
| `exit_summary_sessions` | bigint | N | 그중 `exit_summary`가 기록된 세션 수 |
| `quick_exit_sessions` | bigint | N | 그중 체류 3초 미만으로 나간 세션 수 |
| `quick_exit_rate` | double | Y | `quick_exit_sessions / detail_view_sessions` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**`exit_summary`는 세션 단위 Event라 `product_id`·`brand_id`가 없다**(실측 0건).
그래서 그 세션이 상세를 연 상품 **전부**에 귀속한다. 세션 하나가 상품 셋을 봤으면 세
행에 들어가므로 **상품 축으로 합산하면 세션이 부푼다.**

**`last_content_kind`로 이탈 지점을 가르지 않는다.** `event-properties-schema.md`가
`exit_summary`의 선택 속성으로 선언해 두었지만 재생 데이터 1,000건 중 **0건**만 값을
싣는다. `last_section_id`·`reason`도 같다. 콘텐츠별 이탈 지점은 `exit_summary`가 아니라
콘텐츠 Event의 마지막 시각으로 따로 내야 한다 — 별도 Mart의 몫이다.

**`exit_summary_sessions`를 따로 싣는 이유**는 분모와 다르기 때문이다.
`exit_summary`가 없는 세션은 "빨리 나가지 않았다"가 아니라 "기록이 없다"다. 두 값이 크게
벌어지면 수집 누락이므로 화면이 아니라 Q5가 먼저 본다.

세션에 `exit_summary`가 여럿이면 **가장 긴** 체류로 판정한다. 어느 페이지에도 오래
머물지 않았을 때만 조기 이탈이다 — 최솟값을 쓰면 오래 머문 세션도 짧은 페이지 하나
때문에 조기 이탈로 잡힌다.

**현재 재생 데이터에서 이 비율은 축퇴돼 있다.** `exit_summary`가 기록된 세션
13,251건이 **전부** 3초 미만이다. 생성기가 `dwell_ms`를 항상 3초 미만으로 내기
때문이고, Mart 계산이 아니라 입력의 문제다. 생성기가 고쳐지면 값이 갈린다.

### 4.23 `entry_source_daily`

```text
key = event_date_kst + brand_id + entry_source + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, funnel_session_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 유입 경로 집계 축 |
| `entry_source` | string | N | `list_grid`, `promo_pick`, `similar_products`, `quick_look`, `cart`, `breadcrumb` (§3.3) |
| `product_view_sessions` | bigint | N | 상품 상세를 연 세션 수 |
| `detail_view_sessions` | bigint | N | 상세 ∪ 퀵룩 세션 수. 담기 분모 |
| `add_to_cart_sessions` | bigint | N | 담기까지 간 세션 수 |
| `view_to_cart_rate` | double | Y | `add_to_cart_sessions / detail_view_sessions` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**`product_id`가 key에 없다.** E6는 브랜드 단위 수치를 그리는데 상품 단위 세션 수는
브랜드로 합산할 수 없다 — 한 세션이 같은 브랜드 상품 여럿을 보면 상품 수만큼 부푼다.
`brand_daily_kpi`(§4.14)를 `product_daily_kpi`(§4.1) 합으로 만들 수 없는 것과 같다.

**`entry_source` 축으로도 합산하면 안 된다.** 한 세션이 상품 A는 목록에서, 상품 B는
유사 상품에서 열면 두 행에 모두 들어간다. 경로별 비교가 목적이지 총합이 아니다.

**노출 단계를 이 축으로 가를 수 없다.** `product_impression`에 `entry_source`가 없다
(재생 데이터 100,625건 중 0건, `list_id`만 100%). 그래서 `impression_sessions`와
`detail_entry_rate`를 내지 않고 `product_view_sessions`를 대신 싣는다.

세션의 경로는 **첫 진입**으로 정한다. 같은 세션이 같은 상품에 여러 경로로 들어올 수
있어서다(실측 21,555쌍 중 249쌍). `event_time` 오름차순, 동률이면 `event_id` 사전순으로
고정한다 — 규칙이 없으면 실행마다 판정이 흔들려 재계산 결정성이 깨진다.

담기 분모는 `detail_view_sessions`다(spec §6-6). Quick Look에서 담는 경로가 있어
`product_view_sessions`만 분모로 두면 비율이 1.0을 넘는다.

### 4.24 `product_exit_daily`

```text
key = event_date_kst + brand_id + product_id + last_content_kind + actor_type + source + generator_type + scenario_id + simulation_run_id
input = sessionized_events
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 이탈 지점 집계 축 |
| `exit_sessions` | bigint | N | 그 콘텐츠를 마지막으로 보고 떠난 세션 수 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**§4.22 `exit_daily`와 다른 Mart다.** 그쪽은 "얼마나 빨리 나갔나"(체류 3초 미만)를
재고 이쪽은 "어디에서 멈췄나"를 잰다. 분모도 다르다 — `exit_daily`는 상세를 연 세션을
분모로 비율을 내지만 이 Mart는 이탈 지점의 분포다.

합칠 수 없는 이유는 원천이 다르기 때문이다. `exit_summary.last_content_kind`는 계약에
선언돼 있지만 값이 실리지 않는다(실측 0/1,000). 그래서 이 Mart는 `exit_summary`가
아니라 **콘텐츠 Event의 마지막 시각**으로 이탈 지점을 정한다.

**세션·상품마다 행이 하나다.** 마지막 Event 한 건만 남기므로 한 세션이 같은 상품에서
두 이탈 지점을 갖지 않는다. 따라서 `last_content_kind`로 합산하면 그 상품의 "콘텐츠를
읽은 세션 수"가 되고, 상세를 연 세션 수를 넘지 않는다.

같은 시각이면 `event_id` 사전순으로 고정한다. 규칙이 없으면 실행마다 판정이 흔들려
재계산 결정성이 깨진다.

`content_kind`는 `properties_json`에서 읽는다. `product_id`·`brand_id`가 없는 행은
어느 상품의 이탈인지 알 수 없어 제외한다.

### 4.25 `segment_content_daily`

```text
key = event_date_kst + brand_id + skin_type + content_kind + actor_type + source + generator_type + scenario_id + simulation_run_id
input = section_dwell_agg, sessionized_events, bridge_persona_segment
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | 세그먼트 콘텐츠 축 |
| `dwell_ms_sum` | bigint | N | 그 콘텐츠에 머문 시간 합 |
| `dwell_sessions` | bigint | N | 그 콘텐츠를 본 고유 세션 수 |
| `segment_dwell_ms_sum` | bigint | N | 분모. 그 피부 타입의 같은 브랜드·일자 체류 총합 |
| `dwell_share` | double | Y | `dwell_ms_sum / segment_dwell_ms_sum` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

**`dwell_share`의 분모는 그 피부 타입의 총합이다.** 한 타입 안에서 share를 더하면
1이 되고, **타입끼리 더하면 안 된다** — 타입마다 모집단이 다르다. 분모를
`segment_dwell_ms_sum`으로 같이 실어 화면이 share를 역산해 확인할 수 있게 한다.

**`persona_id`가 없는 세션은 어느 세그먼트에도 넣지 않는다.** 임의 귀속은 없는
고객군을 만들어 내는 일이라 빼는 쪽이 정직하다(§4.6과 같은 규칙). `bridge`에 없는
persona도 같다. `notSureST`는 값이 아니라 결측이라 제외한다.

**`section_dwell_agg`에는 `is_seeded`가 없다.** `_observed_events`는 그 컬럼이 없는
입력을 그대로 통과시키므로, 이 Mart는 `sessionized_events`에서 시드 세션 목록을 만들어
`session_id`로 뺀다. 재생 데이터에 시드 세션 행이 993건 있어 빼지 않으면 섞인다.
판정의 정본은 `properties.seeded`이고 `session_id`의 `seed:` 접두는 파생이다(§3.14).

MySQL projection에서 `content_kind`는 nullable로 선언된다. 이 Mart는 결측을 빼지만
§4.4·§4.21의 같은 컬럼이 nullable이라, 생성기가 컬럼 이름으로 NULL 정책을 맞춘다
(VARCHAR 길이와 같은 규칙 — §7.4). 값이 들어가지 않으므로 적재에 영향은 없다.

`skin_tone`을 축에 넣지 않는다. E4 `top_content`가 타입 4행만 그린다
(`dashboard-mart-api-spec.md` §3 E4). 교차 축이 필요해지면 §4.6처럼 별도 행으로 낸다.

**현재 재생 데이터에서는 한 칸만 찬다.** 등장하는 persona 1,000명이 전원
`combination`이다. 층화 표본 재생성(Jira 318)이 반영된 로그로 다시 돌려야 네 타입이
모두 나온다. Mart 구조와 단위 테스트는 그와 무관하다.

### 4.26 `segment_price_band_daily_kpi`

```text
key = event_date_kst + brand_id + segment_type + segment_value + price_bin + currency + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, dim_product, bridge_persona_segment
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | price_bin·generator/scenario/run만 Y | 고객군 × 가격 교차 축 |
| `segment_user_count`, `session_count` | bigint | N | 세그먼트 규모 |
| `product_view_sessions`, `detail_view_sessions`, `add_to_cart_sessions`, `purchase_sessions` | bigint | N | 단계별 고유 세션 수 |
| `product_count` | bigint | N | 그 셀에서 밟은 고유 상품 수 |
| `view_to_cart_rate`, `view_to_purchase_rate` | double | Y | 분모는 `detail_view_sessions` |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

대시보드 고객군 화면의 S5 히트맵을 채운다
(`docs/dashboard/dashboard-redesign-spec.md` §2-3).

**§4.6·§4.6-1 중 어느 쪽에도 축을 얹을 수 없어서 나눈 Mart다.** 세션 하나는 여러
가격대의 상품을 밟고 동시에 `skin_type` 행과 `skin_tone` 행에 들어간다. 축을 더하면
그 축을 걷어낸 합계가 같은 세션을 여러 번 센다. 같은 함정이 Jira 235에서 실제로
났다 — 브랜드 세션을 상품 Mart 합산으로 구했다가 876행이 336행으로 정정됐다.

**세 Mart를 서로 대체하지 않는다.** `price_bin`을 걷어낸 합계는 §4.6과 같지 않고,
`segment_*`를 걷어낸 합계는 §4.6-1과 같지 않다.

**`segment_type`이 다른 행을 합산하지 않는다.** 한 세션이 `skin_type` 행과
`skin_tone` 행에 동시에 들어가므로 더하면 두 번 센다. §4.6과 같은 규칙이다.

**교차 축(`skin_type_x_skin_tone`)은 내지 않는다.** 여기에 또 얹으면 셀이 100개가
되어 표본이 무너진다. S5 정의가 5밴드 × 4타입 = 20셀이다.

**`persona_id`가 없는 세션은 어느 행에도 넣지 않는다.** 실제 사용자의 피부 정보는
Event 경로에 없으므로 임의 귀속은 없는 사실을 만들어 낸다. 그래서 이 Mart의 세션
합은 §4.14 전체와 같지 않고, 다른 것이 정상이다. `notSureST`는 값이 아니라 결측이라
`segment_value`가 되지 않는다(§4.6과 같다).

**`currency`를 key에 둔다.** 통화가 다른 가격을 환산 규칙 없이 한 구간으로 합치지
않는 것을 필터가 아니라 grain으로 지킨다. 가격이 NULL이거나 0 이하인 상품은
`price_bin = NULL` 행으로 보존한다 — 빼면 그 상품들의 반응을 볼 수 없고, 임의
구간에 넣으면 그 구간이 오염된다. §4.6-1과 같은 규칙이다.

가격 구간은 `contracts/product-feature-vocab.json`의 `price_bin_edges`를 읽는다.
숫자를 여기에 복제하지 않는다 — 추천 CBF 피처·배너 축·상품 등록 화면이 같은 값을
쓰므로 갈라지면 같은 이름의 가격대가 두 벌이 된다. 현재 어휘집 0.7 기준 원화
`[0, 26000, 46000, 66000, 105000]`이다(Jira 302).

**표본 미달 셀을 지우지 않는다.** 화면이 `n<50`을 비우고 `n<200`을 흐리게 표시한다
(`frontend/src/dashboard/screens/SegmentsScreen.tsx`의 기존 격자와 같은 기준).
Mart는 세션 수를 그대로 싣고 판정은 읽는 쪽 몫이다 — §4.18의 억제와 다르다.
그쪽은 다른 브랜드에게 보이는 B층이라 Mart가 지우지만, 이것은 자기 브랜드만 보는
A층이다.

시드 Event는 제외한다(§4.0).

**실데이터로 검증할 수 없는 규칙이 셋 있다.** 카탈로그 208개가 전부 원화(`KRW`)이고
`base_price`가 NULL이거나 0 이하인 상품이 0개이며, `product_event_fact`가 전부
`actor_type=synthetic`이다. 따라서 통화 혼합 · 가격 결측 · 실사용자 미귀속 세 규칙은
fixture 테스트로만 덮인다(§4.10의 `banner_type` 커버리지 한계와 같은 성격).

**현재 재생 데이터에서는 격자가 한 줄만 찬다.** 등장 persona 1,000명이 전원
`combination`·`light`다. 층화 표본 재생성(Jira 318 반영 완료, 로그 재생성 대기)이
된 로그로 다시 돌려야 4타입 × 5밴드가 찬다. `purchase_sessions`도 생성기가 결제를
내기 시작해야 0을 벗어난다(Jira 312).

### 4.27 `event_daily`

```text
key = event_date_kst + brand_id + event_name + actor_type + source + generator_type + scenario_id + simulation_run_id
input = cleaned_events, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | brand/generator/scenario/run만 Y | Event 볼륨 축 |
| `event_count` | bigint | N | 그 날 그 Event 수 |
| `unique_session_count` | bigint | N | 그 Event를 낸 고유 세션 수 |
| `unique_user_count` | bigint | N | 고유 사용자 수 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

E6의 `event_volumes` 블록이 읽는다(`dashboard-mart-api-spec.md` §3 E6).

**다른 Mart와 달리 Event를 고르지 않고 전부 센다.** "어제 로그가 정상적으로
들어왔나"를 보는 진단 지표라서다. 그래서 `event_count`의 합은 `cleaned_events`의
관측 Event 수와 **정확히 같아야 한다** — Q5가 이것을 검사한다.

**`brand_id`가 NULL인 행을 지우지 않는다.** `section_dwell`·`page_view`·
`session_start`·`exit_summary`처럼 상품에 귀속되지 않는 Event가 있고, 재생 데이터
기준 그것이 전체 Event의 **59%(603,564건)**다. 지우면 볼륨 진단이 성립하지 않고
위의 합계 검사도 깨진다. 화면이 브랜드로 거르면 자연히 빠지므로 Mart가 미리 지울
이유가 없다.

`brand_id`는 `dim_product`에서 보강한다. `cleaned_events`에는 상품 차원이 붙기
전이라 브랜드가 없다. 조인은 **left**다 — `inner`로 하면 플랫폼 공통 Event가 통째로
사라진다.

시드 Event는 제외한다(§4.0). 관측된 볼륨을 재는 지표이고, 시드는 생성기가 주입한
표식이지 방문이 아니다.

**§5.1 `realtime_event_stats`를 쓰지 않은 이유**는 그 key에 `brand_id`가 없어 E6의
"브랜드 필터 가능" 요구를 못 맞추기 때문이다. 분 단위 스트리밍 Mart는 상시 구동
Job과 별도 서빙 경로가 필요한데, 배치 Mart는 전부 MySQL projection을 통해 서빙한다.
배치 주기가 일 1회로 확정된 이상 분 단위 신선도에 의미가 없다.

## 5. 실시간 Mart 후보

### 5.1 `realtime_event_stats`

**미구현이고, 현재 정의로는 E6를 채울 수 없다.** key에 `brand_id`가 없어
`dashboard-mart-api-spec.md` §3 E6의 "브랜드 필터 가능해야 한다"를 못 맞춘다.
E6의 `event_volumes`는 §4.27 `event_daily`가 채운다(Jira 323). 이 절은 운영
모니터링용 정의로 남긴다 — 실행 축도 4종이라 구현하려면 `generator_type`을
먼저 넣어야 한다(§2).

```text
key = event_minute_kst + event_name + source + actor_type + scenario_id + simulation_run_id
input = cleaned_events
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | 분 단위 축 |
| `event_count`, `unique_session_count` | bigint | N | 정상 Event·세션 수 |
| `avg_ingest_latency_ms`, `p95_ingest_latency_ms`, `avg_processing_lag_ms`, `p95_processing_lag_ms`, `events_per_second` | double | Y | 지연·처리량 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 5.2 `realtime_bad_event_stats`

**미구현이고 소비자가 없다** (2026-09-16). `bad_events`는 실제로 쌓이고 Q5가 건수를
보고 있어 운영 지표로 쓸 여지는 있지만, 읽는 화면이 없다. §5.1과 같이 상시 구동
Job이 필요하다.

```text
key = event_minute_kst + error_stage + error_code + event_name + source + actor_type
input = bad_events
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `event_minute_kst`, `error_stage`, `error_code` | timestamp/string | N | 오류 집계 축 |
| `event_name`, `source`, `actor_type` | string | Y | 파싱 가능한 경우의 Event 정보 |
| `bad_event_count` | bigint | N | 격리 Event 수 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

Collector가 Kafka 전송 전에 거부한 Event는 별도 topic/storage가 없는 한 이 Mart에
포함하지 않는다.

## 6. 후보 Mart 물리화 시 보존할 조건

1. Parquet `marts`와 MySQL `dw` projection은 같은 grain과 KPI 값을 가져야 한다.
2. MySQL serving table은 API 조회에 불필요한 상세 컬럼을 생략할 수 있지만 key와
   KPI 의미를 바꾸지 않는다.
3. `category_id`, `brand_id`는 `dim_product`에서 보강한 집계 시점 스냅샷이다.
4. 행동 `purchase` Event와 `purchase_fact`는 전환·재구매 분석에만 사용한다.
   매출·정산은 Backend의 PAID 주문 상품 Fact만 정본으로 사용한다.
   행동 `purchase_count`는 `order_id` 기준 고유 전환 수이며 상품 row 수가 아니다.
5. `generator_type`, `scenario_id`, `simulation_run_id`는 Processed에서 승격된
   synthetic metadata를 사용한다.
6. 상품 대상 Mart는 `product_id`에서 파생한 `brand_id`를
   집계 시점 스냅샷으로 보존한다.
7. 상품이 없는 플랫폼 공통 Event를 특정 상품·브랜드에 임의 귀속하거나
   상품·브랜드 KPI에 포함하지 않는다. 플랫폼 공통 콘텐츠는 필요할 때 별도 grain으로
   집계한다. 대시보드 접근 격리는 Backend 인가가 담당한다.
8. `*_interest_score`를 0으로 하한 절단하지 않는다. 음수는 부정 행동의 신호다.
9. §2.4의 표기 병합을 집계 전에 적용한다. 특히 상품 리뷰 통계의 `brunette`를
   `brown`으로 합치지 않으면 segment Join이 같은 사람을 둘로 나눈다.

## 7. MySQL `dw` projection

### 7.1 적재 방식

Spark는 Mart를 계산해 Parquet으로 쓰고, **적재 Job이 그것을 MySQL `dw`로 옮긴다.**
적재 Job은 백엔드가 구현한다 (2026-09-15 합의). 이 절은 그 Job이 지켜야 할 계약이다.

```text
Parquet marts/<mart>          기준 저장소 (§1)
  → dw.<mart>__stg_<run_id>   실행별 staging 테이블에 적재
  → 검증                       건수 · 키 중복 · 필수값
  → dw.<mart>                 조회 테이블과 교체
```

**조회 테이블을 직접 지우고 다시 넣지 않는다.** 적재 도중 조회가 들어오면 빈 결과나
반쪽 결과를 보게 된다. staging에 다 넣고 검증이 끝난 뒤 한 번에 바꾼다.

**검증에 실패하면 기존 조회 결과를 유지한다.** 오래된 값이 잘못된 값보다 낫다.
실패한 staging 테이블은 원인을 확인할 수 있도록 남기고, 다음 성공 적재가 정리한다.

교체는 MySQL `RENAME TABLE`의 원자성을 쓴다.

```sql
RENAME TABLE dw.brand_daily_kpi        TO dw.brand_daily_kpi__old,
             dw.brand_daily_kpi__stg_1 TO dw.brand_daily_kpi;
DROP TABLE dw.brand_daily_kpi__old;
```

검증 항목은 셋이다. 셋 다 통과해야 교체한다.

| 검사 | 기준 |
| --- | --- |
| 건수 | staging 행 수 = Parquet 행 수 |
| 키 중복 | PRIMARY KEY 기준 중복 0건 |
| 필수값 | `NOT NULL` 컬럼에 NULL 0건 |

Q5(`validate_pipeline_job`)가 이미 같은 불변식을 Parquet 단계에서 검사한다. 적재
단계에서 다시 보는 이유는 **옮기는 과정 자체가 깨질 수 있기 때문**이다. 타입 변환에서
잘리거나, 부분 적재로 끝나거나, 문자열이 VARCHAR 길이를 넘칠 수 있다.

### 7.2 projection 대상과 적재 순서

**Parquet을 읽을 수 없는 소비자가 있는 Mart만 MySQL로 옮긴다.** 지금 그런 소비자는
둘뿐이다.

1. **Dashboard API** — Spark는 잡을 띄우는 데만 수 초라 조회를 받을 수 없다.
2. **추천 서버** — EC2-1에 있고 Parquet은 EC2-2에 있다. 파일을 읽을 수 없다
   (`deploy/ec2-2/README`: "EC2-1의 추천 데이터 Volume은 이 서버에 자동
   공유되지 않는다").

나머지는 Parquet에만 둔다. 소비자가 없는데 테이블을 만들면 적재 Job이 옮길 대상만
늘고, 스키마가 바뀔 때 고칠 곳도 는다.

| 순서 | Mart | 소비자 |
| --- | --- | --- |
| 1 | `user_trait_daily` | 추천 서버 `long_term_trait` (Jira 306) |
| 2 | `brand_daily_kpi`, `product_daily_kpi`, `funnel_daily_kpi` | Dashboard E1·E2 |
| 3 | `persona_segment_daily_kpi`, `brand_price_band_daily_kpi`, `segment_price_band_daily_kpi` | Dashboard E4 `by_segment`·`grid`·`price_bands`·`segment_price_grid` |
| 3-1 | `brand_cohort_dim`, `commons_cohort_weekly` | Dashboard E4 `cohort` |
| 4 | `ingredient_weekly_interest` | Dashboard E5 |
| 5 | `brand_repurchase_daily`, `product_repurchase_daily`, `purchase_reason_daily` | Dashboard E7 |

**E4의 네 블록은 2026-09-16에 합의됐다** (프론트 계약 0.3). `price_bands`·
`segment_price_grid`·`cohort` 세 블록을 넣기로 하면서 `brand_price_band_daily_kpi`·
`segment_price_band_daily_kpi`·`brand_cohort_dim`·`commons_cohort_weekly`가
projection 대상이 됐다.

`cohort` 블록은 표 두 개를 함께 쓴다. 서버가 `brand_cohort_dim`에서 그 브랜드의
`cohort_key`를 찾고, 그 값으로 `commons_cohort_weekly`의 코호트 행을 고른다.
**`brand_cohort_dim` 없이는 `commons_cohort_weekly`를 읽을 수 없다** — 코호트 행에
브랜드 식별자가 없기 때문이다(§4.18 R5).

MySQL로 옮기지 않는 Mart와 그 이유다.

| Mart | 이유 |
| --- | --- |
| `banner_daily` | 읽는 엔드포인트가 없다. 배너 성과는 Q5 검증과 기준선 대조에만 쓴다 |
| `cross_brand_daily` | 읽는 엔드포인트가 없다 |
| `category_price_reference` | 카탈로그 파생 참조표다. Event를 읽지 않고 브랜드 축도 없다 |
| `analytics_baseline` | 배너 도입 전후를 비교하는 정책 스냅샷이다. 브랜드별 기간 조회가 아니다 |

소비자가 생기면 DDL 생성기의 `GRAINS`에 한 줄 더하고 다시 돌린다.

**`brand_cohort_dim`을 뺐던 근거는 틀렸다.** "`cohort_key`는 Backend가 브랜드
인가와 함께 넘긴다"고 적었으나, 이 Mart가 Parquet에만 있어 **Backend가 그 값을 알
경로가 없었다.** 검증하지 않은 추정이었고 프론트 검토에서 드러났다(2026-09-16).
제외 사유를 적을 때는 그 소비자가 실제로 다른 경로를 갖고 있는지 확인한다.

### 7.2.1 projection에서 빼는 컬럼

§6-2가 "API 조회에 불필요한 상세 컬럼을 생략할 수 있지만 key와 KPI 의미를 바꾸지
않는다"고 허용한다. 지금 빼는 것은 둘뿐이다.

| Mart | 컬럼 | 이유 |
| --- | --- | --- |
| `product_daily_kpi` | `revenue_amount` | 행동 로그 기반 금액이다. §6-4가 매출·정산 합산을 금지한다 |
| `product_daily_kpi` | `currency` | `revenue_amount`의 단위라 함께 뺀다 |

**비율 컬럼은 빼지 않는다.** count에서 다시 나눌 수 있지만, 분모 규칙이 계약에만
있어서 소비자가 틀릴 수 있다. 실제로 그 실수가 났다 — `product_daily_kpi`의
`add_to_cart_rate`가 1,248행 중 323행에서 1.0을 넘었고 원인이 분모였다(Jira 277).
비율을 값으로 실어 보내는 것이 그 규칙을 소비자에게 전달하는 방법이다.

### 7.3 타입 매핑

논리 타입에서 MySQL 타입으로 가는 규칙이다. **새 Mart도 이 표를 따른다.**

| 논리 타입 | MySQL | 근거 |
| --- | --- | --- |
| date | `DATE` | |
| timestamp | `DATETIME(3)` | `TIMESTAMP`는 2038년 상한과 자동 갱신이 있다. 집계 시각에 둘 다 필요 없다 |
| bigint | `BIGINT` | |
| int | `INT` | |
| double | `DOUBLE` | 비율·점수. 정확한 소수가 필요한 값은 여기 없다 |
| decimal(18,2) | `DECIMAL(18,2)` | 금액. `DOUBLE`로 두면 합산에서 오차가 쌓인다 |
| boolean | `TINYINT(1)` | MySQL에 boolean이 없다 |
| array&lt;string&gt; | `JSON` | Dimension에만 있다. Mart는 배열 컬럼을 두지 않는다 |
| string | `VARCHAR(n)` | 길이는 §7.4 |

문자 집합은 `utf8mb4` / `utf8mb4_0900_ai_ci`다. `label_ko` 같은 한국어 컬럼이 있고,
이모지가 섞여도 깨지지 않아야 한다.

### 7.4 VARCHAR 길이

**컬럼 이름이 같으면 어느 Mart에 있든 길이가 같아야 한다.** 다르면 조인과 적재에서
잘린다. 아래는 2026-09-15 재생 데이터(100만 건) 실측 최댓값에 여유를 둔 값이다.

| 컬럼 | 실측 최댓값 | VARCHAR | 비고 |
| --- | --- | --- | --- |
| `brand_id` | 36 | 64 | UUID 36자. 입점 브랜드는 `ssafy-beauty` 같은 slug |
| `product_id` | 8 | 64 | `P420652`, `SB000001` |
| `ingredient` | 24 | 128 | 성분명 |
| `metric_name`, `secondary_category`, `segment_type` | 22 | 64 | |
| `policy_version`, `trait_policy_version`, `baseline_policy_version`, `vocab_version` | 19 | 32 | |
| `segment_value` | 17 | 64 | 교차 축 `dry\|fair` 형식 |
| `algorithm`, `reference_source`, `label_ko` | 16 | 64 | |
| `generator_type`, `scenario_id`, `simulation_run_id` | 12 | 64 | |
| `trait`, `banner_type`, `trait_source`, `actor_type`, `source`, `price_bin`, `identity_scope`, `currency` | ≤10 | 32 | enum 성격 |
| `user_id` | 7 | 64 | 회원 id와 Persona id가 같은 공간을 쓰지 않는다 |
| `banner_value` | — | 128 | 어휘집 원문. 실데이터에 `new_brand`(NULL)뿐이라 미실측 |

실측이 없는 컬럼은 어휘집·계약의 최대 길이에 여유를 둔다. 길이를 늘리는 것은 온라인
DDL로 가능하지만 줄이는 것은 데이터 손실이므로, 애매하면 넉넉히 잡는다.

### 7.5 NULL 정책

**NULL 허용 여부는 계약의 의도에서 온다. 데이터로 판정하지 않는다.**

지금 데이터에 NULL이 없다는 것과 그 컬럼이 NULL일 수 없다는 것은 다르다. 실제로
`brand_price_band_daily_kpi.price_bin`은 가격이 없는 상품을 버리지 않고 보존하려고
**설계상 NULL을 허용**하는데(§4.6-1), 현재 카탈로그 208개에 가격 결측이 0개라
데이터에는 NULL이 한 건도 없다. 데이터로 정하면 `NOT NULL`이 되고, 가격 없는 상품이
처음 등록되는 순간 적재가 거부된다.

§4에 nullable이 명시된 컬럼은 그대로 따른다. 명시가 없으면 아래 성격으로 정한다.

| 성격 | NULL | 근거 |
| --- | --- | --- |
| grain key | `NOT NULL` | 키가 비면 행을 식별할 수 없다 |
| ㄴ `generator_type`, `scenario_id`, `simulation_run_id` | 허용 | §2.2 — Web은 NULL |
| ㄴ `brand_id` | 허용 | §2.2 — 상품 미귀속 Mart |
| ㄴ `price_bin` | 허용 | §4.6-1 — 가격 결측 보존 |
| count (bigint) | `NOT NULL` | 0은 "없음"이지 "모름"이 아니다 |
| 비율 (double) | 허용 | 분모가 0이면 NULL이라고 §4가 이미 강제한다 |
| 점수 (double) | 허용 | 가중치가 없는 실행에서는 NULL이다 |
| Dimension 스냅샷 (`category_id` 등) | 허용 | 매칭되지 않을 수 있다 |
| `mart_processed_at` | `NOT NULL` | 갱신 시각은 항상 있다 |

데이터는 **교차 검증**에만 쓴다. 계약이 `NOT NULL`이라는데 데이터에 NULL이 있으면
둘 중 하나가 틀린 것이므로 원인을 찾는다.

### 7.6 명명과 인덱스

| 대상 | 규칙 |
| --- | --- |
| 조회 테이블 | Mart 이름 그대로. `dw.brand_daily_kpi` |
| staging | `dw.<mart>__stg_<run_id>` |
| 교체 중 백업 | `dw.<mart>__old` — 교체 직후 삭제 |
| 대리키 | `dw_row_id BIGINT AUTO_INCREMENT` |
| grain 인덱스 | `ix_<mart>__grain` — §4의 grain 전체. 선두는 아래 규칙 |

**grain을 PRIMARY KEY로 둘 수 없다.** 실행 축(`generator_type`·`scenario_id`·
`simulation_run_id`)과 `brand_id`가 NULL을 허용하는데(§2.2), MySQL은 PRIMARY KEY에
NULL을 넣지 못한다. UNIQUE KEY도 답이 아니다 — NULL을 서로 다른 값으로 보므로
`(brand_id=NULL, …)` 행이 몇 개든 중복으로 잡히지 않는다.

그래서 **대리키를 PRIMARY KEY로 두고 grain은 보조 인덱스로 둔다.** projection 대상
10종이 전부 여기 해당한다 — 모든 Mart가 grain에 실행 축을 갖기 때문이다. 실행 축 없이
카탈로그에서만 파생하는 Mart가 생기면 그때는 복합 PRIMARY KEY를 쓸 수 있다.

**따라서 grain 유일성은 DB가 지켜주지 않는다. 적재 Job이 §7.1의 키 중복 검증으로
막는다.** 이 검증을 건너뛰면 중복 행이 조용히 쌓이고 대시보드 합계가 부풀어 오른다.

grain 인덱스의 컬럼 순서가 조회 성능을 정한다. **어떻게 읽히는가로 선두를 정한다.**

| 읽는 방식 | 선두 | 해당 Mart |
| --- | --- | --- |
| 브랜드 하나의 기간 범위 | `brand_id` | 일간 KPI·재구매·구매이유·배너·교차유입 |
| 사용자 한 명 | `user_id` | `user_trait_daily` |
| 주차 범위 | `interest_week_kst` | `ingredient_weekly_interest` — 브랜드 축이 없다 |
| 카테고리 | `secondary_category` | `category_price_reference` — 카탈로그 파생 |
| 정책 버전 | `baseline_policy_version` | `analytics_baseline` — 기간 조회가 아니라 정책 스냅샷이다 |

§4의 key 표기가 날짜를 앞에 두는 Mart는 인덱스에서 순서를 바꾼다 — grain의
**구성**은 같고 **정렬 순서**만 다르다.

인덱스 키 길이는 InnoDB 상한 3072 byte 안이어야 한다. `utf8mb4`는 문자당 4 byte라
VARCHAR를 넉넉히 잡으면 넘기 쉽다. 2026-09-15 기준 가장 긴 것이 `banner_daily`의
2,203 byte다 (grain 12컬럼). 새 Mart를 더할 때 확인한다.

보조 인덱스는 grain 인덱스 선두로 커버되지 않는 조회에만 둔다.

| Mart | PRIMARY KEY 선두 |
| --- | --- |
| 일간 KPI 계열 | `(brand_id, event_date_kst, …)` |
| 재구매 계열 | `(brand_id, snapshot_date_kst, …)` |
| `ingredient_weekly_interest` | `(interest_week_kst, …)` — 브랜드 축이 없다 |
| `user_trait_daily` | `(user_id, trait_date_kst, trait, …)` — 사용자 단건 조회 |

