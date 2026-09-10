# 브랜드 대시보드 마트 조회 API 계약 (백엔드 ↔ 프론트 · 데이터)

> 상태: **초안 0.1 (2026-09-10, 프론트 작성).** 합의 전. 이 문서가 확정되면 `README.md` 단일 출처 표에
> "브랜드 대시보드 마트 조회 API" 행으로 들어간다.
>
> 정본 관계
> - 마트의 grain·컬럼·nullable 은 [`dw-schema.md`](./dw-schema.md) §4 가 정본이다. 이 문서는 **그 마트를 대시보드가
>   어떤 HTTP 로 읽는가**만 정한다. 컬럼 이름은 마트 컬럼을 **그대로** 쓴다 (§1-3).
> - 화면 요소별 원천·가능성 표는 [`docs/dashboard/dashboard-redesign-spec.md`](../docs/dashboard/dashboard-redesign-spec.md) §2.
> - 브랜드 귀속은 [`event-attribution-contract.md`](./event-attribution-contract.md).
> - 프론트 구현: `frontend/src/dashboard/lib/martApi.ts` (요청·응답 타입), `martAdapter.ts` (화면 모양으로 변환),
>   `useBehavior.tsx` (마트가 없으면 모의 집계로 물러남).

---

## 0. 왜 이 계약이 필요한가

대시보드 9화면 중 행동 지표(개요 KPI·상세 콘텐츠·고객군·성분 관심·상품 진단·막히는 곳)는 지금 전부 프론트의
시드 고정 모의값이다. Spark `build_marts_job.py` 가 `product_daily_kpi`·`funnel_daily_kpi`·`brand_daily_kpi`·
`ingredient_weekly_interest` 등을 Parquet 로 만들지만, 그것을 MySQL 로 옮기는 projection 도, 읽어 주는 API 도 없다
(`docs/planning/feature-spec-status.md` "DW Publish 미구현에 가까움 · 실제 대시보드 API 미구현").

세 파트가 각자 할 일이 이 문서 하나로 갈린다.

| 파트 | 할 일 | 이 문서의 어디 |
| --- | --- | --- |
| 데이터 | Delta `marts/*` → MySQL `dw.*` projection. 같은 grain·같은 값 (`dw-schema.md` §6-1) | §5 마트별 사용 컬럼, §6 신규 마트 요청 |
| 백엔드 (shop_backend) | `GET /api/seller/dashboard/*` 6개. SELLER 인증 · brandId 소유 확인 · 기간 합산 | §1~§4 |
| 프론트 | 응답을 화면 모양으로 바꾸고, 마트가 없으면 모의로 물러나며 배지를 바꾼다 | 이미 구현 (`martAdapter.ts`) |

---

## 1. 공통 규칙

### 1-1. 서버·경로·인증

- 서버는 **shop_backend (8090)**. 이미 `GET /api/seller/dashboard?brandId=` 와 `GET /api/seller/feedback?brandId=`
  가 SELLER 토큰과 브랜드 소유 확인(`brand.seller_account_id = actor`)을 하고 있으므로 같은 자리에 붙인다.
  Vite 프록시도 `/api/seller` → 8090 으로 이미 나 있다.
- 경로 접두는 `/api/seller/dashboard/`. 기존 `GET /api/seller/dashboard` (주문·매출·리뷰·피드백 4칸)는 그대로 둔다.
- 인증 실패는 401, 남의 브랜드는 403. 응답 본문은 기존 `ApiExceptionHandler` 형식 `{"error": "..."}`.

### 1-2. 공통 쿼리

| 이름 | 필수 | 기본 | 뜻 |
| --- | --- | --- | --- |
| `brandId` | Y | — | shop_backend `brand.brand_id`. `dw.dim_brand.brand_id` 와 **같은 값**이다 (`dw-schema.md` §3-1 "source = Backend 브랜드 등록 정보"). 서버는 별도 매핑 없이 그대로 마트를 필터한다 |
| `from` | N | `to` − 13일 | KST 일자 `YYYY-MM-DD`. 포함 |
| `to` | N | 어제 (KST) | KST 일자. 포함. 오늘은 마트가 아직 없다 |
| `actorType` | N | `all` | `all` · `web` · `synthetic`. `all` 은 두 actor_type 합산. 마트 key 의 `actor_type` 을 필터한다 |

