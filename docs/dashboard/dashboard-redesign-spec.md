# 브랜드 대시보드 재설계 명세 — 요소 · 데이터 가능성 · 해석 · AI 프롬프트 · UX 규칙

> 2026-09-08. 대상: `frontend/src/dashboard/` 9화면.
> 기준 문서: [ai-insight-rules.md](./ai-insight-rules.md)(해석 근거·출처), [metric-basis.md](./metric-basis.md), [insight-catalog.md](./insight-catalog.md).
> 계약: `contracts/processed-schema.md` §8~§15, `contracts/dw-schema.md` §4, `contracts/persona-schema.md`, `contracts/event-properties-schema.md`.
>
> 이 문서가 답하는 것: **① 화면에 무엇을 넣나 ② 그 수치가 지금 파이프라인(PC 9,900 + PA 100)에서 실제로 나오나 ③ 그 수치는 무슨 뜻이고 어떻게 해석해 보여주나 ④ 해석 AI에 넣을 프롬프트와 기준 ⑤ UX·차트 규칙.**

---

## 0. 먼저 확정해야 하는 데이터 사실 (조사 결과)

화면을 그리기 전에 "그 숫자가 나오는가"를 코드로 확인했다. 결과가 대시보드 구성을 크게 바꾼다.

### 0-1. 지금 로그가 있는 것과 없는 것

| 항목 | 사실 | 출처 |
|---|---|---|
| PC 페르소나 9,900명 로그 | 있음. 1인당 약 590건, 전원 약 590만 건. `actor_type=synthetic` | `simulator/generator/README.md` |
| PC 로그의 상품 범위 | **세포라 200개 상품 · 55개 브랜드** (`batch/ingest/data/products_200.json`). **SSAFY Beauty 8종(SB*)은 로그가 0건** | `gen_behavior_logs.py:62`, 카탈로그 확인 |
| PA 에이전트 100명 | LLM이 실제 브라우저를 조작. 15~30턴. 판단 근거는 `*_decisions.jsonl`에 별도 보존. **정성 검증 축, 정량 지표에 합치지 않음** | `simulator/agents/README.md` |
| 생성되는 이벤트 | 36종 중 34종. **생성되지 않는 것: `navigation_click`, `dead_click`, 그리고 `purchase`·`begin_checkout`·`purchase_reason_select`** (계약에는 있으나 생성기 미구현) | generator grep |
| `section_dwell` | `section_id`·`content_kind`·`content_ref`·`co_visible_blocks` 포함 | `gen_behavior_logs.py:477` |
| `text_selection`·`text_copy` | 생성됨(확률 0.35 / 0.28), 성분 성향 페르소나는 2.2배 | `:487~496` |
| `review_filter_apply` | `same_skin_type` 필터로 생성 | `:524` |
| `recommendation_impression/click` | 생성됨. 노출 정책은 `popular_v0`(전원 동일 화면) 또는 `cbf_v1` | README `--exposure` |
| 페르소나 속성 | `skin_type` 4 · `skin_tone` 5 · `eye_color` · `hair_color` · `n_reviews` · `avg_rating`. **`concern`(피부 고민) 속성 없음** | `persona-schema.md` §4 |
| 페르소나 성향(생성기 입력) | `persona_style.json`: ingredient·price·texture·scent·sensitivity·review_lean 6축 0~1. **생성기 입력값이라 대시보드 "관측치"로 쓰면 순환 논증** | `build_persona_style.py` |
| 리뷰 | 세포라 2,000건(리뷰어 skin_type·tone 포함). **SSAFY Beauty 리뷰 0건** | `reviews.sample.json` |
| 고객 피드백 | SSAFY Beauty 99건 생성 + 30건 분류 (Jira 201·202). **세포라 브랜드 피드백 0건** | `simulator/feedback/` |
| DW 마트 | `product_daily_kpi`·`content_daily_kpi`·`funnel_daily_kpi`·`persona_segment_daily_kpi`·`recommendation_daily_kpi` 정의됨. 물리화·MySQL 적재는 미완 | `dw-schema.md` §4, feature-spec-status |

### 0-2. 결정 1 — 브랜드 스코프가 갈린다

행동 로그는 세포라 브랜드에만 있고, 피드백·상품 등록은 SSAFY Beauty에만 있다. 한 브랜드로 대시보드 전체를 채울 수 없다.

| 선택지 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A (권장)** | 데모 브랜드를 **세포라 카탈로그의 실제 브랜드 하나**(예: Drunk Elephant 16종, Tatcha 14종)로 잡고, 행동·리뷰 화면은 그 브랜드 로그로 채운다. 피드백·상품 등록은 SSAFY Beauty로 유지하고 화면 상단에 "시연 브랜드" 표기 | 지금 데이터로 전 화면이 실측이 된다. 표본이 크다(브랜드당 수천 세션) | 브랜드가 둘로 보인다. 발표에서 한 줄 설명 필요 |
| B | 생성기에 SB 8종을 추가해 SSAFY Beauty 로그를 만든다 | 브랜드 하나로 통일 | 상품 벡터·추천·성분 정규화 테이블(Jira 194)에 SB를 넣어야 하고 AI·데이터 파트 작업. 리뷰는 여전히 0 |
| C | SSAFY Beauty 유지 + 행동 화면은 모의값 | 작업 없음 | 발표에서 "실측"이라 말할 수 없다. 조사 결론(해석 부족을 데이터로 푼다)과 모순 |

