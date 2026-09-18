# Event Properties 계약

작성일: 2026-09-03
상태: 통합 쇼핑몰 기준 v0.2 Properties와 상품 귀속 규칙 확정. 모듈별 구현 반영 대기
실행 Envelope 계약: [`event-schema.json`](./event-schema.json)
귀속 결정·영향 범위: [`event-attribution-contract.md`](./event-attribution-contract.md)
설계 설명: [`event-logging-design.md`](../docs/analytics/event-logging-design.md)

## 1. 범위와 우선순위

이 문서는 활성 Event의 intent 의미와 `properties` 필수값, 타입, enum 및 배열 구조를
정의하는 계약 원본이다. 공통 Envelope, 활성 `event_name`, 공통 intent enum과
synthetic runtime metadata는 `event-schema.json`을 실행 원본으로 사용한다.

두 계약이 충돌하면 JSON Schema가 검증하는 범위에서는 `event-schema.json`을
우선한다. Event별 properties는 이 문서를 기준으로 Collector 또는 Spark semantic
validation에서 검사한다.

표기 규칙:

- `required properties`의 키는 `properties` object에 반드시 존재해야 한다.
- `A 또는 B`는 두 키 중 하나 이상이 존재해야 한다.
- `string|null`은 키는 필수지만 값은 null일 수 있다는 뜻이다.
- 상품 자체가 대상인 Event와 상품 상세의 `page_view`·섹션·`scroll_depth`·
  `scroll_pause` Event는 top-level `product_id`가 필수다.
- 플랫폼 목록의 `section_view`·`section_dwell`·`scroll_depth`·`scroll_pause`는
  `product_id = NULL`을 허용한다.
  상품 미귀속은 빈 문자열이 아니라 JSON `null`로 표현한다.
- Planned Event는 `event-schema.json` enum에 등록되기 전까지 전송하지 않는다.

## 1.1 통합 쇼핑몰의 브랜드·상품 귀속

소비자 행동은 하나의 통합 쇼핑몰에서 발생하므로 Event를 Storefront Tenant로
격리하지 않는다. top-level Envelope에는 `tenant_id`, `brand_id`를
반복하지 않고, 상품에 귀속되는 Event의 `product_id`를 기준으로 Processed 단계에서
귀속을 파생한다. `product_id = NULL`인 플랫폼 공통 Event에는 이 Join을 적용하지
않는다.

```text
Event.product_id
→ dim_product.brand_id
```

| 값 | 위치 | 얻는 법 |
| --- | --- | --- |
| `product_id` | 상품 대상 Event의 top-level Envelope | Event가 직접 싣는다 |
| `brand_id` | Processed Fact·Mart | `product_id`를 `dim_product`와 Join해 파생 |

상품 상세 화면의 `page_view`, `section_view`, `section_dwell`, `scroll_depth`,
`scroll_pause`는 `product_id`가 필수다. 홈·검색·장바구니 등 플랫폼 공통 화면의
`page_view`와 상품 목록의 프로모션·필터·상품 그리드 전체를 측정하는
`section_view`, `section_dwell`, `scroll_depth`, `scroll_pause`는 특정 상품·브랜드에
귀속하지 않으며 `product_id = NULL`을 허용한다. 빈 문자열은
상품 미귀속을 뜻하지 않으며 모든 페이지에서 거부한다. 향후 상품 없이 브랜드 자체가
명시적 대상인 Event를 도입할 때만 `brand_id` 선택 필드를 별도 계약한다. route,
표시명, 직전 상품 또는 세션 내 상품으로 브랜드를 추정하지 않는다.

브랜드 대시보드의 데이터 접근 격리는 Event 필드가 아니라 Backend의
브랜드 계정과 `brand_id`의 1:1 관계 및 인가로 강제한다. Mart는 집계 시점의
`brand_id`를 조회 축으로 보존하지만 물리 partition은 별도 저장 계약에서
결정한다.

### 1.1.1 Schema version

실제 Producer가 사용 중인 `0.2.0-draft`를 유지한다. 통합몰 전환 전에 제안됐던
`0.3.0-draft`의 `tenant_id` 필수 계약은 Producer에 반영하지 않고 철회한다. 다음 버전은
실제 Envelope 구조가 추가로 변경될 때 새 계약으로 정의한다.

## 2. 활성 Event Taxonomy

아래 Event는 `event-schema.json`의 `event_name` enum과 intent 조건에 등록된 항목이다.

### 2.1 Session / Page

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `session_start` | `session` | 새 쇼핑 세션 시작 | 방문 수, 세션당 행동 수 |
| `login` | `session` | 세션 도중 로그인 성공 | 익명→계정 전환 시점 |
| `page_view` | `session` | 페이지·라우트 진입 | 페이지 방문, 이탈 분석 |
| `navigation_click` | `session` | 상품과 무관한 화면 이동 클릭 | 이동·이탈 경로 |
| `product_view` | `interest` | 상품 상세 진입 완료 | 상세 조회, Funnel 분모 |
| `exit_summary` | `session` | 페이지 이탈 요약 | 체류·이탈 구간 |