`source`·`scenario_id`·`simulation_run_id` 축은 **전부 합산**한다. 대시보드는 실행 단위를 구분하지 않는다.
구분이 필요해지면 쿼리를 추가하되 기본은 합산이다.

기간 상한은 92일. 넘으면 400 `{"error":"range_too_long"}`.

### 1-3. 응답 봉투와 이름 규칙

```json
{
  "brand_id": "b-0001",
  "range": { "from": "2026-08-27", "to": "2026-09-09", "days": 14 },
  "actor_type": "all",
  "source": {
    "marts": ["brand_daily_kpi", "product_daily_kpi"],
    "mart_processed_at": "2026-09-10T03:10:00+09:00",
    "coverage": "full"
  },
  "...": "엔드포인트별 본문 (§3)"
}
```

- **컬럼 이름은 마트 컬럼을 그대로** 쓴다 (`snake_case`). 기존 판매자 API 는 camelCase 지만, 이 API 의 값은
  마트를 통과만 하는 값이라 이름을 바꾸면 검증 때 대조가 어려워진다. `dw-schema.md` §6-1 "Delta 와 MySQL projection 은
  같은 grain 과 KPI 값" 을 API 까지 연장한 것이다.
- 기간 합산 컬럼은 마트 컬럼 이름 그대로 두고, **비율은 서버가 합산값에서 다시 계산**한다. 일별 비율을 평균내지
  않는다. 분모 0 이면 `null` (마트 규칙과 같다).
- `source.coverage`: `full` (본문 전부 마트) · `partial` (§3 에서 "조건부" 로 표시한 블록이 `null`) · `none` (이 브랜드
  행이 0건. 본문은 빈 배열·0). 프론트는 `none` 이면 그 화면을 모의로 그리고 배지를 "모의" 로 둔다.
- `mart_processed_at` 은 응답에 쓰인 마트들의 `mart_processed_at` 중 **가장 오래된** 값이다. 화면 하단에 그대로 적는다.

### 1-4. 마트가 없을 때

projection 테이블이 아직 없으면 **503** `{"error":"mart_unavailable","mart":"brand_daily_kpi"}`. 프론트는 503·404·5xx
전부를 "이 화면은 모의" 로 처리하므로 코드 구분은 로그용이다. 테이블은 있는데 행이 0건이면 200 + `coverage: none`.

### 1-5. 표본 억제는 하지 않는다

서버는 표본이 작아도 값을 그대로 준다. 200 미만 흐림·50 미만 비움은 **프론트 규칙**이다 (재설계 명세 §0-5).
단 다른 브랜드 값은 어떤 형태로도 섞지 않는다 (경계 문서 A층). 코호트·중앙값 비교는 이 계약 범위 밖이다.

---

## 2. 엔드포인트 한눈에

| # | 경로 | 화면 | 주 마트 | 상태 |
| --- | --- | --- | --- | --- |
| E1 | `GET /api/seller/dashboard/overview` | 요약 | `brand_daily_kpi`, `product_daily_kpi`, `funnel_daily_kpi` | 가능 |
| E2 | `GET /api/seller/dashboard/products` | 상품 · 요약 관심도 TOP | `product_daily_kpi`, `funnel_daily_kpi` | 가능 (진단 3열은 조건부) |
| E3 | `GET /api/seller/dashboard/content` | 상세 콘텐츠 | `content_daily_kpi` | 가능 (담기율 배수는 조건부) |
| E4 | `GET /api/seller/dashboard/segments` | 고객군 | `persona_segment_daily_kpi` | 단일 축 가능 · 격자는 조건부 |
| E5 | `GET /api/seller/dashboard/ingredients` | 성분 · 상세 콘텐츠 드래그 TOP | `ingredient_weekly_interest` | 가능 |
| E6 | `GET /api/seller/dashboard/friction` | 막히는 곳 | (신규) `friction_daily`, `entry_source_daily`, `exit_daily` | 조건부 |

"가능" = 지금 `dw-schema.md` §4 정의와 `build_marts_job.py` 산출물로 채울 수 있다. "조건부" = 마트 컬럼이나 세션
조인이 없어 §6 요청이 먼저 처리돼야 한다. 조건부 블록은 응답에서 `null` 로 오고 프론트가 그 블록만 모의로 채운다.

---

## 3. 엔드포인트별 응답 본문

이하 본문은 §1-3 봉투 안에 들어간다. 타입은 `dw-schema.md` §2-2 공통 타입. `bigint` 는 JSON number.

### E1 `overview`

