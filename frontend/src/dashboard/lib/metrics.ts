/**
 * 대시보드 v0.1 집계.
 *
 * 수집 파이프라인(Collector→Kafka→Spark)이 아직 데이터를 흘리기 전이라
 * 두 종류의 값이 섞여 있다. 화면은 이 구분을 배지로 드러낸다.
 *
 * - **실측**: 리뷰 2,000건과 상품 성분 문자열에서 지금 실제로 계산한 값
 * - **모의**: 행동 지표. 상품 특성(리뷰 수·평점)에 비례하도록 시드 고정으로 생성.
 *   집계 API 가 붙으면 이 모듈의 함수 본문만 fetch 로 바꾸면 된다
 *
 * 모의값에 Math.random 을 쓰지 않는다. 새로고침마다 숫자가 바뀌면
 * 화면을 검토하는 사람이 변화의 원인을 찾느라 시간을 버린다.
 */
import vocab from '../../../../contracts/product-feature-vocab.json';
import { products as catalogData } from '../../mocks/products';
import { BEHAVIOR_BRAND, FEEDBACK_BRAND } from './scope';
import reviewsData from '../../mocks/reviews.sample.json';
import { EVENT_WEIGHT } from '../../types/log';
import type { EventName } from '../../types/log';
import type { Product } from '../../types/product';
import type { Review } from '../../types/review';

/**
 * 브랜드 대시보드는 **내 브랜드** 상품만 본다.
 *
 * 스코프는 둘이다 (lib/scope.ts, 결정 A). 행동·리뷰 화면은 BEHAVIOR_BRAND(세포라 카탈로그의
 * 실제 브랜드) 상품을, 피드백·등록은 FEEDBACK_BRAND(SSAFY Beauty) 상품을 본다.
 *
 * 다른 브랜드 상품은 이름·절대치를 보이지 않는다는 데이터 경계
 * (collective-insight-data-boundary.md A층). 플랫폼 전체를 분모로 쓰는 지표
 * (주의 성분 보급률 같은 커먼즈)는 `catalogProducts` 를 쓴다.
 */
export const catalogProducts = catalogData as unknown as Product[];
export const products = catalogProducts.filter((p) => p.brand_name === BEHAVIOR_BRAND);
/** 피드백·등록 화면의 상품 목록 (SSAFY Beauty) */
export const feedbackProducts = catalogProducts.filter((p) => p.brand_name === FEEDBACK_BRAND);
export const reviews = reviewsData as unknown as Review[];

/* ---------- 시드 고정 난수 ---------- */

export function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** mulberry32. 같은 시드면 언제나 같은 수열 */
export function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------- 상품별 행동 지표 (모의) ---------- */

export interface ProductMetrics {
  product: Product;
  impressions: number;
  clicks: number;
  detailViews: number;
  quickLooks: number;
  ingredientViewRate: number;
  reviewViewRate: number;
  addToCart: number;
  removedFromCart: number;
  /** EVENT_WEIGHT 기반 행동 가중 관심도. 대시보드의 '상품별 관심도' 정의다 */
  interestScore: number;

  // ---- 상품 진단 (명세 §2-5). funnel_session_fact · exit_summary · variant_select · quick_look_close 에서 온다. 지금은 모의
  /** 노출→클릭→상세→정보확인→담기 중 브랜드 중앙값 대비 가장 낮은 단계 */
  bottleneck: 'click' | 'detail' | 'info' | 'cart';
  /** 이탈 직전 본 콘텐츠 최빈값 (exit_summary.last_content_kind) */
  exitContent: 'ingredient_list' | 'usage_guide' | 'user_review' | 'similar_products' | 'product_hero' | 'price';
  /** 세션당 variant_select 평균. 3 이상은 마찰 */
  variantSwitches: number;
  /** quick_look_close.close_reason = open_detail 비율 */
  quickLookToDetail: number;
  /** 담기 후 제거 비율 */
  removeRate: number;
  /** 정보 확인(성분 또는 리뷰) 도달 세션 비율 */
  infoRate: number;
}

/** 이탈 지점 → 이유 힌트 (규칙 R-1c·e·h). 단정하지 않는다 */
export const EXIT_HINT: Record<ProductMetrics['exitContent'], { ko: string; hint: string }> = {
  ingredient_list: { ko: '성분 목록', hint: '기피 성분 발견 가능성' },
  usage_guide: { ko: '사용법', hint: '설명 난이도 가능성' },
  user_review: { ko: '리뷰', hint: '부정 리뷰 노출 가능성' },
  similar_products: { ko: '유사 상품', hint: '대체 탐색 가능성' },
  product_hero: { ko: '첫 화면', hint: '목록 카드와 기대 불일치 가능성' },
  price: { ko: '가격', hint: '가격 저항 가능성' },
};

