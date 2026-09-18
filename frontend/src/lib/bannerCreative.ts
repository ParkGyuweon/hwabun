/**
 * 광고 배너 크리에이티브 — 어느 상품을 어떤 강조로 보여줄지 정한다.
 *
 * 계획: `docs/planning/ssafy-beauty-creative-plan.md` §2·§3·§10 (올리브영 관행 관찰 반영).
 *
 * 두 가지를 나눠서 정한다.
 *   1) 어느 상품을 올리나      — 세션 성향(축)과 상품 태그가 맞는 것만 (`pickBannerProducts`)
 *   2) 어떤 느낌으로 보여주나  — 같은 상품도 축에 따라 변형 5종 (`creativeFor`)
 *
 * 추천 API(`/api/recommend`)가 붙으면 1)은 API 의 `banners[]` 로 대체되고 2)는 그대로 쓴다.
 * API 가 내리는 `banner_type` 7종을 강조 요소가 같은 것끼리 묶어 변형 5종으로 줄였다.
 *
 * 이미지는 `public/images/ssafy-beauty/` 의 컷아웃·배경 타일이다. 컷아웃 누끼가 용기의
 * 흰 부분을 조금 깎아서, 제품은 **흰 판 위에** 얹어 쓴다 (`ad__stage` 가 그 흰 판이다).
 */
import { labelKo } from './formLabels';
import bannerImages from '../mocks/banner-images.json';
import type { Product } from '../types/product';

/** 추천 API `banner_type` (계약 `recommendation-io-spec.md` §5-1) */
export type BannerAxis =
  | 'concern'
  | 'ingredient'
  | 'clean'
  | 'price_bin'
  | 'category'
  | 'segment'
  | 'new_brand';

/** 이미지·레이아웃 변형. 축 7종을 강조 요소로 묶은 것 */
export type Variant = 'price' | 'ingredient' | 'concern' | 'segment' | 'story';

const AXIS_VARIANT: Record<BannerAxis, Variant> = {
  price_bin: 'price',
  ingredient: 'ingredient',
  clean: 'ingredient',
  concern: 'concern',
  category: 'concern',
  segment: 'segment',
  new_brand: 'story',
};

const IMG = '/images/ssafy-beauty';

/** 변형별 배경 타일. 고민 축은 값에 따라 톤을 바꾼다 */
const BG: Record<Variant, string> = {
  price: `${IMG}/bg-ivory-plain.webp`,
  ingredient: `${IMG}/bg-ivory-sage.webp`,
  concern: `${IMG}/bg-concern-tone.webp`,
  segment: `${IMG}/bg-wall-light.webp`,
  story: `${IMG}/bg-linen-props.webp`,
};

/** 고민 값 → 배경 타일. 없으면 기본 톤 */
const CONCERN_BG: Record<string, string> = {
  Pores: `${IMG}/bg-concern-pores.webp`,
  'Dullness/Uneven Texture': `${IMG}/bg-concern-tone.webp`,
  'Dark spots': `${IMG}/bg-concern-tone.webp`,
  'Loss of firmness': `${IMG}/bg-concern-firm.webp`,
  'Anti-Aging': `${IMG}/bg-concern-firm.webp`,
  Dryness: `${IMG}/bg-concern-hydration.webp`,
  'Acne/Blemishes': `${IMG}/bg-concern-clear.webp`,
  'Dark Circles': `${IMG}/bg-concern-eye.webp`,
  Redness: `${IMG}/bg-concern-clear.webp`,
};

/** 성분 → 곁에 두는 원물 소품 컷아웃 (계획 §5-4) */
const PROP: Record<string, string> = {
  'Vitamin C': `${IMG}/prop-seabuckthorn.webp`,
  Niacinamide: `${IMG}/prop-capsules.webp`,
  'Salicylic Acid': `${IMG}/prop-willowbark.webp`,
  'Lactic Acid': `${IMG}/prop-lactic-powder.webp`,
  'AHA/Glycolic Acid': `${IMG}/prop-lactic-powder.webp`,
  Peptides: `${IMG}/prop-pink-helix.webp`,
  Collagen: `${IMG}/prop-jelly-cube.webp`,
  'Hyaluronic Acid': `${IMG}/prop-droplets.webp`,
  SPF: `${IMG}/prop-droplets.webp`,
  Caffeine: `${IMG}/prop-coffee.webp`,
  'Centella (Cica)': `${IMG}/prop-purslane.webp`,
  Panthenol: `${IMG}/prop-camellia.webp`,
};

/** 피부 톤 → 손 컷아웃. 같은 피부 배너는 톤이 맞아야 성립한다 */
const HAND: Record<string, string> = {
  fair: `${IMG}/hand-fair-drop.webp`,
  light: `${IMG}/hand-light-drop.webp`,
  medium: `${IMG}/hand-medium-drop.webp`,
  tan: `${IMG}/hand-tan-drop.webp`,
  deep: `${IMG}/hand-deep-drop.webp`,
};

