# Event Properties 계약

작성일: 2026-09-03
상태: v0.2 Properties 기준 확정, `0.3.0-draft` Tenant 필드와 구매 Event 3종 추가. 모듈별 구현 반영 대기
실행 Envelope 계약: [`event-schema.json`](./event-schema.json)
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
- 상품 대상 Event의 top-level `product_id`는 필수다.
- Planned Event는 `event-schema.json` enum에 등록되기 전까지 전송하지 않는다.

## 1.1 Tenant와 상품 브랜드는 다른 값이다

`schema_version = 0.3.0-draft`부터 top-level `tenant_id`가 필수다. 두 값을 혼동하면
격리가 깨지므로 여기서 경계를 명시한다.

| 값 | 뜻 | 위치 | 얻는 법 |
| --- | --- | --- | --- |
| `tenant_id` | 이 Storefront가 **누구 것인가** | top-level Envelope | Event가 직접 싣는다 |
| `brand_id` | 그 Event가 **무엇을 대상으로 했나**의 상품 브랜드 | Processed 컬럼 | `product_id` → `dim_product` Join 파생 |

`brand_id`를 Envelope에 넣지 않는 이유는 `page_view`, `filter_change`처럼 상품이 없는
Event에서 값이 정해지지 않기 때문이다. 그런 Event도 어느 Storefront에서 일어났는지는
정해지므로 격리 키는 `tenant_id`여야 한다. 데이터 격리와 Mart partition은
`tenant_id`만 사용한다.

### 1.1.1 `tenant_id` 형식

소문자 영숫자와 하이픈만 사용하는 slug다. 정규식은 `^[a-z0-9]+(-[a-z0-9]+)*$`이며
`event-schema.json`이 직접 검사한다.

생성 규칙은 표시명을 NFKD 정규화해 악센트를 제거하고 ASCII로 접은 뒤, 영숫자가 아닌
구간을 하이픈으로 바꾸고 앞뒤 하이픈을 제거하는 것이다.

```text
Estée Lauder → estee-lauder
Lancôme      → lancome
Dr. Jart+    → dr-jart
```

악센트를 떼지 않으면 `est-e-lauder`처럼 파티션 경로가 깨져 보인다.

**slug는 한 번 생성해 Tenant Dimension에 고정하고 조회할 때마다 다시 계산하지 않는다.**
정규화 규칙을 바꾸거나 표시명이 바뀌면 partition이 조용히 갈라지기 때문이다. 충돌이
발생하면 뒤에 순번을 붙인다. 화면 표시는 `tenant_id`가 아니라 Dimension의 표시명을
사용한다.

Tenant를 다른 Tenant에게 보일 때는 `tenant_id`가 아니라 되돌릴 수 없는 가명을
사용한다. 같은 값을 쓰면 익명 집계에서 경쟁 Tenant의 식별자가 그대로 노출된다.
Dimension 정의는 [`dw-schema.md`](./dw-schema.md)를 따른다.

### 1.1.2 Schema version 전환

`event-schema.json`의 `schema_version`은 `0.2.0-draft`와 `0.3.0-draft`를 모두 허용하며,
`0.3.0-draft`일 때만 `tenant_id`를 필수로 검사한다. 모듈은 준비되는 대로 각자 버전을
올리면 되고 동시에 이동하지 않아도 된다. 두 버전이 Raw에 섞여도 `schema_version`으로
구분한다.

## 2. 활성 Event Taxonomy

아래 Event는 `event-schema.json`의 `event_name` enum과 intent 조건에 등록된 항목이다.

### 2.1 Session / Page

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `session_start` | `session` | 새 쇼핑 세션 시작 | 방문 수, 세션당 행동 수 |
| `page_view` | `session` | 페이지·라우트 진입 | 페이지 방문, 이탈 분석 |
| `navigation_click` | `session` | 상품과 무관한 화면 이동 클릭 | 이동·이탈 경로 |
| `product_view` | `interest` | 상품 상세 진입 완료 | 상세 조회, Funnel 분모 |
| `exit_summary` | `session` | 페이지 이탈 요약 | 체류·이탈 구간 |

