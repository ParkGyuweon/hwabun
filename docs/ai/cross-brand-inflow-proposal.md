# 교차 브랜드 유입 지표 — 마트 정의 제안 (AI → DATA · FE)

> 2026-09-08 · AI 파트 → DATA·FE **요청서** (Jira 209). 마트 설계는 데이터 파트가 정한다 — 이 문서는 추천 쪽에서 필요한 형태와 재료 위치를 적은 것이다.
> 근거 문서: `contracts/event-attribution-contract.md` (브랜드 귀속, 09-07) · `contracts/processed-schema.md` §2.1 ·
> `contracts/dw-schema.md` §4.2 · `contracts/event-properties-schema.md` §3.4 · `docs/planning/feature-spec-status.md` "교차 브랜드 유입 정의"

## 0. 먼저 — 내가 잘못 알고 있던 것

오늘 낮에 "`brand_id` 를 이벤트에 박는 제안" 이라고 했는데 **틀렸다.** 데이터 파트가 09-07 에 이미 정했다:

- `brand_id` 는 **이벤트에 싣지 않고** Processed 에서 `product_id → dim_product.brand_id` Join 으로 파생, Fact·Mart 에 **Join 시점 스냅샷**으로 보존 (`event-attribution-contract.md` §1)
- `tenant_id` 필수 계약(0.3.0-draft)은 **철회**됐다 (`event-properties-schema.md` §1.1.1). 오늘 내가 `feature-spec-status.md` 에 "계약에 이미 있음" 이라고 쓴 줄은 **틀렸고 고쳐야 한다**
- 계약이 명시적으로 막은 것: route·표시명·직전 Event·세션 첫 상품으로 브랜드를 **추정하지 않는다** — 브랜드는 상품 Dimension 에서만 온다

그러니 남은 일은 "필드 하나 추가" 가 아니라 **마트 하나를 정의하는 것**이다. 재료는 전부 있다.

## 1. 지금 있는 것

| 재료 | 어디 | 상태 |
|---|---|---|
| Fact 행에 `session_id` · `sequence_no` · `page_type` · `brand_id`(스냅샷) | `product_event_fact` (`processed-schema.md` §2.1, 행 172~179) | **구현** — `derive_facts_job.py` |
| 세션 안 직전 이벤트 (`lag`) | `derive_facts_job.py` 289~290 | 이미 `previous_sequence` · `previous_event` 를 계산한다 |
| 추천 카드 클릭 식별자 | `recommendation_click` — `recommendation_id` · `list_id` · `position` · `algorithm` · `impression_event_id` · `context_product_id` | 계약 있음 |
| 상세 진입이 어디서 왔는지 | `product_view.navigation_source` (필수) + `recommendation_id` (선택) · `page_view.navigation_source` | 계약 있음 (§3.4) |
| 교차 브랜드 유입 **정의** | `feature-spec-status.md` — "한 세션에서 최초로 조회한 상품의 브랜드와 이후 조회한 상품의 브랜드가 다르면" · 분리 지표 "전체 / 추천 기반" | 정의 있음, **마트 없음** |
| 추천 마트 | `recommendation_daily_kpi` (§4.2) — 노출·클릭·CTR | 있음. **유입까지는 안 이어짐** |

**없는 것 하나:** `dw-schema.md` §4 에 교차 브랜드 유입 마트가 없다. 정의는 기획에, 재료는 Fact 에, 계산은 어디에도 없다.

## 2. 제안 — `brand_inflow_daily` 마트 하나

### 2.1 정의 (기획 문서의 정의를 그대로 계산식으로)

```
세션 s 의 상품 조회 열 = product_event_fact 에서
    session_id = s, page_type = product_detail, event_name ∈ {page_view, product_view},
    brand_id IS NOT NULL   을 sequence_no 순으로

first_brand(s)  = 그 열의 첫 행의 brand_id           ← "최초로 조회한 상품의 브랜드"
유입(s, B)      = first_brand(s) ≠ B 이고, 열 안에 brand_id = B 인 행이 있다
                  → 브랜드 B 의 교차 브랜드 유입 세션 1
추천 경유 유입   = 유입(s, B) 이고, B 상품의 첫 조회 행이
                    product_view.recommendation_id IS NOT NULL
                    또는 navigation_source = 'recommendation'   ← 어느 쪽인지 §3 에서 확정
```

- **세션당 브랜드당 1건.** 같은 세션에서 B 상품을 세 번 봐도 유입 1 (사장님이 보는 건 "몇 명이 넘어왔나")
- `first_brand` 가 B 인 세션은 B 의 유입이 **아니다** (처음부터 B 를 보러 온 사람)
- `brand_id = NULL` 행(공통 페이지·목록 섹션)은 열에서 뺀다 — 귀속 계약 §2 그대로. **추정하지 않는다**
- 시연 데이터(PC 9,900명 합성 로그·PA 100명)는 `actor_type` 으로 실제와 갈라 집계한다 — 기존 마트와 같은 규칙

### 2.2 마트 스키마 (dw-schema §4 형식)

```text
brand_inflow_daily
key   = event_date_kst + brand_id + actor_type + source + scenario_id + simulation_run_id
input = product_event_fact
```

