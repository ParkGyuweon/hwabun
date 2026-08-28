# Event Taxonomy, Trigger, Event Schema

작성일: 2026-08-28  
상태: Draft  
담당 범위: 데이터 파트 - Event Schema, Raw/Processed Log, DW/분석 데이터 초안  
기준 문서: 프로젝트 기획안, 역할 분담/일정, 기능명세서, 서비스 Flow/Architecture, 기업 마케팅 KPI 조사, 프론트 프로토타입, `marketing-signal-research.md`

## 1. 문서 목적

이 문서는 테스트 쇼핑몰에서 발생하는 사용자 행동을 기업용 B2B Dashboard의 KPI와 연결하기 위한 Event 설계 초안이다.

프로젝트의 핵심은 추천 알고리즘 자체가 아니라, 대규모 화장품 소비 행동 데이터를 안정적으로 수집하고 Kafka/Spark 기반으로 분산 처리한 뒤 기업 마케팅 의사결정에 필요한 지표로 제공하는 것이다. 따라서 Event 설계는 다음 세 가지를 동시에 만족해야 한다.

1. Frontend에서 실제로 트리거할 수 있어야 한다.
2. Backend Collector, Kafka, Spark, DW가 공통으로 이해할 수 있어야 한다.
3. Dashboard의 Overview, 상품 분석, 행동 Funnel, 리뷰 분석, 성분 분석 KPI를 계산할 수 있어야 한다.

`marketing-signal-research.md`에서 확인한 것처럼 네이버쇼핑, 무신사, 올리브영 등은 랭킹/마케팅에 쓰는 지표 목록은 일부 공개하지만 정확한 가중치, 집계 기간, 정규화 방식은 공개하지 않는다. 따라서 이 문서의 관심도 점수와 가중치는 외부 플랫폼의 공식 값이 아니라 우리 프로젝트용 출발점이며, 문서에서는 `[추정]`으로 명시한다.

## 2. 확인한 기획과 역할 요약

### 2.1 프로젝트 정의

서비스 관점에서는 가상 소비자의 화장품 탐색 행동을 분석해 고객군별 상품 관심도와 탐색 패턴을 제공하고, 화장품 기업의 상품 배치, 추천, 마케팅 전략 수립을 지원하는 B2B 플랫폼이다.

데이터/분산 관점에서는 대규모 커머스 Activity Log를 비동기로 수집하고 Kafka, Spark Structured Streaming 기반으로 실시간 분산 처리해 고객 행동 Feature와 마케팅 분석 데이터를 생성하는 파이프라인이다.

### 2.2 전체 흐름

```text
상품/성분/리뷰 원천 데이터
→ 전처리 및 AI 분석
→ 테스트 쇼핑몰 제공
→ 사용자/Persona 행동 Event 발생
→ 비동기 로그 수집 API
→ Kafka
→ Spark Structured Streaming
→ Raw 저장소, 실시간 집계 저장소, DW
→ B2B Dashboard KPI/Funnel/Insight
```

### 2.3 데이터 파트 핵심 책임

| 범위 | 산출물 |
| --- | --- |
| Activity Log 종류 정의 | Event Taxonomy, Trigger 정의 |
| Event Schema 설계 | 공통 Envelope, 화면/세션/상품 Context 필드, Properties |
| Raw / Processed 데이터 구조 설계 | Raw Event, 검증 실패 Event, 집계 Fact 기준 |
| Data Warehouse Schema 초안 | Dashboard KPI 계산용 Fact/Dimension |
| Persona 데이터 구조 설계 | `persona_id`, segment, 피부 타입/고민/가격 민감도 등 |
| Behavior Feature 집계 | 상품/성분/리뷰 관심도, Funnel, 고객군별 행동 Feature |

### 2.4 MVP 범위

기획과 기능명세서 기준 MVP Event 범위는 아래 흐름을 반드시 계산할 수 있어야 한다.

```text
상품 목록/노출
→ 상품 클릭
→ 상품 상세 조회
→ 성분/리뷰/상세 정보 확인
→ 장바구니
→ 구매
→ Dashboard KPI/Funnel
```

## 3. 기업 마케팅 질문과 KPI 연결

Event는 기업 사용자의 질문에서 출발해야 한다. 이번 프로젝트에서 우선 답해야 할 질문은 다음이다.

| 기업 질문 | Dashboard 화면 | 핵심 KPI |
| --- | --- | --- |
| 어떤 상품이 실제로 노출됐고 관심을 끌었는가? | Overview, 상품 분석 | 상품 노출 수, 상품 클릭 수, CTR, 상세 조회 수, 상세 진입률 |
| 사용자가 어떤 상품 정보를 중요하게 확인했는가? | 상품 분석, 성분 분석, 리뷰 분석 | 성분 정보 열람률, 리뷰 정보 열람률, Section별 조회율, Section별 평균 체류시간 |
| 탐색 행동이 구매 의도로 이어졌는가? | Overview, 사용자 행동 분석 | 장바구니 전환율, 구매 전환율, 단계별 이탈률 |
| 어떤 고객군이 어떤 상품/정보에 더 반응하는가? | 상품 분석, 인사이트 | 고객군별 CTR, 고객군별 성분/리뷰 관심도, 고객군별 Funnel |
| 리뷰의 어떤 요소가 관심 또는 이탈에 영향을 주는가? | 리뷰 분석 | 리뷰 열람률, 리뷰 필터 사용, 자극/트러블 리뷰 비율, 주요 평가 요소 |
| 성분 정보가 구매 판단에 어떤 영향을 주는가? | 성분 분석 | 성분 정보 조회 수, 성분 상세 조회율, 주의 성분 보유 상품의 Funnel |

## 4. 프론트 프로토타입 반영 사항

현재 프론트 프로토타입은 React/Vite 기반이며, 구현 화면은 상품 상세 페이지 중심이다.

확인한 주요 화면/컴포넌트는 다음이다.

| 위치 | 구현 요소 | Event 설계 반영 |
| --- | --- | --- |
| `ProductDetailPage.tsx` | 상품 상세 전체 레이아웃 | `page_view`, `product_view`, `section_view`, `section_dwell`, `exit_summary` |
| `ProductGallery.tsx` | 대표 이미지, 썸네일 이미지 | `media_view`, `dead_click` |
| `ProductSummary.tsx` | 브랜드, 상품명, 평점, 가격, 옵션, 수량, 장바구니, 찜 | `review_expand`, `variant_select`, `quantity_change`, `add_to_cart`, `wishlist_toggle`, `hover_dwell` |
| `IngredientsSection.tsx` + `Accordion.tsx` | 성분 정보 접기/펼치기 | `accordion_toggle`, `section_view`, `section_dwell`, `text_selection`, `text_copy` |
| `AboutProduct.tsx` | 상품 설명, 주요 성분, 임상 근거, 사용법, 페르소나 매칭 | `section_dwell`, `scroll_pause`, `text_selection` |
| `SimilarProducts.tsx` | 유사/추천 상품 노출과 클릭 | `recommendation_impression`, `recommendation_click`, `product_click` |
| `ReviewSummary`, `ReviewFilterBar`, `ReviewList` | 리뷰 요약, 필터, 정렬, 리뷰 목록 | `review_filter_apply`, `review_expand`, `section_dwell` |
| `useScrollDepth.ts` | 스크롤 깊이, 멈춤, 되돌아보기 | `scroll_depth`, `scroll_pause`, `scroll_backtrack` |
| `useInteractionSignals.ts` | hover, rage click, dead click | `hover_dwell`, `rage_click`, `dead_click` |
| `useExitSummary.ts` | 페이지 이탈 요약 | `exit_summary` |