### 2.2 Product Exposure / Exploration

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `product_impression` | `exposure` | 상품 카드 유효 노출 또는 클릭·Quick Look으로 확정된 합성 노출 | 상품 CTR 분모 |
| `impression_dwell` | `exposure` | 유효 노출 카드의 체류시간 | 노출 품질 |
| `product_click` | `comparison` | 상품 카드 클릭 | 상품 CTR 분자 |
| `recommendation_impression` | `exposure` | 추천 카드 유효 노출 또는 추천 클릭으로 확정된 합성 노출 | 추천 CTR 분모 |
| `recommendation_snapshot` | `exposure` | 추천 목록 순위 스냅샷 | 위치 편향 분석 |
| `recommendation_click` | `comparison` | 추천 카드 클릭 | 추천 CTR 분자 |
| `banner_impression` | `session` | 히어로 배너 노출 또는 배너 클릭으로 확정된 합성 노출 | 배너 CTR 분모 |
| `banner_click` | `interest` | 히어로 배너 클릭 | 배너 CTR 분자 |
| `quick_look` | `interest` | 상품 요약 창 열림 | 상세 진입 전 관심 |
| `quick_look_close` | `interest` | 상품 요약 창 닫힘 | 요약 창 체류·행동 |
| `filter_change` | `comparison` | 상품 필터 변경 | 탐색 기준 |
| `sort_change` | `comparison` | 상품 정렬 변경 | 정렬 선호 |

### 2.3 Product Detail Engagement

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `section_view` | `interest` | 섹션·콘텐츠 유효 조회 | 정보 열람률 |
| `section_dwell` | `interest` | 섹션·콘텐츠 체류시간 | 콘텐츠 관심도 |
| `scroll_depth` | `exposure` | 스크롤 milestone 도달 | 탐색 깊이 |
| `scroll_pause` | `interest` | 스크롤 후 멈춤 | 관심 지점 |
| `scroll_backtrack` | `comparison` | 다시 위로 탐색 | 비교·재확인 |
| `media_view` | `interest` | 이미지·미디어 조회 | 이미지 관심도 |
| `variant_select` | `comparison` | 상품 옵션 선택 | 옵션 선호 |
| `accordion_toggle` | `validation` | 상세 정보 펼침·닫힘 | 정보 확인 의도 |
| `text_selection` | `validation` | 텍스트 선택 | 관심 문장·성분 |
| `text_copy` | `validation` | 텍스트 복사 | 강한 검증 의도 |

`section_view`, `section_dwell`, `scroll_depth`, `scroll_pause`는 상품 상세 콘텐츠뿐
아니라 상품 목록의 플랫폼 공통 탐색도 측정한다. 상품 상세에서는 `product_id`가
필수이고, 목록의 프로모션·필터·상품 그리드 전체 탐색에서는 `product_id = NULL`을
허용한다. 목록 탐색을 직전 상품이나 세션 내 상품에 귀속하지 않는다.

### 2.4 Review / Ingredient

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `review_expand` | `validation` | 리뷰 상세·리뷰 영역 이동 | 리뷰 열람률 |
| `review_filter_apply` | `validation` | 리뷰 필터·정렬 변경 | 리뷰 탐색 기준 |
| `ingredient_view_mode_change` | `validation` | 성분 표시 방식 변경 | 성분 상세 관심 |

### 2.5 Conversion / Friction

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `wishlist_toggle` | `conversion` | 찜 추가·해제 | 지속 관심 |
| `add_to_cart` | `conversion` | 장바구니 담기 | 장바구니 전환 |
| `view_cart` | `conversion` | 장바구니 화면 진입 | Cart 확인율 |
| `quantity_change` | `conversion` | 수량 변경 | 구매 의도 |
| `begin_checkout` | `conversion` | 주문 시작 | Checkout 진입 |
| `purchase` | `conversion` | 주문 완료 행동 로그 | 구매 전환. 매출·정산 근거로 사용하지 않음 |
| `payment_failed` | `conversion` | 결제창 실패·취소 | 전환 마찰. 어디서 이탈하는지의 마지막 칸 |
| `purchase_reason_select` | `validation` | 구매 직후 이유 선택 | 선언 이유와 행동 추론 대조 |
| `remove_from_cart` | `hesitation` | 장바구니 상품 제거 | 전환 마찰 |
| `hover_dwell` | `hesitation` | CTA hover 체류 | 구매 전 망설임 |
| `rage_click` | `friction` | 같은 지점 반복 클릭 | UI 마찰 |
| `dead_click` | `friction` | 클릭 불가 영역 클릭 | 기대 기능 부재 |

`payment_failed`의 intent가 `friction`이 아니라 `conversion`인 이유는, `friction`이
`rage_click`·`dead_click` 같은 **UI 마찰**을 가리키고 이쪽은 **전환 단계에서의 이탈**이기
때문이다. 주문 단위 Event라 top-level `product_id`는 없다.

이 Event는 현재 `cleaned_events`까지만 내려간다. `product_event_fact`는 상품 단위라
주문 단위 Event를 담지 않고, `funnel_session_fact`의 grain도 `session_id + product_id`라
그대로 넣을 수 없다. 결제 실패를 이탈 단계로 세려면 주문 단위 grain 설계가 필요하므로
실데이터가 쌓인 뒤에 다룬다.

## 3. Property Enum

### 3.1 `section_id`

`product_hero`, `highlights`, `about_product`, `ingredients`, `how_to_use`,
`similar_products`, `reviews`, `promo_row`, `list_controls`, `product_grid`,
`cart_items`

