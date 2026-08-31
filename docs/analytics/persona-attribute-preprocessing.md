# Persona 사용자 속성 전처리 기준

작성일: 2026-08-28
최종 검증: 2026-08-31
상태: 현재 Persona 생성 구현과 산출물을 재현하기 위한 전처리 기준서
기준 구현: `simulator/personas/build_personas.py` (`370b05b`)
기준 산출물: `personas_*.json`, `persona_sampling_report.json`, `products_200.json`, `affinity_lift.csv`
관련 문서: `persona-schema.md`, `dw-schema.md`, `docs/ai/recommendation-design.md`, `simulator/personas/data/README.md`, `batch/ingest/data/README.md`

## 1. 문서 목적

Sephora 원본 리뷰에서 Persona 데이터를 만들 때 **실제로 적용하는** 사용자 속성 4종(`skin_type`, `skin_tone`, `eye_color`, `hair_color`)의 정규화·결측 처리와 모집단·층화추출 기준을 한 곳에 정리한다.

이 기준은 이미 세 곳에서 동시에 사용되고 있다.

| 사용처 | 무엇에 쓰이는가 |
| --- | --- |
| Persona 생성 | `personas_9900.json`, `personas_100_agent.json`의 속성값과 층화추출 key |
| 추천 (Attribute Affinity) | `affinity_lift.csv`의 `segment` 값. 정규화 값이 곧 조회 key다 |
| DW 분석 | `bridge_persona_segment.segment_value`, `dim_persona_segment`의 segment 값 |

세 곳이 같은 어휘를 써야 Join이 성립하므로, 값 하나를 바꾸면 세 곳이 동시에 깨진다. 그래서 별도 문서로 고정한다.

이 문서는 새 추천 Feature를 설계하는 문서가 아니다. 이미 완료된 Persona 데이터 전처리와 표본 생성 규칙을 설명하고, 이후 재생성·검증 시 같은 기준을 적용하기 위한 문서다.

## 2. 원천과 적용 지점

| 구분 | 위치 | 비고 |
| --- | --- | --- |
| 원본 데이터셋 | Kaggle "Sephora Products and Skincare Reviews" | 약 520MB. 레포에 커밋하지 않음 |
| Persona 생성기 | `simulator/personas/build_personas.py` | 모집단, 속성 정규화, 층화추출, PA/PC 분리의 실행 기준 |
| 상품 전처리 | `batch/ingest/build_products_json.py` | 상품 병합과 `_review_stats.segment_counts` 생성 |
| Affinity 전처리 | `build_affinity_lift.py` | 현재 레포 외부. 결과 CSV와 계산식은 아래 문서/계약으로 검증 |
| 전처리 결과 (Persona) | `simulator/personas/data/personas_9900.json`, `personas_100_agent.json` | `seed=42` 고정. 재실행 시 동일 결과 |
| 전처리 결과 (상품) | `batch/ingest/data/products_200.json` | `_review_stats.segment_counts` 사용 시 §11.1의 `brunette` 예외 적용 |
| 전처리 결과 (친화도) | `batch/ingest/data/affinity_lift.csv` | `segment` 컬럼이 정규화 후 어휘 |
| 근거 분석 | `docs/ai/recommendation-design.md` §6-4·6-6·6-7 | 병합/버킷 결정 근거 |

Persona 모집단과 표본 생성은 `build_personas.py`를 실행 기준으로 삼고, `persona_sampling_report.json`과 `personas_*.json`을 결과 검증 기준으로 삼는다. 이 문서는 구현의 의미와 변경 절차를 설명한다. 구현이나 산출물이 바뀌면 같은 변경에서 이 문서와 `persona-schema.md`를 함께 갱신한다.

## 3. 대상 필드와 원본 상태

리뷰 1,094,411건 전수 기준 채움률이다.

| 필드 | 채움률 | 원본 값 종류 | 주요 문제 |
| --- | ---: | ---: | --- |
| `skin_type` | 89.81% | 4종 | 없음 |
| `skin_tone` | 84.42% | 14종 | 분포 극단 편중(`ebony` 0.00%), `notSureST` placeholder 혼입 |
| `eye_color` | 80.85% | 6종 | `Grey`/`gray` 표기 중복 |
| `hair_color` | 79.28% | 7종 | `brunette`/`brown` 표기 중복 |

4개 필드가 **모두** 채워진 리뷰는 844,865건(77.20%)이다.