현재 프론트 타입은 `frontend/src/types/log.ts`에 `schema_version = 0.2.0-draft`로 존재한다. 이 문서는 해당 구현을 존중해 Event 이름을 `lower_snake_case`로 통일한다. 기존 기획안의 `PRODUCT_VIEW`, `SECTION_VIEW` 같은 대문자명은 개념명으로만 본다.

## 5. Event 설계 원칙

### 5.1 이름 규칙

- Event 이름은 `lower_snake_case`를 사용한다.
- Event 이름은 행동을 나타내고, 화면/상품/콘텐츠 정보는 공통 필드 또는 properties에 둔다.
- `ingredient_view`, `review_view`처럼 영역별 Event를 무한히 늘리기보다 `section_view`, `section_dwell`, `accordion_toggle`에 `section_id`, `content_kind`를 담는다.
- 단, Dashboard 핵심 Funnel 단계는 명확한 해석을 위해 별도 Event로 둔다. 예: `add_to_cart`, `begin_checkout`, `purchase`.

### 5.2 분석 의미 분류

프론트 구현의 `intent` 개념을 Event Schema에 포함한다. Event 이름만으로는 "관심", "검증", "마찰"을 매번 다시 해석해야 하므로 발생 시점에 의미를 함께 저장한다.

| intent | 의미 | 예시 Event |
| --- | --- | --- |
| `session` | 세션/페이지 경계 | `session_start`, `page_view`, `product_view`, `exit_summary` |
| `exposure` | 화면에 노출됨 | `product_impression`, `recommendation_impression`, `scroll_depth` |
| `interest` | 사용자가 들여다봄 | `section_view`, `section_dwell`, `scroll_pause`, `media_view`, `quick_look`, `quick_look_close` |
| `comparison` | 후보 비교/탐색 | `product_click`, `recommendation_click`, `variant_select`, `scroll_backtrack`, `compare_products` |
| `validation` | 구매 판단 근거 확인 | `accordion_toggle`, `review_filter_apply`, `review_expand`, `text_selection`, `text_copy` |
| `hesitation` | 전환 전 망설임 | `hover_dwell`, `remove_from_cart` |
| `conversion` | 구매 의도/전환 | `wishlist_toggle`, `add_to_cart`, `view_cart`, `begin_checkout`, `purchase` |
| `friction` | 사용성 마찰/좌절 | `rage_click`, `dead_click` |

### 5.3 우선순위

| 우선순위 | 기준 | Event |
| --- | --- | --- |
| P0 | Dashboard 필수 KPI/Funnel 계산에 반드시 필요 | `session_start`, `page_view`, `product_view`, `product_impression`, `product_click`, `section_view`, `section_dwell`, `accordion_toggle`, `add_to_cart`, `view_cart`, `begin_checkout`, `purchase`, `exit_summary` |
| P1 | 프로젝트 차별화와 해석력을 높임 | `recommendation_impression`, `recommendation_click`, `scroll_depth`, `scroll_pause`, `scroll_backtrack`, `media_view`, `quick_look`, `quick_look_close`, `review_filter_apply`, `review_expand`, `ingredient_view_mode_change`, `wishlist_toggle`, `quantity_change`, `remove_from_cart`, `text_selection`, `text_copy` |
| P2 | 확장 기능 또는 구현 후순위 | `search`, `filter_change`, `sort_change`, `compare_products`, `rage_click`, `dead_click`, `hover_dwell` |

P2에 둔 Event라도 이미 프론트에 구현된 항목은 수집 가능하다. 다만 MVP Dashboard 산식의 필수 분모/분자로 쓰지 않는다는 의미다.

### 5.4 현재 구현 상태

현재 프론트 프로토타입은 상품 상세 페이지 중심이다. 따라서 Event는 "이미 구현됨", "설계됨", "후속 화면 구현 후 확정"으로 나누어 관리한다.

| 상태 | Event |
| --- | --- |
| FE 전달 기준 구현됨 | `session_start`, `page_view`, `section_view`, `section_dwell`, `accordion_toggle`, `recommendation_impression`, `recommendation_click`, `product_click`, `wishlist_toggle`, `add_to_cart`, `view_cart`, `remove_from_cart`, `quick_look`, `quick_look_close`, `exit_summary`, `scroll_depth`, `media_view`, `variant_select`, `quantity_change`, `review_filter_apply`, `review_expand`, `scroll_pause`, `scroll_backtrack`, `text_selection`, `text_copy`, `hover_dwell`, `rage_click`, `dead_click` |
| 설계상 필요하지만 보강 필요 | `product_view`, `ingredient_view_mode_change` |
| 후속 화면 구현 후 확정 | `product_impression`, `search`, `filter_change`, `sort_change`, `compare_products`, `begin_checkout`, `purchase` |

`wishlist_toggle`은 `action=add/remove`로 찜 추가와 해제를 모두 표현한다. 별도 `remove_from_wishlist` Event는 두지 않는다.

### 5.5 GA4 이커머스 권장 Event 매핑

기업 마케팅/분석 담당자에게 설명하기 쉽도록 GA4 이커머스 권장 Event와 우리 Event를 대응시킨다. 단, GA4 명칭을 그대로 쓰지는 않고 우리 서비스 Taxonomy를 표준으로 사용한다.

| GA4 Event | 우리 Event | 현재 상태 | 설명 |
| --- | --- | --- | --- |
| `view_item` | `product_view` | 보강 필요 | 상품 상세 조회 |
| `view_item_list` | `product_impression` | 후속 화면 구현 후 확정 | 목록/검색/추천 영역 상품 노출 |
| `select_item` | `product_click` | 일부 구현됨 | 상품 카드 또는 추천 상품 클릭 |
| `add_to_wishlist` | `wishlist_toggle(action=add)` | 구현됨 | 찜 추가 |
| `add_to_cart` | `add_to_cart` | 구현됨 | 장바구니 담기 |
| `view_cart` | `view_cart` | 구현됨 | 장바구니 조회 |
| `remove_from_cart` | `remove_from_cart` | 구현됨 | 장바구니 제거 |
| `begin_checkout` | `begin_checkout` | 후속 화면 구현 후 확정 | 구매 진행 시작 |
| `purchase` | `purchase` | 후속 화면 구현 후 확정 | 테스트 구매 완료 |
| `add_shipping_info` | 범위 제외 | 제외 | 실제 배송 정보 입력은 MVP 범위 밖 |
| `add_payment_info` | 범위 제외 | 제외 | 실제 결제 정보 입력은 MVP 범위 밖 |

GA4 표준 Event만으로는 구매 전 탐색 구간을 설명하기 어렵다. 우리 프로젝트는 화장품 정보 탐색을 다루므로 `section_dwell`, `accordion_toggle`, `review_filter_apply`, `text_selection`, `scroll_pause` 같은 탐색/검증 신호를 별도로 둔다.

## 6. Event Taxonomy v1

### 6.1 Session / Page

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `session_start` | `session` | 사용자 또는 Persona의 새 쇼핑 세션 시작 | 전체 방문 수, 세션당 행동 수 |
| `page_view` | `session` | 페이지/라우트 진입 | 페이지별 방문, 이탈 분석 |
| `product_view` | `session` | 상품 상세 페이지 진입 완료 | 상품 상세 조회 수, 상세 진입률, Funnel 시작점 |
| `exit_summary` | `session` | 페이지 이탈 시점의 요약 | 상세페이지 이탈률, 마지막 관심 영역 |

