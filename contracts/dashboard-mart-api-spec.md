# 브랜드 대시보드 마트 조회 API 계약 (백엔드 ↔ 프론트 · 데이터)

> 상태: **초안 0.3.2 (2026-09-16, 프론트 작성).** 데이터 파트와 합의됨. 0.2.1 → 0.3: 데이터 파트가 §6 요청 마트를
> **전부 만들었다**(이은솔, 09-14~16). §5 를 실제 마트 목록으로 갈아 끼우고(마트 12종 신설 · 컬럼 3개 추가), 읽는
> 규칙(합산 금지 컬럼·`cart_lift`·0행 의미)을 각 엔드포인트에 적었다. **E4 에 가격 블록과 코호트 배지를 더한다** —
> 후자는 §1-5 의 "코호트·중앙값 비교는 이 계약 범위 밖" 선언을 뒤집는 결정이다(§1-5 참고).
>
> 0.3 → 0.3.1 (데이터 파트 확인 09-16): `segment_price_band_daily_kpi` 행 수 1,176 확인 · `brand_cohort_dim` 을
> **projection 대상으로** (백엔드가 `cohort_key` 를 알 수 없다는 지적이 맞았다) · 6-7 시드 제외 확인 완료 ·
> `brand_hash` (B) 존치 확정 · 코호트 생존 브랜드 수 **31개(55%) 확정**(35개는 착수 전 추정이었다) ·
> 억제 분해 R3 27행 / R1 9행.
>
> 0.3.1 → 0.3.2 (데이터 파트 전수 점검 회신 09-16): **§8-1 을 닫았다** — PA 는 `actor_type` 이 아니라
> `generator_type` 으로 가른다(새 `actor_type` 값은 모든 마트의 grain 을 바꾼다). 그에 맞춰 §1-2 에
> `generatorType` 쿼리를 추가했다. 이벤트 금액 단위와 `ingredient_interest_kpi` 철회는 재설계 명세
> §6-1·§6 에 적었다. 남은 것은 조건부 블록 해제 순서뿐이고 백엔드까지 셋이 정한다(§8-5).
>
> 0.2 → 0.2.1: 데이터 235 E2E 결함 보고(이은솔, 09-11)를 반영 —
> `view_to_cart_rate` 분모를 **`detail_view_sessions`(상세 조회 ∪ 퀵룩 세션)** 로, 퍼널 계열 마트에서 **seed 세션 제외**, `brand_daily_kpi` 행 수
> 876 → 336 수용, E7 마트 3종은 실데이터 미검증(§8-4). 프론트 폴백(`martAdapter.ts` `cartRateOf`)은 이미 같은 분모다. 0.1 → 0.2: 0.1 → 0.2: `content_daily_kpi`·`persona_segment_daily_kpi` 는 dw-schema 의
> **후보**일 뿐 Spark 잡이 만들지 않는 것을 확인해 E3·E4 를 조건부로 내렸고, 이미 만들어지는 구매·재구매 마트를 E7 로 넣었다.
> 세포라 브랜드의 `brand_id` 정합 방법(§8-2)을 결정안으로 적었다. 이 문서가 확정되면 `README.md` 단일 출처 표에
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
| `generatorType` | N | `all` | **0.3.1 추가.** PA(에이전트)와 PC(배치 생성)를 가르는 축. 마트 key 의 `generator_type` 을 필터한다. PA 로그는 정성 축이라(명세 §0-1) 정량 지표에서 빼고 싶을 때 쓴다 — `actorType` 으로는 못 가른다 (§8-1) |

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

### 1-5. 표본 억제는 하지 않는다 — A층 한정

서버는 표본이 작아도 **내 브랜드 값**은 그대로 준다. 200 미만 흐림·50 미만 비움은 **프론트 규칙**이다 (재설계 명세 §0-5).
다른 브랜드의 값은 어떤 형태로도 섞지 않는다 (경계 문서 A층).

**0.3 에서 한 군데 열었다 — 코호트 분위(B층).** 0.2.1 까지 "코호트·중앙값 비교는 이 계약 범위 밖" 이었으나,
`commons_cohort_weekly` (dw-schema §4.18) 가 생겨 E4 `cohort` 블록으로 받는다 (§3 E4). 뒤집는 근거는 그 마트가
**브랜드 식별자를 아예 싣지 않고** 억제(R1·R3)를 마트 단계에서 이미 걸어 두어, 계약이 지키려던 것 — "다른 브랜드
값이 식별 가능한 형태로 섞이지 않는다" — 이 그대로 유지되기 때문이다. 경계 문서 §2 B층·L210-214 의 배지가 이 자리다.

그래서 이 계약에서 **억제는 여전히 서버가 하지 않는다.** B층 억제는 마트가 이미 했고 서버는 그 결과(`NULL` + 플래그)를
통과시킬 뿐이다. 억제된 셀은 행을 지우지 않고 값만 `null` 로 온다 — 화면이 "표본 부족" 으로 적는다 (경계 문서 L166).

---

## 2. 엔드포인트 한눈에

| # | 경로 | 화면 | 주 마트 | 상태 |
| --- | --- | --- | --- | --- |
| E1 | `GET /api/seller/dashboard/overview` | 요약 | `brand_daily_kpi`, `product_daily_kpi`, `funnel_daily_kpi` | 가능 |
| E2 | `GET /api/seller/dashboard/products` | 상품 · 요약 관심도 TOP | `product_daily_kpi`, `funnel_daily_kpi`, `product_exit_daily` | **가능** (0.3 · 진단 3열 재료도 생김) |
| E3 | `GET /api/seller/dashboard/content` | 상세 콘텐츠 | `content_daily_kpi`, `content_conversion_daily`, `behavior_conversion_daily` | **가능** (0.3 · 마트 생김) |
| E4 | `GET /api/seller/dashboard/segments` | 고객군 | `persona_segment_daily_kpi`, `segment_content_daily`, `segment_price_band_daily_kpi`, `brand_price_band_daily_kpi`, `commons_cohort_weekly` | **가능** (0.3 · 마트 생김) |
| E5 | `GET /api/seller/dashboard/ingredients` | 성분 · 상세 콘텐츠 드래그 TOP | `ingredient_weekly_interest` | 가능 |
| E6 | `GET /api/seller/dashboard/friction` | 막히는 곳 | `friction_daily`, `entry_source_daily`, `exit_daily` | **가능** (0.3 · `event_volumes` 만 조건부) |
| E7 | `GET /api/seller/dashboard/purchase` | 요약 재구매 배지 · 상품 재구매 | `brand_repurchase_daily`, `product_repurchase_daily`, `purchase_reason_daily` | **가능** (마트 있음 · 0.2 신설) |