### 3.2 `content_kind`

`product_image`, `price`, `variant_option`, `cta`, `highlight_badge`, `what_it_is`,
`what_else`, `ingredient_list`, `ingredient_callout`, `clinical_claim`, `usage_guide`,
`brand_story`, `persona_match`, `product_meta`, `user_review`, `review_stats`,
`review_filter`, `recommendation_card`, `product_card`, `cart_item`, `navigation`

### 3.3 `entry_source`

`list_grid`, `promo_pick`, `similar_products`, `quick_look`, `cart`, `breadcrumb`

### 3.4 `navigation_source`

`session_start`, `in_app`, `history_back`, `direct`

세션 시작과 함께 발생한 첫 `page_view`는 `direct`보다 `session_start`를 우선한다.
같은 상세 진입의 `product_view.navigation_source`는 `page_view` 값과 같아야 한다.

### 3.5 `quick_look_close.close_reason`

`backdrop`, `escape`, `close_button`, `open_detail`

### 3.6 `selection_kind`

`ingredient`, `claim`, `usage`, `price`, `other`

선택·복사한 텍스트가 어떤 종류의 정보인지 분류한다. 원문은 전송하지 않으므로
`matched_ingredients`로 잡히지 않는 주장·사용법·가격 문구의 관심을 이 값으로만
구분할 수 있다.

### 3.7 `variant_kind`

`size`, `shade`, `other`

상품 원천의 `variation_type`을 매핑한다. `Size`는 `size`, `Color`는 `shade`,
그 외와 결측은 `other`다. 용량 선택과 색상 선택은 각각 재구매·톤 신호로 의미가
달라 구분한다.

`badge_id`는 표시 배지의 식별자이며 값 목록이 확정되지 않아 enum을 두지 않는다.

### 3.8 `filter_kind`

`category`, `concern`, `brand`, `price`

Front가 실제로 내보내는 값이며 `frontend/src/types/log.ts`의 `FilterKind` union이
단일 출처다. Generator도 `category`를 사용한다.

`brand`는 2026-09-17에 추가했다. 값은 `all` 또는 `brand_name` 그대로다. 쇼핑몰 목록이
여러 브랜드를 한 화면에 섞어 놓아서, 브랜드로 좁히는 자리가 없으면 등록 브랜드의 상품을
모아 볼 방법이 없다. Generator는 아직 이 값을 내지 않는다.

기피 성분 필터(`ingredient_exclude`)와 피부 타입 필터(`skin_type`)는 화면이 아직
없으므로 등록하지 않는다. 구현되지 않은 값을 미리 넣으면 이 표가 "무엇을 내보내는가"가
아니라 "무엇을 내보낼 수도 있는가"가 되어, 실제 수집 범위를 이 문서로 알 수 없게 된다.
화면이 생기면 계약을 먼저 고치고 구현을 올린다.

### 3.9 `purchase_reason_select.reasons`

`ingredient`, `skin_fit`, `reviews`, `review_same_skin`, `price`, `brand_trust`,
`texture_finish`, `clean_claim`, `recommendation`, `restock`

구매 직후 클릭 설문의 선택지다. `primary_reason`도 같은 값을 사용한다.

| 값 | 뜻 |
| --- | --- |
| `ingredient` | 성분이 마음에 들어서 |
| `skin_fit` | 내 피부 타입·톤에 맞아서 |
| `reviews` | 리뷰가 좋아서 |
| `review_same_skin` | 나와 같은 피부의 리뷰를 보고 |
| `price` | 가격이 맞아서 |
| `brand_trust` | 이 브랜드를 믿어서 |
| `texture_finish` | 제형·마감이 좋아서 |
| `clean_claim` | 무향·비건 등 성분 배제 조건 때문에 |
| `recommendation` | 추천을 받아서 |
| `restock` | 쓰던 것을 다시 사서 |

10개로 고정한다. 선택지가 늘면 응답이 흩어져 행동 추론과 대조할 표본이 줄어든다.

`restock`은 재구매의 **선언 신호**다. 행동으로 관측한 재구매와 교차 검증할 때
사용하며, 둘이 갈리는 구간이 행동 추론의 한계를 보여준다.

### 3.10 `review_expand.target`

`review_text`, `jump_to_reviews`, `ingredients`

`ingredients`는 리뷰 행동이 아니므로 리뷰 열람률은
`target in ('review_text', 'jump_to_reviews')`로 제한한다.

### 3.11 `banner_type`

`concern`, `ingredient`, `clean`, `price_bin`, `category`, `segment`, `new_brand`

### 3.12 `trait_source`

`session`, `profile`, `coldstart`, `explore`

`explore`는 성향 실험의 20% 탐색군 식별자다. 배정은 배너 노출 전에 FE 또는 추천
서비스가 하고, 같은 노출·클릭 쌍에는 같은 값을 싣는다. DATA는 배정하지 않고 비중과
노출·클릭 일치만 검증한다.

### 3.12-1 `impression_origin`

`observed`, `implied_by_click`

세 노출 Event(`product_impression`, `recommendation_impression`, `banner_impression`)의
선택 property다. 화면에서 정상 관측한 노출은 `observed`, 선행 노출 없이 클릭이 발생해
클릭 직전에 보강한 노출은 `implied_by_click`이다. 합성 노출은 대응 클릭과 같은 세션·
상품·노출 위치 식별자를 사용하며 CTR과 노출 분모에 포함한다.

