/**
 * 마트 API 응답 → 화면 모양 (BehaviorMetrics).
 *
 * 규칙 세 가지.
 *   1. **마트에 닿지 못했을 때만**(응답이 null) 그 블록을 모의로 둔다. 200 으로 답했으면 0 건이어도 그 답이
 *      정본이고 배지는 '실측' 이다 — 진짜 브랜드에 남의 숫자를 보여 주지 않는다.
 *   2. 응답 안에서 `null` 인 조건부 블록(계약 §3)은 따로 판정한다.
 *   3. 마트 컬럼 이름은 여기서만 화면 이름으로 바뀐다. 화면 코드에 snake_case 가 새지 않게.
 *
 * 브랜드 중앙값·병목 같은 파생 판단은 여기서 한다 (계약 E2: "병목은 프론트가 계산").
 */
import type { Product } from '../../types/product';
import type { EventName, IntentClass } from '../../types/log';
import { EVENT_INTENT, EVENT_WEIGHT } from '../../types/log';
import type {
  ContentPayload,
  FrictionPayload,
  IngredientsPayload,
  MartBundle,
  MartEnvelope,
  OverviewPayload,
  ProductsPayload,
  PurchasePayload,
  SegmentsPayload,
} from './martApi';
import type { BehaviorMetrics, BehaviorSource, Overview, Repurchase, SegmentTop } from './behavior';
import { buildIngredientGap, canonicalIngredient } from './behavior';
import type { ContentAttention, ProductMetrics } from './metrics';
import { SKIN_TONE_ORDER, catalogProducts } from './metrics';

/* ---------- 이름표 ---------- */

/** 상세페이지 안에서 읽는 콘텐츠 10종 (계약 E3). 마트가 더 주더라도 화면은 이 열 종만 */
export const CONTENT_KO: Record<string, string> = {
  ingredient_list: '성분 목록',
  user_review: '사용자 리뷰',
  clinical_claim: '임상 결과',
  ingredient_callout: '성분 특징',
  what_it_is: '제품 소개',
  usage_guide: '사용법',
  brand_story: '브랜드 소개',
  review_stats: '평점 분포',
  what_else: '추가 설명',
  product_image: '상품 이미지',
};

const BEHAVIOR_KO: Record<string, string> = {
  ingredient_view_mode_change: '전성분 펼쳐 보기',
  review_filter_apply: '내 피부 타입 리뷰만 보기',
  accordion_toggle: '접힌 정보 펼치기',
  text_copy: '성분명 복사',
};

const SECTION_KO: Record<string, string> = {
  product_image: '상품 이미지',
  gallery: '상품 이미지',
  ingredient_list: '성분 목록',
  ingredients: '성분 목록',
  variant_option: '옵션 선택',
  variants: '옵션 선택',
  user_review: '리뷰',
  reviews: '리뷰',
  review_more: '리뷰 더보기',
  cta: '담기 버튼',
  add_to_cart: '담기 버튼',
  price: '가격',
  usage_guide: '사용법',
  clinical_claim: '임상 결과',
};

const FRICTION_KO: Record<string, { ko: string; meaning: string }> = {
  dead_click: { ko: '눌러도 아무 일이 없었습니다', meaning: '반응을 기대하고 눌렀는데 아무 일도 없었습니다. 눌리는 것처럼 보이는 자리일 수 있습니다' },
  rage_click: { ko: '같은 자리를 여러 번 눌렀습니다', meaning: '눌렀는데 반응이 없어 다시 눌렀습니다' },
  scroll_backtrack: { ko: '위로 다시 올려 읽었습니다', meaning: '한 번 읽고 이해가 안 돼 다시 봤을 수 있습니다' },
  hover_dwell: { ko: '누르기 전에 머뭇거렸습니다', meaning: '커서를 얹고 망설였습니다' },
};

const ENTRY_KO: Record<string, string> = {
  similar_products: '유사 상품 추천',
  promo_pick: '맞춤 기획전',
  list_grid: '목록',
  quick_look: '빠른 보기에서',
  search: '검색',
  banner: '배너',
  hero: '첫 화면 큰 배너',
  direct: '주소로 바로 들어옴',
};

/* ---------- 도움 ---------- */