| 채워진 필드 수 | 리뷰 수 | 비율 |
| ---: | ---: | ---: |
| 0개 | 105,827 | 9.67% |
| 1개 | 48,564 | 4.44% |
| 2개 | 54,337 | 4.96% |
| 3개 | 40,818 | 3.73% |
| 4개 전부 | 844,865 | 77.20% |

## 4. 정규화 규칙

### 4.1 `skin_type` — 원본 유지

원본 4종을 그대로 사용한다. 병합·버킷팅 없음.

```text
combination | dry | normal | oily
```

### 4.2 `skin_tone` — 14종 → 5버킷

| 버킷 | 원본 값 | 전체 리뷰 대비 |
| --- | --- | ---: |
| `fair` | porcelain, fair, fairLight | 24.30% |
| `light` | light, lightMedium | 42.30% |
| `medium` | medium, mediumTan, olive | 12.31% |
| `tan` | tan | 3.08% |
| `deep` | deep, rich, dark, ebony | 2.43% |

버킷팅 이유는 두 가지다.

- 원본 14종은 분포가 치우쳐 상품 200개 × 14종 = 2,800셀 중 하위 셀의 리뷰가 한 자릿수라 통계가 성립하지 않는다. 5버킷으로 희소 값을 합쳐 개별 원본 값보다 안정적인 세그먼트 표본을 확보한다.
- `skin_tone`을 5버킷으로 묶어 희소한 원본 값을 합치고, Persona·Affinity·DW가 동일한 어휘로 Join할 수 있게 했다.

### 4.3 `hair_color` — `brunette` → `brown` 병합

원본 7종 → 병합 후 6종.

```text
auburn | black | blonde | brown | gray | red
```

`brunette`는 별개의 색이 아니라 `brown`의 표기 변형이다. 같은 사람이 수집 배치에 따라 다르게 기록됐고, 상품 200개 중 99개는 `brunette` 0%인 반면 특정 상품은 `brunette` 48.5% / `brown` 0.6%처럼 갈렸다. 이 아티팩트 때문에 평점 기반 판별력에서 `hair_color`가 1위로 나왔고, 병합 후 최하위로 내려갔다. 즉 **병합하지 않으면 추천 근거가 틀어진다.**

### 4.4 `eye_color` — `Grey` → `gray` 병합

원본 6종 → 병합 후 5종.

```text
blue | brown | gray | green | hazel
```

대소문자·영미 철자 혼재로 같은 색이 두 값으로 분리된 것이다(`Grey` 0.44% / `gray` 0.06%).

## 5. 결측 처리 기준

| 대상 | 처리 | 근거 |
| --- | --- | --- |
| 사용자 속성 4개 중 하나라도 비어 있는 리뷰 | Persona/Affinity 모집단에서 제외 | 기준을 "2개 이상"으로 완화해도 고유 상품이 2,345 → 2,350개로 5개만 늘어 실익이 없다 |
| `skin_tone='notSureST'` | 결측으로 처리(값으로 두지 않음) | "잘 모르겠음" placeholder. 84만 건 중 63건이라 버킷을 하나 더 만들 이유가 없다 |
| 대표 속성이 리뷰마다 다름 | 최신 리뷰 값 채택(§6) | 프로필 수정이 주된 원인이므로 최신 상태가 기준 |
| Persona 대표 속성이 최종적으로 비는 경우 | `persona_profile`에서 `eye_color`, `hair_color`만 nullable | `skin_type`, `skin_tone`은 모집단 정의상 항상 존재 |
| Affinity 조회 시 attribute가 NULL | 해당 attribute weight를 0으로 두고 나머지를 합 1.0으로 재정규화 | `persona-schema.md` §11 |
| Affinity 테이블에 segment row 없음 | `neutral_lift=1.0`을 변환식에 대입한 값 사용 + `affinity_missing=true` | `persona-schema.md` §11.1 |

**결측 보완(imputation)은 사용자 속성에 적용하지 않는다.** 형제 상품에서 값을 채우는 규칙은 상품 필드(`ingredients`, `highlights`, 카테고리 3종)에만 적용된 것이며, 사용자 속성에는 적용되지 않았다.

## 6. 대표 속성 확정 규칙

한 사용자의 리뷰라도 속성이 다르게 기록된 경우가 있다. 현재 모집단 20,435명 중 2,741명(13.4%)이 이에 해당하며, 최신값과 최빈값의 결과가 다른 사용자는 1,077명이다.

