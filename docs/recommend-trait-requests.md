# 행동 기반 배너 요청 목록 (프론트 → AI · 데이터 · 백엔드)

작성 2026-09-14 · 프론트 기준 브랜치 `S15P21A306-fe-member-recommend-identity` (커밋 `90db54d` · `2492e06`)

배너 축(가격·성분·리뷰·고민·참여)을 사용자 행동으로 고르는 설계(`docs/dashboard/personalized-banner-plan.md`)를
2026-09-14 에 전 구간 대조했습니다. **수집·계약·마트는 맞춰져 있는데, 성향이 화면에 닿는 마지막 두 연결이
비어 있습니다.** 프론트 몫(계약 속성 두 개 누락)은 위 커밋으로 붙였고, 아래 두 건은 다른 파트 코드가 바뀌어야 합니다.

## 0. 지금 상태 (대조 결과)

| 구간 | 상태 | 근거 |
|---|---|---|
| 성향 규칙 | 일치 | `contracts/user-trait-weights.json` (confirmed) = `frontend/src/lib/trait.ts` `traitContribution` |
| 수집기 | 통과 | 성향 이벤트 11종 전부 `EventContractValidator` INTENTS 등록 |
| 식별자 | 정상 | 회원은 JWT → `account_id`, 시뮬레이터는 `persona_id` → 정제 단계 `user_id`·`identity_scope` |
| 장기 마트 | 산출됨 | `build_marts_job._user_trait_daily` 가 계약 JSON 을 그대로 읽어 30일 창 점수·`is_primary_trait` |
| 프론트 속성 | **09-14 수정** | `variant_select.variant_kind` · `text_selection/text_copy.selection_kind` 가 안 실리고 있었다 (`2492e06`) |
| 세션 성향 → 히어로 | **끊김** | 1번. 서버 응답이 오면 클라이언트 `axes` 가 히어로에 반영되지 않는다 |
| 장기 성향 → 프론트 | **끊김** | 2번. `user_trait_daily` 를 읽는 경로가 없다 |

즉 지금은 추천 서버가 살아 있을수록 행동 기반 배너가 **안** 보이고, 서버가 죽어 프론트 목으로 떨어졌을 때만
성향 축이 히어로 변형을 고릅니다 (`recommendMock.ts` :277).

---

## 1. [AI] 히어로 `banner_type` 이 클라이언트 `axes` 순서를 따르게 (한 함수)

`batch/serving/banners.py` `hero_for(product_id, traits)` :128

지금은 `traits` (시드 최빈값 · 프로필 세그먼트)를 **고정 순서** `concern → ingredient → clean → category → price_bin`
으로 훑어 첫 번째로 맞는 축을 씁니다. 프론트가 보낸 `axes`(예: `price_bin,concern,segment,ingredient`)는
`plan()` 의 배너 행(`banners[]`)에만 쓰이는데, 화면은 09-10 기획 검토 이후 **히어로 한 장만** 그리고 배너 행은
버립니다 (`bannerConfig.ts` `BANNER_SLOTS = 1`). 그래서 이 세션에서 가격만 본 사용자도 히어로는 `concern` 문구입니다.

**요청** — `hero_for` 에 `axes` 를 넘겨 그 순서로 먼저 찾고, 없을 때만 지금의 고정 순서로 떨어지게 해 주세요.

```python
def hero_for(self, product_id, traits, axes=()):
    ax = self.attrs_of[self.index[product_id]]
    order = [a for a in axes if a in ("concern", "ingredient", "clean", "category", "price_bin", "segment")]
    order += [a for a in ("concern", "ingredient", "clean", "category", "price_bin", "segment") if a not in order]
    for a in order:
        t = traits.get(a)
        if not t:
            continue
        if a == "segment":
            if product_id in self.members["segment"].get(t[0], ()):
                return {..., "banner_type": "segment", "banner_value": t[0], "trait_source": t[1]}
        elif t[0] in ax.get(a, []):
            return {..., "banner_type": a, "banner_value": t[0], "trait_source": t[1]}
    # 이하 기존 폴백(상품 자신의 값) 그대로
```