export const STEP_KO: Record<ProductMetrics['bottleneck'], string> = {
  click: '노출 → 클릭',
  detail: '클릭 → 상세',
  info: '상세 → 정보 확인',
  cart: '정보 확인 → 담기',
};

function buildProductMetrics(product: Product): ProductMetrics {
  const rand = rng(hashString(product.product_id));

  /** 실제 인기(리뷰 수)에 비례시키되 로그 스케일로 눌러 상위 쏠림을 줄인다 */
  const popularity = Math.log10((product.review_count ?? 0) + 10) / 6;
  const quality = (product.rating ?? 3.5) / 5;

  const impressions = Math.round(400 + popularity * 4200 + rand() * 300);
  const ctr = 0.05 + popularity * 0.1 + rand() * 0.03;
  const clicks = Math.round(impressions * ctr);
  const detailViews = Math.round(clicks * (0.82 + rand() * 0.12));
  const quickLooks = Math.round(clicks * (0.14 + rand() * 0.1));

  const ingredientViewRate = 0.28 + quality * 0.2 + rand() * 0.18;
  const reviewViewRate = 0.4 + popularity * 0.25 + rand() * 0.15;

  const cartRate = 0.05 + quality * 0.1 + rand() * 0.05;
  const addToCart = Math.round(detailViews * cartRate);
  const removedFromCart = Math.round(addToCart * (0.08 + rand() * 0.14));

  const interestScore =
    clicks * EVENT_WEIGHT.product_click +
    detailViews * EVENT_WEIGHT.page_view +
    quickLooks * EVENT_WEIGHT.quick_look +
    addToCart * EVENT_WEIGHT.add_to_cart +
    removedFromCart * EVENT_WEIGHT.remove_from_cart;

  const infoRate = Math.min(0.95, (ingredientViewRate + reviewViewRate) / 2 + rand() * 0.1);
  const rates = {
    click: ctr / 0.12,
    detail: detailViews / Math.max(1, clicks) / 0.9,
    info: infoRate / 0.6,
    cart: cartRate / 0.12,
  };
  const bottleneck = (Object.keys(rates) as Array<keyof typeof rates>).reduce((a, b) => (rates[a] <= rates[b] ? a : b));
  const exits: ProductMetrics['exitContent'][] = ['ingredient_list', 'usage_guide', 'user_review', 'similar_products', 'product_hero', 'price'];
  const exitContent = exits[Math.floor(rand() * exits.length)];

  return {
    product,
    impressions,
    clicks,
    detailViews,
    quickLooks,
    ingredientViewRate,
    reviewViewRate,
    addToCart,
    removedFromCart,
    interestScore: Math.round(interestScore),
    bottleneck,
    exitContent,
    variantSwitches: Math.round((1 + rand() * 3) * 10) / 10,
    quickLookToDetail: 0.3 + rand() * 0.45,
    removeRate: addToCart === 0 ? 0 : removedFromCart / addToCart,
    infoRate,
  };
}

export const productMetrics: ProductMetrics[] = products
  .map(buildProductMetrics)
  .sort((a, b) => b.interestScore - a.interestScore);

/* ---------- 전체 요약 (모의) ---------- */

const totals = productMetrics.reduce(
  (acc, m) => ({
    impressions: acc.impressions + m.impressions,
    clicks: acc.clicks + m.clicks,
    detailViews: acc.detailViews + m.detailViews,
    quickLooks: acc.quickLooks + m.quickLooks,
    addToCart: acc.addToCart + m.addToCart,
    removed: acc.removed + m.removedFromCart,
  }),
  { impressions: 0, clicks: 0, detailViews: 0, quickLooks: 0, addToCart: 0, removed: 0 },
);

export const overview = {
  sessions: Math.round(totals.detailViews * 0.55),
  ...totals,
  detailRate: totals.clicks === 0 ? 0 : totals.detailViews / totals.impressions,
  cartRate: totals.detailViews === 0 ? 0 : totals.addToCart / totals.detailViews,
  /** 담았다 뺀 비율. remove_from_cart 가 생기면서 잴 수 있게 된 지표다 */
  removalRate: totals.addToCart === 0 ? 0 : totals.removed / totals.addToCart,
  ingredientViewRate:
    productMetrics.reduce((s, m) => s + m.ingredientViewRate * m.detailViews, 0) /
    totals.detailViews,
  reviewViewRate:
    productMetrics.reduce((s, m) => s + m.reviewViewRate * m.detailViews, 0) / totals.detailViews,
  bounceRate: 0.34,
};

