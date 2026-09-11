# 페르소나 데이터

| 파일 | 내용 | 크기 |
|---|---|---|
| `personas_100_agent.json` | **인터랙티브** 100명 (`PA00001`~`PA00100`) | 0.6MB |
| `personas_9900.json` | **합성 로그용** 9,900명 (`PC00001`~`PC09900`) | 58.1MB |
| `persona_style.json` | 페르소나별 성향 6축 (10,000명 전체) | 1.2MB |
| `persona_sampling_report.json` | 추출 파라미터 · 모집단 대비 표본 분포 검증 | 2KB |
| `personas_holdout_a.json` | **홀드아웃 A** 2,000명 (`PH00001`~`PH02000`) — 고르는 데 쓴다 | 11.8MB |
| `personas_holdout_b.json` | **홀드아웃 B** 2,000명 (`PH00001`~`PH02000` — A 와 같은 원본 대역) — **확인에만** 쓴다 | 11.6MB |

> **원본 ID 는 그대로 둔다 (2026-09-08, 데이터 파트 Jira 204).** B 의 persona_id 를 직접
> 바꾸면 동적 평가의 결정적 노이즈 시드와 `eval_metadata` 조인이 깨진다. 전역 ID
> (B → `PH02001`~`PH04000`) 는 계약 테이블 `persona_profile.persona_id` 에만 있고, 원본은
> `source_persona_id` 로 보존된다. AI 산출물을 DW 와 붙일 때의 조인 키:
> `eval_metadata.split = persona_profile.evaluation_cohort` AND
> `eval_metadata.persona_id = persona_profile.source_persona_id`. 4,000건 전부 붙고 누락 0,
> 전역 ID 유일 — `contracts/persona/build_persona_tables.py --sample HA:all` / `HB:all` 로 확인.
| `holdout_{a,b}_sampling_report.json` | 홀드아웃 추출 파라미터·분포 검증 | 2KB |

## PA / PC 대역 구분

| 대역 | 용도 | 합성 로그 |
|---|---|---|
| `PA00001` ~ `PA00100` | 프론트 페르소나 전환기(드롭다운) + LLM 에이전트가 **직접 조종** | **생성하지 않음** |
| `PC00001` ~ `PC09900` | 시뮬레이터가 합성 행동 로그를 생성 | 생성 |

PA 에 합성 로그를 쏘면 1인당 약 590건이 미리 쌓여, 사람이 10번 클릭해도 벡터의 1.7% 밖에 못 움직입니다. `gen_behavior_logs.py` 는 기본적으로 PC 만 생성하며 `--include-agents` 로만 PA 를 포함합니다.

두 파일은 `persona_id` · `author_id` 가 하나도 겹치지 않습니다.

## 홀드아웃 (2026-09-07 신설)

### 왜 만들었나 — `test` 를 소진했다

하루에 MMR λ 7개 값 · 브랜드 상한 4개 값 · CF 5개 조건을 `test` 1,971명에서
돌렸다. `persona_split.py` 의 docstring 이 정확히 그 실수를 경고하고 있었는데
같은 일을 했다.

페르소나 풀에 **한 번도 쓰지 않은 리뷰어가 10,425명** 남아 있어 거기서 뗐다.

```
풀 20,435명 − 페르소나 10,000명 − 중복계정 12명 = 후보 10,425명
```

### 쓰는 법 — **A 에서 고르고 B 로 확인한다**

| | 용도 |
|---|---|
| `holdout_a` | **후보를 고른다.** 하이퍼파라미터·구성을 여기서 훑는다 |
| `holdout_b` | **확인만 한다.** 여기서 또 훑으면 같은 오염이 반복된다 |

이 체계가 만든 첫날 바로 값을 했다 — CF 정규화 지수가 `holdout_a` 에서
**+1.00%p [+0.15, +1.80]** 로 CI 가 0 을 제외했는데 `holdout_b` 에서
**−0.20%p** 로 뒤집혔다. 없었으면 개선으로 문서에 적었을 것이다.

