# Persona Schema

작성일: 2026-08-28  
상태: Draft, E2E 테스트 전 Persona 데이터 구조 초안. 리뷰 반영 2차  
관련 문서: `persona-attribute-preprocessing.md`, `event-taxonomy-trigger-schema.md`, `processed-schema.md`, `dw-schema.md`, `contracts/recommendation-io-spec.md`, `contracts/product-feature-spec.md`, `docs/ai/recommendation-design.md`

## 1. 문서 목적

이 문서는 simulator의 Persona 원천 데이터를 Event 생성, User Behavior Feature, Attribute Affinity, DW Segment 분석에 연결하기 위한 Schema 기준을 정의한다.

Persona Schema는 다음 세 가지를 동시에 만족해야 한다.

| 목적 | 설명 |
| --- | --- |
| Event 생성 | synthetic Event에 `persona_id`, `actor_type`, `scenario_id`, `simulation_run_id`, `generator_type`을 안정적으로 부여 |
| 추천/CBF 연결 | Persona의 속성과 행동 이력을 Product Feature, Attribute Affinity, User Behavior Vector에 연결 |
| Dashboard 분석 | 피부 타입/톤/고민 등 segment 기준으로 Funnel, 상품 반응, 관심도 지표를 집계 |

## 2. 원천 데이터와 참고 기준

| 구분 | 위치 | 내용 |
| --- | --- | --- |
| Agent Persona | `simulator/personas/data/personas_100_agent.json` | 에이전트 구동용 100명. 정성/실시간성 검증 중심 |
| Batch Persona | `simulator/personas/data/personas_9900.json` | Python 코드 생성용 9,900명. 대규모 부하/분포 검증 중심 |
| Persona README | `simulator/personas/data/README.md` | 추출 기준, 층화추출, 정규화 규칙 |
| 속성 전처리 기준 | `docs/analytics/persona-attribute-preprocessing.md` | 사용자 속성 4종의 정규화·결측 처리·허용값 원천 |
| Product Data | `batch/ingest/data/products_200.json` | 상위 200개 상품, 병합 대표 `product_id`, 리뷰 통계 |
| Attribute Affinity | `batch/ingest/data/affinity_lift.csv` | 상품 x 사용자 속성 세그먼트별 affinity/lift |
| Product Feature Spec | `contracts/product-feature-spec.md` | Product Vector 93차원, 어휘집/블록/가중치 |
| Recommendation I/O | `contracts/recommendation-io-spec.md` | Product Vector, User Behavior Vector, Attribute Affinity, Redis 구조 |

현재 Persona JSON은 아래 공통 구조를 가진다.

```text
persona
├─ persona_id
├─ author_id
├─ skin_type
├─ skin_tone
├─ eye_color
├─ hair_color
├─ stratum
├─ review_bucket
├─ n_reviews
├─ n_products
├─ avg_rating
└─ reviews[]
```

## 3. 전체 연결 흐름

```text
persona raw files
→ persona_profile (full)
→ persona_review_history
   ├─ seed        → persona_seed_product → 추천 초기 상태 / seen
   └─ holdout     → persona_holdout_target → 오프라인 추천 평가
→ synthetic Event 생성 (persona_id × simulation_run_id)
→ processed_schema.persona_behavior_feature_delta
→ User Behavior Vector / DW segment mart
```

오프라인 추천 평가는 위 흐름과 입력 범위가 다르다. 정답으로 숨긴 holdout 정보가 추천 입력에 섞이지 않도록 별도 경로를 사용한다.

```text
persona_review_history where evaluation_role='seed'
→ persona_profile_eval (profile_scope='eval')
→ 추천 계산 입력
→ persona_holdout_target과 비교해 성능 평가
```

Product Feature, Event, Processed, DW와의 연결은 `canonical_product_id`로 한다. `products_200.json`의 `product_id`는 사이즈 변형이 병합된 대표 ID이므로 이를 canonical 기준으로 사용한다. 리뷰 원천의 상품 ID는 `source_product_id`로 보존하고, `group_id`가 있으면 `canonical_product_id=group_id`, 없으면 `canonical_product_id=source_product_id`로 정규화한다. Event의 top-level `product_id`에는 이 `canonical_product_id`를 넣는다.

## 4. ID 규칙과 Runtime Context 규칙

Persona 자체를 식별하는 값과, Persona가 "어떤 실행에서 어떻게 행동했는지"를 나타내는 값은 서로 다른 축이다. 두 축을 하나의 표로 묶으면 `scenario_id`가 Persona 고유 속성처럼 읽히므로 아래처럼 분리한다.

### 4.1 Persona Identity (고정/준고정)

Persona 1명에 귀속되며 실행이 바뀌어도 값이 바뀌지 않는다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | Y | Persona 고유 ID. Event의 `persona_id`, 추천 API key, DW Join key |
| `author_id` | string/null | Y | 원천 리뷰어 ID. 내부 추적 전용이며 API/Event/Dashboard 외부 노출 금지 |
| `user_id` | string/null | Y | 분석용 사용자 ID. synthetic에서는 기본적으로 `persona_id`와 동일 |
| `persona_source` | string | Y | `agent_sample`, `batch_sample` 등 Persona 원천 표본 구분 |
| `profile_version` | string | Y | Persona 생성/정규화 버전 |

### 4.2 Simulation Runtime Context (실행 속성)

Persona가 아니라 "이번 실행"에 귀속된다. 같은 Persona가 다른 run에서는 다른 값을 가진다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `actor_type` | string | Y | Persona 기반 Event는 `synthetic` |
| `scenario_id` | string | Y | 시나리오 ID. 트래픽/프로모션/상황 조건 |
| `simulation_run_id` | string | Y | 시뮬레이션 실행 1회 단위 ID. 같은 시나리오 반복 실행 분리 |
| `generator_type` | string | Y | 생성 방식. `python_batch`, `agent_realtime` |

즉 `scenario_id`는 `persona_id`의 속성이 아니라 `persona_id × simulation_run_id`의 속성이다.

```text
PA00001 이(가)
run_20260828_001 에서
normal_day 시나리오로
python_batch 방식으로 행동했다
```

`source`는 Event/Processed/DW에서 `actor_type='synthetic' → simulator`로 파생한다. `persona_source`는 Event에 반복 저장하지 않고 `persona_id → persona_profile` 또는 `simulation_run_id → dim_simulation_run` Join으로 확인한다(§14.3). `generator_type`은 Persona 고유 속성이 아니라 `simulation_run`과 Event 생성 실행 방식으로 관리한다.

