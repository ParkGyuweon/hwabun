/**
 * 행동 로그 이벤트 계약.
 *
 * 프론트가 "어떤 UI에서 어떤 행동이 발생했고 어떤 값을 전달할 수 있는가"를 정의한다.
 * 이 값을 어떤 테이블에 어떻게 저장할지는 데이터 담당 범위이므로 여기서 다루지 않는다.
 */

/** 팀과 스키마를 합의할 때마다 올린다 */
export const SCHEMA_VERSION = '0.2.0-draft';

/** 우선순위 P0. 추천과 마케팅 분석에 반드시 필요한 이벤트 */
export type P0EventName =
  | 'session_start'
  | 'page_view'
  | 'product_impression'
  | 'product_click'
  | 'section_view'
  | 'section_dwell'
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
  | 'variant_select'
  | 'quantity_change'
  | 'review_filter_apply'
  | 'review_expand'
  | 'ingredient_view_mode_change'
  /**
   * 목록 화면의 탐색 조작.
   * 무엇을 눌렀는지보다 **무엇으로 좁혔는지**가 취향을 말해준다.
   * (가격으로 좁히는 사람 / 고민으로 좁히는 사람)
   */
  | 'list_sort_change'
  | 'list_filter_apply'
  /**
   * 아래는 클릭이 아닌 "주목" 신호다.
   * 클릭 이벤트만으로는 구매까지 안 간 방문이 전부 빈 세션으로 남아서,
   * 무엇을 들여다보다 이탈했는지 설명할 수 없다.
   * 설계 근거는 docs/analytics/behavior-log-design.md 참고.
   */
  | 'scroll_pause'
  | 'scroll_backtrack'
  | 'text_selection'
  | 'text_copy'
  | 'hover_dwell'
  | 'rage_click'
  | 'dead_click';

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

/**
 * 그 자리에 **무슨 콘텐츠가 있었는지**.
 *
 * `section_id` 는 화면 구조상의 이름이라 "About the Product 를 봤다" 까지만 말해준다.
 * 그런데 그 블록 안에는 개요·성분·임상 근거·사용법이 같이 들어 있고,
 * 구매 판단에서 각각이 하는 역할이 전혀 다르다.
 * 레이아웃을 바꿔도 "성분을 오래 봤다" 가 유지되도록 콘텐츠 종류를 따로 남긴다.
 */
export type LogContentKind =
  | 'product_image'
  | 'price'
  | 'variant_option'
  | 'cta'
  | 'highlight_badge'
  | 'what_it_is'
  | 'what_else'
  | 'ingredient_list'
  | 'ingredient_callout'
  | 'clinical_claim'
  | 'usage_guide'
  | 'brand_story'
  /** 내 피부 타입·고민과 맞는지 보여주는 자리 */
  | 'persona_match'
  | 'product_meta'
  | 'user_review'
  | 'review_stats'
  | 'review_filter'
  | 'recommendation_card'
  | 'navigation';

/**
 * 이벤트가 **무엇을 뜻하는지**.
 *
 * 이벤트 이름만 넘기면 분석하는 쪽이 매번 "이건 관심인가 확인인가" 를 다시 정해야 한다.
 * 프론트가 발생시킬 때 이미 아는 정보라 로그에 같이 실어 보낸다.
 *
 * 노출 → 관심 → 비교 → 확신 → 전환 순서로 좁혀지는 깔때기이고,
 * friction 은 그 어느 단계에서든 이탈로 새는 구멍이다.
 */
export type IntentClass =
  /** 화면에 떴다 */
  | 'exposure'
  /** 들여다봤다 */
  | 'interest'
  /** 다른 후보와 견줬다 */
  | 'comparison'
  /** 사실을 확인했다 */
  | 'validation'
  /** 살까 말까 쟀다 */
  | 'hesitation'
  /** 사는 쪽으로 움직였다 */
  | 'conversion'
  /** 기대대로 안 됐다 */
  | 'friction'
  /** 세션·페이지 경계 */
  | 'session';

/** 이벤트 → 의미. 로거가 이 표를 보고 envelope 의 intent 를 채운다 */
export const EVENT_INTENT: Record<EventName, IntentClass> = {
  session_start: 'session',
  page_view: 'session',
  exit_summary: 'session',

  product_impression: 'exposure',
  recommendation_impression: 'exposure',
  scroll_depth: 'exposure',

  section_view: 'interest',
  section_dwell: 'interest',
  scroll_pause: 'interest',
  media_view: 'interest',

  scroll_backtrack: 'comparison',
  variant_select: 'comparison',
  product_click: 'comparison',
  recommendation_click: 'comparison',

  accordion_toggle: 'validation',
  ingredient_view_mode_change: 'validation',
  review_expand: 'validation',
  review_filter_apply: 'validation',
  list_filter_apply: 'comparison',
  list_sort_change: 'comparison',
  text_selection: 'validation',
  text_copy: 'validation',

  hover_dwell: 'hesitation',

  wishlist_toggle: 'conversion',
  quantity_change: 'conversion',
  add_to_cart: 'conversion',

  rage_click: 'friction',
  dead_click: 'friction',
};

