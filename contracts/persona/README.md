# 페르소나 계약 테이블

중첩 페르소나 JSON 을 `contracts/persona-schema.md` 가 정의한 **grain 별 평탄 테이블**
로 만들고, 만든 것이 계약을 지켰는지 검사한다.

```
simulator/personas/data/personas_*.json      사람 1명 + reviews[] 배열
        |  build_persona_tables.py (holdout B는 계약 ID +2,000)
        v
contracts/persona/data/<sample>/*.jsonl          테이블 8종
        |  validate_persona_tables.py
        v
계약 §11 · grain · nullable · enum · 누출 검사
```

DW 의 `dim_persona_segment` 도, Processed 의 persona join 도 평탄 테이블을 전제한다.
지금까지 이 변환이 없어서 계약이 실제로 산출 가능한지 확인된 적이 없었다.

## 파일

| 파일 | 역할 |
|---|---|
| `build_persona_tables.py` | 평탄화. 계약 컬럼표(`TABLE_SPECS`)의 단일 출처 |
| `holdout_rule.py` | 계약 §7.1 seed / holdout_target / excluded 판정 |
| `validate_persona_tables.py` | 산출물 검사. 위반이 있으면 종료 코드 2 |
| `compare_holdout_rules.py` | 계약 §7.1 과 `eval_metadata.jsonl` 의 차이를 잰다 |
| `test_persona_tables.py` | 원천에 드문 경우(시각 없는 리뷰·NULL 속성·같은 상품 재리뷰)의 단위 테스트 |

## 산출 테이블

| 테이블 | 계약 | grain |
|---|---|---|
| `persona_profile` | §4 | `persona_id` |
| `persona_profile_eval` | §5 | `persona_id` |
| `persona_review_history` | §6 | `persona_id + review_id` |
| `persona_seed_product` | §7.2 | `persona_id + canonical_product_id` |
| `persona_holdout_target` | §7.3 | `persona_id + target_canonical_product_id` |
| `persona_evaluation_split` | §7.4 | `persona_id` |
| `bridge_persona_segment` | §8.1 | `persona_id + segment_type + segment_value` |
| `persona_attribute_affinity_input` | §8.2 | `persona_id` |

계약 §10 의 `simulation_run` · `scenario` 는 여기서 만들지 않는다. 생성기 **실행**
산출물이라 페르소나 평탄화 단계에 원천이 없다.

## 실행

```bash
py contracts/persona/build_persona_tables.py --sample PA:10
py contracts/persona/build_persona_tables.py --sample PA:100
py contracts/persona/build_persona_tables.py --sample PC:100
py contracts/persona/build_persona_tables.py --sample HA:all
py contracts/persona/build_persona_tables.py --sample HB:all

py contracts/persona/validate_persona_tables.py contracts/persona/data
py contracts/persona/compare_holdout_rules.py
py -m unittest discover -s contracts/persona -t contracts/persona -p "test_*.py"
```

`--sample` 은 `대역:인원` 이다 (`PA:10` · `PC:all` · `HA:all` · `HB:all`). 산출은
`contracts/persona/data/<sample_id>/` 아래에 테이블당 JSONL 한 개와 `_manifest.json`
(원천 파일·행 수·규칙 버전) 이다.

포맷이 JSONL 인 이유는 의존성이 필요 없고 저장소의 다른 배치 산출물
(`eval_metadata.jsonl`, `product_feature.jsonl`) 과 같기 때문이다. Delta/Parquet 은
저장 엔진이 확정된 뒤에 붙인다 (`docs/analytics/dw-design.md` §5).

**산출물은 커밋하지 않는다.** 난수가 없어 누가 돌려도 같은 결과가 나오고, 아직 이
테이블을 읽는 모듈이 없다. 필요할 때 로컬에서 다시 만든다. 9,900명 전량은 약 70MB 다.

## Holdout ID와 평가 재현성

Holdout 원본 A/B는 기존 평가를 재현하기 위해 둘 다 `PH00001`~`PH02000`을 유지한다.
원본 B를 고치면 동적 평가의 `persona_id` 기반 노이즈와 기존 metadata 조인이 바뀐다.
대신 평탄 테이블 생성 시 A는 `PH00001`~`PH02000`, B는
`PH02001`~`PH04000`으로 내보낸다. 모든 계약 테이블의 ID와 `user_id`가 함께 바뀌며,
집단은 ID를 파싱하지 않고 `evaluation_cohort`로 조회한다.

`persona_profile.source_persona_id`에는 변환 전 ID를 모든 PA·PC·Holdout 행에 보존한다.
AI 평가 metadata를 Dimension에 연결할 때는 아래 복합 키를 사용하고, 결과 컬럼인
`persona_profile.persona_id`를 전역 ID로 사용한다.

