/**
 * 행동 로그 이벤트 계약.
 *
 * 프론트가 "어떤 UI에서 어떤 행동이 발생했고 어떤 값을 전달할 수 있는가"를 정의한다.
 * 이 값을 어떤 테이블에 어떻게 저장할지는 데이터 담당 범위이므로 여기서 다루지 않는다.
 */

/** 팀과 스키마를 합의할 때마다 올린다 */
/**
 * 0.3.0-draft 부터 봉투에 `tenant_id` 가 필수다 (contracts/event-schema.json).
 * 계약은 두 버전을 함께 받으므로 다른 모듈이 아직 0.2.0-draft 여도 수집은 깨지지 않는다.
 */
export const SCHEMA_VERSION = '0.3.0-draft';

/** 우선순위 P0. 추천과 마케팅 분석에 반드시 필요한 이벤트 */
export type P0EventName =
  | 'session_start'
  | 'page_view'
  /**
   * 상품 상세 조회.  와 별도로 둔다.
   *
   * page_view 는 화면 이동과 체류를 표현하고, product_view 는 **상품 단위 조회 수**와
   * Funnel 의 기준이다. page_view 만 쓰면 상품 조회 집계가 화면 구조에 종속돼서,
   * 나중에 상세를 모달·탭 같은 다른 형태로 바꾸면 과거 수치와 이어지지 않는다.
   *  가 반드시 실린다.
   */
  | 'product_view'
  | 'product_impression'
  /**
   * 화면 이동 클릭. 상품을 지목하지 않는다.
   * 홈으로 가기처럼 상품과 무관한 이동을 product_click 으로 남기면
   * product_id 가 null 인 클릭이 섞여 상품별 클릭 수와 노출 대비 클릭률이 어긋난다.
   */
  | 'navigation_click'
  | 'product_click'
  | 'section_view'
  | 'section_dwell'
  | 'accordion_toggle'
  | 'recommendation_impression'
  | 'recommendation_click'
  /** 개인화 배너의 유효 노출. CTR 분모 전용 */
  | 'banner_impression'
  /** 개인화 배너 클릭 */
  | 'banner_click'
  | 'wishlist_toggle'
  | 'add_to_cart'
  /** 장바구니 화면 진입. GA4 표준 퍼널 단계 */
  | 'view_cart'
  /**
   * 주문 3종. 계약 §6 에서 활성으로 옮겨졌다 (2026-09-07).
   * 매출·정산의 정본은 백엔드 PAID 주문이고, 이 이벤트는 **전환 분석에만** 쓴다.
   */
  | 'begin_checkout'
  | 'purchase'
  /**
   * 구매 직후 한 번 뜨는 클릭 설문. 주문당 1회. 건너뛰면 `skipped=true` + 빈 `reasons`.
   * 상품 선호가 아니라 **이유 선언**이라 가중치는 0 이고, `reasons` 값 자체를 AI 가 따로 쓴다.
   */
  | 'purchase_reason_select'
  /**
   * 추천 배너. 유료 광고가 아니라 추천 결과를 강조해 보여주는 영역이다 (기획 §15-10).
   * 노출은 선호 신호가 아니라 클릭률의 **분모**이고, 클릭 이후 행동만 추천에 반영한다.
   * `banner_skip` 은 만들지 않는다 — 마트에서 "노출 − 클릭" 으로 계산한다.
   */
  | 'banner_impression'
  | 'banner_click'
  | 'exit_summary';

/** 우선순위 P1. 관심 강도를 보조하는 이벤트 */
export type P1EventName =
  | 'scroll_depth'
  /** 노출 확정 카드가 화면을 벗어날 때의 구간 유지 시간. 노출 기준 재집계용 */
  | 'impression_dwell'
  /** 추천 목록이 다시 그려질 때의 정렬 결과. 순위 변동 추적용 */
  | 'recommendation_snapshot'
  | 'media_view'
  /** 목록에서 상세로 가지 않고 요약 창을 연 것. 세포라 Quicklook */
  | 'quick_look'
  /** 요약 창을 닫음. 체류·닫은 방법을 담는 요약 이벤트 */
  | 'quick_look_close'
  /** 담았던 상품을 뺌. 조사 7-2: 상품 특정 부정 신호 중 가장 명확하다 */
  | 'remove_from_cart'
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
  | 'sort_change'
  | 'filter_change'
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

