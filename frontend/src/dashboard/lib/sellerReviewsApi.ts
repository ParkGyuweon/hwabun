/**
 * 판매자 리뷰 API.
 *
 *   GET /api/seller/reviews?brandId=   로그인한 판매자 본인 브랜드 상품의 PUBLISHED 리뷰 전체, 최신순. 페이지네이션 없음 (백엔드 09-18)
 *
 * 행: reviewId · productId · productName · orderItemId · rating · isRecommended · reviewTitle · reviewText · skinType ·
 * submissionTime · isPurchaser (feat/seller-review-api 7527aab, FeedbackController.sellerReviews — 배열 그대로, 감싸지 않음).
 * skinType 은 review.skin_type_snapshot 이 없으면 구매 회원의 member.skin_type_code 다. 코드는 dry·oily·combination·normal.
 * 시드 리뷰는 저장된 피부 타입 스냅샷, 구매 리뷰는 회원 프로필 피부 타입을 보완해 준다. 모르면 null.
 *
 * 못 읽으면 못 읽었다고 한다. 번들 표본이나 다른 브랜드로 대신 채우지 않는다.
 */
import { authFetch } from '../../lib/auth';
import type { SkinType } from '../../types/product';
import type { DashboardReview } from './metrics';

/** 집계용 다섯 필드에 화면이 원문을 보여 주는 데 필요한 것을 더한 행 */
export interface SellerReview extends DashboardReview {
  review_id: string;
  product_name: string | null;
  review_title: string | null;
  /** "2026-09-18" 까지만 쓴다. 시각은 화면에 안 적는다 */
  submission_date: string | null;
  /** 구매 이력이 있는 리뷰인지. 시드 리뷰는 false */
  is_purchaser: boolean;
}

export type SellerReviewsRead = { kind: 'ready'; rows: SellerReview[] } | { kind: 'unavailable' };

const SKIN_TYPES: ReadonlySet<string> = new Set(['dry', 'oily', 'combination', 'normal']);

function asRow(x: unknown): SellerReview | null {
  if (!x || typeof x !== 'object') return null;
  const r = x as Record<string, unknown>;
  if (typeof r.productId !== 'string' || typeof r.rating !== 'number') return null;
  const when = typeof r.submissionTime === 'string' ? r.submissionTime.slice(0, 10) : null;
  return {
    review_id: typeof r.reviewId === 'string' ? r.reviewId : `${r.productId}:${String(r.submissionTime ?? '')}:${r.rating}`,
    product_name: typeof r.productName === 'string' ? r.productName : null,
    review_title: typeof r.reviewTitle === 'string' && r.reviewTitle.trim() ? r.reviewTitle : null,
    submission_date: when,
    is_purchaser: r.isPurchaser === true || r.isPurchaser === 1,
    product_id: r.productId,
    rating: r.rating,
    // MySQL tinyint(1) 은 JdbcTemplate 을 거치면 true/false 대신 1/0 으로 올 수 있다 (shopApi.ts 의 리뷰 매핑과 같은 처리)
    is_recommended: typeof r.isRecommended === 'boolean' ? r.isRecommended : typeof r.isRecommended === 'number' ? r.isRecommended !== 0 : null,
    review_text: typeof r.reviewText === 'string' ? r.reviewText : null,
    skin_type: typeof r.skinType === 'string' && SKIN_TYPES.has(r.skinType) ? (r.skinType as SkinType) : null,
  };
}

/** 응답이 배열이든 `{ items | content | reviews: [...] }` 로 감싸였든 행 배열을 꺼낸다 */
function rowsOf(json: unknown): unknown[] | null {
  if (Array.isArray(json)) return json;
  if (json && typeof json === 'object') {
    const o = json as Record<string, unknown>;
    for (const k of ['items', 'content', 'reviews']) if (Array.isArray(o[k])) return o[k] as unknown[];
  }
  return null;
}

export async function fetchSellerReviews(brandId: string): Promise<SellerReviewsRead> {
  const q = new URLSearchParams({ brandId });
  try {
    const res = await authFetch('SELLER', `/api/seller/reviews?${q.toString()}`);
    if (!res.ok) return { kind: 'unavailable' };
    const rows = rowsOf(await res.json());
    if (rows === null) return { kind: 'unavailable' };
    return { kind: 'ready', rows: rows.map(asRow).filter((r): r is SellerReview => r !== null) };
  } catch {
    return { kind: 'unavailable' };
  }
}
