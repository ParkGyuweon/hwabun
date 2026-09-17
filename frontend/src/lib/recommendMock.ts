/**
 * 추천 API 목 — 계약 §5-1 응답을 **프론트에서** 만든다.
 *
 * 백엔드 `RankingService` 가 아직 없다. 형태를 먼저 확정해 화면을 붙이고, 서빙이 생기면
 * 서버 연결은 hooks/useRecommendation + lib/recommendApi 가 한다 (2026-09-11). 이 목은 서버가 없거나
 * 식별자가 없을 때(비로그인)의 대체이고, 서버 응답과 같은 모양을 유지해야 한다.
 * 화면·로그·타입은 그대로다.
 *
 * 점수는 설명 가능한 두 축만 쓴다 (기존 `skin_match_v0` 와 같다):
 *   피부 타입 일치 +2 (원본 표기 우선, 없으면 리뷰어 분포)
 *   품질 사전확률: 평점(0~1) + 리뷰 수 로그 스케일(0~1)
 * 정확도 장치가 아니다. AI 측정에서 축 배너는 +0.5%p 로 노이즈 수준이고, 배너의 값은
 * "이유를 말해 주는 것" 과 "신규 브랜드에 자리를 주는 것" 이다.
 */
import vocab from '../../../contracts/product-feature-vocab.json';
import { DEFAULT_HERO } from './bannerConfig';
import { isNewRegistered } from './newBrandRule';
import { CLEAN_VALUES } from './vocabLabels';
import { toKrw } from './localize';
import type { BannerType } from '../types/log';
import type { PersonaProfile } from '../types/persona';
import type { Product, SkinType } from '../types/product';
import type { HeroPolicy, RecommendBanner, RecommendResponse } from '../types/recommendation';

const INGREDIENT_SYNONYMS = vocab.ingredient_source.synonyms as Record<string, string[]>;
/** 어휘집 0.7 `price_bin_edges` 는 **원화** 경계 [0, 26000, 46000, 66000, 105000] 이고 토큰은 `blocks[price_bin].vocab` 다 */
const PRICE_EDGES = vocab.price_bin_edges as number[];
const PRICE_BINS = ((vocab.blocks as Array<{ name: string; vocab: string[] }>).find((b) => b.name === 'price_bin')?.vocab ??
  ['~26k', '26k-46k', '46k-66k', '66k-105k', '105k+']) as string[];

export const MOCK_MODEL_VERSION = 'mock-fe-0.1';

/**
 * 응답 한 번을 가리키는 귀속 키. 서버는 uuid4 hex 를 준다 (`recommend_server.py`).
 * `crypto.randomUUID` 는 보안 컨텍스트(https·localhost)에서만 있어서 폴백을 둔다 —
 * 사내 IP 로 열어 본 화면에서 추천 로그가 통째로 빠지면 안 된다.
 */
function newRecommendationId(): string {
  const uuid =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
  return uuid.replace(/-/g, '');
}
/** AI 기본 축. 성향이 없을 때 */
export const DEFAULT_AXES: BannerType[] = ['concern', 'segment', 'price_bin', 'ingredient'];

export interface BuildInput {
  products: Product[];
  persona: PersonaProfile | null;
  /** 담은 상품은 후보에서 뺀다 */
  excluded: Set<string>;
  /** 원본에 피부 타입 표기가 없는 상품의 리뷰어 분포 */
  reviewSkinTypes: Map<string, SkinType[]>;
  axes: BannerType[];
  /**
   * 세션 성향을 알아냈나 (`useTrait().trait_source !== 'cold_start'`).
   * 모르면 신규 브랜드 히어로를 `new_brand`(story) 로 말한다.
   */
  traitKnown?: boolean;
  /** 히어로 정책 (bannerConfig HERO_POLICY). 서버 `hero=` 와 같은 값. 기본 top */
  heroPolicy?: HeroPolicy;
  k: number;
  bannerSlots: number;
  reserved: number;
}

/**
 * 상품의 가격 구간 토큰. 경계가 원화라 `price_usd` 를 표시 환율(localize toKrw)로 바꿔 자른다.
 * 전에는 달러 값을 원화 경계에 대서 늘 첫 칸(`~20`, 어휘집에 없는 폐기 토큰)이 나왔다 — 그 값이 `banner_value` 로
 * 로그에 실렸고 배너 축 매칭이 통째로 빗나갔다 (계약 대조 2026-09-17).
 */
