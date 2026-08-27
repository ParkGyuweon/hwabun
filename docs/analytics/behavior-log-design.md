# 행동 로그 설계 근거

작성: 프론트 (2026-08-27)
대상: 상품 상세 페이지 (`frontend/src/pages/ProductDetailPage.tsx`)

이벤트 목록은 `frontend/src/types/log.ts`, 구현은 `frontend/src/hooks/*` 에 있다.
이 문서는 **왜 그 자리에 그 이벤트를 두었는지**를 남긴다.

## 무엇이 문제였나

초안은 클릭 이벤트 위주였고, 클릭이 아닌 신호는 세 개뿐이었다.
그마저도 전부 `trackOnce` (방문당 1회) 라서 실제로 남는 양이 이랬다.

- `scroll_depth` — 25/50/75/100 네 구간, 방문당 최대 4건
- `section_view` — 섹션당 1건
- `exit_summary` — 이탈 시 1건

그래서 페이지를 한참 훑어보다 그냥 나간 방문은 **거의 빈 세션**으로 남았다.
장바구니까지 간 소수만 데이터가 있고, 정작 "왜 안 샀는지" 를 물어볼 방문에는
아무 근거가 없다. 추천 모델 입력으로도 클릭만으로는 신호가 너무 성기다.

버그도 하나 있었다. `section_view` 가 `intersectionRatio >= 0.5` 를 조건으로 썼는데,
이 비율은 **요소 면적 대비**라서 뷰포트보다 긴 섹션은 값이 0.5 를 넘을 수가 없다.
리뷰 섹션처럼 긴 구간은 아무리 읽어도 로그가 찍히지 않았다.

## 조사: 무엇이 구매 판단에 영향을 주나

### 1. 이미지가 가장 크다