/** 일별 추이. 주말 골과 완만한 성장 곡선을 시드 고정으로 만든다 */
export function dailySeries(days: number): Array<{ label: string; visits: number; carts: number }> {
  const rand = rng(20260828);
  const base = overview.sessions / 14;
  const out: Array<{ label: string; visits: number; carts: number }> = [];

  for (let i = 0; i < days; i += 1) {
    const weekday = (i + 3) % 7;
    const weekend = weekday === 5 || weekday === 6 ? 0.72 : 1;
    const growth = 1 + (i / days) * 0.25;
    const visits = Math.round(base * weekend * growth * (0.9 + rand() * 0.2));
    out.push({
      label: `${i + 1}일`,
      visits,
      carts: Math.round(visits * overview.cartRate * (0.85 + rand() * 0.3)),
    });
  }
  return out;
}

/* ---------- 퍼널 (모의) ---------- */

/** 표준 퍼널. 구매는 이 쇼핑몰의 범위 밖이라 장바구니에서 끝난다 */
export const standardFunnel = [
  { label: '상품 노출', value: totals.impressions },
  { label: '상품 클릭', value: totals.clicks },
  { label: '상세 조회', value: totals.detailViews },
  {
    label: '정보 확인',
    value: Math.round(totals.detailViews * ((overview.ingredientViewRate + overview.reviewViewRate) / 2)),
  },
  { label: '장바구니', value: totals.addToCart },
];

/**
 * 가장 크게 새는 구간을 찾아 한 문장으로 만든다.
 *
 * 조사에서 나온 두 가지에 대한 답이다.
 *   - 경영진은 5초 안에 핵심을 파악해야 한다. 5초 테스트는 "무엇을 봤고 다음에
 *     무엇을 할지" 를 묻는데, 지표만 늘어놓은 화면은 그 답을 못 준다.
 *   - 브랜드가 분석 도구에 갖는 최대 불만이 "수집은 되는데 행동으로 안 이어진다" 다.
 *
 * 그래서 화면 맨 위에 지표가 아니라 **문장**을 둔다. 숫자는 그 아래서 근거를 댄다.
 */
export interface Verdict {
  /** 어디가 문제인가 */
  headline: string;
  /** 왜 그렇게 판단했나 */
  reason: string;
  /** 무엇을 하면 되나 */
  action: string;
  /** 이 판단이 몇 건을 보고 나온 것인가 */
  sampleSize: number;
}

export function leakVerdict(): Verdict {
  const steps = standardFunnel;

  // 단계 사이 유지율. 가장 많이 빠지는 구간이 손볼 곳이다
  const drops = steps.slice(1).map((step, index) => {
    const before = steps[index];
    const kept = before.value === 0 ? 0 : step.value / before.value;
    return { from: before.label, to: step.label, kept, lost: before.value - step.value };
  });

  const worst = drops.reduce((a, b) => (a.kept <= b.kept ? a : b));

  const ACTION: Record<string, string> = {
    상품클릭: "목록 카드의 이미지와 제목을 손보세요. 노출은 되는데 눌리지 않습니다.",
    상세조회: "클릭 후 이탈이 많습니다. 첫 화면 로딩과 히어로 영역을 확인하세요.",
    정보확인: "상세까지 왔는데 성분·리뷰를 안 봅니다. 정보 위치를 위로 올리세요.",
    장바구니: "정보까지 봤는데 담지 않습니다. 가격·용량·담기 버튼을 점검하세요.",
  };

  const key = worst.to.replace(/\s/g, '');

  return {
    headline: `${worst.from} → ${worst.to} 구간에서 가장 많이 이탈합니다`,
    reason: `${fmt.int(worst.lost)}명이 이 구간에서 빠졌습니다 (유지율 ${fmt.pct(worst.kept)}).`,
    action: ACTION[key] ?? "이 구간의 화면 구성을 점검하세요.",
    sampleSize: steps[0].value,
  };
}

/**
 * intent 퍼널 · 이 대시보드의 차별점.
 * 이벤트 이름이 아니라 발생 시점에 실린 의미(intent)로 단계를 세므로
 * 이벤트가 늘어나도 퍼널 정의가 흔들리지 않는다.
 */
