# Persona 생성·분석 설계

작성일: 2026-09-02
최종 검증: 2026-09-03, PA 10·100명과 PC 100명 표본 평탄화 (위반 0건)
상태: 표본 평탄화 검증 완료, §7.1 target 선택 규칙 합의·E2E 검증 대기
계약 원본: [`contracts/persona-schema.md`](../../contracts/persona-schema.md)
평탄화 구현: [`batch/persona/`](../../batch/persona/README.md)

## 1. 문서 목적

이 문서는 리뷰 기반 Persona를 생성하고 시뮬레이션, 추천 평가, Dashboard segment에
연결하는 이유와 처리 흐름을 설명한다. Dataset별 grain, 컬럼, enum, 정규화 및
seed/holdout 판정 순서는 Persona 계약을 단일 출처로 사용한다.

```text
Review 원천
→ 사용자 속성 정규화
→ Persona 모집단
→ PA 100명 / PC 9,900명 표본
→ Scenario·Simulation Run
→ Synthetic Event
→ Processed·DW
```

## 2. 원천과 실행 산출물

| 범위 | 기준 |
| --- | --- |
| 리뷰 원천 | 사용자 속성, 평점, 추천 여부, 작성 시각, 상품 ID |
| 상품 기준 | 상위 200개 canonical Product |
| 생성 구현 | `simulator/personas/build_personas.py` |
| Agent 표본 | `simulator/personas/data/personas_100_agent.json` |
| Batch 표본 | `simulator/personas/data/personas_9900.json` |
| 검증 보고서 | `persona_sampling_report.json` |
| Affinity 입력 | `batch/ingest/data/affinity_lift.csv` |

상품 리뷰 ID는 사이즈 변형 병합 전 값일 수 있어 `group_id`가 있으면 대표 상품으로
정규화한다. 추천, Event, Product Feature와 DW는 canonical Product ID를 사용한다.

## 3. 사용자 속성 전처리 근거

리뷰 1,094,411건 실측에서 `skin_type`, `skin_tone`, `eye_color`, `hair_color`가 모두
존재하는 리뷰는 844,865건(77.20%)이었다. 결측을 임의 보완해 모집단을 늘리는 대신
네 속성이 모두 있는 리뷰만 Persona/Affinity 입력으로 사용한다.

| 항목 | 설계 이유 |
| --- | --- |
| `skin_type` 4종 유지 | 원본이 이미 분석 가능한 범주 |
| `skin_tone` 14종→5버킷 | 희소 조합을 줄이고 Persona·Affinity·DW Join 어휘 통일 |
| `brunette`→`brown` | 표기 차이로 생긴 잘못된 판별력 제거 |
| `Grey`→`gray` | 대소문자·철자 중복 제거 |
| `notSureST` 결측 | 실제 피부 톤이 아닌 placeholder |
| 최신 리뷰 대표값 | 프로필 변경을 현재 상태에 반영 |

동일 사용자의 최신값과 최빈값이 다른 경우가 있어 full Profile은 최신 리뷰를
사용한다. 하지만 평가에서는 마지막 리뷰를 holdout으로 숨기므로 최신 seed 리뷰로
Profile을 다시 만들어 정보 누수를 차단한다.

## 4. 모집단과 표본 설계

현재 모집단은 상위 200개 상품 중 긍정 상품을 3개 이상 가진 사용자 20,435명이다.
같은 상품의 중복 리뷰는 평균 평점으로 합친 뒤 긍정 상품 수를 계산한다.

| 항목 | 기준 |
| --- | --- |
| 긍정 상품 | 상품별 평균 평점 3.5 이상 |
| 층화 key | skin type 4 × skin tone 5 × 긍정 상품 수 4구간 = 80층 |
| Batch 표본 | 모집단 분포 기반 9,900명 |
| Agent 표본 | skin type×tone 20셀에 각 5명, 총 100명 |
| 난수 seed | 42 |

Agent 표본은 소수 segment와 행동 경로를 확인하기 위한 균등표본이라 모집단 분포를
대표하지 않는다. Dashboard 기본 통계는 `batch_sample`만 사용한다. 두 표본을 합산할
때는 sampling weight가 정의되어야 한다.

