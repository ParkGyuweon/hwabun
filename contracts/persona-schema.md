# Persona Schema 계약

작성일: 2026-09-02
최종 검증: 2026-09-08, holdout A/B 계약 편입 · 전역 ID/집단 교집합 검증
상태: Draft, §2.1 holdout 계약 및 §7.1 정본 정렬 완료. Event·Run 축 E2E 검증 대기
설계 설명: [`persona-design.md`](../docs/analytics/persona-design.md)

## 1. 범위와 우선순위

이 문서는 Persona Profile, 리뷰 이력, 평가 split, segment, Attribute Affinity 입력,
Scenario 및 Simulation Run의 grain, key, 컬럼, 타입, nullable과 정규화 규칙을 정의하는
계약 원본이다.

추천 벡터 산식과 행동 집계는 [`recommendation-io-spec.md`](./recommendation-io-spec.md),
Synthetic Event runtime metadata는 [`event-schema.json`](./event-schema.json), Processed
승격 컬럼은 [`processed-schema.md`](./processed-schema.md)를 우선한다.

## 2. ID와 공통 규칙

### 2.1 Persona ID

| 표본 | 범위 | `persona_source` |
| --- | --- | --- |
| Agent 표본 100명 | `PA00001`~`PA00100` | `agent_sample` |
| Batch 표본 9,900명 | `PC00001`~`PC09900` | `batch_sample` |
| Holdout A 2,000명 | `PH00001`~`PH02000` | `holdout_sample` |
| Holdout B 2,000명 | `PH02001`~`PH04000` | `holdout_sample` |

분석에서 prefix나 ID 대역을 파싱하지 않는다. 생성 표본 구분은 `persona_source`, 평가
집단 구분은 `evaluation_cohort`를 사용한다. `evaluation_cohort` 허용값은 현재
`holdout_a`, `holdout_b`이며 PA·PC에서는 NULL이다.

원본 `personas_holdout_a.json`, `personas_holdout_b.json`은 기존 평가 재현성을 위해 둘 다
`PH00001`~`PH02000`을 유지한다. B의 ID를 직접 바꾸면 `persona_id` 기반 결정적 노이즈와
기존 평가 metadata 조인이 달라진다. 따라서 `build_persona_tables.py`가 계약/Dimension
적재 시 B에 2,000을 더한다. 향후 `holdout_c`는 같은 규칙으로
`PH04001`~`PH06000`을 사용한다. 원본 파일 ID는 분석·집단 판정에 사용하지 않는다.

### 2.2 상품 ID

| 필드 | 의미 |
| --- | --- |
| `source_product_id` | 원천 리뷰 상품 ID |
| `group_id` | 병합 대표 ID 후보 |
| `canonical_product_id` | `group_id`가 있으면 `group_id`, 없으면 `source_product_id` |
| `product_id` | Event·Product Feature·DW에서 사용하는 `canonical_product_id` |

### 2.3 Persona와 Runtime Context 분리

`persona_id`, `author_id`, `user_id`, `persona_source`, `evaluation_cohort`,
`profile_version`은 Persona에 귀속된다. `scenario_id`, `simulation_run_id`,
`generator_type`은 실행에 귀속되며 Persona 고유 속성으로 저장하지 않는다.

Synthetic Event에서는 `actor_type='synthetic'`, `user_id=persona_id`로 파생하고
`scenario_id`, `simulation_run_id`, `generator_type`을 Event `properties`에 넣는다.
`generator_type`은 `python_batch` 또는 `agent_llm`이다.

## 3. 사용자 속성 정규화

### 3.1 허용값

| attribute | 허용값 | nullable |
| --- | --- | --- |
| `skin_type` | `combination`, `dry`, `normal`, `oily` | N |
| `skin_tone` | `fair`, `light`, `medium`, `tan`, `deep` | N |
| `hair_color` | `auburn`, `black`, `blonde`, `brown`, `gray`, `red` | Y |
| `eye_color` | `blue`, `brown`, `gray`, `green`, `hazel` | Y |

### 3.2 원본 매핑

| 결과 | 원본 값 |
| --- | --- |
| `skin_type` 4종 | 원본 유지 |
| `fair` | `porcelain`, `fair`, `fairLight` |
| `light` | `light`, `lightMedium` |
| `medium` | `medium`, `mediumTan`, `olive` |
| `tan` | `tan` |
| `deep` | `deep`, `rich`, `dark`, `ebony` |
| `brown` hair | `brown`, `brunette` |
| `gray` eye | `gray`, `Grey` |