설문 응답자의 85% 가 상품 정보와 비주얼이 브랜드·판매처 선택에 영향을 준다고 답했다
([inriver](https://www.inriver.com/resources/10-pieces-of-product-information-every-product-detail-page-needs/)).
화장품은 특히 **사람 모델이 나온 컷**이 있어야 실제 색·질감을 가늠할 수 있다
([Baymard](https://baymard.com/blog/health-and-beauty-ux-research)).

그런데 Baymard 사용성 테스트에서 반복해서 나온 문제가 **갤러리에서 이미지를 못 찾거나
확대를 못 하는 것**이었다 ([Baymard](https://baymard.com/ecommerce-design-examples/42-image-gallery-overlay)).
확대하려다 실패한 사용자는 아무 로그도 안 남기고 사라진다.

### 2. 성분은 화장품 고유의 상위 요인

응답자의 43.9% 가 성분을 핵심 판단 요소로 꼽았고, 신뢰는 성분 투명성·시험 결과·
표기 명확성에서 온다
([PulseAI Research](https://pulseairesearch.com/pulse-shift/blogs/1531/why_do_consumers_choose_certain_skincare_products_the_research_behind_what_they_buy)).
모르는 성분을 만나면 그 부분만 긁어서 따로 검색하는 행동이 뒤따른다.

### 3. 리뷰는 "결정" 이 아니라 "확인"

뷰티 구매자의 88% 가 별점·리뷰를 본다. 67% 는 다른 구매자의 사진·영상을 본다
([PowerReviews](https://www.powerreviews.com/research/health-beauty-shopping-trends-2023/factors-influencing-beauty-shopping/)).
94% 는 나쁜 리뷰 때문에 구매를 접은 적이 있다고 답했다
([DemoUp Cliplister](https://www.demoup-cliplister.com/en/blog/product-detail-pages-ux-guide/)).

중요한 건 순서다. 리뷰는 **이미 후보에 올린 상품을 확인하는 단계**에서 작동한다.
그래서 리뷰 열람은 관심의 시작이 아니라 **구매 직전 신호**로 읽어야 한다.

### 4. 옵션(색·용량) 왕복은 화장품 특유의 마찰

Baymard 는 모바일에서 색상 선택 시 이미지를 보려고 위로 다시 스크롤해야 하는 것을
반복 지적한다 ([Baymard](https://baymard.com/blog/health-and-beauty-ux-research)).
옵션을 A→B→A 로 오가는 건 비교 중이라는 뜻이다.

### 5. 암묵 신호는 하나만 보면 안 된다

추천 연구에서 체류 시간은 명시적 평점과 상관이 있지만, 창만 띄워두고 안 보는 경우가
있어 그것만으로는 해석이 어렵다. **커서 움직임·스크롤과 함께 볼 때** 비로소
관련성의 근거가 된다
([Springer](https://link.springer.com/chapter/10.1007/978-3-662-44654-6_16)).
같은 연구 계열에서 마이크로 단위 행동으로 스크롤, **하이라이트(텍스트 선택)**,
**확대**를 꼽는다
([Jannach 외, Social Information Access](https://web-ainf.aau.at/pub/jannach/files/BookChapter_Social_Information_Access_2018.pdf)).

### 6. 좌절 신호는 이탈로 이어진다

같은 자리를 연타하는 rage click 은 UI 가 기대대로 반응하지 않는다는 신호이고
세션 이탈로 이어진다 ([Conviva](https://www.conviva.ai/glossary/rage-clicks/)).
눌리지 않는 곳을 누르는 dead click 도 같은 계열이다
([Glassbox](https://www.glassbox.com/blog/click-tracking/)).

## 조사 → 로그 매핑

| 조사에서 나온 것 | 화면의 어디 | 남기는 이벤트 | 왜 |
|---|---|---|---|
| 이미지가 판단의 85% | 갤러리 | `media_view` (기존) + `dead_click` | 확대하려다 실패한 클릭을 잡는다 |
| 성분 43.9% | Ingredients | `text_selection` / `text_copy` | 어느 성분에서 걸렸는지 문장 단위로 짚인다 |
| 리뷰는 확인 단계 | Reviews | `section_dwell`, `review_filter_apply` | 머문 시간으로 확인 강도를 본다 |
| 같은 피부 타입 리뷰 | 리뷰 필터 | `review_filter_apply` (기존) | 페르소나 일치 필터는 강한 구매 의도 |
| 옵션 왕복 비교 | VariantPicker | `variant_select` (기존) + `scroll_backtrack` | 되돌아 올려보는 패턴과 함께 본다 |
| 체류는 단독으로 못 씀 | 전 구간 | `section_dwell` + `scroll_pause` | 같은 `section_id` 로 교차 검증 |
| 어디서 붙잡혔나 | 전 구간 | `scroll_pause` | 멈춘 지점 = 관심 지점 |
| 확신이 안 설 때 | 전 구간 | `scroll_backtrack` | 되돌아 읽기 = 비교·망설임 |
| 담을까 말까 | Add to Cart | `hover_dwell` | 올려두고 안 누른 시간 |
| 좌절 → 이탈 | 전 구간 | `rage_click`, `dead_click` | 막힌 지점 |

## 이벤트 이름만으로는 부족하다

로그를 받는 쪽에서 매번 다시 판단해야 하는 게 두 가지 있었다.
둘 다 프론트가 발생 시점에 이미 아는 정보라, 이름 옆에 같이 실어 보낸다.

### 1. 이 이벤트가 무슨 뜻인가 — `intent`

`text_copy` 가 관심인지 확인인지, `hover_dwell` 이 관심인지 망설임인지는
분석하는 사람마다 다르게 잡는다. 그 판단을 한 곳(`EVENT_INTENT`)에 고정했다.

```
exposure  → interest → comparison → validation → conversion
                                                      ↕
                                                  friction
```

| intent | 뜻 | 해당 이벤트 |
|---|---|---|
| `exposure` | 화면에 떴다 | `scroll_depth`, `*_impression` |
| `interest` | 들여다봤다 | `section_view`, `section_dwell`, `scroll_pause`, `media_view` |
| `comparison` | 다른 후보와 견줬다 | `variant_select`, `scroll_backtrack`, `recommendation_click`, `product_click` |
| `validation` | 사실을 확인했다 | `text_selection`, `text_copy`, `review_*`, `ingredient_*`, `accordion_toggle` |
| `hesitation` | 살까 말까 쟀다 | `hover_dwell` |
| `conversion` | 사는 쪽으로 움직였다 | `add_to_cart`, `wishlist_toggle`, `quantity_change` |
| `friction` | 기대대로 안 됐다 | `rage_click`, `dead_click` |
| `session` | 경계 | `session_start`, `page_view`, `exit_summary` |

`friction` 만 깔때기 밖에 있다. 어느 단계에서든 새는 구멍이라서다.

### 2. 그 자리에 뭐가 있었나 — `content_kind`

`section_id` 는 화면 구조상의 이름이라 거기까지만 말해준다.
그런데 `about_product` 안에는 개요·성분·임상 근거·사용법이 같이 들어 있고,
구매 판단에서 하는 역할이 전혀 다르다. **"About the Product 를 40초 봤다"** 로는
성분을 본 건지 사용법을 본 건지 알 수 없다.

그래서 콘텐츠 종류를 따로 붙였다 (`data-log-content`).

| 값 | 어디 |
|---|---|
| `product_image` | 갤러리 |
| `price` · `variant_option` · `cta` | 구매 영역 |
| `what_it_is` · `what_else` | 상품 개요 |
| `ingredient_list` · `ingredient_callout` | 성분 (Highlighted / 전체 목록) |
| `clinical_claim` | Clinical Results |
| `usage_guide` | How to Use |
| `persona_match` | 내 피부 타입·고민과 맞는지 |
| `product_meta` | 카테고리·용량 |
| `user_review` · `review_stats` · `review_filter` | 리뷰 |
| `recommendation_card` | 추천 |
| `highlight_badge` · `navigation` | 배지, 브레드크럼 |

특정 대상이 있으면 `content_ref` 에 식별자를 같이 남긴다 (리뷰 ID, 추천 상품 ID 등).

체류도 섹션이 아니라 **이 블록 단위로** 잰다. 그래야
"임상 근거에서 오래 멈췄다" 같은 문장이 나온다.

레이아웃이 바뀌어도 과거 로그를 계속 읽을 수 있어야 하므로,
어느 값도 픽셀 좌표를 쓰지 않는다 (`frontend/src/lib/section.ts`).

## 화면당 콘텐츠 수를 줄였다

여기까지 해도 문제가 하나 남는다. **한 화면에 블록이 여러 개 겹쳐 보이면
그 체류가 어느 콘텐츠를 향한 건지 단정할 수 없다.**
성분과 사용법이 같이 떠 있는 화면에서 10초 머문 기록은 둘 다에 쌓인다.

그래서 두 가지를 했다.

**여백을 넓혔다.** 섹션 사이 `--space-7`(48px) → `--space-9`(104px),
About 안의 문단 사이 `--space-5`(24px) → `--space-8`(72px).
PC 기준 한 화면에 들어오는 블록이 줄어 귀속이 그만큼 깨끗해진다.
스크롤 양은 늘지만, 이 프로젝트는 상품을 파는 게 목적이 아니라
행동 데이터를 얻는 게 목적이라 그쪽을 택했다.

**남은 모호함은 로그에 적었다.** 여백만으로는 히어로 영역(이미지·가격·옵션·담기)처럼
좌우로 붙어 있는 구조를 못 없앤다. 그래서 숫자로 남긴다.

- `section_dwell.co_visible_blocks` — 머무는 동안 같이 떠 있던 블록 수의 최대치
- `scroll_pause.visible_content_kinds` — 멈춘 순간 함께 보이던 콘텐츠 종류

분석할 때 `co_visible_blocks <= 2` 인 건만 골라 쓰면 귀속이 확실한 표본이 된다.
측정해 보면 페이지 평균 3.9개/화면, 히어로 영역이 4개로 가장 밀집한다.

## 민감도를 어떻게 잡았나

스크롤은 초당 수백 번, mousemove 는 초당 15~60 번 발생해서 그대로 받으면 안 된다
([Nolan Lawson](https://nolanlawson.com/2019/08/11/high-performance-input-handling-on-the-web/)).
대신 **발생 빈도가 낮은 시점** 을 골라 붙였다. 멈췄을 때, 벗어났을 때, 손을 뗐을 때.

| 값 | 설정 | 이유 |
|---|---|---|
| `scroll_depth` 간격 | 25% → **10%** | 긴 페이지에서 25% 한 칸이 2000px 이라 너무 성겼다 |
| `scroll_pause` 판정 | **320ms** | 1초는 훑어보다 시선 두는 시간보다 길어 아무것도 안 남았다 |
| `scroll_pause` 최소 이동 | **24px** | 손떨림 제외 |
| `scroll_backtrack` | **240px** 역방향 | 실수 스크롤과 구분 |
| `section_view` 체류 | 1000ms → **400ms** | 실제로 읽은 섹션까지 놓치고 있었다 |
| `section_view` 노출 | ratio 0.5 → **면적 40% 또는 화면 35%** | 긴 섹션이 영원히 판정 안 되던 버그 |
| `section_dwell` 최소 | **700ms** | 스쳐 간 구간 제외 |
| `section_dwell` 중간 저장 | **15초** | 오래 머물다 이탈해도 유실 안 되게 |
| `text_selection` 확정 | **350ms** | 드래그 중 연속 발생 방지 |
| `hover_dwell` | **600ms** | 지나가는 커서 제외 |
| `rage_click` | **800ms 안 3회, 40px 이내** | 일반적인 더블클릭과 구분 |

대략적인 양은 **한 방문(1~2분)당 30~60건** 정도다. 초안의 5~10건에서 늘었지만
`logger.ts` 가 20건 단위 배치로 묶어 보내므로 요청 수는 몇 건 수준이다.

## 일부러 안 남기는 것

- **마우스 좌표 궤적** — 양 대비 얻는 게 적고, 세션 리플레이는 이 프로젝트 범위가 아니다.
- **사용자가 입력한 값** — 텍스트 선택 로그는 입력 요소(`input`, `textarea`,
  `contenteditable`)를 제외한다. 페이지에 이미 떠 있는 문구만 남긴다.
- **개별 스크롤 프레임** — 멈춘 지점만 남긴다.

## 데이터 담당자에게 확인 필요

1. `text_snippet` 을 그대로 적재할지, 해시나 성분 사전 매칭 결과만 남길지.
   지금은 140자까지 원문을 담고 있다.
2. `section_dwell` 이 한 섹션에 여러 건 쌓인다 (벗어날 때마다 1건).
   적재 후 합산할지, 프론트에서 방문당 1건으로 합쳐 보낼지.
3. `actor_type` 이 `synthetic` 인 부하 테스트 로그를 같은 테이블에 넣을지 분리할지.
4. 주목 이벤트(P1)를 P0 와 같은 보존 기간으로 둘지. 양이 6~10배 많다.