**결정: A 확정 (2026-09-08, 유림).** 이 문서는 A를 전제로 쓴다. 대시보드 상단 스코프 셀렉터에 "행동 데이터: {세포라 브랜드} · 피드백·등록: SSAFY Beauty"를 명시한다. B로 가면 스코프만 바뀌고 요소·해석은 그대로다.

### 0-3. 결정 2 — 구매가 없다

`purchase`가 생성되지 않으므로 **구매 전환·매출·재구매·구매 이유(선언 vs 행동)는 지금 화면에 넣을 수 없다.** 퍼널은 `add_to_cart`에서 끝난다. 이 항목들은 "구매 이벤트 생성 후" 칸으로 분리해 두고, 화면에는 자리를 만들지 않는다. 빈 카드에 "준비 중"을 두는 것은 5초 규칙 위반이다.

### 0-4. 결정 3 — 고민(concern) 축은 상품 쪽에만 있다

페르소나에 고민 속성이 없으므로 "내 고객의 고민 분포"는 만들 수 없다. 대신 **상품의 concern 태그 × 고객 피부 격자의 담기율**은 가능하다(상품 벡터 concern 상위 2축 × `persona_segment_daily_kpi`). "고민 커버 격자"는 이 형태로 바꾼다.

### 0-5. 표본 크기 감각 (추정, 실측으로 교체)

| 단위 | 추정 표본 | 계산 |
|---|---|---|
| 상품 1개 | 상세 조회 세션 약 300 | 9,900명 × 방문 상품 약 6개 ÷ 200 |
| 브랜드 1개(16종) | 약 4,800 세션 | 300 × 16 |
| 브랜드 × 피부타입(4) | 약 1,200 | 4,800 ÷ 4 |
| 브랜드 × 피부타입 × 톤(20셀) | 약 240 | 4,800 ÷ 20 |
| 상품 × 20셀 | **약 15 → 표시 불가** | 300 ÷ 20 |
| 브랜드 × content_kind(21) | 약 200~500 | 세션당 여러 콘텐츠 |

**규칙:** 분모 200 미만은 흐림 + "표본 부족", 50 미만은 셀 자체를 비운다. 상품 × 피부 격자는 만들지 않는다(브랜드 × 격자만).

---

## 1. 화면 구조 (재배치)

조사 결론: 브랜드가 결정하는 순서대로 화면을 놓는다. 범용 KPI는 뒤로.

| 순서 | 화면 | 답하는 질문 | 상태 |
|---|---|---|---|
| 1 | **Overview** | 지금 손봐야 할 것 하나 | 재작성 |
| 2 | **정보 관심도** ★ | 무엇을 보고 사나 | 재작성 |
| 3 | **고객군** | 누가 사나 | 재작성 |
| 4 | **성분** ★ | 어떤 성분이 갭인가 | 재작성 |
| 5 | **상품** | 상품별 병목 | 재작성 |
| 6 | **고객 피드백** ★ | 무엇을 고쳐 달라 하나 | 완료(Jira 195). 담당 라우팅만 추가 |
| 7 | **리뷰** | 공개 평가 | 축소·재배치 |
| 8 | **행동·마찰** | 화면 문제 | 뒤로 이동, 축소 |
| 9 | **상품 등록** | 등록 | 유지 |
| — | 내 위치(벤치마크) | 코호트 대비 | **보류** — 코호트 정의·억제 규칙이 데이터 파트에서 와야 함 |

---

## 2. 요소 카탈로그 — 화면별

표기: **가능** = 지금 PC 로그·마트 정의로 계산 가능 · **조건부** = 데이터는 있으나 마트 물리화 또는 조인 필요 · **불가(구매)** = purchase 이벤트 생성 후 · **불가** = 데이터 없음.
"AI 기준"은 §4 프롬프트에 그대로 들어가는 임계값이다.

### 2-1. Overview

