# DW / Mart Schema Contract

작성일: 2026-09-02  
최종 정적 검증: 2026-09-07
상태: 통합 쇼핑몰의 브랜드·상품 귀속 계약 및 물리 구현 반영

## 1. 범위와 우선순위

이 문서는 [`processed-schema.md`](./processed-schema.md)의 Processed Dataset을
Delta Lake에 보존하고 MySQL `dw`로 제공하는 저장 계층, 책임 경계와 공통 물리
규칙을 확정한다. Dimension과 Mart의 grain, 입력, key, 컬럼, 논리 타입 및 nullable은
현재 Dashboard 후보를 구현 가능성 관점에서 정리한 초안이다.

- Delta Lake의 `marts`는 계산 결과의 기준 저장소다.
- MySQL `dw` schema는 Dashboard API 조회용 serving projection이다.
- 물리 파티션, 인덱스, Delta `MERGE`, MySQL DDL은 구현 단계에서 확정된 저장
  계층과 공통 규칙을 보존하는 범위로 정한다.
- 처리 근거, KPI 화면 연결, 현재 구현 상태와 검증 계획은
  [`../docs/analytics/dw-design.md`](../docs/analytics/dw-design.md)에서 설명한다.

§2의 입력 grain·공통 타입·NULL·집계 원칙과 Delta→MySQL 책임 경계는 이번 작업의
확정 범위다. §3~§5의 Dimension·Mart·KPI는 저장 가능성을 확인하기 위한 후보이며,
Dashboard에 실제 제공할 지표는 추천·AI 담당과 합의한 뒤 별도 확정한다.

## 2. 공통 계약

### 2.1 입력

| 입력 | grain | 용도 |
| --- | --- | --- |
| `cleaned_events` | `event_id` | 정상 Event 수와 실시간 통계 |
| `product_event_fact` | `event_id + item_index + product_id` | 상품·추천·구매 집계 |
| `review_event_fact` | `event_id + product_id` | 리뷰 펼침·필터·정렬·리뷰 영역 체류 상세 |
| `search_event_fact` | `event_id` | 검색 집계 |
| `section_dwell_agg` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 체류 검증·재집계 |
| `content_interest_fact` | `session_id + page_view_id + product_id + section_id + content_kind + content_ref` | 콘텐츠 관심 집계 |
| `purchase_fact` | `order_id + product_id` | 행동 Event 기반 구매 전환·재구매 집계. 매출·정산에는 사용 금지 |
| `purchase_reason_fact` | `order_id + reason` | 구매 이유 집계, 행동 추론 대조 |
| `funnel_session_fact` | `session_id + product_id` | 단계 도달·이탈 집계 |
| `persona_behavior_feature_delta` | `event_id + user_id + product_id` | Persona 관심도 집계 |
| `bad_events` | 격리 Event 1건 | Spark에서 관측한 오류 집계 |

모든 Mart는 `event_id` 중복 제거가 끝난 Processed Dataset만 입력으로 사용한다.
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

`brand_hash`와 `commons_participating`의 산출·억제 규칙은 Commons Mart 작업에서
확정한다. 브랜드 계정과의 1:1 인증 매핑은 Backend가 소유하고 DW에 복제하지 않는다.
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
| `base_price` | decimal(18,2) | Y | 기준 가격 |
| `currency` | string | Y | 가격 통화 |
| `rating` | double | Y | 평균 평점 |
| `rating_source` | string | Y | `observed`, `injected`. 주입값을 실측과 섞지 않는다 |
| `review_count`, `loves_count` | bigint | Y | 리뷰·관심 수 |
| `skin_type_tags`, `concern_tags`, `ingredient_ids` | array<string> | Y | 상품 속성 |
| `caution_ingredient_count` | int | Y | 주의 성분 수 |
| `updated_at` | timestamp | Y | 갱신 시각 |

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

## 4. 일간 Mart 후보

아래 Mart는 현재 Dashboard 요구를 저장 구조에 투영한 후보안이다. 지표 채택 전에는
물리 Table 생성 계약으로 해석하지 않는다. 채택 시 표의 `key` 전체를 복합 key로
사용하고, `scenario_id`, `simulation_run_id`가 NULL인 Web 행도 같은 grain 규칙으로
집계한다.

### 4.0 시드 Event 제외 범위

`is_seed=true`인 Event는 생성기가 Persona의 사전 선호를 주입한 표식이라 관측된
행동이 아니다(`processed-schema.md`, `event-properties-schema.md` §3.14·§7-8). 아래가
제외 여부의 정본이다.

