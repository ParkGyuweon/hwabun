import type { Review } from '../types/review';
import type { SkinType } from '../types/product';

export function formatPrice(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

export function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${y}.${m}.${d}`;
}

const SKIN_TYPE_LABEL: Record<SkinType, string> = {
  combination: '복합성',
  dry: '건성',
  normal: '중성',
  oily: '지성',
};

export function skinTypeLabel(value: string): string {
  return SKIN_TYPE_LABEL[value as SkinType] ?? value;
}

/**
 * skin_tone / eye_color / hair_color 는 lightMedium 같은 camelCase 와
 * Grey/gray 처럼 표기가 섞여 있다. 정규화 전이므로 표시용으로만 다듬는다.
 * (docs/data/README.md - 알려진 데이터 이슈 1번)
 */
export function humanizeAttribute(value: string): string {
  const spaced = value.replace(/([a-z])([A-Z])/g, '$1 $2');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

/**
 * ingredients 는 형식만 배열이고 원소 하나에 전 성분이 쉼표로 이어붙어 있다.
 * 칩으로 뿌리기 위해 쉼표로 분리한다. 데이터 담당자가 정규화해서 주기 전까지의 임시 처리.
 */
export function splitIngredients(ingredients: string[]): string[] {
  return ingredients
    .flatMap((block) => block.split(','))
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export interface ReviewStats {
  total: number;
  average: number;
  /** 5점 -> 1점 순서의 개수 */
  distribution: number[];
  recommendRate: number | null;
}

export function calcReviewStats(reviews: Review[]): ReviewStats {
  const total = reviews.length;
  if (total === 0) {
    return { total: 0, average: 0, distribution: [0, 0, 0, 0, 0], recommendRate: null };
  }

  const distribution = [5, 4, 3, 2, 1].map(
    (score) => reviews.filter((review) => review.rating === score).length,
  );
  const average = reviews.reduce((sum, review) => sum + review.rating, 0) / total;

  const answered = reviews.filter((review) => review.is_recommended !== null);
  const recommendRate = answered.length
    ? Math.round((answered.filter((review) => review.is_recommended).length / answered.length) * 100)
    : null;

  return { total, average, distribution, recommendRate };
}

/** 리뷰에서 파생한 피부 타입 분포 */
export interface DerivedSkinTypes {
  /** 표기할 만큼 비중이 있는 타입. 비중 큰 순서 */
  types: SkinType[];
  /** 타입별 비중 (0~1) */
  shares: Map<SkinType, number>;
  /** 근거가 된 리뷰 수. 화면에 같이 보여준다 */
  sampleSize: number;
}

/** 이 비중을 넘는 타입만 표기한다. 한두 명 때문에 칩이 붙는 것을 막는다 */
const SKIN_TYPE_MIN_SHARE = 0.2;

/**
 * 상품 정보에 피부 타입 표기가 없을 때 리뷰로 채운다.
 *
 * 데이터셋 상품 200개 중 132개(66%)에 `suitable_skin_types` 가 비어 있다.
 * 대신 리뷰마다 작성자의 피부 타입이 붙어 있어서, 그 분포로 대신할 수 있다.
 *
 * **브랜드가 표기한 값이 아니라 리뷰어 분포다.** 성격이 다르므로
 * `suitable_skin_types` 를 덮어쓰지 않고 따로 계산해서 화면에서 구분해 보여준다.
 * (`suitable_skin_types` 는 데이터 담당자가 내려주는 원본 필드다)
 */
export function deriveSkinTypesFromReviews(reviews: Review[]): DerivedSkinTypes {
  const counts = new Map<SkinType, number>();

  for (const review of reviews) {
    if (!review.skin_type) continue;
    counts.set(review.skin_type, (counts.get(review.skin_type) ?? 0) + 1);
  }

  const sampleSize = [...counts.values()].reduce((sum, n) => sum + n, 0);
  const shares = new Map<SkinType, number>();
  if (sampleSize === 0) return { types: [], shares, sampleSize: 0 };

  for (const [type, n] of counts) shares.set(type, n / sampleSize);

  const types = [...shares.entries()]
    .filter(([, share]) => share >= SKIN_TYPE_MIN_SHARE)
    .sort((a, b) => b[1] - a[1])
    .map(([type]) => type);

  return { types, shares, sampleSize };
}