| # | 요소 | 수치 정의 | 원천 | 가능성 | 표본 | 의미·해석 | AI 기준 | 차트 |
|---|---|---|---|---|---|---|---|---|
| O1 | **지금 손봐야 할 것 한 줄** | 아래 O2~O6과 각 화면 상위 이상치 중 **점수 가장 큰 1개**를 문장으로 | 전 화면 집계 | 가능 | — | Few: 한 화면·한눈에. 결론 1개만 | 우선순위 점수 = (코호트/전주 대비 편차 z) × ln(표본). 뷰티 명사 필수 | 큰 문장 카드 + "왜"·"다음" 2줄 |
| O2 | 상세→담기 전환율 + 전주 대비 | `add_to_cart_sessions / product_view_sessions` | `funnel_daily_kpi` | 가능 | 브랜드 ~4,800 | 구매 없는 환경의 최종 전환. Baymard: 장바구니는 "I might want that" 약한 의도 | 전주 대비 ±15%p 이상이면 언급. 표본<200 언급 금지 | KPI 카드 + 미니 스파크라인 |
| O3 | 정보 확인 도달률 | `information_view_sessions / product_view_sessions` | `funnel_daily_kpi` | 가능 | ~4,800 | 상세에서 성분·리뷰 등 "검증 행동"을 한 비율. 우리만 있는 지표 | 코호트 중앙값 대비 하위 25% → "검증 콘텐츠가 안 보인다" | KPI 카드 |
| O4 | 교차 브랜드 유입 비율 | 세션 첫 `product_view`의 brand ≠ 내 brand인 세션 중 내 상품 조회 ÷ 내 상품 조회 세션 | `product_event_fact` + `sessionized_events` | 조건부 (brand_id 귀속 Jira 169 완료, 마트 없음) | ~4,800 | 플랫폼 효과. Amazon New-to-Brand 개념 | 30% 이상이면 "다른 브랜드 고객이 넘어온다" 긍정 | KPI 카드 |
| O5 | 추천 기여 | `recommendation_click` 경유 세션의 담기 ÷ 전체 담기 | `product_event_fact`(entry_source, recommendation_id) | 가능 | 담기 수백 | 추천이 내 매출에 기여하는지 | 20% 이상 언급. 노출 정책(`algorithm`)이 섞인 기간은 비교 금지 | KPI 카드 |
| O6 | 피드백 이번 주 | 건수 + 최다 카테고리 | Feedback(SSAFY) | 가능 | 30 | Q4 | 같은 카테고리 3건 이상이면 언급 | KPI 카드 |
| O7 | 재구매율 배지 | — | `purchase_fact` | **불가(구매)** | — | — | — | 넣지 않음 |
| O8 | 방문·조회·이탈률 (기존) | 유지하되 **접힘** | `product_daily_kpi` | 가능 | — | 범용. 해석 없음 | 결론 문장에 쓰지 않음 | 접힌 보조 지표 |

### 2-2. 정보 관심도 ★

| # | 요소 | 수치 정의 | 원천 | 가능성 | 표본 | 의미·해석 | AI 기준 | 차트 |
|---|---|---|---|---|---|---|---|---|
| C1 | **콘텐츠별 주목도 × 전환 기여** | 주목도 = `dwell_ms_sum / product_view_sessions` (content_kind별, `max_co_visible_blocks ≤ 2`만). 전환 기여 = 그 콘텐츠를 본 세션의 담기율 ÷ 전체 담기율 (lift) | `content_daily_kpi`, `section_dwell_agg`, `funnel_session_fact` | 가능 | content_kind별 200~500 | Contentsquare Exposure→Attractiveness→Conversion 체인. 체류 길다 ≠ 좋다 | lift ≥1.3 & 체류 하위 → "짧게 보지만 결정에 기여, 위로 올려라". lift ≤0.8 & 체류 상위 → "오래 보지만 안 산다: 설명 문제" (사용법이면 난이도, 성분이면 기피 성분 발견 가능성) | **두 축 산점도**(x 주목도, y lift). 막대 2개 나열 금지 |
| C2 | 사용자가 가장 많이 드래그한 성분 | `text_select_count + text_copy_count`를 `matched_ingredients` 성분별 합산 | `content_interest_fact.matched_ingredients` | 가능 | 성분별 수십~수백 | **관심의 크기.** 설명 부족으로 단정하지 않는다. 성분→고객군 문장 붙임(R-3) | 상위 3개 언급. 내 라인에 없는 성분이면 성분 화면으로 연결 | 순위 막대(rank) |
| ~~C2b~~ | ~~드래그 성분의 관심 vs 어려움 판별~~ **보류 (2026-09-16 · §6 참고)** — 성분 단위로 쪼개면 표본이 무너진다. 당분간 C2 의 "관심" 으로만 표시한다 | 성분별로 (드래그 세션 중) `scroll_backtrack(section=ingredients)` 비율, `exit_summary.last_content_kind=ingredient_*` 비율, 담기율 lift(드래그 세션 ÷ 전체) | `content_interest_fact` + `cleaned_events` + `funnel_session_fact` 세션 조인 → **신규 마트 `ingredient_interest_kpi`** (grain: brand_id, product_id, ingredient) | 조건부(마트 없음. 세션 조인이라 FE 계산 불가) | 성분별 수십~수백 | 네 신호 중 둘 이상: 되돌아 읽기↑·이탈↑·lift<1 → "관심은 있는데 이해가 안 됨". lift≥1.3 → "소구 성분". 그 외 → "관심" | 판별은 마트가 준 플래그로만. 없으면 "관심" 으로 표시 | 표 열 2개(관심 지수 · 판별) |
| C3 | 긁어간 문장 유형 | `selection_kind` 분포 | `cleaned_events`(text_selection.selection_kind) | 조건부(생성기가 selection_kind를 내는지 확인) | — | 클레임 긁기 = 근거 찾기 | claim 30% 이상 → "출처·시험 조건 표기" | 가로 누적 막대 1개 |
| C4 | 성분 표시 모드 효과 | `ingredient_view_mode_change.mode`별 이후 담기율 | `cleaned_events` + funnel | 조건부 | 모드별 수백 | 어느 표시가 구매를 돕나 | 모드 간 담기율 차 5%p 이상이면 기본 모드 변경 권고 | 3막대 (표본 병기) |
| C5 | 배지 신뢰도 | `highlight_badge` 체류 (badge_id별) + 전환 기여 | `section_dwell_agg`(content_ref=badge_id) | 조건부(생성기 badge_id 확인) | 배지별 수십 | 클레임 피로 79% | 체류 <0.5초 & lift <1 → "읽히지 않는 배지" | 표 |
| C6 | 리뷰 필터 효과 | `review_filter_apply(same_skin_type)` 사용 세션 vs 미사용 담기율 | `content_interest_fact.review_filter_count` + funnel | 가능 | 사용 세션 수백 | 같은 피부 후기 탐색 77% | lift ≥1.5 → "리뷰어 피부타입 표기 권고" | 두 숫자 비교 카드 |
| C7 | 검증 행동 실행률 × 전환 | 행동(펼침·전성분·리뷰 확장·필터) 유무별 담기율 | `content_interest_fact` + funnel | 가능 | 수천 | Clarity intent: 상호작용 없는 체류는 Low | 행동군 lift 표시 | 4행 표 |
| C8 | 선언 이유 vs 행동 | — | `purchase_reason_fact` | **불가(구매)** | — | — | — | 넣지 않음 |
| C9 | 스크롤 도달 분포 | 세션별 최대 `scroll_depth` 분포 | `cleaned_events` | 가능 | 수천 | 25% 이하 다수 = 첫 화면 기대 불일치 | 25% 이하 40% 초과 → 목록 카드·첫 줄 불일치 | 누적 막대 4단계 |