"가능" = Spark 잡이 **실제로 만드는** 마트로 채울 수 있다. "조건부" = 마트 컬럼이나 세션 조인이 없어 §6 요청이 먼저
처리돼야 한다. 조건부 블록은 응답에서 `null` 로 오고 프론트가 그 블록만 모의로 채운다.

**0.3 에서 E2·E3·E4·E6 이 전부 "가능" 으로 올라갔다.** 데이터 파트가 §6 요청을 09-14~16 에 구현했다 (§5 표).
`event_volumes` 하나만 재료가 없다 — `realtime_event_stats` · `event_daily` 둘 다 dw-schema §5 에 후보로만 있고 구현이
없다. 티켓은 등록됐고(`S15P21A306-323`) 우선순위는 가장 낮다. B-1·B-2 projection 갱신 뒤에 만든다 (§8-5).

**단, "마트가 있다" 와 "엔드포인트가 있다" 는 다르다.** 이 표는 마트 쪽 재료를 말한다. 실제 해제는 백엔드가 그 블록을
구현하고 MySQL projection 에 마트가 올라온 뒤다 — 순서는 §8-5 에서 정한다. 그때까지 응답은 계속 `null` 이고
프론트는 모의로 그린다 (§7). 프론트 쪽 타입·어댑터는 블록 단위로 이미 다 있어 추가 작업이 없다
(`martApi.ts` · `martAdapter.ts`).

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
    "information_view_sessions": 2900, "add_to_cart_sessions": 300, "checkout_sessions": 120, "purchase_sessions": 80
  }
}
```

`current` / `previous`:

| 필드 | 원천 | 비고 |
| --- | --- | --- |
| `impression_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, **`detail_view_sessions`** (0.2.1), `unique_user_count`, `product_count_viewed` | `brand_daily_kpi` 합산 | 브랜드 단위 세션 dedup 은 마트가 이미 했다. 일자를 합산하면 여러 날 온 세션이 중복되지만 그대로 둔다 (마트 grain 을 존중) |
| `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `add_to_cart_sessions_by_product`, `remove_from_cart_sessions` | `product_daily_kpi` 브랜드 합산 | 담았다 뺀 비율의 분자·분모. `add_to_cart_sessions_by_product` 는 상품 합산이라 `brand_daily_kpi` 의 `add_to_cart_sessions` 와 다르다. 이름을 다르게 둔 이유 |
| `detail_entry_rate`, `information_view_rate`, `view_to_cart_rate` | 위 합산에서 재계산 | 분모 0 → null. **`view_to_cart_rate = add_to_cart_sessions / detail_view_sessions`** (0.2.1). 분자가 퀵룩 담기를 포함하므로 분모도 퀵룩을 센다 — `product_view_sessions` 로 나누면 1.0 을 넘는 행이 생긴다(데이터 235 E2E: 107/876 행, 최대 20.0). 마트·서버·프론트 폴백 셋이 같은 식이어야 한다 |
| `removal_rate` | `remove_from_cart_sessions / add_to_cart_sessions_by_product` | 같은 마트 안에서 나눈다 |
| `purchase_sessions`, `purchase_count`, `purchase_quantity` | `product_daily_kpi` 브랜드 합산 | 0.2 추가. 실사용자 `purchase` 이벤트가 쌓이면 값이 생긴다 (생성기는 안 만든다). 매출 금액은 DW 범위 밖(dw-schema §6.4) — 기존 `GET /api/seller/dashboard` 의 PAID 합계가 정본 |

`funnel`: `funnel_daily_kpi` 를 브랜드로 합산한 일곱 칸 (+ `detail_view_sessions`, §6-6 이 되면) (`checkout_sessions`·`purchase_sessions` 는 0.2 추가, 마트에 이미 있다). `click_sessions` 가 `brand_daily_kpi` 에 없어 이 마트를 쓴다.
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
| `funnel` | `funnel_daily_kpi` 합산 | 가능. 담기율 분모 `detail_view_sessions` 는 §6-6 — 상품 단위는 `quick_look_sessions + product_view_sessions` 로 **더할 수 없다**(한 세션이 둘 다 가능). 컬럼이 오기 전까지 프론트 폴백은 `product_view_sessions` |
| `diagnostics` | `{ exit_content_kind_top, exit_sessions, variant_select_per_session, quick_look_open_detail_rate }` — `product_exit_daily` (dw-schema §4.24) + `product_daily_kpi` 의 `variant_select_count`·`quick_look_close_open_detail_count` | **재료 있음** (0.3 · §6-3 구현됨). 백엔드 구현 전까지는 `null` |

`diagnostics` 두 비율은 서버가 나눈다. `variant_select_per_session = variant_select_count / product_view_sessions`,
`quick_look_open_detail_rate = quick_look_close_open_detail_count / quick_look_sessions`. 분모 0 이면 `null`.

**이탈 지점은 `exit_daily` 가 아니라 `product_exit_daily` 다.** 둘은 다른 마트다 (데이터 파트 09-16).

| | `exit_daily` (E6) | `product_exit_daily` (E2) |
| --- | --- | --- |
| 재는 것 | 얼마나 빨리 나갔나 | 어디에서 멈췄나 |
| 원천 | `exit_summary.dwell_ms` | 콘텐츠 Event 의 마지막 시각 |

`exit_summary.last_content_kind` 는 계약에 있지만 재생 데이터 1,000건 중 0건만 값을 싣는다. 그래서 이탈 지점은
콘텐츠 Event 로 따로 낸 것이고, E2 는 `product_exit_daily` 만 읽는다.

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
  "brand": { "product_view_sessions": 4800, "detail_view_sessions": 5100, "add_to_cart_sessions": 300, "view_to_cart_rate": 0.0588 },
  "behaviors": null
}
```

