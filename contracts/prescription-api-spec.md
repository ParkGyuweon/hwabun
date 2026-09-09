# 대시보드 처방 문장 API (AI ↔ 프론트)

> 상태: **참조 구현 (2026-09-09, Jira 220)** — `batch/serving/recommend_server.py` `POST /api/prescription`, 본체 `batch/serving/prescription.py`.
> 프롬프트 규격의 정본은 프론트 문서 [`docs/dashboard/action-prescription-prompt.md`](../docs/dashboard/action-prescription-prompt.md) (v0.1) 이고,
> 이 문서는 **그 규격을 서버가 어떻게 받고 무엇을 돌려주는가**만 적는다. 규격과 다른 점은 §3 에 모아 두었다.

## 1. 역할

| 하는 일 | 누가 |
|---|---|
| 판정 `up · fix · keep` | **프론트** (`verbOf()`, 규칙 고정). 서버는 판정을 바꾸지 않는다 |
| 문장 `how · basis · verify` | **서버 (LLM)** — gpt-4.1-mini · temperature 0 · JSON 스키마 강제 |
| 자동 거부 (규격 §6) | **서버.** 거부되면 `prescription: null` + `rejected_by[]`. 프론트는 판정만 그린다 |
| 저장·재사용 | **서버.** 같은 입력(해시)은 다시 생성하지 않는다 (`cached: true`). 일 1회 생성 권고 |

## 2. 요청

```
POST /api/prescription?force=false&model=gpt-4.1-mini
Content-Type: application/json
```

본문은 규격 §2 그대로: `brand · target · page_context · cross_screen_signals`.
`target.verb` 는 프론트가 정한 판정. `cross_screen_signals[].from` 은 네 화면 이름 중 하나:
`무엇을 보고 사나 · 누가 사나 · 고객이 찾는 성분 · 막히는 곳`.

| 입력 규칙 (§2) | 서버 처리 |
|---|---|
| `verb = keep` | LLM 을 부르지 않고 `prescription: null, rejected_by: ["verb_keep"]` (200) |
| 신호가 `sample_size ≥ 200` 기준 2개 미만 / 6개 초과 | 같은 방식으로 `signals_lt_2` / `signals_gt_6` |
| `from` 이 네 화면 밖 | `signal_from_unknown` |
| `force=true` | 저장본을 무시하고 다시 생성 |

## 3. 응답 (200)

```json
{
  "content_kind": "clinical_claim",
  "verb": "up",
  "brand": "SSAFY Beauty",
  "prompt_version": "0.3",
  "model": "gpt-4.1-mini",
  "key": "b5efbe3797dde921-0.3-gpt-4.1-mini",
  "prescription": {
    "how": "임상 결과를 제품 소개 바로 아래로 옮기세요.",
    "basis": [
      { "from": "무엇을 보고 사나", "text": "임상 결과의 상세페이지 열람률은 34.0%이고 담기율 배수는 2.1배입니다." },
      { "from": "누가 사나", "text": "지성 고객이 가장 오래 보는 글이 임상 결과이고, 이 고객군 체류의 29.0%를 여기서 씁니다." }
    ],
    "verify": "열람률 34.0% → 44.0%. 열람률이 줄면 원래 위치로 되돌리세요."
  },
  "rejected_by": [],
  "cached": false,
  "generated_at": "2026-09-09T19:12:03",
  "raw": null
}
```

`prescription` 의 모양은 프론트 `frontend/src/dashboard/lib/prescription.ts` 의 `Prescription` 과 같다.
거부됐을 때는 `prescription: null`, `rejected_by` 에 아래 코드, `raw` 에 모델 원문(디버그용).