```text
1. 사용자의 리뷰를 submission_time 오름차순 정렬
2. 가장 마지막(최신) 리뷰의 속성을 그 사용자의 대표값으로 확정
3. submission_time이 같으면 review_id 순으로 결정 (재현성)
```

최빈값을 쓰지 않은 이유는 속성 불일치의 주된 원인이 프로필 수정이기 때문이다. 피부 타입은 나이·계절·관리 방식에 따라 실제로 바뀌는데, 최빈값을 쓰면 과거에 오래 머물렀던 상태가 채택된다. 추천은 "지금 이 사용자"에게 하는 것이므로 최신 상태를 기준으로 한다.

> **오프라인 추천 평가에서는 이 규칙을 그대로 쓰면 안 된다.** 최신 리뷰는 holdout target이기도 하므로, 평가용 Profile은 holdout을 제외한 **최신 seed 리뷰** 기준으로 만든다. `persona-schema.md` §5.2를 따른다.

## 7. 정규화 후 허용값 (enum)

아래가 Persona·Affinity·DW가 공유하는 최종 어휘다. `affinity_lift.csv` 실측으로 확인했다.

| attribute | 값 | 개수 |
| --- | --- | ---: |
| `skin_type` | `combination`, `dry`, `normal`, `oily` | 4 |
| `skin_tone` | `fair`, `light`, `medium`, `tan`, `deep` | 5 |
| `hair_color` | `auburn`, `black`, `blonde`, `brown`, `gray`, `red` | 6 |
| `eye_color` | `blue`, `brown`, `gray`, `green`, `hazel` | 5 |

검증: `affinity_lift.csv` 4,000행 = 200상품 × **20세그먼트**(4+5+6+5). 각 세그먼트가 정확히 200행씩 존재하며, 위 20개 외의 값은 나타나지 않는다.

## 8. 모집단과 표본 기준

전처리 기준이 바뀌면 모집단 수치도 바뀌므로 함께 기록한다. 아래 값은 `build_personas.py`와 `persona_sampling_report.json`의 현재 기준이다.

| 항목 | 값 |
| --- | --- |
| 모집단 | 상위 200개 상품 중 **긍정 상품 3개 이상**을 보유한 사용자 20,435명 |
| 긍정 판정 | 같은 상품의 평점 평균이 3.5 이상. 원본 4~5점 기준을 상품 단위 평균에 적용 |
| 추출률 | 10,000 / 20,435 = 48.9% |
| 층화 key | `skin_type`(4) × `skin_tone`(5) × 긍정 상품 수 구간(`3`, `4`, `5-6`, `7+`) = **80층** |
| 배분 | 비례배분 + 최대잔여법 |
| 표본 | 코드 생성 9,900명 + 에이전트 100명 |
| 에이전트 100명 | `skin_type` × `skin_tone` 20셀 × 5명 **균등배분**. 소수 세그먼트 검증용이라 분포가 의도적으로 왜곡되어 있다 |
| 검증 결과 | 모집단 대비 층화 축별 최대 0.03%p 이내. 페르소나당 평균 리뷰 5.5768건 / 평균 상품 4.5659개(10,000명 합산) |
| 난수 seed | 42 고정 |

긍정 상품 3개 하한은 seed/좋아요/정답 역할을 나눌 최소 재료를 확보하기 위해서다. 단순 리뷰 건수가 아니라 같은 상품의 중복 리뷰를 합친 뒤의 긍정 상품 수를 사용한다.

### 8.1 `persona_id` 발급 규칙

두 표본은 ID prefix로 구분되며 겹치지 않는다.

| 표본 | prefix | 범위 | `persona_source` |
| --- | --- | --- | --- |
| 에이전트 100명 | `PA` | `PA00001` ~ `PA00100` | `agent_sample` |
| 코드 생성 9,900명 | `PC` | `PC00001` ~ `PC09900` | `batch_sample` |

`persona_id` prefix만으로 표본을 판별할 수 있지만, **분석에서 prefix를 파싱하지 않는다.** 표본 구분은 `persona_profile.persona_source` 또는 `dim_simulation_run.persona_source`로 한다. prefix 규칙이 바뀌어도 분석이 깨지지 않게 하기 위해서다.

## 9. 실측 검증 결과

문서를 쓰면서 결과 파일로 위 기준이 실제로 지켜졌는지 확인했다. 검증 시점 2026-08-28.

