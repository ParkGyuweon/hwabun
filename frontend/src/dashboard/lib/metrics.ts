/**
 * 대시보드 v0.1 집계.
 *
 * 수집 파이프라인(Collector→Kafka→Spark)이 아직 데이터를 흘리기 전이라
 * 두 종류의 값이 섞여 있다. 화면은 이 구분을 배지로 드러낸다.
 *
 * - **실측**: 리뷰 표본(상품당 100건)과 상품 성분 문자열에서 지금 실제로 계산한 값
 * - **모의**: 행동 지표. 상품 특성(리뷰 수·평점)에 비례하도록 시드 고정으로 생성.
 *   집계 API 가 붙으면 이 모듈의 함수 본문만 fetch 로 바꾸면 된다
 *
 * 모의값에 Math.random 을 쓰지 않는다. 새로고침마다 숫자가 바뀌면
 * 화면을 검토하는 사람이 변화의 원인을 찾느라 시간을 버린다.
 */
import vocab from '../../../../contracts/product-feature-vocab.json';
import { products as catalogData } from '../../mocks/products';
import type { Product, SkinType } from '../../types/product';
import { splitIngredients } from '../../lib/format';

/**
 * 브랜드 대시보드는 **내 브랜드** 상품만 본다.
 *
 * 이 모듈은 이제 **고정 브랜드 상품 목록을 내보내지 않는다**. 내 상품은 화면이
 * `useBrandProducts(brandId, brandName)` 로 받는다. 피드백·등록도 마찬가지다 (2026-09-18, FEEDBACK_BRAND 삭제).
 *
 * 다른 브랜드 상품은 이름·절대치를 보이지 않는다는 데이터 경계
 * (collective-insight-data-boundary.md A층). 플랫폼 전체를 분모로 쓰는 지표
 * (주의 성분 보급률 같은 커먼즈)는 `catalogProducts` 를 쓴다.
 */
export const catalogProducts = catalogData as unknown as Product[];
/**
 * 대시보드 리뷰 집계가 읽는 행. 판매자 리뷰 API(`GET /api/seller/reviews?brandId=`, sellerReviewsApi.ts)의 응답을
 * 이 다섯 필드로 줄인 것이다. 번들 표본은 더 이상 없다 — 로그인한 브랜드의 실제 리뷰만 센다.
 * 본문은 영어·한국어가 섞일 수 있다. 키워드 패턴은 영어라 한국어 본문은 0 으로 잡힌다 (화면에 근사치라고 적는다).
 * `skin_type` 은 백엔드가 모르면 null 이고, 전부 null 이면 화면이 피부타입별 표를 숨긴다.
 */
export interface DashboardReview {
  product_id: string;
  rating: number;
  is_recommended: boolean | null;
  review_text: string | null;
  skin_type: SkinType | null;
}

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
  /**
   * 상세를 본 **세션 수** (detail_view_sessions). 문턱(200)과 담기 비율의 분모가 이것이다 (계약 §4.1).
   * 2026-09-21 까지는 Event 건수(product_view_count)를 넣어서, 8개 상품 전부 세션은 500~768 인데 건수는 200 을 못 넘어
   * 상품 화면 네 칸이 한꺼번에 비었다 (규원님 실측).
   */
  detailViews: number;
  /** 상세를 본 세션 중 장바구니에 담은 세션 비율. 서버 view_to_cart_rate, 없으면 세션끼리 나눈 값 */
  cartRate: number;
  quickLooks: number;
  ingredientViewRate: number;
  reviewViewRate: number;
  addToCart: number;
  removedFromCart: number;
  /** EVENT_WEIGHT 기반 행동 가중 관심도. 대시보드의 '상품별 관심도' 정의다 */
  interestScore: number;

  // ---- 상품 진단 (명세 §2-5). product_exit_daily · product_daily_kpi 에서 온다. **마트가 안 주면 null 이다**
  /** 노출→클릭→상세→정보확인→담기 중 브랜드 중앙값 대비 가장 낮은 단계 */
  bottleneck: 'click' | 'detail' | 'info' | 'cart';
  /** 이탈 직전 본 콘텐츠 최빈값 (product_exit_daily). 마트가 없으면 null — 화면은 하이픈 */
  exitContent: 'ingredient_list' | 'usage_guide' | 'user_review' | 'similar_products' | 'product_hero' | 'price' | null;
  /** 세션당 variant_select 평균. 3 이상은 마찰. 마트가 없으면 null */
  variantSwitches: number | null;
  /** quick_look_close.close_reason = open_detail 비율. 마트가 없으면 null */
  quickLookToDetail: number | null;
  /** 담기 후 제거 비율 */
  removeRate: number;
  /** 정보 확인(성분 또는 리뷰) 도달 세션 비율 */
  infoRate: number;
}