## 5. Full Profile과 평가 Profile

Full Profile은 시뮬레이션 행동 생성과 Dashboard segment에 사용한다. 평가 Profile은
holdout 리뷰를 제외한 seed만 사용하며 오프라인 Recall/NDCG와 가중치 선택에만 쓴다.

```text
full profile = 전체 리뷰 기준
eval profile = holdout 제외 seed 리뷰 기준
```

holdout 후보는 최신 리뷰 한 건이다. Product Feature Join이 불가능하면 평가에서
제외하고, Join은 가능하지만 긍정 조건을 만족하지 않으면 negative/diagnostic target으로
보존한다. 이 순서를 고정해야 실행마다 평가 대상 수가 달라지지 않는다.

생성된 Synthetic 로그로 생성 규칙 자체를 평가하면 순환 검증이 되므로 추천 품질은
실제 리뷰 holdout으로 검증한다.

## 6. 추천 입력 연결

Seed 리뷰 상품은 이미 경험한 상품으로 보고 추천 후보에서 제외한다. 리뷰만 존재하고
행동 Event가 없는 상품을 `viewed` 행동으로 간주하지는 않는다.

별점 1~2점 리뷰 상품은 긍정 seed에 섞지 않고 리뷰 기반 negative 축으로 보낸다.
행동 로그에서 “조회했지만 전환하지 않은 상품”으로 만드는 negative 축과 발생 근거가
다르므로 평가 결과에서 구분한다.

행동 집계와 Product/User Vector 결합 산식은
[`recommendation-io-spec.md`](../../contracts/recommendation-io-spec.md)를 따른다.
Persona 문서에는 벡터 산식을 복제하지 않는다.

Attribute Affinity는 피부·헤어·눈 속성별 값을 가중 결합한다. NULL 속성은 weight를
제외하고 나머지를 재정규화한다. Missing segment의 현재 실행 계약값은
`recommendation-io-spec.md`에 정의된 0.5다. 다만 lift 1.0을 clip 0.60~1.60 변환식에
넣으면 0.40이므로, 변환식과 fallback 의미를 AI/Product Feature 담당과 통일해야 한다.

## 7. Synthetic Event 연결

PA와 PC는 같은 Event 계약을 사용하지만 생성 방식이 다르다.

| 구분 | Persona ID | `generator_type` | 생성 경로 |
| --- | --- | --- | --- |
| PA | `PA00001~` | `agent_llm` | LLM Agent runner |
| PC | `PC00001~` | `python_batch` | Batch generator |

PA는 FE logger를 수정하지 않는다. runner가 `/api/events` batch를 캡처하고 Collector로
전송하기 직전에 synthetic metadata를 보강한다. Persona 선택 전 발생한 초기 Event는
필수 metadata가 없으므로 PA Event로 전송하지 않는다.

`persona_source`는 Event마다 반복하지 않는다. Persona 분석에서는 Profile segment로,
Mart 분석에서는 `simulation_run_id → dim_simulation_run`으로 확인한다.

## 8. Scenario와 Simulation Run

Scenario는 “무엇을 실행했는가”, Simulation Run은 “언제 어떤 버전과 표본으로 한 번
실행했는가”를 나타낸다. 같은 Scenario를 반복할 수 있으므로 grain을 분리한다.

`simulation_run_id`는 PA와 PC 모두 `run_<UTC timestamp>` 형식을 사용한다. 한 run에
두 표본이나 생성 방식을 섞지 않는다. seed만 저장해서는 재현할 수 없으므로 Persona,
Product Feature, Affinity, 추천 정책 및 Event Schema 버전을 함께 기록한다.

Dashboard의 기본 Synthetic 모집단 필터:

```text
Mart.simulation_run_id
→ dim_simulation_run
→ persona_source = 'batch_sample'
```

실제 Web Event는 `simulation_run_id=NULL`, `actor_type='user'`이므로 먼저 actor_type으로
분리한다.

## 9. 현재 정합성과 알려진 차이