| Mart | 시드 | 근거 |
| --- | --- | --- |
| `funnel_session_fact`, `product_daily_kpi`, `funnel_daily_kpi`, `brand_daily_kpi`, `cross_brand_daily` | 제외 | 전환 퍼널. 긍정 시드는 조회 없는 담기를, 부정 시드는 담기 없는 조회를 내서 분자·분모를 양방향으로 왜곡한다 |
| `product_repurchase_daily`, `brand_repurchase_daily`, `purchase_reason_daily` | 제외 | 구매 행동. 같은 원칙 |
| `banner_daily` | 제외 | 노출·클릭 행동. 시드는 배너 Event를 내지 않아 실제 차이는 없다 |
| `ingredient_weekly_interest` | 제외 | 탐색으로 드러난 관심을 재는 지표다 |
| `analytics_baseline` | 제외 | 위 Mart의 기준선이라 같은 모집단을 써야 한다 |
| `user_trait_daily` | **유지** | 장기 성향이 재려는 것이 바로 주입된 선호다. 뺄지는 미결 |
| `category_price_reference` | 해당 없음 | 카탈로그 파생이라 Event를 읽지 않는다 |

### 4.1 `product_daily_kpi`

```text
key = event_date_kst + brand_id + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = product_event_fact, purchase_fact, persona_behavior_feature_delta, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통 계약 | key 규칙 | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `purchase_count`, `purchase_quantity` | bigint | N | Event·수량 집계. `purchase_count`는 `order_id` 기준 고유 주문 수 |
| `quick_look_sessions`, `product_view_sessions`, `add_to_cart_sessions`, `remove_from_cart_sessions`, `purchase_sessions`, `unique_user_count`, `session_count` | bigint | N | 세션·사용자 집계 |
| `product_ctr`, `detail_entry_rate`, `add_to_cart_rate`, `purchase_rate`, `product_interest_score` | double | Y | 비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.2 `recommendation_daily_kpi`

```text
key = event_date_kst + brand_id + recommendation_id + list_id + algorithm + product_id + context_product_id + position + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string/int | `list_id`, `context_product_id`, scenario/run만 Y | 집계 축 |
| `recommendation_impression_count`, `recommendation_click_count`, `unique_session_count` | bigint | N | 추천 성과 |
| `recommendation_ctr` | double | Y | 클릭/노출 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.3 `search_daily_kpi`

```text
key = event_date_kst + search_query_hash + actor_type + source + scenario_id + simulation_run_id
input = search_event_fact, product_event_fact
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | scenario/run만 Y | 집계 축 |
| `normalized_query` | string | Y | 저장 정책이 허용할 때만 보존 |
| `search_count`, `search_session_count`, `zero_result_count`, `search_click_session_count`, `clicked_product_count` | bigint | N | 검색 성과 |
| `avg_result_count`, `search_to_click_rate` | double | Y | 평균·전환율 |
| `top_clicked_product_id` | string | Y | 최다 클릭 상품 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.4 `content_daily_kpi`

```text
key = event_date_kst + brand_id + product_id + section_id + content_kind + actor_type + source + scenario_id + simulation_run_id
input = content_interest_fact, section_dwell_agg, funnel_session_fact, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | section/content/scenario/run만 Y | 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `section_view_count`, `section_view_sessions`, `dwell_ms_sum`, `accordion_expand_count`, `text_selection_count`, `text_copy_count`, `matched_ingredient_count`, `ingredient_view_sessions`, `review_view_sessions`, `product_view_sessions` | bigint | N | 콘텐츠 행동 집계 |
| `avg_dwell_ms_per_session`, `ingredient_view_rate`, `review_view_rate`, `content_interest_score` | double | Y | 평균·비율·관심도 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`dwell_ms_sum`은 `content_interest_fact`를 기본 원천으로 사용한다.
`section_dwell_agg`와 동시에 합산하지 않는다.
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
| `impression_sessions`, `click_sessions`, `quick_look_sessions`, `detail_view_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `checkout_sessions`, `purchase_sessions` | bigint | N | 단계 도달 세션 |
| `impression_to_click_rate`, `click_to_view_rate`, `view_to_information_rate`, `view_to_cart_rate`, `cart_to_purchase_rate`, `view_to_purchase_rate`, `dropoff_after_impression_rate`, `dropoff_after_view_rate`, `dropoff_after_cart_rate` | double | Y | 전환·이탈률 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`detail_view_sessions`의 정의와 분모 규칙은 §4.14와 같다. `view_to_cart_rate`,
`view_to_purchase_rate`, `dropoff_after_view_rate`는 `detail_view_sessions`를 분모로
쓰고, `view_to_information_rate`는 상품 상세에서만 일어나므로 `product_view_sessions`를
유지한다. `dropoff_after_view_rate`는 `view_to_cart_rate`의 여집합이라 같은 분모여야 한다.

`quick_look_cart_sessions`, `direct_click_sessions`, `direct_click_cart_sessions`는
0.1에서 열거만 하고 의미를 정의하지 않아 구현하지 않았다. 정의가 정해지면 추가한다.

### 4.6 `persona_segment_daily_kpi`

```text
key = event_date_kst + brand_id + segment_type + segment_value + product_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = funnel_session_fact, persona_behavior_feature_delta, bridge_persona_segment, dim_persona_segment, dim_product
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator/scenario/run만 Y | segment 집계 축 |
| `category_id`, `brand_id` | string | Y | 상품 차원 스냅샷 |
| `segment_user_count`, `session_count`, `product_view_sessions`, `add_to_cart_sessions`, `purchase_sessions` | bigint | N | 행동 집계 |
| `avg_interest_score`, `category_interest_score`, `affinity_lift` | double | Y | 행동 로그 기반 지표 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