```text
eval_metadata.split      = persona_profile.evaluation_cohort
eval_metadata.persona_id = persona_profile.source_persona_id
```

예를 들어 A와 B의 원본 `PH00001`은 각각 전역 `PH00001`, `PH02001`로 Join된다.
소비처가 ID 숫자 대역을 파싱하거나 B에 직접 2,000을 더하는 것은 계약이 아니다.

CF 동시발생은 `build_cooc.py`가 `personas_*.json` 전체의 `author_id`를 제외한다.
`batch/jobs/test_build_cooc.py`가 A/B 파일 추가 시 이 누출 차단 규칙을 검증한다.

## 검증 결과 (2026-09-08)

| 표본 | 페르소나 | 검사 행 | 위반 |
|---|---:|---:|---:|
| `paall` | 100 | 2,125 | 0 |
| `pcall` | 9,900 | 208,602 | 0 |
| `haall` | 2,000 | 44,245 | 0 |
| `hball` | 2,000 | 43,981 | 0 |

네 표본의 전역 `persona_id` 교집합은 0건이며, Holdout A/B AI metadata 4,000행은
`(split, persona_id) = (evaluation_cohort, source_persona_id)`로 모두 Join된다.

계약 §11 조건 9·10 은 Simulation Run 과 Event 의 `generator_type` 을 보는 항목이라
이 산출물의 범위 밖이다. Event 계약 검증기가 담당한다.

## 계약을 고치게 만든 것

평탄화를 실제로 돌려 보고 계약 §7.1 의 결함 세 가지를 찾아 고쳤다.

1. **`negative` / `diagnostic` 경계가 없었다.** 둘 중 하나라고만 쓰고 기준을 정하지
   않았다. `recommendation-io-spec.md` 의 리뷰 극성(1~2 부정 / 3 중립)을 따르도록
   계약에 명시했다.
2. **정답 상품이 seed 에 남았다.** 이전 리뷰를 전부 seed 로 두면, 같은 상품에 리뷰를
   두 번 이상 쓴 사람(PC 2,137명 · 21.6%)의 target 상품이 seed 에도 들어간다. seed
   상품은 `is_seen=true` 로 추천 후보에서 하드 제외되므로 정답을 절대 맞힐 수 없는
   평가가 된다. target 과 같은 상품의 이전 리뷰를 `excluded` 로 돌렸다.
3. **정답 선택 규칙이 평가 정본과 달랐다.** 계약은 가장 최신 리뷰를,
   `batch/jobs/eval_metadata.py` 는 마지막 긍정 리뷰를 골라 PC 9,900명 중 752명(7.6%)
   에서 다른 상품이 나왔다. 우리가 만드는 것은 선호 상품을 맞히는 추천기이므로
   계약을 정본 정의로 맞췄다. 불만 리뷰는 정답이 아니라
   `persona_profile.latest_review_label` 로 사람 속성에 남긴다.

## 정답 규칙 정렬 현황

`compare_holdout_rules.py` 가 계약과 평가 정본이 같은 정답을 고르는지 확인한다.

| 단계 | PC 9,900명 | PA 100명 |
|---|---:|---:|
| 계약 개정 전 | 752명 (7.6%) | 정본 없음 |
| 계약을 정본 정의로 개정 | 162명 (1.6%) | 정본 없음 |
| 정본이 §7.1.1·§7.1.2 반영 | **0명** | **0명** |

2026-09-03 양쪽 모두 0건으로 정렬됐다. 정본은 PC 가 `eval_metadata.jsonl`,
PA 가 `eval_metadata_agent.jsonl` 로 분리돼 있다. PC 평가 표본에 PA 가 섞이면 안 되기
때문이며 이 도구는 두 파일을 각각 읽는다.

```bash
py contracts/persona/compare_holdout_rules.py --require-zero
```

규칙이나 원천이 바뀌면 다시 갈라지므로 회귀 확인용으로 남긴다. 불일치가 1건이라도
있으면 종료 코드 2 로 실패한다.

## 의도적으로 비우는 값

`persona_seed_product.initial_event_weight` 는 **항상 NULL 이다.** 산식이 정해지지
않아 비워 둔 것이 아니다.

Seed 상품은 스칼라 가중치로 주입되지 않는다. 생성기가 Seed 를 실제 Event 로 펼치고,
그 뒤로는 일반 Event 와 같은 행동 가중치 표로 누적된다. 그래서 이 컬럼에 채울 값이
없는 것이 정상이다 (AI 담당 확인, 2026-09-03). 누적 규칙은 계약 §12.1 이 참조하는
`recommendation-io-spec.md` §2 에 있다.

컬럼은 Seed 에 스칼라 초기값을 주는 방식으로 바뀔 경우를 위해 계약에 남아 있다.
