/**
 * 브랜드 대시보드 마트 조회 API 클라이언트.
 *
 * 계약: contracts/dashboard-mart-api-spec.md (초안 0.1). 서버는 shop_backend `/api/seller/dashboard/*`,
 * SELLER 토큰 + brandId 소유 확인. 응답 필드 이름은 마트 컬럼(snake_case) 그대로다 (계약 §1-3).
 *
 * 여기서는 **받아서 타입만 붙인다.** 화면 모양으로 바꾸는 일은 martAdapter.ts, 모의로 물러나는 판단은
 * useBehavior.tsx 가 한다. 실패는 전부 null. 어떤 상태 코드든(401·403·503·네트워크) "이 화면은 모의" 로
 * 읽으므로 코드 구분은 콘솔 로그로만 남긴다.
 */
import { authFetch } from '../../lib/auth';

export type ActorType = 'all' | 'web' | 'synthetic';

export interface MartSource {
  marts: string[];
  mart_processed_at: string | null;
  coverage: 'full' | 'partial' | 'none';
}

export interface MartEnvelope {
  brand_id: string;
  range: { from: string; to: string; days: number };
  actor_type: ActorType;
  source: MartSource;
}

/* ---------- E1 overview ---------- */

export interface BrandPeriod {
  impression_sessions: number;
  product_view_sessions: number;
  information_view_sessions: number;
  add_to_cart_sessions: number;
  /** 상세 조회 ∪ 퀵룩 세션 — view_to_cart_rate 분모 (계약 0.2.1, 데이터 235 결함 보고). 마트에 아직 없으면 생략 */
  detail_view_sessions?: number | null;
  unique_user_count: number;
  product_count_viewed: number;
  product_view_count: number;
  add_to_cart_count: number;
  remove_from_cart_count: number;
  add_to_cart_sessions_by_product: number;
  remove_from_cart_sessions: number;
  detail_entry_rate: number | null;
  information_view_rate: number | null;
  view_to_cart_rate: number | null;
  removal_rate: number | null;
}

export interface FunnelSessions {
  impression_sessions: number;
  click_sessions: number;
  product_view_sessions: number;
  information_view_sessions: number;
  add_to_cart_sessions: number;
  quick_look_sessions?: number;
  quick_look_cart_sessions?: number;
  /** 상세 조회 ∪ 퀵룩 세션 — view_to_cart_rate 분모 (계약 0.2.1, 데이터 235 결함 보고). 마트에 아직 없으면 생략 */
  detail_view_sessions?: number | null;
  /** 결제 시작·구매 세션 (계약 0.2 추가, 마트에 있다). 옛 응답에는 없을 수 있어 선택 */
  checkout_sessions?: number | null;
  purchase_sessions?: number | null;
}

export interface OverviewPayload extends MartEnvelope {
  current: BrandPeriod;
  previous: BrandPeriod | null;
  daily: Array<{
    event_date_kst: string;
    product_view_sessions: number;
    add_to_cart_sessions: number;
    unique_user_count: number;
  }>;
  funnel: FunnelSessions | null;
}

/* ---------- E2 products ---------- */

export interface ProductDiagnostics {
  exit_content_kind_top: string | null;
  exit_sessions: number;
  variant_select_per_session: number | null;
  quick_look_open_detail_rate: number | null;
}

export interface ProductRow {
  product_id: string;
  product_impression_count: number;
  product_click_count: number;
  quick_look_count: number;
  product_view_count: number;
  add_to_cart_count: number;
  remove_from_cart_count: number;
  quick_look_sessions: number;
  product_view_sessions: number;
  add_to_cart_sessions: number;
  remove_from_cart_sessions: number;
  session_count: number;
  unique_user_count: number;
  /** 상세 조회 ∪ 퀵룩 세션. view_to_cart_rate 의 분모(계약 §4.1). 배포본 E2 가 준다 (규원님 실측 09-21) */
  detail_view_sessions?: number | null;
  product_ctr: number | null;
  detail_entry_rate: number | null;
  add_to_cart_rate: number | null;
  product_interest_score: number | null;
  funnel: FunnelSessions | null;
  diagnostics: ProductDiagnostics | null;
}

export interface ProductsPayload extends MartEnvelope {
  products: ProductRow[];
}

/* ---------- E3 content ---------- */