`skin_tone='notSureST'`는 값이 아니라 결측으로 처리한다. 사용자 속성은 imputation하지
않는다. Persona/Affinity 모집단은 사용자 속성 4개가 모두 존재하는 리뷰만 사용한다.

한 사용자의 리뷰별 속성이 다르면 `submission_time ASC → review_id ASC`로 정렬한 최신
리뷰 값을 full Profile 대표값으로 사용한다. 평가 Profile은 holdout을 제외한 최신 seed
리뷰 값을 사용한다.

## 4. `persona_profile`

```text
grain = persona_id
profile_scope = full
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Unique key |
| `author_id` | string | Y | 원천 리뷰어 ID, 외부 노출 금지 |
| `user_id` | string | N | Synthetic 분석 ID, 기본값 `persona_id` |
| `persona_source` | string | N | `agent_sample`, `batch_sample`, `holdout_sample` |
| `evaluation_cohort` | string | Y | 홀드아웃만 `holdout_a`, `holdout_b`; 그 외 NULL |
| `skin_type` | string | N | §3 enum |
| `skin_tone` | string | N | §3 enum |
| `eye_color` | string | Y | §3 enum |
| `hair_color` | string | Y | §3 enum |
| `stratum` | string | N | `skin_type\|skin_tone\|review_bucket` |
| `review_bucket` | string | N | `3`, `4`, `5-6`, `7+` |
| `n_reviews` | int | N | 원천 리뷰 수 |
| `n_products` | int | N | 고유 상품 수 |
| `n_positive` | int | N | 긍정 상품 수 |
| `n_negative` | int | N | 부정 상품 수 |
| `n_neutral` | int | N | 중립 상품 수 |
| `avg_rating` | double | Y | 평균 평점 |
| `latest_review_label` | string | N | 가장 최신 리뷰의 극성. `positive`, `negative`, `diagnostic` |
| `profile_version` | string | N | 생성·정규화 버전 |
| `profile_scope` | string | N | `full` |
| `created_at` | timestamp | N | 생성·적재 시각 |
| `updated_at` | timestamp | N | 갱신 시각 |

`latest_review_label`은 §7.1 정렬 기준의 첫 리뷰에 §7.1.1 긍정 조건과
[`recommendation-io-spec.md`](./recommendation-io-spec.md)의 리뷰 극성을 적용한 값이다.
긍정이면 `positive`, `rating <= 2`면 `negative`, 그 외는 `diagnostic`이다.

Holdout target이 마지막 긍정 리뷰로 바뀌면서 최신 리뷰의 극성은 target 판정에서
쓰이지 않는다. 그러나 "가장 최근에 불만이었던 고객"은 Dashboard의 이탈 직전 segment
신호이므로 Persona 속성으로 보존한다. `negative`와 `diagnostic`을 하나의 boolean으로
합치지 않는 이유는 불만과 미온적 반응의 마케팅 의미가 다르기 때문이다.

## 5. `persona_profile_eval`

```text
grain = persona_id
input = seed review only
profile_scope = eval
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Unique key |
| `profile_scope` | string | N | `eval` |
| `skin_type` | string | N | 최신 seed 리뷰 기준 |
| `skin_tone` | string | N | 최신 seed 리뷰 기준 |
| `eye_color` | string | Y | 최신 seed 리뷰 기준 |
| `hair_color` | string | Y | 최신 seed 리뷰 기준 |
| `n_reviews_seed` | int | N | seed 리뷰 수 |
| `n_products_seed` | int | N | seed 고유 상품 수 |
| `avg_rating_seed` | double | Y | seed 평균 평점 |
| `profile_version` | string | N | full Profile과 동일 버전 |
| `split_version` | string | N | 평가 split 버전 |

오프라인 평가에만 사용한다. 시뮬레이션과 Dashboard segment는 full Profile을 사용한다.

## 6. `persona_review_history`

