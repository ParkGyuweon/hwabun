/**
 * 마트 API 응답 → 화면 모양 (BehaviorMetrics).
 *
 * 규칙 세 가지.
 *   1. 응답이 없거나 `coverage: none` 이면 그 블록은 **모의 그대로** 두고 source 도 'mock' 으로 남긴다.
 *   2. 응답이 있으면 채운 블록만 'real'. 조건부 블록(계약 §3 의 null 가능)은 따로 판정한다.
 *   3. 마트 컬럼 이름은 여기서만 화면 이름으로 바뀐다. 화면 코드에 snake_case 가 새지 않게.
 *
 * 브랜드 중앙값·병목 같은 파생 판단은 여기서 한다 (계약 E2: "병목은 프론트가 계산").
 */
import type { Product } from '../../types/product';
import type { EventName } from '../../types/log';
import { EVENT_WEIGHT } from '../../types/log';
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
import { hasRows } from './martApi';
import type { BehaviorMetrics, BehaviorSource, Overview, Repurchase, SegmentTop } from './behavior';
import { buildIngredientGap, canonicalIngredient } from './behavior';
import type { ContentAttention, ProductMetrics } from './metrics';
import { SKIN_TONE_ORDER, catalogProducts, hashString, rng } from './metrics';

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
  dead_click: { ko: '눌러도 아무 일이 없었습니다', meaning: '반응을 기대하고 눌렀는데 아무 일도 없었습니다' },
  rage_click: { ko: '같은 자리를 여러 번 눌렀습니다', meaning: '눌렀는데 반응이 없어 다시 눌렀습니다' },
  scroll_backtrack: { ko: '위로 다시 올려 읽었습니다', meaning: '한 번 읽고 이해가 안 돼 다시 봤을 수 있습니다' },
  hover_dwell: { ko: '누르기 전에 머뭇거렸습니다', meaning: '커서를 얹고 망설였습니다' },
};

const ENTRY_KO: Record<string, string> = {
  similar_products: '유사 상품 추천',
  promo_pick: '맞춤 기획전',
  list_grid: '목록',
  quick_look: '퀵룩에서',
  search: '검색',
  banner: '배너',
  hero: '히어로',
  direct: '직접 진입',
};

const EXIT_KINDS: ProductMetrics['exitContent'][] = ['ingredient_list', 'usage_guide', 'user_review', 'similar_products', 'product_hero', 'price'];

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
    bounceRate: bounce,
  };
}

