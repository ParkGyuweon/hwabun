# 페르소나 데이터

| 파일 | 내용 | 크기 |
|---|---|---|
| `personas_100_agent.json` | **인터랙티브** 100명 (`PA00001`~`PA00100`) | 0.6MB |
| `personas_9900.json` | **합성 로그용** 9,900명 (`PC00001`~`PC09900`) | 58.1MB |
| `persona_style.json` | 페르소나별 성향 6축 (10,000명 전체) | 1.2MB |
| `persona_sampling_report.json` | 추출 파라미터 · 모집단 대비 표본 분포 검증 | 2KB |

## PA / PC 대역 구분

| 대역 | 용도 | 합성 로그 |
|---|---|---|
| `PA00001` ~ `PA00100` | 프론트 페르소나 전환기(드롭다운) + LLM 에이전트가 **직접 조종** | **생성하지 않음** |
| `PC00001` ~ `PC09900` | 시뮬레이터가 합성 행동 로그를 생성 | 생성 |

PA 에 합성 로그를 쏘면 1인당 약 590건이 미리 쌓여, 사람이 10번 클릭해도 벡터의 1.7% 밖에 못 움직입니다. `gen_behavior_logs.py` 는 기본적으로 PC 만 생성하며 `--include-agents` 로만 PA 를 포함합니다.

두 파일은 `persona_id` · `author_id` 가 하나도 겹치지 않습니다.

## 레코드 필드

`contracts/persona-schema.md` §4 `persona_profile` 을 따릅니다. 계약이 `nullable=N`
으로 요구하는 컬럼은 전부 채워져 있습니다 (2026-09-02 확인, 10,000명 위반 0건).

| 필드 | 값 | 비고 |
|---|---|---|
| `persona_id` | `PA00001` / `PC00001` … | 파일 안에서의 순번. `author_id` 와 무관 |
| `user_id` | `persona_id` 와 같음 | 계약 §4 기본값 |
| `author_id` | 원천 리뷰어 ID | 추적용. 조인 키가 아니고 외부 노출 금지 |
| `persona_source` | `agent_sample` / `batch_sample` | **접두사를 파싱하지 말고 이 값을 쓰십시오** (계약 §2.1) |
| `skin_type` · `skin_tone` · `eye_color` · `hair_color` | 정규화된 값 | 계약 §3 enum |
| `stratum` · `review_bucket` | `skin_type\|skin_tone\|review_bucket` | 층 식별 |
| `n_reviews` · `n_products` · `n_positive` · `n_negative` · `n_neutral` · `avg_rating` | 집계값 | |
| `profile_version` | `persona-v1` | 추출 규칙이 바뀌면 올립니다 |
| `profile_scope` | `full` | seed 만 쓰는 eval Profile 은 계약 §5 로 따로 냅니다 |
| `created_at` · `updated_at` | 생성 시각 (UTC) | 한 번의 실행에서 전원 같은 값 |
| `reviews` | 구매 이력 배열 | 계약 §6 `persona_review_history` 에 대응 |

이 파일은 **중첩 JSON**(사람 1명 + `reviews` 배열)이고 계약은 grain 별 평탄
테이블입니다. 평탄화·적재와 E2E 검증은 데이터 파트가 이 산출물을 입력으로 받아
수행합니다. `evaluation_role`(seed/holdout_target/excluded)은 여기 없고
`batch/ingest/data/eval_metadata.jsonl` 이 정본입니다.
PA 에이전트 100명의 대조군은 같은 규칙으로 만든 `eval_metadata_agent.jsonl` 입니다
(`python batch/jobs/eval_metadata.py --agent`).

> **2026-09-03.** 계약 §7.1 과 정본이 같은 정답을 고르도록 정렬했습니다.
> target 은 **가장 마지막 긍정 리뷰**이고, 긍정은 `rating >= 4` 또는
> (`is_recommended` 그리고 `rating >= 3`), 같은 날짜 tie-break 은 `review_id DESC`
> 입니다 (§7.1.1 · §7.1.2). 이 둘로 PC 162명의 target 이 바뀌었고 남은 불일치는
> **0건**입니다 (`contracts/persona/compare_holdout_rules.py --require-zero`).
> 모수는 PC 9,900행 · PA 100행 그대로입니다.

