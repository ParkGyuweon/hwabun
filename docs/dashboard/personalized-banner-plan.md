# 성향 반응형 추천 배너 — 같은 상품, 다른 강조

작성: 프론트 (2026-09-07)
상태: 기획 제안. 기획 정리(v0.1) §5 "사용자 성향별 강조 문구", §12 "추천 배너",
§15-10 "추천 배너의 범위" 를 화면과 데이터로 구체화한다. 데이터 파트 확인 항목은 §7.
선행 문서: [`positioning-why-small-brands.md`](./positioning-why-small-brands.md) ·
[`recommendation-io-spec.md`](../../contracts/recommendation-io-spec.md) ·
[`event-properties-schema.md`](../../contracts/event-properties-schema.md) ·
[`data-event-backlog.md`](./data-event-backlog.md)

근거 표기: `[확정]` 기획 정리에 있음 · `[있음]` 코드·계약에 이미 있음 · `[제안]` 이 문서가 정함

---

## 0. 한 줄

> **무엇을 보여줄지는 추천이 정하고, 어떻게 보여줄지는 지금 이 세션의 행동이 정한다.**

지금 목록 화면은 "정렬"이다. 페르소나의 피부 타입으로 점수를 매겨 10개를 줄 세운다
(`ProductListPage.tsx` `promo`, `skin_match_v0`). 상품은 바뀌지만 **말하는 방식은 하나**다.
이 문서는 두 번째 축을 더한다. 같은 세럼이라도 가격을 따지는 사람에게는 가격을, 성분을
따지는 사람에게는 성분을 앞세운다. 그 판단을 페이지를 떠나기 전에, 세션 안에서 한다.

기획 정리가 못 박은 제약 세 가지를 그대로 지킨다 `[확정]`.

| 제약 | 이 문서의 대응 |
|---|---|
| 추천 배너는 유료 광고가 아니다 | 배너에 오르는 상품은 추천 API 결과에서만 고른다. 브랜드가 돈으로 올리는 자리는 없다 |
| 노출 자체는 선호 신호로 쓰지 않는다 | 배너 노출은 CTR 분모로만 쓴다. 성향 추정에도 노출은 넣지 않는다 |
| 클릭·상세 조회·장바구니 반응만 추천에 반영 | 강조 변형(variant)의 학습도 클릭 이후 행동으로만 한다 |

---

## 1. 두 층 구조

```
 ┌─ 층 A. 무엇을 (상품)  ──────────────────────────────────────────────┐
 │  GET /api/recommend?persona_id=…&size=10          [있음]           │
 │  items[].score · breakdown · reason(attribute/content)              │
 │  → 배너 후보 = 상위 N. 브랜드 다양성(MMR)은 API 가 이미 건다        │
 └──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌─ 층 B. 어떻게 (강조 변형)  ────────────────────────────────────────┐
 │  trait = argmax( 세션 점수 ⊕ 장기 성향 ⊕ 콜드스타트 )   [제안]      │
 │  variant ∈ { price, ingredient, review, concern, participate }      │
 │  → 같은 product_id 에 variant 별 카피·강조 요소를 입힌다            │
 └──────────────────────────────────────────────────────────────────┘
```

층 A 는 이미 있다. 이 문서의 작업은 전부 층 B 다. 층 B 는 **프론트에서 먼저 돌아가고**,
데이터 파트가 장기 성향 마트를 주면 그것을 덧입힌다. 마트가 늦어도 데모는 된다.

---

## 2. 성향 5종과 실시간 신호

기획 정리 §5 의 성향 표를 그대로 쓴다. 각 성향을 **이미 수집 중인 이벤트** 로 어떻게
알아내는지가 이 표의 핵심이다. 새 이벤트는 없다.