`product_view`는 `page_view(page_type=product_detail)`와 별도 Raw Event로 직접 전송한다. `page_view`는 페이지 경계, `product_view`는 상품 Funnel 분모로 역할이 다르므로 동일 상세 진입에서 두 Event가 모두 발생하되 같은 `page_view_id`를 공유한다.

### 6.2 Product Exposure / Exploration

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `product_impression` | `exposure` | 상품 카드가 목록/검색/홈/추천 영역에서 유효 노출 | 상품 노출 수, CTR 분모 |
| `product_click` | `comparison` | 상품 카드 또는 추천 상품 클릭 | 상품 클릭 수, CTR 분자 |
| `recommendation_impression` | `exposure` | 추천/유사 상품 카드 유효 노출 | 추천 영역 CTR, CBF 노출 품질 |
| `recommendation_click` | `comparison` | 추천/유사 상품 클릭 | 추천 클릭률, 추천 기반 상세 진입 |
| `quick_look` | `interest` | 목록에서 상품 요약 창 열림 | 상세 진입 전 관심, select_item 이전 단계 |
| `quick_look_close` | `interest` | 상품 요약 창 닫힘 | 요약 창 체류/행동 요약 |
| `search` | `comparison` | 검색 실행 | 검색 키워드, 검색 후 클릭률 |
| `filter_change` | `comparison` | 상품 목록 필터 적용/해제/초기화 | 필터별 관심, 고객군별 탐색 기준 |
| `sort_change` | `comparison` | 상품 목록 정렬 변경 | 인기순/가격순/평점순 선호 |
| `compare_products` | `comparison` | 상품 비교 기능 실행 | 경쟁 상품군 분석 |

`recommendation_impression`과 `recommendation_click`은 상세 페이지의 유사 상품뿐 아니라 목록/기획전의 `promo_pick` 리스트에서도 발생할 수 있다. `promo_pick`이 페르소나 맞춤 추천(`skin_match_v0`)으로 구성되어도 추천 CTR 산식은 `recommendation_click_count / recommendation_impression_count`로 동일하게 유지한다.

### 6.3 Product Detail Engagement

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `section_view` | `interest` | 상세 페이지의 특정 섹션/콘텐츠 블록이 유효 조회됨 | 성분/리뷰 정보 열람률, Section 조회율 |
| `section_dwell` | `interest` | 특정 섹션/콘텐츠 블록 체류시간 확정 | Section 평균 체류시간, 상품별 관심도 |
| `scroll_depth` | `exposure` | 상세 페이지 스크롤 깊이 milestone 도달 | 상세 탐색 깊이, 이탈 구간 |
| `scroll_pause` | `interest` | 스크롤 중 멈춘 지점 | 사용자가 붙잡힌 콘텐츠 |
| `scroll_backtrack` | `comparison` | 아래로 보다가 다시 위로 되돌아봄 | 비교/망설임 신호 |
| `media_view` | `interest` | 상품 이미지 썸네일/미디어 조회 | 이미지 관심도 |
| `accordion_toggle` | `validation` | 성분/사용법 등 접힌 정보 펼침/닫힘 | 정보 확인 의도 |
| `text_selection` | `validation` | 상품 설명/성분/리뷰 텍스트 선택 | 관심 문장/성분 후보 |
| `text_copy` | `validation` | 상품 설명/성분/리뷰 텍스트 복사 | 강한 검증 의도 |

### 6.4 Review / Ingredient

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `review_expand` | `validation` | 리뷰 링크 이동, 리뷰 상세 펼침 등 리뷰 확인 행동 | 리뷰 정보 열람률, 리뷰 관심도 |
| `review_filter_apply` | `validation` | 리뷰 필터 또는 정렬 적용 | 리뷰 탐색 기준, 같은 피부 타입 리뷰 관심 |
| `ingredient_view_mode_change` | `validation` | 주요 성분/전체 성분/주의 성분 등 표시 방식 변경 | 성분 상세 조회율 |

성분과 리뷰는 별도 Event를 과도하게 늘리지 않고 `section_id`, `content_kind`, `content_ref`로 구분한다.

예:

```json
{
  "event_name": "section_view",
  "properties": {
    "section_id": "ingredients",
    "content_kind": "ingredient_list"
  }
}
```

### 6.5 Conversion

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `wishlist_toggle` | `conversion` | 찜 추가/해제 | 관심 상품, 구매 전 약한 전환 |
| `add_to_cart` | `conversion` | 장바구니 담기 성공 | 장바구니 전환율 |
| `view_cart` | `conversion` | 장바구니 화면 진입 | Cart 확인율 |
| `quantity_change` | `conversion` | 수량 변경 | 구매 의도 강도 |
| `remove_from_cart` | `hesitation` | 장바구니 상품 제거 | 장바구니 제거율, add_to_cart 과대평가 검증 |
| `begin_checkout` | `conversion` | 구매 진행 시작 | Checkout 전환율 |
| `purchase` | `conversion` | 테스트 구매 완료 | 구매 전환율 |

### 6.6 Friction

| event_name | intent | 설명 | 주요 KPI/활용 |
| --- | --- | --- | --- |
| `hover_dwell` | `hesitation` | CTA 위에 오래 머물렀으나 즉시 클릭하지 않음 | 장바구니 전 망설임 |
| `rage_click` | `friction` | 짧은 시간 같은 지점 반복 클릭 | UI 마찰, 이탈 원인 |
| `dead_click` | `friction` | 클릭 가능하지 않은 영역 클릭 | 기대 기능 부재, 이미지 확대 요구 등 |

## 7. Trigger v1

### 7.1 공통 Trigger 규칙

| 규칙 | 내용 |
| --- | --- |
| 발생 시각 | 클라이언트에서 행동이 발생한 시각을 `occurred_at`에 담고, 서버 수신 시각은 `received_at`으로 별도 저장 |
| 중복 제거 책임 | Backend Collector는 Redis/DB로 중복 차단하지 않아도 된다. Raw는 중복 수신을 허용하고, Data/Spark Processed 단계에서 `event_id` 기준으로 중복 제거한다 |
| 재시도 조건 | Front가 `sendBeacon`, keepalive, 재시도로 같은 Event를 다시 보낼 때는 같은 `event_id`를 유지한다 |
| 노출 중복 | 노출/스크롤/섹션 조회는 `event_id` 외에 `dedupe_key`를 추가로 사용할 수 있다 |
| 세션 연결 | 같은 쇼핑 흐름은 동일 `session_id`, 같은 페이지 방문은 동일 `page_view_id`를 사용 |
| 순서 복원 | 클라이언트 전송 순서가 바뀔 수 있으므로 `sequence_no`를 저장 |
| 비동기 전송 | 화면 동작은 로그 저장을 기다리지 않고, Front Logger가 batch 전송 |
| 이탈 flush | 페이지 이탈/탭 숨김 시 `sendBeacon` 또는 keepalive로 잔여 버퍼 전송 |

`sendBeacon`은 성공 여부를 알 수 없으므로 같은 batch/Event가 재전송될 수 있다. 이 중복은 정상적인 at-least-once 전송 특성으로 보고, Backend가 요청 시점에 막지 않고 Data/Spark가 `cleaned_events` 생성 전 `event_id` 기준으로 멱등 처리한다.

`session_start`도 공통 필드 규칙상 `page_view_id`를 가진다. Front는 첫 페이지의 `page_view_id`를 발급한 뒤 `session_start`와 첫 `page_view`가 같은 `page_view_id`를 공유하도록 전송한다.

