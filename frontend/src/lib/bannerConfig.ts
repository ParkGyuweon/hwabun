import type { BannerType } from '../types/log';

/**
 * 추천 배너 영역 설정. 코드에 박지 않고 여기 한 곳에 둔다.
 *
 * 지금 화면은 **히어로 한 칸만** 그린다 (`service-plan.md` :709, 데이터 파트 회신 2026-09-11).
 * 배너 행 6칸을 요청해서 첫 칸만 쓰고 5칸을 버리던 것을 생성기(239 · `banner_slots 1 · reserved 0 · hero=new_brand`)와
 * 같게 맞췄다. 배너 행이 다시 살아나면 아래 셋을 되돌리고 `reserved` 계약(244)을 다시 연다.
 *
 * `reserved` 칸 수의 근거(AI 회신 2026-09-07, recommendation-io-spec §5-1)는 그때 다시 쓴다:
 *   ~10% → 2칸 · 10~30% → 2~3칸 · 30%+ → 3칸. SSAFY Beauty 8종 / 208 ≈ 4% 라 2칸이었다.
 */
export const BANNER_SLOTS = 1;
export const BANNER_RESERVED = 0;
/** 메인 칸 수 (`items`) */
export const MAIN_SLOTS = 10;

/**
 * 히어로 정책 (AI 회신 2026-09-10 · 추천 서버 `hero=top|new_brand`).
 *
 *   top        items[0]. 예전 계약 그대로
 *   new_brand  신규 상품(지지자 3명 미만 또는 어휘집 밖 브랜드) 중 이 사용자 점수 최고. 전환한 상품은 빼고,
 *              신규가 없으면 top 으로 돌아간다. 실제 적용값은 응답 `hero_policy` 에 찍힌다
 *
 * 전용 칸이 화면에서 사라진 몫을 히어로가 받는 지금 판은 `new_brand` 다. 배너 행이 살아나면 `top` 으로 돌린다.
 * 서버 호출: `GET /api/recommend?…&banner_slots=1&reserved=0&hero=new_brand`.
 */
export const HERO_POLICY: 'top' | 'new_brand' = 'new_brand';

/*
 * `banner_impression` / `banner_click` 전환 기록.
 *
 * 2026-09-11 계약 enum(`event-schema.json`)·수집기 INTENTS(`banner_impression → session` · `banner_click → interest`)·
 * 배너 속성 검증이 dev 에 들어왔고, 2026-09-17 프론트가 실제로 이름을 바꿨다 (ProductListPage heroRef · selectFromBanner).
 * 그 전 기간은 `recommendation_*` 에 배너 property 를 얹어 보냈으므로 `banner_daily` 마트(event_name 으로 거름)는 0행이고
 * 소급되지 않는다. 전에 있던 `BANNER_EVENTS_ENABLED` 스위치는 읽는 곳이 없어 지웠다 — 스위치가 아니라 코드가 바뀐 것이다.
 */

/**
 * 배너·정렬 정책의 배포 버전. 배너 이벤트에 실으면 `banner_daily` 까지 내려가서
 * 정책 배포 전후를 같은 마트 안에서 잘라 볼 수 있다
 * (계약 event-properties-schema.md §3.13, dw-schema.md §400). `banner_daily` 는 이 값을 key 에 갖는다.
 *
 * 배너 뽑는 규칙(`bannerCreative`·`BANNER_RESERVED`·축 선택·**로그에 적는 축**)을 바꾸면 이 값을 올린다.
 * 올리지 않으면 전후 비교가 한 덩어리로 뭉개진다.
 */
export const BANNER_POLICY_VERSION = 'banner-2026-09-15';

/*
 * 판 이력
 *   banner-2026-09-10    히어로 = ranked[0]. 배너 행 6칸을 빼고 히어로만 그리기 시작
 *   banner-2026-09-10.2  히어로 = 신규 브랜드 우선. 전용 칸이 화면에서 사라진 몫을
 *                        히어로가 받는다. 성향 없는 세션은 new_brand(story) 로 말한다.
 *                        → 이 판부터 `banner_type: new_brand` 노출이 크게 는다
 *   banner-2026-09-11    배너 이벤트 스위치 ON · 요청 칸 1/0 (생성기와 일치) ·
 *                        **완성형 배너는 `banner_type=new_brand · banner_value 없음` 으로 기록** (AI 회신 2026-09-10).
 *                        완성형 배너는 브랜드 크리에이티브라 축 문구 배너가 아니고, PDRN 처럼 어휘집에 없는
 *                        토큰은 어떤 규칙으로도 banner_value 가 될 수 없다. 축 값은 조립 배너에만 기록한다.
 *                        → 이 판부터 new_brand 노출이 한 번 더 늘고, 축별 CTR 은 조립 배너만 본다
 *   banner-2026-09-15    추천 서버 `hero_for(axes)` 반영 (AI Jira 304, 프론트 요청 09-14 §1). 히어로 `banner_type` 이
 *                        클라이언트 `axes` 순서(세션 성향)를 먼저 따른다. 이 판부터 서버 경로에서도 성향 축 배너가
 *                        노출되므로 `banner_daily` 의 `trait_source × banner_type` CTR 표본이 처음 쌓인다.
 *                        프론트 코드는 안 바뀌었다 — 서버 판단이 바뀌어 전후를 잘라야 해서 올린다.
 */

/**
 * 기본 히어로 배너 — 아무 단서가 없는 첫 방문(익명 · 세션 성향 없음)에 띄운다.
 *
 * 추천이 고를 근거가 하나도 없을 때 무엇을 보여줄지는 알고리즘이 아니라 **브랜드가
 * 정하는 것**이다. 그 자리를 여기 한 줄로 둬서 화면·추천 코드를 건드리지 않고 바꾼다.
 *
 * 페르소나가 있거나 세션 성향이 잡히면 이 값은 쓰이지 않는다 — 그때부터는 피부 타입이
 * 상품을, 행동이 문구(변형)를 고른다.
 */
export const DEFAULT_HERO: { product_id: string; banner_type: BannerType } = {
  product_id: 'SB000008',
  banner_type: 'concern',
};