| 성향 `trait` | 이 사람이 하는 행동 | 세션 신호 (전부 `[있음]`) | 가중 `[제안]` |
|---|---|---|---:|
| `price` 가격을 따진다 | 가격 필터·정렬, 가격 문구 선택, 용량 옵션 왕복 | `filter_change(filter_kind=price)` · `sort_change(price)` · `text_selection(selection_kind=price)` · `section_dwell(content_kind=price)` · `variant_select(variant_kind=size)` | 1.0 · 1.0 · 1.5 · 0.5/초 · 0.5 |
| `ingredient` 성분을 따진다 | 전성분 펼침·표시 전환, 성분 문구 선택·복사, 성분 섹션 체류 | `ingredient_view_mode_change` · `accordion_toggle(ingredients)` · `text_selection/text_copy(selection_kind=ingredient)` · `section_dwell(section_id=ingredients)` · `review_expand(target=ingredients)` | 1.5 · 1.0 · 1.5/2.0 · 1.0/초 · 0.5 |
| `review` 리뷰를 따진다 | 리뷰로 점프, 리뷰 필터, 리뷰 섹션 체류 | `review_expand(review_text/jump_to_reviews)` · `review_filter_apply` · `section_dwell(section_id=reviews)` · `section_dwell(content_kind=review_stats)` | 1.0 · 1.5 · 1.0/초 · 0.5/초 |
| `concern` 피부 고민이 있다 | 고민 필터, 하이라이트 배지·클레임 체류, 클레임 문구 선택 | `filter_change(filter_kind=concern)` · `section_dwell(content_kind=highlight_badge/clinical_claim)` · `text_selection(selection_kind=claim)` · 페르소나 `skin_type` 존재 | 1.5 · 0.5/초 · 1.0 · +1.0 고정 |
| `participate` 같이 키우고 싶다 | 브랜드 스토리 체류, 의견·피드백 남김, 체험단 신청 | `section_dwell(content_kind=brand_story)` · `purchase_reason_select` (backlog 2-1) · 참여 루프 이벤트 (§6) | 1.0/초 · 2.0 · 2.0 |

계산은 단순하다 `[제안]`.

```
trait_score[k] = Σ_events  w(event, k) × decay(세션 내 경과)     decay: 최근 5분 1.0 → 30분 0.3
trait          = argmax_k trait_score[k]
                 단, max < 임계(2.0) 이면 "성향 없음" → §3 콜드스타트
```

체류 계열은 `SECTION_DWELL_WEIGHT` (`log.ts`) 와 방향이 같다. `ingredients`·`reviews` 가
1.5 로 가장 높은 것과 일치하므로 데이터 쪽 해석과 어긋나지 않는다.

**왜 프론트에서 계산하나.** 사용자 벡터(Redis `user:vec:*`)는 상품 벡터의 가중 평균이라
"무엇을 좋아하나" 는 알지만 "무엇을 보고 결정하나" 는 담지 않는다. 그리고 Spark 마트는
세션 안에서 돌아오지 않는다. 세션 성향은 브라우저 메모리(`sessionStorage`)에서 이벤트
발행과 같은 자리(`useLog` 계열)에서 누적하면 **지연 0** 이다.

---

## 3. 세 겹의 성향 — 세션 · 장기 · 콜드스타트

| 겹 | 출처 | 갱신 | 쓰는 때 |
|---|---|---|---|
| **세션** | §2 프론트 계산 | 이벤트마다 | 임계 넘으면 항상 우선 |
| **장기** | 마트 `user_trait_daily` (§7 요청) → 추천 API 응답 또는 별도 조회 | 일 1회 | 세션 신호가 임계 미만일 때 |
| **콜드스타트** | 페르소나 `skin_type` 있으면 `concern`. 없으면 **탐색 로테이션** | — | 둘 다 없을 때 |

탐색 로테이션 `[제안]`: 성향을 모르는 방문자에게는 variant 를 세션 단위로 무작위 배정한다.
이것이 기획 정리 Should 의 "문구 A/B 테스트" 표본이 된다. 성향을 아는 사용자에게도
**20%는 탐색**으로 다른 variant 를 준다. 그래야 "가격 성향인데 성분 문구에 더 반응했다"
를 배울 수 있다.

---

## 4. 배너 화면 — 무엇이 어떻게 바뀌나

### 4-1. 자리

```
 ┌──────────────────────────────────────────────────────────────┐
 │  히어로 배너 (1개, 추천 1위)              [신규]                │
 │  ┌ 이미지 ┐  variant 별 헤드라인 · 강조 칩 · 근거 한 줄       │
 │  │        │  "왜 나에게" = 추천 API reason 그대로              │
 │  └────────┘                                                   │
 ├──────────────────────────────────────────────────────────────┤
 │  지금 주목할 상품 (promo_row, 10개)        [있음 → 카드에 variant 칩 추가]  │
 │  ○ ○ ○ ○ ○ ○ ○ ○ ○ ○                                          │
 ├──────────────────────────────────────────────────────────────┤
 │  카테고리 탭 · 필터 · 그리드                [유지]              │
 └──────────────────────────────────────────────────────────────┘
```