function priceBin(usd: number): string {
  const krw = toKrw(usd);
  for (let i = 1; i < PRICE_EDGES.length; i += 1) {
    if (krw < PRICE_EDGES[i]) return PRICE_BINS[i - 1];
  }
  return PRICE_BINS[PRICE_BINS.length - 1];
}

/**
 * 이 상품에서 알아본 성분을 **전성분에 나온 순서대로** 돌려준다.
 *
 * 전에는 어휘집(`product-feature-vocab.json`) 등재 순서로 돌려줬다. 그래서 배너 문구가
 * "{성분}이 앞에 있는 {카테고리}" 인데 실제로 앞에 있는 성분이 아니었다 — SSAFY Beauty
 * 8종 중 7종이 전성분과 무관하게 `Hyaluronic Acid` 로 나왔다(제로 포어 토닝 패드는
 * Lactic Acid 가 4번째인데도).
 *
 * 문구가 위치를 말하므로 순서도 위치여야 한다. `bannerCreative.leadIngredients`
 * ("전성분 앞 30% 안에 있는 성분만 앞에 있다고 말한다", 계획 §3 · 명세 I2) 와 같은
 * 규칙이다. 두 곳이 다른 답을 내고 있었다.
 */
function ingredientsOf(p: Product): string[] {
  const haystack = p.ingredients.join(' ').toLowerCase();
  const hits: Array<{ name: string; at: number }> = [];

  for (const [name, aliases] of Object.entries(INGREDIENT_SYNONYMS)) {
    let at = -1;
    for (const alias of aliases) {
      const i = haystack.indexOf(alias);
      if (i >= 0 && (at < 0 || i < at)) at = i;
    }
    if (at >= 0) hits.push({ name, at });
  }

  return hits.sort((a, b) => a.at - b.at).map((h) => h.name);
}

function skinTypesOf(p: Product, reviewSkinTypes: Map<string, SkinType[]>): SkinType[] {
  return p.suitable_skin_types.length
    ? p.suitable_skin_types
    : (reviewSkinTypes.get(p.product_id) ?? []);
}

/**
 * 이 상품을 이 축으로 말할 수 있나. 있으면 어휘집 원문 값, 없으면 null.
 * 세그먼트는 페르소나 피부 타입과 맞을 때만 "당신 피부" 라고 말한다.
 */
export function axisValue(
  p: Product,
  axis: BannerType,
  persona: PersonaProfile | null,
  reviewSkinTypes: Map<string, SkinType[]>,
): string | null {
  switch (axis) {
    case 'concern':
      return p.skincare_concerns[0] ?? null;
    case 'ingredient': {
      const found = ingredientsOf(p);
      // 하이라이트에 적힌 성분을 우선한다 — 브랜드가 앞세운 성분이 문구로 자연스럽다
      const featured = found.find((f) => p.highlights.some((h) => h.toLowerCase() === f.toLowerCase()));
      return featured ?? found[0] ?? null;
    }
    case 'clean':
      return p.highlights.find((h) => CLEAN_VALUES.has(h)) ?? null;
    case 'price_bin':
      return priceBin(p.price_usd);
    case 'category':
      return p.category[1] ?? null;
    case 'segment': {
      const types = skinTypesOf(p, reviewSkinTypes);
      if (persona && types.includes(persona.skin_type)) return persona.skin_type;
      return null;
    }
    case 'new_brand':
      return null;
    default:
      return null;
  }
}

/**
 * 신규 상품 — 계약 §5 6-1 (2026-09-11, Jira 247-b): **등록 후 14일 이내인 등록 상품**.
 * 등록 시각(`created_at`)이 있으면 그것으로 재고, 없는 등록 상품(백엔드 요약이 아직 `createdAt` 을
 * 안 줌)은 신규로 본다. 원천 카탈로그는 `rank` 가 있어 신규가 아니다 — 서버와 같은 판정.
 */
export function isNewBrandProduct(p: Product): boolean {
  if (p.rank !== undefined && !p.created_at) return false;
  return isNewRegistered(p.product_id, p.created_at);
}

/**
 * 인기도 항 — `loves_count` 를 log1p 후 min-max 로 편 0~1 값.
 *
 * 전에는 `min(1, log10(review_count + 1) / 5)` 였다. 리뷰를 상품마다 100건으로
 * 맞추면(AI 파트 요청 2026-09-10 §1-3) `review_count` 가 전 상품 100 이 되어
 * **이 항이 상수 0.4 로 죽는다.** PA 에이전트 클릭의 대부분이 이 목이 만드는
 * 기획전 레일 안에서 일어나므로 그대로 두면 노출층이 통째로 바뀐다.
 *
 * 정의를 추천 서버의 인기 prior 와 같게 맞췄다 (`build_feature_sample.py`:228
 * "prior 는 loves_count 를 log1p 후 min-max 로 편 값"). 나중에 이 레일을
 * `/api/recommend` 로 바꿔도 전후가 이어진다.
 *
 * 등록 상품(loves 0)은 정규화 범위에서 빼고 0 을 준다 — 원천 200개의 눈금을
 * 신규 상품이 흔들면 안 된다 (`recommend_server.py`:198 과 같은 처리).
 */
