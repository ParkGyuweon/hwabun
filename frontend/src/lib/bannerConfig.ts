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
 * 막고 있는 것이 바뀌었다 (데이터 파트 회신 2026-09-10).
 *   계약 enum  — **등록됨.** `contracts/event-schema.json` event_name enum 41종에 둘 다 있다 (198)
 *   수집기      — 아직. EventContractValidator 에 없어 지금 켜면 unregistered_event 400 이 난다
 *
 * 그래서 스위치는 계속 false 다. 수집기 등록 회신이 오면 true 한 줄로 끝난다.
 * 그동안은 `recommendation_impression` / `recommendation_click` 에 배너 property 를
 * 얹어 보낸다 — properties 는 열린 객체라 계약에 무해하다.
 *
 * 켜기 전까지의 손해는 알고 있다. `banner_daily` 마트가 `event_name` 으로 거르므로
 * 그 기간은 0행이고 나중에 켜도 소급되지 않는다 (축별 CTR·탐색군 비중 포함).
 * `algorithm` 에 `/banner` 접미사를 붙여 둔 덕에 추천 CTR 기준선은 오염되지 않는다.
 */
export const BANNER_EVENTS_ENABLED = false;

/**
 * 배너·정렬 정책의 배포 버전. 배너 이벤트에 실으면 `banner_daily` 까지 내려가서
 * 정책 배포 전후를 같은 마트 안에서 잘라 볼 수 있다
 * (계약 event-properties-schema.md §3.13, dw-schema.md §400).
 *
 * 배너 뽑는 규칙(`bannerCreative`·`BANNER_RESERVED`·축 선택)을 바꾸면 이 값을 올린다.
 * 올리지 않으면 전후 비교가 한 덩어리로 뭉개진다.
 */
export const BANNER_POLICY_VERSION = 'banner-2026-09-10';