**property가 없으면 `observed`로 간주한다.** 필수로 두면 Raw 전량이 `bad_events`로 빠지고
Front·수집기·시뮬레이터가 같은 시점에 배포돼야 하므로 선택으로 둔다. 값이 실려 있으면
enum을 강제한다.

**이 기본값은 마커 발행 이전 로그에 대해서만 사실이다.** 합성 노출 자체는 2026-09-18
프론트 머지(`useImpression.confirmImpressionByClick`)부터 이미 생기고 있고, 마커는 아직
실리지 않는다. 그 사이에 쌓이는 로그는 합성분도 기본값에 따라 `observed`로 잡히므로,
합성·관측 구분이 필요한 분석은 마커 발행 시점을 시작점으로 잡는다. 구분 없이 분모만
세는 지표(`impression_count`·CTR)는 이 공백의 영향을 받지 않는다 — 합성 노출도 분모에
포함하는 것이 계약이기 때문이다(`dw-schema.md` §4.1).

**소비하는 쪽은 이 property를 필수로 요구하지 않는다.** `event-schema.json`의 required,
Q2의 거절 조건, Q4의 집계 전제, Q5의 존재 검사 어디에도 넣지 않는다. 값이 없는 로그를
만드는 생산자가 정상이며(생성기는 가드로 합성 노출 자체를 만들지 않으므로 전부
`observed`다), 필수로 올리는 순간 그 로그가 전량 격리된다. 값의 타입·enum 검증은
실려 있을 때만 건다.

세 노출 Event는 공통 노출 Hook(`frontend/src/hooks/useImpression.ts`)을 쓰므로 `hold_ms`와
`visible_ratio`를 함께 싣는다. `banner_impression`도 2026-09-17 배너 전환 이후 같은 Hook을
탄다. 합성 노출은 실측 체류가 없어 `hold_ms: 0`을 싣는다.

`hold_ms`는 실측 체류가 아니라 노출로 인정한 **판정 임계값**이다(목록 300ms · 추천
1000ms 상수). 그래서 현재 구현에서는 관측 노출이 0을 싣는 경우가 없고, `hold_ms == 0`이
사실상 합성 노출과 일치한다. 그래도 **합성 판정에는 `impression_origin`만 쓴다.** 그
일치는 임계 상수가 마침 0이 아니어서 성립하는 것이지 계약이 보장하는 성질이 아니다.
임계값을 0으로 낮추거나 `hold_ms`를 실측값으로 바꾸는 순간 조용히 깨지고, 그때 이미
쌓인 집계는 되돌릴 수 없다. 마커가 실리기 전까지의 잠정 구분에만 `hold_ms == 0`을
쓰고, 그 사실을 분석 결과에 함께 적는다.

`visible_ratio`는 측정값이 아니라 노출로 인정하는 **판정 임계값**이다. 세 노출 Event 모두
`0.5` 상수이며 `IntersectionObserver`의 threshold와 같은 값을 그대로 싣는다. 카드가 실제로
얼마나 보였는지를 뜻하지 않으므로 노출 품질 지표나 가중치로 쓰지 않는다. 합성 노출도 같은
상수를 싣되, 클릭으로 확정한 노출은 가시성 검사를 거치지 않았다는 사실을 `impression_origin`
이 대신 말한다.

### 3.13 배너 값과 slot 규칙

`banner_slot`은 1 이상의 정수다. 추천 API 응답의 `slot`은 Event 발행 시 이 이름으로
변환하며 Event properties의 `slot`은 허용하지 않는다.

`banner_value`는 `product-feature-vocab.json` 또는 `affinity_lift.csv`의 원문
문자열이다. `banner_type`이 `new_brand`일 때만 JSON `null`이며, 나머지 축에서는 비어
있지 않은 문자열이다. 한국어 표시 라벨은 소비 시점에 붙이고 Event·Fact·Mart에는
넣지 않는다.

배너 대상 `product_id`는 다른 상품 Event와 같이 top-level Envelope에 둔다. Front 로거가
호출부의 `properties.product_id`를 top-level로 승격하므로 properties에 중복 저장하지 않는다.

`policy_version`은 배너·정렬 정책의 배포 버전이다. 사전/사후 비교의 귀속 키이므로
배너 Event에 실으면 `banner_daily`까지 그대로 내려간다.

### 3.14 시뮬레이션 시드 표식 `seeded`

생성기가 Persona의 사전 선호를 추천기에 주입하려고 만드는 Event에 `seeded: true`를
싣는다 (`persona-schema.md` §9). 관측된 행동이 아니라 **주입된 선호 표식**이다.

| property | type | 값 | 설명 |
| --- | --- | --- | --- |
| `seeded` | boolean | `true` | 시드 Event가 싣는다. 관측 Event는 키를 두지 않으며, `false`가 와도 관측으로 본다 |

타입은 `event-schema.json`이 강제한다. `actor_type='synthetic'` 블록에 `boolean`으로
선언했고, `actor_type='user'` 블록은 이 키를 금지한다. 문자열 `"true"`처럼 타입이
흔들리면 Spark의 `is_seeded` 판정이 조용히 달라지므로 봉투 검증에서 먼저 막는다.