| 확인 항목 | 결과 |
| --- | --- |
| 정규화 후 허용값 위반 | **없음.** 두 파일의 persona-level 속성값이 §7 어휘 안에만 존재 |
| `brunette` / `Grey` / `notSureST` 잔존 | Persona 파일과 `affinity_lift.csv`에는 **없음** (단, §11 예외 1건) |
| `skin_tone` 원본 값(`lightMedium`, `porcelain`, `olive`, `ebony`) 잔존 | 없음. 5버킷으로만 존재 |
| 속성 NULL | 없음. 9,900명·100명 모두 4개 속성이 전부 채워짐 |
| `persona_id` 중복 | 없음. 파일 내 유일하고 두 파일 간 교집합 0 |
| `author_id` 중복 | 두 표본 간 교집합 **0명**. 같은 사람이 양쪽에 들어간 경우 없음 |
| `n_reviews` | 9,900명 min 3 / max 91 / 평균 5.5763, agent min 3 / max 24 / 평균 5.63 |
| `n_products` | 9,900명 min 3 / max 71 / 평균 4.5660, agent min 3 / max 20 / 평균 4.56 |
| `review_bucket` | 긍정 상품 수 기준 `3`, `4`, `5-6`, `7+` 4종만 존재 |
| `stratum` 형식 | `skin_type\|skin_tone\|review_bucket`. 예: `combination\|light\|4` |
| 리뷰의 `group_id` | 563건(agent) 전부 존재하며 NULL 없음. `product_id`와 다른 경우 103건(18.3%) |
| agent 100명 균등배분 | `skin_type` 4종 × 25명, `skin_tone` 5종 × 20명. 20셀 × 5명 성립 |

### 9.1 표본에 존재하지 않는 층

층은 80개로 정의했지만 **9,900명 표본에 실제로 나타나는 층은 79개**다. 비례배분 결과 `dry|deep|7+`에 배정된 인원이 0명이다.

| 항목 | 값 |
| --- | --- |
| 정의된 층 | 80 (4 × 5 × 4) |
| 표본에 존재하는 층 | 79 |
| 빈 층 | `dry\|deep\|7+` |
| 층별 인원 범위 | 최소 1명(`oily\|tan\|7+`, `normal\|deep\|7+`) ~ 최대 1,547명(`combination\|light\|3`) |

층별 집계나 가중치 보정을 할 때 **모든 층에 값이 있다고 가정하면 안 된다.** 빈 층과 1명짜리 층이 실제로 존재한다. 모집단 분포를 그대로 따른 결과이므로 오류가 아니다.

## 10. Persona Schema와의 일치 확인

`persona-schema.md`와 이 문서의 기준이 어긋나는 곳이 없는지 점검한 결과다.

| 확인 항목 | Persona Schema | 전처리 실제 | 일치 |
| --- | --- | --- | --- |
| `skin_type` 허용값 | 4종 원본 유지 | 4종 | O |
| `skin_tone` 허용값 | 5버킷 | 5버킷 | O |
| `hair_color` 허용값 | `brunette`→`brown` 병합 | 6종(`auburn` 포함) | O |
| `eye_color` 허용값 | `Grey`→`gray` 병합 | 5종 | O |
| 대표 속성 선정 | 최신 리뷰 기준 | 최신 리뷰 기준(동일자는 `review_id`) | O |
| nullable 정책 | `eye_color`, `hair_color`만 nullable | 모집단이 4개 전부 채워진 리뷰 기준이므로 실제 결측은 발생하지 않음 | O (스키마가 더 관대) |
| 모집단 | 긍정 상품 3개 이상 | 동일. `MIN_POSITIVE=3` | O |
| `review_bucket` | `3`, `4`, `5-6`, `7+` | 동일 | O |
| `stratum` | `skin_type\|skin_tone\|review_bucket` | 동일(예: `combination\|light\|4`) | O |
| agent/batch 분리 | Dashboard 기본은 `batch_sample` | agent 100명은 균등배분이라 합산 불가 | O |
| segment_type 목록 | `concern` 미포함 | 원천에 고민 필드 없음 | O |

**불일치 없음.** `persona-schema.md` §5.1의 정규화 규칙 표는 이 문서의 §4~§6을 요약한 것이며, 상세 근거와 허용값 전체는 이 문서를 원천으로 본다.

## 11. 알려진 불일치