### 7.2 Event별 Trigger

| event_name | Trigger | 중복/주의사항 |
| --- | --- | --- |
| `session_start` | Persona/User가 새 쇼핑 세션을 시작하거나 Persona가 변경될 때 | `session_id` 새로 발급 |
| `page_view` | 라우트 진입 또는 상품 상세 상품 변경이 완료될 때 | `page_view_id` 새로 발급 |
| `product_view` | 상품 상세 데이터 렌더링이 완료되고 `product_id`가 확정될 때 | `page_view`와 별도 전송, 같은 `page_view_id` 공유 |
| `exit_summary` | `visibilitychange=hidden`, `pagehide`, 상품/페이지 이동 시 | 최소 체류 300ms 미만은 제외 가능 |
| `product_impression` | 상품 카드가 viewport 50% 이상에서 1초 이상 노출될 때 | `page_view_id + list_id + product_id + position` 최초 1회 |
| `product_click` | 상품 카드 클릭 후 상세 이동이 시작될 때 | `impression_event_id`가 있으면 함께 전달 |
| `recommendation_impression` | 추천/유사 상품 카드가 viewport 50% 이상에서 1초 이상 노출될 때 | `recommendation_id + product_id` 최초 1회 |
| `recommendation_click` | 추천/유사 상품 카드 클릭 | `recommendation_id`, `algorithm`, `position` 필수 |
| `quick_look` | 목록/기획전 상품 카드에서 요약 창이 열릴 때 | 상세 진입 전 관심 신호. `select_item` 이전 단계 |
| `quick_look_close` | 상품 요약 창이 닫힐 때 | `dwell_ms`와 창 안 행동 요약을 함께 해석 |
| `section_view` | 섹션/콘텐츠가 유효 노출 기준을 만족하고 400ms 이상 유지될 때 | `section_id/content_kind/content_ref` 방문당 최초 1회 |
| `section_dwell` | 유효 노출된 섹션이 viewport를 벗어나거나 page hidden/leave, 또는 15초 checkpoint 도달 시 | 700ms 미만 체류는 제외 |
| `scroll_depth` | 상세 페이지에서 10% 단위 milestone 최초 도달 시 | Dashboard는 25/50/75/100으로 재집계 가능 |
| `scroll_pause` | 스크롤 이동 후 320ms 이상 멈추고 이동거리 24px 이상일 때 | 관심 지점 보조 신호 |
| `scroll_backtrack` | 아래로 탐색하다가 240px 이상 위로 되돌아볼 때 | 비교/재확인 신호 |
| `media_view` | 이미지 썸네일 또는 미디어 항목 선택 | `media_index`, `media_type` 필요 |
| `accordion_toggle` | 성분/사용법 등 Accordion 펼침/닫힘 | `action=expand/collapse` |
| `review_expand` | 평점/리뷰 링크 클릭, 리뷰 상세 펼침 | 리뷰 섹션 점프도 포함 |
| `review_filter_apply` | 리뷰 필터 또는 정렬 조건 변경 | 검색 입력 중이 아니라 적용 완료 시점만 |
| `ingredient_view_mode_change` | 주요/전체/주의 성분 탭 또는 보기 모드 변경 | 구현 시 추가 |
| `text_selection` | 페이지 텍스트 선택 후 350ms 안정화 | input/textarea/contenteditable 제외 |
| `text_copy` | 페이지 텍스트 복사 | 원문 저장 여부는 개인정보/보존 정책 확정 필요 |
| `wishlist_toggle` | 찜 추가 또는 해제 성공 | action으로 add/remove 구분 |
| `add_to_cart` | 장바구니 추가 API 또는 프론트 상태 반영 성공 | 실패 시 성공 로그 전송 금지 |
| `remove_from_cart` | 장바구니 삭제 성공 | `quantity`, `cart_size_after` 필요 |
| `view_cart` | 장바구니 페이지 진입 | `item_count`, `distinct_products`, `cart_value` 권장 |
| `quantity_change` | 수량 변경 성공 | 최종 수량 저장 |
| `begin_checkout` | 구매 진행 화면 진입 또는 Checkout 시작 버튼 성공 | items 배열 필요 |
| `purchase` | 테스트 주문 완료 확정 | `order_id` 기준 중복 제거 |
| `hover_dwell` | `data-log-action` 요소 위에 600ms 이상 hover 후 벗어남 | 모바일에서는 제한적 |
| `rage_click` | 800ms 안에 40px 이내 3회 이상 클릭 | 디버깅/UX 분석용 |
| `dead_click` | 클릭 가능 요소가 아닌 영역 클릭 | 좌표 저장은 하지 않음 |
| `search` | 검색어 submit 또는 검색 버튼 클릭 후 결과 확정 | 키 입력마다 남기지 않음 |
| `filter_change` | 필터 적용/해제/초기화 후 결과 확정 | `result_count` 권장 |
| `sort_change` | 정렬 기준 변경 후 결과 확정 | 상품 목록 구현 후 적용 |
| `compare_products` | 상품 비교 기능 실행 또는 비교함 추가 | MVP 후순위 |

## 8. Event Schema v1

### 8.1 Schema 흐름

Front → Collector → Kafka 구간에서는 같은 Raw Event Schema를 유지한다. Collector는 Event 구조를 바꾸지 않고 검증, 수신 시각 추가, Kafka 전송만 담당한다.

```text
Frontend LogEnvelope
→ Collector validation + server fields 추가
→ Kafka raw_events topic
→ Spark validation/dedup/sessionize
→ Processed/DW tables
```

따라서 MVP 기준 공식 수집 Schema는 프론트가 보내는 flat 구조를 기준으로 한다. `context`, `target`처럼 중첩된 구조는 Kafka Raw Event가 아니라 Spark 이후 Processed/DW 정규화 단계에서 사용할 수 있는 형태다.

### 8.2 Raw Event Schema

프론트가 Collector로 보내는 LogEnvelope는 아래 구조를 기준으로 한다. 서버 메타 필드인 `received_at`은 Collector가 검증 후 Kafka payload에 추가한다.

```json
{
  "schema_version": "0.2.0-draft",
  "event_id": "uuid",
  "event_name": "add_to_cart",
  "intent": "conversion",
  "occurred_at": "2026-08-28T01:13:12.123Z",
  "persona_id": "persona_1024",
  "session_id": "session_923",
  "page_view_id": "pv_1001",
  "sequence_no": 12,
  "page_type": "product_detail",
  "product_id": "P342",
  "actor_type": "synthetic",
  "environment": "local",
  "properties": {
    "scenario_id": "normal_day",
    "simulation_run_id": "run_20260828_001",
    "sku_id": "SKU342-01",
    "quantity": 1,
    "price_usd": 32
  }
}
```

E2E 기준 `schema_version`은 현재 프론트 구현과 맞춰 `0.2.0-draft`로 둔다. `1.0.0-draft`는 JSON Schema와 구현 계약을 확정한 뒤 올릴 후보 버전이다. 요청 body의 top-level `schema_version`과 각 Event의 `schema_version`이 함께 존재하면 값은 같아야 한다.

### 8.3 Collector Enriched Fields

Collector는 Raw Event의 의미 구조를 바꾸지 않고 서버에서만 알 수 있는 메타 필드를 추가할 수 있다.

