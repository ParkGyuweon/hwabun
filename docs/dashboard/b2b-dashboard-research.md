# B2B 대시보드 — 무엇을 왜 보여주는가

작성: 프론트 (2026-08-31)
상태: 조사 결과와 설계 근거. 화면 구현이 이 문서를 따른다.

보는 사람은 **우리 쇼핑몰에 상품을 올린 화장품 브랜드의 마케팅 담당자**다.
이 문서는 화면의 모든 요소가 왜 거기 있는지를 외부 조사로 뒷받침한다.

근거 표기: `[공개]` 출처 있음 · `[관행]` 업계 통용 · `[추정]` 우리가 정한 값

---

## 0. 왜 지금 이 제품인가 — 시장 맥락

이 대시보드는 "있으면 좋은 부가 기능" 이 아니다. 리테일이 행동 데이터를
브랜드에 파는 사업 모델 자체가 지금 업계에서 가장 빠르게 크는 축이다.

### 리테일 미디어 — 유통이 데이터를 파는 시대 [공개]

미국 리테일 미디어 광고비는 2024년 **548.5억 달러**에서 2026년
**763.9억 달러**로 가는 궤도에 있고, 글로벌 시장은 2033년까지
**연평균 18.9%** 성장이 전망된다. 그중 뷰티·퍼스널케어는
**연평균 9.39%** 로 빠르게 크는 버티컬로 꼽힌다.

2025년 광고주의 **60% 이상**이 리테일 미디어 파트너를 고를 때
**유통사가 보유한 고객 데이터**를 최상위 기준으로 꼽았다.
즉 브랜드가 유통 플랫폼에 돈을 내는 이유가 광고 지면이 아니라
**로그인된 고객의 행동 데이터** 그 자체다.

우리 프로젝트는 이 구조의 축소판이다 — 쇼핑몰(수집) → 행동 로그(자산) →
브랜드 대시보드(수익화). 이 화면이 그 수익화 지점이다.

### 서드파티 쿠키 이후 — 퍼스트파티 데이터의 가치 [공개]

쿠키 규제가 확대되면서 마케터의 **74%** 가 퍼스트파티 데이터의 가치가
더 커졌다고 답했다. 리테일 환경은 로그인·장바구니·결제가 한 곳에 있어
**쿠키 없이 광고 노출과 구매를 확정적으로 연결할 수 있는 유일한 디지털
채널**로 평가된다.

우리 로그가 정확히 이 구조다. persona_id 로 로그인된 사용자의 노출
(`recommendation_impression`)부터 전환(`add_to_cart`)까지 한 파이프라인에서
잇는다. 추정 매칭이 아니라 확정 매칭이다.

### 개인화의 값 [공개]

McKinsey 조사에서 소비자의 **71%** 가 개인화된 경험을 기대하고,
개인화를 잘하는 기업은 매출의 **40%를 더** 개인화에서 얻으며,
개인화는 통상 **매출 10~15% 상승**(기업별 5~25%)을 만든다.

④ 고객군 화면이 이 값을 만드는 입구다. "건성은 성분을, 지성은 임상
근거를 본다" 는 데이터가 있어야 브랜드가 고객군별로 다른 소재를 만들 수
있고, 그 차이가 위 수치로 돌아온다.

---

## 1. 조사에서 나온 것 — 고객은 데이터가 부족한 게 아니다

B2B 분석 도구를 쓰는 브랜드가 실제로 겪는 문제를 먼저 봤다.
공통적으로 나오는 불만이 **"데이터가 없다" 가 아니라 "쓸 수가 없다"** 였다.

| 조사에서 확인된 불만 | 우리에게 주는 의미 |
|---|---|
| **데이터 과부하** — 매일 쏟아지는데 모으는 데만 시간이 간다 [공개] | 화면에 지표를 더 얹는 것은 개선이 아니다 |
| **행동으로 이어지지 않는다** — 수집에서 실행 가능한 통찰로 넘어가는 것이 최대 난제 [공개] | 숫자 옆에 **무엇을 해야 하는지**가 없으면 실패다 |
| **입도 부족** — 뭉뚱그려진 수치라 사각지대가 남는다 [공개] | 상품·고객군·콘텐츠 단위까지 쪼개야 한다 |
| **적시성** — POS 데이터를 격주로 받아 대응이 늦다 [공개] | 실시간이 우리 강점이다. 그것이 보여야 한다 |

