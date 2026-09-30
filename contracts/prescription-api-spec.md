# 대시보드 처방 문장 API (AI ↔ 프론트)

> 상태: **참조 구현, 규격 v0.3 정합 (2026-09-09, Jira 220 → 225)** — `batch/serving/recommend_server.py` `POST /api/prescription`, 본체 `batch/serving/prescription.py`.
> 프롬프트 규격의 정본은 프론트 문서 [`docs/dashboard/action-prescription-prompt.md`](../docs/dashboard/action-prescription-prompt.md) **v0.3** 이고,
> 이 문서는 **그 규격을 서버가 어떻게 받고 무엇을 돌려주는가**만 적는다. 규격 §5·§6 프롬프트는 서버가 그대로 쓴다.

## 1. 역할

| 하는 일 | 누가 |
|---|---|
| 판정 `up · fix · keep` · **옮길 위치 `insert_after`** | **프론트** (`verbOf()` · `insertAfter()`, 규칙 고정). 서버는 바꾸지 않는다 |
| 문장 `how · basis · verify` | **서버 (LLM)** — gpt-4.1-mini · temperature 0 · `response_format=json_schema strict` |
| 자동 거부 11개 (규격 §7) | **서버.** 거부되면 `prescription: null` + `rejected_by[]`. 실증 필요 표현은 거부 대신 `needs_evidence[]` |
| 저장·재사용 | **서버.** `input_hash` 가 같으면 재생성하지 않는다 (`cached: true`). 생성 주기 일 1회 권고 |

## 2. 요청

```
POST /api/prescription?force=false
```

본문은 규격 §3 그대로 (`brand · target · page_context · cross_screen_signals`). 비율·배수는 **`_text` 문자열**(`view_rate_text: "34.0%"`, `cart_lift_text: "2.1배"`), `dwell_sec` 은 초.
`target.insert_after` 는 `up` 일 때 프론트가 계산한 칸 이름(순서 표에 있어야 함), 없으면 "맨 위". `fix` 는 넣지 않는다.
`brand.functional_certified: true` 면 기능성 심사 품목으로 보고 `functional_only` 낱말을 허용한다 (기본 false).
v0.1 수치 필드(`view_rate · cart_lift · avg_dwell_ms`)도 받아 `_text` 가 없을 때만 문자열로 바꿔 쓴다.

| 입력 규칙 (§3) | 서버 처리 (LLM 을 부르지 않고 200) |
|---|---|
| `verb = keep` | `rejected_by: ["verb_keep"]` |
| 표본 200 이상 신호가 2개 미만 / 6개 초과 | `signals_lt_2` / `signals_gt_6` |
| `from` 이 여섯 화면 밖 | `signal_from_unknown` |
| `insert_after` 가 순서 표에 없음 | `insert_after_not_in_blocks` |
| `force=true` | 헤더 `X-Admin-Token` 이 서버 env `SERVING_ADMIN_TOKEN` 과 같을 때만 저장본을 무시하고 다시 생성. 아니면 무시. 모델은 요청으로 고르지 않는다 (env `PRESCRIPTION_MODEL`, 공개 자리 과금 방어) |

`from` 허용 화면 여섯: `무엇을 보고 사나 · 누가 사나 · 고객이 찾는 성분 · 상품마다 어디서 멈추나 · 고객이 고쳐 달라는 것 · 막히는 곳`.

## 3. 응답 (200) — 프론트 `PrescriptionEnvelope`

```json
{
  "content_kind": "clinical_claim",
  "verb": "up",
  "brand": "SSAFY Beauty",
  "prescription": {
    "how": "임상 결과를 성분 목록 바로 아래로 옮기세요.",
    "basis": [
      { "from": "무엇을 보고 사나", "text": "상세페이지를 연 사람 중 여기까지 본 비율: 34.0%" },
      { "from": "누가 사나", "text": "지성 고객이 가장 오래 보는 글이 임상 결과입니다. 이 고객군 체류의 29.0%입니다." },
      { "from": "막히는 곳", "text": "성분 목록 구간에서 위로 다시 올려 읽은 기록이 388건입니다." }
    ],
    "verify": "34.0% → 44.0%. 임상 결과를 옮긴 후 상세페이지를 연 사람 중 임상 결과를 보는 비율이 줄면 원래 위치로 되돌리세요."
  },
  "rejected_by": [],
  "needs_evidence": [],
  "model": "gpt-4.1-mini",
  "prompt_version": "0.4",
  "input_hash": "sha256:6a5bc60d…",
  "generated_at": "2026-09-09T13:19:53",
  "cached": false
}
```

거부됐을 때는 `prescription: null`, `rejected_by` 에 아래 코드, `raw` 에 모델 원문(디버그용). `needs_evidence` 가 비어 있지 않으면 프론트가 "실증자료 필요" 꼬리표를 붙인다 (처방은 그대로).