상품 ID는 아래처럼 구분한다.

| 필드 | 위치 | 설명 |
| --- | --- | --- |
| `source_product_id` | `persona_review_history` | 원천 리뷰 파일의 상품 ID |
| `group_id` | `persona_review_history` | 병합 대표 ID 후보 |
| `canonical_product_id` | seed/holdout/recommendation/Event/DW | 추천과 분석의 기준 상품 ID. `group_id`가 있으면 `group_id`, 없으면 `source_product_id` |
| `product_id` | Event top-level, Product Feature, DW | 외부 계약에서는 `canonical_product_id`를 `product_id`로 사용 |

## 5. `persona_profile`

Persona 1명당 1 row의 기본 Profile 테이블이다. 원천 리뷰 전체를 사용하는 **full profile**이며, 시뮬레이션 구동과 Dashboard segment 통계의 기준이다. 오프라인 추천 평가에는 이 테이블 대신 §5.2의 평가용 Profile을 사용한다.

```text
grain = persona_id
source = simulator/personas/data/personas_100_agent.json,
         simulator/personas/data/personas_9900.json
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `author_id` | string/null | Y | 원천 리뷰어 ID. 내부 추적용 |
| `user_id` | string | N | synthetic 분석용 사용자 ID. 기본값 `persona_id` |
| `persona_source` | string | N | `agent_sample` 또는 `batch_sample` |
| `skin_type` | string | N | `combination`, `dry`, `normal`, `oily` |
| `skin_tone` | string | N | `fair`, `light`, `medium`, `tan`, `deep` |
| `eye_color` | string | Y | `brown`, `blue`, `green`, `hazel`, `gray` |
| `hair_color` | string | Y | `brown`, `black`, `blonde`, `gray`, `red`, 기타 정규화 값 |
| `stratum` | string | N | 층화추출 key. 예: `combination\|light\|4-5` |
| `review_bucket` | string | N | `3`, `4-5`, `6-9`, `10+` |
| `n_reviews` | int | N | Persona 원천 리뷰 수 |
| `n_products` | int | N | Persona가 리뷰한 고유 상품 수 |
| `avg_rating` | double/null | Y | Persona 평균 평점 |
| `profile_version` | string | N | Persona 생성/정규화 버전. E2E 초안값 `0.1-draft` |
| `profile_scope` | string | N | `full`. 원천 리뷰 전체 기준 Profile임을 표시. 평가용은 §5.2의 `eval` |
| `created_at` | timestamp | N | 생성 또는 적재 시각. 원천에 없으면 적재 시각으로 채움 |
| `updated_at` | timestamp | N | 갱신 시각. 최초 적재 시에는 `created_at`과 동일 |

### 5.1 정규화 규칙

아래는 요약이며, 원본 값 매핑·결측 처리·허용값 전체는 `persona-attribute-preprocessing.md`를 원천으로 한다.

| 항목 | 규칙 |
| --- | --- |
| `skin_type` | 원본 4종 유지: `combination`, `dry`, `normal`, `oily` |
| `skin_tone` | 원본 14종을 5버킷으로 정규화. `notSureST`는 결측 처리 |
| `hair_color` | `brunette`는 `brown`으로 병합. 결과 6종(`auburn` 포함) |
| `eye_color` | `Grey`는 `gray`로 병합. 결과 5종 |
| 모집단 조건 | 사용자 속성 4개가 모두 채워진 리뷰만 사용 |
| 대표 속성 | 리뷰마다 속성이 다르면 최신 리뷰 기준 |
| 100명 agent | `skin_type x skin_tone` 20셀 균등배분. Dashboard 기본 모집단 통계에서는 제외하고 실시간/정성 실험용으로 분리 |
| 9,900명 batch | 모집단 분포에 맞춘 층화추출. 대규모 Dashboard 통계 기본 집단 |

100명 agent sample과 9,900명 batch sample을 합산해야 하는 분석은 별도 `analysis_weight` 또는 `sampling_weight`가 정의된 뒤에만 수행한다. MVP Dashboard 기본값은 `persona_source='batch_sample'` 기준으로 둔다. Dashboard가 이 필터를 걸 수 있는 Join 경로는 §14.3에 정의한다.

### 5.2 `persona_profile_eval` — 평가용 Profile

`persona_profile`의 대표 속성은 "가장 최신 리뷰" 기준이고, holdout target도 "가장 마지막 리뷰"다. 두 규칙을 그대로 겹치면 **정답으로 숨긴 리뷰의 정보가 추천 입력에 들어간다.** `skin_type`, `skin_tone` 같은 시점 속성뿐 아니라 `n_reviews`, `n_products`, `avg_rating`도 holdout 리뷰를 포함해 계산되면 간접 누수가 된다.

따라서 오프라인 추천 평가에서는 holdout 대상 리뷰를 제외한 seed 이력만으로 Profile을 다시 만든다.

```text
grain = persona_id
source = persona_review_history where evaluation_role='seed'
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `profile_scope` | string | N | 고정값 `eval` |
| `skin_type` | string | N | **최신 seed 리뷰** 기준 대표 속성 |
| `skin_tone` | string | N | 최신 seed 리뷰 기준 |
| `eye_color` | string | Y | 최신 seed 리뷰 기준 |
| `hair_color` | string | Y | 최신 seed 리뷰 기준 |
| `n_reviews_seed` | int | N | seed 리뷰 수. `n_reviews`에서 holdout 건수를 뺀 값 |
| `n_products_seed` | int | N | seed 기준 고유 상품 수 |
| `avg_rating_seed` | double/null | Y | seed 리뷰 평균 평점 |
| `profile_version` | string | N | `persona_profile`과 동일 버전 사용 |
| `split_version` | string | N | 함께 사용한 `persona_evaluation_split` 버전 |

규칙:

| 항목 | 규칙 |
| --- | --- |
| 사용처 | 오프라인 추천 성능 평가(Recall/NDCG 등)와 가중치 튜닝에만 사용 |
| 미사용처 | 시뮬레이션 행동 생성, Dashboard segment 통계, 실시간 추천에는 `persona_profile`(full)을 사용 |
| seed가 0건 | 평가 대상에서 제외한다. Persona는 최소 3개 리뷰로 추출되므로 정상 케이스에서는 발생하지 않는다 |
| 대표 속성 누락 | 최신 seed 리뷰에 값이 없으면 그 이전 seed 리뷰로 내려가며 채우고, 전부 없으면 NULL로 두고 §11 fallback을 적용 |