시드 Event의 `session_id`는 `seed:{simulation_run_id}:{persona_id}:{product_id}`
형식이라 세션 네임스페이스로도 갈라지지만, **판정은 `properties.seeded`를 정본으로
한다.** `session_id` 규칙은 파생이고 생성기가 먼저 찍는 표식이 이 키다.

긍정 시드는 조회 없이 `add_to_cart`만, 부정 시드는 장바구니 없는 `product_view`와
`scroll_backtrack`·`rage_click`을 낸다. 그래서 퍼널 전환 지표에 그대로 섞이면 분자와
분모를 **양방향으로** 왜곡한다. 행동 Mart에서의 처리는 §7-8과 `dw-schema.md`를 따른다.

`actor_type='user'` Event에는 이 키가 올 수 없다.

### 3.15 `payment_method`

`kakaopay`, `card`, `test`

| 값 | 뜻 |
| --- | --- |
| `kakaopay` | PortOne 경유 카카오페이 결제 |
| `card` | 카드 결제 |
| `test` | 결제 PG를 타지 않은 시연용 주문 |

`purchase`와 `payment_failed`가 같은 값을 쓴다. 실패 Event에서는 선택 키다 — 결제수단을
고르기 전에 창을 닫으면 값이 없다.

`test`는 결제수단 분포에서 실제 수단과 함께 세지 않는다. 시연 주문을 섞으면
결제수단 선호가 시연 횟수에 따라 흔들린다.

### 3.16 `order_channel`

`backend`, `local`

| 값 | 뜻 |
| --- | --- |
| `backend` | Backend 주문 API를 거쳐 생성된 주문 |
| `local` | 브라우저에서만 만든 주문. Backend에 주문 row가 없다 |

`local`은 화면 시연 경로다. Backend 주문과 대사(對査)할 수 없으므로 매출성 집계에서
제외한다 ([`dw-schema.md`](./dw-schema.md) §6). 이 축이 없으면 시연 주문과 실제 주문이
한 덩어리가 되어 전환 지표가 시연 횟수만큼 부풀어 오른다.

## 4. Event별 Required Properties

### 4.1 Session / Page

| event_name | required properties | optional properties |
| --- | --- | --- |
| `session_start` | 없음 | `entry_page: string`, `referrer: string`, `utm_source: string`, `utm_medium: string`, `utm_campaign: string` |
| `login` | 없음 | 없음 |
| `page_view` | 없음 | `referrer: string`, `route: string`, `navigation_source: string` |
| `navigation_click` | `target: string`, `entry_source: string` | 없음 |
| `product_view` | `navigation_source: string` | `list_id: string`, `position: integer`, `recommendation_id: string`, `context_product_id: string` |
| `exit_summary` | `dwell_ms: integer`, `max_scroll_percent: number` | `last_section_id: string`, `last_content_kind: string`, `reason: string` |

### 4.2 Product Exposure / Exploration

| event_name | required properties | optional properties |
| --- | --- | --- |
| `banner_impression` | `banner_type: string`, `banner_value: string\|null`, `banner_slot: integer`, `trait_source: string`; top-level `product_id` 필수 | `policy_version: string`, `impression_origin: string`, `list_id: string`, `position: integer`, `hold_ms: integer`, `visible_ratio: number`, `algorithm: string`, `recommendation_id: string` |
| `banner_click` | `banner_type: string`, `banner_value: string\|null`, `banner_slot: integer`, `trait_source: string`; top-level `product_id` 필수 | `policy_version: string` |
| `product_impression` | `list_id: string`, `position: integer`, `hold_ms: integer`, `visible_ratio: number` | `impression_area: string`, `dedupe_key: string`, `impression_origin: string` |
| `product_click` | 없음 | `list_id: string`, `position: integer`, `entry_source: string`, `impression_event_id: string`, `context_product_id: string` |
| `recommendation_impression` | `recommendation_id: string`, `list_id: string`, `position: integer`, `algorithm: string`, `hold_ms: integer`, `visible_ratio: number` | `section_id: string`, `context_product_id: string`, `impression_origin: string` |
| `recommendation_click` | `recommendation_id: string`, `list_id: string`, `position: integer`, `algorithm: string` | `section_id: string`, `impression_event_id: string`, `context_product_id: string` |
| `impression_dwell` | `list_id: string`, `position: integer`, `visible_ms: integer` | `recommendation_id: string`, `algorithm: string`, `context_product_id: string` |
| `recommendation_snapshot` | `recommendation_id: string`, `list_id: string`, `algorithm: string`, `size: integer`, `ranking: object[]` | 없음 |
| `quick_look` | `entry_source: string`, `position: integer` | `list_id: string`, `recommendation_id: string`, `algorithm: string`, `context_product_id: string` |
| `quick_look_close` | `close_reason: string`, `dwell_ms: integer`, `variants_viewed: integer`, `added_to_cart: boolean`, `wishlisted: boolean` | `list_id: string`, `position: integer`, `entry_source: string` |
| `filter_change` | `filter_kind: string`, `filter_value: string` | `from: string`, `result_count: integer`, `filter_action: string`, `filter_values: string[]` |
| `sort_change` | `sort_key: string` | `sort_direction: string`, `result_count: integer` |

### 4.3 Detail Engagement