기간 합산 브랜드 KPI + 직전 같은 길이 기간 + 일별 추이 + 퍼널.

```json
{
  "current":  { "...": "아래 표" },
  "previous": { "...": "같은 표. from−days ~ from−1" },
  "daily": [ { "event_date_kst": "2026-08-27", "product_view_sessions": 412, "add_to_cart_sessions": 27, "unique_user_count": 380 } ],
  "funnel": {
    "impression_sessions": 9800, "click_sessions": 1210, "product_view_sessions": 4800,
    "information_view_sessions": 2900, "add_to_cart_sessions": 300
  }
}
```

`current` / `previous`:

| 필드 | 원천 | 비고 |
| --- | --- | --- |
| `impression_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `unique_user_count`, `product_count_viewed` | `brand_daily_kpi` 합산 | 브랜드 단위 세션 dedup 은 마트가 이미 했다. 일자를 합산하면 여러 날 온 세션이 중복되지만 그대로 둔다 (마트 grain 을 존중) |
| `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `add_to_cart_sessions_by_product`, `remove_from_cart_sessions` | `product_daily_kpi` 브랜드 합산 | 담았다 뺀 비율의 분자·분모. `add_to_cart_sessions_by_product` 는 상품 합산이라 `brand_daily_kpi` 의 `add_to_cart_sessions` 와 다르다. 이름을 다르게 둔 이유 |
| `detail_entry_rate`, `information_view_rate`, `view_to_cart_rate` | 위 합산에서 재계산 | 분모 0 → null |
| `removal_rate` | `remove_from_cart_sessions / add_to_cart_sessions_by_product` | 같은 마트 안에서 나눈다 |

`funnel`: `funnel_daily_kpi` 를 브랜드로 합산한 다섯 칸. `click_sessions` 가 `brand_daily_kpi` 에 없어 이 마트를 쓴다.
상품 합산이라 브랜드 세션 dedup 이 아니다 → §6-1 요청. 프론트는 퍼널 아래에 "상품 합산" 을 적는다.

### E2 `products`

브랜드 상품별 기간 합산. 정렬은 서버가 하지 않는다.

```json
{
  "products": [
    {
      "product_id": "P0001",
      "product_impression_count": 3200, "product_click_count": 410, "quick_look_count": 60,
      "product_view_count": 380, "add_to_cart_count": 40, "remove_from_cart_count": 6,
      "quick_look_sessions": 55, "product_view_sessions": 340, "add_to_cart_sessions": 38, "remove_from_cart_sessions": 6,
      "session_count": 900, "unique_user_count": 850,
      "product_ctr": 0.128, "detail_entry_rate": 0.119, "add_to_cart_rate": 0.105, "product_interest_score": 812.5,
      "funnel": {
        "impression_sessions": 2900, "click_sessions": 400, "product_view_sessions": 340,
        "information_view_sessions": 210, "add_to_cart_sessions": 38,
        "quick_look_sessions": 55, "quick_look_cart_sessions": 9
      },
      "diagnostics": null
    }
  ]
}
```

| 블록 | 원천 | 상태 |
| --- | --- | --- |
| 상단 수량·세션·비율 | `product_daily_kpi` 합산 · 비율 재계산 | 가능 |
| `funnel` | `funnel_daily_kpi` 합산 | 가능 |
| `diagnostics` | `{ exit_content_kind_top, exit_sessions, variant_select_per_session, quick_look_open_detail_rate }` | **조건부** · §6-3. 없으면 `null` |

병목 단계(노출→클릭→상세→정보확인→담기 중 브랜드 중앙값 대비 최저)는 **프론트가** `funnel` 에서 계산한다.
중앙값은 내 브랜드 상품들 사이의 값이라 다른 브랜드 경계를 넘지 않는다.

### E3 `content`

브랜드 상품 상세페이지 안의 `content_kind` 별 기간 합산. 상품 축은 접는다 (`product_id` 합산).

```json
{
  "by_content_kind": [
    {
      "content_kind": "ingredient_list",
      "section_view_count": 5100, "section_view_sessions": 2980, "dwell_ms_sum": 113800000,
      "accordion_expand_count": 640, "text_selection_count": 410, "text_copy_count": 120, "matched_ingredient_count": 380,
      "product_view_sessions": 4800,
      "avg_dwell_ms_per_session": 23708.3, "view_rate": 0.62,
      "conversion": null
    }
  ],
  "brand": { "product_view_sessions": 4800, "add_to_cart_sessions": 300, "view_to_cart_rate": 0.0625 },
  "behaviors": null
}
```