| `rejected_by` 코드 | 규격 §7 | 뜻 |
|---|---|---|
| `shape` | — | `{how, basis[{from,text}], verify}` 모양이 아님 |
| `banned_term:…` | 1 | `contracts/cosmetic-claim-banned-terms.json` `banned` 낱말 (+ 규격 §5 웹 분석 용어) |
| `functional_only:…` | 2 | `functional_only` 낱말인데 `brand.functional_certified` 가 아님 |
| (꼬리표) `needs_evidence` | 3 | 거부 아님. 봉투 `needs_evidence[]` |
| `no_such_number:…` | 4 | how·basis 의 숫자가 입력 JSON 에 없음 (0.34↔34.0 변형, 표 줄 수 1~5 는 허용) |
| `unsupported_comparison:…` | 5 | "평균보다 높/낮·좋다·나쁘다·충분" 류가 입력 신호 문장에 없음 |
| `slot_mismatch:…` | 6 | `up` 인데 how 첫 문장에 `insert_after` 칸 이름이 없거나 다른 칸 이름이 있음. `insert_after` 가 null 이면 "맨 위" 필요 |
| `direction_mismatch:…` | 7 | `up` 인데 빼기·지우기·삭제·없애기 지시 또는 "아래로" ("X **바로** 아래로" 는 위치 지정이라 허용). v0.4 부터 **어간으로 잡는다** — 어미가 권유형이라 "빼 주시면 좋겠습니다"·"지우시는 게 좋겠습니다" 도 걸린다 |
| `basis_from` | 8 | 2~3개가 아니거나 여섯 화면 밖 (대괄호·따옴표는 벗겨 본다) |
| `basis_diversity` | 9 | 모두 같은 화면 |
| `verify_range:…` | 10 | "현재값 → 목표값" 화살표 없음(`no_arrow`) / 목표가 현재 이하 또는 1.6배 초과 |
| `em_dash` | 11 | `—` 또는 `–` |
| `how_vague` | (fix) | `fix` 인데 how 에 형식·항목 지시가 없음 |

오류: `503 LLM_UNAVAILABLE` — `GMS_KEY` 없음 (추천은 영향 없음, keep 등 입력 규칙 응답은 키 없이도 200). `422` — 본문이 §3 모양이 아님.

## 4. 금지 표현 계약

`contracts/cosmetic-claim-banned-terms.json` (프론트 작성, MR !171). 문장과 낱말을 NFC·공백 제거·한글/영문/숫자만 남겨 부분 일치.
`allow` 항은 대조 전에 지운다. 파일이 없으면 규격 §5 의 열 낱말 + 웹 분석 용어만으로 건다.

## 5. 실측 (같은 입력 5회, 규격 §10-1)

| 판 | 결과 |
|---|---|
| v0.1 그대로 (nano·mini × 온도 0·1, 20회) | basis 20/20 문자열 · `up` 인데 아래 칸 · 억지 "1개" · verify 화살표 미준수 |
| v0.3 (mini · 온도 0 · 스키마 강제) | 5/5 같은 지시 · 거부 0/5. nano 는 "위쪽으로" 만 써 5/5 거부 → 쓰지 않음 |
| v0.3 서버 실호출 (2026-09-09) | `how` "임상 결과를 성분 목록 바로 아래로 옮기세요." · basis 3개(세 화면) · verify 34.0% → 44.0% · 거부 0 |
| **v0.4 실호출 (2026-09-22, Jira 409)** | `how` "임상 결과를 성분 목록 바로 아래로 **옮겨 보시면 좋겠습니다.**" · verify "…**되돌리시는 게 좋겠습니다.**" · 거부 0 |

`insert_after` 를 입력으로 주므로 위치 흔들림은 구조적으로 0 이다. 처음엔 §7-7 "아래로" 검사가 "바로 아래로" 를 잡아 정상 응답을 거부했다 — "바로 " 뒤는 제외한다. **규격 §7-7 문구에 이 예외를 적어 달라고 프론트에 요청.**

## 6. 운영

| 항목 | 값 |
|---|---|
| 환경변수 | `GMS_KEY` · `PRESCRIPTION_MODEL`(기본 gpt-4.1-mini) · `PRESCRIPTIONS_PATH`(컨테이너 `/data/prescriptions.jsonl`) |
| 비용·시간 | 1회 2~3초, 수백 토큰. 브랜드당 콘텐츠 4~5개 = 15초 안 |
| 검증 | `python -m unittest batch.serving.test_prescription` (가짜 LLM, 거부 11 각각). `RUN_LIVE=1` 이면 실제 1회 |

## 판 번호와 저장본 (v0.4, 2026-09-22)

**프롬프트를 고치면 `PROMPT_VERSION` 을 반드시 같이 올린다.** 저장본 키가
`input_hash-PROMPT_VERSION-model` 이라, 판을 안 올리면 같은 입력이 옛 말투 저장본을
그대로 돌려준다. 09-22 에 어미만 고치고 판을 안 올렸다가 배포본에서 `cached: true` ·
`llm_calls: 0` 으로 옛 문장이 계속 나온 적이 있다.

v0.4 에서 바뀐 것은 **지시 어미**다 — `"~하세요"` → `"~해 보시면 좋겠습니다"` ·
`"~하시는 게 좋겠습니다"`. 읽는 사람이 그 브랜드의 주인이라 시키는 말투로 쓰지 않는다.

**프롬프트 규격의 정본은 프론트 문서 `docs/dashboard/action-prescription-prompt.md` 다.
그 문서도 v0.4 로 올려 달라고 프론트에 요청해야 한다** — 참조 구현만 먼저 올린 상태다.
