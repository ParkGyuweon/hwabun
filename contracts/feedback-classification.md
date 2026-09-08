# 고객 피드백 분류 계약

> 2026-09-08 · 어휘 `feedback-category-vocab.json` `0.1.0-draft`
> 관련: [`feedback-category-vocab.json`](feedback-category-vocab.json) (실행 계약 — 축·카테고리 목록) · [`feedback-banned-terms.json`](feedback-banned-terms.json) (실행 계약 — 금지어, Jira 202) · `simulator/feedback/classify_feedback.py` (분류기, Jira 201) · `docs/planning/feature-spec-status.md` (브랜드 대시보드 "고객 피드백")

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
| 분류 방식 | **텍스트 자동 분류.** 소비자가 고르는 항목 없음 |
| 분류 단위 | **건당 단일** — 축 1 + 카테고리 1. 배열 아님. 증상이 여러 개면 가장 두드러진 하나 |
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
| `packaging` | 용기·포장 | `pkg_lid_loose` 뚜껑 헐거움·누수 · `pkg_lid_stiff` 뚜껑 뻑뻑함 · `pkg_pump` 펌프 막힘·고장 · `pkg_durability` 재질·내구성 약함 · `pkg_label` 라벨·표기 불분명 · `pkg_visibility` 내용물 확인 어려움 |
| `value` | 용량·가격 | `value_small` 용량 부족 · `value_price` 가격 비쌈 · `value_option` 리필·대용량 요청 |
| `other` | 기타 | `other` |

FE 가 임시로 둔 8종과의 대응: 향→`scent` · 용기→`packaging` · 제형→`texture` ·
효과→`efficacy` · 성분→`efficacy` (자극·트러블) · 사용법→`packaging` (라벨·표기 불분명) ·
가격구성→`value` · 기타→`other`.

`pkg_lid_loose` 와 `pkg_lid_stiff` 는 **의도적으로 갈라 둔 것**이다. 고치는 방향이
정반대라 한 칸에 두면 뚜껑을 헐겁게 고친 뒤 "안 열린다" 고 한 사람에게도 반영
알림이 간다.

## 3. 입력 — FE → 분류기

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `feedback_id` | string | ✔ | 피드백 식별자 |
| `user_id` | string | ✔ | 작성자. 프로필 조인 키 |
| `product_id` | string | ✔ | 대상 상품. `product-registration-spec.md` 의 `product_id` |
| `body` | string | ✔ | 본문. 빈 문자열 불가 |
| `created_at` | string (ISO-8601) | ✔ | 작성 시각 |

본문 외 다른 것은 분류에 쓰지 않는다. 상품명은 분류기가 `product_id` 로 조회해
프롬프트에 넣는다 (펌프가 있는 상품인지 등 용기·포장 판단에 쓴다).

## 4. 출력 — 분류기 → 저장 → 대시보드

입력 필드 전부 + 아래.

| 필드 | 타입 | 설명 |
|---|---|---|
| `axis_id` | string | §2 의 축 id. `other` 포함 |
| `axis` | string | 축 라벨 (표시용) |
| `category_id` | string | §2 의 카테고리 id. `other` 포함 |
| `category` | string | 카테고리 라벨 (표시용) |
| `classifier` | string | 분류 모델 (`gpt-4.1-nano`) |
| `vocab_version` | string | 분류 시점의 어휘 `schema_version` |
| `classified_at` | string (ISO-8601) | 분류 시각 |
| `banned_terms` | string[] | 본문에서 걸린 금지어. 없으면 `[]` |
| `hidden_by_default` | boolean | `banned_terms` 가 비어 있지 않으면 `true`. **대시보드는 이 행의 본문을 접어 두고 "금지어 포함 · 눌러서 보기" 로 보여준다.** 집계에는 그대로 포함한다 |