| 필드 | 원천 | 비고 |
| --- | --- | --- |
| 합산 수량 | `content_daily_kpi` `product_id`·일자 합산 | `dwell_ms_sum` 은 마트 규칙대로 `content_interest_fact` 기준 (§4-4) |
| `product_view_sessions` | 같은 마트의 분모 컬럼 합산 | content_kind 마다 같은 값이 되는 것이 정상 |
| `avg_dwell_ms_per_session` | `dwell_ms_sum / product_view_sessions` 재계산 | 화면의 "얼마나 오래 읽나" |
| `view_rate` | `section_view_sessions / product_view_sessions` | 화면의 "몇 명이 봤나". 마트에 없어 서버가 만든다 |
| `conversion` | `{ viewed_sessions, viewed_cart_sessions, cart_lift }` | **조건부** · §6-2. 화면의 "본 사람의 담기율 배수". `cart_lift = (viewed_cart_sessions/viewed_sessions) / brand.view_to_cart_rate` |
| `brand` | `brand_daily_kpi` 합산 | lift 의 분모 |
| `behaviors` | `[{ event, done_sessions, cart_rate_with, cart_rate_without }]` · event ∈ `ingredient_view_mode_change`·`review_filter_apply`·`accordion_toggle`·`text_copy` | **조건부** · §6-2 |

`content_kind` 는 상품 상세 안에서 읽는 10종만 프론트가 고른다 (`ingredient_list`·`ingredient_callout`·`clinical_claim`·
`user_review`·`review_stats`·`what_it_is`·`what_else`·`usage_guide`·`brand_story`·`product_image`). 서버는 필터하지 않고
마트에 있는 종류를 전부 준다.

### E4 `segments`

```json
{
  "by_segment": [
    { "segment_type": "skin_type", "segment_value": "dry", "segment_user_count": 1100, "session_count": 1500,
      "product_view_sessions": 1240, "add_to_cart_sessions": 88, "view_to_cart_rate": 0.071, "avg_interest_score": 3.1 }
  ],
  "grid": null,
  "top_content": null,
  "same_skin_filter_rate": null
}
```

| 블록 | 원천 | 상태 |
| --- | --- | --- |
| `by_segment` | `persona_segment_daily_kpi` `product_id`·일자 합산. `segment_type` ∈ `skin_type`·`skin_tone` (있으면 `eye_color`·`hair_color` 도) | 가능 |
| `grid` | `[{ skin_type, skin_tone, product_view_sessions, add_to_cart_sessions, view_to_cart_rate }]` 20칸 | **조건부** · §6-4 (교차 축 마트). 화면 히트맵의 정본 |
| `top_content` | `[{ skin_type, content_kind, dwell_ms_sum, dwell_share }]` 타입 4행 × 상위 2 | **조건부** · §6-4 |
| `same_skin_filter_rate` | `review_filter_apply(same_skin_type)` 세션 / 필터 사용 세션 | **조건부** · §6-2 behaviors 와 같은 마트 |

`grid` 가 `null` 이면 프론트는 히트맵을 모의로 그리고 `by_segment` 는 KPI 한 칸(최고 전환 타입)에만 쓴다.

### E5 `ingredients`

```json
{
  "weeks": ["2026-08-24", "2026-08-31", "2026-09-07"],
  "by_ingredient": [
    { "ingredient_id": 12, "ingredient": "niacinamide", "label_ko": "나이아신아마이드", "vocab_version": "0.4",
      "ingredient_interest_score": 812.4, "direct_match_score": 210.0, "product_attributed_score": 602.4,
      "contributing_event_count": 1930, "ingredient_interest_share": 0.061 }
  ]
}
```

- 원천 `ingredient_weekly_interest`. 기간에 걸친 주(`interest_week_kst`, KST 월요일)를 모두 합산한다. `share` 는 합산 후
  재계산.
- 이 마트에는 **brand 축이 없다.** 플랫폼 전체 관심이다. 화면의 "고객이 찾는 성분" 은 원래 플랫폼 관심 대비 **내 라인
  보유**를 보는 표라 그대로 맞는다. 보유·함량 위치는 프론트가 내 상품 전성분에서 계산한다 (실측, 이미 구현).