function toProducts(p: ProductsPayload, mock: ProductMetrics[]): { rows: ProductMetrics[]; diagnostics: boolean } {
  const byId = new Map<string, Product>(catalogProducts.map((c) => [c.product_id, c]));
  const mockById = new Map(mock.map((m) => [m.product.product_id, m]));
  let anyDiag = false;

  const base = p.products
    .map((r) => {
      const product = byId.get(r.product_id);
      if (!product) return null; // 카탈로그에 없는 상품은 이름을 못 붙인다. 등록 카탈로그 동기화가 붙으면 여기서 찾는다
      const f = r.funnel;
      const impressions = r.product_impression_count;
      const clicks = r.product_click_count;
      const detailViews = r.product_view_count;
      const addToCart = r.add_to_cart_count;
      const removed = r.remove_from_cart_count;
      const infoRate = f ? ratio(f.information_view_sessions, f.product_view_sessions) : 0;
      const rates = {
        click: f ? ratio(f.click_sessions, f.impression_sessions) : ratio(clicks, impressions),
        detail: f ? ratio(f.product_view_sessions, f.click_sessions) : ratio(detailViews, clicks),
        info: infoRate,
        cart: f ? ratio(f.add_to_cart_sessions, f.detail_view_sessions ?? f.product_view_sessions) : ratio(addToCart, detailViews),
      };
      const interest =
        r.product_interest_score ??
        clicks * EVENT_WEIGHT.product_click +
          detailViews * EVENT_WEIGHT.page_view +
          r.quick_look_count * EVENT_WEIGHT.quick_look +
          addToCart * EVENT_WEIGHT.add_to_cart +
          removed * EVENT_WEIGHT.remove_from_cart;

      // 진단 3열. 마트가 없으면 모의 상품의 값을 그대로(같은 상품이면) 아니면 시드로
      const d = r.diagnostics;
      const fallback = mockById.get(r.product_id);
      const rand = rng(hashString(r.product_id));
      const exitContent = (d?.exit_content_kind_top && EXIT_KINDS.includes(d.exit_content_kind_top as ProductMetrics['exitContent'])
        ? d.exit_content_kind_top
        : fallback?.exitContent ?? EXIT_KINDS[Math.floor(rand() * EXIT_KINDS.length)]) as ProductMetrics['exitContent'];
      if (d) anyDiag = true;

      const row: ProductMetrics & { rates: typeof rates } = {
        product,
        impressions,
        clicks,
        detailViews,
        quickLooks: r.quick_look_count,
        ingredientViewRate: infoRate,
        reviewViewRate: infoRate,
        addToCart,
        removedFromCart: removed,
        interestScore: Math.round(interest),
        bottleneck: 'cart',
        exitContent,
        variantSwitches: d?.variant_select_per_session ?? fallback?.variantSwitches ?? Math.round((1 + rand() * 3) * 10) / 10,
        quickLookToDetail: d?.quick_look_open_detail_rate ?? fallback?.quickLookToDetail ?? 0.3 + rand() * 0.45,
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

function toContent(p: ContentPayload, mock: ContentAttention[]): { rows: ContentAttention[]; lift: boolean } {
  const mockLift = new Map(mock.map((m) => [m.kind, m.conversionLift]));
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
        conversionLift: lift ?? mockLift.get(kind) ?? 1,
        sampleSize: r.section_view_sessions,
      };
    })
    .filter((r): r is ContentAttention => r !== null);
  return { rows, lift: anyLift };
}

function toSegments(p: SegmentsPayload, mockMatrix: BehaviorMetrics['segmentMatrix'], mockTop: SegmentTop[]) {
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
    : mockMatrix;

  const top = p.top_content
    ? types.map((type) => {
        const rows = p.top_content?.filter((t) => t.skin_type === type).sort((a, b) => b.dwell_ms_sum - a.dwell_ms_sum) ?? [];
        const ko = (k: string | undefined) => (k ? CONTENT_KO[k] ?? k : '-');
        return { type, top: ko(rows[0]?.content_kind), second: ko(rows[1]?.content_kind), dwellShare: rows[0]?.dwell_share ?? 0 };
      })
    : mockTop;

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

function toFriction(p: FrictionPayload, mock: BehaviorMetrics) {
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
    : mock.frictionByLocation;
  const entry = p.entry_source
    ? p.entry_source
        .map((e) => ({
          source: e.entry_source,
          ko: ENTRY_KO[e.entry_source] ?? e.entry_source,
          sessions: e.product_view_sessions,
          cartRate: cartRateOf(e),
        }))
        .sort((a, b) => b.sessions - a.sessions)
    : mock.entryConversion;
  const volumes = p.event_volumes
    ? p.event_volumes.map((e) => ({ name: e.event_name as EventName, count: e.event_count })).sort((a, b) => b.count - a.count).slice(0, 13)
    : mock.eventVolumes;
  return {
    byLocation,
    counts: p.counts ?? mock.frictionCounts,
    quickExit: p.quick_exit_rate ?? mock.quickExitRate,
    entry,
    volumes,
    frictionReal: Boolean(p.by_location || p.counts),
    entryReal: Boolean(p.entry_source),
  };
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
 * 마트 묶음을 화면 모양으로. `mock` 은 같은 기간의 모의 묶음이고, 없는 블록은 거기서 그대로 가져온다.
 * 브랜드 상품 목록(`brandProducts`)은 성분 갭의 보유 판정에 쓴다. 마트 브랜드가 카탈로그에 있으면 그 상품들, 없으면 모의 브랜드 상품.
 */
export function fromMart(bundle: MartBundle, mock: BehaviorMetrics, brandProducts?: Product[]): BehaviorMetrics {
  const src: BehaviorSource = { ...mock.source };
  let out: BehaviorMetrics = { ...mock };

  const ov = hasRows(bundle.overview) ? bundle.overview : null;
  const pr = hasRows(bundle.products) ? bundle.products : null;
  const ct = hasRows(bundle.content) ? bundle.content : null;
  const sg = hasRows(bundle.segments) ? bundle.segments : null;
  const ig = hasRows(bundle.ingredients) ? bundle.ingredients : null;
  const fr = hasRows(bundle.friction) ? bundle.friction : null;
  const pu = hasRows(bundle.purchase) ? bundle.purchase : null;

  // E2 먼저. 개요의 퀵룩 합계와 성분 보유 판정에 상품이 필요하다
  let quickLooks = mock.overview.quickLooks;
  if (pr) {
    const { rows, diagnostics } = toProducts(pr, mock.productMetrics);
    if (rows.length > 0) {
      out = { ...out, productMetrics: rows };
      src.products = 'real';
      src.diagnostics = diagnostics ? 'real' : 'mock';
      quickLooks = rows.reduce((s, r) => s + r.quickLooks, 0);
    }
  }

  // E6 (개요의 이탈률에 quick_exit 를 쓴다)
  let bounce: number | null = null;
  if (fr) {
    const f = toFriction(fr, mock);
    out = {
      ...out,
      frictionByLocation: f.byLocation,
      frictionCounts: f.counts,
      quickExitRate: f.quickExit,
      entryConversion: f.entry,
      eventVolumes: f.volumes,
    };
    src.friction = f.frictionReal ? 'real' : 'mock';
    src.entry = f.entryReal ? 'real' : 'mock';
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
        standardFunnel: [
          { label: '상품 노출', value: ov.funnel.impression_sessions },
          { label: '상품 클릭', value: ov.funnel.click_sessions },
          { label: '상세 조회', value: ov.funnel.product_view_sessions },
          { label: '정보 확인', value: ov.funnel.information_view_sessions },
          { label: '장바구니', value: ov.funnel.add_to_cart_sessions },
        ],
      };
      src.funnel = 'real';
    }
  }

  // E3
  if (ct) {
    const { rows, lift } = toContent(ct, mock.contentAttention);
    if (rows.length > 0) {
      out = { ...out, contentAttention: rows };
      src.content = 'real';
      src.contentLift = lift ? 'real' : 'mock';
    }
    if (ct.behaviors && ct.behaviors.length > 0) {
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
    const s = toSegments(sg, mock.segmentMatrix, mock.segmentTopContent);
    out = {
      ...out,
      segmentByType: s.byType,
      segmentMatrix: s.matrix,
      segmentTopContent: s.top,
      sameSkinFilterRate: s.sameSkin ?? mock.sameSkinFilterRate,
    };
    src.segments = s.byType ? 'real' : 'mock';
    src.grid = s.grid ? 'real' : 'mock';
    src.topContent = s.topReal ? 'real' : 'mock';
  }

  // E5
  if (ig && ig.by_ingredient.length > 0) {
    const ver = ig.by_ingredient[0].vocab_version;
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