시뮬레이션 실행용 Persona와 평가용 Persona가 달라지는 것이 아니라, **같은 Persona의 입력 범위만 다르다.** 두 Profile은 `profile_scope`로 구분한다.

## 6. `persona_review_history`

Persona의 실제 리뷰 이력을 보존하는 테이블이다. 시뮬레이션 seed, holdout 검증, 추천 초기 상태 생성에 사용한다.

```text
grain = persona_id + review_id
source = persona.reviews[]
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `review_id` | string | N | 리뷰 ID |
| `author_id` | string/null | Y | 원천 리뷰어 ID |
| `source_product_id` | string | N | 원천 리뷰의 상품 ID |
| `group_id` | string/null | Y | 병합 대표 상품 ID 후보 |
| `canonical_product_id` | string | N | 추천/분석 기준 상품 ID. `group_id`가 있으면 `group_id`, 없으면 `source_product_id` |
| `product_name` | string/null | Y | 원천 표시용 상품명 |
| `brand_name` | string/null | Y | 원천 표시용 브랜드명 |
| `rating` | int/null | Y | 1~5 평점 |
| `is_recommended` | boolean/null | Y | 추천 여부 |
| `review_title` | string/null | Y | 원천 리뷰 제목. 분석 원천으로만 사용 |
| `review_text` | string/null | Y | 원천 리뷰 본문. Event payload로 보내지 않음 |
| `submission_time` | date/null | Y | 리뷰 작성일 |
| `helpfulness` | double/null | Y | 도움됨 비율 |
| `total_feedback_count` | int/null | Y | 전체 피드백 수 |
| `total_pos_feedback_count` | int/null | Y | 긍정 피드백 수 |
| `total_neg_feedback_count` | int/null | Y | 부정 피드백 수 |
| `skin_type` | string/null | Y | 리뷰 시점 속성 |
| `skin_tone` | string/null | Y | 정규화된 피부 톤 |
| `skin_tone_raw` | string/null | Y | 원본 피부 톤 |
| `eye_color` | string/null | Y | 리뷰 시점 눈 색상 |
| `hair_color` | string/null | Y | 리뷰 시점 머리 색상 |
| `product_rank` | int/null | Y | 상위 200개 내 rank |
| `evaluation_role` | string | N | `seed`, `holdout_target`, `excluded` 중 하나 |
| `is_simulation_context` | boolean | N | 시뮬레이션 행동 생성 참고에 사용할 수 있는 리뷰 여부 |

### 6.1 Seed / Holdout 규칙

오프라인 추천 검증에서는 시간순 leave-last-out을 사용한다. "마지막 리뷰는 holdout"과 "조건 미충족이면 excluded"가 동시에 성립하지 않도록 **판정 순서를 아래로 고정한다.** 구현자가 순서를 다르게 해석하면 평가 대상 Persona 수 자체가 달라지므로 이 순서가 계약이다.

| 단계 | 처리 | 결과 |
| --- | --- | --- |
| 1 | `submission_time DESC NULLS LAST → review_id DESC`로 정렬해 첫 번째 리뷰를 **holdout 후보**로 선정 | 후보 1건 확정 |
| 2 | 후보의 `canonical_product_id`가 Product Feature/Product Data에 존재하는지 확인 | 실패 시 4단계로 |
| 3 | 후보가 `rating >= 4` 또는 `is_recommended=true`를 만족하는지 확인 | 실패 시 4단계로 |
| 4 | 2·3을 모두 통과 → `evaluation_role='holdout_target'`, `target_label='positive'`, `is_holdout_eligible=true` | positive 평가 대상 |
| 5 | 3만 실패(상품 Join은 성공) → `evaluation_role='holdout_target'`, `target_label='negative'` 또는 `diagnostic`, `is_holdout_eligible=false` | 진단용으로 보존, positive 평가 제외 |
| 6 | 2 실패(상품 Join 불가) → `evaluation_role='excluded'` | 평가에서 제외. 해당 Persona는 positive 평가 모집단에서 빠짐 |
| 7 | 후보를 제외한 이전 리뷰 전부 → `evaluation_role='seed'` | seed 이력 |

정렬 기준은 재현 가능해야 하므로 `submission_time`이 같으면 `review_id DESC`로 결정한다.

보조 규칙:

| 항목 | 규칙 |
| --- | --- |
| seed의 상품 Join 실패 | seed 리뷰의 `canonical_product_id`가 Product Feature에 없으면 그 리뷰는 seed 벡터 생성에서 제외하되 `evaluation_role='seed'`는 유지하고 품질 flag로 남긴다 |
| holdout 제외 Persona | 6단계로 빠진 Persona는 `persona_profile_eval`을 만들되 평가 모집단에서 제외한다. 제외 수는 평가 리포트에 함께 기록한다 |
| 순환 검증 금지 | 생성 로그로 추천 가중치를 다시 평가하면 생성 규칙을 되찾는 순환 검증이 되므로, 추천 성능 검증은 실제 리뷰 holdout을 기준으로 한다 |
| threshold 조정 | `rating >= 4` 또는 `is_recommended=true`는 초안이며 AI/Product Feature 담당과 합의 후 조정 가능하다. 조정 시 `split_version`과 함께 평가 리포트에 기록한다 |

## 7. `persona_seed_product`

추천 초기 상태와 synthetic 행동 시작점을 만들기 위한 Persona x Product seed 테이블이다.

```text
grain = persona_id + canonical_product_id
source = persona_review_history where evaluation_role='seed'
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `canonical_product_id` | string | N | 추천/행동 기준 상품 ID |
| `product_id` | string | N | Event/Product Feature/DW에서 사용할 상품 ID. `canonical_product_id`와 동일 |
| `source_review_ids` | array<string> | N | 이 seed를 만든 리뷰 ID 목록 |
| `last_reviewed_at` | date/null | Y | 가장 최근 seed 리뷰일 |
| `avg_seed_rating` | double/null | Y | 해당 상품 seed 리뷰 평균 |
| `is_positive_seed` | boolean/null | Y | 평점/추천 여부 기준 긍정 seed |
| `initial_event_weight` | double/null | Y | 초기 User Behavior Vector 반영 시 사용할 가중치 |
| `is_seen` | boolean | N | 추천 후보 제외용 seen 상품 여부 |