> **가장 중요한 결론:** 경쟁 도구가 못 하는 것은 수집이 아니라 **해석**이다.
> 클릭 수와 방문 수를 더 예쁘게 보여주는 것으로는 팔 수 없다.

## 2. 화면 설계 규칙 — 조사에서 그대로 가져온 것

### 2-1. 지표 개수 상한 8~12개 [공개]

뷰티 브랜드 대시보드의 의사결정 지원 상한이 **8~12개**로 제시된다.
그 이상은 판단을 돕지 못한다.

**적용:** 개요 화면의 최상단 요약을 **4개**로 묶고, 화면 전체 지표를
12개 아래로 유지한다. 더 보고 싶으면 파고들어 가게 한다.

### 2-2. 5초 규칙 [공개]

경영진은 **5초 안에** 핵심을 파악해야 한다. 검증법까지 정의되어 있다 —
화면을 5초 보여주고 가린 뒤, **무엇을 봤고 다음에 무엇을 할지** 물어본다.
주 지표가 무엇인지 헷갈리거나 다음 행동을 말하지 못하면 그 화면은 실패다.

**적용:** 개요 첫 화면에 **"지금 손봐야 할 것" 한 줄**을 가장 크게 둔다.
지표 카드보다 위에 놓는다. 5초 테스트를 통과하는 유일한 방법은
답을 화면이 먼저 말하는 것이다.

### 2-3. 역피라미드 배치 [공개]

- **최상단** 요약 지표 3~5개. 큰 숫자, 명확한 이름, 변화 표시
- **중단** 추세와 원인
- **하단** 파고들 수 있는 표

결론부터 말하고 근거를 아래로 펼치는 구조다.

**적용:** 모든 화면을 `결론 → 추세 → 표` 세 층으로 고정한다.

### 2-4. 표본 수를 반드시 함께 준다 [추정]

조사에서 **표본 기반 데이터가 오해를 부르고 실행 불가능하다**는 지적이 반복된다.
5명 보고 낸 "전환율 40%" 를 그냥 보여주면 브랜드가 잘못된 판단을 한다.

**적용:** 모든 수치에 표본 수를 붙이고, 표본이 적으면 **흐리게 처리**해서
신뢰할 수 없다는 것을 형태로 알린다.

## 3. 우리만 답할 수 있는 것 — 화면의 존재 이유

일반 웹 분석 도구는 클릭과 페이지뷰까지만 본다. 답이 늘
"상세 페이지 이탈률이 높습니다" 에서 멈추고 그 다음이 없다.

우리는 세 가지를 더 갖고 있다.

| 우리만 있는 것 | 어디서 오나 | 답할 수 있게 되는 질문 |
|---|---|---|
| **콘텐츠 단위 주목도** | `section_dwell` + `content_kind` | 성분을 보고 샀나, 리뷰를 보고 샀나 |
| **고객군 속성** | 페르소나 피부 타입·톤 | 어떤 피부 타입이 무엇을 보고 사나 |
| **좌절 지점** | `rage_click` `dead_click` `scroll_backtrack` | 어디서 막혀서 나갔나 |

**화면의 모든 요소는 이 셋 중 하나를 팔아야 한다.**

### 3-1. 성분이 왜 중심축인가 [공개]

조사에서 화장품 시장 세분화의 축으로 **성분 선호**가 반복해 나온다.
히알루론산·레티놀 같은 성분의 인기 변화를 추적하는 것이 트렌드 식별의
표준 방법으로 제시되고, The Ordinary 처럼 **성분 중심으로 상품군을 나누는**
브랜드 사례가 있다.

우리 AI 파트가 상품 벡터에 브랜드 블록을 넣어 추천 정확도를
**11.4% → 23.6%** 로 올린 것도 같은 방향이다. 성분과 브랜드가
화장품에서 실제로 작동하는 축이라는 뜻이다.