호출부 `recommend_server.py` :462·:469 는 `self.planner.hero_for(pid, traits, axes)` 로 한 단어씩.

- `traits` 에 그 축의 값이 없으면(예: 시드에 price_bin 이 없음) 지금처럼 다음 축으로 넘어갑니다. **응답 모양은 안 바뀝니다.**
- 검증은 `banner_daily` 의 `trait_source × banner_type` 별 CTR 로 합니다. 이게 붙어야 "가격 성향 판정 세션에서 가격
  배너 CTR 이 높은가" 표본이 처음 쌓입니다 (계획서 §10-4). 프론트는 반영 시 `BANNER_POLICY_VERSION` 을 올립니다.
- 프론트 대안(서버 히어로 상품은 두고 `banner_type` 만 프론트 성향으로 덮어쓰기)은 응답과 로그의 축이 달라져
  **권하지 않습니다.** 데이터 파트가 그쪽을 원하면 알려 주세요.

## 2. [AI 또는 백엔드] 장기 성향 `user_trait_daily` 를 회원별로 읽는 경로

프론트 `trait.ts` 는 `setTraitProfile({ longTerm })` 로 마트 점수를 세션 점수에 ×0.5 로 섞도록 만들어져 있는데
(계약 `long_term_blend_weight`), **부르는 곳이 없습니다** — 읽을 API 가 없어서입니다. 그래서 지난 방문에서 가격만
보던 회원도 새 세션은 콜드스타트(concern·segment)로 시작합니다.

두 안 중 **2-A 를 권합니다.** 호출이 늘지 않습니다.

### 2-A. [AI] 추천 응답에 `long_term_trait` 한 칸 (권장)

`GET /api/recommend` 응답 최상위에:

```json
"long_term_trait": { "price": 4.5, "ingredient": 1.0, "review": 0.0, "concern": 2.5, "participate": 0.0,
                     "primary": "price", "window_end_date": "2026-09-13", "trait_policy_version": "user-trait-v2" }
```

- 소스: `data/marts/user_trait_daily` 최신 `trait_date_kst` 의 `user_id = persona_id` 행 (identity_scope 는 회원 `account`,
  시뮬레이터 `persona`). 없으면 `null`.
- 카탈로그 동기화처럼 마트 파일을 주기적으로 읽어 메모리에 두면 됩니다 (5종 × 사용자 수 · 작음).
- 프론트는 응답을 받으면 `setTraitProfile({ longTerm })` 한 줄로 붙습니다.

### 2-B. [백엔드] `GET /api/members/me/trait`

shop_backend 가 `dw.user_trait_daily` (대시보드 마트 projection, 계약 `dashboard-mart-api-spec.md` §5) 를 읽어
같은 JSON 을 돌려주는 안. MEMBER 토큰. projection 이 끝나야 하고 호출이 하나 늘어서 2-A 다음입니다.

## 3. [데이터] 확인 부탁 (변경 없음)

- `variant_kind` 는 원천 `variation_type` 이 수집본·백엔드 어디에도 없어 **라벨의 용량 단위로 판정**합니다
  (`ml·oz·g`, `Mini/Standard/Jumbo/Refill` → `size`, 그 외 `other`, `shade` 는 안 붙임). 계약 §3.7 문구를
  "원천 필드가 없을 때는 라벨 판정" 으로 한 줄 보태 주시면 마트 쪽 해석이 어긋나지 않습니다.
- `selection_kind` 가 실리기 시작하면 성향 표의 `require_absent: selection_kind` 폴백 규칙은 09-14 이전 로그에만
  걸립니다. 의도한 동작이라 바꿀 것은 없고, 알려만 드립니다.

---

## 참고 — 프론트가 이번에 붙인 것

| 커밋 | 무엇 |
|---|---|
| `90db54d` | 피부 프로필 없는 회원도 추천을 회원 id 로 (스위처 PA00001 폴백 제거, 런북 §5 요청) |
| `2492e06` | `variant_select.variant_kind` · `text_selection/text_copy.selection_kind` 전송 |