초기 E2E에서는 `is_seen=true`인 상품을 Redis `seen` 또는 equivalent structure에 반영할 수 있다. 다만 시뮬레이션의 목표가 "처음 방문한 사용자 행동 생성"이면 seed를 추천 제외에만 쓰고, 실제 클릭/조회 Event는 새로 발생시킨다. seed를 `n_products`에도 반영할지는 §12.3의 기준을 따른다.

오프라인 평가에서 seed 상품은 `persona_profile_eval`과 같은 입력 범위를 사용한다. 즉 holdout 대상 리뷰에서 파생된 상품은 seed에 포함되지 않는다.

## 8. `persona_holdout_target`

추천 오프라인 검증용 정답 상품이다. 실시간 Event/Dashboard KPI에는 직접 섞지 않는다.

```text
grain = persona_id + target_canonical_product_id
source = persona_review_history where evaluation_role='holdout_target'
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `target_canonical_product_id` | string | N | 추천 평가 기준 정답 상품 ID |
| `target_product_id` | string | N | Event/Product Feature/DW에서 사용할 상품 ID. `target_canonical_product_id`와 동일 |
| `target_source_product_id` | string/null | Y | 원천 리뷰의 상품 ID |
| `target_review_id` | string | N | 정답 리뷰 ID |
| `target_rating` | int/null | Y | 정답 리뷰 평점 |
| `target_is_recommended` | boolean/null | Y | 정답 추천 여부 |
| `target_submission_time` | date/null | Y | 정답 리뷰 작성일 |
| `target_label` | string | N | `positive`, `negative`, `diagnostic` |
| `is_holdout_eligible` | boolean | N | positive 추천 평가에 사용할 수 있는지 여부 |

`target_label`과 `is_holdout_eligible`은 §6.1의 판정 순서 결과를 그대로 옮긴 값이다. 4단계 통과는 `positive/true`, 5단계는 `negative` 또는 `diagnostic`/`false`이며, 6단계(`excluded`)는 이 테이블에 row를 만들지 않는다.

`evaluation_split`은 이 테이블에 중복 저장하지 않고 `persona_evaluation_split`을 `persona_id`로 Join해 사용한다. 동일한 split 값이 두 테이블에 중복 저장되면 불일치 위험이 생기기 때문이다.

## 9. `persona_evaluation_split`

가중치 선택과 최종 보고를 분리하기 위한 오프라인 평가 split이다. 별도 파일 없이 `persona_id` 해시로 재현한다.

```text
grain = persona_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `evaluation_split` | string | N | `train`, `valid`, `test` |
| `split_rule` | string | N | 예: `md5("split-v1\|" + persona_id) % 10` |
| `split_version` | string | N | 예: `split-v1` |

초안 기준 분할은 `train=60%`, `valid=20%`, `test=20%`다. Agent 100명은 정성 검증용이므로 이 split과 별개로 관리한다.

## 10. `bridge_persona_segment`

DW에서 Persona를 segment별로 분석하기 위한 연결 테이블이다. `dw-schema.md`의 `bridge_persona_segment`와 같은 구조를 따른다.

```text
grain = persona_id + segment_type + segment_value
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `segment_type` | string | N | `skin_type`, `skin_tone`, `hair_color`, `eye_color`, `review_bucket`, `persona_source` |
| `segment_value` | string | N | segment 값 |
| `valid_from` | date/null | Y | 적용 시작일 |
| `valid_to` | date/null | Y | 적용 종료일 |
| `updated_at` | timestamp/null | Y | 갱신 시각 |

예시:

```text
PA00001 | skin_type      | combination
PA00001 | skin_tone      | light
PA00001 | review_bucket  | 4-5
PA00001 | persona_source | agent_sample
```

`generator_type`은 Persona segment가 아니라 시뮬레이션 실행 방식이므로 `bridge_persona_segment`에 넣지 않는다. 실행 방식별 분석은 Processed/DW의 `generator_type` 또는 `simulation_run`을 기준으로 수행한다.

`segment_type`의 허용 값은 위 6종이 전부이며 **`dw-schema.md`의 `dim_persona_segment`/`bridge_persona_segment`도 같은 목록을 사용한다.** 현재 Persona 원천(`personas_*.json`)에는 피부 고민 필드가 없으므로 `concern`은 segment_type에 포함하지 않는다. 상품 쪽 `dim_product.concern_tags`는 상품 속성이라 그대로 유지하며, 이는 Persona segment와 다른 축이다. Persona 생성기에 고민 속성이 추가되면 그때 원천·정규화 규칙과 함께 `concern`을 다시 넣는다.

## 11. `persona_attribute_affinity_input`

Attribute Affinity 조회에 필요한 Persona 속성만 정규화해 제공하는 논리 View다.

```text
grain = persona_id
input = persona_profile
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `persona_id` | string | N | Persona ID |
| `skin_type` | string | N | Attribute Affinity 조회 key |
| `skin_tone` | string | N | Attribute Affinity 조회 key |
| `hair_color` | string | Y | Attribute Affinity 조회 key |
| `eye_color` | string | Y | Attribute Affinity 조회 key |
| `skin_type_weight` | double | N | 일반 0.40, `combination`은 0.00 |
| `skin_tone_weight` | double | N | 일반 0.40, `combination`은 0.80 |
| `hair_color_weight` | double | N | 0.10 |
| `eye_color_weight` | double | N | 0.10 |

`combination` 사용자는 `skin_type` 항의 판별력이 낮으므로 해당 가중치를 0으로 두고 `skin_tone`으로 이관한다.

NULL 또는 missing affinity는 아래 규칙으로 처리한다.

| 상황 | 처리 |
| --- | --- |
| `hair_color` 또는 `eye_color`가 NULL | 해당 attribute weight를 0으로 두고 남은 attribute weight를 합 1.0이 되도록 재정규화 |
| `affinity_lift.csv`에 segment row가 없음 | `neutral_lift=1.0`을 affinity 변환식에 넣은 값을 사용하고 `affinity_missing=true` 품질 flag를 남김 |
| `skin_type='combination'` | `skin_type_weight=0.00`, `skin_tone_weight=0.80`으로 이관 후 NULL attribute가 있으면 다시 재정규화 |

