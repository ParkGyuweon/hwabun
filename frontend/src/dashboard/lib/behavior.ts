/**
 * 행동 지표 묶음 · 화면이 읽는 단 하나의 모양.
 *
 * 화면은 여기 정의된 `BehaviorMetrics` 만 본다. 값이 어디서 왔는지는 `source` 가 블록별로 말해 주고,
 * 화면은 그 값을 배지에 그대로 붙인다.
 *
 *   마트 응답 있음 → martAdapter.ts 가 이 모양으로 바꾼다. 배지 '실측'
 *   없음           → `emptyBehavior` 의 0·빈 표 그대로. 배지 '없음'
 *
 * **지어낸 값을 끼워 넣지 않는다.** 예전에는 마트가 없으면 metrics.ts 의 시드 고정 집계로 화면을 채웠는데,
 * 사장님은 그 숫자를 자기 브랜드 값으로 읽는다. 없는 것은 없다고 적는 편이 언제나 낫다.
 */
import type { Product } from '../../types/product';
import type { EventName } from '../../types/log';
import {
  type ContentAttention,
  type IngredientGapRow,
  type ProductMetrics,
  MINOR_WEIGHT,
  ingredientWeights,
} from './metrics';
import vocab from '../../../../contracts/product-feature-vocab.json';

export type Src = 'real' | 'none';

/**
 * 행동 이름 → 사장님이 읽는 한국어. "행동별 기록 건수" 목록이 쓴다.
 * 데이터 파트와 맞춘 영문 이름은 화면에 그대로 내지 않는다.
 */
export const EVENT_KO: Record<EventName, string> = {
  login: '로그인',
  session_start: '방문 시작',
  page_view: '화면 열기',
  product_view: '상품 상세 보기',
  product_impression: '상품이 화면에 보임',
  navigation_click: '메뉴 이동',
  product_click: '상품 누르기',
  section_view: '글 구간이 화면에 보임',
  section_dwell: '글 구간에 머묾',
  accordion_toggle: '접힌 정보 펼치기',
  recommendation_impression: '추천 상품이 보임',
  recommendation_click: '추천 상품 누르기',
  banner_impression: '배너가 보임',
  banner_click: '배너 누르기',
  wishlist_toggle: '찜하기',
  add_to_cart: '장바구니 담기',
  view_cart: '장바구니 보기',
  begin_checkout: '결제 시작',
  purchase: '구매',
  purchase_reason_select: '구매 이유 고르기',
  payment_failed: '결제 실패·취소',
  exit_summary: '나가기 전 마지막 화면',
  scroll_depth: '얼마나 내려 읽었나',
  impression_dwell: '상품 카드가 보인 시간',
  recommendation_snapshot: '추천 순서 기록',
  media_view: '사진·영상 보기',
  quick_look: '빠른 보기 열기',
  quick_look_close: '빠른 보기 닫기',
  remove_from_cart: '장바구니에서 빼기',
  variant_select: '옵션 고르기',
  quantity_change: '수량 바꾸기',
  review_filter_apply: '리뷰 걸러 보기',
  review_expand: '리뷰 더 보기',
  ingredient_view_mode_change: '전성분 펼쳐 보기',
  sort_change: '정렬 바꾸기',
  filter_change: '조건으로 좁히기',
  scroll_pause: '읽다가 멈춤',
  scroll_backtrack: '위로 되돌아가 다시 읽음',
  text_selection: '글자 긁기',
  text_copy: '글자 복사',
  hover_dwell: '누르기 전 머뭇거림',
  rage_click: '연달아 누름',
  dead_click: '눌러도 반응 없음',
};

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
  /**
   * 성분·리뷰까지 확인한 방문 수. 분모는 **상품 상세를 연 방문**(`sessions`)이다 — 퀵룩에는 성분·리뷰가 없어서
   * 볼 기회 자체가 없다. 그래서 이 값은 구매 단계 퍼널에 넣지 않고 옆에 따로 적는다 (데이터 파트 2026-09-22).
   */
  infoViews: number;
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

/**
 * 가격대 한 줄 (E4 `price_bands`, brand_price_band_daily_kpi). `bin` 이 null 이면 가격이 없는 상품들의 반응이다 —
 * 빼면 그 상품들의 반응을 볼 수 없어 행으로 남긴다. 축을 걷어낸 합계는 고객군 합계와 같지 않다 (계약 §3 E4).
 */
export interface PriceBandM {
  bin: string | null;
  productCount: number;
  /** 상세를 본 방문. 칸을 비우고 흐리는 기준 */
  sessions: number;
  cartSessions: number;
  purchaseSessions: number;
  detailEntryRate: number | null;
  cartRate: number | null;
  purchaseRate: number | null;
}

/** 피부 타입 × 가격대 (E4 `segment_price_grid`, S5 히트맵). 마트는 표본 미달 칸을 지우지 않는다 — 화면이 50 미만 비움·200 미만 흐림 */
export interface SegmentPriceRowM {
  type: string;
  cells: Array<{ bin: string | null; sessions: number; cartRate: number }>;
}

/**
 * 비슷한 브랜드 묶음(코호트) 속 내 위치 (E4 `cohort`, commons_cohort_weekly). 다른 브랜드를 식별할 값은 없다.
 * `suppressed` 면 분위 셋이 null 이고 화면은 "표본 부족" 만 적는다. 블록이 없으면(null) 배지 자체를 그리지 않는다 — 모의 금지.
 */
