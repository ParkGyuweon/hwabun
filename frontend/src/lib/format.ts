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