- `direct_match_score` 가 화면의 "긁기" 열, `ingredient_interest_score` 가 관심 순위, `product_attributed_score` 는 "체류" 열
  자리에 들어간다 (체류 ms 가 아니라 점수이므로 프론트가 단위를 바꿔 적는다).
- `ingredient` 는 `product-feature-vocab.json` `ingredient_source.synonyms` 의 **키**(예 `Niacinamide`, `Hyaluronic Acid`)와
  같아야 한다. 프론트는 대소문자·동의어(`niacinamide`, `sodium hyaluronate`)도 키로 되돌려 받지만, 어휘집에 없는 이름은
  한국어 표시명과 내 라인 보유를 붙일 수 없어 표에서 뺀다. `vocab_version` 이 `0.4` 와 다르면 프론트가 콘솔에 남긴다.
- 상세 콘텐츠 화면의 "고객이 드래그한 성분 TOP 10" 도 이 응답의 `direct_match_score` 상위 10 을 쓴다.

### E6 `friction` (전부 조건부)

```json
{
  "by_location": [ { "section_id": "product_image", "event_name": "dead_click", "event_count": 412, "session_count": 380 } ],
  "counts": { "rage_click": 121, "dead_click": 412, "scroll_backtrack": 2900 },
  "quick_exit_rate": 0.29,
  "entry_source": [ { "entry_source": "similar_products", "product_view_sessions": 860, "add_to_cart_sessions": 95, "view_to_cart_rate": 0.11 } ],
  "event_volumes": [ { "event_name": "section_dwell", "event_count": 30000 } ]
}
```

| 블록 | 신규 마트 (§6-5) |
| --- | --- |
| `by_location`, `counts` | `friction_daily` (grain: event_date_kst, brand_id, section_id, event_name) |
| `quick_exit_rate` | `exit_daily` (`exit_summary.dwell_ms < 3000` 세션 / 상세 세션) |
| `entry_source` | `entry_source_daily` (grain: event_date_kst, brand_id, entry_source) |
| `event_volumes` | `realtime_event_stats` 또는 `event_daily`. 브랜드 필터 가능해야 한다 |

`dead_click` 은 생성기가 만들지 않으므로 PC 로그에서는 0 이다. 0 이어도 행을 지우지 않는다 (화면이 그 사실을 적는다).

---

## 4. 오류

| 상태 | 본문 | 언제 |
| --- | --- | --- |
| 400 | `{"error":"bad_range"}` | `from > to`, 날짜 형식 오류 |
| 400 | `{"error":"range_too_long"}` | 92일 초과 |
| 400 | `{"error":"bad_actor_type"}` | `all`·`web`·`synthetic` 외 |
| 401 | `{"error":"unauthorized"}` | 토큰 없음·만료. `/error` permitAll 이 안 돼 있으면 400 도 이걸로 바뀌니 먼저 고친다 (`docs/shop-backend-requests.md` 1번) |
| 403 | `{"error":"forbidden"}` | SELLER 아님, 또는 남의 brandId |
| 503 | `{"error":"mart_unavailable","mart":"..."}` | projection 테이블 없음 |

---

## 5. 마트별 사용 컬럼 (데이터 파트 projection 범위)

MySQL `dw` 스키마에 아래 컬럼만 있으면 E1~E5 가 돈다. key 는 `dw-schema.md` §4 그대로.