> **2,000명으로는 1%p 를 못 본다.** (아래 38%대는 CF 가점 단계(09-07 오전)의 값이다. 현행 대표 지표는
> LTR 42.15 / 43.15%, evaluation-framework 부록 W.) 당시 값 자체가 표본 간에 38.15% ↔ 39.25% 로
> 1.1%p 흔들린다 — 찾던 개선폭과 같은 크기다. **1%p 급 실험은 홀드아웃을 더 크게
> 잡거나 두 개를 짝지어 판정한다.**

### 검증

| | 결과 |
|---|---|
| 분포 (skin_type·tone·review_bucket) | 모집단 대비 **최대 0.10%p** |
| 시드 평균 | 3.5개 — 기존 세 split 과 같다 |
| 새 브랜드 target | 69.2 / 70.0% (기존 68.6~69.9% 범위 안) |
| `eval_metadata` 제외 | **0명** |
| a·b 교집합 | **0명** |

### ⚠️ 계약에 아직 없는 대역이다

`contracts/persona-schema.md` §2.1 은 `PA`·`PC` 두 대역만, 검증기
(`validate_persona_tables.py:164`)는 `persona_source` 를
`{agent_sample, batch_sample}` 로만 압니다. 홀드아웃은 잠정으로
`PH` · `holdout_sample` 을 씁니다.

**그래서 이 산출물은 측정용이고 계약 평탄 테이블로 내리지 않습니다.**
정식화하려면 데이터 파트가 enum 과 대역을 열어 주어야 합니다 (요청 전달됨).

### ⚠️ 파일이 늘면 동시발생을 다시 만들어야 한다

CF 가점의 입력인 `batch/ingest/data/serving/item_cooc.npz` 는 **이 디렉터리를
훑어서** `personas_*.json` 의 `author_id` 를 전부 뺍니다 (현재 14,000명).

**새 홀드아웃이 동시발생에 남아 있으면 그것으로 잰 수치가 전부 거짓이 됩니다.**
`regenerate_all` 12단계에서 다시 만듭니다.

### 남은 인원

**8,425명.** 2,000명짜리를 4개 더 뗄 수 있습니다. 유한하므로 어느 시점에는
**대표 지표를 어느 집합으로 고정할지**를 팀이 정해야 합니다.

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

### 홀드아웃

```bash
# 이미 쓴 사람을 전부 뺀 뒤 같은 층화 경로로 뽑는다.
# --tag 만 다르면 서로 겹치지 않는다 (자기 자신 외의 personas_*.json 을 전부 제외)
python simulator/personas/build_personas.py --holdout 2000 --seed 43 --tag a        --exclude simulator/personas/holdout_exclude_dupaccounts.txt
python batch/jobs/eval_metadata.py        --personas simulator/personas/data/personas_holdout_a.json --tag holdout_a
```

`--exclude` 는 **같은 리뷰 본문을 쓴 계정 12명**입니다. 같은 사람이 계정을 두 개
쓰는 것은 원리적으로 못 가리지만, 본문이 여러 `author_id` 에 걸친 경우로 상한을
쟀습니다 — 전체의 0.043% 였고 페르소나/미사용 경계를 넘는 것이 12명이었습니다.

> **플래그를 안 주면 `personas_9900.json` 이 한 바이트도 달라지지 않습니다**
> (타임스탬프 외 diff 0줄로 확인). 홀드아웃 모드는 기존 경로를 안 건드립니다.

**`batch/ingest/data/products_200.json` 이 먼저 있어야 합니다.** 리뷰를 상품에 조인할 때 `_merged.member_product_ids` 를 쓰기 때문입니다. 카탈로그가 바뀌면 페르소나도 다시 만들어야 합니다.

`personas_9900.json` 은 58MB 입니다. 내용을 바꿀 때마다 파일 전체가 새 blob 으로 저장되므로 잦은 재생성·커밋은 저장소 용량을 빠르게 늘립니다. 추출 기준이 확정된 뒤에만 갱신하는 것을 권합니다.