### 11.1 Missing affinity의 neutral 값

neutral은 상수 `0.5`로 고정하지 않는다. `affinity_lift.csv`의 `affinity` 컬럼은 lift를 clip 구간으로 정규화한 값이므로, 중립값도 같은 변환식에서 나와야 한다.

```text
affinity = clip((lift - CLIP_LO) / (CLIP_HI - CLIP_LO), 0, 1)
neutral_affinity = clip((1.0 - CLIP_LO) / (CLIP_HI - CLIP_LO), 0, 1)
```

현재 채택된 구간은 `CLIP_LO=0.60`, `CLIP_HI=1.60`이므로 다음과 같다.

```text
neutral_affinity = (1.0 - 0.60) / (1.60 - 0.60) = 0.40
```

`lift=1.0`은 "평균과 동일"이라는 뜻이고, 실제 CSV에서도 `lift≈1.0` 행의 `affinity`가 `0.40` 근처로 나온다. 따라서 missing segment에 `0.5`를 넣으면 **평균보다 유리한 값**을 준 셈이 되어, 데이터가 없는 조합이 있는 조합보다 높은 점수를 받을 수 있다.

| 항목 | 기준 |
| --- | --- |
| neutral 계산 기준 | `neutral_lift=1.0`을 현재 clip 구간에 대입한 값 |
| 현재 값 | `0.40` (`CLIP_LO=0.60`, `CLIP_HI=1.60` 기준) |
| clip 구간 변경 시 | neutral 값도 함께 재계산한다. 문서에 상수만 적어두지 않는다 |
| 확인 필요 | `contracts/recommendation-io-spec.md`는 "셀이 없는 경우 기본값 0.5"로 적혀 있어 변환식과 불일치한다. AI/Product Feature 담당과 `0.40` 기준으로 통일할지 확정한다 |

이 fallback은 추천 계산이 중단되지 않도록 하는 MVP 기준이다. neutral 값과 재정규화 방식은 로그 축적 후 AI/Product Feature 담당이 조정할 수 있으며, 조정 시 `affinity_version`(§14.1)을 올린다.

## 12. User Behavior Vector 연결

User Behavior Vector 자체는 Persona Profile에 저장하지 않는다. Event가 발생할 때마다 `processed-schema.md`의 `persona_behavior_feature_delta`를 만들고, Product Vector와 결합해 Redis 또는 후속 저장소의 User Vector를 증분 갱신한다.

```text
persona_id
+ event.product_id(canonical_product_id)
+ event_weight
+ product_feature.vector
→ positive_u_sum, positive_w_sum, negative_u_sum, negative_w_sum, n_products, seen
```

| 저장 항목 | 위치 | 설명 |
| --- | --- | --- |
| `positive_u_sum` | Redis Hash 또는 equivalent store | 양수 행동 가중 Product Vector 누적합 |
| `positive_w_sum` | Redis Hash 또는 equivalent store | 양수 행동 누적 가중치. 기존 추천 문서의 `w_sum`에 해당 |
| `negative_u_sum` | Redis Hash 또는 equivalent store | 부정 행동 가중 Product Vector 누적합 |
| `negative_w_sum` | Redis Hash 또는 equivalent store | 부정 행동 절대값 가중치 합 |
| `n_products` | Redis Hash | 상호작용한 고유 상품 수 |
| `seen` | Redis Set 또는 equivalent set | 추천 제외 상품 |
| `updated_at` | Redis Hash | 마지막 갱신 시각 |

`n_products`는 Event 수가 아니라 고유 상품 수 기준이다. 스크롤/섹션 Event가 여러 번 발생해도 같은 상품 하나를 본 것은 고유 상품 1개로 계산한다.

User Behavior Vector의 분모는 양수 행동 가중치만 사용한다. `rage_click`, `dead_click`, `scroll_backtrack`, `remove_from_cart`처럼 부정/망설임 신호는 `positive_w_sum`에 넣지 않고 별도 부정 축에 누적한 뒤 최종 추천 점수에서 감점 신호로 사용한다. 이렇게 해야 음수 weight 때문에 분모가 0 또는 음수가 되는 문제를 막을 수 있다.

기존 `contracts/recommendation-io-spec.md`와 `docs/ai/recommendation-design.md`의 `u_sum`, `w_sum` 표현은 양수 행동 벡터 기준으로 해석한다. 실제 Redis 필드명을 그대로 유지할 경우에도 문서상 의미는 `positive_u_sum`, `positive_w_sum`과 동일하다.

### 12.1 증분 갱신 공식

`final_weight`는 `processed-schema.md`의 `persona_behavior_feature_delta.final_weight`(`event_weight × decay_weight`)다. 부호가 두 번 적용되는 실수를 막기 위해 **negative 축에는 절대값을 누적하고, 감점은 최종 점수 계산에서 한 번만 적용한다.**

```text
if final_weight > 0:
    positive_u_sum += final_weight * product_vector
    positive_w_sum += final_weight

if final_weight < 0:
    negative_u_sum += abs(final_weight) * product_vector
    negative_w_sum += abs(final_weight)

final_weight == 0 인 Event는 두 축 모두에 반영하지 않는다.
```

조회 시점:

```text
positive_vector = positive_u_sum / positive_w_sum      (positive_w_sum > 0)
negative_vector = negative_u_sum / negative_w_sum      (negative_w_sum > 0)
```

| 항목 | 기준 |
| --- | --- |
| 분모 | 항상 양수. `positive_w_sum`, `negative_w_sum` 모두 절대값 누적이므로 0 또는 음수가 되지 않는다 |
| 분모 0 | `positive_w_sum=0`이면 user vector를 만들지 않고 `n_products=0` 구간의 가중치 스케줄(속성/인기도 중심)을 사용한다 |
| 감점 적용 위치 | 벡터 누적 단계가 아니라 최종 추천 점수 단계에서 `- w_neg × cos(negative_vector, v_i)` 형태로 한 번만 적용한다 |
| 감점 계수 | `w_neg` 값과 감점 공식은 AI/Product Feature 담당 확정 대상이다 |
| `event_weight` 원천 | Front 구현 기준 단일 출처는 `frontend/src/types/log.ts`의 `EVENT_WEIGHT`, `SECTION_DWELL_WEIGHT`, `scrollDepthWeight()`다. Processed의 초안 표와 값이 다르면 log.ts를 기준으로 맞춘다 |