### 2-3. 고객군

| # | 요소 | 수치 정의 | 원천 | 가능성 | 표본 | 의미·해석 | AI 기준 | 차트 |
|---|---|---|---|---|---|---|---|---|
| S1 | **피부타입 × 톤 격자 담기율** | `add_to_cart_sessions / product_view_sessions` (segment_type=skin_type, skin_tone 교차) | `persona_segment_daily_kpi` — 단일 축만 정의됨. **교차 격자는 `funnel_session_fact` + `persona_profile` 조인 필요** | 조건부 | 20셀 × ~240 | 누가 사나 | 최고·최저 셀 차 ≥10%p면 언급. 셀 <50 비움 | 히트맵 4×5, 셀에 n |
| S2 | **복합성 → 톤 축 자동 전환** | skin_type=combination 고객은 톤별로만 표시 + 고정 문장 | `[실측]` 타입 편차 0.053 vs 톤 0.269 | 가능 | — | 복합성 55%는 타입 판별력 없음 | 고정 문장. 복합성 셀은 타입 비교 문장 생성 금지 | 히트맵 행 병합 |
| S3 | 고객군별 가장 오래 본 콘텍츠 | 격자 × content_kind 체류 최댓값 | `section_dwell_agg` + persona 조인 | 조건부 | 셀×콘텍츠 ~50 → **타입 4행만** | 건성은 성분, 지성은 리뷰 | 셀당 1문장 "이 고객군은 {content}를 가장 오래 본다" | 격자 셀 라벨 |
| S4 | 상품 concern × 격자 담기율 | 상품 벡터 concern 상위 2축 × 격자 lift | `product_feature.jsonl` + funnel + persona | 조건부 | — | 결정 3. "모공 상품은 지성·미디엄이 담는다" | lift ≥1.3 셀 강조 | 히트맵 9×4 |
| S5 | 고객군 × 가격 밴드 | `price_bin` × 피부타입 담기율 | dim_product.price_usd + funnel + persona | 조건부 | 5×4=20셀 | `[실측]` lift 1.30x | 최고 밴드 언급 | 히트맵 |
| S6 | 예측 적합 vs 실측 | 친화도 lift(상품×피부) vs 실측 담기율 | `ingredient_skin_affinity`/attribute affinity + funnel | 조건부 | 상품×타입 ~75 → **경고 표시** | 갈리는 상품이 인사이트 | 예측 상위 타입 ≠ 실측 상위 타입 → "갈림" | 두 열 표 |
| S7 | 내 고객 고민 분포 | — | 페르소나 concern 없음 | **불가** | — | — | — | 넣지 않음 |

### 2-4. 성분 ★

| # | 요소 | 수치 정의 | 원천 | 가능성 | 표본 | 의미·해석 | AI 기준 | 차트 |
|---|---|---|---|---|---|---|---|---|
| I1 | **성분 갭 표** | 성분 30종 × (관심 = 긁기+체류, 내 라인 보유 여부, 함량 위치가중) | `content_interest_fact.matched_ingredients` + 상품 벡터 ingredient 블록 | 가능 | 성분별 | 찾는데 없는 성분 최상단 | 관심 상위 10 중 미보유 → "갭". 성분→고객군 문장(R-3) | 표 30행, 갭 행 강조 |
| I2 | 함량 위치 | 전성분 순서 위치가중 `max(1-위치/전체, 0.10)` | 상품 벡터 계산값 | 가능 | — | 주요/미량 | 태그 성분이 위치 ≤0.3(미량) → 경고 | 상품별 성분 띠 |
| I3 | 주의 성분 포함 상품 | 변성알코올·향료 등 포함 상품 수 | dim_product ingredients | 가능 | — | 향료 = 접촉피부염 최다 원인 | 포함 상품의 이탈률이 브랜드 평균보다 높으면 언급 | 표 |
| I4 | 성분 × 피부 반응 | 상품 lift를 성분 보유로 가중 평균 | affinity + funnel | 조건부 | — | "살리실산은 지성 1.8배" | lift 차 ≥0.5 언급 | 히트맵 성분×타입 |
| I5 | 성분 관심 추세 | 주간 긁기·체류 시계열 | `content_daily_kpi` 일자 축 | 조건부(기간 축 필요, 생성 로그는 시각 분포 확인) | — | 2주 연속 상승 | 2주 연속 +20% | 라인 |
| I6 | 병용 주의 조합 | 같은 세션 담기 쌍 × caution_pairs | `product_event_fact` 세션 쌍 | 조건부(사전 없음) | — | 레티놀+AHA | — | 보류 |