```text
grain = persona_id + review_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `review_id` | string | N | Review ID |
| `author_id` | string | Y | 원천 리뷰어 ID |
| `source_product_id` | string | N | 원천 상품 ID |
| `group_id` | string | Y | 병합 대표 ID 후보 |
| `canonical_product_id` | string | N | 추천·분석 상품 ID |
| `product_name` | string | Y | 원천 표시명 |
| `brand_name` | string | Y | 원천 브랜드명 |
| `rating` | int | Y | 1~5 |
| `is_recommended` | boolean | Y | 추천 여부 |
| `review_title` | string | Y | 분석 원천, Event 전송 금지 |
| `review_text` | string | Y | 분석 원천, Event 전송 금지 |
| `submission_time` | date | Y | 작성일 |
| `helpfulness` | double | Y | 도움됨 비율 |
| `total_feedback_count` | int | Y | 전체 피드백 수 |
| `total_pos_feedback_count` | int | Y | 긍정 피드백 수 |
| `total_neg_feedback_count` | int | Y | 부정 피드백 수 |
| `skin_type` | string | Y | 리뷰 시점 속성 |
| `skin_tone` | string | Y | 정규화 값 |
| `skin_tone_raw` | string | Y | 원본 값 |
| `eye_color` | string | Y | 리뷰 시점 속성 |
| `hair_color` | string | Y | 리뷰 시점 속성 |
| `product_rank` | int | Y | 상위 200개 내 순위 |
| `evaluation_role` | string | N | `seed`, `holdout_target`, `excluded` |
| `is_simulation_context` | boolean | N | 행동 생성 참고 가능 여부 |

## 7. Seed와 Holdout

### 7.1 판정 순서

Holdout target은 **가장 마지막 긍정 리뷰**다. 추천은 선호 상품을 맞히는 과제이므로
정답은 긍정 상호작용이어야 한다. 불만 리뷰는 정답이 아니라 §4의
`latest_review_label`로 Persona 속성에 남긴다.

1. `canonical_product_id`가 Product Feature에 존재하는 리뷰만 남기고,
   `submission_time DESC NULLS LAST → review_id DESC`로 정렬한다. Join에 실패한
   리뷰는 `excluded`이며 이후 단계에서 제외한다.
2. 정렬 순서대로 §7.1.1의 긍정 조건을 만족하는 첫 리뷰를 target으로 고른다.
   이때 `holdout_target`, `target_label='positive'`, `is_holdout_eligible=true`다.
3. 긍정 리뷰가 하나도 없으면 target이 없다. 이 Persona는 `persona_holdout_target`에
   넣지 않고 `is_holdout_eligible` 대상에서 제외한다.
4. target보다 나중에 작성된 리뷰는 `excluded`다. 시간 절단을 위반하므로 seed로 쓰지
   않는다.
5. target보다 먼저 작성된 리뷰 중 target과 `canonical_product_id`가 **다른** 리뷰가
   `seed`다.
6. target과 같은 상품의 이전 리뷰는 `excluded`이며 `persona_seed_product`에 넣지
   않는다.

6번에서 같은 상품을 제외하는 이유는 seed 상품이 `is_seen=true`로 추천 후보에서 하드
제외되기 때문이다. 같은 상품에 리뷰를 두 번 이상 쓴 Persona가 있으므로, 상품 단위로
제외하지 않으면 target 상품이 후보에서 빠져 정답을 맞힐 수 없는 평가가 된다.

#### 7.1.1 긍정 조건

```text
rating >= 4  또는  (is_recommended = true 그리고 rating >= 3)
```

`is_recommended`는 명시적인 추천 의사이므로 `rating = 3`과 함께 있으면 긍정으로
본다. `rating <= 2`와 함께 있는 경우는 서로 모순되는 입력이므로 긍정으로 보지 않는다.

#### 7.1.2 정렬 tie-break

`submission_time`은 날짜 단위라 같은 날 작성된 리뷰의 선후를 가릴 수 없다.
`review_id DESC`를 tie-break으로 사용해 실행마다 결과가 달라지지 않게 한다.

### 7.2 `persona_seed_product`

```text
grain = persona_id + canonical_product_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `canonical_product_id` | string | N | Seed 상품 ID |
| `product_id` | string | N | canonical ID와 동일 |
| `source_review_ids` | array<string> | N | 원천 리뷰 ID |
| `last_reviewed_at` | date | Y | 최근 seed 리뷰일 |
| `avg_seed_rating` | double | Y | seed 상품 평균 평점 |
| `is_positive_seed` | boolean | Y | 긍정 seed 여부 |
| `initial_event_weight` | double | Y | 항상 NULL. 아래 참조 |
| `is_seen` | boolean | N | 추천 후보 하드 제외 여부 |