### 12.2 부정 Event 적용 범위

`persona_behavior_feature_delta`는 `product_id`가 필수다. 따라서 상품과 연결되지 않는 Event는 User Behavior Vector에 반영할 수 없다.

| Event 조건 | 처리 |
| --- | --- |
| `product_id`가 있는 부정 Event (`remove_from_cart`, 상품 카드/상세에서 발생한 `rage_click`, `dead_click`, `scroll_backtrack`) | negative 축에 반영 |
| `product_id`가 없는 friction Event (목록 조작 영역, 장바구니 화면 전체, 네비게이션 등) | Behavior Vector에 반영하지 않고 UX/Dashboard 지표(`realtime_event_stats`, friction 집계)로만 사용 |

이 규칙 때문에 Dashboard의 friction Event 수와 추천에 반영된 부정 신호 수는 일치하지 않는다. 이는 정상이며, 두 값을 같은 KPI로 비교하지 않는다.

### 12.3 `seen` / `n_products` 갱신 기준

`seen`은 추천 후보에서 상품을 빼는 값이므로, 어떤 Event부터 "봤다"로 볼지에 따라 추천 결과가 크게 달라진다. 기준은 아래 원칙으로 두되 **최종 canonical 정의는 `contracts/recommendation-io-spec.md`를 따른다.** Persona 문서는 산식을 중복 정의하지 않는다.

| 구분 | 초안 기준 | 근거 |
| --- | --- | --- |
| `seen`에 등록 | `final_weight > 0`인 상품 대상 Event가 1건이라도 발생한 상품 | 사용자가 능동적으로 접촉한 상품만 제외 대상 |
| `seen`에 등록하지 않음 | `product_impression`, `recommendation_impression` 등 `event_weight=0`인 노출 | 노출은 사용자 의지가 아니므로 제외하면 추천 후보가 과도하게 줄어든다 |
| `n_products` 증가 | `seen`에 상품이 새로 추가되는 시점에만 증가. 값은 `seen` 집합의 크기와 같다 | Event 수가 아니라 고유 상품 수 기준. 가중치 스케줄 판정 입력 |
| seed 상품 | §7의 `is_seen` 정책에 따른다 | seed를 seen 제외에만 쓰고 Behavior Vector 초기값에 넣지 않는 경우, `n_products`도 함께 올릴지 추천 담당과 합의한다 |

`seen`/`n_products` 기준이 바뀌면 추천 후보 집합이 바뀌므로, 변경 시 `recommendation_policy`(§14.1)를 함께 올려 run 간 비교가 가능하도록 한다.

## 13. Event 생성 시 Persona 필드 매핑

synthetic Event를 만들 때는 아래 기준으로 Event Schema에 매핑한다.

| Persona/Simulation 값 | Event 위치 | 설명 |
| --- | --- | --- |
| `persona_id` | top-level `persona_id` | synthetic 사용자 식별 |
| `user_id` | Processed 파생 | synthetic은 `persona_id → user_id` |
| `actor_type` | top-level `actor_type` | `synthetic` |
| `persona_source` | Event에 반복 저장하지 않음 | `persona_id → persona_profile` 또는 `simulation_run_id → dim_simulation_run` Join으로 확인 |
| `generator_type` | `properties.generator_type` | 필수. `agent_realtime`, `python_batch`. 실행 방식이므로 `simulation_run`에도 저장 |
| `scenario_id` | `properties.scenario_id` | 필수. 시나리오 ID |
| `simulation_run_id` | `properties.simulation_run_id` | 필수. 실행 단위 ID |
| `canonical_product_id` | top-level `product_id` | Event 대상 상품. Event 계약에서는 `product_id` 이름 사용 |
| `source` | Processed 파생 | `actor_type='synthetic' → simulator` |

`scenario_id`, `simulation_run_id`, `generator_type`은 현재 Backend top-level DTO가 아니라 `properties`에 담고 Processed 단계에서 승격한다. 이 3개는 `actor_type='synthetic'` Event의 **공통 필수 properties**이며, 같은 계약이 `event-taxonomy-trigger-schema.md` §8.4와 `event-contract-summary.md` §5.3에 들어 있다. 누락된 synthetic Event는 Spark semantic validation에서 `invalid_properties`로 격리한다.

`persona_source`는 Persona 정적 속성이므로 Event payload에 매번 싣지 않는다. 실제 Web Event(`actor_type='user'`)에는 이 runtime metadata를 요구하지 않으므로 프론트 구현에는 영향이 없다.

## 14. Scenario / Simulation Run Schema

시뮬레이션 실행 단위를 재현하고 Dashboard에서 비교하기 위한 메타데이터다. 시나리오(무엇을 돌렸는가)와 실행(언제 어떤 조건으로 돌렸는가)은 grain이 다르므로 테이블을 분리한다. `dw-schema.md`의 `dim_scenario`(§6.6), `dim_simulation_run`(§6.7)과 각각 연결된다.

### 14.1 `simulation_run`

