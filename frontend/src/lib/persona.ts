import type { PersonaProfile } from '../types/persona';
import type { Review } from '../types/review';

/**
 * 화면 전환기에 올릴 페르소나 수 상한.
 *
 * 리뷰 3,000건에는 작성자가 1,634명 들어 있다. 그걸 다 올리면 드롭다운을 쓸 수 없다.
 * 페르소나 전환은 이 사이트의 로그인에 해당하므로 고를 수 있어야 한다.
 *
 * 여러 상품을 리뷰한 사람을 앞으로 보내고 잘라낸다.
 * 상품 하나만 본 페르소나는 행동 시나리오를 굴릴 여지가 없다.
 */
const MAX_PERSONAS = 60;

/**
 * 리뷰 샘플에서 가상 페르소나를 파생시킨다.
 *
 * 같은 author_id 가 리뷰 시점에 따라 다른 skin_tone 을 가진 경우가 있어서
 * 대표 프로필은 가장 최근 리뷰 기준으로 잡는다.
 * (최근값이냐 최빈값이냐는 데이터 담당자 확인 대기 중)
 *
 * 부하 테스트용 1만 명 페르소나는 `simulator/personas/data/` 에 따로 있다.
 * 여기서 만드는 것은 **화면에서 골라 볼 수 있는 소수**다.
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
    .sort((a, b) => b.reviewed_product_count - a.reviewed_product_count)
    .slice(0, MAX_PERSONAS);
}