export interface ContentRow {
  content_kind: string;
  section_view_count: number;
  section_view_sessions: number;
  dwell_ms_sum: number;
  accordion_expand_count: number;
  text_selection_count: number;
  text_copy_count: number;
  matched_ingredient_count: number;
  product_view_sessions: number;
  avg_dwell_ms_per_session: number | null;
  view_rate: number | null;
  /**
   * `content_conversion_daily` (계약 0.3). 마트가 주는 것은 `viewed_cart_rate` 까지고 `cart_lift` 는 서버가 나눈다
   * (`viewed_cart_rate / brand.view_to_cart_rate`). 마트에서 미리 나누면 어느 브랜드·어느 기간의 비율을 썼는지가
   * 행에 박혀 다른 기준으로 다시 볼 수 없다 (데이터 파트 2026-09-16).
   */
  conversion: {
    viewed_sessions: number;
    viewed_cart_sessions: number;
    viewed_cart_rate?: number | null;
    cart_lift: number | null;
  } | null;
}

/**
 * `behavior_conversion_daily` (계약 0.3 · dw-schema §4.20). 이름은 마트 컬럼 그대로다.
 *
 * **행동 0건이어도 행이 온다.** 네 Event 가 항상 전부 나오고 `done_sessions = 0` 이면 `done_cart_rate` 가 null 이다 —
 * "아무도 안 했다" 이지 "집계 안 함" 이 아니다. 블록 자체가 null 인 것(= 마트 없음, 모의로 물러남)과 다르다.
 * 재생 데이터에서 `text_copy` 가 128세션뿐이라 실제로 밟는다.
 */
export interface BehaviorRow {
  event: string;
  done_sessions: number;
  not_done_sessions: number;
  done_cart_rate: number | null;
  not_done_cart_rate: number | null;
}

export interface ContentPayload extends MartEnvelope {
  by_content_kind: ContentRow[];
  brand: { product_view_sessions: number; add_to_cart_sessions: number; detail_view_sessions?: number | null; view_to_cart_rate: number | null };
  behaviors: BehaviorRow[] | null;
}

/* ---------- E4 segments ---------- */

export interface SegmentRow {
  segment_type: string;
  segment_value: string;
  segment_user_count: number;
  session_count: number;
  product_view_sessions: number;
  add_to_cart_sessions: number;
  /** 상세 조회 ∪ 퀵룩 세션 — view_to_cart_rate 분모 (계약 0.2.1, 데이터 235 결함 보고). 마트에 아직 없으면 생략 */
  detail_view_sessions?: number | null;
  view_to_cart_rate: number | null;
  avg_interest_score: number | null;
}

export interface SegmentsPayload extends MartEnvelope {
  by_segment: SegmentRow[];
  grid:
    | Array<{
        skin_type: string;
        skin_tone: string;
        product_view_sessions: number;
        add_to_cart_sessions: number;
        detail_view_sessions?: number | null;
        view_to_cart_rate: number | null;
      }>
    | null;
  /** `dwell_share` 의 분모는 **그 피부 타입의 총합**이라 한 타입 안에서만 합이 1 이다. 타입끼리 더하면 안 된다 */
  top_content: Array<{ skin_type: string; content_kind: string; dwell_ms_sum: number; dwell_share: number }> | null;
  same_skin_filter_rate: number | null;
  /** 브랜드 × 가격대 (`brand_price_band_daily_kpi`, 계약 0.3). 축을 걷어낸 합계는 by_segment 와 같지 않다 */
  price_bands?: PriceBandRow[] | null;
  /** 고객군 × 가격대 (`segment_price_band_daily_kpi`, 계약 0.3). 재설계 명세 §2-3 S5 히트맵의 정본 */
  segment_price_grid?: SegmentPriceCell[] | null;
  /** 코호트 배지 (`commons_cohort_weekly`, 계약 0.3 · §1-5). 유일한 B층 블록 */
  cohort?: CohortBlock | null;
}

/** 가격 구간은 `product-feature-vocab.json` 의 `price_bin_edges` 가 정본이다. 가격 결측 상품은 `price_bin = null` 행 */
export interface PriceBandRow {
  price_bin: string | null;
  currency: string;
  session_count: number;
  product_count: number;
  impression_sessions: number;
  quick_look_sessions: number;
  product_view_sessions: number;
  detail_view_sessions: number;
  add_to_cart_sessions: number;
  purchase_sessions: number;
  detail_entry_rate: number | null;
  view_to_cart_rate: number | null;
  view_to_purchase_rate: number | null;
}

