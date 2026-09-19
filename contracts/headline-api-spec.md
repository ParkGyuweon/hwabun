# 대시보드 한 마디 API (AI ↔ 프론트)

> 상태: **참조 구현 (2026-09-19, Jira 365)** — `batch/serving/recommend_server.py` `POST /api/headline`, 본체 `batch/serving/headline.py`.
> 처방 API([`prescription-api-spec.md`](prescription-api-spec.md))와 **자리가 다르다.** 같은 GMS 키·같은 스위치를 쓰고 거부 규칙 일부를 공유하지만, 쓰는 말이 다르다.

## 1. 왜 따로 있나

| | 처방 `/api/prescription` | 한 마디 `/api/headline` |
|---|---|---|
| 답하는 질문 | "이번 주에 뭘 고칠까" | "지금 무슨 일이 일어나고 있나" |
| 문장 | 지시문 `~하세요` | 서술문 `~입니다` |
| 붙는 자리 | 판정(up·fix)이 난 콘텐츠 하나 | 화면 하나 + 그 화면의 섹션마다 |
| 없을 때 | 규칙 표 문장으로 대체 | 규칙 문장으로 대체 (`origin: "rule"`) |

**한 마디에 지시문이 섞이면 거부한다** (`imperative`). 같은 화면에서 두 자리가 서로 다른 할 일을 말하면 사장님이 어느 쪽을 따라야 할지 모른다. 할 일은 처방 자리 하나로 모은다.

## 2. 역할

| 하는 일 | 누가 |
|---|---|
| 숫자 계산·표기 (`1,360건` · `34.0%` · `92초`) | **프론트.** 화면에 그린 문자열을 그대로 보낸다. 서버는 계산하지 않는다 |
| 비교·변화 판단 (`늘었습니다` · `지난 2주보다`) | **프론트.** 완성된 문장으로 `comparisons` 에 넣는다. 거기 없는 비교는 서버가 거부한다 |
| 표본이 얇은지 (`thin`) | **프론트.** 화면이 이미 흐리게 그리는 기준(격자 n<50 · 콘텐츠 n<500 등)을 그대로 쓴다 |
| 문장 | **서버 (LLM)** — 기본 `gpt-4.1-mini` · temperature 0 · `response_format=json_schema strict` |
| 자동 거부 9종 | **서버.** 거부되면 규칙 문장으로 바꿔 주고 `rejected_by[]` 에 이유를 남긴다 |
| 저장·재사용 | **서버.** `input_hash` 가 같으면 재생성하지 않는다 (`cached: true`) |

## 3. 요청

```
POST /api/headline?force=false&model=gpt-4.1-mini
```

```json
{
  "brand": { "name": "SSAFY Beauty", "product_count": 8, "functional_certified": false },
  "screen": { "id": "overview", "label_ko": "한눈에 보기", "period_text": "최근 14일" },
  "sections": [
    {
      "id": "traffic",
      "label_ko": "찾아온 사람",
      "facts": [
        { "label_ko": "상세를 본 방문", "value_text": "1,360건" },
        { "label_ko": "상세를 본 사람", "value_text": "412명" }
      ],
      "comparisons": ["상세를 본 방문이 지난 2주 1,120건에서 1,360건으로 늘었습니다."],
      "thin": false
    }
  ]
}
```

- `facts[].value_text` 는 **화면에 보이는 그대로**. 단위·천 단위 쉼표·소수점 자리까지 같아야 한다. 서버가 문장에 쓰는 숫자는 여기 있는 것뿐이다.
- `comparisons` 는 **완성형 한 문장**들. 서버는 이 문장 안에 있는 말로만 비교·변화를 쓸 수 있다. 값 하나만 보내면 그 값이 큰지 작은지 말하지 않는다.
- `thin: true` 면 그 섹션 줄은 결론 대신 "아직 판단하기 이릅니다" 쪽으로 간다.
- `brand.functional_certified: true` 면 기능성 심사 품목으로 보고 `functional_only` 낱말을 허용한다 (처방과 같은 규칙).

| 입력 규칙 | 서버 처리 (LLM 을 부르지 않는다) |
|---|---|
| `sections` 가 빈 배열 | `rejected_by: ["no_section"]`, 문장 없음 |
| 섹션 8개 초과 | `too_many_sections:<n>` |
| 같은 `id` 가 두 번 | `duplicate_section_id` |
| 한 섹션의 `facts` 8개 초과 | `too_many_facts:<id>` |
| `facts` 도 `comparisons` 도 비었음 | `empty_section:<id>` |
| `force=true` | 저장본을 무시하고 다시 생성 |