export const intentFunnel = [
  { label: 'exposure', ko: '노출', value: totals.impressions + Math.round(totals.detailViews * 9.5) },
  { label: 'interest', ko: '열람', value: Math.round(totals.detailViews * 8.2) },
  { label: 'comparison', ko: '비교', value: Math.round(totals.detailViews * 1.9) },
  { label: 'validation', ko: '확인', value: Math.round(totals.detailViews * 1.1) },
  { label: 'conversion', ko: '전환', value: totals.addToCart + Math.round(totals.addToCart * 0.9) },
];

/** 마찰 신호. 어느 단계에서든 새는 구멍이라 퍼널 밖에 따로 둔다 */
export const frictionCounts = {
  rage_click: Math.round(totals.detailViews * 0.013),
  dead_click: Math.round(totals.detailViews * 0.058),
  scroll_backtrack: Math.round(totals.detailViews * 0.31),
};

/** 이벤트별 발생량. 실측 분포(section_dwell 이 압도적)를 반영한 모의값 */
export const eventVolumes: Array<{ name: EventName; count: number }> = (
  [
    ['section_dwell', totals.detailViews * 6.4],
    ['section_view', totals.detailViews * 2.4],
    ['scroll_depth', totals.detailViews * 3.1],
    ['product_impression', totals.impressions],
    ['scroll_pause', totals.detailViews * 1.7],
    ['page_view', totals.detailViews * 1.8],
    ['product_click', totals.clicks],
    ['media_view', totals.detailViews * 0.9],
    ['recommendation_impression', totals.detailViews * 2.2],
    ['quick_look', totals.quickLooks],
    ['add_to_cart', totals.addToCart],
    ['text_selection', totals.detailViews * 0.21],
    ['remove_from_cart', totals.removed],
  ] as Array<[EventName, number]>
)
  .map(([name, count]) => ({ name, count: Math.round(count) }))
  .sort((a, b) => b.count - a.count);

/* ---------- 리뷰 분석 (실측) ---------- */

/** 리뷰 본문에서 찾을 표현. 데이터셋 리뷰가 영문이라 영문 패턴을 쓴다 */
const IRRITATION_PATTERN = /irritat|sting|burn|tingl|itch|sensitiv/i;
const TROUBLE_PATTERN = /break\s?out|breakout|acne|pimple|rash|redness|bumps/i;

const FACTOR_PATTERNS: Array<{ label: string; pattern: RegExp }> = [
  { label: '보습감', pattern: /hydrat|moistur/i },
  { label: '향', pattern: /scent|smell|fragrance/i },
  { label: '발림성·질감', pattern: /texture|apply|absorb|greasy|sticky/i },
  { label: '순함', pattern: /gentle|mild|calm|sooth/i },
  { label: '윤기·톤', pattern: /glow|bright|radian|dewy/i },
  { label: '가성비', pattern: /price|worth|expensive|value/i },
  { label: '지속력', pattern: /last|all day|long/i },
];

export interface ReviewStats {
  sampleSize: number;
  withText: number;
  avgRating: number;
  ratingDist: number[];
  recommendRate: number;
  irritationRate: number;
  troubleRate: number;
  factors: Array<{ label: string; count: number; share: number }>;
}

export function reviewStats(productId: string | null): ReviewStats {
  const scoped = productId ? reviews.filter((r) => r.product_id === productId) : reviews;
  const texts = scoped.filter((r) => r.review_text);

  const ratingDist = [0, 0, 0, 0, 0];
  for (const r of scoped) ratingDist[Math.min(4, Math.max(0, Math.round(r.rating) - 1))] += 1;

  const recommended = scoped.filter((r) => r.is_recommended !== null);

  const factors = FACTOR_PATTERNS.map(({ label, pattern }) => {
    const count = texts.filter((r) => pattern.test(r.review_text as string)).length;
    return { label, count, share: texts.length === 0 ? 0 : count / texts.length };
  }).sort((a, b) => b.count - a.count);

  return {
    sampleSize: scoped.length,
    withText: texts.length,
    avgRating: scoped.length === 0 ? 0 : scoped.reduce((s, r) => s + r.rating, 0) / scoped.length,
    ratingDist,
    recommendRate:
      recommended.length === 0
        ? 0
        : recommended.filter((r) => r.is_recommended).length / recommended.length,
    irritationRate:
      texts.length === 0
        ? 0
        : texts.filter((r) => IRRITATION_PATTERN.test(r.review_text as string)).length /
          texts.length,
    troubleRate:
      texts.length === 0
        ? 0
        : texts.filter((r) => TROUBLE_PATTERN.test(r.review_text as string)).length / texts.length,
    factors,
  };
}