```json
{
  "schema_version": "0.2.0-draft",
  "event_id": "uuid",
  "event_name": "add_to_cart",
  "intent": "conversion",
  "occurred_at": "2026-08-28T01:13:12.123Z",
  "persona_id": "persona_1024",
  "session_id": "session_923",
  "page_view_id": "pv_1001",
  "sequence_no": 12,
  "page_type": "product_detail",
  "product_id": "P342",
  "actor_type": "user",
  "environment": "local",
  "received_at": "2026-08-28T01:13:12.420Z",
  "properties": {
    "sku_id": "SKU342-01",
    "quantity": 1,
    "price_usd": 32
  }
}
```

서버 보강 필드:

| field | 설명 |
| --- | --- |
| `received_at` | Collector가 Event를 받은 서버 시각 |
| `request_id` | 한 번의 batch 요청을 묶는 식별자. 현재는 HTTP 응답/Header 기준 |
| `source` | Event 유입 경로. 현재 Kafka payload 필드가 아니라 Processed 단계 파생값 |
| `collector_version` | Collector 배포 버전. 선택 |

### 8.4 공통 필드 정의

| field | type | required | 설명 |
| --- | --- | --- | --- |
| `schema_version` | string | Y | Event Schema 버전 |
| `event_id` | string | Y | Event 고유 ID. 중복 제거 기준 |
| `event_name` | string | Y | Event Taxonomy에 정의된 이름 |
| `intent` | string | Y | `session/exposure/interest/comparison/validation/hesitation/conversion/friction` |
| `occurred_at` | timestamp | Y | 행동 발생 시각 |
| `received_at` | timestamp | Server | Collector 수신 시각. Kafka payload 포함 |
| `source` | string | Derived | `web`, `simulator`, `server`. Processed 단계에서 파생 |
| `request_id` | string | Response | batch 요청 단위 식별자. 현재는 HTTP 응답/Header 기준 |
| `persona_id` | string/null | 조건부 | Persona 기반 이벤트일 때 사용 |
| `actor_type` | string | Y | `user`, `synthetic` |
| `session_id` | string | Y | 쇼핑 세션 ID |
| `page_view_id` | string | Y | 페이지 방문 1회 ID |
| `sequence_no` | integer | Y | 세션 내 Event 순서 |
| `page_type` | string | Y | MVP 기준 `product_list`, `product_detail`, `cart` |
| `environment` | string | Y | `local`, `dev`, `staging`, `prod`, `loadtest` |
| `scenario_id` | string/null | N | 시뮬레이션 조건. 현재 API에는 top-level 필드가 없으므로 `properties.scenario_id` 또는 후속 DTO 확장으로 처리 |
| `simulation_run_id` | string/null | N | 시뮬레이션 실행 1회 식별자. 현재 API에는 top-level 필드가 없으므로 `properties.simulation_run_id` 또는 후속 DTO 확장으로 처리 |
| `experiment_id` | string/null | N | A/B 테스트 또는 추천 정책 실험 |
| `ab_variant` | string/null | N | A/B 그룹 |
| `product_id` | string/null | Event별 | 상품 대상 Event일 때 필수. 값은 보고 있는 상품이 아니라 Event 대상 상품 기준 |
| `properties` | object | Y | Event별 세부 속성 |

`product_id`는 Event의 대상 상품을 의미한다. 예를 들어 A 상품 상세에서 추천 상품 B를 클릭하면 top-level `product_id`는 B이고, A는 `properties.context_product_id`로 보낸다. 컨텍스트가 없거나 대상과 같으면 `context_product_id`는 생략한다. 섹션 체류·스크롤처럼 화면 자체를 대상으로 하는 Event는 보고 있는 상품을 `product_id`로 둔다.

### 8.5 Processed / DW 정규화 예시

Spark 이후 분석 단계에서는 Raw Event를 아래처럼 논리적으로 정규화할 수 있다. 이 구조는 Kafka Raw Event Schema가 아니라 DW/분석 편의를 위한 형태다.

| Raw field | Processed/DW 의미 |
| --- | --- |
| `persona_id`, `actor_type` | actor 차원 |
| `session_id`, `page_view_id`, `sequence_no` | session 차원 |
| `page_type`, `environment`, `scenario_id`, `simulation_run_id`, `experiment_id`, `ab_variant` | context 차원 |
| `product_id`, `properties.sku_id` | target/product 차원 |
| `properties.context_product_id` | Event가 발생한 배경 상품. 추천 클릭처럼 대상 상품과 보고 있던 상품이 다를 때 사용 |
| `properties` | Event별 세부 속성 또는 별도 fact 컬럼 |

### 8.6 주요 Enum

#### page_type

| value | 설명 |
| --- | --- |
| `product_list` | 상품 목록/검색/필터 결과 |
| `product_detail` | 상품 상세 |
| `cart` | 장바구니 |

후속 화면에서 `home`, `checkout`, `dashboard`를 별도 page_type으로 둘 수 있지만, 현재 Backend validation 기준에는 포함되어 있지 않다.

#### section_id

현재 프론트 프로토타입 기준.

| value | 설명 |
| --- | --- |
| `product_hero` | 상품 이미지, 가격, 옵션, CTA 영역 |
| `highlights` | 상품 주요 특징 |
| `about_product` | 상품 설명, 주요 성분, 임상 근거 등 |
| `ingredients` | 성분 Accordion |
| `how_to_use` | 사용법 Accordion |
| `similar_products` | 유사/추천 상품 |
| `reviews` | 리뷰 요약, 필터, 리뷰 목록 |
| `promo_row` | 목록 상단 기획전/추천 상품 행 |
| `list_controls` | 목록 필터/정렬 조작 영역 |
| `product_grid` | 상품 목록 그리드 |
| `cart_items` | 장바구니 상품 목록 |

#### content_kind

| value | 설명 |
| --- | --- |
| `product_image` | 상품 이미지/갤러리 |
| `price` | 가격 |
| `variant_option` | 색상/향/용량 등 옵션 |
| `cta` | 장바구니/찜/구매 CTA |
| `highlight_badge` | 상품 특징 배지 |
| `what_it_is` | 상품 개요 |
| `what_else` | 추가 설명 |
| `ingredient_list` | 전체 성분 |
| `ingredient_callout` | 주요/주의 성분 강조 |
| `clinical_claim` | 임상 근거 |
| `usage_guide` | 사용법 |
| `brand_story` | 브랜드 설명 |
| `persona_match` | 피부 타입/고민 매칭 정보 |
| `product_meta` | 카테고리, 용량 등 메타 정보 |
| `user_review` | 개별 사용자 리뷰 |
| `review_stats` | 평점/리뷰 요약 |
| `review_filter` | 리뷰 필터/정렬 |
| `recommendation_card` | 추천/유사 상품 카드 |
| `product_card` | 목록/기획전 상품 카드 |
| `navigation` | Breadcrumb, 링크 이동 |

#### entry_source

| value | 설명 |
| --- | --- |
| `list_grid` | 일반 상품 목록에서 진입 |
| `promo_pick` | 기획전/추천 상품 행에서 진입 |
| `similar_products` | 상세 페이지 유사/추천 상품에서 진입 |
| `quick_look` | 요약 창 내부 CTA에서 진입 또는 장바구니 담기 |
| `cart` | 장바구니에서 수량 변경/재진입 |

## 9. Event별 Required Properties

`product_id`는 상품 대상 Event에서 공통 top-level 필드로 보낸다. 아래 표의 `required properties`는 `properties` 객체 안에 들어가는 Event별 세부 값만 적는다.

### 9.1 Session / Page