| event_name | required properties | optional properties |
| --- | --- | --- |
| `section_view` | `section_id: string` 또는 `content_kind: string` | `content_ref: string`, `visible_duration_ms: integer`, `visible_ratio: number`, `badge_id: string` |
| `section_dwell` | `section_id: string` 또는 `content_kind: string`, `dwell_ms: integer` | `content_ref: string`, `co_visible_blocks: integer`, `reason: string`, `badge_id: string` |
| `scroll_depth` | `depth_percent: number` | `section_id: string`, `content_kind: string` |
| `scroll_pause` | `depth_percent: number`, `direction: string`, `distance_px: number`, `duration_ms: integer` | `section_id: string`, `content_kind: string`, `visible_content_kinds: string[]`, `velocity_px_per_sec: number` |
| `scroll_backtrack` | `depth_percent: number`, `distance_px: number` | `section_id: string`, `content_kind: string` |
| `media_view` | `media_type: string`, `media_index: integer` | `media_id: string`, `image_url_hash: string` |
| `accordion_toggle` | `section_id: string`, `action: string` | `content_kind: string` |
| `text_selection` | `text_length: integer` | `section_id: string`, `content_kind: string`, `content_ref: string`, `truncated: boolean`, `selection_kind: string`, `matched_ingredients: string[]`, `matched_keywords: string[]`, `matched_count: integer`, `vocab_version: string` |
| `text_copy` | `text_length: integer` | `section_id: string`, `content_kind: string`, `content_ref: string`, `truncated: boolean`, `selection_kind: string`, `matched_ingredients: string[]`, `matched_keywords: string[]`, `matched_count: integer`, `vocab_version: string` |

`text_snippet` 원문은 전송하지 않는다.

### 4.4 Review / Ingredient

| event_name | required properties | optional properties |
| --- | --- | --- |
| `review_expand` | `target: string` | `review_id: string`, `section_id: string`, `revealed_count: integer` |
| `review_filter_apply` | `filter: string` 또는 `sort: string` | `result_count: integer`, `persona_skin_type: string`, `persona_skin_tone: string` |
| `ingredient_view_mode_change` | `mode: string` | `ingredient_id: string`, `ingredient_name: string`, `ingredient_group: string` |

### 4.5 Conversion / Friction

| event_name | required properties | optional properties |
| --- | --- | --- |
| `wishlist_toggle` | `action: string` | `sku_id: string` |
| `add_to_cart` | `quantity: integer` | `sku_id: string`, `unit_price: number`, `currency: string`, `entry_source: string`, `context_product_id: string`, `price_usd: number` (**deprecated**) |
| `remove_from_cart` | `quantity: integer`, `cart_size_after: integer` | `sku_id: string`, `reason: string`, `cart_value: number`, `unit_price: number`, `currency: string`, `price_usd: number` (**deprecated**) |
| `view_cart` | `item_count: integer`, `distinct_products: integer`, `cart_value: number`, `currency: string` | `navigation_source: string` |
| `quantity_change` | `quantity: integer` | `sku_id: string`, `entry_source: string` |
| `begin_checkout` | `items: object[]`, `currency: string` | `cart_value: number`, `client_order_id: string` |
| `purchase` | `order_id: string`, `items: object[]`, `payment_method: string`, `paid_value: number`, `order_channel: string`, `currency: string` | `order_value: number`, `client_order_id: string`, `pg_provider: string`, `payment_id: string`, `paid_at: string` |
| `payment_failed` | `order_id: string` | `reason_code: string`, `payment_method: string`, `client_order_id: string` |
| `purchase_reason_select` | `order_id: string`, `reasons: string[]` | `primary_reason: string`, `free_text_kind: string`, `skipped: boolean` |
| `variant_select` | `sku_id: string`, `label: string` | `previous_sku_id: string`, `variant_group: string`, `variant_kind: string` |
| `hover_dwell` | `dwell_ms: integer`, `action: string\|null` | `section_id: string`, `content_kind: string` |
| `rage_click` | `click_count: integer` | `action: string\|null`, `section_id: string`, `content_kind: string` |
| `dead_click` | `target_tag: string\|null` | `section_id: string`, `content_kind: string` |

**`client_order_id`는 프론트가 만드는 주문 번호다** (2026-09-17, 프론트 !304).
`purchase.order_id`는 서버가 발급하는 UUID라 `begin_checkout` 시점에는 아직 없다.
그래서 두 Event를 이어 붙일 키가 없었고, **"확인까지 갔다가 안 산 세션"**을 셀 수
없었다. 이 값은 세 Event(`begin_checkout`·`purchase`·`payment_failed`)에 같은 값으로
실려 그 조인을 가능하게 한다.

**서버 `order_id`를 대체하지 않는다.** 정산·주문 조회의 정본은 여전히 `order_id`이고,
`client_order_id`는 **행동 분석에서 한 주문 흐름을 잇는 용도**다. 프론트가 만드는 값이라
서버 주문과 1:1이 보장되지 않는다 — 결제창을 닫았다 다시 열면 새 값이 나올 수 있다.

**금액의 정본 통화는 원화이고 이름은 `unit_price`로 확정했다** (S15P21A306-303,
2026-09-16 프론트 합의). 신규 Producer는 담기·빼기에 `unit_price`와
`currency="KRW"`를 함께 싣고 `price_usd`를 보내지 않는다. `view_cart`·
`begin_checkout`·`purchase`의 `cart_value`·`order_value`·`paid_value` 및
`items[].unit_price`도 모두 원화이며 `currency="KRW"`다.

