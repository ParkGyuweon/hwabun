# Event Logging 설계

작성일: 2026-09-01
상태: 현재 `dev` Trigger·구현 gap 1차 검수 완료, E2E 검증 대기
실행 계약: [`event-schema.json`](../../contracts/event-schema.json)
Properties 계약: [`event-properties-schema.md`](../../contracts/event-properties-schema.md)

## 1. 목적과 범위

테스트 쇼핑몰에서 사용자와 Persona의 행동을 Event로 수집하고 Kafka, Spark,
DW를 거쳐 상품 반응, 콘텐츠 관심도, Funnel 및 고객군별 인사이트로 변환한다.

이 문서는 화면에서 Event를 발생시키는 시점, KPI 연결 근거, 현재 구현 현황과
검증 계획을 설명한다. Event 이름·intent·properties 타입과 필수 여부는 계약 파일을
단일 출처로 사용하며 이 문서에 Schema 표를 복제하지 않는다.

## 2. 설계 원칙

| 원칙 | 기준 |
| --- | --- |
| 이름 | `lower_snake_case` |
| 전송 단위 | 공통 Envelope + Event별 `properties` |
| 세션 | 쇼핑 흐름은 `session_id`, 페이지 방문은 `page_view_id` |
| 상품 대상 | 상품 관련 Event는 대상 상품의 `product_id` 사용 |
| 비동기 전송 | 화면 동작은 로그 저장을 기다리지 않고 batch 전송 |
| 재시도 | 같은 행동 재전송 시 동일 `event_id` 유지 |
| 중복 책임 | Raw는 모두 보존하고 Processed에서 `event_id` 정본 선택 |
| 가중치 | 실행 상수는 `frontend/src/types/log.ts`가 원본 |
| 개인정보 | 선택·복사 원문은 보내지 않고 길이와 사전 매칭 결과만 사용 |

`product_view`는 `page_view(page_type=product_detail)`와 역할이 다르므로 상세 진입에서
두 Event를 모두 보내되 같은 `page_view_id`를 공유한다. 직접 URL 진입은
`navigation_source='session_start'`로 구분한다.

## 3. 공통 Trigger 규칙

| 규칙 | 내용 |
| --- | --- |
| 발생 시각 | 클라이언트 행동 시각은 `occurred_at`, Collector 수신 시각은 `received_at` |
| 노출 판단 | Event별 viewport 비율과 유지시간을 충족한 뒤 발화 |
| 노출 중복 | `event_id` 외에 화면 grain의 `dedupe_key` 사용 가능 |
| 순서 | `sequence_no`로 클라이언트 발생 순서 보존 |
| 이탈 flush | `visibilitychange`, `pagehide`에서 `sendBeacon` 또는 keepalive 사용 |
| 실패 행동 | API·상태 반영 실패 시 성공 Event를 보내지 않음 |

`sendBeacon`은 성공을 확인할 수 없어 같은 Event가 다시 들어올 수 있다. Collector에서
Redis나 DB로 막지 않고 Spark가 `received_at → topic → partition → offset` 순으로
정본을 선택한다.

`session_start` 발생 시 첫 `page_view_id`를 함께 발급한다. 첫 `page_view`는 같은 값을
공유하고 `navigation_source='session_start'`를 사용한다.

## 4. Event별 Trigger

### 4.1 Session / Page

| event_name | Trigger | 주의사항 |
| --- | --- | --- |
| `session_start` | 사용자·Persona가 새 세션을 시작하거나 Persona가 변경될 때 | 새 `session_id`, 첫 `page_view_id` 발급 |
| `page_view` | 라우트 진입 또는 상세 상품 변경 완료 | 첫 화면 이후 이동은 새 `page_view_id` 발급 |
| `navigation_click` | 상품 대상이 아닌 이동 UI 클릭 | 이동 완료 `page_view`는 별도 |
| `product_view` | 상세 데이터 렌더링과 `product_id` 확정 | `page_view`와 별도, 같은 `page_view_id` |
| `exit_summary` | 탭 숨김, pagehide, 상품·페이지 이동 | 300ms 미만 체류 제외 가능 |

### 4.2 상품 노출·탐색

| event_name | Trigger | 주의사항 |
| --- | --- | --- |
| `product_impression` | 카드가 viewport 50% 이상에서 1초 유지 | page/list/product/position 최초 1회 |
| `impression_dwell` | 유효 노출 카드가 viewport를 벗어나거나 해제 | 실제 `visible_ms` 전송 |
| `product_click` | 카드 클릭 후 상세 이동 시작 | 가능한 경우 `impression_event_id` 연결 |
| `recommendation_impression` | 추천 카드가 viewport 50% 이상에서 1초 유지 | recommendation/list/product/position 최초 1회 |
| `recommendation_snapshot` | 추천 목록 렌더링·순서 변경 완료 | `ranking[]`에 위치 저장 |
| `recommendation_click` | 추천 카드 클릭 | 추천 ID·알고리즘·위치 연결 |
| `quick_look` | 목록 카드의 요약 창 열림 | 상세 진입 전 별도 관심 단계 |
| `quick_look_close` | 요약 창 닫힘 | 체류와 창 내부 행동을 함께 기록 |
| `filter_change` | 필터 적용·해제 후 결과 확정 | 입력 중간 상태 제외 |
| `sort_change` | 정렬 변경 후 결과 확정 | 결과 수 연결 권장 |