### 2-5. 상품

| # | 요소 | 수치 정의 | 원천 | 가능성 | AI 기준 | 차트 |
|---|---|---|---|---|---|---|
| P1 | **병목 단계** | 노출→클릭→상세→정보확인→담기 단계별 전환, 브랜드 중앙값 대비 | `funnel_daily_kpi` | 가능 | 브랜드 중앙값 대비 가장 낮은 단계 1개만 지목 | 상품 행 + 미니 퍼널 |
| P2 | 이탈 지점 + 이유 힌트 | `exit_summary.last_content_kind` 최빈값 | `cleaned_events` | 가능 | 사용법 → 난이도, 성분 → 기피 성분 가능성, 유사상품 → 대체 탐색 | 열 |
| P3 | 옵션 왕복 | 세션당 `variant_select` 평균 | `product_event_fact` | 가능 | ≥3 → 마찰 | 열 |
| P4 | 퀵룹→상세 | `quick_look_close.close_reason=open_detail` 비율 | funnel `quick_look_close_reason` | 가능 | <40% → 카드 정보 보강 | 열 |
| P5 | 찜 대비 담기 | `wishlist_toggle / add_to_cart` | `product_daily_kpi` (wishlist 컬럼 없음 → fact 집계) | 조건부 | >1.5 → 가격 저항 가능성 | 열 |
| P6 | 담기 후 제거율 | `remove_from_cart_sessions / add_to_cart_sessions` | `product_daily_kpi` | 가능 | >30% 언급 | 열 |
| P7 | 미량 성분 경고 | I2 | — | 가능 | — | 배지 |
| P8 | 대신 산 상품 | — | purchase | **불가(구매)** | — | 없음 |
| P9 | 비교된 상품 수 | 세션 내 `product_view` 고유 상품 수(다른 브랜드 포함) | `sessionized_events` | 조건부 | 카테고리 평균 대비 | 열 |

### 2-6. 리뷰 (축소)

| # | 요소 | 원천 | 가능성 | 비고 |
|---|---|---|---|---|
| R1 | 피부타입별 평점 갈림 | `reviews.sample.json` (리뷰어 skin_type) | 가능(세포라 브랜드만) | 차 ≥0.5 → 타깃 문구 |
| R2 | 자극·트러블 언급률 × 리뷰어 피부 | 리뷰 텍스트 키워드 | 가능 | 카테고리 평균 대비 |
| R3 | 리뷰 열람률 | `review_view_rate` | `content_daily_kpi` | 가능 |
| R4 | 피드백과 교차 | 피드백 카테고리 ↔ 리뷰 키워드 | 조건부(브랜드가 갈려서 지금은 불가) | 결정 1 B일 때만 |

### 2-7. 행동·마찰 (뒤로)

| # | 요소 | 원천 | 가능성 | 규칙 |
|---|---|---|---|---|
| B1 | 마찰 위치 | `rage_click`·`scroll_backtrack` × section_id | 가능(dead_click은 미생성) | "상품이 아니라 화면 문제" 고정 문구. 상품 선호 점수와 분리 |
| B2 | 빠른 이탈 | `exit_summary` dwell <3초 비율 | 가능 | 40% 초과 → 첫 화면 불일치 |
| B3 | 진입 경로별 전환 | `entry_source`별 담기율 | 가능 | 추천 진입 lift |
| B4 | 의도 단계 분포 | intent 8종 | 가능 | 참고용 |

### 2-8. 고객 피드백 (완료 + 추가)

| # | 추가 요소 | 규칙 |
|---|---|---|
| F1 | 담당 라우팅 배지 | axis → 담당: efficacy·texture·scent → 처방, packaging → 포장, value → 가격·상품기획. 카테고리 그룹 헤더에 배지 |
| F2 | 종합 요약 한 줄 | 카테고리 상위 2개 + 건수. LLM 없이 템플릿으로 |
| F3 | 광고 금지 표현 경고 | 사장님 답글 입력란에 §4-3 금지어 실시간 표시 |

---

## 3. UX·UI 규칙 (브랜드 입장의 불편 해소)

### 3-1. 차트 선택 — "차이가 없는데 길이만 긴 막대" 금지

| 상황 | 규칙 |
|---|---|
| 항목 간 최대·최소 차이가 **최댓값의 15% 미만** | 막대를 그리지 않는다. 숫자 표 + "차이 없음 (n=…)" 한 줄 |
| 차이가 15~40% | 막대 대신 **점 + 기준선(코호트 중앙값 또는 브랜드 평균)** 도트 플롯. 편차가 보이게 |
| 차이가 40% 이상 | 막대. 축은 항상 0에서 시작 |
| 비율(%) 지표 | 축 0~100 고정 또는 0~max×1.2. 축 잘라내기 금지. 잘라야 하면 "축 시작 X%" 명시 |
| 두 지표 관계(주목도×전환) | 산점도. 막대 2개 나열 금지 |
| 격자 | 히트맵. 셀마다 값 + n. n<50 빈칸, n<200 흐림 |
| 순위 | 상위 5~10만. 나머지 "더 보기" |
| 시계열 | 라인. 점 7개 이하면 라인 대신 막대 |