### 2.2 Product Exposure / Exploration

| event_name | intent | 의미 | 주요 활용 |
| --- | --- | --- | --- |
| `product_impression` | `exposure` | 상품 카드 유효 노출 | 상품 CTR 분모 |
| `impression_dwell` | `exposure` | 유효 노출 카드의 체류시간 | 노출 품질 |
| `product_click` | `comparison` | 상품 카드 클릭 | 상품 CTR 분자 |
| `recommendation_impression` | `exposure` | 추천 카드 유효 노출 | 추천 CTR 분모 |
| `recommendation_snapshot` | `exposure` | 추천 목록 순위 스냅샷 | 위치 편향 분석 |
| `recommendation_click` | `comparison` | 추천 카드 클릭 | 추천 CTR 분자 |
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
| `purchase` | `conversion` | 주문 완료 | 구매 전환, 매출 |
| `purchase_reason_select` | `validation` | 구매 직후 이유 선택 | 선언 이유와 행동 추론 대조 |
| `remove_from_cart` | `hesitation` | 장바구니 상품 제거 | 전환 마찰 |
| `hover_dwell` | `hesitation` | CTA hover 체류 | 구매 전 망설임 |
| `rage_click` | `friction` | 같은 지점 반복 클릭 | UI 마찰 |
| `dead_click` | `friction` | 클릭 불가 영역 클릭 | 기대 기능 부재 |

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

`category`, `concern`, `price`

Front가 실제로 내보내는 값이며 `frontend/src/types/log.ts`의 `FilterKind` union이
단일 출처다. Generator도 `category`를 사용한다.

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

## 4. Event별 Required Properties

### 4.1 Session / Page

| event_name | required properties | optional properties |
| --- | --- | --- |
| `session_start` | 없음 | `entry_page: string`, `referrer: string`, `utm_source: string`, `utm_medium: string`, `utm_campaign: string` |
| `page_view` | 없음 | `referrer: string`, `route: string`, `navigation_source: string` |
| `navigation_click` | `target: string`, `entry_source: string` | 없음 |
| `product_view` | `navigation_source: string` | `list_id: string`, `position: integer`, `recommendation_id: string`, `context_product_id: string` |
| `exit_summary` | `dwell_ms: integer`, `max_scroll_percent: number` | `last_section_id: string`, `last_content_kind: string`, `reason: string` |

### 4.2 Product Exposure / Exploration

| event_name | required properties | optional properties |
| --- | --- | --- |
| `product_impression` | `list_id: string`, `position: integer`, `hold_ms: integer`, `visible_ratio: number` | `impression_area: string`, `dedupe_key: string` |
| `product_click` | 없음 | `list_id: string`, `position: integer`, `entry_source: string`, `impression_event_id: string`, `context_product_id: string` |
| `recommendation_impression` | `recommendation_id: string`, `list_id: string`, `position: integer`, `algorithm: string`, `hold_ms: integer`, `visible_ratio: number` | `section_id: string`, `context_product_id: string` |
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
| `add_to_cart` | `quantity: integer` | `sku_id: string`, `price_usd: number`, `unit_price: number`, `currency: string`, `entry_source: string`, `context_product_id: string` |
| `remove_from_cart` | `quantity: integer`, `cart_size_after: integer` | `sku_id: string`, `reason: string`, `cart_value: number`, `price_usd: number` |
| `view_cart` | `item_count: integer`, `distinct_products: integer`, `cart_value: number` | `navigation_source: string` |
| `quantity_change` | `quantity: integer` | `sku_id: string`, `entry_source: string` |
| `begin_checkout` | `items: object[]` | `cart_value: number`, `currency: string` |
| `purchase` | `order_id: string`, `items: object[]` | `order_value: number`, `currency: string` |
| `purchase_reason_select` | `order_id: string`, `reasons: string[]` | `primary_reason: string`, `free_text_kind: string`, `skipped: boolean` |
| `variant_select` | `sku_id: string`, `label: string` | `previous_sku_id: string`, `variant_group: string`, `variant_kind: string` |
| `hover_dwell` | `dwell_ms: integer`, `action: string\|null` | `section_id: string`, `content_kind: string` |
| `rage_click` | `click_count: integer` | `action: string\|null`, `section_id: string`, `content_kind: string` |
| `dead_click` | `target_tag: string\|null` | `section_id: string`, `content_kind: string` |