| 필드 | 원천 | 비고 |
| --- | --- | --- |
| 합산 수량 | `content_daily_kpi` (dw-schema §4.4) `product_id`·일자 합산 | **마트 생김** (0.3). `dwell_ms_sum` 은 마트 규칙대로 `content_interest_fact` 기준 — `section_dwell_agg` 와 동시에 더하지 않는다 |
| `product_view_sessions` | 같은 마트의 분모 컬럼. **`content_kind` 축으로 합산하지 않는다** | content_kind 마다 같은 값이 되는 것이 정상. 아래 참고 |
| `avg_dwell_ms_per_session` | `dwell_ms_sum / product_view_sessions` 재계산 | 화면의 "얼마나 오래 읽나" |
| `view_rate` | `section_view_sessions / product_view_sessions` | 화면의 "몇 명이 봤나". 마트에 없어 서버가 만든다 |
| `conversion` | `{ viewed_sessions, viewed_cart_sessions, viewed_cart_rate, cart_lift }` — `content_conversion_daily` (dw-schema §4.19) | **마트 생김** (0.3). `viewed_cart_rate` 까지가 마트 값이고 **`cart_lift` 는 서버가 나눈다** (아래) |
| `brand` | `brand_daily_kpi` 합산 | lift 의 분모. `view_to_cart_rate` 는 E1 과 같은 식(`/ detail_view_sessions`) |
| `behaviors` | `[{ event, done_sessions, not_done_sessions, done_cart_rate, not_done_cart_rate }]` — `behavior_conversion_daily` (dw-schema §4.20) · event ∈ `ingredient_view_mode_change`·`review_filter_apply`·`accordion_toggle`·`text_copy` | **마트 생김** (0.3). 0건이어도 행이 온다 (아래) |

**세 컬럼은 `content_kind` 축으로 합산하면 안 된다** (데이터 파트 09-16 · dw-schema §4.4).
`product_view_sessions`·`ingredient_view_sessions`·`review_view_sessions` 는 **상품 단위**라 `content_kind` 마다 같은
값이 반복된다. 그 축으로 더하면 같은 세션을 콘텐츠 종류 수만큼 센다. 반복시킨 이유는, 행 단위로 세면 `user_review`
행이 `ingredient_view_sessions = 0` 을 달고 나와 "아무도 성분을 안 봤다" 로 읽히기 때문이다.
`avg_dwell_ms_per_session`·`ingredient_view_rate`·`review_view_rate` 가 전부 이 분모를 쓴다. 서버는 이 셋을
**`content_kind` 중 아무 행의 값(전부 같다)** 으로 내보내고, 다른 컬럼만 합산한다.

**`cart_lift` 는 마트에 없다 — 서버가 나눈다.**

```text
cart_lift = content_conversion_daily.viewed_cart_rate / brand_daily_kpi.view_to_cart_rate
```

마트에서 미리 나누면 어느 브랜드·어느 기간의 비율을 썼는지가 행에 박혀 다른 기준으로 다시 볼 수 없다 (데이터 파트
09-16). 계약 §1-3 의 "비율은 서버가 합산값에서 다시 계산한다" 와 같은 규칙이고, 분모는 `brand` 블록의
`view_to_cart_rate` 다 — 응답 안에 분모를 같이 실어 화면이 검산할 수 있게 한다. 분모 0 이면 `null`.

**`behaviors` 는 행동 0건이어도 행이 온다.** 네 Event 가 항상 전부 나오고, `done_sessions = 0` 이면
`done_cart_rate` 가 `null` 이다 — **"아무도 안 했다" 이지 "집계 안 함" 이 아니다.** 재생 데이터에서 `text_copy` 가
128세션뿐이라 실제로 밟는다. 화면은 이 둘을 다르게 적는다 (0건 → "아무도 하지 않음", 블록 자체 `null` → 모의 배지).
검산: `done_sessions + not_done_sessions` = 그 상품의 조회 세션 수.

`content_kind` 는 상품 상세 안에서 읽는 10종만 프론트가 고른다 (`ingredient_list`·`ingredient_callout`·`clinical_claim`·
`user_review`·`review_stats`·`what_it_is`·`what_else`·`usage_guide`·`brand_story`·`product_image`). 서버는 필터하지 않고
마트에 있는 종류를 전부 준다.

### E4 `segments`

```json
{
  "by_segment": [
    { "segment_type": "skin_type", "segment_value": "dry", "segment_user_count": 1100, "session_count": 1500,
      "product_view_sessions": 1240, "detail_view_sessions": 1300, "add_to_cart_sessions": 88, "view_to_cart_rate": 0.068, "avg_interest_score": 3.1 }
  ],
  "grid": null,
  "top_content": null,
  "same_skin_filter_rate": null,

  "price_bands": [
    { "price_bin": "46k-66k", "currency": "KRW", "session_count": 900, "product_count": 4,
      "impression_sessions": 2100, "quick_look_sessions": 90, "product_view_sessions": 640, "detail_view_sessions": 700,
      "add_to_cart_sessions": 58, "purchase_sessions": 0,
      "detail_entry_rate": 0.333, "view_to_cart_rate": 0.083, "view_to_purchase_rate": 0.0 }
  ],
  "segment_price_grid": [
    { "segment_type": "skin_type", "segment_value": "combination", "price_bin": "46k-66k", "currency": "KRW",
      "segment_user_count": 610, "session_count": 780, "product_count": 4,
      "product_view_sessions": 520, "detail_view_sessions": 560, "add_to_cart_sessions": 47, "purchase_sessions": 0,
      "view_to_cart_rate": 0.084, "view_to_purchase_rate": 0.0 }
  ],
  "cohort": {
    "cohort_key": "2-3|105k+", "product_count_band": "2-3", "dominant_price_bin": "105k+",
    "snapshot_week_kst": "2026-09-07", "window_start_date": "2026-09-07", "window_end_date": "2026-09-13",
    "brand_count": 6, "is_suppressed": false, "is_sample_sufficient": true, "is_dominated": false,
    "metrics": [
      { "metric_name": "view_to_cart_rate", "p25": 0.121, "p50": 0.169, "p75": 0.201, "my_value": 0.188, "my_position": "p50_p75" }
    ]
  }
}
```