### 3-2. 텍스트

- 상품명은 **1줄, 말줄임, 호버 시 전체**. 목록에서는 24자, 카드 제목 36자 상한.
- 지표 라벨은 명사 2~4어절. 설명은 라벨 아래 12px 한 줄. 줄글 문단은 Panel 상단 `note` 1개까지.
- 숫자: 비율은 소수 1자리, 건수는 천 단위 콤마, 배수는 "1.6배". 단위는 숫자 뒤 붙임.
- 모든 비율 옆에 `n=`. 200 미만은 `--ink-faint`, 50 미만은 표시 안 함.
- 실측/모의 배지 유지. 모의값이 하나라도 있는 패널은 제목 옆에 배지.

### 3-3. 레이아웃 — 역피라미드 고정

각 화면은 세 층: **결론 카드(1개) → 근거 차트(1~2개) → 표(접힘 가능)**. 화면당 시각 요소 6개 이하.

### 3-4. 인터랙션

- 축·격자·순위 항목 클릭 → 해당 필터 적용(상품·고객군), URL 쿼리에 반영해 새로고침·공유 유지.
- 호버 툴팁: 값 + n + 정의 한 줄. 툴팁 없이 의미를 모르는 축약어 금지.
- 필터 상태(상품·기간·고객군)는 화면 간 유지.
- 결론 카드의 "왜" 클릭 → 근거 차트로 스크롤·하이라이트.

### 3-5. 애니메이션 — 절제

- 진입: 카드 opacity 0→1, 160ms, stagger 40ms. 이상.
- 값 변경: 숫자 카운트업 300ms, 막대 width transition 240ms ease-out.
- 히트맵 셀·산점도 점 호버: scale 1.04, 120ms.
- `prefers-reduced-motion: reduce`면 전부 끈다.
- 로딩 스켈레톤은 실제 API 연결 후. 지금은 정적이라 넣지 않는다.

### 3-6. 색

- 데이터 색은 2개(브랜드 그린 + 액센트 핑크)와 회색 계열만. 히트맵은 브랜드 그린 단색 명도 5단계.
- 경고(갭·마찰·미량)는 액센트. 긍정은 브랜드색. 나머지 회색.
- 색으로만 구분 금지. 항상 라벨·값 병기.

---

## 4. 해석 AI 프롬프트

### 4-1. 시스템 프롬프트 (그대로 사용)

```
당신은 소규모 뷰티 브랜드 대표에게 대시보드 수치를 해석해 주는 분석가다.
입력은 JSON(지표, 표본, 비교값, 엔티티, 어휘)이고 출력은 아래 형식의 한국어다.

[출력 형식]
결론: 한 줄, 20자 내외. 성분·피부타입·고민·콘텍츠 중 하나 이상의 뷰티 명사를 반드시 포함.
근거: 2~3개. 각 줄에 숫자와 (n=표본). 비교값이 있으면 "기준 X" 병기.
권고: 1~2개. 상세페이지 / 타깃·문구 / 제품·처방 / 포장 / 가격 중 어느 단위인지 앞에 적는다.
신뢰도: 높음|보통|낮음 + 이유 한 줄 (표본, 기간, 단일 신호 여부).

[해석 규칙]
- 표본(n) 200 미만 지표는 결론에 쓰지 않는다. 언급하려면 "참고"로 낮춘다. 50 미만은 언급 금지.
- 인과를 단정하지 않는다. "~해서 이탈했다" 대신 "~에서 이탈했다. ~일 가능성".
- 다른 브랜드·상품의 실명, 절대 매출을 쓰지 않는다. 코호트 분위와 속성 차이만.
- 체류가 길다를 좋다로 쓰지 않는다. 전환 기여(lift)와 함께 본다.
  lift ≥ 1.3이고 체류 하위면 "짧게 보지만 결정에 기여". lift ≤ 0.8이고 체류 상위면 "오래 보지만 결정 못 함".
  content_kind가 usage_guide면 "설명 난이도", ingredient_*면 "기피 성분 발견 가능성", similar_products면 "대체 탐색".
- rage_click, scroll_backtrack은 상품 선호가 아니라 화면 문제로 먼저 서술한다.
- 복합성(combination) 고객은 피부타입 대신 톤으로 서술한다. 타입 비교 문장을 만들지 않는다.
- 성분을 말할 때 그 성분을 찾는 고객군과 고민을 붙인다. 매핑은 입력 vocab.ingredient_map을 따른다.
- 구매·매출·재구매는 입력에 없으면 언급하지 않는다. 장바구니 담기가 최종 전환이다.
- 추천 기여는 입력 algorithm이 한 종류일 때만 해석한다.
- 관행·벤더 수치를 인용할 때 "업계 관행 기준"이라고 쓴다.

[광고 표현 금지 — 화장품법 제13조, 식약처 표시·광고 관리 지침 2025-08-14]
권고 문구에 다음 표현을 쓰지 않는다: 아토피·건선·소양증·여드름·기미·주근깨·화상 "치료", 살균, 소독, 항염, 항균, 해독,
혈액순환, 피부재생, 세포 재생, 호르몬, "홍조·홍반 개선·제거", "뾰루지 개선", "상처 치료", "병원용", "피부과 전용", "엑소좀",
"마이크로니들", "피부나이 n세 감소".
다음 표현을 권고할 때는 "(실증자료 필요)"를 붙인다: 여드름성 피부에 사용 적합, 다크서클 완화, 피부장벽 손상 개선에 도움,
피지분비 조절, 붓기 완화, 미세먼지 차단.
미백·주름·자외선차단 표현은 기능성화장품 심사 제품에만 허용한다고 명시한다.

[금지]
- 지표 나열로 끝내지 않는다. 결론 1개, 권고 2개까지.
- 입력에 없는 숫자를 만들지 않는다.
```

