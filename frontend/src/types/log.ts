/**
 * 행동 로그 이벤트 계약.
 *
 * 프론트가 "어떤 UI에서 어떤 행동이 발생했고 어떤 값을 전달할 수 있는가"를 정의한다.
 * 이 값을 어떤 테이블에 어떻게 저장할지는 데이터 담당 범위이므로 여기서 다루지 않는다.
 */

/** 팀과 스키마를 합의할 때마다 올린다 */
export const SCHEMA_VERSION = '0.1.0-draft';

/** 우선순위 P0. 추천과 마케팅 분석에 반드시 필요한 이벤트 */
export type P0EventName =
  | 'session_start'
  | 'page_view'
  | 'product_impression'
  | 'product_click'
  | 'section_view'
  | 'accordion_toggle'
  | 'recommendation_impression'
  | 'recommendation_click'
  | 'wishlist_toggle'
  | 'add_to_cart'
  | 'exit_summary';

/** 우선순위 P1. 관심 강도를 보조하는 이벤트 */
export type P1EventName =
  | 'scroll_depth'
  | 'media_view'
  | 'quantity_change'
  | 'review_filter_apply'
  | 'review_expand'
  | 'ingredient_view_mode_change';

export type EventName = P0EventName | P1EventName;

/** 상세 페이지 안의 의미 단위 구역. 픽셀 위치가 아니라 이 값으로 로그를 남긴다 */
export type LogSection =
  | 'product_hero'
  | 'highlights'
  | 'about_product'
  | 'ingredients'
  | 'how_to_use'
  | 'similar_products'
  | 'reviews';

export type PageType = 'product_detail' | 'product_list' | 'cart';

/** 실제 사용자 로그와 부하 테스트용 가상 로그를 반드시 분리한다 */
export type ActorType = 'user' | 'synthetic';

export interface LogEnvelope {
  schema_version: string;
  event_id: string;
  event_name: EventName;
  /** 클라이언트 발생 시각. 서버 수신 시각과는 별개로 관리한다 */
  occurred_at: string;

  persona_id: string | null;
  session_id: string;
  page_view_id: string;
  /** 세션 안에서의 발생 순서. 도착 순서가 뒤바뀌어도 복원할 수 있게 한다 */
  sequence_no: number;

  page_type: PageType;
  product_id: string | null;
  actor_type: ActorType;
  environment: string;

  properties: Record<string, unknown>;
}