| 블록 | 원천 | 상태 |
| --- | --- | --- |
| `by_segment` | `persona_segment_daily_kpi` (dw-schema §4.6) 일자 합산. `segment_type` ∈ `skin_type`·`skin_tone`·`skin_type_x_skin_tone` | **마트 생김** (0.3) |
| `grid` | `[{ skin_type, skin_tone, product_view_sessions, detail_view_sessions, add_to_cart_sessions, view_to_cart_rate }]` 20칸 — `persona_segment_daily_kpi` 의 `segment_type = 'skin_type_x_skin_tone'` 행을 `\|` 로 갈라 낸다 | **마트 생김** (0.3). 화면 히트맵(S1)의 정본 |
| `top_content` | `[{ skin_type, content_kind, dwell_ms_sum, dwell_share }]` 타입 4행 × 상위 2 — `segment_content_daily` (dw-schema §4.25) | **마트 생김** (0.3) |
| `same_skin_filter_rate` | `review_filter_apply(same_skin_type)` 세션 / 필터 사용 세션 — `behavior_conversion_daily` | **마트 생김** (0.3) |
| `price_bands` | `brand_price_band_daily_kpi` (dw-schema §4.6-1) 일자 합산 | **0.3 신설.** 브랜드 × 가격대 단일 축 |
| `segment_price_grid` | `segment_price_band_daily_kpi` (dw-schema §4.26) 일자 합산 | **0.3 신설.** 재설계 명세 §2-3 **S5** 히트맵(5밴드 × 4타입 = 20셀)의 정본 |
| `cohort` | `commons_cohort_weekly` (dw-schema §4.18) + `brand_cohort_dim` (§3.7) | **0.3 신설.** 경계 문서 L210-214 의 B층 배지. §1-5 참고 |

`grid` 가 `null` 이면 프론트는 히트맵을 모의로 그리고 `by_segment` 는 KPI 한 칸(최고 전환 타입)에만 쓴다.

#### E4 를 읽을 때 틀리기 쉬운 것

**`by_segment` 의 세 축을 합산하지 않는다.** 한 세션이 `skin_type` 행과 `skin_tone` 행에 동시에 들어간다. 교차 축도
단일 축의 분해가 아니라 별도 집계다. 교차 축끼리는 배타라 그 안에서만 합이 성립한다 (dw-schema §4.6).

**세그먼트 합은 `brand_daily_kpi` 보다 작고, 작은 것이 정상이다.** `persona_id` 가 없는 세션은 어느 행에도 들어가지
않는다 — 실사용자의 피부 정보는 이벤트 경로에 없어서다. `skin_tone = 'notSureST'` 도 값이 아니라 결측이라
`segment_value` 가 되지 않는다. 화면은 세그먼트 합계를 브랜드 총계로 적지 않는다.

**세 가격 마트를 서로 대체하지 않는다.** `price_bin` 을 걷어낸 `segment_price_grid` 합계는 `by_segment` 와 같지
않고, `segment_*` 를 걷어낸 합계는 `price_bands` 와 같지 않다. 한 세션이 여러 구간의 상품을 밟으면 구간마다 한 번씩
세어지기 때문이다. 서버는 **축을 걷어낸 합계를 만들지 않는다** — 필요한 축의 마트를 그대로 읽는다.

**가격 구간은 계약이 정하지 않는다.** `product-feature-vocab.json` 의 `price_bin_edges` 가 정본이고, 어휘집 0.7 기준
원화 5구간이다 (`~26k` · `26k-46k` · `46k-66k` · `66k-105k` · `105k+`, 반열린 `[하한, 상한)`). 가격이 결측·0 이하인
상품은 `price_bin = null` 행으로 보존한다 — 빼면 그 상품들의 반응을 볼 수 없다. `currency` 는 key 다.

**`segment_price_grid` 는 지금 한 줄만 찬다.** 재생 데이터의 페르소나 1,000명이 전원 `combination|light` 라 20셀 중
5셀만 값이 있다. 층화 표본 재생성(Jira 318 반영 완료, 로그 재생성 대기) 뒤에 채워진다. 화면은 이 상태를 빈칸으로
그린다 — 마트가 표본 미달 셀을 지우지 않고(A층이라 억제 없음) 화면이 `n<50` 비움·`n<200` 흐림을 적용한다.

#### `cohort` — 유일한 B층 블록

`commons_cohort_weekly` 는 **브랜드 식별자가 없다.** 서버가 `brand_cohort_dim` 에서 이 brandId 의 `cohort_key` 를
찾아 해당 코호트 행만 골라 준다. 응답에도 다른 브랜드를 식별할 값은 없다.

| 필드 | 뜻 |
| --- | --- |
| `p25` · `p50` · `p75` | 코호트 안 브랜드들의 **주간** 비율 분위. 억제되면 셋 다 `null` |
| `brand_count` | 셀 안 브랜드 수 (R1 판정 근거). 절대 건수가 아니다 (R4) |
| `is_suppressed` | R1(브랜드 5 미만) 또는 R3(한 브랜드가 분모 50% 초과) 위반. `true` 면 분위 3종이 `null` |
| `is_sample_sufficient` | R2 — 코호트 주간 분모가 하한 이상. `false` 여도 값은 온다 (흐림 판정은 화면) |
| `my_value` | **내 브랜드**의 같은 주·같은 지표 값. `brand_daily_kpi`(A층)에서 서버가 낸다 |
| `my_position` | `below_p25` · `p25_p50` · `p50_p75` · `above_p75` · `null`(억제·분위 없음) |

`metric_name` 은 현재 `detail_entry_rate` · `view_to_cart_rate` · `information_view_rate` 셋이다. 롱 포맷이라
지표가 늘어도 grain 이 바뀌지 않는다.

**억제된 셀은 행을 지우지 않고 값만 비운다.** 행이 사라지면 "억제됐다" 와 "코호트가 아예 없다" 를 구분할 수 없다.
화면은 `is_suppressed` 면 배지 자리에 **"표본 부족"** 을 적고 숫자를 적지 않는다 (경계 문서 L166).