const ratio = (num: number, den: number): number => (den === 0 ? 0 : num / den);
const nz = (v: number | null | undefined, fallback: number): number => (v === null || v === undefined || Number.isNaN(v) ? fallback : v);
/**
 * 담기율(view_to_cart_rate) 폴백 — 마트가 비율을 안 주면 여기서 나눈다. 분모는 계약 0.2.1 대로
 * `detail_view_sessions`(상세 ∪ 퀵룩). 분자 add_to_cart_sessions 가 퀵룩 담기를 포함해서 분모도 퀵룩을 세야
 * 1.0 을 안 넘는다(데이터 235 E2E). 마트에 그 컬럼이 아직 없으면 옛 분모 product_view_sessions 로 물러난다.
 */
const cartRateOf = (x: { view_to_cart_rate: number | null; add_to_cart_sessions: number; product_view_sessions: number; detail_view_sessions?: number | null }): number =>
  nz(x.view_to_cart_rate, ratio(x.add_to_cart_sessions, x.detail_view_sessions ?? x.product_view_sessions));

function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** 여러 응답의 mart_processed_at 중 가장 오래된 것 (계약 §1-3) */
function oldestProcessedAt(payloads: Array<MartEnvelope | null>): string | null {
  const ts = payloads
    .filter((p): p is MartEnvelope => p !== null)
    .map((p) => p.source.mart_processed_at)
    .filter((t): t is string => Boolean(t))
    .sort();
  return ts[0] ?? null;
}

/* ---------- 블록별 변환 ---------- */

function toOverview(p: OverviewPayload['current'], content: ContentPayload | null, funnelClicks: number, quickLooks: number, bounce: number | null): Overview {
  const kind = (k: string) => content?.by_content_kind.find((c) => c.content_kind === k)?.view_rate ?? null;
  const infoRate = nz(p.information_view_rate, ratio(p.information_view_sessions, p.product_view_sessions));
  return {
    sessions: p.product_view_sessions,
    impressions: p.impression_sessions,
    clicks: funnelClicks,
    detailViews: p.product_view_count,
    quickLooks,
    addToCart: p.add_to_cart_count,
    removed: p.remove_from_cart_count,
    detailRate: nz(p.detail_entry_rate, ratio(p.product_view_sessions, p.impression_sessions)),
    cartRate: cartRateOf(p),
    removalRate: nz(p.removal_rate, ratio(p.remove_from_cart_sessions, p.add_to_cart_sessions_by_product)),
    ingredientViewRate: nz(kind('ingredient_list'), infoRate),
    reviewViewRate: nz(kind('user_review'), infoRate),
    infoRate,
    infoViews: p.information_view_sessions,
    bounceRate: bounce,
  };
}