- 히어로는 `storefront_promo` 축(`top`/`side`/`bottom`/`off`)을 따른다. `off` 인 브랜드
  진열에서는 히어로도 없다. 로그 규칙("카드는 `data-log-section` 밖으로 옮기지 않는다")을
  지키기 위해 히어로는 **새 섹션** 으로 둔다 → `section_id` enum 에 `hero_banner` 추가 필요 (§7).
- `promo_row` 는 그대로 두고 카드 위에 variant 칩 하나만 얹는다. 카드 순위·position 은
  건드리지 않는다.

### 4-2. variant 별 강조 요소 — 있는 데이터로만

`[있음]` 은 `Product` 타입에 이미 있는 필드다. 없는 것은 만들어 쓰지 않는다.

| variant | 헤드라인 틀 | 강조 칩 | 쓰는 데이터 | 주의 |
|---|---|---|---|---|
| `price` | "{용량}에 {가격} — 같은 {카테고리} 중앙값보다 {n}% 아래" | 용량당 가격 · 카테고리 대비 | `price_usd` · `size` `[있음]` · 카테고리 가격 중앙값 `[요청]` | **할인율은 쓰지 않는다.** `sale_price_usd` 가 200개 중 198개 비어 있다. "할인" 대신 "용량 대비" 와 "같은 군 대비" 로 말한다 |
| `ingredient` | "{성분1} · {성분2} · {성분3} 이 앞에 있는 {카테고리}" | 상위 성분 3개 · clean 태그 | `ingredients` 전성분 순서 `[있음]` · `highlights` clean 태그 `[있음]` | **함량(%) 데이터가 없다.** 전성분은 함량 순 표기이므로 "앞에 있다" 로 말한다. 브랜드 등록 폼에 핵심 성분 함량 optional 을 둘지는 §7 |
| `review` | "{피부타입} 리뷰 {n}건, 평점 {r}" | 같은 피부 리뷰 수 · 재구매 언급 | `rating` · `review_count` `[있음]` · 피부타입별 리뷰 수 `[있음]`(`reviewSkinTypes`) · 재구매 언급 수 `[요청]` | 리뷰 63.4%가 5점이라 평점만으로는 변별이 없다. **건수와 같은 피부** 를 앞세운다 |
| `concern` | "{고민} 을 위한 {카테고리}" | `Good for:` 태그 · 피부 타입 일치 | `highlights` `Good for:` `[있음]` · `suitable_skin_types` `[있음]` | 페르소나 `skin_type` 과 맞을 때만 "당신 피부" 를 말한다 |
| `participate` | "{브랜드} 가 이 제품에 받은 의견 {n}건, 반영 {m}건" | 의견 수 · 반영 배지 · 체험단 모집 | 참여 루프 카운트 `[요청, §6]` | 데이터가 0이면 "첫 의견을 남겨 보세요" 로 대체. 숫자를 만들지 않는다 |

근거 한 줄("왜 나에게")은 variant 와 무관하게 추천 API `reason.attribute` 또는
`reason.content` 를 그대로 붙인다 `[있음]`. 추천 근거와 강조 문구가 분리되므로
"가격 문구인데 근거는 성분 유사" 같은 조합도 정직하게 드러난다.

---

## 5. 로그 — 무엇을 남기고 무엇을 배우나

새 이벤트를 만들지 않는다. 기획 정리 §12 의 `banner_impression`·`banner_click` 은
이미 있는 `recommendation_impression`·`recommendation_click` 이 담당한다 (`list_id`
로 자리를 구분). `banner_skip` 은 "노출 있음 · 클릭 없음" 으로 마트에서 계산하면 되므로
이벤트로 두지 않는다 — 노출은 신호가 아니라는 원칙과도 맞는다.

**기존 이벤트에 optional 속성 추가** (backlog 2-2 방식, 계약 무해) `[제안]`:

| event_name | 추가 속성 | 값 | 왜 |
|---|---|---|---|
| `recommendation_impression` / `recommendation_click` (`list_id ∈ {hero_banner, promo_pick}`) | `variant` | `price \| ingredient \| review \| concern \| participate` | variant 별 CTR 분모·분자 |
| 위와 같음 | `trait_source` | `session \| profile \| coldstart \| explore` | 성향을 어디서 얻었는지. `explore` 가 A/B 표본 |
| 위와 같음 | `trait_snapshot` | `{price: 2.5, ingredient: 0.5, …}` (반올림) | 성향 점수와 반응의 관계. 임계 재조정 근거 |
| `product_view` (`entry_source=promo_pick` 또는 새 값 `hero_banner`) | `variant` | 위와 같음 | 클릭 → 상세 → 담기 funnel 을 variant 로 자른다 |

배우는 것은 둘이다.

| 질문 | 마트 `[요청]` | 대시보드에서 |
|---|---|---|
| 어떤 성향에 어떤 문구가 먹히나 | `banner_variant_daily`: brand × product × variant × trait_source → impressions, clicks, views, carts | 기획 정리 §13 "추천 배너 반응" 칸. 브랜드는 "가격 성향 방문자에게는 성분 문구가 더 클릭됐다" 를 본다 |
| 사용자의 장기 성향은 무엇인가 | `user_trait_daily`: user × trait → 점수 (§2 식을 세션 대신 30일 창으로) | 소비자 화면에는 안 보인다. §3 "장기" 겹의 입력 |

---

## 6. 참여 루프 이벤트 — `participate` 성향의 재료

`positioning-why-small-brands.md` §3-3 의 4단계 루프가 이 성향의 데이터원이다. 여기서
필요한 새 이벤트는 backlog 2-1 의 `purchase_reason_select` 하나로 시작하고, 아래는
**후속** 이다 `[제안]`.

| 단계 | 이벤트 | 상태 |
|---|---|---|
| ① 의견 남김 | `purchase_reason_select` | backlog 에 있음 |
| ① 개선 의견 | `feedback_submit` (`product_id`, `feedback_kind` enum, 원문 미저장) | 신규 후보 |
| ③ 사장이 반영 | 백엔드 상품 수정 이력 (`product_change` 테이블, 로그 아님) | 백엔드 |
| ④ "반영됐어요" 확인 | `feedback_reflected_view` | 신규 후보 |

배너의 `participate` variant 는 ③④ 카운트를 읽는다. 카운트가 없는 동안은 "첫 의견" 문구다.

---

## 7. 데이터 파트에 확인할 것

아래를 그대로 메시지로 보낸다.

> **[프론트 → 데이터] 성향 반응형 추천 배너, 가능한지 확인 부탁드립니다**
>
> 기획 정리 §5·§12 의 "가격 따지는 사람에겐 가격, 성분 따지는 사람에겐 성분" 배너를
> 화면으로 만들려고 합니다. 상품은 추천 API 가 고르고, **강조 방식(variant)만** 세션 행동으로
> 바꾸는 구조입니다. 새 이벤트 없이 기존 이벤트에 optional 속성만 얹는 방향이고, 세션
> 성향은 프론트에서 계산합니다. 확인 부탁드릴 것은 일곱 가지입니다.
>
> 1. **성향 5종 정의** — `price / ingredient / review / concern / participate` 로 가도
>    되나요? 성향을 알아내는 이벤트 매핑과 가중치 초안은 `docs/dashboard/personalized-banner-plan.md`
>    §2 에 있습니다. `SECTION_DWELL_WEIGHT` 와 방향을 맞췄는데, 데이터 쪽에서 보기에
>    빠지거나 과한 신호가 있으면 알려 주세요.
> 2. **실시간성** — 세션 안에서는 프론트가 `sessionStorage` 로 계산하고, 서버는 장기 성향만
>    주는 구조로 가려 합니다. Spark 마트의 실제 반영 지연이 어느 정도인지(분 단위? 시간
>    단위?) 알려 주시면 "세션 우선, 장기는 보조" 경계를 확정하겠습니다.
> 3. **장기 성향 마트** — `user_trait_daily` (user × trait → 점수, 30일 창) 를 `build_marts`
>    에 얹을 수 있을까요? 있으면 추천 API 응답에 `trait` 필드로 실어 주시거나 별도 조회
>    엔드포인트 중 편한 쪽을 말씀해 주세요.
> 4. **optional 속성 추가** — `recommendation_impression` / `recommendation_click` /
>    `product_view` 에 `variant`, `trait_source`, `trait_snapshot` 을 optional 로 얹습니다
>    (backlog 2-2 와 같은 방식). 계약에 무해한지, 그리고 `section_id` enum 에 `hero_banner`,
>    `entry_source` 에 `hero_banner` 를 추가해도 되는지 확인 부탁드립니다.
> 5. **배너 반응 마트** — `banner_variant_daily` (brand × product × variant × trait_source →
>    노출·클릭·상세·담기) 를 만들어 주실 수 있을까요? 브랜드 대시보드 "추천 배너 반응" 칸의
>    입력입니다. `banner_skip` 은 이벤트로 두지 않고 "노출 − 클릭" 으로 마트에서 계산하는
>    걸로 생각하는데 괜찮은지도요.
> 6. **가격 강조의 재료** — `sale_price_usd` 가 200개 중 198개 비어 있어 할인율은 못 씁니다.
>    대신 "같은 카테고리 가격 중앙값 대비 n%" 를 쓰려 하는데, 카테고리(secondary 또는
>    tertiary)별 가격 중앙값을 마트나 상품 마스터에 넣어 주실 수 있나요?
> 7. **성분 강조의 재료** — 성분 함량(%) 데이터가 없어서 전성분 **순서** 로 "앞에 있는 성분
>    3개" 를 씁니다. 상품 벡터 `ingredient` 블록의 위치가중과 같은 논리인데, 프론트가 전성분
>    순서로 상위 3개를 뽑을 때 쓸 "핵심 성분 30종" 목록(`product-feature-vocab.json`)을
>    그대로 참조해도 되는지 확인 부탁드립니다. 그리고 브랜드 상품 등록 폼에 "핵심 성분
>    함량" optional 입력을 둘지도 의견 주세요.
>
> 6·7 은 없으면 프론트가 "용량당 가격", "전성분 상위 3개" 로 시작하고, 마트가 오면 바꿔
> 끼우겠습니다. 2·4 답이 오면 바로 구현 들어가겠습니다.