/** 이탈 지점 → 이유 힌트 (규칙 R-1c·e·h). 단정하지 않는다 */
export const EXIT_HINT: Record<NonNullable<ProductMetrics['exitContent']>, { ko: string; hint: string }> = {
  ingredient_list: { ko: '성분 목록', hint: '피하는 성분을 봤을 수 있습니다' },
  usage_guide: { ko: '사용법', hint: '설명이 어려웠을 수 있습니다' },
  user_review: { ko: '리뷰', hint: '안 좋은 리뷰를 봤을 수 있습니다' },
  similar_products: { ko: '유사 상품', hint: '다른 상품과 비교하러 갔을 수 있습니다' },
  product_hero: { ko: '첫 화면', hint: '목록에서 기대한 것과 달랐을 수 있습니다' },
  price: { ko: '가격', hint: '가격이 부담됐을 수 있습니다' },
};

export const STEP_KO: Record<ProductMetrics['bottleneck'], string> = {
  click: '보이고 → 누르기',
  detail: '누르고 → 상세 보기',
  info: '상세 → 성분·리뷰 확인',
  cart: '성분·리뷰 확인 → 담기',
};

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

function scopeReviews(reviews: DashboardReview[], productId: string | null, mine: Product[]): DashboardReview[] {
  const ids = new Set(mine.map((p) => p.product_id));
  if (productId) return ids.has(productId) ? reviews.filter((r) => r.product_id === productId) : [];
  return reviews.filter((r) => ids.has(r.product_id));
}

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

/**
 * 내 상품(`mine`)의 리뷰만 센다. 고른 상품이 있으면 그 하나, 없으면 내 상품 전체다.
 * 고른 id 가 내 상품이 아니면(화면을 오가며 남은 값) 빈 집계다 — 남의 상품 리뷰를 내 것으로 보이지 않는다.
 */
export function reviewStats(reviews: DashboardReview[], productId: string | null, mine: Product[]): ReviewStats {
  const scoped = scopeReviews(reviews, productId, mine);
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

/** 내 상품 중 자극·트러블 언급 비율 상위 (실측) */
export const troubleRanking = (reviews: DashboardReview[], mine: Product[]) => mine
  .map((p) => {
    const stats = reviewStats(reviews, p.product_id, mine);
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
    totalCount: splitIngredients(product.ingredients).length,
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

/**
 * 가격 구간. 정본은 contracts/product-feature-vocab.json 의 price_bin_edges (어휘집 0.7, 원화 5구간, 반열린 [하한, 상한)).
 * 마트의 `price_bin` 문자열을 사장님이 읽는 원화 표기로 바꾼다. 순서도 여기서 정한다.
 */
export const PRICE_BIN_ORDER = ['~26k', '26k-46k', '46k-66k', '66k-105k', '105k+'] as const;
export const PRICE_BIN_KO: Record<string, string> = {
  '~26k': '2.6만원 미만',
  '26k-46k': '2.6~4.6만원',
  '46k-66k': '4.6~6.6만원',
  '66k-105k': '6.6~10.5만원',
  '105k+': '10.5만원 이상',
};
/** null 구간 = 가격이 등록되지 않은 상품들 */
export const priceBinKo = (bin: string | null) => (bin === null ? '가격 미입력' : PRICE_BIN_KO[bin] ?? bin);

export const SKIN_TYPE_KO: Record<string, string> = {
  dry: '건성',
  oily: '지성',
  combination: '복합성',
  normal: '중성',
};

export const SKIN_TONE_ORDER = ['fair', 'light', 'medium', 'tan', 'deep'] as const;

interface IngredientSource {
  synonyms: Record<string, string[]>;
  position_formula: string;
  position_min: number;
}

const INGREDIENT_SOURCE = (vocab as unknown as { ingredient_source: IngredientSource }).ingredient_source;
const POS_MIN = INGREDIENT_SOURCE.position_min ?? 0.1;
/** 태그 성분이 전성분 앞 30% 안에 없으면 "미량". 명세 I2 */
export const MINOR_WEIGHT = 0.3;

// 화면(IngredientsSection)과 같은 구분 규칙. `1,2-Hexanediol` 을 둘로 자르면 위치가중의 분모가 늘어 뒤 성분이 전부 밀린다
const splitFull = (p: Product): string[] => splitIngredients(p.ingredients).map((s) => s.toLowerCase());

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
export function reviewsBySkinType(reviews: DashboardReview[], productId: string | null, mine: Product[]): SkinReviewRow[] {
  const scoped = scopeReviews(reviews, productId, mine);
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

/* ---------- 막히는 곳 보조 (모의) ---------- */