/**
 * 화면 안의 의미 단위 구역. 픽셀 위치가 아니라 이 값으로 로그를 남긴다.
 *
 * **목록과 상세의 구역 이름은 반드시 다르게 둔다.**
 * 같은 이름을 쓰면 `section_dwell` 이 어느 화면에서 나온 것인지 구분할 수 없다.
 */
export type LogSection =
  // 목록 화면
  | 'promo_row'
  | 'list_controls'
  | 'product_grid'
  // 상세 화면
  | 'product_hero'
  | 'highlights'
  | 'about_product'
  | 'ingredients'
  | 'how_to_use'
  | 'similar_products'
  | 'reviews'
  /** 장바구니 화면 */
  | 'cart_items';

/**
 * 그 자리에 **무슨 콘텐츠가 있었는지**.
 *
 * `section_id` 는 화면 구조상의 이름이라 "About the Product 를 봤다" 까지만 말해준다.
 * 그런데 그 블록 안에는 개요·성분·임상 근거·사용법이 같이 들어 있고,
 * 구매 판단에서 각각이 하는 역할이 전혀 다르다.
 * 레이아웃을 바꿔도 "성분을 오래 봤다" 가 유지되도록 콘텐츠 종류를 따로 남긴다.
 */
/**
 * `filter_change.filter_kind` — 무엇으로 좁혔는가.
 *
 * 무엇을 눌렀는지보다 **무엇으로 좁혔는지**가 취향을 말해준다.
 * 가격으로 좁히는 사람과 고민으로 좁히는 사람은 다른 고객이다.
 *
 * 이 목록이 프론트의 단일 출처다. 전에는 `applyFilter(kind: string)` 이라
 * 호출부를 하나씩 세어야만 값 범위를 알 수 있었고, 계약의 enum 과 조용히
 * 어긋날 수 있었다. 여기에 없는 값은 이제 컴파일이 막는다.
 *
 * 계약(`contracts/event-properties-schema.md`)에 `ingredient_exclude` 와
 * `skin_type` 도 함께 등재하기로 했지만 그 필터는 아직 화면에 없다.
 * 화면이 생길 때 여기에 더한다 — 안 쓰는 값을 미리 넣으면 이 표가
 * "무엇을 내보내는가" 가 아니라 "무엇을 내보낼 수도 있는가" 가 된다.
 */
export type FilterKind =
  /** 카테고리 탭과 헤더 메뉴. 값은 'all' 또는 중분류 이름 */
  | 'category'
  /** 고민 셀렉트. 값은 'all' 또는 skincare_concerns 의 값 */
  | 'concern'
  /** 가격대 버튼. 값은 all · under20 · 20to50 · 50to100 · over100 */
  | 'price';

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
  /** 목록·기획전의 상품 카드. 추천 카드와 구분해야 추천 성과를 따로 볼 수 있다 */
  | 'product_card'
  /** 장바구니 행. ref = product_id */
  | 'cart_item'
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
  // 상품을 열어본 것 자체가 관심의 시작이다
  product_view: 'interest',
  exit_summary: 'session',

  product_impression: 'exposure',
  recommendation_impression: 'exposure',
  banner_impression: 'session',
  scroll_depth: 'exposure',
  impression_dwell: 'exposure',
  recommendation_snapshot: 'exposure',

  section_view: 'interest',
  section_dwell: 'interest',
  scroll_pause: 'interest',
  media_view: 'interest',
  quick_look: 'interest',
  quick_look_close: 'interest',

  scroll_backtrack: 'comparison',
  variant_select: 'comparison',
  navigation_click: 'session',
  product_click: 'comparison',
  recommendation_click: 'comparison',
  banner_click: 'interest',

  accordion_toggle: 'validation',
  ingredient_view_mode_change: 'validation',
  review_expand: 'validation',
  review_filter_apply: 'validation',
  filter_change: 'comparison',
  sort_change: 'comparison',
  text_selection: 'validation',
  text_copy: 'validation',

  hover_dwell: 'hesitation',

  wishlist_toggle: 'conversion',
  quantity_change: 'conversion',
  add_to_cart: 'conversion',
  view_cart: 'conversion',
  begin_checkout: 'conversion',
  purchase: 'conversion',
  // 왜 샀는지를 말하는 것이지 사는 쪽으로 움직인 것이 아니다
  purchase_reason_select: 'validation',

  // 담았다 뺀 것은 재고(再考)다. 좌절(friction)이 아니라 망설임 축에 둔다
  remove_from_cart: 'hesitation',

  rage_click: 'friction',
  dead_click: 'friction',
};