- `axis_id == "other"` 이면 `category_id` 도 `"other"` 다. 둘이 어긋나는 행은 없다.
- `hidden_by_default` 는 금지어 여부만 뜻한다. 분류 결과(`axis_id`, `category_id`)와 무관하고 집계에서 빼지 않는다 — 욕이 섞여도 "펌프 막힘" 은 사장님이 봐야 할 내용이다.
- 라벨(`axis`, `category`)은 표시용이다. **집계·조인은 id 로 한다.** 라벨은 어휘 개정 때 바뀔 수 있다.
- 대시보드 집계 grain: `(product_id, axis_id, category_id)`. 상품별 보기는 이 grain 에 `product_id` 필터다 — 분류 시점에 상품으로 나누지 않는다 (같은 문제가 상품 수만큼 갈라진다).

## 5. 처리

1. `body` 와 상품명을 프롬프트에 넣고 어휘 목록에서 **딱 하나** 고르게 한다. 건당 호출 1회.
2. 답의 `axis`, `category` 가 어휘 목록에 **글자 그대로** 있는지 검사한다. 하나라도 어긋나면 `other`. 모델이 지어낸 이름을 그대로 받지 않는다.
3. 응답 JSON 파싱은 첫 객체만 떼어 낸다. 3회 실패하면 `other`.
4. **금지어 대조 (LLM 없음).** 본문과 목록 단어를 같은 방식으로 정규화(NFC·소문자·한글/자모/영문/숫자만 남김)한 뒤 부분 일치. 공백·기호를 지우므로 "시 발"·"시.발" 이 잡힌다. 단일 출처는 `feedback-banned-terms.json` — 출처 VaneProject/bad-word-filtering (MIT), 599개. 우리가 보태는 단어는 `added`, 오탐 예외 낱말은 `allow`(대조 전에 본문에서 지운다 — "똥손"), 출처에 있지만 끄는 단어는 `disabled`("18년" — 기간 표현과 구분 불가)에 넣고 이유를 함께 적는다.
   - **못 잡는 것:** 비방(허위 사실·타 브랜드 비교)은 단어로 못 잡는다. 초성·변형 우회는 목록에 있는 형태만 잡힌다.

이름을 짓게 하고 기존 항목과 비교해 붙이는 방식(건당 3회)은 **채택하지 않았다.**
아홉 번 돌리는 동안 파편·과병합·프롬프트 예시 누출·반대 방향 혼입이 번갈아 났고,
비교 프롬프트 한 줄을 넣으면 파편, 빼면 과병합으로 오갔다. 고정 목록에서는 넷이
구조적으로 사라진다. 30건 시험에서 목록 밖 답 0건.

## 6. 어휘 변경 규칙

1. 카테고리 **추가**는 `schema_version` patch 를 올린다 (`0.1.0` → `0.1.1`). 기존 id 는 유지.
2. 카테고리 **이름 변경**은 `label` 만 바꾼다. id 는 바꾸지 않는다.
3. 카테고리 **삭제·병합·id 변경**은 minor 를 올리고, 기존 분류 행의 재분류 여부를 MR 에 적는다.
4. 추가 후보는 `other` 에 쌓인 원문에서 고른다. 한 상품·한 사람의 표현이 아니라 여러 상품에 걸쳐 반복되는 문제만 올린다.

## 7. 아직 아닌 것

- 시연 데이터(`simulator/feedback/data/`)의 `intended_axis`·`generator` 필드는 생성 흔적이라 **이 계약의 필드가 아니다.** 실서비스 행에는 없다.
- `scent_strong` 과 `scent_artificial` 은 한 문장에 같이 나오는 일이 많다("인공적이고 강해서"). 사장님이 고칠 것이 같으면 합칠 후보다. 시연 99건에서 판단하지 않고 실데이터가 쌓이면 본다.
- 분류 정확도는 **사람이 쓴 피드백**으로만 잰다. 시연 데이터는 같은 모델이 축을 알고 쓴 문장이라 성능 근거가 아니다.
