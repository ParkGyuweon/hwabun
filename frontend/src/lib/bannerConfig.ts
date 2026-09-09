/**
 * 추천 배너 영역 설정. 코드에 박지 않고 여기 한 곳에 둔다.
 *
 * `reserved` 는 신규 브랜드 비율에 따라 바뀐다 (AI 회신 2026-09-07, recommendation-io-spec §5-1):
 *   ~10%  → 2칸   3칸은 전체를 1.3%p 더 깎는다
 *   10~30% → 2~3칸  이 구간부터 전용 칸이 공짜를 넘어 이득
 *   30%+  → 3칸
 * 지금은 SSAFY Beauty 8종 / 208 ≈ 4% 라 2칸이다. 브랜드가 늘면 이 값만 바꾼다.
 */
export const BANNER_SLOTS = 6;
export const BANNER_RESERVED = 2;
/** 메인 칸 수 (`items`) */
export const MAIN_SLOTS = 10;

/**
 * `banner_impression` / `banner_click` 발행 스위치.
 *
 * 두 이벤트는 `log.ts` 에는 있지만 `contracts/event-schema.json` enum 에 아직 없다.
 * 등록 전에 보내면 검증기가 격리한다. 그동안은 `recommendation_impression` /
 * `recommendation_click` 에 배너 property 를 얹어 보낸다 — properties 는 열린 객체라
 * 계약에 무해하고, 마트가 `banner_type` 으로 걸러 쓸 수 있다.
 */
export const BANNER_EVENTS_ENABLED = false;