function toProducts(p: ProductsPayload): { rows: ProductMetrics[]; diagnostics: boolean } {
  const byId = new Map<string, Product>(catalogProducts.map((c) => [c.product_id, c]));
  let anyDiag = false;

  const base = p.products
    .map((r) => {
      const product = byId.get(r.product_id);
      if (!product) return null; // 카탈로그에 없는 상품은 이름을 못 붙인다. 등록 카탈로그 동기화가 붙으면 여기서 찾는다
      const f = r.funnel;
      const impressions = r.product_impression_count;
      const clicks = r.product_click_count;
      // 관심 점수·단계 비율은 Event 건수로, 문턱·담기 비율은 세션 수로. 둘을 섞으면 비율이 1.0 을 넘는다 (계약 §4.1 실측)
      const detailViewCount = r.product_view_count;
      const detailViews = r.detail_view_sessions ?? f?.detail_view_sessions ?? r.product_view_sessions;
      const addToCart = r.add_to_cart_count;
      const removed = r.remove_from_cart_count;
      const infoRate = f ? ratio(f.information_view_sessions, f.product_view_sessions) : 0;
      const rates = {
        click: f ? ratio(f.click_sessions, f.impression_sessions) : ratio(clicks, impressions),
        detail: f ? ratio(f.product_view_sessions, f.click_sessions) : ratio(detailViewCount, clicks),
        info: infoRate,
        cart: r.add_to_cart_rate ?? (f ? ratio(f.add_to_cart_sessions, f.detail_view_sessions ?? f.product_view_sessions) : ratio(r.add_to_cart_sessions, detailViews)),
      };
      const interest =
        r.product_interest_score ??
        clicks * EVENT_WEIGHT.product_click +
          detailViewCount * EVENT_WEIGHT.page_view +
          r.quick_look_count * EVENT_WEIGHT.quick_look +
          addToCart * EVENT_WEIGHT.add_to_cart +
          removed * EVENT_WEIGHT.remove_from_cart;

      /*
       * 진단 3열. **마트가 안 주면 null 이다.** 예전에는 상품 id 로 시드 난수를 굴려 이탈 지점·옵션 왕복을
       * 지어냈다. 배지가 '모의' 였다고는 해도 표에는 그럴듯한 값이 박혀 있어서, 사장님이 "리뷰에서 나간다"
       * 같은 문장을 그대로 읽고 손을 댔다. 없는 것은 하이픈으로 둔다.
       */
      const d = r.diagnostics;
      // 마트가 준 종류를 그대로 받는다. 여섯 종만 걸러 받던 흰목록이 마트 660행을 '-' 로 만들었다 (2026-09-21)
      const exitContent = d?.exit_content_kind_top ?? null;
      if (d) anyDiag = true;

      const row: ProductMetrics & { rates: typeof rates } = {
        product,
        impressions,
        clicks,
        detailViews,
        cartRate: rates.cart,
        quickLooks: r.quick_look_count,
        ingredientViewRate: infoRate,
        reviewViewRate: infoRate,
        addToCart,
        removedFromCart: removed,
        interestScore: Math.round(interest),
        bottleneck: 'cart',
        exitContent,
        variantSwitches: d?.variant_select_per_session ?? null,
        quickLookToDetail: d?.quick_look_open_detail_rate ?? null,
        removeRate: ratio(r.remove_from_cart_sessions, r.add_to_cart_sessions),
        infoRate,
        rates,
      };
      return row;
    })
    .filter((r): r is ProductMetrics & { rates: Record<'click' | 'detail' | 'info' | 'cart', number> } => r !== null);

  // 병목 = 브랜드 중앙값 대비 가장 낮은 단계 (계약 E2). 다른 브랜드 값은 섞이지 않는다
  const med = {
    click: median(base.map((b) => b.rates.click)),
    detail: median(base.map((b) => b.rates.detail)),
    info: median(base.map((b) => b.rates.info)),
    cart: median(base.map((b) => b.rates.cart)),
  };
  const rows: ProductMetrics[] = base.map(({ rates, ...m }) => {
    const rel = (k: keyof typeof rates) => (med[k] === 0 ? 1 : rates[k] / med[k]);
    const keys = Object.keys(rates) as Array<keyof typeof rates>;
    const bottleneck = keys.reduce((a, b) => (rel(a) <= rel(b) ? a : b));
    return { ...m, bottleneck };
  });
  rows.sort((a, b) => b.interestScore - a.interestScore);
  return { rows, diagnostics: anyDiag };
}

function toContent(p: ContentPayload): { rows: ContentAttention[]; lift: boolean } {
  let anyLift = false;
  const rows = Object.keys(CONTENT_KO)
    .map((kind) => {
      const r = p.by_content_kind.find((c) => c.content_kind === kind);
      if (!r) return null;
      const lift = r.conversion?.cart_lift;
      if (lift !== null && lift !== undefined) anyLift = true;
      return {
        kind,
        ko: CONTENT_KO[kind],
        avgDwellMs: nz(r.avg_dwell_ms_per_session, ratio(r.dwell_ms_sum, r.product_view_sessions)),
        viewRate: nz(r.view_rate, ratio(r.section_view_sessions, r.product_view_sessions)),
        conversionLift: lift ?? 1,
        sampleSize: r.section_view_sessions,
      };
    })
    .filter((r): r is ContentAttention => r !== null);
  return { rows, lift: anyLift };
}

