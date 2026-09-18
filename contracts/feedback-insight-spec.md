# 고객 목소리 AI 요약 API (백엔드 · 추천 서비스 ↔ 프론트)

> 상태: **초안 0.1 (2026-09-18, 프론트 제안)** — 서버 구현 전. 백엔드·AI 회신에 따라 이름과 모양을 고친다.
> 프론트 참조 구현: `frontend/src/dashboard/lib/insightApi.ts` · 화면 `frontend/src/dashboard/screens/InsightCard.tsx` · 타입 `frontend/src/types/insight.ts`.

## 1. 흐름과 역할 (09-18 합의)

```
쇼핑몰 ──POST /api/feedback · /api/reviews──▶ 쇼핑몰 백엔드 DB (feedback.body · review.body)
                                                 │  원문을 추천 서비스로 넘긴다 (컨테이너 내부 recommend:8300)
                                                 ▼
                                            추천 서비스 (LLM 취합 · 요약)
                                                 │  결과를 백엔드가 저장
                                                 ▼
대시보드 ◀──GET /api/seller/insights──────── 쇼핑몰 백엔드
```

| 하는 일 | 누가 |
|---|---|
| 원문 저장 | **백엔드.** 이미 된다 (`FeedbackController` · `POST /api/reviews`) |
| 원문 → 추천 서비스 전달, 결과 저장, 대시보드 응답 | **백엔드** |
| 텍스트 취합 · 요약 · 근거 문장 고르기 | **추천 서비스 (LLM)** |
| 갱신 시점 | **매일 06:00 KST 한 번** + 사장님이 "즉시 반영" 을 누른 때 |
| 프론트 | 읽기 · 버튼 · 기다리는 표시. **요약을 만들지 않는다.** 규칙 표 폴백도 없다 |

이벤트 스키마·Kafka·DW 는 건드리지 않는다. 원문은 DB 에서 읽는다.

## 2. 읽기 — `GET /api/seller/insights?brandId=&productId=`

SELLER 권한 · 브랜드 소유 검사 (`/api/seller/feedback` 와 같은 규칙). `productId` 를 빼면 **브랜드 전체** 요약.

| 상황 | 응답 |
|---|---|
| 요약 있음 | `200` + 아래 JSON |
| 아직 만든 적 없음 (글이 없거나 첫 06:00 전) | `204` (본문 없음) |
| 권한 없음 | `401` / `403` |

```json
{
  "brandId": "b_ssafy_beauty",
  "productId": null,
  "generatedAt": "2026-09-18T06:00:12+09:00",
  "source": "scheduled",
  "inputCount": { "feedback": 41, "review": 118 },
  "newSince": 7,
  "summary": {
    "topComplaints": [
      { "text": "발림이 무겁고 끈적인다", "count": 14, "axisId": "texture" },
      { "text": "향이 강하다", "count": 9, "axisId": "scent" },
      { "text": "용량 대비 비싸다", "count": 6, "axisId": "value" }
    ],
    "preBuyDropReasons": [
      { "text": "가격이 부담돼서 안 샀다", "count": 5 },
      { "text": "향이 강할 것 같아 망설였다", "count": 3 }
    ],
    "priceMentionRate": 0.18,
    "actions": [
      "끈적임 언급이 가장 많습니다. 제형 개선 여부를 처방팀과 확인하세요.",
      "가격 언급이 5건 중 1건입니다. 용량·구성 안내를 상세페이지 위쪽에 두세요."
    ]
  },
  "evidence": [
    { "type": "feedback", "id": "fb_01H…", "quote": "발림이 무거워서 낮에 쓰기엔 끈적여요", "productId": "P421996" },
    { "type": "review", "id": "rv_…", "quote": "향이 생각보다 세서 놀랐어요", "productId": "P421996" }
  ],
  "model": "gpt-4.1-mini"
}
```

| 필드 | 뜻 | 규칙 |
|---|---|---|
| `source` | `scheduled` (06:00) · `manual` (버튼) | |
| `inputCount` | 요약에 넣은 글 수 | 금지어로 숨긴 글도 센다 (본문은 넣되 근거로는 안 고른다) |
| `newSince` | `generatedAt` 이후 새로 쌓인 글 수 | 화면이 "이후 새 의견 N건" 으로 적고, 버튼을 누를 이유가 된다 |
| `topComplaints` | 많이 나온 불만, 많은 순 | **최대 3.** `axisId` 는 피드백 축(`efficacy·texture·scent·packaging·value`), 리뷰에서만 나온 것은 null |
| `preBuyDropReasons` | **비구매자 피드백**에서만 뽑은 이유 | 구매자 글은 넣지 않는다. 비구매자 글이 없으면 빈 배열 |
| `priceMentionRate` | 가격을 말한 글 / 전체 글 (0~1) | 글이 없으면 null |
| `actions` | 지금 할 일. 짧은 명령문 | **최대 3.** 문장 규칙은 §4 |
| `evidence` | 요약의 근거가 된 원문 한 문장씩 | `id` 로 원문과 잇는다. 금지어 걸린 글은 넣지 않는다 |