/**
 * 이벤트 → 선호도 가중치.
 *
 * 근거는 `docs/analytics/marketing-signal-research.md` 7-3 이다.
 * 척도는 AI 추천 설계서를 그대로 따른다 — `page_view`(설계서 `PRODUCT_VIEW`) = 1.0 기준,
 * `wishlist_toggle`(`LIKE`) = 3.0, `add_to_cart`(`CART`) = 4.0.
 *
 * **이 표가 단일 출처다.** 프론트·AI·데이터셋이 각자 숫자를 들고 있으면
 * 조용히 어긋난다. 값을 바꿀 때는 조사 문서와 함께 바꾼다.
 *
 * 값이 확정값이라는 뜻은 아니다. 초기 가설이고 Ablation 으로 검증해야 한다.
 */
export const EVENT_WEIGHT: Record<EventName, number> = {
  // 전환 — 구매 데이터가 없는 환경에서 가장 강한 신호
  add_to_cart: 4.0,
  wishlist_toggle: 3.0,
  quantity_change: 2.0,

  // 비교 — 후보를 좁혔다
  variant_select: 2.0,
  product_click: 1.0,
  recommendation_click: 1.5,

  // 확인 — 능동적으로 사실을 확인했다
  ingredient_view_mode_change: 1.5,
  review_expand: 1.5,
  accordion_toggle: 1.5,
  review_filter_apply: 1.0,
  list_filter_apply: 1.0,
  list_sort_change: 0.5,
  text_selection: 0.5,
  text_copy: 1.0,

  // 관심
  media_view: 1.5,
  section_dwell: 1.0, // 섹션에 따라 SECTION_DWELL_WEIGHT 로 다시 조정한다
  scroll_pause: 0.3,
  hover_dwell: 0.3,
  section_view: 0.3,

  // 기준선
  page_view: 1.0,

  /**
   * 노출은 사용자 의지가 아니다. 가중 0 으로 두고 **분모**로만 쓴다.
   * 이 값이 있어야 클릭률을 계산할 수 있다.
   */
  product_impression: 0,
  recommendation_impression: 0,
  scroll_depth: 0, // 도달 깊이는 scrollDepthWeight() 로 따로 계산한다

  // 메타. 선호도가 아니다
  session_start: 0,
  exit_summary: 0,

  /**
   * 감점. **`v_u` 분모에 넣지 않는다.**
   * 음수를 분모에 넣으면 분모가 0 에 가까워질 수 있어서,
   * 긍정 벡터와 부정 벡터를 따로 만들고 최종 점수에서 뺀다.
   */
  rage_click: -2.0,
  dead_click: -1.5,
  scroll_backtrack: -1.0,
};

/** 감점 축으로 보내는 이벤트. 긍정 벡터와 분리해서 누적한다 */
export const NEGATIVE_EVENTS: ReadonlySet<EventName> = new Set<EventName>([
  'rage_click',
  'dead_click',
  'scroll_backtrack',
]);

/**
 * 섹션별 체류 가중치.
 *
 * 같은 1초도 어느 섹션인지에 따라 의미가 다르다.
 * `similar_products` 는 값이 낮다 — 유사 상품을 오래 보는 것은 이 상품에 대한
 * 관심이 아니라 **다른 것을 찾고 있다는 신호**에 가깝다.
 */
export const SECTION_DWELL_WEIGHT: Record<LogSection, number> = {
  ingredients: 1.5,
  reviews: 1.5,
  about_product: 1.0,
  how_to_use: 1.0,
  product_hero: 0.5,
  highlights: 0.5,
  similar_products: 0.5,
};

/**
 * 도달 깊이 가중치.
 *
 * **누적 합산하면 안 된다.** 끝까지 내려간 사용자가 25·50·75·100 을 모두 더해
 * 과대 점수를 받는다. 상품별로 **도달한 최대 깊이 1건만** 반영한다.
 *
 * 프론트는 10% 단위로 로그를 남기고(긴 페이지에서 25% 한 칸이 2000px 이라 성겼다,
 * `behavior-log-design.md`), 데이터셋 쪽은 25% 단위로 생성한다.
 * 그래서 **조회를 25% 버킷으로 내림 처리**해서 양쪽이 같은 값을 얻게 한다.
 * 어느 쪽도 자기 단위를 바꿀 필요가 없다.
 */
export function scrollDepthWeight(depthPercent: number): number {
  if (depthPercent >= 100) return 1.5;
  if (depthPercent >= 75) return 1.0;
  if (depthPercent >= 50) return 0.5;
  if (depthPercent >= 25) return 0.2;
  return 0;
}

export type PageType = 'product_detail' | 'product_list' | 'cart';

/** 실제 사용자 로그와 부하 테스트용 가상 로그를 반드시 분리한다 */
export type ActorType = 'user' | 'synthetic';

export interface LogEnvelope {
  schema_version: string;
  event_id: string;
  event_name: EventName;
  /** 이벤트의 의미. EVENT_INTENT 에서 자동으로 채운다 */
  intent: IntentClass;
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