## 추출 기준

- **모집단**: 상위 200개 상품에서 **긍정(4~5점) 상품 3개 이상**을 보유한 리뷰어 **20,435명** (추출률 48.9%)
- 하한이 3개인 이유는 리뷰를 **시드 / 좋아요 / 정답**으로 나눠 써야 하기 때문입니다. 2개면 시드가 1개만 남아 사용자 벡터가 상품 하나의 복사본이 됩니다
- **극성**: 4~5점 = 긍정 / 3점 = 중립(제외) / 1~2점 = 부정. 같은 상품에 리뷰를 여러 번 쓴 경우(59%)는 평점 평균으로 합칩니다
- **층화추출**: `skin_type`(4) × `skin_tone`(5버킷) × **긍정 상품 수 구간**(`3` / `4` / `5-6` / `7+`) = **80개 층**, 비례배분 + 최대잔여법
- 세 번째 축이 리뷰 건수가 아니라 **긍정 상품 수**인 이유는, 시드·정답으로 쓸 수 있는 재료의 개수가 곧 추천 난이도이기 때문입니다
- **사용자 속성**: 리뷰마다 다를 경우 **가장 최신 리뷰** 기준 (`submission_time` 정렬 후 마지막, 동일 시각은 `review_id` 순)
- **표기 정규화**: `skin_tone` 5버킷, `hair_color` `brunette`→`brown` 병합, `eye_color` `Grey`→`gray` 병합
- **에이전트 100명만 균등배분** (`skin_type` × `skin_tone` 20셀 × 5명) — 드롭다운에서 어떤 조합을 골라도 시연이 되도록

### 속성이 흔들리는 사용자

세포라는 리뷰를 쓸 때마다 프로필 속성을 다시 받습니다. 그래서 같은 사람인데 리뷰마다 값이 다른 경우가 **2,741명(13.4%)** 있습니다. 최신값을 채택했고, 최빈값을 썼을 때와 **1,077명**의 결과가 달라집니다. 수치를 해석할 때 기억해 둘 것.

### 분포 검증

모집단 대비 표본 차이가 전 항목 **0.03%p 이내**입니다 (최대 0.027%p).

| | 모집단 | 표본 |
|---|---:|---:|
| 평균 리뷰 수 | 5.59 | 5.58 |
| 평균 상품 수 | 4.57 | 4.57 |
| 평균 평점 | 4.610 | 4.615 |

> 에이전트 100명은 분포가 **의도적으로 왜곡**되어 있습니다. 9,900명과 통계를 합산하려면 셀별 가중치 보정이 필요합니다.

## 재생성

`seed=42` 고정이라 **누가 돌려도 동일한 결과**가 나옵니다. 원본 CSV 에서 처음부터 다시 돌려 세 파일이 바이트 단위로 동일함을 확인했습니다 (2026-08-31).

원본 CSV 는 `.gitignore` 대상이라 위치를 환경변수로 넘깁니다.

```bash
export SEPHORA_DATASET=/path/to/dataset/sephora

# 1) 페르소나 10,000명
python simulator/personas/build_personas.py

# 2) 성향 6축 — 페르소나에서 파생되므로 1)을 돌렸으면 반드시 같이 돌린다
python simulator/generator/build_persona_style.py
```

**`batch/ingest/data/products_200.json` 이 먼저 있어야 합니다.** 리뷰를 상품에 조인할 때 `_merged.member_product_ids` 를 쓰기 때문입니다. 카탈로그가 바뀌면 페르소나도 다시 만들어야 합니다.

`personas_9900.json` 은 56MB 입니다. 내용을 바꿀 때마다 파일 전체가 새 blob 으로 저장되므로 잦은 재생성·커밋은 저장소 용량을 빠르게 늘립니다. 추출 기준이 확정된 뒤에만 갱신하는 것을 권합니다.
