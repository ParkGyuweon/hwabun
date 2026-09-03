# 페르소나 계약 테이블

중첩 페르소나 JSON 을 `contracts/persona-schema.md` 가 정의한 **grain 별 평탄 테이블**
로 만들고, 만든 것이 계약을 지켰는지 검사한다.

```
simulator/personas/data/personas_*.json      사람 1명 + reviews[] 배열
        |  build_persona_tables.py
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

py contracts/persona/validate_persona_tables.py contracts/persona/data
py -m unittest discover -s contracts/persona -t contracts/persona -p "test_*.py"
```

`--sample` 은 `대역:인원` 이다 (`PA:10` · `PC:100` · `PC:all`). 산출은
`contracts/persona/data/<sample_id>/` 아래에 테이블당 JSONL 한 개와 `_manifest.json`
(원천 파일·행 수·규칙 버전) 이다.

포맷이 JSONL 인 이유는 의존성이 필요 없고 저장소의 다른 배치 산출물
(`eval_metadata.jsonl`, `product_feature.jsonl`) 과 같기 때문이다. Delta/Parquet 은
저장 엔진이 확정된 뒤에 붙인다 (`docs/analytics/dw-design.md` §5).

**산출물은 커밋하지 않는다.** 난수가 없어 누가 돌려도 같은 결과가 나오고, 아직 이
테이블을 읽는 모듈이 없다. 아래 §7.1 규칙이 확정되면 산출물이 바뀌므로 그때까지는
필요할 때 로컬에서 다시 만든다. 9,900명 전량은 약 70MB 다.

## 검증 결과 (2026-09-03)

| 표본 | 페르소나 | 검사 행 | 위반 |
|---|---:|---:|---:|
| `pa010` | 10 | 200 | 0 |
| `pa100` | 100 | 2,031 | 0 |
| `pc100` | 100 | 1,770 | 0 |

계약 §11 조건 9·10 은 Simulation Run 과 Event 의 `generator_type` 을 보는 항목이라
이 산출물의 범위 밖이다. Event 계약 검증기가 담당한다.

## 계약을 고치게 만든 것

평탄화를 실제로 돌려 보고 계약 §7.1 의 결함 두 가지를 찾아 고쳤다.

1. **`negative` / `diagnostic` 경계가 없었다.** §7.1-5 가 둘 중 하나라고만 쓰고
   기준을 정하지 않았다. `recommendation-io-spec.md` 의 리뷰 극성(1~2 부정 / 3 중립)
   을 따르도록 계약에 명시했다.
2. **정답 상품이 seed 에 남았다.** §7.1-7 을 글자대로 적용하면, 같은 상품에 리뷰를
   두 번 이상 쓴 사람(PC 9,900명 중 2,160명 · 21.8%)의 target 상품이 seed 에도
   들어간다. seed 상품은 `is_seen=true` 로 추천 후보에서 하드 제외되므로 정답을
   절대 맞힐 수 없는 평가가 된다. 후보와 같은 상품의 이전 리뷰를 `excluded` 로
   돌리도록 계약과 구현을 함께 고쳤다. `batch/jobs/eval_metadata.py` 도 같은 방어를
   이미 하고 있었다.

## 아직 결정되지 않은 것

- **§7.1 의 target 선택 규칙.** 계약(가장 최신 리뷰)과 `batch/jobs/eval_metadata.py`
  (마지막 긍정 리뷰)가 PC 9,900명 중 752명(7.6%)에서 다른 상품을 고른다.
  `compare_holdout_rules.py` 가 수치를 낸다. AI/추천 담당과 합의 전이다.
- **`initial_event_weight` 산식.** 계약상 nullable=Y 이고 `recommendation-io-spec.md`
  에 정의가 없어 NULL 로 둔다.
- **PA 100명의 평가 정본.** `eval_metadata.jsonl` 은 PC 9,900명만 담는다.