`initial_event_weight`는 **의도적으로 비운다.** Seed 상품은 스칼라 가중치로 주입되지
않는다. 생성기가 Seed를 실제 Event로 펼치고, 그 뒤로는 일반 Event와 같은 행동
가중치 표로 누적된다. 따라서 이 컬럼에 채울 값이 없는 것이 정상이며 산식이 정해지지
않아 비어 있는 것이 아니다. 누적 규칙은 §12.1이 참조하는
[`recommendation-io-spec.md`](./recommendation-io-spec.md) §2를 따른다.

컬럼 자체는 Seed에 스칼라 초기값을 주는 방식으로 바뀔 경우를 위해 남겨 둔다.

### 7.3 `persona_holdout_target`

```text
grain = persona_id + target_canonical_product_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `target_canonical_product_id` | string | N | 정답 상품 ID |
| `target_product_id` | string | N | canonical ID와 동일 |
| `target_source_product_id` | string | Y | 원천 상품 ID |
| `target_review_id` | string | N | 정답 리뷰 ID |
| `target_rating` | int | Y | 정답 평점 |
| `target_is_recommended` | boolean | Y | 정답 추천 여부 |
| `target_submission_time` | date | Y | 정답 작성일 |
| `target_label` | string | N | `positive` |
| `is_holdout_eligible` | boolean | N | Positive 평가 대상 여부 |

§7.1이 긍정 리뷰만 target으로 고르므로 이 테이블의 `target_label`은 항상 `positive`,
`is_holdout_eligible`은 항상 `true`다. 두 컬럼은 소비처가 규칙을 몰라도 평가 대상을
필터할 수 있도록 유지하며, §11이 이 불변식을 검사한다. 긍정 리뷰가 없어 target을
만들 수 없는 Persona는 행 자체가 없다.

### 7.4 `persona_evaluation_split`

```text
grain = persona_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `evaluation_split` | string | N | `train`, `valid`, `test` |
| `split_rule` | string | N | 결정론적 hash 규칙 |
| `split_version` | string | N | 예: `split-v1` |

기본 분할은 60/20/20이며 Agent 100명 정성 검증은 별도로 관리한다.

## 8. Segment와 Affinity 입력

### 8.1 `bridge_persona_segment`

```text
grain = persona_id + segment_type + segment_value
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `segment_type` | string | N | `skin_type`, `skin_tone`, `hair_color`, `eye_color`, `review_bucket`, `persona_source`, `evaluation_cohort` |
| `segment_value` | string | N | Segment 값 |
| `valid_from` | date | Y | 적용 시작일 |
| `valid_to` | date | Y | 적용 종료일 |
| `updated_at` | timestamp | Y | 갱신 시각 |

`generator_type`과 `concern`은 Persona segment가 아니다.

### 8.2 `persona_attribute_affinity_input`

```text
grain = persona_id
input = persona_profile
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `skin_type` | string | N | Affinity key |
| `skin_tone` | string | N | Affinity key |
| `hair_color` | string | Y | Affinity key |
| `eye_color` | string | Y | Affinity key |
| `skin_type_weight` | double | N | 일반 0.40, combination 0.00 |
| `skin_tone_weight` | double | N | 일반 0.40, combination 0.80 |
| `hair_color_weight` | double | N | 0.10 |
| `eye_color_weight` | double | N | 0.10 |

NULL attribute의 weight는 0으로 두고 나머지를 합 1.0으로 재정규화한다. Missing segment
fallback 값은 `recommendation-io-spec.md`를 따르며 현재 계약값은 0.5다.
`affinity_missing=true`를 함께 남긴다.

## 9. Event 매핑

| Persona·Run 값 | Event 위치 |
| --- | --- |
| `persona_id` | top-level `persona_id` |
| `actor_type` | top-level `actor_type='synthetic'` |
| `scenario_id` | `properties.scenario_id` |
| `simulation_run_id` | `properties.simulation_run_id` |
| `generator_type` | `properties.generator_type` |
| `canonical_product_id` | top-level `product_id` |
| `persona_source` | Event에 미포함, Dimension Join |
| `evaluation_cohort` | Event에 미포함, Persona Dimension Join |

Seed Event의 `session_id`는 `seed:{simulation_run_id}:{persona_id}:{product_id}` 형식을
사용하고 `properties.seeded=true`를 함께 기록한다.

## 10. Scenario와 Simulation Run

### 10.1 `simulation_run`