### 11.1 데이터 불일치 — `products_200.json`의 `hair_color`에 `brunette` 잔존

`batch/ingest/data/README.md`는 `_review_stats.segment_counts`가 정규화 후 값 기준이라고 적고 있으나, **`hair_color`만 병합이 적용되지 않았다.** 200개 상품 중 137개의 `segment_counts.hair_color`에 `brunette` key가 남아 있다.

| 항목 | 값 |
| --- | --- |
| `brunette` key가 있는 상품 | 137 / 200 |
| 합계 | `brown` 219,372 vs `brunette` 6,394 |
| 다른 필드 | `skin_tone` 5버킷 정상, `eye_color` `Grey` 없음 — `hair_color` 단독 문제 |
| `affinity_lift.csv` | 정상. 6종만 존재하고 `brunette` 없음 |
| Persona 파일 | 정상. `brunette` 없음 |

영향 범위는 제한적이지만 명확하다.

| 사용처 | 영향 |
| --- | --- |
| 추천 계산 | **없음.** `affinity_lift.csv`를 쓰므로 정상 |
| Persona 생성 | **없음.** 병합 후 값 사용 |
| DW `dim_persona_segment.population_count` 등 상품 단위 segment 통계 | **있음.** 이 필드를 원천으로 쓰면 `hair_color`에 7번째 segment가 생기고 `brown`이 과소 집계된다 |

대응: `_review_stats.segment_counts.hair_color`를 집계 원천으로 쓸 때는 **읽는 쪽에서 `brunette`를 `brown`에 합산**한다. 재생성 시 `build_products_json.py`에서 병합을 적용하는 것이 근본 해결이며, AI/데이터 담당 확인이 필요하다.

### 11.2 문서 표기 불일치

값 자체가 아니라 **문서 표기**에서 어긋나는 곳이다. 데이터에는 영향이 없지만 읽는 사람이 헷갈릴 수 있어 기록한다.

| 위치 | 내용 | 실제 |
| --- | --- | --- |
| `contracts/recommendation-io-spec.md` §3 | "4,000행 = 200상품 × 21세그먼트(4+5+6+5)" | 4+5+6+5 = **20**세그먼트. 행 수 4,000은 맞다 |
| 과거 수행 기록 | 모집단과 구간이 이전 버전 값일 수 있음 | 현재 기준은 긍정 상품 3개 이상 20,435명, 구간 `3/4/5-6/7+`. 본 문서와 `persona_sampling_report.json`을 사용 |
| `contracts/recommendation-io-spec.md` §3 | missing affinity 기본값 `0.5` | 변환식 기준 `lift=1.0`의 정규화 값은 `0.40`. `persona-schema.md` §11.1 참조. AI 담당 확인 대기 |

## 12. 기준 변경 시 절차

사용자 속성 정규화 기준은 세 곳이 공유하므로 단독 변경이 불가능하다.

| 순서 | 작업 |
| --- | --- |
| 1 | 이 문서의 §4·§7 갱신 |
| 2 | `simulator/personas/build_personas.py`로 `personas_*.json`, `persona_sampling_report.json` 재생성(`seed=42` 유지) |
| 3 | `affinity_lift.csv` 재생성. segment 어휘가 바뀌면 필수 |
| 4 | `products_200.json` 재생성. `_review_stats.segment_counts`가 정규화 어휘를 따라가야 한다(§11.1) |
| 5 | `persona-schema.md` §5.1 정규화 규칙 표 갱신 |
| 6 | `dw-schema.md`의 `dim_persona_segment` / `bridge_persona_segment` 허용값 갱신 |
| 7 | `simulation_run.persona_profile_version` / `affinity_version`을 올려 이전 run과 구분 |
| 8 | 이 문서 §9 실측 검증을 다시 수행해 결과 파일이 기준을 따르는지 확인 |

새 속성(예: `concern`)이 추가되는 경우에도 같은 절차를 따르되, §7 허용값 표에 attribute를 추가하고 `affinity_lift.csv`의 세그먼트 수(현재 20)를 함께 갱신한다. 추가 속성이 `affinity_lift.csv`에 없으면 추천 계산은 §5의 missing 규칙으로 동작하고, DW segment로만 사용된다.

`personas_9900.json`은 52MB이고 내용을 바꾸면 파일 전체가 새 blob으로 저장된다. 잦은 재생성·커밋은 저장소 용량을 빠르게 늘리므로, 기준이 확정된 뒤에만 갱신한다.