| 마트 | 사용 컬럼 |
| --- | --- |
| `brand_daily_kpi` | key 전체, `impression_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `unique_user_count`, `product_count_viewed`, `mart_processed_at` |
| `product_daily_kpi` | key 전체, `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `quick_look_sessions`, `product_view_sessions`, `add_to_cart_sessions`, `remove_from_cart_sessions`, `unique_user_count`, `session_count`, `product_interest_score`, `mart_processed_at` |
| `funnel_daily_kpi` | key 전체, `impression_sessions`, `quick_look_sessions`, `quick_look_cart_sessions`, `click_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `mart_processed_at` |
| `content_daily_kpi` | key 전체, `section_view_count`, `section_view_sessions`, `dwell_ms_sum`, `accordion_expand_count`, `text_selection_count`, `text_copy_count`, `matched_ingredient_count`, `product_view_sessions`, `mart_processed_at` |
| `persona_segment_daily_kpi` | key 전체, `segment_user_count`, `session_count`, `product_view_sessions`, `add_to_cart_sessions`, `avg_interest_score`, `mart_processed_at` |
| `ingredient_weekly_interest` | 전 컬럼 |

인덱스 권고: `(brand_id, event_date_kst)` 선두. `ingredient_weekly_interest` 는 `(interest_week_kst)`.

---

## 6. 신규 마트·컬럼 요청 (데이터 파트)

조건부 블록을 채우려면 아래가 필요하다. 우선순위 순. 각 항목은 없어도 API 는 200 을 주고 블록만 `null` 이다.

| # | 요청 | 채우는 블록 | 왜 마트여야 하나 |
| --- | --- | --- | --- |
| 6-1 | `brand_daily_kpi` 에 `click_sessions` 추가 | E1 `funnel` | 브랜드 세션 dedup 퍼널. 지금은 상품 합산으로 대신한다 |
| 6-2 | **`content_conversion_daily`** (grain: event_date_kst, brand_id, product_id, content_kind · 컬럼: `viewed_sessions`, `viewed_cart_sessions`) 와 **`behavior_conversion_daily`** (grain: …, event_name · 컬럼: `done_sessions`, `done_cart_sessions`, `not_done_sessions`, `not_done_cart_sessions`) | E3 `conversion`·`behaviors`, E4 `same_skin_filter_rate` | "그 콘텐츠를 본 세션의 담기율" 은 `funnel_session_fact` 와 세션 조인이다. 프론트가 못 한다. 화면의 핵심 열(할 일 판정 up/fix)이 여기서 나온다 |
| 6-3 | **`product_exit_daily`** (grain: …, product_id, `last_content_kind` · 컬럼: `exit_sessions`) 와 `product_daily_kpi` 에 `variant_select_count`, `quick_look_close_open_detail_count` | E2 `diagnostics` | 상품 진단 표의 이탈 지점·옵션 왕복·퀵룩→상세 |
| 6-4 | `persona_segment_daily_kpi` 에 `segment_type = 'skin_type_x_skin_tone'` (`segment_value = "dry|fair"`) 행 추가, **`segment_content_daily`** (grain: …, skin_type, content_kind · `dwell_ms_sum`) | E4 `grid`·`top_content` | 히트맵 4×5 와 "고객군별 가장 오래 본 콘텍츠" |
| 6-5 | **`friction_daily`**, **`exit_daily`**, **`entry_source_daily`** (§3 E6 표) | E6 전부 | 막히는 곳 화면 전체 |

이미 `docs/dashboard/action-prescription-prompt.md` §9 와 `data-event-backlog.md` 에 올린 요청과 겹치는 것은 그쪽 번호를
이 표에 적어 하나로 합친다.

---

## 7. 프론트 동작 (이미 구현 · 참고)

- 대시보드가 뜨면 브랜드·기간별로 E1~E6 를 **병렬로 한 번** 부른다 (`useBehavior.tsx`). 기간 셀렉터가 바뀌면 다시 부른다.
- 응답이 없거나(401·403·5xx·네트워크) `coverage: none` 이면 그 화면은 기존 모의 집계 그대로이고 배지는 "모의".
  응답이 있으면 채워진 블록만 "실측" 배지로 바뀌고, `null` 블록은 모의로 남는다. 화면마다 섞일 수 있고 배지가 그 사실을
  드러낸다.
- 사이드바 하단에 "마트 갱신 {mart_processed_at}" 또는 "행동 지표는 모의 집계" 를 적는다.
- 모의 집계 코드는 지우지 않는다. 시연 브랜드(SSAFY Beauty)는 행동 로그가 0건이라(재설계 명세 §0-1) 마트가 붙어도
  `coverage: none` 이 정상이고, 그때 화면이 비면 안 된다.

---

## 8. 열린 질문

1. `actorType` 기본을 `all` 로 둘지 `synthetic` 으로 둘지. PA 100명 로그는 정성 축이라(명세 §0-1) 정량 지표에 섞지
   않기로 했는데, PA 의 `actor_type` 이 `web` 인지 `synthetic` 인지에 따라 기본값이 달라진다. 데이터 파트 확인 필요.
2. 세포라 카탈로그 브랜드(Drunk Elephant 등 55개)는 shop_backend `brand` 행이 없다. 시연에서 행동 화면을 그 브랜드로
   보려면 `seed_catalog` 상품의 브랜드를 `brand` 테이블에 시드하고 시연 판매자 계정에 연결해야 한다
   (`docs/shop-backend-requests.md` 5번 시드와 함께).
3. `previous` 기간 비교를 서버가 줄지 프론트가 두 번 부를지. 초안은 서버가 준다 (요청 한 번).