### 4.3 상세 콘텐츠

| event_name | Trigger | 주의사항 |
| --- | --- | --- |
| `section_view` | 유효 노출 기준을 400ms 이상 충족 | section/content grain 최초 1회 |
| `section_dwell` | viewport 이탈, page hidden·leave 또는 15초 checkpoint | 700ms 미만 제외, delta 전송 |
| `scroll_depth` | 상세 페이지 10% milestone 최초 도달 | Dashboard에서 25/50/75/100 재집계 가능 |
| `scroll_pause` | 24px 이상 이동 후 320ms 이상 멈춤 | 관심 지점 보조 신호 |
| `scroll_backtrack` | 아래 탐색 후 240px 이상 위로 이동 | 비교·재확인 신호 |
| `media_view` | 이미지 썸네일·미디어 선택 | index와 type 연결 |
| `variant_select` | 옵션 선택 확정 | `sku_id`, `label` 필요 |
| `accordion_toggle` | 상세 정보 펼침·닫힘 | `expand`, `collapse` 구분 |
| `review_expand` | 리뷰 본문 펼침·리뷰 영역 이동 | 성분 더보기와 target으로 구분 |
| `review_filter_apply` | 리뷰 필터·정렬 적용 완료 | 입력 중간 상태 제외 |
| `ingredient_view_mode_change` | 성분 표시 모드 변경 | mode 연결 |
| `text_selection` | 텍스트 선택 후 350ms 안정화 | 입력 요소 제외, 원문 미전송 |
| `text_copy` | 페이지 텍스트 복사 | 원문 미전송 |

### 4.4 전환·마찰

| event_name | Trigger | 주의사항 |
| --- | --- | --- |
| `wishlist_toggle` | 찜 상태 변경 성공 | add/remove 구분 |
| `add_to_cart` | 장바구니 추가 성공 | 실패 시 전송 금지 |
| `remove_from_cart` | 장바구니 삭제 성공 | 변경 후 수량·금액 연결 |
| `view_cart` | 장바구니 화면 진입 | 뒤로가기 경로도 동일 집계값 전송 |
| `quantity_change` | 수량 변경 성공 | 최종 수량 저장 |
| `hover_dwell` | logging 대상 CTA에서 600ms 이상 hover | 모바일 해석 제한 |
| `rage_click` | 800ms 안에 40px 이내 3회 이상 클릭 | UX 품질 신호 |
| `dead_click` | 클릭 가능하지 않은 영역 클릭 | 좌표는 저장하지 않음 |

Planned Event는 검색 결과 확정 시 `search`, 비교 기능 실행 시 `compare_products`,
Checkout 시작 성공 시 `begin_checkout`, 테스트 주문 완료 시 `purchase`를 발화한다.
계약 활성화 전에는 전송하지 않는다.

## 5. GA4 대응

| GA4 Event | 프로젝트 Event |
| --- | --- |
| `view_item` | `product_view` |
| `view_item_list` | `product_impression` |
| `select_item` | `product_click` |
| `add_to_wishlist` | `wishlist_toggle(action=add)` |
| `add_to_cart` | `add_to_cart` |
| `view_cart` | `view_cart` |
| `remove_from_cart` | `remove_from_cart` |
| `begin_checkout` | `begin_checkout` 활성화 후 |
| `purchase` | `purchase` 활성화 후 |

화장품 정보 탐색은 GA4 이커머스 Event만으로 설명하기 어려워 `section_dwell`,
`review_filter_apply`, `ingredient_view_mode_change`, `text_selection` 등을 별도로 둔다.

## 6. Dashboard KPI 연결

| KPI | Event 기준 |
| --- | --- |
| 상품 CTR | `product_click / product_impression` |
| 추천 CTR | `recommendation_click / recommendation_impression` |
| 상세 진입률 | `product_view / product_impression` |
| 성분 열람률 | 성분 `section_view` page_view / `product_view` page_view |
| 리뷰 열람률 | 리뷰 `section_view`·`review_expand` page_view / `product_view` page_view |
| 장바구니 전환율 | add-to-cart session/product / product-view session/product |
| 구매 전환율 | purchase session/product / product-view session/product |
| 단계별 이탈률 | `1 - 다음 단계 도달 수 / 현재 단계 도달 수` |

