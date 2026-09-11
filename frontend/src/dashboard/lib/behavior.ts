/**
 * 행동 지표 묶음 · 화면이 읽는 단 하나의 모양.
 *
 * 화면은 여기 정의된 `BehaviorMetrics` 만 본다. 값이 어디서 왔는지(마트 API 인지 모의 집계인지)는
 * `source` 가 블록별로 말해 주고, 화면은 그 값을 배지에 그대로 붙인다.
 *
 *   모의  → metrics.ts 의 시드 고정 집계를 이 모양으로 묶는다 (mockBehavior)
 *   마트  → martAdapter.ts 가 API 응답을 이 모양으로 바꾼다. 블록이 없으면 모의 블록을 그대로 둔다
 *
 * 그래서 화면 코드는 마트가 붙기 전과 후가 같다. 바뀌는 것은 배지와 숫자만이다.
 */
import type { Product } from '../../types/product';
import type { EventName } from '../../types/log';
import {
  type ContentAttention,
  type IngredientGapRow,
  type ProductMetrics,
  MINOR_WEIGHT,
  contentAttention as mockContent,
  dailySeries as mockDaily,
  entryConversion as mockEntry,
  eventVolumes as mockEventVolumes,
  frictionByLocation as mockFriction,
  frictionCounts as mockFrictionCounts,
  ingredientGap as mockGap,
  ingredientWeights,
  intentFunnel as mockIntent,
  overview as mockOverview,
  productMetrics as mockProducts,
  products as mockBrandProducts,
  quickExitRate as mockQuickExit,
  sameSkinFilterRate as mockSameSkin,
  scrapedIngredients as mockScraped,
  segmentMatrix as mockMatrix,
  segmentTopContent as mockTopContent,
  standardFunnel as mockFunnel,
  validationBehaviors as mockValidation,
} from './metrics';
import vocab from '../../../../contracts/product-feature-vocab.json';

export type Src = 'real' | 'mock';

export interface Overview {
  sessions: number;
  impressions: number;
  clicks: number;
  detailViews: number;
  quickLooks: number;
  addToCart: number;
  removed: number;
  detailRate: number;
  cartRate: number;
  removalRate: number;
  ingredientViewRate: number;
  reviewViewRate: number;
  /** 정보 확인 도달률. 마트는 information_view_rate, 모의는 성분·리뷰 열람률 평균 */
  infoRate: number;
  /** 마트에 없으면 null. 화면은 하이픈 */
  bounceRate: number | null;
}

export interface DailyPoint {
  label: string;
  visits: number;
  carts: number;
}

export interface FunnelStep {
  label: string;
  value: number;
}

export interface ScrapedIngredient {
  name: string;
  count: number;
  /** 마트(ingredient_weekly_interest)에는 복사 수가 따로 없다 → null */
  copyCount: number | null;
}

export interface ValidationBehavior {
  event: string;
  ko: string;
  doneRate: number;
  cartRateWith: number;
  cartRateWithout: number;
}

export interface SegmentCell {
  tone: string;
  cartRate: number;
  sessions: number;
}

export interface SegmentRowM {
  type: string;
  cells: SegmentCell[];
}

export interface SegmentTop {
  type: string;
  top: string;
  second: string;
  dwellShare: number;
}

/** 격자가 없을 때 KPI 한 칸에 쓰는 단일 축 (persona_segment_daily_kpi skin_type) */
export interface SegmentByType {
  type: string;
  sessions: number;
  cartRate: number;
}

export interface FrictionRow {
  where: string;
  event: string;
  ko: string;
  count: number;
  meaning: string;
}

export interface EntryConversion {
  source: string;
  ko: string;
  sessions: number;
  cartRate: number;
}

