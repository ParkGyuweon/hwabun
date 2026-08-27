import ReviewCard from './ReviewCard';
import EmptyState from '../common/EmptyState';
import type { PersonaProfile } from '../../types/persona';
import type { Review } from '../../types/review';

interface ReviewListProps {
  reviews: Review[];
  persona: PersonaProfile | null;
  /** author_id -> 샘플 전체에서 이 작성자가 남긴 리뷰 수 */
  authorReviewCounts: Map<string, number>;
}

export default function ReviewList({ reviews, persona, authorReviewCounts }: ReviewListProps) {
  if (reviews.length === 0) {
    return <EmptyState message="선택한 조건에 해당하는 리뷰가 없습니다." />;
  }

  return (
    <div className="review-list">
      {reviews.map((review) => (
        // author_id + product_id 는 중복될 수 있어 review_id 를 키로 쓴다
        <ReviewCard
          key={review.review_id}
          review={review}
          persona={persona}
          otherReviewCount={Math.max(0, (authorReviewCounts.get(review.author_id) ?? 1) - 1)}
        />
      ))}
    </div>
  );
}