**적용:** 성분을 독립 화면으로 둔다. 그리고 **긁어간 성분**
(`matched_ingredients`) 을 함께 보여준다. 사용자가 성분명을 긁어 밖에서
검색했다는 것은 **그 성분의 설명이 부족하다**는 직접적인 증거다.

### 3-2. 피부 타입·톤 세분화 [공개]

조사에서 피부 타입(건성·지성·복합성·민감성)이 표준 세분화 축으로 확인된다.
지역·기후에 따라 자외선 차단과 유분 조절, 보습과 장벽 회복으로 수요가
갈린다는 것도 나온다.

**적용:** 고객군 화면의 주 축을 **피부 타입 × 톤**으로 둔다.
페르소나 100명이 4종 × 5종으로 균등해서 어느 조합을 골라도 비교가 된다.

## 4. 화면 구성

구현 상태: ①~⑤ 전부 화면으로 존재한다 (frontend/src/dashboard/screens/).
지표는 수집 파이프라인 연결 전이라 시드 고정 모의값이고, 화면마다 배지로 표시한다.

```
① 개요        지금 손봐야 할 것은 무엇인가        ← 5초 규칙
② 상품 반응    어떤 상품이 되고 어떤 상품이 안 되나
③ 정보 관심도  ★ 무엇을 보여줘야 사나            ← 우리 핵심
④ 고객군      누가 사나
⑤ 마찰       어디서 막히나
```

### ① 개요

**맨 위에 문장 하나.** "지금 손봐야 할 것" 을 한 줄로 쓴다.
지표 카드보다 위에, 가장 크게 둔다. 5초 규칙을 통과시키는 장치다.

그 아래 요약 4개(8~12 상한을 지킨다) — 노출, 상세 진입률, 장바구니 전환율,
평균 주목 시간. 각각 표본 수와 변화량을 함께 준다.

**의도 깔때기** — `intent` 값을 그대로 쓴다. 별도 계산이 필요 없다.

```
exposure → interest → comparison → validation → conversion
  노출       열람        비교         확인         전환
```

단계 사이 이탈률을 보여주고 **가장 크게 새는 구간을 강조**한다.
누르면 ③ 또는 ⑤ 로 이동한다.

`friction` 은 깔때기 옆에 따로 세운다. 단계가 아니라 어디서든 새는 구멍이다.

**실시간 흐름** — 조사에서 확인된 적시성 불만(격주 POS)에 대한 우리 답이다.
초당 이벤트 수와 최근 이벤트를 흘려보낸다. 실시간이 이 서비스의 정체성이라
데이터가 지금 들어오고 있다는 것이 보여야 한다.

### ② 상품 반응

상품을 한 줄씩 놓고 깔때기를 가로로 편다.

| 열 | 계산 |
|---|---|
| 노출 | `product_impression` + `recommendation_impression` |
| 상세 진입률 | `product_view` ÷ 노출 |
| 평균 주목 | `section_dwell` 합 ÷ `product_view` |
| 끝까지 본 비율 | `scroll_depth` 90 이상 ÷ `product_view` |
| 찜 | `wishlist_toggle` |
| 장바구니 | `add_to_cart` |
| **이탈 지점** | `exit_summary.last_content_kind` 최빈값 |

**이탈 지점 열이 이 표의 핵심이다.** 전환율이 낮은 상품 옆에
"성분에서 이탈" 이라고 적혀 있으면 그것만으로 할 일이 정해진다.
조사에서 나온 "행동으로 이어지지 않는다" 는 불만에 대한 직접적인 답이다.

### ③ 정보 관심도 ★

이 화면이 제품의 존재 이유다.

**3-1. 콘텐츠별 주목도** — `content_kind` 를 체류 시간 순으로 세운다.

```
ingredient_list   ████████████  38초   전환 기여 2.3x
user_review       ██████████    31초   전환 기여 1.8x
clinical_claim    ███████       22초   전환 기여 2.1x
usage_guide       ████          12초   전환 기여 0.9x
```