function toSegments(p: SegmentsPayload, emptyMatrix: BehaviorMetrics['segmentMatrix'], emptyTop: SegmentTop[]) {
  const types = ['dry', 'oily', 'combination', 'normal'];
  const byType = p.by_segment
    .filter((s) => s.segment_type === 'skin_type')
    .map((s) => ({ type: s.segment_value, sessions: s.product_view_sessions, cartRate: cartRateOf(s) }));

  const matrix = p.grid
    ? types.map((type) => ({
        type,
        cells: SKIN_TONE_ORDER.map((tone) => {
          const c = p.grid?.find((g) => g.skin_type === type && g.skin_tone === tone);
          return {
            tone,
            cartRate: c ? cartRateOf(c) : 0,
            sessions: c?.product_view_sessions ?? 0,
          };
        }),
      }))
    : emptyMatrix;

  const top = p.top_content
    ? types.map((type) => {
        const rows = p.top_content?.filter((t) => t.skin_type === type).sort((a, b) => b.dwell_ms_sum - a.dwell_ms_sum) ?? [];
        const ko = (k: string | undefined) => (k ? CONTENT_KO[k] ?? k : '-');
        return { type, top: ko(rows[0]?.content_kind), second: ko(rows[1]?.content_kind), dwellShare: rows[0]?.dwell_share ?? 0 };
      })
    : emptyTop;

  return { byType: byType.length > 0 ? byType : null, matrix, grid: Boolean(p.grid), top, topReal: Boolean(p.top_content), sameSkin: p.same_skin_filter_rate };
}

/** 드래그 TOP 10. 어휘집에 없는 이름은 한국어 표시명을 붙일 수 없어 뺀다 (성분 갭 표와 같은 규칙) */
function toScraped(p: IngredientsPayload) {
  return [...p.by_ingredient]
    .map((i) => ({ name: canonicalIngredient(i.ingredient), score: i.direct_match_score }))
    .filter((i): i is { name: string; score: number } => i.name !== null)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10)
    .map((i) => ({ name: i.name, count: Math.round(i.score), copyCount: null }));
}

function toFriction(p: FrictionPayload, base: BehaviorMetrics) {
  const byLocation = p.by_location
    ? p.by_location
        .map((f) => ({
          where: SECTION_KO[f.section_id] ?? f.section_id,
          event: f.event_name,
          ko: FRICTION_KO[f.event_name]?.ko ?? f.event_name,
          count: f.event_count,
          meaning: FRICTION_KO[f.event_name]?.meaning ?? '',
        }))
        .sort((a, b) => b.count - a.count)
    : base.frictionByLocation;
  const entry = p.entry_source
    ? p.entry_source
        .map((e) => ({
          source: e.entry_source,
          ko: ENTRY_KO[e.entry_source] ?? e.entry_source,
          sessions: e.product_view_sessions,
          cartRate: cartRateOf(e),
        }))
        .sort((a, b) => b.sessions - a.sessions)
    : base.entryConversion;
  const volumes = p.event_volumes
    ? p.event_volumes.map((e) => ({ name: e.event_name as EventName, count: e.event_count })).sort((a, b) => b.count - a.count).slice(0, 13)
    : base.eventVolumes;
  return {
    byLocation,
    counts: p.counts ?? base.frictionCounts,
    // 마트가 답했는데 비율이 없으면 "판정할 세션이 없었다" 는 뜻이다. 모의 이탈률을 끼워 넣지 않는다
    quickExit: p.quick_exit_rate ?? 0,
    entry,
    volumes,
    frictionReal: Boolean(p.by_location || p.counts),
    entryReal: Boolean(p.entry_source),
  };
}

/**
 * "고객이 지나온 단계" — 이벤트 건수를 의미(intent)별로 접는다.
 *
 * 마트에 단계 축이 따로 없다. 그런데 이벤트 하나하나의 의미는 `EVENT_INTENT` 가 이미 정하고 있고
 * (로거가 envelope 의 `intent` 를 그 표로 채운다), `event_daily` 가 브랜드별 이벤트 건수를 준다.
 * 둘을 곱하면 이 화면이 필요한 다섯 칸이 나온다 — 지어낼 필요가 없다.
 *
 * 망설임(hesitation)·막힘(friction)·세션 경계(session)는 단계가 아니라 빼고, 막힘은 옆 패널이 따로 센다.
 */
const INTENT_STEPS: Array<{ label: IntentClass; ko: string }> = [
  { label: 'exposure', ko: '상품이 보임' },
  { label: 'interest', ko: '열어 봄' },
  { label: 'comparison', ko: '비교함' },
  { label: 'validation', ko: '성분·리뷰 확인' },
  { label: 'conversion', ko: '담기·구매' },
];

function toIntentFunnel(volumes: Array<{ event_name: string; event_count: number }>): Array<{ label: string; ko: string; value: number }> {
  const totals = new Map<IntentClass, number>();
  for (const v of volumes) {
    const intent = EVENT_INTENT[v.event_name as EventName];
    if (!intent) continue;
    totals.set(intent, (totals.get(intent) ?? 0) + v.event_count);
  }
  return INTENT_STEPS.map((s) => ({ label: s.label, ko: s.ko, value: totals.get(s.label) ?? 0 }));
}

