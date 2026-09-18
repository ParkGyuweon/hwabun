# 고객 피드백 분류 계약

> 2026-09-18 (서빙 §6 추가) · 2026-09-08 · 어휘 `feedback-category-vocab.json` `0.2.0-draft` (0.1.0 → 0.2.0: **축은 고객 입력** `axis_id` · 건당 단일 → **다중 라벨** `labels[]`·`primary` · `off_axis_hint` · `other` 는 축이 아니라 카테고리 · 집계 단위 = 언급 수)
> 관련: [`feedback-category-vocab.json`](feedback-category-vocab.json) (실행 계약 — 축·카테고리 목록) · [`feedback-banned-terms.json`](feedback-banned-terms.json) (실행 계약 — 금지어, Jira 202) · `simulator/feedback/classify_feedback.py` (분류기·오프라인 CLI, Jira 201) · `batch/serving/feedback_classify.py` + `recommend_server.py` (서빙 §6, Jira 353) · `docs/planning/feature-spec-status.md` (브랜드 대시보드 "고객 피드백")

소비자가 상품에 대해 **사장님에게 보내는 개선 요청**을 축·카테고리로 자동 분류하는
입력 → 처리 → 출력을 정의한다. 리뷰가 아니다.

| | 리뷰 | 피드백 (이 계약) |
|---|---|---|
| 수신자 | 다른 소비자 | 브랜드 사장님 |
| 공개 | 공개 | 비공개 (사장님만) |
| 별점·극성 | 있음 | **없음** — 전부 불만·개선 요청 |
| 목적 | "살 만한가" | "무엇을 고쳐야 하나" |

## 1. 확정된 것

| 항목 | 값 |
|---|---|
| 분류 방식 | **축은 고객이 고르고(토글), 카테고리는 텍스트에서 자동 분류.** 화면: 왼쪽 축 토글 세로 나열, 오른쪽 그 축의 주관식 칸 하나. 축을 바꾸면 칸이 비고 새 피드백 |
| 분류 단위 | **건당 다중 — `labels[]`, 개수 제한 없음** (각각 축 1 + 카테고리 1; 그 축의 카테고리 수가 자연스러운 상한). 문장에 **실제로 적힌** 불만만 붙인다. `primary` 는 그중 가장 두드러진 하나. `other` 는 단독으로만. **(0.2.0 에서 단일 → 다중으로 바뀜.** 사람 정답 50건 채점에서 카테고리 불일치 15건 중 11건이 "용량 적은데 가격 비싸서" 처럼 한 문장에 두 불만이 함께 적힌 것이었다 — 사용자는 우리 축을 모르고 쓴다. 하나만 고르게 하면 불만이 버려진다) |
| 극성 | **없음.** 피드백 자체가 개선 요청이라 전부 부정으로 본다. 칭찬은 리뷰가 받는다 |
| 익명 | **아님.** 사장님 화면에 작성자 프로필(피부 타입·톤 등)을 보여도 된다. `user_id` 로 조인 |
| 어휘 | **고정 목록.** 분류기는 `feedback-category-vocab.json` 에서만 고른다. 목록에 없는 답은 `other` |
| 새 카테고리 | 분류기가 만들지 않는다. `other` 누적분을 훑어 **사람이** 어휘에 추가하고 `schema_version` 을 올린다 |
| 범위 | 브랜드가 **제품을 고쳐서** 해결할 수 있는 축만. 배송·CS 는 플랫폼 문제라 제외 |
| 금지어 | **입력을 막지 않는다.** `feedback-banned-terms.json` 에 걸리면 `hidden_by_default=true` 로 표시만 하고 분류는 그대로. 사장님 화면은 그 행을 접어 두고 눌러야 본문을 보여준다 |

## 2. 축·카테고리

단일 출처는 `feedback-category-vocab.json` 이다. 아래는 읽기용 요약이며 충돌하면 JSON 이 우선한다.