function popularityScale(products: Product[]): (p: Product) => number {
  const loved = products.map((p) => p.loves_count ?? 0).filter((n) => n > 0);
  if (loved.length === 0) return () => 0;

  const lo = Math.log1p(Math.min(...loved));
  const hi = Math.log1p(Math.max(...loved));
  const span = hi - lo;

  return (p: Product): number => {
    const loves = p.loves_count ?? 0;
    if (loves <= 0) return 0;
    if (span <= 0) return 1;
    const v = (Math.log1p(loves) - lo) / span;
    return Math.min(1, Math.max(0, v));
  };
}

/**
 * 히어로에 올릴 신규 브랜드 상품.
 *
 * **동점을 사람마다 다르게 깬다.** 신규 상품은 평점도 loves 도 없어서 점수가
 * `피부 타입 일치 2 또는 0` 뿐이다. 그래서 같은 피부 타입이면 전부 동점이고, 그냥
 * 정렬 순서를 쓰면 목록 앞의 한둘만 영원히 뜬다 — 실제로 8종 중 SB000001·SB000002
 * 둘만 나와서 완성형 배너 40장 중 10장만 도달했다.
 *
 * 페르소나 id 로 자리를 정한다. 같은 사람은 늘 같은 상품을 보고(새로고침마다 배너가
 * 흔들리면 안 된다 — `trait.ts` 의 explore 를 세션에 고정한 것과 같은 이유다),
 * 사람이 달라지면 다른 상품이 뜬다. 페르소나 100명이면 8종이 고루 노출된다.
 *
 * 익명이고 성향도 없으면 `DEFAULT_HERO` 를 띄운다 (§기본 배너).
 */
function pickHero(
  ranked: Product[],
  score: (p: Product) => number,
  persona: PersonaProfile | null,
  traitKnown: boolean,
): Product | null {
  const fresh = ranked.filter(isNewBrandProduct);
  if (fresh.length === 0) return null;

  // 익명 + 성향 없음 = 아무 단서가 없는 첫 방문. 브랜드가 정한 기본 배너를 띄운다
  if (!persona && !traitKnown) {
    const preset = fresh.find((p) => p.product_id === DEFAULT_HERO.product_id);
    if (preset) return preset;
  }

  const best = score(fresh[0]);
  const tied = fresh.filter((p) => score(p) === best);
  if (tied.length <= 1) return tied[0] ?? fresh[0];

  if (!persona) return tied[0];
  let seed = 7;
  for (const ch of persona.persona_id) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  return tied[seed % tied.length];
}