**전환 기여**는 "그 콘텐츠를 본 방문의 `add_to_cart` 비율 ÷ 전체 평균" 이다.
**체류가 길다고 좋은 게 아니라는 걸 같이 보여줘야 한다.**
`usage_guide` 처럼 오래 보는데 전환이 안 되는 것은 설명이 어렵다는 신호다.

집계할 때 `co_visible_blocks <= 2` 인 건만 쓴다. 한 화면에 블록이 여러 개
겹쳐 있었으면 그 체류가 어느 콘텐츠를 향한 건지 단정할 수 없다.
PC 쇼핑이라 한 화면에 블록이 여러 개 들어가서 이 조건이 특히 중요하다.

**3-2. 긁어간 성분** — `matched_ingredients` 를 빈도순으로 보여준다.

원문은 저장하지 않는다(데이터 계약). 대신 성분 사전에 걸린 **표준 명칭**만
남긴다. 사전은 `contracts/product-feature-vocab.json` 으로 AI 파트가 상품
벡터에 쓰는 것과 같아서, "이 성분을 긁은 사람" 과 "이 성분이 든 상품" 이
같은 이름으로 조인된다.

**3-3. 검증 행동** — `ingredient_view_mode_change`, `accordion_toggle`,
`review_filter_apply` 의 실행률. 그 행동을 한 방문과 안 한 방문의 전환율을
비교해서 보여준다.

### ④ 고객군

피부 타입 × 톤이 주 축이다.

- 고객군별 전환율
- **고객군별로 무엇을 보는지가 다른가** — ③의 콘텐츠 주목도를 고객군으로 쪼갠다
- `review_filter_apply` 에서 "나와 같은 피부 타입" 을 고른 비율

건성은 성분을, 지성은 임상 근거를 오래 보는 식의 차이가 나오면 그게 인사이트다.

### ⑤ 마찰

| 지표 | 이벤트 | 뜻 |
|---|---|---|
| 헛클릭 위치 | `dead_click` + `content_kind` | 눌릴 거라 기대한 지점 |
| 연타 위치 | `rage_click` | 반응 없는 UI |
| 되돌아 읽기 | `scroll_backtrack` + `section_id` | 이해가 안 되는 구간 |
| 망설임 | `hover_dwell` | 담을까 말까 잰 시간 |

`dead_click` 이 `product_image` 에 몰리면 **확대를 기대했는데 안 되는 것**이다.

> **주의:** 좌절 신호는 상품이 아니라 화면 구성의 문제일 수 있다. 특정 상품에
> `rage_click` 이 몰리면 그 상품이 싫다는 뜻이 아니라 그 페이지의 UI 문제일
> 가능성을 먼저 본다. 상품 선호와 UI 품질을 같은 축에 넣지 않는다.

## 5. 색을 어떻게 쓰나

브랜드 색(HWABUN)을 쓰되, **지표 화면에서 색이 판단을 앞지르지 않게** 한다.

| 쓰임 | 색 | 이유 |
|---|---|---|
| 강조·긍정 추세 | Fresh Green `#A8C96E` | 브랜드 주색. 성장 |
| 주목·경고 | Soft Blossom Pink `#E68FA1` | 브랜드 보조색. 빨강보다 덜 단정적이다 |
| 중립 기준선 | Earthy Brown `#7A5B43` | 기준선·축 |
| 배경 | Warm Ivory `#FAF7F1` | 흰 바탕보다 오래 봐도 눈이 덜 아프다 |
| 본문 | Charcoal `#2B2B2B` | 가독성 |

**숫자 자체에는 색을 칠하지 않는다.** 빨간 숫자는 읽기 전에 나쁜 것이 된다.
좋고 나쁨의 판단은 보는 사람이 한다. 색은 **어디를 먼저 볼지**만 알려준다.

막대와 추세선에만 색을 쓰고, 표의 숫자는 Charcoal 하나로 간다.
표본이 적어 신뢰할 수 없는 값은 색이 아니라 **투명도**로 낮춘다.

## 6. 확인 필요

