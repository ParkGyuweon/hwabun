import type { PersonaProfile } from '../types/persona';
import type { Review } from '../types/review';

/**
 * 리뷰 샘플에서 가상 페르소나를 파생시킨다.
 *
 * 같은 author_id 가 리뷰 시점에 따라 다른 skin_tone 을 가진 경우가 있어서
 * 대표 프로필은 가장 최근 리뷰 기준으로 잡는다.
 * (최근값이냐 최빈값이냐는 데이터 담당자 확인 대기 중)
 */
export function buildPersonas(reviews: Review[]): PersonaProfile[] {
  const latestByAuthor = new Map<string, Review>();
  const productsByAuthor = new Map<string, Set<string>>();

  for (const review of reviews) {
    const current = latestByAuthor.get(review.author_id);
    if (!current || review.submission_time > current.submission_time) {
      latestByAuthor.set(review.author_id, review);
    }

    const products = productsByAuthor.get(review.author_id) ?? new Set<string>();
    products.add(review.product_id);
    productsByAuthor.set(review.author_id, products);
  }

  return [...latestByAuthor.values()]
    .map((review) => ({
      persona_id: review.author_id,
      skin_type: review.skin_type,
      skin_tone: review.skin_tone,
      eye_color: review.eye_color,
      hair_color: review.hair_color,
      reviewed_product_count: productsByAuthor.get(review.author_id)?.size ?? 1,
    }))
    // 여러 상품을 본 페르소나가 시나리오 테스트에 쓸모가 많아서 앞으로 보낸다
    .sort((a, b) => b.reviewed_product_count - a.reviewed_product_count);
}