function toRepurchase(p: PurchasePayload): Repurchase | null {
  const hasAny = p.brand !== null || p.products.length > 0 || p.reasons.length > 0;
  if (!hasAny) return null;
  return {
    brand: p.brand
      ? {
          buyerCount: p.brand.buyer_count,
          repeatBuyerCount: p.brand.repeat_buyer_count,
          orderCount: p.brand.purchase_order_count,
          rate: p.brand.repurchase_rate,
          medianDays: p.brand.median_days_between_purchases,
          declaredRestockOrders: p.brand.declared_restock_order_count,
          windowDays: p.brand.window_days,
        }
      : null,
    products: new Map(p.products.map((r) => [r.product_id, { buyerCount: r.buyer_count, repeatBuyerCount: r.repeat_buyer_count, rate: r.repurchase_rate }])),
    reasons: p.reasons.map((r) => ({ reason: r.reason, orderCount: r.order_count, share: r.reason_share })),
  };
}

/* ---------- 합치기 ---------- */

/**
 * 마트 묶음을 화면 모양으로. `base` 는 `emptyBehavior()` 의 0·빈 표이고, 마트가 답하지 않은 블록은 그대로 남는다.
 * 브랜드 상품 목록(`brandProducts`)은 성분 갭의 보유 판정에 쓴다. 마트 브랜드가 카탈로그에 있으면 그 상품들, 없으면 모의 브랜드 상품.
 */