/** 자극·트러블 언급 비율 상위 상품 (실측) */
export const troubleRanking = products
  .map((p) => {
    const stats = reviewStats(p.product_id);
    return {
      product: p,
      irritationRate: stats.irritationRate,
      troubleRate: stats.troubleRate,
      sampleSize: stats.withText,
    };
  })
  .sort((a, b) => b.troubleRate + b.irritationRate - (a.troubleRate + a.irritationRate));

/* ---------- 성분 분석 (실측) ---------- */

/**
 * 주의 깊게 볼 성분. 규제 목록이 아니라 **민감성 피부에서 흔히 확인하는 항목**이다.
 * 위해성 판정이 아니므로 화면에서도 '주의'가 아닌 '확인 필요' 톤으로 쓴다.
 */
const CAUTION_INGREDIENTS: Array<{ label: string; pattern: RegExp }> = [
  { label: '향료 (Fragrance/Parfum)', pattern: /fragrance|parfum/i },
  { label: '변성 알코올', pattern: /alcohol denat|denatured alcohol|sd alcohol/i },
  { label: '에센셜 오일', pattern: /essential oil|lavender oil|peppermint oil|eucalyptus/i },
  { label: '리모넨', pattern: /\blimonene\b/i },
  { label: '리날룰', pattern: /\blinalool\b/i },
  { label: '시트랄·시트로넬롤', pattern: /citral|citronellol|geraniol/i },
  { label: '착색료', pattern: /\bci \d{5}\b|red \d|yellow \d|blue \d/i },
  { label: '페녹시에탄올', pattern: /phenoxyethanol/i },
];

export interface IngredientStats {
  totalCount: number;
  cautions: Array<{ label: string; hit: boolean }>;
  cautionCount: number;
}

export function ingredientStats(product: Product): IngredientStats {
  const joined = product.ingredients.join(' ');
  const cautions = CAUTION_INGREDIENTS.map(({ label, pattern }) => ({
    label,
    hit: pattern.test(joined),
  }));
  return {
    totalCount: joined === '' ? 0 : joined.split(',').length,
    cautions,
    cautionCount: cautions.filter((c) => c.hit).length,
  };
}

/** 주의 성분 유형별 포함 상품 수 (플랫폼 전 상품 실측 · 커먼즈 지표) */
export const cautionPrevalence = CAUTION_INGREDIENTS.map(({ label, pattern }) => ({
  label,
  count: catalogProducts.filter((p) => pattern.test(p.ingredients.join(' '))).length,
})).sort((a, b) => b.count - a.count);

/* ---------- 세그먼트 (리뷰 실측 + 전환 모의) ---------- */

export const skinTypeSegments = (() => {
  const counts = new Map<string, number>();
  for (const r of reviews) if (r.skin_type) counts.set(r.skin_type, (counts.get(r.skin_type) ?? 0) + 1);
  const total = [...counts.values()].reduce((s, n) => s + n, 0);
  const rand = rng(777);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([type, n]) => ({
      type,
      share: n / total,
      cartRate: overview.cartRate * (0.8 + rand() * 0.5),
    }));
})();

/* ---------- 포맷터 ---------- */

export const fmt = {
  int: (n: number) => n.toLocaleString('ko-KR'),
  pct: (n: number, digits = 1) => `${(n * 100).toFixed(digits)}%`,
  compact: (n: number) =>
    n >= 10000 ? `${(n / 10000).toFixed(1)}만` : n >= 1000 ? `${(n / 1000).toFixed(1)}천` : String(n),
};


/* ---------- ③ 정보 관심도 ---------- */

/**
 * 콘텐츠 종류별 주목도.
 *
 * 체류가 길다고 좋은 게 아니라는 것을 함께 보여줘야 한다. 그래서 평균 체류 옆에
 * **전환 기여**(그 콘텐츠를 본 방문의 담기 비율 ÷ 전체 평균)를 나란히 둔다.
 * usage_guide 처럼 오래 보는데 전환이 안 되는 것은 설명이 어렵다는 신호다.
 *
 * 집계 전제: co_visible_blocks <= 2 인 체류만 쓴다. PC 는 한 화면에 블록이
 * 여러 개 들어가서, 겹쳐 보인 체류는 어느 콘텐츠를 향한 것인지 단정할 수 없다.
 */
