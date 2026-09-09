/**
 * 사이트 한국어화 · 표시 전용 레이어.
 *
 * 단일 출처는 `contracts/localization/` (데이터 파트, Jira 234). 사람이 검수한 대조표를
 * 빌더가 JSON 으로 옮긴 것이라 여기서 문장을 고치지 않는다.
 *
 * 원칙은 하나다. **분석이 읽는 값은 영문 그대로, 사람이 읽는 값만 한국어.**
 *   · `product_name`·`size`·`description` 은 사람만 읽으므로 바꿔 끼운다
 *   · `ingredients` 는 그대로 두고 `ingredients_ko` 를 옆에 둔다. 대시보드의 주의 성분
 *     정규식, 배너의 성분 매칭, 어휘집 위치 가중이 전부 영문 전성분을 읽는다
 *   · `category[]`·`highlights[]`·`skincare_concerns[]`·`badges[]`·`variants[].label` 값은
 *     손대지 않고 화면에서만 `labels-ko` 로 바꿔 보여준다. 값을 바꾸면 추천 매칭이 조용히 0 이 된다
 *   · 리뷰는 쇼핑몰 화면만 한국어를 쓴다. 대시보드 리뷰 지표(자극·트러블 언급)는 영문
 *     정규식이라 원본을 읽는다 (`dashboard/lib/metrics.ts`)
 *   · 가격은 원화로 **표시만** 한다. 이벤트의 `price_usd`·`cart_value`·`currency:'USD'` 는
 *     데이터 팀과 단위 합의 전이라 그대로다 (README 원칙)
 */
import productsKo from '../../../contracts/localization/products-ko.json';
import reviewsKo from '../../../contracts/localization/reviews-ko.json';
import labelsKo from '../../../contracts/localization/labels-ko.json';
import type { Product, ProductDescription } from '../types/product';
import type { Review } from '../types/review';

interface ProductKo {
  product_name: string;
  size: string | null;
  price_krw: number;
  variant_labels: Record<string, string>;
  description: ProductDescription | null;
  ingredients: string[];
}
interface ReviewKo {
  product_id: string;
  review_title: string | null;
  review_text: string;
}
type LabelGroup = 'category' | 'highlights' | 'skincare_concerns' | 'suitable_skin_types' | 'badges' | 'variant_labels';

const PRODUCTS = productsKo as unknown as Record<string, ProductKo | Record<string, unknown>>;
const REVIEWS = reviewsKo as unknown as Record<string, ReviewKo | Record<string, unknown>>;
const LABELS = labelsKo as unknown as Record<LabelGroup, Record<string, string>> & { _meta?: unknown };

/** 빌더가 쓴 고정 환율. products-ko 의 price_krw 와 같은 식이어야 표시 가격이 어긋나지 않는다 */
export const KRW_PER_USD = 1340.86;
export const KRW_ROUNDING = 100;

/** 달러 → 원. 100원 단위 반올림. 검수본 200개 전부 이 식과 일치함을 확인했다 (2026-09-10) */
export function toKrw(usd: number): number {
  return Math.round((usd * KRW_PER_USD) / KRW_ROUNDING) * KRW_ROUNDING;
}

const isProductKo = (v: unknown): v is ProductKo =>
  typeof v === 'object' && v !== null && 'product_name' in (v as Record<string, unknown>);
const isReviewKo = (v: unknown): v is ReviewKo =>
  typeof v === 'object' && v !== null && 'review_text' in (v as Record<string, unknown>);

/**
 * 상품 하나를 표시용으로 바꾼다. 번역이 없는 상품(SSAFY Beauty 시드·브랜드 등록 상품)은 그대로.
 * 번역 쪽이 비어 있으면(원본도 비어 있던 것) 원본을 유지한다.
 */
export function localizeProduct(p: Product): Product {
  const ko = PRODUCTS[p.product_id];
  if (!isProductKo(ko)) return p;
  return {
    ...p,
    product_name: ko.product_name || p.product_name,
    size: ko.size ?? p.size,
    description: ko.description ?? p.description,
    // README 는 빈 배열이라 했지만 실제 파일엔 null 인 항목이 있다. 둘 다 "번역 없음" 으로 본다
    ingredients_ko: Array.isArray(ko.ingredients) && ko.ingredients.length > 0 ? ko.ingredients : undefined,
  };
}

export function localizeReview(r: Review): Review {
  const ko = REVIEWS[r.review_id];
  if (!isReviewKo(ko)) return r;
  return {
    ...r,
    review_title: ko.review_title,
    review_text: ko.review_text || r.review_text,
  };
}

/** 라벨 조회. 없는 키는 영문 그대로 (README: 원본 200개가 쓰는 키는 전부 있다) */
function label(group: LabelGroup, value: string): string {
  return LABELS[group]?.[value] ?? value;
}

export const categoryKo = (v: string): string => label('category', v);
export const highlightKo = (v: string): string => label('highlights', v);
export const concernKo = (v: string): string => label('skincare_concerns', v);
export const skinTypeKo = (v: string): string => label('suitable_skin_types', v);
export const badgeKo = (v: string): string => label('badges', v);
export const variantLabelKo = (v: string): string => label('variant_labels', v);

/** `Skincare > Moisturizers` 처럼 단계별로 바꾼 뒤 잇는다 */
export const categoryPathKo = (path: string[], sep = ' › '): string => path.map(categoryKo).join(sep);
