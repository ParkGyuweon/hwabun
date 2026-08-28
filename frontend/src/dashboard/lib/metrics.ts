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
import productsData from '../../mocks/products.sample.json';
import reviewsData from '../../mocks/reviews.sample.json';
import { EVENT_WEIGHT } from '../../types/log';
import type { EventName } from '../../types/log';
import type { Product } from '../../types/product';
import type { Review } from '../../types/review';

export const products = productsData as unknown as Product[];
export const reviews = reviewsData as unknown as Review[];

/* ---------- 시드 고정 난수 ---------- */

function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** mulberry32. 같은 시드면 언제나 같은 수열 */
function rng(seed: number): () => number {
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
}

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
 * intent 퍼널 — 이 대시보드의 차별점.
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

/** 주의 성분 유형별 포함 상품 수 (전 상품 실측) */
export const cautionPrevalence = CAUTION_INGREDIENTS.map(({ label, pattern }) => ({
  label,
  count: products.filter((p) => pattern.test(p.ingredients.join(' '))).length,
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