export interface SegmentPriceCell {
  segment_type: string;
  segment_value: string;
  price_bin: string | null;
  currency: string;
  segment_user_count: number;
  session_count: number;
  product_count: number;
  product_view_sessions: number;
  detail_view_sessions: number;
  add_to_cart_sessions: number;
  purchase_sessions: number;
  view_to_cart_rate: number | null;
  view_to_purchase_rate: number | null;
}

/**
 * B층. 다른 브랜드를 식별할 값은 응답 어디에도 없다 — 마트가 브랜드 식별자를 아예 싣지 않는다 (dw-schema §4.18).
 *
 * `is_suppressed` 는 R1(브랜드 5 미만) 또는 R3(한 브랜드가 분모 50% 초과)이다. **행을 지우지 않고 값만 비운다** —
 * "억제됐다" 와 "코호트가 아예 없다" 를 구분하기 위해서다. 화면은 이때 "표본 부족" 으로 적고 숫자를 적지 않는다.
 * 블록 자체가 null 이면(코호트 미배정·그 주 행 없음) 배지를 그리지 않는다 — **모의로 채우지 않는다.**
 */
export interface CohortMetric {
  metric_name: string;
  p25: number | null;
  p50: number | null;
  p75: number | null;
  my_value: number | null;
  my_position: 'below_p25' | 'p25_p50' | 'p50_p75' | 'above_p75' | null;
}

export interface CohortBlock {
  cohort_key: string;
  product_count_band: string;
  dominant_price_bin: string | null;
  snapshot_week_kst: string;
  window_start_date: string;
  window_end_date: string;
  brand_count: number;
  is_suppressed: boolean;
  is_sample_sufficient: boolean;
  is_dominated: boolean;
  metrics: CohortMetric[];
}

/* ---------- E5 ingredients ---------- */

export interface IngredientRow {
  ingredient_id: number;
  ingredient: string;
  label_ko: string | null;
  vocab_version: string;
  ingredient_interest_score: number;
  direct_match_score: number;
  product_attributed_score: number;
  contributing_event_count: number;
  ingredient_interest_share: number | null;
}

export interface IngredientsPayload extends MartEnvelope {
  weeks: string[];
  by_ingredient: IngredientRow[];
}

/* ---------- E6 friction ---------- */

export interface FrictionPayload extends MartEnvelope {
  by_location: Array<{ section_id: string; event_name: string; event_count: number; session_count: number }> | null;
  counts: { rage_click: number; dead_click: number; scroll_backtrack: number } | null;
  quick_exit_rate: number | null;
  entry_source: Array<{
    entry_source: string;
    product_view_sessions: number;
    add_to_cart_sessions: number;
    detail_view_sessions?: number | null;
    view_to_cart_rate: number | null;
  }> | null;
  event_volumes: Array<{ event_name: string; event_count: number }> | null;
}

/* ---------- E7 purchase (계약 0.2 · brand_repurchase_daily · product_repurchase_daily · purchase_reason_daily) ---------- */

export interface RepurchaseRow {
  buyer_count: number;
  repeat_buyer_count: number;
  purchase_order_count: number;
  repurchase_rate: number | null;
  median_days_between_purchases: number | null;
  window_days: number;
  window_start_date: string;
  window_end_date: string;
}

export interface PurchasePayload extends MartEnvelope {
  /** brand_repurchase_daily 최신 스냅샷 한 행. 행이 없으면 null */
  brand: (RepurchaseRow & { declared_restock_order_count: number }) | null;
  products: Array<RepurchaseRow & { product_id: string }>;
  reasons: Array<{ reason: string | null; order_count: number; primary_order_count: number; reason_share: number | null }>;
}

/* ---------- 호출 ---------- */