```text
grain = simulation_run_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `simulation_run_id` | string | N | Unique key, `run_<UTC timestamp>` 형식 |
| `scenario_id` | string | N | Scenario ID |
| `scenario_name` | string | Y | 표시명 |
| `generator_type` | string | N | `python_batch`, `agent_llm` |
| `persona_source` | string | N | `batch_sample`, `agent_sample`, `holdout_sample` |
| `target_persona_count` | int | N | 실행 대상 수 |
| `seed` | int | Y | 난수 seed |
| `started_at` | timestamp | Y | 시작 시각 |
| `ended_at` | timestamp | Y | 종료 시각 |
| `event_count` | bigint | Y | 생성 Event 수 |
| `persona_profile_version` | string | Y | Profile 버전 |
| `product_feature_version` | string | Y | Product Feature 버전 |
| `affinity_version` | string | Y | Affinity 버전 |
| `recommendation_policy` | string | Y | 추천 정책 버전 |
| `event_schema_version` | string | Y | Event Schema 버전 |
| `split_version` | string | Y | 평가 split 버전 |
| `note` | string | Y | 실행 메모 |

한 run에는 하나의 `persona_source`와 `generator_type`만 사용한다.

### 10.2 `scenario`

```text
grain = scenario_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `scenario_id` | string | N | 예: `normal_day`, `sale_burst` |
| `scenario_name` | string | Y | 표시명 |
| `description` | string | Y | 설명 |
| `traffic_pattern` | string | Y | 평시·급증·감쇠 |
| `recommendation_policy` | string | Y | 추천 정책 |
| `created_at` | timestamp | Y | 생성 시각 |

## 11. 검증 조건

1. PA·PC·Holdout A/B 전체에서 계약/Dimension `persona_id`가 유일하다. Holdout A/B의
   ID 교집합은 0건이어야 한다.
2. `skin_type`, `skin_tone`, `stratum`, `review_bucket`이 존재한다.
3. 사용자 속성이 §3 enum에 속한다.
4. Persona 모집단은 `n_reviews >= 3`, `n_products >= 3`, `n_positive >= 3`이다.
5. `review_bucket`은 `n_positive=3 → 3`, `4 → 4`, `5~6 → 5-6`, `7 이상 → 7+`다.
6. `canonical_product_id`가 Product Feature에 존재한다.
7. Holdout과 eval Profile에서 target 리뷰와 target 상품이 seed 입력에 포함되지 않는다.
8. `bridge_persona_segment.segment_type`은 허용 7종만 사용한다. 집단 판정은 ID 대역이
   아니라 `evaluation_cohort`를 사용한다.
9. 한 Simulation Run 안에서 `persona_source`, `generator_type`, `scenario_id`가 일관된다.
10. PA와 PC Event가 각각 `agent_llm`, `python_batch`를 사용한다.
11. `persona_holdout_target`의 `target_label`이 모두 `positive`이고
    `is_holdout_eligible`이 모두 `true`다.
12. seed 리뷰의 `submission_time`이 target보다 나중이 아니다. target 이후 리뷰는
    `evaluation_role='excluded'`다.
13. `latest_review_label`이 §7.1 정렬 기준 첫 리뷰의 극성과 일치한다.
14. `holdout_sample`에는 `evaluation_cohort`가 반드시 존재하고, 다른 표본에서는 NULL이다.
15. CF 동시발생 생성 시 모든 `personas_*.json`의 `author_id`를 제외한다. 새 Holdout
    파일을 추가하면 해당 author_id가 제외 집합에 포함되는지 회귀 테스트한다.

## 12. 추천 행동 상태 연결

이 절은 기존 추천 계약의 참조 호환성을 유지하기 위한 연결 규칙이다. 실행 산식은
`recommendation-io-spec.md`를 단일 출처로 사용한다.

### 12.1 증분 갱신

Persona별 positive·negative 행동 합과 weight 합, Product Vector 결합 및 감점 적용
순서는 [`recommendation-io-spec.md`](./recommendation-io-spec.md) §2를 따른다. Persona
계약에는 벡터 산식을 복제하지 않는다.

### 12.2 Negative 입력 구분

별점 1~2점 리뷰에서 파생된 negative와 조회 후 미전환 행동에서 파생된 negative는
발생 근거를 구분해 기록한다. 두 입력의 결합 방식은 추천 계약을 따른다.

### 12.3 `converted`, `viewed`, `n_products`

행동 Event별 전환 판정, 접촉 상품 집합, 상품 수 갱신 기준은
[`recommendation-io-spec.md`](./recommendation-io-spec.md) §2를 따른다. Seed 리뷰 상품의
후보 제외와 실제 행동 접촉을 동일한 `viewed` 의미로 합치지 않는다.