**빈칸이 많을 것을 전제한다.** 재생 데이터에서 코호트 17개 중 브랜드 5개 이상인 것이 5개뿐이라 31/56 브랜드만
배지를 보고 나머지 25개는 빈칸을 본다. 억제 51행 중 36행이고 분해는 **R3 27행 · R1 9행**이다 — 상품 1~3개짜리 브랜드가 모인
코호트라 한 브랜드가 조회 세션 절반을 넘기 쉽다. **규칙대로 동작하는 것이다.**

`cohort` 자체가 `null` 인 경우가 둘 있다: 이 브랜드의 `cohort_key` 가 `null`(전 상품 가격 결측)이거나, 그 주
코호트 행이 아직 없을 때. 화면은 배지를 그리지 않는다 — 모의로 채우지 **않는다.** 다른 브랜드와의 비교는
모의값으로 흉내 내면 안 되는 종류의 숫자다.

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

### E6 `friction` (0.3 · `event_volumes` 만 조건부)

```json
{
  "by_location": [ { "section_id": "product_image", "event_name": "dead_click", "event_count": 412, "session_count": 380 } ],
  "counts": { "rage_click": 121, "dead_click": 412, "scroll_backtrack": 2900 },
  "quick_exit_rate": 0.29,
  "entry_source": [ { "entry_source": "similar_products", "product_view_sessions": 860, "detail_view_sessions": 900, "add_to_cart_sessions": 95, "view_to_cart_rate": 0.106 } ],
  "event_volumes": [ { "event_name": "section_dwell", "event_count": 30000 } ]
}
```

| 블록 | 마트 | 상태 |
| --- | --- | --- |
| `by_location`, `counts` | `friction_daily` (dw-schema §4.21) | **마트 생김** (0.3) |
| `quick_exit_rate` | `exit_daily` (dw-schema §4.22 · `exit_summary.dwell_ms < 3000` 세션 / 상세 세션) | **마트 생김** (0.3) |
| `entry_source` | `entry_source_daily` (dw-schema §4.23) | **마트 생김** (0.3) |
| `event_volumes` | `realtime_event_stats` 또는 `event_daily`. 브랜드 필터 가능해야 한다 | **재료 없음** — 티켓 `S15P21A306-323`. 우선순위 최하 (§8-5) |

#### E6 을 읽을 때 틀리기 쉬운 것

**0 이어도 행이 온다.** `rage_click`·`dead_click`·`scroll_backtrack` 세 Event 가 위치마다 전부 행으로 나온다.
재생 데이터에서 `dead_click` 은 생성기가 만들지 않아 0 이고, `rage_click` 43건은 전부 시드라 시드 제외 후 0 이다.
**실질 신호는 `scroll_backtrack` 1,883건뿐이다.** 화면은 0 을 지우지 않고 "이 로그에는 없다" 로 적는다.

**`exit_daily` 를 상품 축으로 합산하면 안 된다.** `exit_summary` 는 세션 단위 Event 라 상품이 없다. 그 세션이 상세를
연 상품 전부에 귀속되므로 상품 축으로 더하면 세션이 부푼다. 브랜드 단위로만 읽는다.

**`entry_source_daily` 를 `entry_source` 축으로 합산하면 안 된다.** 브랜드 단위라 한 세션이 여러 경로 행에 들어가
중복된다. 경로별로 비교만 하고 합계를 만들지 않는다.

**`quick_exit_rate` 는 지금 축퇴돼 있다 — 1.0 을 전제로 화면을 설계하지 않는다.** `exit_summary` 가 기록된 세션
13,251건이 전부 체류 3초 미만이다. 생성기가 `dwell_ms` 를 항상 3초 미만으로 내기 때문이고 마트 계산이 아니라
입력의 문제다. 생성기가 고쳐지면 값이 갈린다. 그래서 개요 화면의 이탈률 칸은 이 값을 **그대로 적기만 하고**
"높다/낮다" 판정 문장을 붙이지 않는다.

**이탈 "지점" 은 여기가 아니라 E2 `diagnostics` 다.** `exit_daily` 는 얼마나 빨리 나갔나, `product_exit_daily` 는
어디에서 멈췄나를 잰다 (E2 참고).

### E7 `purchase` (0.2 신설 · 마트 있음)

```json
{
  "brand": { "buyer_count": 210, "repeat_buyer_count": 34, "purchase_order_count": 260, "repurchase_rate": 0.162,
             "median_days_between_purchases": 21.0, "declared_restock_order_count": 12,
             "window_days": 90, "window_start_date": "2026-06-12", "window_end_date": "2026-09-09" },
  "products": [ { "product_id": "SB000001", "buyer_count": 40, "repeat_buyer_count": 6, "purchase_order_count": 48, "repurchase_rate": 0.15 } ],
  "reasons": [ { "reason": "restock", "order_count": 12, "primary_order_count": 9, "reason_share": 0.31 } ]
}
```

| 블록 | 원천 | 비고 |
| --- | --- | --- |
| `brand` | `brand_repurchase_daily` 의 **최신 `snapshot_date_kst` 한 행** (합산하지 않는다 — 창 단위 스냅샷) | 화면의 "재구매 배지 · 단위 = 브랜드" (ai-insight-rules §2-1). 상품 단위 재구매를 더해서 만들 수 없다 (같은 브랜드 다른 상품 재구매) |
| `products` | `product_repurchase_daily` 최신 스냅샷, 브랜드 상품 전부 | 상품 화면 열 하나 |
| `reasons` | `purchase_reason_daily` 를 기간 합산 · `reason` NULL(건너뜀)은 `skipped_order_count` 로만 | 선언 재구매(`restock`) vs 관측 재구매 대조 |

`from`·`to` 는 `reasons` 에만 적용된다. 재구매 두 마트는 창(`window_days`)이 이미 들어 있어 최신 스냅샷을 그대로 준다.

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

key 는 `dw-schema.md` §4 그대로. **0.3 에서 마트 12종이 신설되고 컬럼 3개가 늘어 이 표를 다시 썼다** (데이터 파트
보고 2026-09-14~16). 행 수는 현재 재생 데이터 기준 참고값이다.

#### 5-1. 이미 projection 된 마트 (E1·E2·E5·E7)