---

## 8. UI 수정 목록 — 기획 정리 대비

배너 외에 기획 정리 v0.1 이 요구하는 소비자 화면 변경을 같이 적어 둔다. 우선순위는
기획 정리 §16 을 따른다.

| 기획 정리 | 지금 화면 | 바꿀 것 | 우선 |
|---|---|---|---|
| §1 소비자가 보는 쇼핑몰은 하나, 회원가입 한 번 | 브랜드별 진열(`storefront_*`)이 localStorage 로 전환되는 단일 페이지 | 공동 쇼룸 헤더·브랜드 필터. 진열 축은 **브랜드 상세 페이지** 로 내려보낸다 | Must |
| §5 성향별 강조 문구 | 없음 | 이 문서 §4 | Must (추천 영역) |
| §12 추천 배너 | `promo_row` 10개, 피부 타입 규칙 | 히어로 1개 + `promo_row` 유지, 상품은 추천 API 로 교체 | Must |
| §15-11 리뷰·피드백 작성 (구매자만) | 리뷰 열람만 | 주문 상품당 1개 작성 폼 · 평점 + 개선 피드백 | Must |
| §8 / positioning §3-3 참여 루프 | 없음 | 의견 남기기 진입점 · "반영됐어요" 알림 · 브랜드 페이지의 반영 이력 | Must (루프 ④ 가 차별점) |
| §15-9 교차 브랜드 유입 | `entry_source` 로 부분 추적 | 세션 최초 조회 브랜드를 `sessionStorage` 에 두고 이후 `product_view` 에 `cross_brand: boolean` optional | Should |
| §16 Should 체험단·신상품 피드백 신청 | 없음 | 상품 상세 "체험단 신청" 버튼 → `participate` 성향 신호 | Should |

---

## 9. 구현 순서

1. 프론트 세션 성향 계산기 (§2 식) — 이벤트 발행 훅 옆에 붙인다. 하루.
2. 히어로 배너 + `promo_row` variant 칩. 카피 템플릿 5종 (§4-2). 이틀.
3. optional 속성 발행 (§5). 데이터 파트 4번 답 후. 반나절.
4. 추천 API 연결 (`promo` 규칙 대체). 백엔드 엔드포인트 준비되는 대로.
5. 장기 성향·배너 마트 연결 (§3 장기 겹, §5 마트). 데이터 파트 3·5번 답 후.
6. 참여 루프 이벤트 (§6). 백엔드 상품 수정 이력과 같이.

1·2 는 데이터 파트 답과 무관하게 지금 시작할 수 있다.