## 3. 즉시 반영 — `POST /api/seller/insights/refresh?brandId=&productId=`

그 시점까지 쌓인 리뷰·피드백으로 다시 만든다. 완성까지 기다릴지, 접수만 하고 폴링할지는 서버가 고른다. **프론트는 둘 다 받는다.**

| 응답 | 뜻 | 프론트 |
|---|---|---|
| `200` + §2 JSON | 동기로 끝냄 | 바로 바꿔 그린다 |
| `202 {"jobId": "…"}` | 접수. 뒤에서 만든다 | 2초마다 §3.1 을 묻는다. 60초 넘으면 포기하고 §2 를 다시 읽는다 |
| `409 {"reason": "nothing_new"}` | 마지막 정리 뒤 새 글이 없다 | "새 의견이 없어 그대로 둡니다" |
| `429 {"reason": "too_soon", "retryAfterSec": 300}` | 연타. 브랜드당 N분 1회 | 그 시간만큼 버튼을 잠근다. `Retry-After` 헤더도 읽는다 |
| `503` | LLM 못 부름 | "정리 서버에 닿지 못했습니다. 06:00 자동 정리는 그대로" |

연타 규칙(N분)은 서버가 정한다. 프론트 제안: **브랜드당 5분에 1회.**

### 3.1 `GET /api/seller/insights/refresh/{jobId}`

```json
{ "status": "running" }
{ "status": "done", "insight": { …§2 JSON… } }
{ "status": "failed", "reason": "llm_unavailable" }
```

## 4. 문장 규칙 (처방 API 와 같다)

`docs/dashboard/ai-insight-rules.md` §4-3 을 따른다.

- **효능을 단정하지 않는다.** "보습이 안 된다" 가 아니라 "보습이 안 된다는 말이 N건".
- **원인을 단정하지 않는다.** "~일 가능성" · "~라는 의견".
- 숫자는 입력에 있는 것만. 글 수·비율 외의 숫자를 만들지 않는다.
- 금지어(`contracts/feedback-banned-terms.json` · `cosmetic-claim-banned-terms.json`)는 요약 문장에도 적용한다.
- 원문 인용(`evidence.quote`)은 한 문장, 개인 식별 정보 없이.

## 5. 결정된 것 (AI 파트 회신 09-18)

| # | 내용 | 결정 |
|---|---|---|
| 저장·조회 | 어디에 두나 | **백엔드 DB.** 브랜드×상품×기간 조회는 마트 API 가 이미 하는 일. 서빙 서버는 생성만 하고 상태를 갖지 않는다 |
| 생성 | LLM 취합 잡 | **서빙 서버.** 처방 API 의 GMS 클라이언트·스위치·금지어 검증·JSON 스키마 강제를 그대로 쓴다 |
| 빈도 | 언제 만드나 | **06:00 일 1회 + 즉시 반영 버튼만.** "N건 넘으면 즉시" 는 비용 예측이 안 돼 하지 않는다 |
| 분류 | `feedback_classification` PENDING 채우기 | 서빙 서버가 라벨만 돌려주고(`POST /api/feedback/classify`) **DB 는 백엔드가 쓴다.** 별도 문서 |
| 화면 해설 | 탭 지표의 자연어 풀이 | **새 엔드포인트 `/api/insight/explain`.** 처방 API 확장은 하지 않는다. 이 문서 범위 밖 |
| 이벤트 | `feedback_submit` · `review_submit` | **만들지 않는다.** `log.ts`·이벤트 계약에도 없다. `feature-spec-status.md` 항목은 정리한다 |

## 6. 아직 정해야 할 것 (백엔드 회신 대기)

1. 원문 전달 시점: 저장 즉시인지 06:00·버튼 때 한꺼번인지. "버튼 눌렀는데 방금 쓴 글이 빠졌다" 가 생기는지 알아야 한다.
2. `refresh` 를 동기(200)로 갈지 비동기(202)로 갈지. 프론트는 둘 다 받는다.
3. 백엔드 테이블 이름·컬럼 (제안 `feedback_insight`: brand_id · product_id NULL · generated_at · source · summary_json · evidence_json · model).
4. 비구매자 피드백 403 해제 (`S15P21A306-fe-feedback-open` MR !335). 풀리기 전엔 `preBuyDropReasons` 가 항상 빈 배열이다.