/**
 * 이벤트 → 선호도 가중치.
 *
 * 근거는 `docs/analytics/marketing-signal-research.md` 7-3 이다.
 * 척도는 AI 추천 설계서를 그대로 따른다 — `page_view`(설계서 `PRODUCT_VIEW`) = 1.0 기준,
 * `wishlist_toggle`(`LIKE`) = 3.0, `add_to_cart`(`CART`) = 3.0.
 *
 * **이 표가 단일 출처다.** 프론트·AI·데이터셋이 각자 숫자를 들고 있으면
 * 조용히 어긋난다. 값을 바꿀 때는 조사 문서와 함께 바꾼다.
 *
 * 값이 확정값이라는 뜻은 아니다. 초기 가설이고 Ablation 으로 검증해야 한다.
 */
export const EVENT_WEIGHT: Record<EventName, number> = {
  /**
   * 전환. 구매가 들어오면서 담기는 **구매의 약한 대리**로 내려간다 (2026-09-07, AI 제안).
   *
   * 담기→구매 전환이 100% 가 아니므로 "담고 안 산 사람" 과 "산 사람" 을 같은 무게로
   * 두면 안 된다. 지켜야 하는 것은 절대값이 아니라 **purchase : add_to_cart ≥ 2 : 1**.
   * 아직 측정값이 아니다 — 첫 구매 로그 1,000건쯤 쌓이면 실제 전환율로 재조정한다.
   */
  purchase: 8.0,
  // 결제 화면까지 갔다. 담기보다 세지만 완결은 아니다. 전환 정의(CONVERT)에는 넣지 않는다
  begin_checkout: 5.0,
  add_to_cart: 3.0,
  // 장바구니를 열어본 것 자체가 구매 검토 신호다
  view_cart: 1.0,
  wishlist_toggle: 3.0,
  quantity_change: 2.0,

  // 비교 — 후보를 좁혔다
  variant_select: 2.0,
  // 화면 이동이라 상품 선호가 아니다
  navigation_click: 0,
  product_click: 1.0,
  recommendation_click: 1.5,
  banner_click: 1.5,

  // 확인 — 능동적으로 사실을 확인했다
  ingredient_view_mode_change: 1.5,
  review_expand: 1.5,
  accordion_toggle: 1.5,
  review_filter_apply: 1.0,
  filter_change: 1.0,
  sort_change: 0.5,
  text_selection: 0.5,
  text_copy: 1.0,

  // 관심
  media_view: 1.5,
  // 요약 창을 여는 것은 카드 클릭과 같은 무게의 능동 행동이다
  quick_look: 1.5,
  // 닫힘은 exit_summary 처럼 요약 전달용이다. 열림(1.5)에 이미 가중했다
  quick_look_close: 0,
  section_dwell: 1.0, // 섹션에 따라 SECTION_DWELL_WEIGHT 로 다시 조정한다
  scroll_pause: 0.3,
  hover_dwell: 0.3,
  /**
   * 섹션이 화면에 들어온 것 자체는 0 이다.
   *
   * 같은 섹션에서 section_dwell 이 함께 발생하고 그쪽이 섹션별 가중을 갖는다.
   * 둘 다 양수면 같은 행동을 두 번 센다. 여기는 "보여줬다" 는 분모로만 쓰고,
   * 얼마나 봤는지는 section_dwell 이 담당한다.
   */
  section_view: 0,

  /**
   * 화면 이동은 0 이다.
   *
   * 상세에서 page_view 와 product_view 가 **둘 다 product_id 를 싣는다.**
   * 집계는 product_id 가 있고 가중이 양수인 이벤트를 전부 그 상품에 귀속시키므로,
   * 양쪽 다 1.0 이면 상세 진입 한 번을 두 번 센다.
   * 페르소나 300명 실측에서 두 이벤트의 귀속 가중 합이 1,378 로 정확히 같았다.
   *
   * 상품 단위 조회는 product_view 가 담당한다. 여기는 목록·장바구니에서도
   * 발생하므로 상품 선호의 기준선으로 쓸 수 없다. section_view 를 0 으로 둔 것과
   * 같은 이유다 — 한 행동을 두 이벤트가 세면 한쪽을 0 으로 둔다.
   */
  page_view: 0,
  /** 상품 단위 조회. **선호도 척도의 기준선**이다 */
  product_view: 1.0,

  /**
   * 노출은 사용자 의지가 아니다. 가중 0 으로 두고 **분모**로만 쓴다.
   * 이 값이 있어야 클릭률을 계산할 수 있다.
   */
  product_impression: 0,
  recommendation_impression: 0,
  banner_impression: 0,
  impression_dwell: 0,
  recommendation_snapshot: 0,
  scroll_depth: 0, // 도달 깊이는 scrollDepthWeight() 로 따로 계산한다

  /**
   * 이유 선언은 상품 선호가 아니다. 벡터에 넣으면 purchase 와 이중 계산이 된다.
   * `reasons` 값은 AI 가 선언 이유 vs 행동 추론 대조에 따로 쓴다.
   */
  purchase_reason_select: 0,


  // 메타. 선호도가 아니다
  session_start: 0,
  exit_summary: 0,

  /**
   * 감점. **`v_u` 분모에 넣지 않는다.**
   * 음수를 분모에 넣으면 분모가 0 에 가까워질 수 있어서,
   * 긍정 벡터와 부정 벡터를 따로 만들고 최종 점수에서 뺀다.
   */
  /**
   * 담았다 뺀 상품. UI 좌절 3종과 달리 **상품을 특정하는** 부정 신호라
   * 조사(7-2)가 가장 명확한 감점으로 꼽았다. add_to_cart 3.0 의 과대평가 검증에도 쓴다.
   */
  remove_from_cart: -2.0,
  rage_click: -2.0,
  dead_click: -1.5,
  scroll_backtrack: -1.0,
};