현재 허용 사용자 속성은 총 20개 segment 값이며 `affinity_lift.csv`는 200개 상품 ×
20개 segment = 4,000행으로 구성된다.

해소된 차이:

- Profile 식별·버전 필드 6종(`user_id`, `persona_source`, `profile_version`,
  `profile_scope`, `created_at`, `updated_at`)이 생성기에 반영되어 두 표본 10,000명
  전원에 존재한다. 파일명이나 ID prefix로 추론하지 않는다.
- 중첩 JSON을 계약 테이블 8종으로 평탄화하는 구현이 `batch/persona/`에 생겼다.
  PA 10·100명과 PC 100명 표본에서 계약 §11 조건과 grain·nullable·enum·누출 검사가
  위반 0건으로 통과했다.

남은 차이:

- **§7.1의 target 선택 규칙이 `batch/jobs/eval_metadata.py`와 다르다.** 계약은 가장
  최신 리뷰를, 정본은 마지막 긍정 리뷰를 고른다. PC 9,900명 중 752명(7.6%)에서 다른
  상품이 나오고, 계약 규칙에서는 598명(6.0%)이 `is_holdout_eligible=false`가 된다.
  `batch/persona/compare_holdout_rules.py`가 수치를 낸다. AI/추천 담당과 합의 전이다.
- `persona_seed_product.initial_event_weight`의 산식이
  [`recommendation-io-spec.md`](../../contracts/recommendation-io-spec.md)에 없어 NULL로
  둔다. 값을 임의로 채우지 않는다.
- `eval_metadata.jsonl`은 PC 9,900명만 담는다. PA 100명의 평가 정본이 없다.
- `products_200.json`의 일부 리뷰 통계에는 `hair_color='brunette'`가 남아 있어 DW에서
  읽을 때 `brown`으로 합산해야 한다.
- Recommendation 계약의 missing affinity 0.5 표기와 현재 변환식 결과 0.40이
  불일치한다. AI/Product Feature 담당과 기준 통일이 필요하다.
- `simulation_run`·`scenario`(계약 §10)는 생성기 실행 산출물이라 평탄화 단계에 원천이
  없다. 실행 시점에 run manifest를 남길지 정해야 한다.

평탄화를 실제로 돌려 계약 §7.1의 결함 두 가지를 찾아 고쳤다. `negative`/`diagnostic`
경계가 없던 것과, 같은 상품에 리뷰를 두 번 이상 쓴 Persona(PC 2,160명·21.8%)의 target
상품이 seed에 남아 추천 후보에서 하드 제외되던 것이다. 자세한 근거는
[`batch/persona/README.md`](../../batch/persona/README.md)에 있다.

## 10. 샘플·E2E 검증 체크리스트

평탄화 산출물로 확인 완료:

1. ~~10명 smoke sample에서 Persona Schema와 enum을 검증한다.~~ PA 10명 위반 0건.
2. ~~PA·PC 전체 `persona_id` 교집합과 중복이 0인지 확인한다.~~ 표본 기준 0건.
3. ~~Profile 통계와 review bucket이 원천 리뷰에서 재현되는지 확인한다.~~ 위반 0건.
4. ~~Holdout 리뷰가 eval Profile과 seed Product에 포함되지 않는지 확인한다.~~
   상품 단위 누출까지 검사하도록 계약 §7.1-7과 §11-7을 고친 뒤 통과.
5. ~~모든 canonical Product가 Product Feature에 Join되는지 확인한다.~~ 위반 0건.

Event·Run 축이라 평탄화 산출물로 확인할 수 없는 항목:

6. PA Event가 `agent_llm`, PC Event가 `python_batch`를 사용하는지 확인한다.
7. 같은 run에서 Scenario, Persona source, generator type이 일관되는지 확인한다.
8. `persona_source` 필터가 DW/Mart까지 연결되는지 확인한다.
9. Sampling report의 층화 분포와 생성 결과가 일치하는지 확인한다.

§7.1 규칙 합의와 6~9번이 끝나기 전까지 Persona Schema 상태는 Draft로 유지한다.