export function fromMart(bundle: MartBundle, base: BehaviorMetrics, brandProducts?: Product[]): BehaviorMetrics {
  const src: BehaviorSource = { ...base.source };
  let out: BehaviorMetrics = { ...base };

  /**
   * **서버가 답했으면 그 답이 정본이다. 0 건이어도 그렇다.**
   *
   * 예전에는 `coverage: none`(= 이 브랜드 행이 0건)을 모의로 덮었다. 시연 브랜드는 로그가 없으니 화면이 비면
   * 안 된다는 이유였는데, SSAFY Beauty 는 진짜 브랜드다. 진짜 브랜드 사장님에게 남의 숫자를 "우리 브랜드" 로
   * 보여 주는 것이 화면이 비는 것보다 나쁘다 — 그 숫자를 보고 재고를 잡고 기획을 건다.
   *
   * 그래서 모의로 물러나는 경우를 하나로 줄인다: **마트에 닿지 못했을 때만**(401·403·5xx·네트워크 →
   * 응답이 `null`). 200 으로 답했으면 0 을 0 으로 그리고 배지는 "실측" 이다.
   */
  const ov = bundle.overview;
  const pr = bundle.products;
  const ct = bundle.content;
  const sg = bundle.segments;
  const ig = bundle.ingredients;
  const fr = bundle.friction;
  const pu = bundle.purchase;

  // E2 먼저. 개요의 퀵룩 합계와 성분 보유 판정에 상품이 필요하다
  let quickLooks = base.overview.quickLooks;
  if (pr) {
    const { rows, diagnostics } = toProducts(pr);
    // 행이 0 개여도 그대로 쓴다. "아직 아무도 안 봤다" 는 사실이고, 모의 상품 목록으로 덮으면 사실이 사라진다
    out = { ...out, productMetrics: rows };
    src.products = 'real';
    src.diagnostics = diagnostics ? 'real' : 'none';
    quickLooks = rows.reduce((s, r) => s + r.quickLooks, 0);
  }

  // E6 (개요의 이탈률에 quick_exit 를 쓴다)
  let bounce: number | null = null;
  if (fr) {
    const f = toFriction(fr, base);
    out = {
      ...out,
      frictionByLocation: f.byLocation,
      frictionCounts: f.counts,
      quickExitRate: f.quickExit,
      entryConversion: f.entry,
      eventVolumes: f.volumes,
    };
    src.friction = f.frictionReal ? 'real' : 'none';
    src.entry = f.entryReal ? 'real' : 'none';
    if (fr.event_volumes) out = { ...out, intentFunnel: toIntentFunnel(fr.event_volumes) };
    bounce = fr.quick_exit_rate;
  }

  // E1
  if (ov) {
    const clicks = ov.funnel?.click_sessions ?? 0;
    out = {
      ...out,
      overview: toOverview(ov.current, ct, clicks, quickLooks, bounce),
      previous: ov.previous ? toOverview(ov.previous, null, 0, 0, null) : null,
      daily: ov.daily.map((d) => ({ label: d.event_date_kst.slice(5).replace('-', '/'), visits: d.product_view_sessions, carts: d.add_to_cart_sessions })),
    };
    src.overview = 'real';
    if (ov.funnel) {
      out = {
        ...out,
        /*
         * 구매까지 가는 단계 (데이터 파트 지적 2026-09-22).
         *
         * **성분·리뷰 확인은 뺐다.** 순차 단계가 아니라 상세 아래 형제 단계다 — 퀵룩에는 성분·리뷰가 없어서
         * 퀵룩에서 바로 담은 방문은 볼 기회가 없었는데 담기 수에는 들어간다. 그래서 "성분·리뷰 → 담기" 가
         * 154% 로 나왔다. 계약도 담기 ≤ 성분·리뷰 를 보장한 적이 없다 (전체 행의 84.7% 가 담기 > 성분·리뷰).
         * 이 값은 퍼널 옆에 상품 상세를 분모로 따로 적는다.
         *
         * **'상세를 봄' 은 세션 기준이다.** 담기(퀵룩 포함)와 모집단을 맞춘다. 전에는 퀵룩을 뺀 수를 써서
         * 담기와 분모가 달랐고 96.4% 까지 올라갔다 — 조건이 조금만 바뀌면 이 칸도 100% 를 넘는다.
         *
         * **'상품을 누름' 칸도 뺐다** (은솔님 2026-09-22 사슬 전체 확인). 목록의 퀵룩 버튼은 product_click 을 내지 않아
         * 클릭과 퀵룩은 병렬 경로다. 클릭을 분모로 두면 "누름 → 상세" 가 646% 가 된다 (전체 행의 99% 가 상세 > 누름).
         * 클릭률은 퍼널 밖 한 줄(funnelNote)로 적는다 — 실제 주 동선은 퀵룩이라 퍼널에 클릭 칸이 있으면 반대로 읽힌다.
         * 뒤에 결제·구매를 이어 붙인다. 네 쌍(보임→상세→담기→결제→구매) 전부 단조 감소가 보장된 값이다.
         */
        standardFunnel: [
          { label: '상품이 보임', value: ov.funnel.impression_sessions },
          { label: '상세를 봄', value: ov.funnel.detail_view_sessions ?? ov.funnel.product_view_sessions },
          { label: '장바구니에 담음', value: ov.funnel.add_to_cart_sessions },
          ...(typeof ov.funnel.checkout_sessions === 'number' ? [{ label: '결제로 감', value: ov.funnel.checkout_sessions }] : []),
          ...(typeof ov.funnel.purchase_sessions === 'number' ? [{ label: '구매', value: ov.funnel.purchase_sessions }] : []),
        ],
        funnelNote: {
          impressionSessions: ov.funnel.impression_sessions,
          clickSessions: ov.funnel.click_sessions,
          detailSessions: ov.funnel.detail_view_sessions ?? ov.funnel.product_view_sessions,
          productViewSessions: ov.funnel.product_view_sessions,
          quickLookSessions: ov.funnel.quick_look_sessions ?? null,
        },
      };
      src.funnel = 'real';
    }
  }

  // E3
  if (ct) {
    const { rows, lift } = toContent(ct);
    out = { ...out, contentAttention: rows };
    src.content = 'real';
    src.contentLift = lift ? 'real' : 'none';
    if (ct.behaviors) {
      out = {
        ...out,
        /**
         * 실행률의 분모는 `done + not_done` 이다 (계약 0.3). 마트가 "그 상품의 조회 세션 수" 로 이 둘을 가르므로
         * 같은 행에서 나누는 것이 브랜드 총계로 나누는 것보다 정확하다 — 세션 모집단이 어긋나지 않는다.
         * 행동 0건이어도 행이 오고, 그때 `done_cart_rate` 는 null 이다. 0 은 "아무도 안 했다" 로 그대로 그린다.
         */
        validationBehaviors: ct.behaviors.map((b) => ({
          event: b.event,
          ko: BEHAVIOR_KO[b.event] ?? b.event,
          doneRate: ratio(b.done_sessions, b.done_sessions + b.not_done_sessions),
          cartRateWith: b.done_cart_rate ?? 0,
          cartRateWithout: b.not_done_cart_rate ?? 0,
        })),
      };
      src.behaviors = 'real';
    }
  }

  // E4
  if (sg) {
    const s = toSegments(sg, [], []);
    out = {
      ...out,
      segmentByType: s.byType ?? [],
      // 격자·상위 콘텐츠가 비어 있는 것도 답이다. 모의 히트맵으로 덮으면 없는 고객군이 있는 것처럼 보인다
      segmentMatrix: s.matrix,
      segmentTopContent: s.top,
      sameSkinFilterRate: s.sameSkin ?? 0,
    };
    src.segments = 'real';
    src.grid = 'real';
    src.topContent = 'real';

    /*
     * 가격 블록 셋 (계약 0.3). 서버가 아직 안 주면(undefined·null) 자리를 비운다 — 모의로 채우지 않는다.
     * 비교 대상이 다른 브랜드인 코호트는 특히 흉내 내면 안 되는 숫자다.
     */
    if (sg.price_bands) {
      out = {
        ...out,
        priceBands: sg.price_bands.map((b) => ({
          bin: b.price_bin,
          productCount: b.product_count,
          sessions: b.detail_view_sessions,
          cartSessions: b.add_to_cart_sessions,
          purchaseSessions: b.purchase_sessions,
          detailEntryRate: b.detail_entry_rate,
          cartRate: b.view_to_cart_rate,
          purchaseRate: b.view_to_purchase_rate,
        })),
      };
      src.priceBands = 'real';
    }
    if (sg.segment_price_grid) {
      const types = ['dry', 'oily', 'combination', 'normal'];
      const cellsOf = sg.segment_price_grid.filter((c) => c.segment_type === 'skin_type');
      out = {
        ...out,
        segmentPriceGrid: types.map((type) => ({
          type,
          cells: cellsOf
            .filter((c) => c.segment_value === type)
            .map((c) => ({ bin: c.price_bin, sessions: c.detail_view_sessions, cartRate: c.view_to_cart_rate ?? 0 })),
        })),
      };
      src.segmentPriceGrid = 'real';
    }
    if (sg.cohort) {
      const c = sg.cohort;
      out = {
        ...out,
        cohort: {
          key: c.cohort_key,
          productBand: c.product_count_band,
          priceBin: c.dominant_price_bin,
          weekStart: c.window_start_date,
          weekEnd: c.window_end_date,
          brandCount: c.brand_count,
          suppressed: c.is_suppressed,
          sampleSufficient: c.is_sample_sufficient,
          metrics: c.metrics.map((m) => ({ name: m.metric_name, p25: m.p25, p50: m.p50, p75: m.p75, mine: m.my_value, position: m.my_position })),
        },
      };
    }
  }

  // E5
  if (ig) {
    const ver = ig.by_ingredient[0]?.vocab_version;
    if (import.meta.env.DEV && ver && ver !== '0.4') console.info(`[mart] ingredient vocab_version ${ver} (프론트 어휘집 0.4)`);
    const gapProducts = brandProducts && brandProducts.length > 0 ? brandProducts : out.productMetrics.map((m) => m.product);
    out = {
      ...out,
      scrapedIngredients: toScraped(ig),
      ingredientGap: buildIngredientGap(
        ig.by_ingredient.map((i) => ({
          name: i.ingredient,
          scrapeCount: Math.round(i.direct_match_score),
          dwellMs: i.product_attributed_score,
          interest: i.ingredient_interest_score,
        })),
        gapProducts,
      ),
      ingredientInterestKind: 'score',
    };
    src.scraped = 'real';
    src.ingredients = 'real';
  }

  // E7 재구매. 모의가 없으니 마트가 있을 때만 값이 생긴다
  if (pu) {
    const rp = toRepurchase(pu);
    if (rp) {
      out = { ...out, repurchase: rp };
      src.purchase = 'real';
    }
  }

  const anyReal = Object.values(src).some((v) => v === 'real');
  return {
    ...out,
    source: src,
    martProcessedAt: oldestProcessedAt([ov, pr, ct, sg, ig, fr, pu]),
    anyReal,
  };
}