- 집계 주기 (실시간 / 5분 / 1시간). ③ 같은 무거운 집계를 실시간으로 할지
- `conversion_lift` 를 서버가 계산할지, 프론트가 두 수치를 받아 나눌지
- 브랜드 계정과 권한 모델 — 담당자는 자기 브랜드만 봐야 한다
- 실시간 전송 방식 (SSE 제안)

## 7. 출처

- 뷰티 대시보드 지표 상한 8~12개 — [Web Tonic: Beauty & Skincare Dashboard Statistics](https://www.webtonic.io/blog/beauty-skincare-dashboards-statistics)
- 5초 규칙과 5초 테스트 — [Customer Science: Designing Actionable Dashboards — The 5-Second Rule for Executives](https://customerscience.com.au/customer-experience-2/designing-actionable-dashboards-the-5-second-rule-for-executives/)
- 역피라미드 배치와 요약 KPI 개수 — [Domo: Executive Dashboard Best Practices](https://www.domo.com/learn/article/what-should-be-on-an-executive-dashboard)
- 데이터 과부하·실행 불가 문제 — [Crisp: CPG Data Analytics](https://www.gocrisp.com/learning-center/sales-merchandising/cpg-data-analytics)
- 입도 부족과 사각지대 — [NIQ: CPG data analytics](https://nielseniq.com/global/en/insights/analysis/2024/cpg-data-analytics-part-1/)
- 데이터 파편화 — [Snowflake: The Data Dilemma — Fragmented Insights for Retail & CPG](https://www.snowflake.com/en/blog/retail-cpg-data-fragmentation-personalization/)
- POS 적시성 문제 — [PDI: Top CPG Challenges in Retail Industry](https://pditechnologies.com/resources/article/cpg-challenges-in-retail-industry/)
- 성분 중심 세분화와 트렌드 추적 — [Cosmetic Index: Segmenting Your Market for a Skincare Brand](https://www.cosmeticindex.com/segmenting-your-market-skincare-brand-p2321.php)
- 피부 타입·기후 세분화 — [BO International: Skincare Market Segmentation](https://www.bointernational.net/blogs/skincare-market-segmentation)
- B2B 뷰티 데이터 공유와 실시간 대응 — [Shopify: B2B Beauty Guide](https://www.shopify.com/enterprise/blog/b2b-beauty)
- 리테일 미디어 시장 규모·성장률 — [Improvado: Top Retail Media Networks](https://improvado.io/blog/top-retail-media-networks) · [Persistence Market Research: Retail Media Networks Market](https://www.persistencemarketresearch.com/market-research/retail-media-networks-market.asp)
- 퍼스트파티 데이터 가치 상승(마케터 74%)·확정 측정 — [Osmos: First-Party Shopper Data in Retail Media](https://www.osmos.ai/blog/first-party-data-in-retail-media-the-complete-targeting-guide)
- 광고주의 유통사 데이터 중시(60%+) — [Tinuiti: Top Retail Media Networks](https://tinuiti.com/blog/ecommerce/retail-media-networks/)
- 개인화 기대(71%)·매출 기여(40%)·상승폭(10~15%) — [McKinsey: The value of getting personalization right](https://www.mckinsey.com/capabilities/growth-marketing-and-sales/our-insights/the-value-of-getting-personalization-right-or-wrong-is-multiplying)

### 조사 한계

- 지표 상한 8~12개는 한 매체의 제시값이다. 학술 근거는 찾지 못했다.
- CPG 불만 조사는 대부분 분석 도구 벤더가 쓴 글이라, 자사 제품이 푸는 문제를
  강조하는 편향이 있다. 불만 자체는 여러 출처에서 반복되므로 채택했다.
- 화장품 성분 트렌드 자료는 시장 보고서 요약이라 원 데이터를 확인하지 못했다.
- 5절의 색 배치는 브랜드 색을 받아 우리가 정한 것이다. 사용성 검증 전이다.
- 0절의 시장 수치는 각 조사기관 추정치로, 기관마다 시장 정의가 달라 수치가
  갈린다. 방향(고성장·퍼스트파티 중심)은 여러 출처에서 일치한다.
- 개인화 수치는 업종 전체 평균이다. 화장품 단독 수치는 확인하지 못했다.