`price_usd`는 과거 로그를 읽기 위한 **deprecated 입력**으로만 당분간 허용한다.
`unit_price`와 함께 보내지 않는다. Processed는 전환 기간에 `unit_price`를 먼저 보고
없으면 `price_usd`로 떨어지지만 Fact 컬럼은 계속 `unit_price` 하나다
(`dw-schema.md` §3.2). 원화 로그 재생성 및 전환 검증이 끝나면 이 폴백을 제거한다.

## 5. 배열과 Object 구조

| property | type | required child fields | 설명 |
| --- | --- | --- | --- |
| `ranking[]` | object[] | `product_id: string`, `position: integer` | 추천 스냅샷 상품 순위 |
| `matched_ingredients[]` | string[] | 해당 없음 | 정규화된 성분 ID 또는 이름 |
| `matched_keywords[]` | string[] | 해당 없음 | 정규화된 분석 키워드 |
| `items[]` | object[] | `product_id: string`, `quantity: integer`, `unit_price: number` | 주문 상품. `sku_id: string`은 선택 |
| `reasons[]` | string[] | 해당 없음 | §3.9 enum. 1~2개, `skipped=true`면 빈 배열 |

`items[]`는 전환 분석용 `unit_price`를 싣을 수 있지만 매출·정산의 정본이 아니다. 상품별 매출은
`item_revenue = quantity * unit_price`는 Processed에서 파생하며 Event가 직접
운반하지 않는다. 파생값을 Event에 실으면 단가가 사라져 가격 분석을 할 수 없고,
`order_value`와 합계가 어긋났을 때 어느 쪽이 맞는지 판단할 근거도 없어진다.

`purchase.order_value`는 주문 전체 금액이다. `items[]`를 상품 row로 explode한 뒤
행동 Event가 아니라 Backend의 PAID 주문 상품 Fact에서만 합산한다
([`dw-schema.md`](./dw-schema.md) §6).

`paid_value`는 할인을 적용한 **실결제액**이고 `order_value`는 할인 전 주문 금액이다.
둘은 다를 수 있고, 다른 것이 정상이다. 전환의 금액 축은 `paid_value`를 쓴다 —
`order_value`로 보면 쿠폰·프로모션이 붙은 주문이 실제보다 크게 잡힌다. 다만 둘 다
행동 로그가 운반하는 값이라 매출·정산의 정본은 아니다(§4 앞 단락과 같은 이유).

`pg_provider` · `payment_id` · `paid_at`은 **키를 생략한다.** `null`을 싣지 않는다.
셋 다 결제 confirm 을 거쳐야 생기는 값인데, 시연 경로의 주문은 confirm 을 건너뛴다.
필수로 두면 그 purchase 가 전부 봉투 검증에서 거절된다. `null`을 허용하면 "confirm 을
안 거쳤다"와 "값이 유실됐다"가 구분되지 않으므로, 없으면 키 자체를 두지 않는다.

`payment_failed`는 주문 단위라 `product_id`를 갖지 않는다. `cleaned_events`까지만
내려가고 상품 grain 의 Fact 로는 파생하지 않는다 — 실패에는 상품 축이 없다.

`purchase_reason_select`는 주문 하나당 한 번만 발생한다. `reasons` 키는 항상
존재해야 하며, 사용자가 설문을 건너뛰면 `skipped=true`와 함께 빈 배열을 보낸다.
건너뛴 것과 응답이 유실된 것을 구분해야 응답률을 셀 수 있기 때문이다. 건너뛰지
않았다면 1~2개다.

자유 입력 원문은 전송하지 않고 분류값 `free_text_kind`만 남긴다.

`section_dwell.dwell_ms`는 누적값이 아니라 구간 체류시간 delta다. 여러 Event는
Processed에서 합산한다. `quick_look_close.dwell_ms`는 `variants_viewed`,
`added_to_cart`, `wishlisted`와 함께 해석한다.

## 6. Planned Event

다음 항목은 아직 활성 계약이 아니다.

| event_name | 예정 intent | 도입 조건 | properties 초안 |
| --- | --- | --- | --- |
| `search` | `comparison` | 검색 화면·Trigger 구현 | `query_text: string`; 선택 `result_count`, `normalized_query` |
| `compare_products` | `comparison` | 비교 기능 구현 | `compared_product_ids: string[]`; 선택 `base_product_id`, `compare_count` |

`begin_checkout`, `purchase`, `purchase_reason_select`는 활성 Event로 이동했다.
§2.5와 §4.5를 따른다.

## 6-2. 공통 선택 properties: 쇼핑몰 진열 (`storefront_*`)

브랜드마다 쇼핑몰 진열이 달라져서(가입 때 소상공인이 고른다) **모든 Event**의
`properties`에 진열 정보가 실린다. 검증 대상이 아닌 **선택 항목**이다.