export interface ContentAttention {
  kind: string;
  ko: string;
  avgDwellMs: number;
  viewRate: number;
  conversionLift: number;
  sampleSize: number;
}

export const contentAttention: ContentAttention[] = (() => {
  const rand = rng(hashString('content-attention'));
  const base: Array<[string, string, number, number, number]> = [
    // [kind, 한국어, 평균 체류 ms, 열람률, 전환 기여]
    ['ingredient_list', '성분 목록', 38200, 0.62, 2.3],
    ['user_review', '사용자 리뷰', 31400, 0.71, 1.8],
    ['clinical_claim', '임상 결과', 22300, 0.34, 2.1],
    ['ingredient_callout', '성분 특징', 15800, 0.41, 1.6],
    ['what_it_is', '제품 소개', 12900, 0.88, 1.0],
    ['usage_guide', '사용법', 12100, 0.37, 0.9],
    ['brand_story', '브랜드 소개', 9800, 0.22, 1.2],
    ['review_stats', '평점 분포', 8400, 0.66, 1.1],
    ['what_else', '추가 설명', 7600, 0.28, 0.8],
    ['product_image', '상품 이미지', 6900, 0.94, 1.0],
  ];
  return base.map(([kind, ko, avgDwellMs, viewRate, conversionLift]) => ({
    kind,
    ko,
    avgDwellMs,
    viewRate,
    conversionLift,
    sampleSize: Math.round(400 + rand() * 900),
  }));
})();

/**
 * 긁어간 성분 빈도.
 *
 * 원문은 로그에 남지 않는다(데이터 계약). 성분 사전에 걸린 표준 명칭만 온다.
 * 사전은 contracts/product-feature-vocab.json · AI 파트가 상품 벡터에 쓰는 것과
 * 같은 파일이라 "이 성분을 긁은 사람" 과 "이 성분이 든 상품" 이 같은 이름으로
 * 조인된다. 여기서도 그 사전을 그대로 읽어 화면과 로그의 성분 목록이 어긋나지
 * 않게 한다.
 *
 * 반복해서 드래그되는 성분 = 사용자가 가장 관심을 두는 성분. 드래그 자체는 관심의 크기다.
 * "설명이 어렵다" 는 별개의 판단이라 같은 성분 구간의 되돌아 읽기·이탈·담기율을 함께 봐야 하고,
 * 그 조합은 세션 단위 조인이 필요해 데이터 마트(ingredient_interest_kpi 제안)에서 만든다.
 */
export const scrapedIngredients: Array<{ name: string; count: number; copyCount: number }> =
  (() => {
    const rand = rng(hashString('scraped-ingredients'));
    return Object.keys(vocab.ingredient_source.synonyms)
      .map((name) => {
        const count = Math.round(8 + rand() * 190);
        return { name, count, copyCount: Math.round(count * (0.15 + rand() * 0.3)) };
      })
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  })();

/**
 * 검증 행동 실행률과 전환 비교.
 * "그 행동을 한 방문" 과 "안 한 방문" 의 담기 비율을 나란히 두면
 * 어떤 정보가 결정을 만드는지가 바로 보인다.
 */
export const validationBehaviors = [
  {
    event: 'ingredient_view_mode_change',
    ko: '전성분 펼쳐 보기',
    doneRate: 0.18,
    cartRateWith: 0.132,
    cartRateWithout: 0.051,
  },
  {
    event: 'review_filter_apply',
    ko: '내 피부 타입 리뷰만 보기',
    doneRate: 0.11,
    cartRateWith: 0.148,
    cartRateWithout: 0.056,
  },
  {
    event: 'accordion_toggle',
    ko: '접힌 정보 펼치기',
    doneRate: 0.42,
    cartRateWith: 0.094,
    cartRateWithout: 0.049,
  },
  {
    event: 'text_copy',
    ko: '성분명 복사',
    doneRate: 0.06,
    cartRateWith: 0.087,
    cartRateWithout: 0.061,
  },
];

/* ---------- ④ 고객군 ---------- */

export const SKIN_TYPE_KO: Record<string, string> = {
  dry: '건성',
  oily: '지성',
  combination: '복합성',
  normal: '중성',
};

export const SKIN_TONE_ORDER = ['fair', 'light', 'medium', 'tan', 'deep'] as const;