| 축 `axis_id` | 라벨 | 카테고리 `category_id` (라벨) |
|---|---|---|
| `efficacy` | 효능 | `efficacy_low` 효과 미흡 · `efficacy_irritation` 자극·트러블 · `efficacy_dryness` 건조·당김 |
| `texture` | 사용감 | `texture_sticky` 끈적임 · `texture_runny` 묽음·흘러내림 · `texture_slow` 흡수 느림 · `texture_whitecast` 백탁 · `texture_heavy` 무겁고 답답함 |
| `scent` | 향 | `scent_strong` 향이 강함 · `scent_artificial` 향이 인공적 · `scent_weak` 향이 약함 |
| `packaging` | 용기·포장 | `pkg_lid_loose` 뚜껑 헐거움·누수 · `pkg_lid_stiff` 뚜껑 뻑뻑함 · `pkg_pump` 펌프 막힘·고장·토출량 · `pkg_durability` 재질·내구성 약함 · `pkg_label` 라벨·표기 불분명 · `pkg_visibility` 내용물 확인 어려움 |
| `value` | 용량·가격 | `value_small` 용량 부족 · `value_price` 가격 비쌈 · `value_option` 리필·대용량 요청 |
| (모든 축) | — | `other` 기타 — **축이 아니라 카테고리.** 입력 축 안에서 목록에 없는 불만 |

FE 가 임시로 둔 8종과의 대응: 향→`scent` · 용기→`packaging` · 제형→`texture` ·
효과→`efficacy` · 성분→`efficacy` (자극·트러블) · 사용법→`packaging` (라벨·표기 불분명) ·
가격구성→`value` · 기타→`other`.

`pkg_lid_loose` 와 `pkg_lid_stiff` 는 **의도적으로 갈라 둔 것**이다. 고치는 방향이
정반대라 한 칸에 두면 뚜껑을 헐겁게 고친 뒤 "안 열린다" 고 한 사람에게도 반영
알림이 간다.

**라벨 지침 (분류기와 사람 정답이 같이 따른다, 2026-09-08)**

| 문장 | 라벨 |
|---|---|
| "가격 대비 아쉽다" · "용량이 적은데 가격이 부담" | `value_small` **+** `value_price` 둘 다 — 용량을 늘리든 값을 내리든 사장님의 대응은 같은 가성비 축이다 |
| "향이 은은하지 않다" · "향이 오래 남는다" | `scent_strong` (약함이 아니다) |
| "대용량이 있었으면" · "리필이 있었으면" | `value_option` — 용량 부족과 함께 적혀 있으면 둘 다 |
| "인공적이고 강하다" | `scent_strong` + `scent_artificial` 둘 다 |
| "뚜껑이 자꾸 열린다 · 샌다" / "뚜껑이 안 열린다 · 뻑뻑하다" | `pkg_lid_loose` / `pkg_lid_stiff` — 방향이 반대 |
| 고객이 고른 축과 다른 축 얘기 | **그 축 안에서만 분류한다.** 다른 축 라벨을 붙이지 않는다 — 칸을 고른 것은 고객이다 |

## 3. 입력 — FE → 분류기

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `feedback_id` | string | ✔ | 피드백 식별자 |
| **`axis_id`** | string | ✔ | **고객이 고른 축** (§2 의 5개 중 하나). 화면은 왼쪽에 축 토글, 오른쪽에 그 축의 주관식 칸 — 축을 바꾸면 칸이 비고 새 피드백이 된다. 한 고객이 상품 하나에 축마다 한 건씩 여러 건 보낼 수 있다 |
| `user_id` | string | ✔ | 작성자. 프로필 조인 키 |
| `product_id` | string | ✔ | 대상 상품. `product-registration-spec.md` 의 `product_id` |
| `body` | string | ✔ | 본문. 빈 문자열 불가 |
| `created_at` | string (ISO-8601) | ✔ | 작성 시각 |

분류기는 `axis_id` 와 `body` 만 본다. **축은 다시 판단하지 않는다** — 고객이 고른 칸을
존중한다.

**프롬프트 규칙은 축별로 넣는다.** 그 축을 분류할 때 그 축의 지침만 들어간다 — 모든 축에
향·가격 규칙을 같이 넣었을 때 효능 3건이 `기타`로 빠졌다(2026-09-08). 지시문은 한국어가 기본이고
영어 지시문(`--lang en`)은 같은 50건에서 F1 93.6 vs 94.3 으로 차이가 없어 비교용으로만 둔다. 상품명은 `product_id` 로 조회해 프롬프트에 넣는다 (펌프가 있는 상품인지 등).

> **왜 축을 고객이 고르나 (0.2.0).** 0.1.0 은 자유 문장에서 축까지 추론했다. 사람 정답
> 50건에서 축 일치 96% 였지만, 화면 설계가 "축 토글 + 축별 주관식" 으로 정해지면서 축은
> 입력이 됐다. 분류기가 할 일이 카테고리만으로 줄고 축 오류가 구조적으로 사라진다.