| key | 값 | 뜻 |
| --- | --- | --- |
| `storefront_layout` | `grid` \| `showcase` \| `catalog` \| `list` | 상품 배열 |
| `storefront_promo` | `top` \| `side` \| `bottom` \| `off` | 기획전 섹션 위치 |
| `storefront_density` | `airy` \| `cozy` \| `compact` | 카드 크기·열 수 |
| `storefront_corner` | `sharp` \| `soft` \| `round` | 모서리 |
| `storefront_card` | `line` \| `shadow` \| `plain` | 카드 표면 |
| `storefront_font` | `sans` \| `serif` \| `wide` | 글꼴 |
| `storefront_theme` | `bloom` `rose` `coral` `lavender` `mint` `earth` `sand` `clinic` `mono` | 색 |

규칙:

1. `event-schema.json`은 바뀌지 않는다. `properties`가 열린 object이므로
   (`"properties": {"type": "object"}`) 기존 검증기·Collector·소비자가 그대로 통과한다.
2. **required가 아니다.** 없다고 격리하지 않는다. 쇼핑몰 화면이 아닌 출처(시뮬레이터
   등)에서는 비어 있을 수 있다.
3. 호출부가 같은 키를 이미 실었으면 덮지 않는다 (synthetic runtime metadata와 같은 규칙).
4. 화면 구조를 바꾸는 축은 `layout`·`promo`·`density` 셋이다. 나머지 넷은 겉모습만
   바꾼다. 진열별 지표를 비교할 때는 앞의 셋을 기준으로 묶는 것이 의미가 있다.

해석 주의:

- `storefront_promo='off'`인 브랜드는 기획전 섹션 자체가 없다. `promo_pick` 목록의
  `product_impression`이 0이므로 CTR 분모가 0이다. 브랜드 간 평균을 낼 때 제외한다.
- 상품 상세의 `section_dwell`·`scroll_depth` 분포는 진열에 따라 달라진다. 브랜드를
  가로질러 비교할 때는 진열을 통제 변수로 넣어야 한다. 상품 목록의 미귀속
  `section_dwell`은 브랜드 비교에 사용하지 않는다.
- 반대로 `section_id`·`content_kind` 목록은 진열이 바뀌어도 **변하지 않는다**.
  로그는 좌표가 아니라 의미(`data-log-section` / `data-log-content`)에 묶여 있고,
  진열은 CSS 자리 이동으로만 구현되기 때문이다. 기존 집계는 그대로 유효하다.

## 7. Semantic Validation

1. 활성 Event의 intent가 `event-schema.json` 조건과 일치해야 한다.
2. §4의 required properties와 §3 enum을 검사한다.
3. 상품 자체가 대상인 Event와 `page_type='product_detail'`인 `page_view`,
   `section_view`, `section_dwell`의 top-level `product_id`는 비어 있지 않은
   string이어야 한다. 플랫폼 목록의 두 섹션 Event는 JSON `null`을 허용하지만 빈
   문자열은 허용하지 않는다.
4. `actor_type='synthetic'`이면 `scenario_id`, `simulation_run_id`,
   `generator_type`이 필요하다. 이 공통 규칙은 JSON Schema에서도 검사한다.
5. `actor_type='user'`에 synthetic runtime metadata가 있으면 경고하고 분석에는
   사용하지 않는다.
6. Collector가 동기 검증한 위반 Event는 Kafka에 발행하지 않는다. HTTP `202`의
   `rejections`와 Collector 구조화 로그·메트릭으로만 기록한다. Kafka에 발행된 Event를
   Spark가 추가 검증하다 위반을 발견한 경우에만 `bad_events`에 격리한다. 한 Event에 여러
   위반이 있으면 원인을 모두 기록하되 대표 `error_code`는 표의 우선순위를 따른다.
7. Collector는 `begin_checkout`, `purchase`, `payment_failed`,
   `purchase_reason_select`의 required key, 타입, 양수 수량·가격, `reasons` 길이 및
   enum을 동기 검증한다. `purchase`의 `payment_method`·`order_channel` enum과
   `paid_value` 부호도 여기에 포함된다. 이 밖의 Event별 properties는 Spark가
   방어적으로 검사한다.
8. `properties.seeded=true`(§3.14)인 Event는 주입된 선호 표식이라 관측 행동이 아니다.
   Spark는 `cleaned_events`에 그대로 보존하되 행동 Mart 집계에서 제외한다. 어느 Mart가
   제외 대상인지는 `dw-schema.md`가 정본이다. `actor_type='user'`에 이 키가 오면
   위반으로 보고 분석에 쓰지 않는다.

| 우선순위 | error_code | 판정 기준 |
| --- | --- | --- |
| 1 | `event_intent_mismatch` | 활성 `event_name`과 `intent` 조합 불일치 |
| 2 | `missing_required_property` | §4 필수 key 또는 `A 또는 B` 조건 누락 |
| 3 | `invalid_property_type` | §4·§5에 선언된 타입과 실제 JSON 타입 불일치 |
| 4 | `invalid_property_enum` | §3에 선언된 허용값 밖의 값 사용 |

`properties`에 계약 표에 없는 key가 존재하는 것만으로 Event를 격리하지 않는다.
다만 공통 분석 필드로 사용할 key는 이 문서에 타입과 의미를 먼저 추가한다.

`coverage_report.py`는 이 문서의 §3·§4를 직접 읽어 required property, 타입 및 enum을
검사한다. 정상·오류 예시는 `samples/event-properties.valid.json`과
`samples/event-properties.invalid.json`에 둔다.

현재 구현과의 차이 및 E2E 확인 대상은 `event-logging-design.md`에서 추적한다.