/**
 * 피부 타입 × 톤 전환 매트릭스.
 *
 * 페르소나 100명이 타입 4종 × 톤 5종으로 정확히 균등이라(칸마다 5명)
 * 어느 조합을 골라도 비교가 성립한다. 균등이 아니었으면 칸마다 표본 수부터
 * 보정해야 했다.
 */
export const segmentMatrix = (() => {
  const rand = rng(hashString('segment-matrix'));
  const types = ['dry', 'oily', 'combination', 'normal'];
  return types.map((type) => ({
    type,
    cells: SKIN_TONE_ORDER.map((tone) => ({
      tone,
      cartRate: 0.04 + rand() * 0.11,
      sessions: Math.round(60 + rand() * 200),
    })),
  }));
})();

/**
 * 고객군별로 가장 오래 본 콘텐츠.
 * "건성은 성분을, 지성은 임상 근거를 오래 본다" 가 데이터로 나오면
 * 그것이 바로 브랜드에 파는 인사이트다.
 */
export const segmentTopContent = [
  { type: 'dry', top: '성분 목록', second: '사용자 리뷰', dwellShare: 0.34 },
  { type: 'oily', top: '임상 결과', second: '성분 목록', dwellShare: 0.29 },
  { type: 'combination', top: '사용자 리뷰', second: '성분 목록', dwellShare: 0.31 },
  { type: 'normal', top: '상품 이미지', second: '사용자 리뷰', dwellShare: 0.26 },
];

/** 리뷰 필터에서 "나와 같은 피부 타입" 을 고른 방문 비율 */
export const sameSkinFilterRate = 0.63;

/* ---------- ⑤ 마찰 위치 ---------- */

/**
 * 좌절 신호를 위치와 함께 본다.
 * dead_click 이 상품 이미지에 몰리면 확대를 기대했는데 안 되는 것이고,
 * scroll_backtrack 이 성분에 몰리면 그 구간 설명이 어렵다는 뜻이다.
 * 상품 선호와 UI 품질은 같은 축이 아니라서 여기 값은 선호 벡터에 넣지 않는다.
 */
export const frictionByLocation = [
  { where: '상품 이미지', event: 'dead_click', count: 412, meaning: '확대 기대 · 줌 없음' },
  { where: '성분 목록', event: 'scroll_backtrack', count: 388, meaning: '되돌아 읽기 · 설명 난이도' },
  { where: '옵션 선택', event: 'rage_click', count: 214, meaning: '품절 옵션 반응 없음' },
  { where: '리뷰 더보기', event: 'dead_click', count: 156, meaning: '버튼처럼 보이는 비버튼' },
  { where: '담기 버튼', event: 'hover_dwell', count: 1893, meaning: '평균 2.4초 망설임' },
];

/* ---------- ④ 성분 갭 (명세 I1·I2) ---------- */

interface IngredientSource {
  synonyms: Record<string, string[]>;
  position_formula: string;
  position_min: number;
}

const INGREDIENT_SOURCE = (vocab as unknown as { ingredient_source: IngredientSource }).ingredient_source;
const POS_MIN = INGREDIENT_SOURCE.position_min ?? 0.1;
/** 태그 성분이 전성분 앞 30% 안에 없으면 "미량". 명세 I2 */
export const MINOR_WEIGHT = 0.3;

const splitFull = (p: Product): string[] =>
  p.ingredients
    .flatMap((block) => block.split(','))
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

/**
 * 성분 30종의 위치가중. 전성분에서 처음 나오는 자리로 `max(1 - 위치/전체, 0.1)` (어휘집 position_formula).
 * 태그(highlights)에 있으면 1.0 · AI 파트 상품 벡터와 같은 규칙이라 "긁은 성분" 과 "든 성분" 이 같은 이름으로 만난다.
 */
export function ingredientWeights(p: Product): Map<string, number> {
  const parts = splitFull(p);
  const tags = new Set(p.highlights.map((h) => h.toLowerCase()));
  const out = new Map<string, number>();
  for (const [name, syns] of Object.entries(INGREDIENT_SOURCE.synonyms)) {
    if (tags.has(name.toLowerCase())) {
      out.set(name, 1);
      continue;
    }
    const lowered = syns.map((s) => s.toLowerCase());
    const idx = parts.findIndex((part) => lowered.some((s) => part.includes(s)));
    if (idx >= 0 && parts.length > 0) out.set(name, Math.max(1 - idx / parts.length, POS_MIN));
  }
  return out;
}