## 5. 배열과 Object 구조

| property | type | required child fields | 설명 |
| --- | --- | --- | --- |
| `ranking[]` | object[] | `product_id: string`, `position: integer` | 추천 스냅샷 상품 순위 |
| `matched_ingredients[]` | string[] | 해당 없음 | 정규화된 성분 ID 또는 이름 |
| `matched_keywords[]` | string[] | 해당 없음 | 정규화된 분석 키워드 |
| `items[]` | object[] | `product_id: string`, `quantity: integer`, `unit_price: number` | 주문 상품. `sku_id: string`은 선택 |
| `reasons[]` | string[] | 해당 없음 | §3.9 enum. 1~2개, `skipped=true`면 빈 배열 |

`items[]`는 `unit_price`를 싣고 매출액을 싣지 않는다. 상품별 매출
`item_revenue = quantity * unit_price`는 Processed에서 파생하며 Event가 직접
운반하지 않는다. 파생값을 Event에 실으면 단가가 사라져 가격 분석을 할 수 없고,
`order_value`와 합계가 어긋났을 때 어느 쪽이 맞는지 판단할 근거도 없어진다.

`purchase.order_value`는 주문 전체 금액이다. `items[]`를 상품 row로 explode한 뒤
합산하면 상품 수만큼 중복되므로, 상품 매출은 `item_revenue`만 합산한다
([`dw-schema.md`](./dw-schema.md) §6).

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
- `section_dwell`·`scroll_depth`의 분포는 진열에 따라 달라진다. 브랜드를 가로질러
  비교할 때는 진열을 통제 변수로 넣어야 한다.
- 반대로 `section_id`·`content_kind` 목록은 진열이 바뀌어도 **변하지 않는다**.
  로그는 좌표가 아니라 의미(`data-log-section` / `data-log-content`)에 묶여 있고,
  진열은 CSS 자리 이동으로만 구현되기 때문이다. 기존 집계는 그대로 유효하다.

## 7. Semantic Validation

1. 활성 Event의 intent가 `event-schema.json` 조건과 일치해야 한다.
2. §4의 required properties와 §3 enum을 검사한다.
3. 상품 대상 Event의 top-level `product_id`가 존재해야 한다.
4. `actor_type='synthetic'`이면 `scenario_id`, `simulation_run_id`,
   `generator_type`이 필요하다. 이 공통 규칙은 JSON Schema에서도 검사한다.
5. `actor_type='user'`에 synthetic runtime metadata가 있으면 경고하고 분석에는
   사용하지 않는다.
6. Collector가 동기 검증한 위반 Event는 Kafka에 발행하지 않는다. HTTP `202`의
   `rejections`와 Collector 구조화 로그·메트릭으로만 기록한다. Kafka에 발행된 Event를
   Spark가 추가 검증하다 위반을 발견한 경우에만 `bad_events`에 격리한다. 한 Event에 여러
   위반이 있으면 원인을 모두 기록하되 대표 `error_code`는 표의 우선순위를 따른다.
7. Collector는 `begin_checkout`, `purchase`, `purchase_reason_select`의 required key,
   타입, 양수 수량·가격, `reasons` 길이 및 enum을 동기 검증한다. 이 밖의 Event별
   properties는 Spark가 방어적으로 검사한다.

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