/**
 * 재구매 (계약 0.2 E7). **모의값이 없다.** 구매는 실사용자만 만들고(생성기는 안 만든다) 재구매를 흉내 내면
 * 사장님이 진짜로 읽는다. 마트가 없으면 null 이고 화면은 그 자리를 비운다 (5초 규칙: 빈 카드 금지).
 */
export interface Repurchase {
  brand: {
    buyerCount: number;
    repeatBuyerCount: number;
    orderCount: number;
    /** repeat_buyer_count / buyer_count. 분모 0 이면 null */
    rate: number | null;
    medianDays: number | null;
    /** 설문에서 "다시 사려고" 를 고른 주문 수 (선언 재구매) */
    declaredRestockOrders: number;
    windowDays: number;
  } | null;
  /** product_id → 상품 재구매 */
  products: Map<string, { buyerCount: number; repeatBuyerCount: number; rate: number | null }>;
  reasons: Array<{ reason: string | null; orderCount: number; share: number | null }>;
}

/** 블록별 출처. 화면 배지가 이 값을 그대로 쓴다 */
export interface BehaviorSource {
  overview: Src;
  funnel: Src;
  products: Src;
  /** 상품 진단 3열(이탈 지점·옵션 왕복·퀵룩→상세) */
  diagnostics: Src;
  content: Src;
  /** 본 사람의 담기율 배수 (content_conversion_daily) */
  contentLift: Src;
  behaviors: Src;
  scraped: Src;
  /** 고객군 단일 축 */
  segments: Src;
  /** 고객군 4×5 격자 */
  grid: Src;
  topContent: Src;
  friction: Src;
  entry: Src;
  ingredients: Src;
  /** 재구매 (E7). 모의가 없어 'mock' 이면 화면에 자리 자체가 없다 */
  purchase: Src;
}

export interface BehaviorMetrics {
  overview: Overview;
  /** 직전 같은 길이 기간. 마트만 준다 */
  previous: Overview | null;
  daily: DailyPoint[];
  standardFunnel: FunnelStep[];
  productMetrics: ProductMetrics[];
  contentAttention: ContentAttention[];
  scrapedIngredients: ScrapedIngredient[];
  validationBehaviors: ValidationBehavior[];
  segmentMatrix: SegmentRowM[];
  segmentByType: SegmentByType[] | null;
  segmentTopContent: SegmentTop[];
  sameSkinFilterRate: number;
  frictionByLocation: FrictionRow[];
  frictionCounts: { rage_click: number; dead_click: number; scroll_backtrack: number };
  entryConversion: EntryConversion[];
  intentFunnel: Array<{ label: string; ko: string; value: number }>;
  eventVolumes: Array<{ name: EventName; count: number }>;
  quickExitRate: number;
  ingredientGap: IngredientGapRow[];
  /** 성분 갭 표의 셋째 열이 체류(ms)인지 상품 귀속 점수인지 */
  ingredientInterestKind: 'dwell' | 'score';
  /** 재구매. 마트 없으면 null (모의 없음) */
  repurchase: Repurchase | null;
  source: BehaviorSource;
  /** 응답에 쓰인 마트 중 가장 오래된 갱신 시각. 모의면 null */
  martProcessedAt: string | null;
  /** 실제로 채운 화면이 하나라도 있나 */
  anyReal: boolean;
}

export const ALL_MOCK: BehaviorSource = {
  overview: 'mock',
  funnel: 'mock',
  products: 'mock',
  diagnostics: 'mock',
  content: 'mock',
  contentLift: 'mock',
  behaviors: 'mock',
  scraped: 'mock',
  segments: 'mock',
  grid: 'mock',
  topContent: 'mock',
  friction: 'mock',
  entry: 'mock',
  ingredients: 'mock',
  purchase: 'mock',
};