### 4-2. 입력 스키마

```json
{
  "screen": "overview|content|segments|ingredients|products|reviews|behavior|feedback",
  "brand": {"id": "…", "name": "…", "scope_note": "행동: {브랜드} / 피드백: SSAFY Beauty"},
  "period": {"from": "…", "to": "…", "compare": "prev_week|cohort|none"},
  "metrics": [
    {"id": "C1", "name": "콘텐츠 주목도×전환", "rows": [
      {"key": "ingredient_list", "attention_ms": 5400, "lift": 1.6, "n": 412}
    ]}
  ],
  "cohort": {"median": …, "p25": …, "p75": …, "brands": 7},
  "entities": {"products": [{"id": "…", "name": "…"}], "segments": ["dry|fair", …]},
  "vocab": {"ingredient_map": {"Ceramide": {"skin": ["dry","sensitive"], "concern": ["Dryness","Redness"]}}, "content_kind_ko": {…}},
  "flags": {"algorithm_mixed": false, "purchase_available": false}
}
```

### 4-3. 지표별 임계값 표 (프롬프트에 함께 전달)

| 지표 | 언급 조건 | 강조 조건 | 금지 조건 |
|---|---|---|---|
| 전환율 변화 | ±15%p | ±25%p | n<200 |
| 콘텐츠 lift | ≥1.3 또는 ≤0.8 | ≥1.6 또는 ≤0.6 | co_visible>2 포함 집계 |
| 격자 셀 차 | ≥10%p | ≥20%p | 셀 n<50 |
| 성분 갭 | 관심 상위 10 & 미보유 | 상위 3 & 미보유 | — |
| 배지 | 체류<0.5초 & lift<1 | — | 배지 n<100 |
| 리뷰 필터 lift | ≥1.5 | ≥2.0 | 사용 세션<100 |
| 마찰 | 섹션 집중도 ≥40% | — | 상품 선호 문장으로 변환 |
| 피드백 | 같은 카테고리 ≥3건 | ≥5건 & 상품 2개 이상 | 원문은 피드백 화면만 |
| 코호트 비교 | brands ≥5 & 지배 <50% | — | 조건 미달 시 비교 문장 금지 |

### 4-4. 검증 방법

- 시연 로그(PC 100명 표본, `--behavior hidden_preference`)로 각 지표를 계산해 프롬프트에 넣고, 출력 30건을 사람이 채점: 뷰티 명사 포함 / 표본 규칙 준수 / 인과 단정 없음 / 금지어 0.
- 결론 문장과 화면 차트가 같은 숫자를 가리키는지 대조(숫자 불일치 0).

---

## 5. 구현 순서와 산출물

| 단계 | 내용 | 의존 | 산출물 |
|---|---|---|---|
| 0 | **결정 1(브랜드 스코프) 팀 확정** | 없음 | 이 문서 §0-2 체크 |
| 1 | 차트 컴포넌트 재작성: DotPlot(기준선), Scatter, Heatmap, KpiCard(스파크라인), ConclusionCard. 15% 규칙·n 규칙 내장 | 없음 | `dashboard/charts/*.tsx` |
| 2 | 집계 레이어: 마트 컬럼명 그대로의 타입 + 모의 어댑터(지금) → API 어댑터(후) | 마트 정의 | `dashboard/data/*.ts` |
| 3 | Overview·정보관심도·고객군·성분 재작성 | 1, 2 | 4화면 |
| 4 | 상품·리뷰·행동 축소 재배치, 피드백 F1~F3 | 1 | 4화면 |
| 5 | 해석 문장 생성: 템플릿(LLM 없음) 먼저 → §4 프롬프트로 교체 | AI 파트 | `dashboard/lib/insight.ts` |
| 6 | 데이터 파트 요청: 교차 격자 마트, brand 귀속 세션 마트, 물리화·MySQL | 데이터 | 요청 목록 §6 |

## 6. 데이터·AI 파트 요청 목록