export interface MartQuery {
  brandId: string;
  /** 최근 N일. 계약의 from/to 로 바꿔 보낸다 (to = 어제 KST) */
  days: number;
  actorType?: ActorType;
  /**
   * PA(에이전트)와 PC(배치 생성)를 가르는 축 (계약 0.3.1 · §1-2).
   *
   * `actorType` 으로는 못 가른다 — 데이터 파트 확인(09-11)대로 PA 도 전부 `synthetic` 이다.
   * `actor_type` enum 에 값을 더하면 기존 모든 마트의 grain 이 바뀌어서, 대신 이미 갈려 있는
   * `generator_type` 을 쓴다 (데이터 파트 결정 09-16 · Jira 324 에서 모든 마트 key 에 들어갔다).
   *
   * 기본은 `all`. PA 로그는 정성 축이라 정량 지표에서 빼고 싶을 때만 쓴다 (명세 §0-1).
   */
  generatorType?: string;
}

/**
 * KST 기준 **오늘까지** N일.
 *
 * 계약 §1-2 의 기본값은 어제까지다. "오늘은 마트가 아직 없다" 를 전제했기 때문인데, 그 전제가 뒤집혔다 —
 * 지금 마트에 있는 것이 오늘(재생한 날) 것뿐이라 어제까지로 부르면 전부 `coverage: none` 이다
 * (데이터 파트 확인 2026-09-17).
 *
 * 오늘을 넣어서 잃는 것은 없다. 오늘 마트가 없으면 그 날짜의 행이 0건이라 합계가 그대로다. 있으면 보인다.
 * 하나만 감수한다: 배치를 돌린 시각에 따라 방문 추이의 마지막 점이 덜 찬 하루일 수 있다.
 */
export function rangeOf(days: number): { from: string; to: string } {
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const to = new Date(kstNow);
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - (days - 1));
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { from: iso(from), to: iso(to) };
}

async function getMart<T extends MartEnvelope>(path: string, q: MartQuery): Promise<T | null> {
  const { from, to } = rangeOf(q.days);
  const params = new URLSearchParams({
    brandId: q.brandId,
    from,
    to,
    actorType: q.actorType ?? 'all',
    generatorType: q.generatorType ?? 'all',
  });
  try {
    const res = await authFetch('SELLER', `/api/seller/dashboard/${path}?${params.toString()}`);
    if (!res.ok) {
      if (import.meta.env.DEV && res.status !== 401) {
        // 401 은 서버 미기동·미로그인 때 늘 나오므로 조용히. 그 외는 계약 위반일 수 있어 남긴다
        console.info(`[mart] ${path} ${res.status}`);
      }
      return null;
    }
    const body = (await res.json()) as T;
    if (!body || typeof body !== 'object' || !body.source) return null;
    return body;
  } catch {
    return null;
  }
}

export const fetchOverview = (q: MartQuery) => getMart<OverviewPayload>('overview', q);
export const fetchProducts = (q: MartQuery) => getMart<ProductsPayload>('products', q);
export const fetchContent = (q: MartQuery) => getMart<ContentPayload>('content', q);
export const fetchSegments = (q: MartQuery) => getMart<SegmentsPayload>('segments', q);
export const fetchIngredients = (q: MartQuery) => getMart<IngredientsPayload>('ingredients', q);
export const fetchFriction = (q: MartQuery) => getMart<FrictionPayload>('friction', q);
export const fetchPurchase = (q: MartQuery) => getMart<PurchasePayload>('purchase', q);

export interface MartBundle {
  overview: OverviewPayload | null;
  products: ProductsPayload | null;
  content: ContentPayload | null;
  segments: SegmentsPayload | null;
  ingredients: IngredientsPayload | null;
  friction: FrictionPayload | null;
  purchase: PurchasePayload | null;
}

/** 일곱 개를 병렬로 한 번. 하나가 실패해도 나머지는 쓴다 */
export async function fetchMartBundle(q: MartQuery): Promise<MartBundle> {
  const [overview, products, content, segments, ingredients, friction, purchase] = await Promise.all([
    fetchOverview(q),
    fetchProducts(q),
    fetchContent(q),
    fetchSegments(q),
    fetchIngredients(q),
    fetchFriction(q),
    fetchPurchase(q),
  ]);
  return { overview, products, content, segments, ingredients, friction, purchase };
}

/** `coverage: none` 은 "마트는 있는데 이 브랜드 행이 0건". 화면은 모의로 그린다 (계약 §1-3) */
export function hasRows<T extends MartEnvelope>(p: T | null): p is T {
  return p !== null && p.source.coverage !== 'none';
}