## 4. 출력 — 분류기 → 저장 → 대시보드

입력 필드 전부 + 아래.

| 필드 | 타입 | 설명 |
|---|---|---|
| **`labels`** | array | **1개 이상, 상한 없음.** 각 원소 `{axis_id, axis, category_id, category}` — **`axis_id` 는 전부 입력의 축과 같다.** 문장에 실제로 적힌 불만만. 그 축 안에서 못 고르면 `{axis_id: 입력 축, category_id: "other"}` 하나 |
| **`primary`** | object | `labels[0]` — 가장 두드러진 하나. 단일 태그가 필요한 곳(정렬·대표 표시)은 이것을 쓴다 |
| `off_axis_hint` | string \| null | **참고용 · 보장 없음.** 문장이 다른 축 얘기로 보이면 그 축 id 를 줄 수 있지만 현재 모델은 거의 안 낸다(사람 정답 50건 중 다른 축 라벨 4개, 힌트 0건). **화면은 무시한다.** 고객이 고른 칸에 다른 얘기를 쓴 것은 고객 책임이고 분류기는 입력 축 안에서만 한다 (2026-09-08 결정) |
| `axis_id` / `axis` / `category_id` / `category` | string | **= `primary` 의 값.** 0.1.0 소비자 호환용. 새 코드는 `labels` 를 읽는다 |
| `classifier` | string | 분류 모델 (`gpt-4.1-nano`) |
| `vocab_version` | string | 분류 시점의 어휘 `schema_version` |
| `classified_at` | string (ISO-8601) | 분류 시각 |
| `banned_terms` | string[] | 본문에서 걸린 금지어. 없으면 `[]` |
| `hidden_by_default` | boolean | `banned_terms` 가 비어 있지 않으면 `true`. **대시보드는 이 행의 본문을 접어 두고 "금지어 포함 · 눌러서 보기" 로 보여준다.** 집계에는 그대로 포함한다 |

- **`other` 는 0.2.0 부터 축이 아니라 카테고리다** — 입력 축 안에서 목록에 없는 불만. `axis_id` 는 항상 고객이 고른 5개 중 하나. `other` 는 `labels` 에 단독으로만 온다.
- **집계 단위는 "언급 수"다.** 피드백 하나가 `labels` 를 둘 가지면 두 칸에 각 1씩 센다. 카테고리별 합은 피드백 수를 **넘을 수 있다** — 화면 문구는 "펌프 막힘 13건"이 아니라 **"펌프 막힘 언급 13"** 이다. 피드백 수가 필요하면 `feedback_id` 를 distinct 로 센다.
- `labels` 안에 같은 `(axis_id, category_id)` 가 두 번 오지 않는다.
- `hidden_by_default` 는 금지어 여부만 뜻한다. 분류 결과(`axis_id`, `category_id`)와 무관하고 집계에서 빼지 않는다 — 욕이 섞여도 "펌프 막힘" 은 사장님이 봐야 할 내용이다.
- 라벨(`axis`, `category`)은 표시용이다. **집계·조인은 id 로 한다.** 라벨은 어휘 개정 때 바뀔 수 있다.
- 대시보드 집계 grain: `(product_id, axis_id, category_id)`. 상품별 보기는 이 grain 에 `product_id` 필터다 — 분류 시점에 상품으로 나누지 않는다 (같은 문제가 상품 수만큼 갈라진다).

## 5. 처리