/**
 * 감점 축으로 보내는 이벤트. 긍정 벡터와 분리해서 누적한다.
 *
 * ## 집계 규칙 B — 전환 안 한 상품은 v_u⁺ 가 아니라 v_u⁻ 다
 *
 * - 장바구니·찜을 누른 상품          → v_u⁺
 * - 눌러봤지만 아무것도 안 한 상품    → v_u⁻ (보고 나서 안 담았다는 뜻이다)
 * - 목록에 뜨기만 한 상품            → 어느 쪽에도 안 넣는다 (CTR 분모로만)
 *
 * "보긴 봤다" 는 좋아한다는 뜻이 아니다. 규칙 A·B 를 함께 적용하면
 * Recall@10 이 5.9% → 12.6% 로 오른다 (3,000명 부트스트랩, AI 검증).
 */
export const NEGATIVE_EVENTS: ReadonlySet<EventName> = new Set<EventName>([
  'remove_from_cart',
  'rage_click',
  'dead_click',
  'scroll_backtrack',
]);

/**
 * 섹션별 체류 가중치.
 *
 * ## 집계 규칙 A — 선호도 가중에는 상품 × 섹션당 1건만 반영한다
 *
 * `section_dwell` 은 체크포인트·이탈 때마다 나가므로 스크롤을 오르내리면
 * 같은 섹션 체류가 계속 쌓인다. 그대로 합산하면 오래 스크롤한 것이
 * `add_to_cart`(4.0)보다 훨씬 강한 신호가 된다 — 실측에서 담은 상품 점수의
 * 92% 가 체류였고 담기 자체는 8% 였다.
 *
 * 이벤트는 전부 전송한다 (총 체류 시간 분석에 필요하다).
 * **1건만 세는 것은 선호도 벡터를 만들 때다.** scrollDepthWeight 의
 * "최대 도달 1건만" 과 같은 규칙이다.
 *
 * 같은 1초도 어느 섹션인지에 따라 의미가 다르다.
 * `similar_products` 는 값이 낮다 — 유사 상품을 오래 보는 것은 이 상품에 대한
 * 관심이 아니라 **다른 것을 찾고 있다는 신호**에 가깝다.
 */