| 요청 | 이유 | 대상 |
|---|---|---|
| `persona_segment_daily_kpi`에 `skin_type × skin_tone` 교차 segment_type 추가 | S1 격자 | 데이터 |
| 세션 첫 조회 브랜드 컬럼(`first_brand_id`)을 `sessionized_events`에 | O4 교차 유입 | 데이터 |
| `content_daily_kpi`에 `co_visible_le2_dwell_ms_sum` 분리 컬럼 | C1 귀속 순도 | 데이터 · **별도 티켓 진행 중 (2026-09-16)**. 기존 `dwell_ms_sum` 은 두고 컬럼을 하나 더 단다 — 화면은 C1 산점도의 x축(주목도)만 새 컬럼을 쓴다 |
| ~~**신규 마트 `ingredient_interest_kpi`**~~ **철회 (2026-09-16)** — 판별에 쓸 표본이 안 나온다. 실질 마찰 신호가 `scroll_backtrack` 1,883건뿐이고(`dead_click`·`rage_click` 은 시드 제외 후 0), 이걸 성분 30종 × 상품으로 쪼개면 셀당 몇 건이라 플래그가 잡음이 된다. `content_kind` 단위로는 `friction_daily`·`content_conversion_daily` 로 이미 답할 수 있다. 실사용자 로그가 쌓이면 다시 요청한다 | C2b | 데이터 |
| `product_daily_kpi`에 `wishlist_count` | P5 | 데이터 · **별도 티켓 진행 중 (2026-09-16)** |
| 생성기 `selection_kind`, `badge_id` 실제 값 확인 | C3, C5 | 데이터·AI |
| `purchase`·`purchase_reason_select` 생성기 구현 | O7, C8, P8 전부 | AI(생성기) |
| 결정 1-B 선택 시: SB 8종 상품 벡터·정규화 테이블 포함 | 브랜드 통일 | AI |
| 해석 LLM 호출 경로(배치 or 요청 시)와 모델 | §4 | AI |
| **이벤트 금액을 원화로** — `unit_price` + `currency: 'KRW'` | §6-1 | 프론트 |

### 6-1. 이벤트 금액 단위 — 원화로 확정 (2026-09-16)

지금까지 프론트 주석(`lib/format.ts`·`lib/localize.ts`)이 "데이터 팀과 단위 합의 전이라 이벤트의
`price_usd`·`cart_value`·`currency:'USD'` 는 건드리지 않는다" 였다. 합의됐다.

네 곳 중 **한 곳만 달러였다.**

| | 단위 |
|---|---|
| 화면 표시 | 원화 |
| 카카오페이 결제 (`payment.ts`) | 원화 (`CURRENCY_KRW`) |
| `dim_product.base_price` | 원화 (Jira 302) |
| **이벤트 금액** | **달러** ← 여기만 |

실제로 원화로 결제되는데 `purchase.paid_value` 가 달러값이었다.

**필드 이름은 `unit_price` 다.** 데이터 파트 제안은 `price_usd` → `price` 개명이었는데
(`dim_product` 가 `base_price`/`source_price_usd` 로 겪은 문제와 같다), `price` 로 가면 네 번째
이름이 생긴다. 이미 세 곳이 `unit_price` 를 쓰고 있다 — `event-properties-schema.md` §4 의
`purchase.items[]` 필수 속성, 같은 표의 `add_to_cart` 선택 속성, 그리고 생성기(`--currency KRW`)와
Fact 컬럼. `unit_price` 로 맞추면 프론트만 바꾸면 되고 Fact 의 폴백(`unit_price` 없으면
`price_usd`)도 필요 없어진다.

| 이벤트 | 바꾸는 것 |
|---|---|
| `add_to_cart` · `remove_from_cart` | `price_usd` 제거 → `unit_price` + `currency: 'KRW'` |
| `begin_checkout` | `cart_value` 원화 + `currency: 'KRW'` |
| `purchase` | `order_value`·`paid_value` 원화, `items[].unit_price` 원화 |
| `price_usd` | 계약에서 **deprecated**. 당분간 두되 프론트는 보내지 않는다 |

환산 규칙은 데이터·추천이 쓰는 것과 같다 (`dw-schema.md` §3.2 · `batch/jobs/product_encoder.py`
`price_krw_of()`).

```text
price_krw 가 있으면 그 값
없으면  round(price_usd × 1340.86 / 100) × 100     (100원 반올림)
```

**프론트에 이미 같은 함수가 있다** — `lib/localize.ts` 의 `toKrw()` 가 같은 식이다
(`KRW_PER_USD = 1340.86` · `KRW_ROUNDING = 100`). 지금은 화면 표시에만 쓰고 있어서 이벤트에도
태우면 된다.

**구현 시점은 결제 작업과 맞춘다.** 고칠 자리가 `App.tsx` 의 `begin_checkout`·`purchase` 인데 그
파일이 배포 브랜치의 결제 작업과 겹친다. 백엔드 담당과 순서를 정한 뒤 넣는다. 데이터 파트는 이
문구만 있으면 구현을 마무리할 수 있다고 해서 결정을 먼저 적어 둔다.

### 6-2. PA 를 가르는 축 — `actor_type` 이 아니라 `generator_type` (2026-09-16)

마트 계약 §8-1 에서 "PA 에 별도 `actor_type`(예: `agent`)을 줄 수 있는지" 를 데이터 파트 판단으로
넘겼던 건이다. **주지 않는다.**

`actor_type` enum 에 새 값을 넣으면 **기존 모든 마트의 grain 이 바뀐다.** 대신 `generator_type` 으로
가른다 — PA 와 PC 가 이미 이 값으로 갈려 있고, Jira 324 에서 `generator_type` 이 모든 마트의 key 에
들어갔다.

그래서 화면의 `actorType` 기본값은 `all` 로 두고, PA 를 뺄 때는 `generatorType` 으로 거른다.
