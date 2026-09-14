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
  conversion: { viewed_sessions: number; viewed_cart_sessions: number; cart_lift: number | null } | null;
}

export interface BehaviorRow {
  event: string;
  done_sessions: number;
  cart_rate_with: number | null;
  cart_rate_without: number | null;
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
  top_content: Array<{ skin_type: string; content_kind: string; dwell_ms_sum: number; dwell_share: number }> | null;
  same_skin_filter_rate: number | null;
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
}

/** KST 기준 어제까지 N일. 계약 §1-2 기본과 같지만 명시적으로 보낸다 */
export function rangeOf(days: number): { from: string; to: string } {
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const to = new Date(kstNow);
  to.setUTCDate(to.getUTCDate() - 1);
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - (days - 1));
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { from: iso(from), to: iso(to) };
}

async function getMart<T extends MartEnvelope>(path: string, q: MartQuery): Promise<T | null> {
  const { from, to } = rangeOf(q.days);
  const params = new URLSearchParams({ brandId: q.brandId, from, to, actorType: q.actorType ?? 'all' });
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