const SKIN_KO: Record<string, string> = {
  dry: '건성',
  oily: '지성',
  combination: '복합성',
  normal: '중성',
};

const PRICE_BAND_KO = (usd: number): string => {
  if (usd < 20) return '2만원대 이하';
  if (usd < 35) return '2~4만원대';
  if (usd < 50) return '4~6만원대';
  if (usd < 80) return '6~10만원대';
  return '10만원대 이상';
};

/** 전성분 앞 30% 안에 있는 성분만 "앞에 있다"고 말한다 (계획 §3, 명세 I2) */
export function leadIngredients(p: Product, limit = 3): string[] {
  const raw = Array.isArray(p.ingredients) ? p.ingredients[0] : p.ingredients;
  if (!raw) return [];
  const parts = String(raw)
    .split(/,\s*/)
    .map((s) => s.trim())
    .filter(Boolean);
  const head = parts.slice(0, Math.max(3, Math.ceil(parts.length * 0.3)));
  const found: string[] = [];
  for (const key of Object.keys(PROP)) {
    const needle = key.split(/[ /(]/)[0].toLowerCase();
    if (head.some((t) => t.toLowerCase().includes(needle))) found.push(key);
    if (found.length >= limit) break;
  }
  return found;
}

export interface Creative {
  axis: BannerAxis;
  variant: Variant;
  /** 우상단 원형 배지 */
  badge: string;
  /** 질문형·상황형 킥커 한 줄 */
  kicker: string;
  /** 헤드라인. `mark` 는 하이라이트 박스로 감싼다 */
  head: { mark: string; rest: string };
  /** 가격 아래 한 줄 */
  foot: string;
  /** 하단 CTA 바 */
  cta: string;
  bg: string;
  /** 제품 옆 소품 (성분 원물·손). 없으면 제품만 */
  prop: string | null;
  /** 가격을 크게 보여주는 변형인가 */
  bigPrice: boolean;
}

/**
 * 배너 문구·이미지. 축과 값이 정해지면 나머지는 이 함수가 만든다.
 *
 * 올리브영 관행(계획 §10-1·§10-6)을 따른다: 킥커는 질문·상황, 헤드라인은 명사로 끝내고
 * 핵심 낱말만 하이라이트 박스, 하단은 CTA 바. 할인·순위·효능 단정은 쓰지 않는다.
 */
export function creativeFor(
  product: Product,
  axis: BannerAxis,
  value: string | null,
  skinTone?: string,
): Creative {
  const variant = AXIS_VARIANT[axis];
  const cat = labelKo(product.category[product.category.length - 1] ?? '');
  const lead = leadIngredients(product, 2);

  if (variant === 'ingredient') {
    const ing = value && axis === 'ingredient' ? value : (lead[0] ?? '');
    const ko = ing ? labelKo(ing) : '';
    const clean = axis === 'clean' && value ? labelKo(value) : '';
    return {
      axis,
      variant,
      badge: '성분 PICK',
      kicker: clean ? '성분 조건부터 보는 편이라면' : '성분표부터 확인하는 편이라면',
      head: clean ? { mark: clean, rest: `조건을 지킨 ${cat}` } : { mark: ko, rest: `가 앞에 있는 ${cat}` },
      foot: lead.length > 1 ? `전성분 앞쪽 · ${lead.map(labelKo).join(' · ')}` : '전성분 앞쪽에 있습니다',
      cta: '전성분 보기',
      bg: BG.ingredient,
      prop: ing ? (PROP[ing] ?? null) : null,
      bigPrice: false,
    };
  }

  if (variant === 'concern') {
    const concern = value ?? product.skincare_concerns[0] ?? '';
    const ko = concern ? labelKo(concern) : cat;
    return {
      axis,
      variant,
      badge: '고민 맞춤',
      kicker: `${ko}이 신경 쓰인다면?`,
      head: { mark: ko, rest: `을 위한 ${cat}` },
      foot: lead.length ? `${lead.map(labelKo).join(' · ')} 함유` : (product.size ?? ''),
      cta: '자세히 보기',
      bg: CONCERN_BG[concern] ?? BG.concern,
      prop: lead[0] ? (PROP[lead[0]] ?? null) : null,
      bigPrice: false,
    };
  }

  if (variant === 'price') {
    return {
      axis,
      variant,
      badge: '가격·용량',
      kicker: '용량까지 따져 보는 편이라면',
      head: { mark: PRICE_BAND_KO(product.price_usd), rest: `에서 고른 ${cat}` },
      foot: product.size ? `${product.size} · 정가입니다` : '정가입니다',
      cta: '가격·용량 보기',
      bg: BG.price,
      prop: null,
      bigPrice: true,
    };
  }

  if (variant === 'segment') {
    const type = value && SKIN_KO[value] ? SKIN_KO[value] : (SKIN_KO[product.suitable_skin_types[0] ?? ''] ?? '');
    return {
      axis,
      variant,
      badge: '같은 피부',
      kicker: type ? `${type} 피부라면` : '나와 같은 피부라면',
      head: { mark: type ? `${type} 피부` : '같은 피부', rest: `가 오래 본 ${cat}` },
      foot: '리뷰에서 같은 피부 타입만 골라 볼 수 있습니다',
      cta: '같은 피부 리뷰 보기',
      bg: BG.segment,
      prop: skinTone ? (HAND[skinTone] ?? HAND.medium) : HAND.medium,
      bigPrice: false,
    };
  }

  return {
    axis,
    variant: 'story',
    badge: 'NEW 입점',
    kicker: '이번 주 새로 들어온 브랜드',
    head: { mark: product.brand_name, rest: `의 첫 ${cat}` },
    foot: '리뷰가 쌓이기 전이라 성분과 설명으로 판단하는 상품입니다',
    cta: '브랜드 보기',
    bg: BG.story,
    prop: null,
    bigPrice: false,
  };
}

/** 상품 대표 이미지. 시트에서 자른 팩샷이 있으면 그것을, 없으면 원본 */
export function packshot(product: Product): string {
  return /^SB\d+$/.test(product.product_id)
    ? `${IMG}/${product.product_id}-m1.webp`
    : (product.image_url ?? '/images/product-placeholder.svg');
}

export interface BannerSlot {
  banner_slot: number;
  banner_type: BannerAxis;
  banner_value: string | null;
  product: Product;
}

/**
 * 어느 상품을 어느 축 배너에 올릴지 (추천 API 붙기 전 규칙).
 *
 * 축과 상품 태그가 맞을 때만 올린다. 성분 축은 전성분 앞 30% 안에 있어야 하고,
 * 고민 축은 `skincare_concerns` 에, clean 축은 `highlights` 에 그 값이 있어야 한다.
 * 같은 상품이 두 칸에 겹치지 않는다.
 */
export function pickBannerProducts(
  products: Product[],
  axes: BannerAxis[],
  slots: number,
  skinType?: string,
): BannerSlot[] {
  const out: BannerSlot[] = [];
  const used = new Set<string>();

  const valueFor = (axis: BannerAxis, p: Product): string | null | undefined => {
    switch (axis) {
      case 'concern':
        return p.skincare_concerns[0];
      case 'ingredient':
        return leadIngredients(p, 1)[0];
      case 'clean':
        return p.highlights.find((h) => h.startsWith('Without') || h === 'Fragrance Free' || h === 'Oil Free');
      case 'price_bin':
        return PRICE_BAND_KO(p.price_usd);
      case 'category':
        return p.category[p.category.length - 1];
      case 'segment':
        return skinType && p.suitable_skin_types.includes(skinType as never) ? skinType : p.suitable_skin_types[0];
      case 'new_brand':
        return null;
    }
  };

  for (const axis of axes) {
    if (out.length >= slots) break;
    const cand = products.find((p) => {
      if (used.has(p.product_id)) return false;
      const v = valueFor(axis, p);
      return axis === 'new_brand' ? true : Boolean(v);
    });
    if (!cand) continue;
    used.add(cand.product_id);
    out.push({
      banner_slot: out.length + 1,
      banner_type: axis,
      banner_value: axis === 'new_brand' ? null : (valueFor(axis, cand) ?? null),
      product: cand,
    });
  }
  return out;
}

/**
 * 완성형 배너 이미지. 디자이너(팀)가 글자까지 넣어 만든 한 장이 있으면 CSS 조립 대신 그 이미지를 쓴다.
 * 어떤 상품·변형에 이미지가 있는지는 mocks/banner-images.json 이 말한다 (파일 존재 여부를 브라우저가
 * 미리 알 수 없어서다). 파일은 public/images/ssafy-beauty/banners/{product_id}-{variant}.webp.
 */
const BANNER_IMAGES = bannerImages as unknown as Record<string, Partial<Record<Variant, string>>>;

export function bannerImage(productId: string, variant: Variant): string | null {
  const file = BANNER_IMAGES[productId]?.[variant];
  return file ? `${IMG}/banners/${file}` : null;
}

/** 완성형 배너가 한 장이라도 등록된 상품인지. 히어로는 이 상품군 안에서만 고른다 (2026-09-18) */
export function hasBannerImages(productId: string): boolean {
  const files = BANNER_IMAGES[productId];
  return files !== undefined && Object.values(files).some(Boolean);
}

/**
 * 그 상품의 완성형 배너 중 하나. 원하는 변형이 있으면 그것, 없으면 같은 상품의 다른 변형이다.
 * 다른 상품으로는 넘어가지 않는다. 등록된 것이 없으면 null.
 */
export function anyBannerImage(productId: string, preferred: Variant): { src: string; variant: Variant } | null {
  const files = BANNER_IMAGES[productId];
  if (!files) return null;
  const order: Variant[] = [preferred, 'story', 'concern', 'segment', 'price', 'ingredient'];
  for (const v of order) {
    const file = files[v];
    if (file) return { src: `${IMG}/banners/${file}`, variant: v };
  }
  return null;
}