| 마트 | 사용 컬럼 |
| --- | --- |
| `brand_daily_kpi` | key 전체, `impression_sessions`, **`click_sessions`** (0.3 · Jira 277 · §6-1 해결), `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, **`detail_view_sessions`** (0.2.1, 데이터 235 수정안 2), `unique_user_count`, `product_count_viewed`, `mart_processed_at` |
| `product_daily_kpi` | key 전체, `product_impression_count`, `product_click_count`, `quick_look_count`, `product_view_count`, `add_to_cart_count`, `remove_from_cart_count`, `quick_look_sessions`, `product_view_sessions`, **`detail_view_sessions`** (0.3), `add_to_cart_sessions`, `remove_from_cart_sessions`, `unique_user_count`, `session_count`, `product_interest_score`, `mart_processed_at` |
| `product_daily_kpi` (추가) | `purchase_sessions`, `purchase_count`, `purchase_quantity`, **`variant_select_count`**, **`quick_look_close_open_detail_count`** (0.3 · Jira 317 · E2 `diagnostics`) |
| `funnel_daily_kpi` | key 전체, `impression_sessions`, `quick_look_sessions`, `quick_look_cart_sessions`, `click_sessions`, `product_view_sessions`, `information_view_sessions`, `add_to_cart_sessions`, `detail_view_sessions`, `checkout_sessions`, `purchase_sessions`, `mart_processed_at` |
| `ingredient_weekly_interest` | 전 컬럼 |
| `brand_repurchase_daily` · `product_repurchase_daily` | 전 컬럼 (최신 스냅샷만 읽음) |
| `purchase_reason_daily` | key 전체, `order_count`, `primary_order_count`, `skipped_order_count`, `reason_share`, `mart_processed_at` |

**`product_daily_kpi` 의 담기·구매율 분모가 `detail_view_sessions` 로 바뀌었다** (Jira 277). 이전
`product_view_sessions` 로는 1,248행 중 323행이 1.0 을 넘었다 (최댓값 6.0). 계약 0.2.1 이 E1·E2 에서 같은 분모를
쓰기로 한 것과 이제 마트가 맞는다 — 마트·서버·프론트 폴백 셋이 같은 식이다.

#### 5-2. 0.3 에서 새로 생긴 마트 (전부 dw-schema 에 계약 있음)

| 마트 | 행 | 계약 | 쓰는 곳 | 사용 컬럼 |
| --- | --- | --- | --- | --- |
| `persona_segment_daily_kpi` | 1,008 | §4.6 | E4 `by_segment`·`grid` | 전 컬럼. `product_id` 가 key 에 **없다** — 브랜드 grain |
| `brand_price_band_daily_kpi` | 588 | §4.6-1 | E4 `price_bands` | 전 컬럼 |
| `segment_price_band_daily_kpi` | 1,176 | §4.26 | E4 `segment_price_grid` (S5 히트맵) | 전 컬럼 |
| `commons_cohort_weekly` | 51 | §4.18 | E4 `cohort` 배지 | 전 컬럼 |
| `brand_cohort_dim` | 56 | §3.7 | E4 `cohort` — 내 `cohort_key` 조회 | `brand_id`, `cohort_key`, `product_count_band`, `dominant_price_bin` |
| `content_daily_kpi` | 17,603 | §4.4 | E3 | 전 컬럼 |
| `content_conversion_daily` | 15,763 | §4.19 | E3 `conversion` | 전 컬럼 |
| `behavior_conversion_daily` | 4,388 | §4.20 | E3 `behaviors` · E4 `same_skin_filter_rate` | 전 컬럼 |
| `friction_daily` | 4,566 | §4.21 | E6 `by_location`·`counts` | 전 컬럼 |
| `exit_daily` | 1,238 | §4.22 | E6 `quick_exit_rate` | 전 컬럼 |
| `entry_source_daily` | 647 | §4.23 | E6 `entry_source` | 전 컬럼 |
| `product_exit_daily` | 2,500 | §4.24 | E2 `diagnostics` | 전 컬럼 |
| `segment_content_daily` | 4,581 | §4.25 | E4 `top_content` | 전 컬럼 |

`persona_segment_daily_kpi` 는 0.2.1 까지 이 표에 "마트가 생기면" 으로 적혀 있던 것이다. 이제 있다.
**`product_id` 를 key 에서 뺀 것이 맞다** — 브랜드 단위 세션 수를 상품별로 합산하면 중복된다.

`brand_cohort_dim` 은 브랜드 → 코호트 배정표다. **projection 대상이다** (데이터 파트 확정 09-16). 한때
"`cohort_key` 는 Backend 가 브랜드 인가와 함께 넘긴다" 로 보고 대상에서 빠져 있었는데, 백엔드는 그 값을 알 수 없다 —
Spark 가 만든 Mart 이고 Parquet 에만 있어 백엔드가 읽을 경로가 아예 없다. 56행짜리 작은 표라 그대로 올린다.
서버는 `brand_id` 로 이 표를 조회해 `cohort_key` 를 찾고, 그 값으로 `commons_cohort_weekly` 의 코호트 행을 고른다.

**5-2 의 네 마트는 아직 MySQL 에 없다 (2026-09-16).** 전부 Parquet 에만 있고, B-1·B-2 확정에 따라 projection
대상으로 올라가는 중이다 — `brand_price_band_daily_kpi` · `segment_price_band_daily_kpi` ·
`commons_cohort_weekly` · `brand_cohort_dim`. 적재가 끝나기 전까지 E4 의 `price_bands`·`segment_price_grid`·
`cohort` 는 `null` 이고 화면은 그 블록만 모의로 그린다. **E2 `diagnostics` 의 두 컬럼**
(`variant_select_count`·`quick_look_close_open_detail_count`)은 마트에는 있지만 **Q3 재실행이 필요하다** —
`close_reason` 을 Fact 에 새로 실어서, 다음 E2E 부터 값이 찬다.

#### 5-3. projection 대상이 아닌 것

`banner_daily` · `cross_brand_daily` · `category_price_reference` · `analytics_baseline` 은 읽는 엔드포인트가 없다.
**소비자 없는 마트는 옮기지 않는다** 는 원칙에 프론트도 동의한다 (dw-schema §7.2).

인덱스 권고: `(brand_id, event_date_kst)` 선두. `ingredient_weekly_interest` 는 `(interest_week_kst)`,
`commons_cohort_weekly` 는 `(cohort_key, snapshot_week_kst)`.

---

## 6. 신규 마트·컬럼 요청 (데이터 파트) — **전부 처리됨 (0.3)**

> **상태 2026-09-16: 6-1 ~ 6-7 전부 처리됐다.** 아래 표는 무엇을 왜 요청했는지의 기록으로
> 남긴다. 실제로 만들어진 마트의 계약은 `dw-schema.md` §4 이고, 대시보드가 쓰는 컬럼은 §5-2 다. 두 곳이 갈라지면
> dw-schema 가 정본이다.
>
> | # | 상태 | 어디로 갔나 |
> | --- | --- | --- |
> | 6-1 | 완료 | `brand_daily_kpi.click_sessions` (Jira 277) |
> | 6-2 | 완료 | `content_daily_kpi` §4.4 · `content_conversion_daily` §4.19 · `behavior_conversion_daily` §4.20 |
> | 6-3 | 완료 | `product_exit_daily` §4.24 + `product_daily_kpi` 2컬럼 (Jira 317) |
> | 6-4 | 완료 | `persona_segment_daily_kpi` §4.6 (교차 축 포함) · `segment_content_daily` §4.25 |
> | 6-5 | 완료 | `friction_daily` §4.21 · `exit_daily` §4.22 · `entry_source_daily` §4.23 |
> | 6-6 | 완료 | `detail_view_sessions` 가 §4.1·§4.5·§4.6·§4.6-1·§4.14·§4.26 에 들어갔다 |
> | 6-7 | 완료 | E7 3종도 dw-schema §4.0 표에 "제외" 로 등재. `properties.seeded` 는 `event-properties-schema.md` §3.14 에 등재됐고 **"판정은 `properties.seeded` 를 정본으로 한다"** 까지 명시됐다 (`session_id` 의 `seed:` 접두는 파생) |

조건부 블록을 채우려면 아래가 필요했다. 우선순위 순. 각 항목은 없어도 API 는 200 을 주고 블록만 `null` 이다.

| # | 요청 | 채우는 블록 | 왜 마트여야 하나 |
| --- | --- | --- | --- |
| 6-1 | `brand_daily_kpi` 에 `click_sessions` 추가 | E1 `funnel` | 브랜드 세션 dedup 퍼널. 지금은 상품 합산으로 대신한다 |
| 6-2 | **`content_daily_kpi` 물리화** (dw-schema §4-4 후보 그대로) + **`content_conversion_daily`** (grain: event_date_kst, brand_id, product_id, content_kind · 컬럼: `viewed_sessions`, `viewed_cart_sessions`) 와 **`behavior_conversion_daily`** (grain: …, event_name · 컬럼: `done_sessions`, `done_cart_sessions`, `not_done_sessions`, `not_done_cart_sessions`) | E3 `conversion`·`behaviors`, E4 `same_skin_filter_rate` | "그 콘텐츠를 본 세션의 담기율" 은 `funnel_session_fact` 와 세션 조인이다. 프론트가 못 한다. 화면의 핵심 열(할 일 판정 up/fix)이 여기서 나온다 |
| 6-3 | **`product_exit_daily`** (grain: …, product_id, `last_content_kind` · 컬럼: `exit_sessions`) 와 `product_daily_kpi` 에 `variant_select_count`, `quick_look_close_open_detail_count` | E2 `diagnostics` | 상품 진단 표의 이탈 지점·옵션 왕복·퀵룩→상세 |
| 6-4 | **`persona_segment_daily_kpi` 물리화** (dw-schema §4-6 후보 그대로) + `segment_type = 'skin_type_x_skin_tone'` (`segment_value = "dry|fair"`) 행 추가, **`segment_content_daily`** (grain: …, skin_type, content_kind · `dwell_ms_sum`) | E4 `grid`·`top_content` | 히트맵 4×5 와 "고객군별 가장 오래 본 콘텍츠" |
| 6-5 | **`friction_daily`**, **`exit_daily`**, **`entry_source_daily`** (§3 E6 표) | E6 전부 | 막히는 곳 화면 전체 |
| 6-6 | **`detail_view_sessions`** 를 `view_to_cart_rate` 가 있는 마트 전부에 — `funnel_daily_kpi`(상품·브랜드 퍼널), `persona_segment_daily_kpi`·교차 축(6-4), `entry_source_daily`(6-5). `brand_daily_kpi` 는 데이터 235 수정안에 이미 포함 | E2 `funnel` 담기율, E4 `by_segment`·`grid`, E6 `entry_source` | 세션 합집합(상세 ∪ 퀵룩)이라 프론트·서버가 두 컬럼을 더해 만들 수 없다. 한 화면 안에서 브랜드(E1)와 상품(E2) 담기율 분모가 다르면 안 된다 |
| 6-7 | **seed 세션 제외**를 퍼널 계열 마트(데이터 235 수정안 1: `funnel_session_fact`·`product_daily`·`funnel_daily`·`brand_daily`·`cross_brand_daily`)에 더해 E7 의 재구매·구매사유 마트에도 같은 원칙으로. 판정은 `session_id` 접두 `seed:` 보다 생성기가 우선으로 찍는 **`properties.seeded = true`** (`gen_behavior_logs.py` `is_seed`) 로 — 이 필드를 `event-properties-schema.md` 에 적어 달라 | 전 엔드포인트 | seed 는 페르소나 선호 주입용(persona-schema §9)이라 방문이 아니다. 전체 세션의 57% 가 seed 였다 |

`docs/dashboard/action-prescription-prompt.md` §9 와 겹친다: §9-1 콘텐츠별 담기율 = 6-2 · §9-2 `scroll_backtrack` 의 `content_kind` 귀속 = 6-5 `friction_daily.section_id` · §9-6 겹쳐 보인 체류 제외 합계 = 6-2 물리화 때 `co_visible_blocks ≤ 2` 필터. 한 표로 본다.

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

1. ~~`actorType` 기본을 `all` 로 둘지 `synthetic` 으로 둘지~~ — **닫힘 (2026-09-16).** `actorType` 기본은 `all` 이고,
   **PA 를 가를 때는 `generatorType` 을 쓴다** (§1-2).
   경위: PA 100명 로그는 정성 축이라(명세 §0-1) 정량 지표에 섞지 않기로 했는데, 데이터 답(09-11)이
   "PA 도 전부 `synthetic`"(`gen_behavior_logs.py` 고정) 이라 `actorType` 으로는 못 갈랐다. 그래서 PA 에 별도
   `actor_type`(예: `agent`)을 줄 수 있는지 물었고, 데이터 답(09-16)은 **주지 않는다** 였다 — `actor_type` enum 에
   새 값을 넣으면 **기존 모든 마트의 grain 이 바뀐다.** 대신 PA 와 PC 가 이미 `generator_type` 으로 갈려 있고
   Jira 324 에서 그 값이 모든 마트 key 에 들어갔다.
2. **세포라 브랜드의 `brand_id` (결정안 0.2 → 데이터 확인 09-11: 결정안 그대로, `dim_brand` 56 행, 매핑 테이블 불필요).** dw 의 `dim_product.brand_id` 는 원천 `products_200.json` 의 세포라 브랜드
   번호(예 LANEIGE `6125`)를 문자열로 쓴다 (`derive_facts_job.py`). 등록 상품(SB…)만 shop_backend `brand_id` 로 덮어쓴다.
   그래서 세포라 브랜드는 shop_backend `brand` 테이블에 **`brand_id = 세포라 번호 문자열`(`"6125"`), `name = brand_name`** 으로
   시드하고 시연 판매자 계정에 연결하면 이 API 의 `brandId` 가 마트 `brand_id` 와 그대로 만난다. 매핑 테이블이 필요 없다.
   백엔드 시드(`docs/shop-backend-requests.md` 5·7번)에 이 규칙으로 부탁한다. 데이터 파트는 `dim_brand` 에 같은 값이
   들어가는지만 확인.
3. `previous` 기간 비교를 서버가 줄지 프론트가 두 번 부를지. 초안은 서버가 준다 (요청 한 번).
4. **E7 마트 3종(`brand_repurchase_daily`·`product_repurchase_daily`·`purchase_reason_daily`)은 실데이터로 검증된 적이 없다** (데이터 235 E2E 에서
   셋 다 0 행 — 생성기가 `purchase` 를 안 만든다). 생성기가 purchase 를 내고 마트가 한 번 검증되기 전까지 프론트 E7 은 모의값으로 둔다.
   백엔드도 E7 projection 을 그 뒤로 미룬다.
   **09-16 진행:** AI 파트가 에이전트 러너에 `checkout` 행동을 넣었고, 프론트는 배포본에서 카카오페이를 건너뛰는
   `?pay=test` 스위치를 넣었다 (`frontend/src/lib/payment.ts`). 에이전트 주문이 끝까지 가면 `purchase` 가 쌓여
   이 마트 3종이 처음으로 0 행을 벗어난다. 그 로그로 한 번 검증한 뒤 E7 을 실측으로 돌린다.
5. **조건부 블록을 언제 어떤 순서로 해제할지 (0.3 신설 · 백엔드·데이터와 함께 정한다).** 마트는 다 생겼고
   (§5-2) 프론트 타입·어댑터도 블록 단위로 다 있다. 남은 것은 **백엔드 엔드포인트 구현 순서**와 **MySQL projection
   순서**다. 프론트가 혼자 정할 일이 아니라 여기 열어 둔다.

   | 엔드포인트 | 블록 | 필요 마트 |
   | --- | --- | --- |
   | E2 | `diagnostics` | `product_exit_daily` + `product_daily_kpi` 신규 2컬럼 |
   | E3 | 전체 | `content_daily_kpi` |
   | E3 | `conversion`·`behaviors` | `content_conversion_daily`·`behavior_conversion_daily` |
   | E4 | `by_segment`·`grid` | `persona_segment_daily_kpi` |
   | E4 | `top_content` | `segment_content_daily` |
   | E4 | `price_bands`·`segment_price_grid` | `brand_price_band_daily_kpi`·`segment_price_band_daily_kpi` |
   | E4 | `cohort` | `commons_cohort_weekly` + `brand_cohort_dim` (둘 다 projection 대상 · §5-2) |
   | E6 | `by_location`·`counts`·`quick_exit_rate`·`entry_source` | `friction_daily`·`exit_daily`·`entry_source_daily` |
   | E6 | `event_volumes` | **재료 없음** — 티켓 등록됨 (`S15P21A306-323`). 우선순위 최하 |

   프론트 입장은 **전부 해제**다. 블록이 `null` 이면 모의로 물러나므로 부분 해제도 안전하고, 배지가 섞인 상태를
   이미 드러낸다 (§7). 순서는 백엔드 작업량과 시연 일정이 정하는 것이라 여기서 단정하지 않되, 프론트 의견은
   **E3 → E2 `diagnostics` → E4 → E6** 이다 (데이터 파트 이견 없음, 09-16). E3 가 화면의 핵심(콘텐츠별 담기율 =
   할 일 판정)이고 E6 은 실질 신호가 `scroll_backtrack` 하나라 마지막이어도 손해가 적다. E2 를 두 번째로 두면
   `diagnostics` 두 컬럼의 Q3 재실행(§5-2)이 그 사이에 끝나 일정이 맞는다. 백엔드까지 셋이 한 번에 정한다.
6. ~~6-7 (시드 세션 제외)~~ — **확인 완료 (09-16).** E7 3종도 dw-schema §4.0 표에 "제외" 로 등재됐고,
   `properties.seeded` 는 `event-properties-schema.md` §3.14 에 **정본 판정 기준**으로 적혔다.
7. ~~`brand_hash` 존치 여부~~ — **(B) 존치로 확정 (09-16).** 이 계약의 값에는 영향이 없다 —
   `commons_cohort_weekly` 가 내는 숫자는 어느 쪽이든 같고, E4 `cohort` 응답에도 해시가 실리지 않는다.
   근거는 `docs/dashboard/collective-insight-data-boundary.md` §6-5.
