/**
 * 추천 API 목 — 계약 §5-1 응답을 **프론트에서** 만든다.
 *
 * 백엔드 `RankingService` 가 아직 없다. 형태를 먼저 확정해 화면을 붙이고, 서빙이 생기면
 * 이 파일의 `buildRecommendation` 호출을 `fetch('/api/recommend?…')` 로 바꾼다.
 * 화면·로그·타입은 그대로다.
 *
 * 점수는 설명 가능한 두 축만 쓴다 (기존 `skin_match_v0` 와 같다):
 *   피부 타입 일치 +2 (원본 표기 우선, 없으면 리뷰어 분포)
 *   품질 사전확률: 평점(0~1) + 리뷰 수 로그 스케일(0~1)
 * 정확도 장치가 아니다. AI 측정에서 축 배너는 +0.5%p 로 노이즈 수준이고, 배너의 값은
 * "이유를 말해 주는 것" 과 "신규 브랜드에 자리를 주는 것" 이다.
 */
import vocab from '../../../contracts/product-feature-vocab.json';
import { CLEAN_VALUES } from './vocabLabels';
import type { BannerType } from '../types/log';
import type { PersonaProfile } from '../types/persona';
import type { Product, SkinType } from '../types/product';
import type { RecommendBanner, RecommendResponse } from '../types/recommendation';

const INGREDIENT_SYNONYMS = vocab.ingredient_source.synonyms as Record<string, string[]>;
const PRICE_EDGES = vocab.price_bin_edges as number[];
const PRICE_BINS = ['~20', '20-35', '35-50', '50-80', '80+'];

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
  k: number;
  bannerSlots: number;
  reserved: number;
}

function priceBin(usd: number): string {
  for (let i = 1; i < PRICE_EDGES.length; i += 1) {
    if (usd < PRICE_EDGES[i]) return PRICE_BINS[i - 1];
  }
  return PRICE_BINS[PRICE_BINS.length - 1];
}

function ingredientsOf(p: Product): string[] {
  const haystack = p.ingredients.join(' ').toLowerCase();
  return Object.entries(INGREDIENT_SYNONYMS)
    .filter(([, aliases]) => aliases.some((a) => haystack.includes(a)))
    .map(([name]) => name);
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

/** 신규·저노출: 리뷰가 없거나 인기 순위가 없는 상품. 시드 브랜드가 여기 든다 */
export function isNewBrandProduct(p: Product): boolean {
  return (p.review_count ?? 0) === 0 || p.rank === undefined;
}

export function buildRecommendation(input: BuildInput): RecommendResponse {
  const { products, persona, excluded, reviewSkinTypes, k, bannerSlots, reserved } = input;
  const axes = input.axes.length ? input.axes : DEFAULT_AXES;

  const candidates = products.filter((p) => !excluded.has(p.product_id));

  const score = (p: Product): number => {
    if (!persona) {
      // 페르소나 없음: 신제품·한정판·단독을 인기순으로
      const badge = (p.badges ?? []).length > 0 ? 1 : 0;
      return badge * 2 + 1 / ((p.rank ?? 999) + 1);
    }
    const match = skinTypesOf(p, reviewSkinTypes).includes(persona.skin_type) ? 2 : 0;
    const quality = (p.rating ?? 0) / 5 + Math.min(1, Math.log10((p.review_count ?? 0) + 1) / 5);
    return match + quality;
  };

  const ranked = [...candidates].sort((a, b) => score(b) - score(a));
  const items = ranked.slice(0, k).map((p, i) => ({ product_id: p.product_id, score: score(p), rank: i + 1 }));
  const used = new Set(items.map((i) => i.product_id));

  // 히어로: items[0] 에 축 문구를 얹는다. 첫 축으로 말할 수 없으면 말할 수 있는 축을 찾는다
  const top = ranked[0] ?? null;
  let hero: RecommendResponse['hero'] = null;
  if (top) {
    const axis = axes.find((a) => axisValue(top, a, persona, reviewSkinTypes) !== null) ?? axes[0];
    hero = { product_id: top.product_id, banner_type: axis, banner_value: axisValue(top, axis, persona, reviewSkinTypes) };
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
  };
}