Funnel은 `product_impression → product_click → product_view → information_view →
add_to_cart → begin_checkout → purchase`로 본다. `information_view`는 성분·리뷰 관련
조회·펼침·필터 Event에서 파생한다. Quick Look은 Funnel 단계가 아니라 노출 이후
비교 분기다.

일간 Dashboard는 KST 기준을 사용하고 최근 7일 추세를 함께 제공한다. 실시간·일간·
주간 집계는 동일 테이블 grain을 무리하게 합치지 않는다.

## 7. 행동 가중치와 품질 해석

가중치 상수의 원본은 `frontend/src/types/log.ts`의 `EVENT_WEIGHT`,
`SECTION_DWELL_WEIGHT`, `NEGATIVE_EVENTS`, `scrollDepthWeight()`다.
`batch/jobs/behavior_weights.py`가 이를 직접 읽으므로 문서에 숫자를 복제하지 않는다.

`quick_look=1.5`는 현재 초기값으로 유지한다. `added_to_cart`는 별도 Event로 가산되므로
Quick Look에서 다시 상향하지 않는다. 조건부 가중치는 실제 `dwell_ms` 분포를 확인한
뒤 한 지점에서만 적용한다.

과도한 반복 클릭·장바구니 반복, 불가능한 Funnel 순서, 비정상 체류시간은 품질 flag
또는 cap 대상으로 분리한다. Synthetic Event는 의도된 시뮬레이션이며 비정상 로그와
같은 의미가 아니다.

## 8. 현재 구현과 계약의 차이

2026-09-03 `dev` 기준 Front Event 36종이 활성 계약에 등록돼 있다. Simulator는 이 중
34종을 생성하며 `navigation_click`은 브라우저 UI 이동에서, `dead_click`은 실제 UI
오작동에서 발생하므로 의도적으로 생성하지 않는다.

Properties 계약에 반영한 Front 실제 값:

- 장바구니 뒤로가기에서도 `item_count`, `distinct_products`, `cart_value` 전송
- breadcrumb 이동을 `navigation_click(intent=session, weight=0)`으로 분리
- `entry_source=breadcrumb`, `content_kind=cart_item`을 enum에 등록
- `text_selection`, `text_copy`의 `text_snippet` 원문 제거
- `matched_count`를 선택 property로 등록

모듈별 후속 반영 대상은 다음과 같다. 이 표는 계약을 다시 정의하지 않고 구현 차이만
추적한다.

| 담당 모듈 | 현재 차이 | 완료 기준 |
| --- | --- | --- |
| Backend Collector | `navigation_click`이 Java Event 허용 목록에서 누락 | `session` intent로 수집되고 회귀 테스트 통과 |
| PC Generator | impression 필수값, 일부 required property, 타입·enum 불일치 | 생성 로그의 Properties 위반 0건 |
| PA Agent | Agent 행동 Event의 동일 계약 준수 여부 미검증 | PA 샘플을 같은 검증기로 확인 |
| Spark Q2 | 공통 필드·synthetic metadata만 검사 | required/type/enum 위반을 `bad_events`로 격리 |

Collector는 현재 공통 Envelope와 synthetic runtime metadata를 검증하지만 Event별
properties 전체는 `JsonNode`로 통과시킨다. 이 차이는 HTTP 200만으로 확인할 수 없어
`contracts/coverage_report.py`가 계약 문서의 required property, 타입, enum을 직접 읽어
검사한다. Spark semantic validation 반영 전까지 이 검증 결과를 구현 인수 기준으로
사용한다.

## 9. E2E 검증 체크리스트

1. `event-schema.json`으로 Envelope와 event/intent 조합을 검증한다.
2. `event-properties-schema.md`의 required property, 타입, enum 위반을 확인한다.
3. 실제 UI Trigger가 threshold와 중복 grain을 지키는지 확인한다.
4. 재전송 Event가 같은 `event_id`를 유지하는지 확인한다.
5. PA runner가 `agent_llm` metadata를 Collector 전송 시점에 보강하는지 확인한다.
6. PC generator가 `python_batch` metadata를 포함하는지 확인한다.
7. Synthetic 필수값 누락이 Collector 또는 Spark에서 격리되는지 확인한다.
8. Event Guide와 Front `log.ts`의 Event 목록이 실행 계약과 일치하는지 확인한다.
9. Planned Event가 활성 enum 등록 전에 전송되지 않는지 확인한다.

Raw·Processed 저장 구조는 각각 Raw Event Log 문서와
[`processed-schema.md`](../../contracts/processed-schema.md), Spark 처리 근거는
[`spark-processing-design.md`](./spark-processing-design.md), Dashboard Mart는
[`dw-schema.md`](../../contracts/dw-schema.md), 적재·조회 근거는
[`dw-design.md`](./dw-design.md)를 따른다.