export interface IngredientGapRow {
  name: string;
  /** 관심 = 긁기 + 체류 (모의). 순위 산출에만 쓴다 */
  interest: number;
  scrapeCount: number;
  dwellMs: number;
  /** 내 라인에서 이 성분이 든 상품 (실측) */
  owned: Array<{ product: Product; weight: number }>;
  maxWeight: number;
  rank: number;
  /** 관심 상위 10 & 미보유 */
  gap: boolean;
  /** 보유하지만 전부 미량(위치가중 ≤ 0.3) */
  minor: boolean;
}

/**
 * 성분 갭 표. 관심(모의) 순으로 30행, 갭 행이 위로 올라온다.
 * 관심은 수집 연결 전이라 시드 고정 모의값이고, 보유·위치가중은 내 상품 전성분에서 실측.
 */
export const ingredientGap: IngredientGapRow[] = (() => {
  const rand = rng(hashString('ingredient-interest'));
  const weightsByProduct = products.map((p) => ({ product: p, weights: ingredientWeights(p) }));
  const rows = Object.keys(INGREDIENT_SOURCE.synonyms).map((name) => {
    const scrapeCount = Math.round(8 + rand() * 190);
    const dwellMs = Math.round(4000 + rand() * 30000);
    const owned = weightsByProduct
      .filter(({ weights }) => weights.has(name))
      .map(({ product, weights }) => ({ product, weight: weights.get(name) ?? 0 }))
      .sort((a, b) => b.weight - a.weight);
    const maxWeight = owned[0]?.weight ?? 0;
    return {
      name,
      interest: scrapeCount * 100 + dwellMs / 100,
      scrapeCount,
      dwellMs,
      owned,
      maxWeight,
      rank: 0,
      gap: false,
      minor: owned.length > 0 && maxWeight <= MINOR_WEIGHT,
    };
  });
  rows.sort((a, b) => b.interest - a.interest);
  rows.forEach((r, i) => {
    r.rank = i + 1;
    r.gap = i < 10 && r.owned.length === 0;
  });
  return rows.sort((a, b) => Number(b.gap) - Number(a.gap) || a.rank - b.rank);
})();


/* ---------- 리뷰 × 리뷰어 피부 타입 (실측) ---------- */

export interface SkinReviewRow {
  type: string;
  n: number;
  avgRating: number;
  irritationRate: number;
}

/**
 * 피부 타입별 평점·자극 언급. 리뷰어 skin_type 은 원천에 있어 전부 실측이다.
 * 같은 상품이 건성 4.6 / 지성 3.4 처럼 갈리면 타깃 문구를 갈라 쓸 근거다 (명세 R1·R2).
 */
export function reviewsBySkinType(productId: string | null): SkinReviewRow[] {
  const scoped = productId ? reviews.filter((r) => r.product_id === productId) : reviews.filter((r) => products.some((p) => p.product_id === r.product_id));
  return ['dry', 'oily', 'combination', 'normal'].map((type) => {
    const rows = scoped.filter((r) => r.skin_type === type);
    const texts = rows.filter((r) => r.review_text);
    return {
      type,
      n: rows.length,
      avgRating: rows.length === 0 ? 0 : rows.reduce((s, r) => s + r.rating, 0) / rows.length,
      irritationRate: texts.length === 0 ? 0 : texts.filter((r) => IRRITATION_PATTERN.test(r.review_text as string)).length / texts.length,
    };
  });
}

/* ---------- 행동·마찰 보조 (모의) ---------- */

/** 진입 경로별 상세→담기 전환 (entry_source). 추천 진입 lift 가 이 표의 답이다 */
export const entryConversion = [
  { source: 'similar_products', ko: '유사 상품 추천', sessions: Math.round(totals.detailViews * 0.18), cartRate: overview.cartRate * 1.8 },
  { source: 'promo_pick', ko: '맞춤 기획전', sessions: Math.round(totals.detailViews * 0.14), cartRate: overview.cartRate * 1.5 },
  { source: 'list_grid', ko: '목록', sessions: Math.round(totals.detailViews * 0.58), cartRate: overview.cartRate * 0.9 },
  { source: 'quick_look', ko: '퀵룩에서', sessions: Math.round(totals.detailViews * 0.1), cartRate: overview.cartRate * 1.1 },
];

/** 3초 안에 나간 상세 방문 비율 (exit_summary dwell). 40% 초과면 첫 화면 기대 불일치 */
export const quickExitRate = 0.29;