export function buildRecommendation(input: BuildInput): RecommendResponse {
  const { products, persona, excluded, reviewSkinTypes, k, bannerSlots, reserved } = input;
  const traitKnown = input.traitKnown ?? false;
  const axes = input.axes.length ? input.axes : DEFAULT_AXES;

  const candidates = products.filter((p) => !excluded.has(p.product_id));
  const popularity = popularityScale(products);

  const score = (p: Product): number => {
    if (!persona) {
      // 페르소나 없음: 신제품·한정판·단독을 인기순으로
      const badge = (p.badges ?? []).length > 0 ? 1 : 0;
      return badge * 2 + 1 / ((p.rank ?? 999) + 1);
    }
    const match = skinTypesOf(p, reviewSkinTypes).includes(persona.skin_type) ? 2 : 0;
    const quality = (p.rating ?? 0) / 5 + popularity(p);
    return match + quality;
  };

  const ranked = [...candidates].sort((a, b) => score(b) - score(a));
  const items = ranked.slice(0, k).map((p, i) => ({ product_id: p.product_id, score: score(p), rank: i + 1 }));
  const used = new Set(items.map((i) => i.product_id));

  /*
   * 히어로 — **화면에 그려지는 유일한 배너 칸이다.** 배너 행 6칸은 2026-09-10 기획
   * 검토로 빠졌고, 그래서 신규 브랜드 전용 칸(reserved 2)도 화면에서 사라졌다.
   *
   * 그 상태에서 히어로를 `ranked[0]` 로 두면 **신규 브랜드는 배너 노출이 0 이다.**
   * 점수로는 이길 수 없다 — 리뷰도 loves 도 없어 품질 항이 0 이라 최대 2.0 인데
   * 원천 상품은 3.9 까지 간다. 전용 칸이 없어진 만큼 히어로가 그 몫을 받는다.
   *
   * 신규 브랜드 상품 중 **그 사람 점수가 가장 높은 것**을 올린다. 없으면 예전처럼
   * `ranked[0]` 이다. 상품은 점수가 고르고 문구(축)는 세션 성향이 고른다 —
   * personalized-banner-plan.md §2 의 분업 그대로다.
   */
  // hero=new_brand 면 신규 상품 우선(없으면 top 으로 돌아감), hero=top 이면 예전 계약대로 items[0] (서버와 같은 규칙)
  const heroPolicy: HeroPolicy = input.heroPolicy ?? 'top';
  const top = (heroPolicy === 'new_brand' ? pickHero(ranked, score, persona, traitKnown) : null) ?? ranked[0] ?? null;
  const heroIsFresh = top !== null && isNewBrandProduct(top);
  let hero: RecommendResponse['hero'] = null;
  if (top) {
    /*
     * 성향을 모르는 세션은 신규 브랜드를 `new_brand`(→ story) 로 말한다.
     * "새로 들어온 브랜드의 첫 세럼" 이 처음 보는 사람에게 할 말이고, 이 축이 없으면
     * story 변형이 영영 안 뜬다(축 목록에 new_brand 가 없어서다).
     * 성향을 알면 그 축으로 말한다.
     */
    const isPreset = !persona && !traitKnown && top.product_id === DEFAULT_HERO.product_id;
    const preferStory = !isPreset && !traitKnown && isNewBrandProduct(top);
    const axis: BannerType = isPreset
      ? DEFAULT_HERO.banner_type
      : preferStory
        ? 'new_brand'
        : (axes.find((a) => axisValue(top, a, persona, reviewSkinTypes) !== null) ?? axes[0]);
    hero = {
      product_id: top.product_id,
      banner_type: axis,
      banner_value: axis === 'new_brand' ? null : axisValue(top, axis, persona, reviewSkinTypes),
    };
  }

  const banners: RecommendBanner[] = [];
  const axisSlots = Math.max(0, bannerSlots - reserved);
  const pool = ranked.filter((p) => !used.has(p.product_id));

  // 축 배너: 축을 돌아가며, 그 축으로 말할 수 있는 가장 점수 높은 상품
  let slot = 1;
  let axisIdx = 0;
  let tries = 0;
  while (banners.length < axisSlots && tries < axes.length * 3) {
    const axis = axes[axisIdx % axes.length];
    axisIdx += 1;
    tries += 1;
    const pick = pool.find((p) => !used.has(p.product_id) && !isNewBrandProduct(p) && axisValue(p, axis, persona, reviewSkinTypes) !== null);
    if (!pick) continue;
    used.add(pick.product_id);
    banners.push({
      slot,
      banner_type: axis,
      banner_value: axisValue(pick, axis, persona, reviewSkinTypes),
      product_id: pick.product_id,
      score: score(pick),
    });
    slot += 1;
  }

  // 전용 칸: 신규·저노출 브랜드. 점수로 싸우게 하지 않고 자리를 떼어 준다
  const fresh = pool.filter((p) => !used.has(p.product_id) && isNewBrandProduct(p));
  for (const p of fresh.slice(0, reserved)) {
    used.add(p.product_id);
    banners.push({
      slot: slot,
      banner_type: 'new_brand',
      banner_value: null,
      product_id: p.product_id,
      score: score(p),
      reserved: true,
    });
    slot += 1;
  }

  return {
    user_id: persona?.persona_id ?? 'anonymous',
    generated_at: new Date().toISOString(),
    model_version: MOCK_MODEL_VERSION,
    // 응답마다 새로 발급한다. 서버(`recommend_server.py`)가 uuid4 를 주는 자리라
    // 목도 같은 성질을 가져야 노출-클릭 귀속이 지금부터 제대로 쌓인다
    recommendation_id: newRecommendationId(),
    list_id: 'main',
    banner_list_id: 'banner_row',
    items,
    hero,
    banners,
    // 실제 적용값. new_brand 를 요청했어도 신규 상품이 없어 items[0] 로 돌아갔으면 top (서버와 같은 규칙)
    hero_policy: heroPolicy === 'new_brand' && heroIsFresh ? 'new_brand' : 'top',
  };
}