```text
grain = simulation_run_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `simulation_run_id` | string | N | 실행 1회 식별자 |
| `scenario_id` | string | N | 시나리오 ID |
| `scenario_name` | string/null | Y | 표시명 |
| `generator_type` | string | N | `python_batch`, `agent_realtime` |
| `persona_source` | string | N | `batch_sample`, `agent_sample` |
| `target_persona_count` | int | N | 실행 대상 Persona 수 |
| `seed` | int/null | Y | 재현용 난수 seed |
| `started_at` | timestamp/null | Y | 실행 시작 |
| `ended_at` | timestamp/null | Y | 실행 종료 |
| `event_count` | bigint/null | Y | 생성 Event 수 |
| `persona_profile_version` | string/null | Y | 사용한 Persona `profile_version` |
| `product_feature_version` | string/null | Y | 사용한 Product Vector 버전. `contracts/product-feature-vocab.json`의 `vocab_version` 기준 |
| `affinity_version` | string/null | Y | 사용한 Attribute Affinity 생성 버전. clip 구간/neutral 기준이 바뀌면 올린다 |
| `recommendation_policy` | string/null | Y | 사용한 추천 정책/가중치 스케줄 버전. 예: `skin_match_v0` |
| `event_schema_version` | string/null | Y | 생성 Event의 `schema_version`. 예: `0.2.0-draft` |
| `split_version` | string/null | Y | 함께 사용한 `persona_evaluation_split` 버전 |
| `note` | string/null | Y | 실행 조건 메모 |

`seed`만으로는 과거 run을 재현할 수 없다. 같은 seed라도 Persona 표본, 상품 벡터 어휘집, affinity 기준, 추천 정책이 바뀌면 결과가 달라지기 때문이다. 위 version 컬럼들은 "왜 지난 run과 결과가 다른가"를 추적하기 위한 최소 집합이며, E2E에서는 값이 NULL이어도 파이프라인이 동작한다. 운영/실험 비교 단계에서는 필수로 채운다.

### 14.2 `scenario`

```text
grain = scenario_id
```

| column | type | nullable | 설명 |
| --- | --- | --- | --- |
| `scenario_id` | string | N | 예: `normal_day`, `sale_burst` |
| `scenario_name` | string/null | Y | 표시명 |
| `description` | string/null | Y | 시나리오 설명 |
| `traffic_pattern` | string/null | Y | 평시, 급증, 감쇠 등 |
| `recommendation_policy` | string/null | Y | 추천/기획전 정책. 예: `skin_match_v0` |
| `created_at` | timestamp/null | Y | 생성 시각 |

`scenario_id`는 트래픽/프로모션/상황 조건을 나타낸다. `skin_match_v0`처럼 추천 로직을 뜻하는 값은 `scenario_id`가 아니라 `recommendation_policy` 또는 Event의 `properties.algorithm`으로 기록한다.

### 14.3 DW 연결과 `persona_source` 필터 경로

`persona_source`는 Event payload에 싣지 않는다. 대신 실행 단위 Dimension을 통해 필터한다. `dw-schema.md`는 이 구조에 맞춰 `dim_scenario`(grain `scenario_id`)와 `dim_simulation_run`(grain `simulation_run_id`)을 분리해 둔다.

| Persona 문서 | DW 대응 | grain |
| --- | --- | --- |
| `scenario` | `dim_scenario` | `scenario_id` |
| `simulation_run` | `dim_simulation_run` | `simulation_run_id` |
| `persona_profile` | `bridge_persona_segment`, `dim_persona_segment` | `persona_id` 기준 segment 전개 |

Dashboard가 "agent 100명을 빼고 batch 9,900명만" 보려면 아래 경로를 사용한다.

```text
Mart(product_daily_kpi / funnel_daily_kpi / scenario_daily_kpi ...)
→ simulation_run_id
→ dim_simulation_run
→ persona_source = 'batch_sample'
```

| 항목 | 기준 |
| --- | --- |
| 기본 필터 | Dashboard 모집단 통계 기본값은 `persona_source='batch_sample'` |
| 혼합 run | 한 run에 두 표본을 섞지 않는다. run 단위로 `persona_source`가 하나여야 이 필터가 성립한다 |
| 혼합이 필요한 경우 | run을 나누어 실행하거나, `dim_simulation_run.persona_source='mixed'`로 두고 `analysis_weight` 정의 후에만 합산한다 |
| 실제 Web Event | `simulation_run_id=NULL`이므로 이 필터의 대상이 아니다. `actor_type='user'`로 먼저 분리한다 |

Persona 단위로 표본을 확인해야 하면 `bridge_persona_segment`의 `segment_type='persona_source'`를 사용한다. 두 경로는 같은 값을 가리키며, Mart 단위 필터는 `dim_simulation_run`, Persona 단위 분석은 bridge를 쓴다.

## 15. 검증 규칙 초안

| 검증 | 기준 | 실패 처리 |
| --- | --- | --- |
| `persona_id` 중복 | 100명/9,900명 전체에서 유일해야 함. 현재는 표본별 prefix(`PA`/`PC`)로 분리되어 교집합 0 | 생성 실패 또는 bad persona 격리 |
| 필수 속성 | `skin_type`, `skin_tone`, `stratum`, `review_bucket` 존재 | bad persona |
| 정규화 enum | `skin_type`, `skin_tone`, `hair_color`, `eye_color`는 정규화 값 사용 | 경고 또는 bad persona |
| 리뷰 수 | `n_reviews >= 3` | 샘플링 기준 위반 |
| 상품 수 | `n_products >= 3` 권장 | seed/holdout 품질 경고 |
| Canonical product join | `canonical_product_id`가 Product Feature/Product Data에 존재 | 없는 경우 seed/holdout 제외 또는 join 경고 |
| Holdout 판정 순서 | §6.1의 1~7단계 순서대로 판정 | 순서를 바꿔 구현하면 평가 모집단이 달라지므로 재구현 |
| Holdout eligibility | positive 평가 target은 `rating >= 4` 또는 `is_recommended=true` | 미충족 시 positive 평가 제외, 진단용으로만 보존 |
| 평가 누수 | `persona_profile_eval`의 어떤 컬럼도 holdout 리뷰를 입력으로 쓰지 않음 | 누수 발견 시 평가 결과 폐기 후 재계산 |
| 평가/운영 Profile 혼용 | 오프라인 평가는 `profile_scope='eval'`, 시뮬레이션/Dashboard는 `full` | 잘못된 scope 사용 시 평가 무효 |
| Attribute affinity fallback | NULL attribute와 missing segment row 처리 규칙 적용 | neutral/renormalization flag 확인 |
| Affinity neutral 값 | `neutral_lift=1.0`을 현재 clip 구간에 대입한 값(현재 `0.40`) 사용 | 상수 `0.5` 하드코딩 발견 시 수정 |
| synthetic runtime metadata | `actor_type='synthetic'` Event는 `properties.scenario_id`, `properties.simulation_run_id`, `properties.generator_type`을 모두 포함 | 누락 시 Spark semantic validation에서 `invalid_properties`로 bad event 격리 |
| run 단위 표본 일관성 | 한 `simulation_run_id` 안의 Persona는 모두 같은 `persona_source` | 섞이면 Dashboard `persona_source` 필터가 무효 |
| Agent 100명 분포 | Dashboard 기본 모집단 통계에서 9,900명 batch와 무보정 합산 금지 | 기본값에서 분리, 합산 시 `analysis_weight` 필요 |
| `author_id` 노출 | API/Event/Dashboard 외부 노출 금지. `persona_id`로 `author_id`를 그대로 쓰지 않음 | 문서/응답에서 제거, 생성기에서 ID 재발급 |

## 16. E2E 최소 사용 기준

다음 주 E2E에서 최소로 필요한 Persona 필드는 아래다.

| 목적 | 필수 필드 |
| --- | --- |
| synthetic Event 생성 | `persona_id`, `actor_type=synthetic`, `properties.scenario_id`, `properties.simulation_run_id`, `properties.generator_type` |
| Kafka/Spark dedup 후 분석 | `persona_id`, `session_id`, `event_id`, `product_id=canonical_product_id`, `event_time` |
| User Behavior Feature | `persona_id`, `canonical_product_id`, `event_weight`, `event_time` |
| Attribute Affinity 추천 | `skin_type`, `skin_tone`, `hair_color`, `eye_color`, NULL/missing fallback rule |
| DW Segment | `bridge_persona_segment`의 `segment_type`, `segment_value` |
| Dashboard 모집단 필터 | `simulation_run_id` → `dim_simulation_run.persona_source` |
| 오프라인 추천 평가 | `persona_profile_eval`, `persona_holdout_target`, `persona_evaluation_split` |

E2E 단계에서 아직 없어도 되는 것은 아래와 같다. 파이프라인 동작에는 영향이 없고, 운영/실험 비교 단계에서 채운다.

| 항목 | E2E 필수 여부 |
| --- | --- |
| `simulation_run`의 version 컬럼 4종 + `event_schema_version`, `split_version` | 선택. NULL 허용 |
| `persona_profile_eval` | E2E 파이프라인에는 불필요. 추천 성능 리포트를 낼 때 필수 |
| `analysis_weight` / `sampling_weight` | 미정의 상태 유지. agent/batch 합산을 하지 않으면 필요 없음 |

## 17. 남은 합의 사항

| 항목 | 확인 대상 | 설명 |
| --- | --- | --- |
| `profile_version` 값 | Data / AI-Product Feature | Persona 생성 기준 버전명을 어떻게 둘지 |
| `persona_source` 값 | Data / Simulator | `agent_sample`, `batch_sample` 명칭 확정 |
| `generator_type` 값 | Data / Kafka-Spark | `agent_realtime`, `python_batch` 명칭 확정 |
| seed 초기화 정책 | Data / AI-Product Feature | seed 리뷰를 User Behavior Vector 초기값에 반영할지, seen 제외에만 쓸지 |
| Holdout positive 기준 | Data / AI-Product Feature | 초안은 `rating >= 4` 또는 `is_recommended=true`. 추천 평가 정의에 따라 조정 가능 |
| User Behavior Vector 부정축 | Data / AI-Product Feature | positive/negative 분리 구조와 §12.1의 `abs()` 누적, 최종 감점 계수 `w_neg` 동기화 |
| Attribute Affinity neutral | Data / AI-Product Feature | 본 문서는 `neutral_lift=1.0` 기준(현재 `0.40`). `contracts/recommendation-io-spec.md`의 `0.5` 표기와 통일 필요 |
| `seen`/`n_products` 갱신 Event | Data / AI-Product Feature | 초안은 `final_weight > 0` 기준. canonical 정의는 `contracts/recommendation-io-spec.md`에서 확정 |
| Event weight 단일 출처 | Data / Frontend / AI | `frontend/src/types/log.ts`의 `EVENT_WEIGHT`와 `processed-schema.md` §18 초안 표의 값이 다르다. log.ts 기준으로 통일 |
| Persona ID 네임스페이스 | Data / Frontend | 프론트는 현재 `persona_id = author_id`(원천 리뷰어 ID)를 사용한다. Persona Schema의 `PA#####`와 충돌하고 `author_id` 비노출 원칙에도 어긋나므로 분리 규칙 확정 필요 |
| Agent 100명 합산 보정 | Data / Dashboard | 기본은 분리. 합산이 필요하면 `analysis_weight`/`sampling_weight` 정의 |
| `concern` segment 재도입 | Data / Dashboard | 현재 원천에 없어 제외. 생성 로직이 생기면 원천·정규화 규칙과 함께 Persona/DW 양쪽에 동시 추가 |
| Persona 저장소 | Data / Backend | Persona Profile을 파일, DB, Redis 중 어디에 둘지 |