export interface CohortM {
  key: string;
  /** 상품 수 구간 ("2-3") */
  productBand: string;
  /** 주력 가격대 (price_bin) */
  priceBin: string | null;
  weekStart: string;
  weekEnd: string;
  brandCount: number;
  suppressed: boolean;
  sampleSufficient: boolean;
  metrics: Array<{
    name: string;
    p25: number | null;
    p50: number | null;
    p75: number | null;
    mine: number | null;
    position: 'below_p25' | 'p25_p50' | 'p50_p75' | 'above_p75' | null;
  }>;
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
  /** 가격대별 반응 (E4 price_bands) */
  priceBands: Src;
  /** 피부 타입 × 가격대 (E4 segment_price_grid) */
  segmentPriceGrid: Src;
  friction: Src;
  entry: Src;
  ingredients: Src;
  /** 재구매 (E7). 'none' 이면 화면에 자리 자체가 없다 */
  purchase: Src;
}

export interface BehaviorMetrics {
  overview: Overview;
  /** 직전 같은 길이 기간. 마트만 준다 */
  previous: Overview | null;
  daily: DailyPoint[];
  standardFunnel: FunnelStep[];
  /**
   * 퍼널 밖에 적는 진입 경로 한 줄 (은솔님 2026-09-22). 클릭과 퀵룩은 병렬 경로라 퍼널 칸으로 두면 100% 를 넘는다.
   * 대신 "노출 중 몇 %가 상품을 눌렀나" 와 "상세를 연 세션이 퀵룩·상품 상세 중 어느 쪽인가" 를 따로 적는다. 마트가 없으면 null
   */
  funnelNote: {
    impressionSessions: number;
    clickSessions: number;
    detailSessions: number;
    productViewSessions: number;
    quickLookSessions: number | null;
  } | null;
  productMetrics: ProductMetrics[];
  contentAttention: ContentAttention[];
  scrapedIngredients: ScrapedIngredient[];
  validationBehaviors: ValidationBehavior[];
  segmentMatrix: SegmentRowM[];
  segmentByType: SegmentByType[] | null;
  segmentTopContent: SegmentTop[];
  sameSkinFilterRate: number;
  /** 가격대별 반응. 마트 없으면 빈 배열 (모의 없음) */
  priceBands: PriceBandM[];
  /** 피부 타입 × 가격대. 마트 없으면 빈 배열 (모의 없음) */
  segmentPriceGrid: SegmentPriceRowM[];
  /** 비슷한 브랜드 대비 내 위치. 마트 없으면 null — 배지를 그리지 않는다 */
  cohort: CohortM | null;
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

export const ALL_NONE: BehaviorSource = {
  overview: 'none',
  funnel: 'none',
  products: 'none',
  diagnostics: 'none',
  content: 'none',
  contentLift: 'none',
  behaviors: 'none',
  scraped: 'none',
  segments: 'none',
  grid: 'none',
  topContent: 'none',
  priceBands: 'none',
  segmentPriceGrid: 'none',
  friction: 'none',
  entry: 'none',
  ingredients: 'none',
  purchase: 'none',
};

/**
 * 마트가 답하지 않았을 때의 묶음. 전부 0 과 빈 표다.
 *
 * `days` 를 받지만 일별 추이는 빈 배열이다 — 없는 날짜를 0 으로 채워 그리면 "방문이 0 이었던 날" 처럼 보인다.
 * 모르는 것과 0 인 것은 다르고, 여기서는 모르는 쪽이다. 화면은 빈 그래프에 "아직 데이터가 없습니다" 를 적는다.
 */
export function emptyBehavior(): BehaviorMetrics {
  return {
    overview: {
      sessions: 0,
      impressions: 0,
      clicks: 0,
      detailViews: 0,
      quickLooks: 0,
      addToCart: 0,
      removed: 0,
      detailRate: 0,
      cartRate: 0,
      removalRate: 0,
      ingredientViewRate: 0,
      reviewViewRate: 0,
      infoRate: 0,
      infoViews: 0,
      bounceRate: null,
    },
    previous: null,
    daily: [],
    standardFunnel: [],
    funnelNote: null,
    productMetrics: [],
    contentAttention: [],
    scrapedIngredients: [],
    validationBehaviors: [],
    segmentMatrix: [],
    segmentByType: null,
    segmentTopContent: [],
    sameSkinFilterRate: 0,
    priceBands: [],
    segmentPriceGrid: [],
    cohort: null,
    frictionByLocation: [],
    frictionCounts: { rage_click: 0, dead_click: 0, scroll_backtrack: 0 },
    entryConversion: [],
    intentFunnel: [],
    eventVolumes: [],
    quickExitRate: 0,
    ingredientGap: [],
    ingredientInterestKind: 'score',
    repurchase: null,
    source: ALL_NONE,
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
// 내 라인 상품은 **호출부가 준다**. 기본값으로 고정 브랜드 목록을 두면 남의 상품으로 보유 판정이 된다
export function buildIngredientGap(interest: IngredientInterestInput[], brandProducts: Product[]): IngredientGapRow[] {
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