### 4.7 `scenario_daily_kpi`

```text
key = event_date_kst + scenario_id + simulation_run_id + actor_type + source + generator_type
input = cleaned_events, product_event_fact, funnel_session_fact, content_interest_fact, persona_behavior_feature_delta
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| key 전체 | 공통/string | generator만 Y | synthetic 실행 비교 축 |
| `event_count`, `session_count`, `persona_count`, `product_view_count`, `add_to_cart_count`, `purchase_count` | bigint | N | 실행 성과 |
| `avg_event_count_per_session`, `avg_product_interest_score`, `avg_content_interest_score`, `view_to_cart_rate`, `view_to_purchase_rate` | double | Y | 평균·전환율 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

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
      + trait_source + policy_version + actor_type + source + scenario_id + simulation_run_id
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
key = event_date_kst + destination_brand_id + actor_type + source + scenario_id + simulation_run_id
input = sessionized_events
```

`sessionized_events.event_order`로 정렬한 `product_view`만 사용하며, 세션 최초 브랜드와
목적 브랜드가 다를 때 교차 유입으로 판정한다. Front의 `cross_brand` boolean은 입력으로
사용하지 않고, 한 세션의 같은 목적 브랜드는 각 지표에서 한 번만 센다.

추천 귀속은 목적 `product_view.properties.recommendation_id`를 우선 사용하고, 값이 없으면
같은 세션·상품의 선행 `recommendation_click`을 사용한다. 배너 귀속은 같은 세션·상품의
선행 `banner_click`을 사용하며 직전 Event만으로 제한하지 않는다.

`brand_view_sessions`를 공통 분모로 `cross_brand_entry_rate`,
`recommendation_cross_brand_entry_rate`, `banner_cross_brand_entry_rate`를 저장한다. 또한
전체 교차 유입 세션을 분모로 `recommendation_share_of_cross_brand_entries`,
`banner_share_of_cross_brand_entries`를 저장한다. `top_source_brand_id`는 공개 임계값과
정책 버전이 확정될 때까지 산출하지 않는다.

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
| `impression_sessions`, `quick_look_sessions`, `detail_view_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions` | bigint | N | 브랜드 단계별 고유 세션 수 |
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
| `window_days`, `window_start_date`, `window_end_date` | int, date, date | N | 관측 창 |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

재구매는 **서로 다른 `order_id`** 기준이다. 한 주문에 같은 상품 row가 여러 개 있어도
구매는 한 번이며, 주문 단위로 먼저 접은 뒤 센다. 재구매 간격은 첫 구매와 마지막 구매의
간격을 구매 횟수로 나눈 사용자별 평균이고, 1회 구매자는 NULL이라 중앙값에 들어가지 않는다.
`snapshot_date_kst`는 입력의 최대 `event_date_kst`이며 창은 그 날부터 `window_days`일
직전까지다. `brand_id`·`user_id`·`order_id`가 비어 있는 row는 제외한다.

### 4.16 `brand_repurchase_daily`

```text
key = snapshot_date_kst + brand_id + actor_type + source + generator_type + scenario_id + simulation_run_id
input = purchase_fact, purchase_reason_fact
```

컬럼은 §4.15와 같고 `declared_restock_order_count`(bigint, N)가 추가된다.

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

## 5. 실시간 Mart 후보

### 5.1 `realtime_event_stats`

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

1. Delta `marts`와 MySQL `dw` projection은 같은 grain과 KPI 값을 가져야 한다.
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