| column | type | nullable | 설명 |
|---|---|---|---|
| key 전체 | 공통 | scenario/run 만 Y | 집계 축. `brand_id` 는 **유입을 받은** 브랜드 |
| `session_count` | bigint | N | 그날 그 브랜드 상품을 상세 조회한 세션 수 (분모) |
| `inflow_session_count` | bigint | N | 그중 `first_brand ≠ brand_id` 인 세션 (교차 브랜드 유입) |
| `rec_inflow_session_count` | bigint | N | 그중 B 첫 조회가 추천 경유인 세션 |
| `inflow_ratio` | double | Y | `inflow_session_count / session_count` — **"다른 브랜드 고객이 내 브랜드로 넘어온 비율"** |
| `rec_inflow_ratio` | double | Y | `rec_inflow_session_count / inflow_session_count` — 유입 중 추천이 만든 몫 |
| `top_source_brand_id` | string | Y | 유입 세션의 `first_brand` 최다값 — "어느 브랜드 고객이 많이 넘어오나" |
| `mart_processed_at` | timestamp | N | 갱신 시각 |

`top_source_brand_id` 는 **익명 집계값**이다 — 브랜드 이름 하나만 나가고 고객·세션은 안 나간다.
`collective-insight-data-boundary.md` 와 기획 §15-12 의 "익명 집계값만, 표본 부족 시 데이터 수집 중" 규칙을 그대로 받는다
(`inflow_session_count` 가 임계 미만이면 NULL).

### 2.3 대시보드 문구

- "이번 주 다른 브랜드 고객 **N명**이 내 상품을 봤어요 (상세 조회 세션의 **R%**)"
- "그중 **M명**은 추천에서 넘어왔어요"
- "가장 많이 넘어온 곳: ○○ 브랜드 고객" (임계 이상일 때만)

## 3. 각 파트가 할 일

| 파트 | 할 일 | 크기 |
|---|---|---|
| **DATA (은솔)** | ① `dw-schema.md` §4.10 `brand_inflow_daily` 추가 ② `build_marts_job.py` 에 마트 1개 — 세션 윈도우 `first(brand_id)` 와 브랜드별 존재 여부, `recommendation_id`/`navigation_source` 로 추천 경유 분리 ③ `validate_pipeline_job` 에 검증 2건: `inflow ≤ session`, `rec_inflow ≤ inflow` | 마트 1개 · 검증 2건 |
| **FE** | 추천 카드를 눌러 상세로 갔을 때 **`product_view` 에 `recommendation_id` 가 실리는지** 확인 (계약상 선택 필드). 안 실리면 `navigation_source='recommendation'` 만으로 갈라야 해서 정밀도가 떨어진다. `product_view.navigation_source` 는 이미 필수 | 확인 1건, 필요하면 필드 1개 |
| **AI** | 추천 API 응답에 **`recommendation_id` 와 `algorithm` 을 싣는다** — 지금 계약 §5 응답에 없다. FE 가 그 값을 `recommendation_click` · `product_view` 에 그대로 실어야 "추천 경유" 가 닫힌다. `recommend_server.py` 응답 + 계약 §5 | 필드 2개 |
| **BE** | 없음. 정산·매출과 무관 (행동 Fact 기준) | — |
| **기획/FE 대시보드** | 카드 1장 — 위 2.3 문구. 데이터 경계 규칙(익명·임계) 적용 | 카드 1개 |

## 4. 추천 쪽에서 이 지표가 왜 중요한가

- 신규 브랜드 전용 칸(`reserved`, Jira 129)과 CF 채택의 **입점 유인 근거가 이 숫자**다. 지금은 "신규 브랜드 상품이 정답인 사람 43.6%" 같은 오프라인 값만 있고, "실제로 다른 브랜드 고객이 넘어왔다" 는 운영 지표가 없다
- `rec_inflow_ratio` 가 추천의 **비시드 브랜드 도달**(`brand-exposure` 측정의 "파는 값") 을 실측하는 자리다. 평가 프레임워크 부록에 "노출 평등으로 팔면 안 되고 비시드 칸으로 팔아야 한다" 고 적었는데, 그 칸이 실제 유입으로 이어졌는지를 이 마트가 말해 준다

## 5. 이 MR 에서 같이 고친 것 (Jira 209)

- `feature-spec-status.md` — `tenant_id` "계약에 이미 있음" → **철회됨**, "이벤트에 `brand_id` 추가" → **불필요(Join 파생)**, 교차 브랜드 유입 행에 재료 위치와 이 문서 링크
- 추천 API 응답에 `recommendation_id` · `list_id` · `algorithm` · `items[].position` (`recommend_server.py`, 계약 §5)

## 6. 정하지 않은 것

- 세션 첫 조회가 **목록·검색 결과의 상품 카드 클릭**(`product_click`, `page_type` 이 상세가 아님)인 경우 첫 브랜드로 볼지 — 위 정의는 **상세 조회만** 센다. 카드만 보고 지나간 브랜드는 "보러 온" 것으로 안 친다. 기획 확인 필요
- 유입 임계값(익명 집계 최소 세션 수) — 데이터 경계 문서 값을 그대로 쓸지
- 시연에서 이 카드를 보여주려면 합성 로그에 **브랜드 이동**이 들어 있어야 한다 — `gen_behavior_logs.py` 가 세션 안에서 브랜드를 바꾸는지 확인 (S1~S7 요청과 연결)