| event_name | required properties | optional properties |
| --- | --- | --- |
| `session_start` | 없음 | `entry_page`, `referrer`, `utm_source`, `utm_medium`, `utm_campaign` |
| `page_view` | 없음 | `referrer`, `route` |
| `product_view` | 없음 | `entry_source`, `list_id`, `position`, `recommendation_id`, `context_product_id` |
| `exit_summary` | `dwell_ms`, `max_scroll_percent` | `last_section_id`, `last_content_kind`, `reason` |

### 9.2 Product Exposure / Exploration

| event_name | required properties | optional properties |
| --- | --- | --- |
| `product_impression` | `list_id`, `position` | `visible_ratio`, `impression_area`, `dedupe_key` |
| `product_click` | 없음 | `list_id`, `position`, `entry_source`, `impression_event_id`, `context_product_id` |
| `recommendation_impression` | `recommendation_id`, `list_id`, `position`, `algorithm` | `section_id`, `visible_ratio`, `context_product_id` |
| `recommendation_click` | `recommendation_id`, `list_id`, `position`, `algorithm` | `section_id`, `impression_event_id`, `context_product_id` |
| `quick_look` | 없음 | `list_id`, `position`, `entry_source`, `recommendation_id`, `algorithm`, `context_product_id` |
| `quick_look_close` | `dwell_ms` | `variants_viewed`, `added_to_cart`, `wishlisted`, `list_id`, `position`, `entry_source` |
| `search` | `query_text` | `result_count`, `normalized_query` |
| `filter_change` | `filter_name`, `filter_action`, `filter_values` | `result_count` |
| `sort_change` | `sort_key`, `sort_direction` | `result_count` |
| `compare_products` | `compared_product_ids` | `base_product_id`, `compare_count` |

### 9.3 Detail Engagement

| event_name | required properties | optional properties |
| --- | --- | --- |
| `section_view` | `section_id` 또는 `content_kind` | `content_ref`, `visible_duration_ms`, `visible_ratio` |
| `section_dwell` | `section_id` 또는 `content_kind`, `dwell_ms` | `content_ref`, `co_visible_blocks`, `reason` |
| `scroll_depth` | `depth_percent` | `section_id`, `content_kind` |
| `scroll_pause` | `depth_percent`, `direction`, `distance_px`, `duration_ms` | `section_id`, `content_kind`, `visible_content_kinds`, `velocity_px_per_sec` |
| `scroll_backtrack` | `depth_percent`, `distance_px` | `section_id`, `content_kind` |
| `media_view` | `media_type`, `media_index` | `media_id`, `image_url_hash` |
| `accordion_toggle` | `section_id`, `action` | `content_kind` |
| `text_selection` | `text_length` | `section_id`, `content_kind`, `content_ref`, `matched_ingredients`, `matched_keywords`, `vocab_version` |
| `text_copy` | `text_length` | `section_id`, `content_kind`, `content_ref`, `matched_ingredients`, `matched_keywords`, `vocab_version` |

### 9.4 Review / Ingredient

| event_name | required properties | optional properties |
| --- | --- | --- |
| `review_expand` | `target` | `review_id`, `section_id` |
| `review_filter_apply` | `filter` 또는 `sort` | `result_count`, `persona_skin_type`, `persona_skin_tone` |
| `ingredient_view_mode_change` | `mode` | `ingredient_id`, `ingredient_name`, `ingredient_group` |

### 9.5 Conversion / Friction

| event_name | required properties | optional properties |
| --- | --- | --- |
| `wishlist_toggle` | `action` | `sku_id` |
| `add_to_cart` | `quantity` | `sku_id`, `price_usd`, `unit_price`, `currency`, `entry_source`, `context_product_id` |
| `remove_from_cart` | `quantity`, `cart_size_after` | `sku_id`, `reason`, `cart_value` |
| `view_cart` | 없음 | `item_count`, `distinct_products`, `cart_value` |
| `quantity_change` | `quantity` | `sku_id` |
| `variant_select` | `variant_name` 또는 `option_name`, `selected_value` | `previous_value`, `sku_id`, `variant_group` |
| `begin_checkout` | `items` | `cart_value`, `currency` |
| `purchase` | `order_id`, `items` | `order_value`, `currency` |
| `hover_dwell` | `action`, `dwell_ms` | `section_id`, `content_kind` |
| `rage_click` | `click_count` | `action`, `section_id`, `content_kind` |
| `dead_click` | `target_tag` | `section_id`, `content_kind` |

`section_dwell.dwell_ms`는 누적값이 아니라 이번 Event가 나타내는 구간 체류시간(delta)이다. 15초 checkpoint 또는 이탈 시 여러 건이 발생하면 Processed에서 delta 값을 합산한다.

`quick_look_close.dwell_ms`는 요약 창 안에서 머문 시간이다. 체류시간 단독으로 구매 의도를 해석하지 않고, `variants_viewed`, `added_to_cart`, `wishlisted`와 함께 창 내부 행동 요약으로 해석한다.

`begin_checkout`, `purchase`의 `items[]`는 Raw에서는 Event 1건 안에 배열로 보관하고, Processed의 `product_event_fact`에서는 Spark가 `items explode`를 수행해 상품별 row로 변환한다.

## 10. Dashboard KPI 산식

### 10.1 Overview

| KPI | 산식 |
| --- | --- |
| 전체 방문 수 | `count(session_start)` 또는 `count(distinct session_id)` |
| 상품 상세 조회 수 | `count(product_view)` |
| 상품 상세 진입률 | `count(product_view) / count(product_impression)` |
| 성분 정보 열람률 | `count(distinct page_view_id where section/content is ingredient) / count(product_view)` |
| 리뷰 정보 열람률 | `count(distinct page_view_id where section/content is review) / count(product_view)` |
| 장바구니 전환율 | `count(distinct session_id, product_id with add_to_cart) / count(distinct session_id, product_id with product_view)` |
| 구매 전환율 | `count(distinct session_id, product_id with purchase) / count(distinct session_id, product_id with product_view)` |
| 상세페이지 이탈률 | `count(product_view without next conversion/interest action before exit) / count(product_view)` |
| 인기 상품 TOP N | 상품별 `interest_score` 또는 조회/장바구니/구매 가중 합 |

### 10.2 상품 분석

| KPI | 산식 |
| --- | --- |
| 상품 노출 수 | `count(product_impression by product_id)` |
| 상품 클릭 수 | `count(product_click by product_id)` |
| CTR | `product_click / product_impression` |
| 상세페이지 조회 수 | `count(product_view by product_id)` |
| 장바구니 담기 수 | `count(add_to_cart by product_id)` |
| 구매 수 | `count(purchase item by product_id)` |
| 상품별 성분 관심도 | `ingredient section_view/dwell/text events by product_id` |
| 상품별 리뷰 관심도 | `review section_view/dwell/filter/expand events by product_id` |

### 10.3 Funnel

MVP Funnel은 동일 `session_id + product_id` 기준으로 계산한다.

```text
product_impression
→ product_click
→ product_view
→ information_view
→ add_to_cart
→ begin_checkout
→ purchase
```

`information_view`는 별도 Event가 아니라 아래 조건 중 하나 이상을 만족하는 파생 단계다.

```text
section_view where section_id in ('ingredients', 'reviews')
or section_view where content_kind in ('ingredient_list', 'ingredient_callout', 'user_review', 'review_stats', 'review_filter')
or accordion_toggle action='expand'
or review_filter_apply
or review_expand
```

단계별 전환율:

```text
next_step_users_or_sessions / current_step_users_or_sessions
```

단계별 이탈률:

```text
1 - 단계별 전환율
```

### 10.4 리뷰 분석

리뷰 분석 화면은 Event 데이터와 AI 리뷰 분석 결과를 함께 사용한다.

| 지표 | 필요 데이터 |
| --- | --- |
| 리뷰 열람률 | `section_view`, `section_dwell`, `review_expand`, `review_filter_apply` |
| 리뷰 상세 조회 수 | `review_expand`, `content_ref=review_id` |
| 평균 평점 | Product/Review 원천 데이터 |
| 긍정/부정 리뷰 비율 | AI 리뷰 분석 결과 |
| 주요 평가 요소 | AI 리뷰 분석 결과 |
| 자극/트러블 언급 비율 | AI 리뷰 분석 결과 |
| 자극/트러블 확인 후 이탈률 | 리뷰 관련 Event 이후 `exit_summary` 또는 전환 미발생 |

### 10.5 성분 분석

성분 분석 화면은 Event 데이터와 성분/규제 데이터 매핑 결과를 함께 사용한다.

| 지표 | 필요 데이터 |
| --- | --- |
| 주요 성분 | Product Ingredient 데이터 |
| 주의 성분 수 | 규제/주의 성분 매핑 결과 |
| 성분 정보 조회 수 | `section_view`, `accordion_toggle`, `ingredient_view_mode_change` |
| 성분 정보 열람률 | 성분 관련 `section_view` 발생 page_view / `product_view` |
| 성분 상세 조회율 | `ingredient_view_mode_change`, `text_selection`, `text_copy` |
| 성분 확인 후 장바구니 전환율 | 성분 관련 Event 이후 같은 session/product의 `add_to_cart` |

### 10.6 집계 기간 및 시간 감쇠

마케팅 실무에서는 같은 Event라도 집계 기간에 따라 의미가 달라진다. 실시간 인기 상품, 일간 성과, 주간 추세, 장기 관심도는 같은 산식으로 한 번에 처리하지 않는다.

| 집계 창 | 목적 | 적용 지표 |
| --- | --- | --- |
| 실시간/최근 5분 | 대시보드 현재 상태, 부하 테스트, 급증 감지 | TPS, Event 수, 인기 상품, Consumer Lag |
| 시간별 | 시연용 추이, 시간대별 행동 변화 | 방문 수, 상세 조회 수, 장바구니 수 |
| 일간 | 기본 Dashboard KPI | 상품별 KPI, 성분/리뷰 열람률, Funnel |
| 최근 7일 | 단기 마케팅 반응 | 인기 상품, 고객군별 반응 |
| 최근 30일 | 안정적인 상품 성과 | 상품 비교, 브랜드/카테고리 확장 |
| 전체 기간 | 데이터 검증, 누적 성과 참고 | 총 Event 수, 전체 Funnel |

인기 상품이나 상품별 관심도처럼 순위를 만드는 지표에는 최신성을 반영할 수 있다. MVP에서는 우선 일간/최근 7일 집계를 만들고, 여유가 있으면 아래 감쇠식을 적용한다.

```text
decayed_score = raw_score * exp(-age_hours / half_life_hours)
```

권장 시작값 `[추정]`:

| 지표 | half_life_hours |
| --- | --- |
| 실시간 인기 상품 | 6 |
| 일간 인기 상품 | 24 |
| 최근 7일 관심도 | 72 |

위 값은 외부 플랫폼 공식값이 아니라 프로젝트용 실험값이다. 발표에서는 "실시간/일간/주간 집계 창을 분리했고, 최신성 반영은 확장 가능하다" 정도로 설명한다.

## 11. 상품별 관심도 초안 `[추정]`

상품별 관심도는 Event 확정 후 가중치를 조정하되, MVP에서는 단순하고 설명 가능한 방식으로 시작한다. 아래 값은 네이버쇼핑, 무신사, 올리브영 등 외부 플랫폼의 공식 가중치가 아니다. `marketing-signal-research.md`에서 정리한 신호 강도를 바탕으로 우리 프로젝트에 맞춰 정한 초기값이다.

### 11.1 Event Weight v1 `[추정]`

| 신호 | Event / 조건 | 가중치 | 이유 |
| --- | --- | --- | --- |
| 상품 조회 | `product_view` | 1 | 양이 많고 노이즈가 있어 기준선으로 사용 |
| 리뷰 열람 | review 관련 `section_view`, `review_expand`, `review_filter_apply` | 2 | 구매 전 확인 단계 |
| 이미지 갤러리 전환 | `media_view` | 2 | 화장품은 이미지/질감 확인이 중요 |
| 섹션 체류 | `section_dwell` 임계 초과 | 2 | 관심 깊이. 단독 해석 금지 |
| 옵션 선택 | `variant_select` | 3 | 특정 색/용량/향으로 후보를 좁힘 |
| 성분/상세 펼침 | `accordion_toggle(action=expand)`, `ingredient_view_mode_change` | 3 | 능동적 검증 행동 |
| 찜 | `wishlist_toggle(action=add)` | 4 | 지속 관심. 즉시 구매보다는 약함 |
| 장바구니 | `add_to_cart` | 5 | 구매 없는 환경에서 가장 강한 전환 의도 |
| 구매 | `purchase` | 8 | 테스트 구매 완료. 구현 시 최상위 신호 |
| 빠른 이탈 | `exit_summary` 중 짧은 체류/낮은 탐색 | -2 | 부적합 또는 관심 낮음 |
| 좌절 신호 | `rage_click`, `dead_click`, 과도한 `scroll_backtrack` | -2 | 정보 탐색 실패 또는 UI 마찰 |

### 11.2 Product Interest Score v1 `[추정]`

```text
interest_score =
  1 * normalized(product_view)
+ 2 * normalized(review_or_media_or_dwell_signal)
+ 3 * normalized(variant_or_ingredient_validation_signal)
+ 4 * normalized(wishlist_add)
+ 5 * normalized(add_to_cart)
+ 8 * normalized(purchase)
- 2 * normalized(exit_or_friction_signal)
```

### 11.3 주의점

- 이 점수는 실제 매출 예측이 아니라 "설정된 가상 소비자 조건에서 관찰된 관심 수준"이다.
- 외부 플랫폼의 공식 가중치가 아니므로 발표/문서에서 반드시 `[추정]`으로 표기한다.
- `section_dwell`은 탭 방치 노이즈가 있으므로 `scroll_pause`, `text_selection`, `accordion_toggle`과 함께 해석한다.
- 체류시간은 긴 outlier를 막기 위해 page_view/product 단위 cap을 둔다. 예: 섹션별 최대 60초.
- 고객군별 관심도는 `segment_id` 또는 Persona Feature와 Join해서 계산한다.
- 조회 수처럼 빈도가 높은 신호가 점수를 지배하지 않도록 Event별 정규화와 cap을 적용한다.

## 12. Raw / Processed 적재 초안

이 문서는 Event Schema가 중심이지만, 데이터 파트 진행을 위해 최소 적재 구조도 함께 둔다.
Processed Dataset의 상세 컬럼과 생성 기준은 `processed-schema.md`에 분리한다.
Dashboard 조회용 DW/Mart 상세 구조는 `dw-schema.md`에 분리한다.