export const SECTION_DWELL_WEIGHT: Record<LogSection, number> = {
  /**
   * 목록 화면.
   * 그리드 체류는 "고르는 중" 이라 상품 하나에 귀속시킬 수 없다.
   * 그래서 상품 선호도 가중이 아니라 **탐색 노력의 크기**로만 쓴다.
   */
  product_grid: 0.5,
  promo_row: 0.5,
  list_controls: 0.3,

  // 장바구니 체류는 구매 검토 시간이다
  cart_items: 1.0,

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

/**
 * 추천 배너 property. 계약 `recommendation-io-spec.md` §5-1.
 *
 * `banner_value` 는 **어휘집 문자열 그대로** 보낸다 (`contracts/product-feature-vocab.json`).
 * 화면의 한국어 라벨(`product-form-labels-ko.json` 의 `ko`)을 보내면 한 글자 차이로
 * 그 축이 통째로 매칭 실패하고 화면에는 아무 표시도 나지 않는다.
 */
export type BannerType =
  | 'concern'
  | 'ingredient'
  | 'clean'
  | 'price_bin'
  | 'category'
  | 'segment'
  /** 신규·저노출 브랜드 전용 칸. 축이 아니라 자리라 `banner_value` 는 null */
  | 'new_brand';

/**
 * 이 배너의 축을 어디서 골랐나. 없으면 "성향 추정이 맞았는지" 를 나중에 가릴 수 없다.
 * - session    세션 행동으로 추정한 성향
 * - profile    장기 성향(마트)
 * - coldstart  성향 없음 → AI 기본값(concern·segment)
 * - explore    성향이 있어도 20% 는 다른 축을 준다. A/B 표본
 */
export type TraitSource = 'session' | 'profile' | 'coldstart' | 'explore';

export interface BannerEventProperties {
  banner_type: BannerType;
  banner_value: string | null;
  /** 배너 영역에서 몇 번째 칸인가 (히어로는 0) */
  banner_slot: number;
  product_id: string;
  trait_source: TraitSource;
}

/** 계약 §3.9. 10개로 고정 — 늘리면 응답이 흩어져 행동 추론과 대조할 표본이 준다 */
export type PurchaseReason =
  | 'ingredient'
  | 'skin_fit'
  | 'reviews'
  | 'review_same_skin'
  | 'price'
  | 'brand_trust'
  | 'texture_finish'
  | 'clean_claim'
  | 'recommendation'
  | 'restock';

/** 계약 §5 `items[]`. 단가는 전환 분석용이고 매출의 정본이 아니다 */
export interface OrderItem {
  product_id: string;
  quantity: number;
  unit_price: number;
  sku_id?: string;
}

export interface BeginCheckoutProperties {
  items: OrderItem[];
  cart_value?: number;
  currency?: string;
}

export interface PurchaseProperties {
  order_id: string;
  items: OrderItem[];
  order_value?: number;
  currency?: string;
}

/** 주문당 1회. 건너뛰면 `skipped: true` 와 빈 `reasons` 를 **반드시** 보낸다 — 유실과 구분해야 응답률을 센다 */
export interface PurchaseReasonSelectProperties {
  order_id: string;
  /** 1~2개. `skipped` 면 [] */
  reasons: PurchaseReason[];
  primary_reason?: PurchaseReason;
  /** 자유 입력 원문은 보내지 않는다. 분류값만 */
  free_text_kind?: string;
  skipped?: boolean;
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

  /**
   * 이 이벤트가 일어난 쇼핑몰이 누구 것인가. 격리·파티션 키 (계약 §1.1).
   * 상품 브랜드(`brand_id`)와 다르다 — 그건 상품이 없는 이벤트에서 정해지지 않아
   * 봉투에 싣지 않고 처리 단계에서 `product_id` 로 파생한다.
   */
  tenant_id: string;
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