1. `axis_id` 의 카테고리 목록만 프롬프트에 넣고, `body` 에서 **적힌 불만을 전부**(개수 제한 없음), 두드러진 순서로 고르게 한다. 같은 응답에서 `off_axis` (다른 축 얘기로 보이면 그 축) 를 받는다. 건당 호출 1회. (`classify_in_axis`)
2. 각 카테고리가 **그 축의 목록에 글자 그대로** 있는지 검사한다. 어긋나면 버린다. 중복은 하나로. 살아남은 것이 없으면 `other` 하나. 모델이 지어낸 이름을 그대로 받지 않는다. `off_axis` 는 5개 축 이름 중 하나이고 입력 축과 다를 때만 `off_axis_hint` 로 남긴다.
3. 응답 JSON 파싱은 첫 객체만 떼어 낸다. 3회 실패하면 `other`.
3-1. `primary = labels[0]`. `axis_id` 등 단일 필드는 `primary` 를 복사한다.
4. **금지어 대조 (LLM 없음).** 본문과 목록 단어를 같은 방식으로 정규화(NFC·소문자·한글/자모/영문/숫자만 남김)한 뒤 부분 일치. 공백·기호를 지우므로 "시 발"·"시.발" 이 잡힌다. 단일 출처는 `feedback-banned-terms.json` — 출처 VaneProject/bad-word-filtering (MIT), 599개. 우리가 보태는 단어는 `added`, 오탐 예외 낱말은 `allow`(대조 전에 본문에서 지운다 — "똥손"), 출처에 있지만 끄는 단어는 `disabled`("18년" — 기간 표현과 구분 불가)에 넣고 이유를 함께 적는다.
   - **못 잡는 것:** 비방(허위 사실·타 브랜드 비교)은 단어로 못 잡는다. 초성·변형 우회는 목록에 있는 형태만 잡힌다.

이름을 짓게 하고 기존 항목과 비교해 붙이는 방식(건당 3회)은 **채택하지 않았다.**
아홉 번 돌리는 동안 파편·과병합·프롬프트 예시 누출·반대 방향 혼입이 번갈아 났고,
비교 프롬프트 한 줄을 넣으면 파편, 빼면 과병합으로 오갔다. 고정 목록에서는 넷이
구조적으로 사라진다. 30건 시험에서 목록 밖 답 0건.

## 6. 서빙 — 백엔드 배치가 부르는 엔드포인트

분류기는 추천 서버(8300)에 실려 있다. **내부망 전용**이다 — nginx 가 `/api/feedback/*` 을 밖으로
열지 않는다. 프론트는 이 엔드포인트를 직접 부르지 않는다. GMS 키를 브라우저에 내보내지 않기
위해서다 (처방과 같은 이유, `prescription-api-spec.md` §1).

### 6.1 `POST /api/feedback/classify`

```json
{"items": [{"feedback_id": "fb_0001", "product_id": "P427406",
            "axis_id": "texture", "body": "펌프가 자꾸 막혀요"}]}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `feedback_id` | ● | 응답을 되짚는 열쇠. 서버는 뜻을 보지 않고 그대로 돌려준다 |
| `axis_id` | ● | **고객이 고른 축**. 서버가 다시 고르지 않는다 (§3) |
| `body` | ● | 주관식 원문 |
| `product_id` | | 상품명을 프롬프트 참고로 넣기 위한 값(펌프가 있는 제형인지 등). 카탈로그에 없으면 빈 이름으로 돈다 — **분류가 상품으로 갈라지지 않는다** (§4) |

응답:

```json
{"results": [{"feedback_id": "fb_0001", "status": "COMPLETED",
              "labels": [{"axis_id": "texture", "category_id": "pump_clog"}],
              "primary_category_id": "pump_clog", "off_axis_hint": null,
              "banned_terms": [], "hidden_by_default": false,
              "classifier": "gpt-4.1-nano", "vocab_version": "0.2.0"}]}