| 데이터셋 | Grain | 설명 |
| --- | --- | --- |
| `raw_events` | received event record | Collector가 검증한 원본 Event. `event_id`는 dedup key |
| `bad_events` | received record | Schema 검증 실패, 필수값 누락, 파싱 실패 |
| `session_event_ordered` | session_id + sequence_no | 순서 복원 및 세션 분석용 |
| `product_event_fact` | event_id + item_index + product_id | 상품별 Event 집계용. `context_product_id`, `item_revenue` 보존 |
| `product_daily_kpi` | date + product_id | Dashboard 상품 KPI |
| `content_interest_fact` | date + product_id + section/content | 성분/리뷰/콘텐츠 관심도. `event_date_kst`, `actor_type`, `source` 보존 |
| `funnel_session_fact` | session_id + product_id | Funnel 단계 도달 여부. `funnel_date_kst`로 일간 귀속 |
| `persona_behavior_feature_delta` | event_id + user_id + product_id | CBF/고객군 분석용 Behavior Feature delta |

## 13. 검증 규칙 초안

| 검증 항목 | 처리 |
| --- | --- |
| `event_id` 없음 | bad event 격리 |
| `event_name` taxonomy 미등록 | bad event 격리 |
| `schema_version` 미지원 | bad event 격리 또는 별도 migration |
| `occurred_at` 파싱 실패 | bad event 격리 |
| `session_id/page_view_id` 없음 | bad event 격리 |
| `sequence_no` 없음 | 경고 후 수신 순서 보조 사용, 가능하면 bad 처리 |
| 필수 properties 누락 | bad event 격리 |
| 중복 `event_id` | 최초 1건만 사용 |
| 너무 늦게 도착한 Event | watermark 정책에 따라 late event 처리 |
| `actor_type=synthetic` | 실제 사용자와 분리 집계 가능하도록 필수 저장 |

### 13.1 신뢰도 / 비정상 로그 감점 기준 초안

마케팅 실무에서는 행동 신호가 순위와 인사이트에 영향을 주기 때문에 조작 가능성도 고려해야 한다. 이 기준은 `actor_type=synthetic`과는 다른 문제다. Synthetic Event는 의도된 부하 테스트/시뮬레이션이고, 비정상 로그는 같은 사용자 또는 같은 세션에서 발생 패턴이 분석을 왜곡할 가능성이 있는 Event를 뜻한다.

| 기준 | 예시 | 처리 |
| --- | --- | --- |
| 불가능한 순서 | `purchase`가 있는데 같은 session/product에 `product_view`가 없음 | 품질 경고, Funnel 집계 제외 검토 |
| 과도한 반복 클릭 | 짧은 시간 동일 상품/버튼 수십 회 클릭 | `trust_penalty` 부여 |
| 과도한 장바구니 반복 | 동일 세션에서 같은 상품 add/remove 반복 | 전환 지표에서 cap 적용 |
| 비정상 체류시간 | 섹션 체류가 지나치게 김 | dwell cap 적용. 예: 섹션별 60초 |
| 중복 노출 | 같은 page/list/product/position impression 반복 | 최초 1건만 사용 |
| 봇/부하 테스트 혼입 | `source=simulator`인데 Dashboard 실제 사용자 필터에 포함됨 | Dashboard 기본 필터에서 분리 |
| 마찰 신호 집중 | `rage_click`, `dead_click`이 특정 UI에 집중 | 관심도 감점 또는 UX 이슈로 별도 집계 |

권장 파생 필드:

| field | 설명 |
| --- | --- |
| `is_valid_event` | Schema와 필수값을 통과했는지 |
| `quality_flags` | `duplicate`, `late_event`, `invalid_order`, `excessive_repeat` 등 |
| `trust_penalty` | 관심도/랭킹 계산에서 감점할 값 |
| `is_synthetic` | `actor_type=synthetic` 또는 `source=simulator` 여부 |

MVP에서는 bad event 격리, 중복 제거, dwell cap, synthetic/user 필터 분리를 먼저 구현한다. `trust_penalty`는 관심도 점수나 인기 상품 랭킹을 만들 때 확장한다.

## 14. 합의 현황 및 남은 미확정 사항

프론트/백 확인 결과, 공식 Raw Event Schema 작성에 필요한 핵심 방향은 아래처럼 정리한다.

| 상태 | 안건 | 결정 내용 |
| --- | --- | --- |
| 합의 | Raw Event Schema 기준 | Front JSON 구조를 유지하고, Backend는 큰 가공 없이 검증과 서버 메타 필드만 추가 |
| 합의 | Event 수집 API | `POST /api/events`, body는 `{ schema_version, events: [ ...LogEnvelope ] }` |
| 합의 | E2E Schema Version | 현재 구현 기준 `0.2.0-draft` 사용. `1.0.0-draft`는 추후 계약 확정 후 전환 |
| 합의 | batch 크기 | 프론트 기본값 20건 기준, 추후 부하 테스트 결과로 조정 |
| 합의 | 서버/파생 메타 필드 | Kafka payload에는 `received_at` 포함. `request_id`는 HTTP 응답/Header, `source`는 Processed 단계 파생 기준 |
| 합의 | `source` 파생 | MVP는 `actor_type=user → web`, `actor_type=synthetic → simulator`, 서버 내부 Event는 `server` |
| 합의 | 검증 실패 Event | 전체 batch 실패보다 실패 Event만 분리 처리하는 방향. 정확한 응답 포맷은 Backend 구현 시 확정 |
| 합의 | `product_view` 생성 위치 | Front에서 별도 Event로 직접 전송 |
| 합의 | `section_dwell` 합산 위치 | Front는 여러 건을 보내고 Spark/DW에서 합산 |
| 합의 | Synthetic/Web Event 분리 | 같은 Schema를 사용하고 `actor_type`, `source`, `simulation_run_id`로 구분 |
| 합의 | `text_snippet` 저장 | 원문 제거, `text_length`, `matched_ingredients`, `vocab_version` 중심 |
| 초안 | Dashboard 기본 산식 | session/product 기준 우선 |
| 초안 | 집계 기간 | 일간 + 최근 7일 우선 |
| 초안 | DW 집계 방식 | 서로 다른 grain의 Fact는 목표 Mart grain으로 먼저 집계한 뒤 Join |
| 초안 | 상품별 매출 | `items[]` explode 후 상품별 매출은 `item_revenue`, 주문 총액 검증은 `order_value` |
| 구현 후 재검증 | 후속 화면 Trigger | `product_impression`, `search`, `filter_change`, `begin_checkout`, `purchase` Trigger |
| 현재 구현 | Kafka 기본값 | topic 기본값은 `activity-events`, message는 Event 1건 단위, key는 `persona_id` |
| 미확정 | Kafka fallback | 실제 Web Event에서 `persona_id=NULL`일 때 partition key fallback은 Kafka/Spark 담당자와 합의 필요 |
| 확장 | 관심도 가중치/비정상 행동 | MVP 이후 샘플 데이터와 QA 결과로 조정 |

## 15. MVP 구현 순서 제안

1. Frontend `LogEnvelope`와 이 문서의 필수 필드 차이를 정리한다.
2. Collector `POST /api/events`에서 배열 수신, Schema 검증, bad event 격리를 구현한다.
3. `product_view`, `section_view`, `section_dwell`, `add_to_cart` 4종을 우선 Kafka까지 전달한다.
4. Spark에서 Raw 적재와 `product_daily_kpi`, `content_interest_fact`, `funnel_session_fact`를 만든다.
5. Dashboard Overview에 상세 조회 수, 성분 열람률, 리뷰 열람률, 장바구니 전환율을 먼저 연결한다.
6. 이후 `product_impression`, `purchase`, `review_filter_apply`, `scroll_depth`를 추가해 CTR, 구매 전환율, Funnel 이탈률을 완성한다.