## 18. 다른 문서·구현과의 정합성

이 문서를 기준으로 다른 문서와 구현이 맞춰져야 하는 항목이다.

| 항목 | 본 문서 기준 | 상대 문서/구현 상태 |
| --- | --- | --- |
| synthetic runtime metadata | `properties`에 `scenario_id`, `simulation_run_id`, `generator_type` 필수 | `event-taxonomy-trigger-schema.md` §8.4에 계약 반영됨. Collector는 `properties`를 검증 없이 통과시키므로 실제 강제는 Simulator(생성 시)와 Spark semantic validation에서 수행 |
| `persona_source` 필터 | Event 미포함, `dim_simulation_run` Join | `dw-schema.md` §6.7에 `dim_simulation_run` 정의 |
| `concern` segment | Persona segment에서 제외 | `dw-schema.md`의 `dim_persona_segment`/`bridge_persona_segment`에서 제거됨. `dim_product.concern_tags`는 상품 속성이므로 유지 |
| scenario/run 분리 | `scenario`(scenario_id) + `simulation_run`(simulation_run_id) | `dw-schema.md`에서 `dim_scenario` + `dim_simulation_run`으로 분리 |
| canonical product ID | Event/Feature/DW의 `product_id` = `canonical_product_id` | `products_200.json`의 `product_id`(병합 대표 ID)와 동일 기준 |
| 속성 정규화 값 | §5.1 요약 | `persona-attribute-preprocessing.md`가 원천. 일치 확인 완료(그 문서 §10) |
| Affinity neutral | `neutral_lift=1.0` → 현재 `0.40` | `contracts/recommendation-io-spec.md`는 `0.5` 표기. 통일 대상 |
| `persona_id` 발급 | 표본별 prefix. agent `PA00001~PA00100`, batch `PC00001~PC09900`. `author_id`와 분리 | 프론트 `frontend/src/lib/persona.ts`는 `persona_id = author_id`를 사용 중. 실제 Web Event(`actor_type='user'`)에만 해당하며 synthetic 경로에는 영향 없음 |

이 문서는 Persona 원천과 분석/추천 연결 기준을 정의하는 초안이다. 실제 생성기 구현 후 `persona_source`, `generator_type`, seed 초기화 정책, holdout 평가 기준, `seen` 갱신 기준을 E2E 결과와 추천 평가 결과에 맞춰 확정한다.