```

| 필드 | 설명 |
|---|---|
| `status` | `COMPLETED` 또는 `FAILED`. **건별**이다 |
| `labels[]` | `(axis_id, category_id)` 쌍. 순서는 두드러진 순서 (§5-1) |
| `primary_category_id` | `labels[0].category_id`. `FAILED` 면 `null` |
| `off_axis_hint` | 다른 축 얘기로 보이면 그 축의 **id**. 재분류는 하지 않는다 |
| `banned_terms[]` · `hidden_by_default` | 금지어 대조 결과 (§5-4). LLM 과 무관 |
| `classifier` · `vocab_version` | 어느 모델·어느 어휘로 붙었는지. 어휘 개정 뒤 재분류 대상을 고르는 값이다 (§7) |
| `error` | `FAILED` 일 때만. 예) `unknown axis_id: 'skin'` · `empty body` |

**한 건이 실패해도 나머지는 돌아온다.** 배치 200건 중 3건이 죽으면 197건은 `COMPLETED` 로 온다 —
`status` 를 건별로 보고 `FAILED` 만 다음 배치에서 다시 넣는다. `items` 가 비면 `200 {"results": []}` 다.

**서버는 DB 를 쓰지 않는다.** 라벨만 돌려주고 저장은 테이블 주인인 `shop_backend` 가 한다
(2026-09-18 합의). 분류 결과를 어느 컬럼에 넣는지는 백엔드 몫이다.

### 6.2 스위치

| | |
|---|---|
| `GET /api/feedback/classify/llm` | `{enabled, key_present, model, llm_calls, items, failed, refused_off}` |
| `POST /api/feedback/classify/llm` | `{"enabled": false}` 로 끈다. 재배포 없이 |
| `FEEDBACK_CLASSIFY_LLM` | 기동 기본값. `off`·`0`·`false`·`no` 만 끔으로 읽는다. **기본은 on** |

꺼져 있거나 GMS 키가 없으면 `503 {"code": "LLM_UNAVAILABLE"}` 다. 처방(`PRESCRIPTION_LLM`)과
스위치를 나눈 이유: 처방은 비용 때문에 시연 직전에만 켜지만, 분류는 매일 새벽 배치가 부른다.

### 6.3 호출 시점

| | |
|---|---|
| 매일 1회 | `SHOP_FEEDBACK_CLASSIFY_CRON` (기본 `0 0 6 * * *` — 06:00). `PENDING`·`FAILED` 를 집어서 부른다 |
| 사장님 "즉시 갱신" | 버튼을 누르면 그때 바로 한 번 더. 피드백이 들어올 때마다 부르지 않는다 |
| 한 번에 | `SHOP_FEEDBACK_CLASSIFY_BATCH_SIZE` (기본 200) |
| 응답 대기 | `RECOMMEND_FEEDBACK_TIMEOUT_MS` (기본 30,000) |

건당 LLM 1회다 (§5-1). 하루에 여러 번 돌리거나 피드백마다 부르면 GMS 비용이 건수에 비례해 늘어난다.

## 7. 어휘 변경 규칙

1. 카테고리 **추가**는 `schema_version` patch 를 올린다 (`0.1.0` → `0.1.1`). 기존 id 는 유지.
2. 카테고리 **이름 변경**은 `label` 만 바꾼다. id 는 바꾸지 않는다.
3. 카테고리 **삭제·병합·id 변경**은 minor 를 올리고, 기존 분류 행의 재분류 여부를 MR 에 적는다.
4. 추가 후보는 `other` 에 쌓인 원문에서 고른다. 한 상품·한 사람의 표현이 아니라 여러 상품에 걸쳐 반복되는 문제만 올린다.

## 8. 아직 아닌 것

- 시연 데이터(`simulator/feedback/data/`)의 `intended_axis` 는 생성 때 지시한 축이고 0.2.0 부터 **`axis_id` 입력 자리에 그대로 쓴다** (고객이 고른 축에 해당). `generator` 는 생성 흔적이라 계약 필드가 아니다.
- `scent_strong` 과 `scent_artificial` 은 한 문장에 같이 나오는 일이 많다("인공적이고 강해서"). 사장님이 고칠 것이 같으면 합칠 후보다. 시연 99건에서 판단하지 않고 실데이터가 쌓이면 본다.
- 분류 정확도는 **사람이 붙인 정답**으로만 잰다. 시연 데이터의 `intended_axis` 는 같은 모델이 축을 알고 쓴 문장이라 성능 근거가 아니다. 정답 50건과 채점기는 `Research/eval/feedback_gold_50.tsv` · `eval_feedback_gold.py` (다중 라벨: 집합 정밀도·재현율).
- 단일 라벨(0.1.0) 채점: 축 96% · 카테고리 71% (49건). 불일치 15건 중 11건이 복합 문장 — 0.2.0 으로 바꾼 이유.
- **0.2.0 채점 (2026-09-08, 같은 50건 재라벨):** 입력 축 안 도달 가능 정답 49건 기준 **정밀도 93.7 · 재현율 94.9 · F1 94.3 · 라벨 집합 완전 일치 88%**. 남은 불일치 6건 — 다른 축 라벨 3(고객 책임) · "은은하지 않다"→약함 1(nano 한계) · 흡수 느림 누락 1 · 뚜껑 "고장" 방향 애매 1. 50건이라 ±10%p 는 잡음.
- 영어 지시문(`--lang en`)은 F1 93.6 으로 차이 없음 — 못 알아듣는 건 언어가 아니라 모델. 비교용 옵션으로만 둔다.