/** 모의 집계를 화면 모양으로 묶는다. 값은 metrics.ts 그대로 */
export function mockBehavior(days: number): BehaviorMetrics {
  return {
    overview: {
      ...mockOverview,
      infoRate: (mockOverview.ingredientViewRate + mockOverview.reviewViewRate) / 2,
      bounceRate: mockOverview.bounceRate,
    },
    previous: null,
    daily: mockDaily(days),
    standardFunnel: mockFunnel,
    productMetrics: mockProducts,
    contentAttention: mockContent,
    scrapedIngredients: mockScraped,
    validationBehaviors: mockValidation,
    segmentMatrix: mockMatrix,
    segmentByType: null,
    segmentTopContent: mockTopContent,
    sameSkinFilterRate: mockSameSkin,
    frictionByLocation: mockFriction,
    frictionCounts: mockFrictionCounts,
    entryConversion: mockEntry,
    intentFunnel: mockIntent,
    eventVolumes: mockEventVolumes,
    quickExitRate: mockQuickExit,
    ingredientGap: mockGap,
    ingredientInterestKind: 'dwell',
    repurchase: null,
    source: ALL_MOCK,
    martProcessedAt: null,
    anyReal: false,
  };
}

/* ---------- 성분 갭 표 · 관심 입력만 바꿔 다시 만든다 ---------- */

interface IngredientSource {
  synonyms: Record<string, string[]>;
}
const SYNONYMS = (vocab as unknown as { ingredient_source: IngredientSource }).ingredient_source.synonyms;

/** 소문자 표기 → 어휘집 표준 키 ("niacinamide" · "Niacinamide" · 동의어 전부 → "Niacinamide") */
const CANONICAL: Map<string, string> = (() => {
  const m = new Map<string, string>();
  for (const [key, syns] of Object.entries(SYNONYMS)) {
    m.set(key.toLowerCase(), key);
    for (const s of syns) m.set(s.toLowerCase(), key);
  }
  return m;
})();

/**
 * 마트가 준 성분 이름을 어휘집 표준 키로. 어휘집(vocab 0.4)의 키는 Title Case 인데 마트 `ingredient` 컬럼의
 * 표기는 ingredient_vocab.csv 에 달려 있어 대소문자·동의어를 관대하게 받는다. 모르는 이름은 null.
 */
export function canonicalIngredient(name: string): string | null {
  return CANONICAL.get(name.trim().toLowerCase()) ?? null;
}

export interface IngredientInterestInput {
  name: string;
  /** 긁기 열 */
  scrapeCount: number;
  /** 셋째 열. 체류 ms 또는 상품 귀속 점수 */
  dwellMs: number;
  /** 순위 산출용. 없으면 scrapeCount·dwellMs 로 만든다 */
  interest?: number;
}

/**
 * 관심 30종 × 내 라인 보유 (실측). metrics.ts 의 ingredientGap 과 같은 규칙이고, 관심 입력만 밖에서 받는다.
 * 어휘집에 없는 성분 이름은 보유 판정을 할 수 없어 표에서 뺀다 (마트 vocab_version 이 다를 때 조용히 틀리는 것보다 낫다).
 */
export function buildIngredientGap(interest: IngredientInterestInput[], brandProducts: Product[] = mockBrandProducts): IngredientGapRow[] {
  const weightsByProduct = brandProducts.map((p) => ({ product: p, weights: ingredientWeights(p) }));
  const rows: IngredientGapRow[] = interest
    .map((i) => ({ ...i, name: canonicalIngredient(i.name) ?? '' }))
    .filter((i) => i.name !== '')
    .map((i) => {
      const owned = weightsByProduct
        .filter(({ weights }) => weights.has(i.name))
        .map(({ product, weights }) => ({ product, weight: weights.get(i.name) ?? 0 }))
        .sort((a, b) => b.weight - a.weight);
      const maxWeight = owned[0]?.weight ?? 0;
      return {
        name: i.name,
        interest: i.interest ?? i.scrapeCount * 100 + i.dwellMs / 100,
        scrapeCount: i.scrapeCount,
        dwellMs: i.dwellMs,
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
}