## 4. 응답 (200)

```json
{
  "screen": "overview",
  "brand": "SSAFY Beauty",
  "headline": "최근 14일 동안 상세를 본 방문이 1,360건이고 그중 141건이 장바구니까지 갔습니다.",
  "sections": [
    { "id": "traffic", "line": "상세를 본 방문이 1,360건으로 지난 2주보다 늘었습니다." }
  ],
  "origin": "llm",
  "rejected_by": [],
  "needs_evidence": [],
  "model": "gpt-4.1-mini",
  "prompt_version": "0.1",
  "input_hash": "sha256:…",
  "generated_at": "2026-09-19T18:20:39",
  "cached": false
}
```

**503 을 내지 않는다.** 설명 한 줄 때문에 화면이 비면 표만 남아 읽을 사람이 더 막힌다.

| `origin` | 뜻 | 화면 표시 권고 |
|---|---|---|
| `llm` | 문장이 검사를 통과했다 | 그대로 |
| `rule` | 키가 없거나 문장이 거부됐다. 값을 이어 붙인 문장이다 | "값 그대로" 같은 옅은 배지. 요약이 아니라 나열이다 |
| `none` | 섹션이 없어 문장을 만들 수 없다 | 줄을 그리지 않는다 |

`sections` 는 **요청한 섹션 전부**를 같은 `id` 로 돌려준다. 하나라도 빠지거나 없는 `id` 가 오면 서버가 먼저 거부한다.

## 5. 자동 거부 9종

| 코드 | 무엇을 막나 |
|---|---|
| `banned_term:<낱말>` | 웹 분석 용어(전환율·퍼널·이탈률·리텐션·CTA·UX·세션·임프레션)와 효능 단정. 목록은 `contracts/cosmetic-claim-banned-terms.json` |
| `functional_only:<낱말>` | 기능성 심사 기록이 없는데 기능성 표현을 씀 |
| `no_such_number:<값>` | 입력에 없는 숫자. 업계 평균·경쟁사·벤치마크를 지어내는 것을 막는다 |
| `unsupported_comparison:<섹션>:<말>` | 그 섹션의 `comparisons` 에 없는 비교·변화 판단. **섹션별로 본다** — 옆 섹션이 "늘었습니다" 를 가졌다고 이 섹션이 쓸 수 있는 것은 아니다. **두 숫자를 나눠 만든 크기 주장("두 배"·"절반"·"배 이상")도 여기서 막는다** — 한글 수사라 숫자 대조로는 안 잡힌다. 한 줄 안의 모든 표현을 본다 |
| `imperative:<어미>` | 지시문. 할 일은 처방 자리다 |
| `section_mismatch:<id>` | 섹션이 빠졌거나 없는 id 를 만들었다 |
| `off_topic:<id>` | 섹션 줄에 그 섹션 이름도, 그 섹션 값의 이름도 없다 |
| `two_sentences:<id>` / `too_long:<id>:<길이>` | 한 줄은 한 문장, 90자 이내 |
| `em_dash` | 줄표 |

`needs_evidence[]` 는 거부가 아니라 꼬리표다 (처방과 같음). 실증 자료가 필요한 표현이 있다는 뜻.

## 6. 부르는 주기

- 화면당 한 번. 브랜드·기간·값이 그대로면 `input_hash` 가 같아 저장본이 온다 (`cached: true`).
- 과금되는 자리는 처방과 이 API 둘뿐이다. 스위치는 처방과 공유한다 (`POST /api/prescription/llm`) — 끄면 이쪽도 규칙 문장만 나간다.
- 상태는 `GET /api/headline/stats` 와 `/health.headline`.

## 7. 배포본 경로 (Jira 365)

`/api/headline` 과 `/api/prescription` 은 **추천 서버 8300** 이 답한다. `deploy/nginx/default.conf` 에 두 경로의 정확 일치 블록이 있어야 한다. 없으면 `location /api/` 에 걸려 shop-backend 8090 으로 가고, 거기엔 핸들러가 없어 404 다 — 09-18까지 배포본 처방이 한 번도 안 돈 이유가 이것이다.

스위치 엔드포인트(`/api/prescription/llm`)는 열지 않는다. 과금을 켜고 끄는 자리인데 인증이 없다. 두 경로는 IP 당 분당 6회로 제한한다.

**이 블록은 임시 경로다.** 오래 갈 모양은 shop-backend 가 대시보드 세션을 들고 서버-투-서버로 부르는 것이다 (`/api/feedback/classify`, Jira 353 과 같은 방식). 그때 이 nginx 블록은 지운다.