| `rejected_by` 코드 | 규격 §6 | 뜻 |
|---|---|---|
| `shape` | — | JSON 이 {how, basis[{from,text}], verify} 모양이 아님 |
| `dash` | 줄표 | `—` 등장 |
| `forbidden_terms:…` | 용어·효능 단정 | 규격 §4 목록 (웹 분석 용어·효능 단정) |
| `banned_terms` | 금지 표현 | `contracts/feedback-banned-terms.json` |
| `how_vague` | 구체성 | how 에 위치·형식·개수 표현이 없음 |
| `how_moves_down` | (추가) | `up` 인데 지금보다 뒤 칸으로 옮기라고 함 |
| `how_contradicts_verb` | §8-2 | `up` 인데 "빼세요·삭제하세요" |
| `basis_n` · `basis_from` · `basis_same_from` | 근거 출처·다양성 | 2~3개, 네 화면 안, 서로 다른 화면 최소 2종 |
| `basis_numbers:…` | 없는 숫자 | basis 의 숫자가 입력에 없음 (0.34↔34.0%, 22300ms↔22초 변형은 허용) |
| `basis_judgement:…` | (추가) | "평균보다 높다" 류 비교 판단이 입력 문장에 없음 |
| `verify_no_arrow` · `verify_range:…` | 목표값 범위 | "현재값 → 목표값" 화살표 없음 / 목표가 현재 미만 또는 1.6배 초과 |

오류: `503 LLM_UNAVAILABLE` — 서버에 `GMS_KEY` 가 없다. 추천은 되고 이 엔드포인트만 막힌다. `422` — 본문이 §2 모양이 아니다.

## 4. 규격 v0.1 과 다른 점 (v0.3) — 왜

같은 입력 5회 실측(nano · mini × 온도 0 · 1)에서 v0.1 그대로는 basis 가 20/20 문자열로 오고, `up` 인데 아래 칸으로 옮기라고 했다.
답변서 `처방프롬프트_v0.1_AI답변_20260909.md` 참조. 고친 것:

1. §4 마지막 줄을 **출력 JSON 골격**으로 바꾸고 `response_format = json_schema (strict)` 강제
2. `up` 이면 **지금보다 앞 칸으로만**, `fix` 면 위치 그대로. 형식·개수는 근거 있을 때만 (억지 "1개" 금지)
3. verify 는 **"현재값 → 목표값"** 화살표 문자 그대로, 목표 1.2~1.6배
4. 비율은 템플릿에서 **34.0%** 로 미리 적어 준다
5. `from` 허용 목록 명시, 대상 콘텐츠 집계에도 화면 이름
6. (추가) 입력에 없는 **비교 판단 금지** 한 줄 + `basis_judgement` 검사

결과: mini 온도 0 → 5/5 같은 지시, 거부 0/5. nano → 5/5 "위쪽으로" (칸 이름 없음) 거부. **nano 는 쓰지 않는다.**

## 5. 남은 결정 (프론트)

| # | 결정 | 서버 기본값 |
|---|---|---|
| ① | 최상단 쏠림 — mini 는 대개 가장 위 칸으로 올리라고 한다. 상한 규칙을 줄지 | 없음 (규칙상 틀리지 않음) |
| ② | 생성 주기 | 같은 입력은 저장본. 집계 갱신 때 `force=true` 로 하루 1회 권고 |
| ③ | 효능 단정 금지 목록 확정본 (ai-insight-rules §4-3) | 규격 §4 의 10개 낱말 |

## 6. 운영

| 항목 | 값 |
|---|---|
| 환경변수 | `GMS_KEY` (또는 `OPENAI_API_KEY`) · `PRESCRIPTION_MODEL` (기본 gpt-4.1-mini) · `PRESCRIPTIONS_PATH` (기본 `batch/ingest/data/serving/prescriptions.jsonl`, 컨테이너는 `/data/prescriptions.jsonl`) |
| 비용·시간 | 1회 2~3초, 수백 토큰. 브랜드당 콘텐츠 4~5개 = 15초 안 |
| 검증 | `python -m unittest batch.serving.test_prescription` (가짜 LLM). `RUN_LIVE=1` 이면 실제 1회 |
