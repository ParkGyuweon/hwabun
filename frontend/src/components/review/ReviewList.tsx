import ReviewCard from './ReviewCard';
import EmptyState from '../common/EmptyState';
import type { Review } from '../../types/review';

interface ReviewListProps {
  reviews: Review[];
  /** author_id -> 샘플 전체에서 이 작성자가 남긴 리뷰 수 */
  authorReviewCounts: Map<string, number>;
}

export default function ReviewList({ reviews, authorReviewCounts }: ReviewListProps) {
  if (reviews.length === 0) {
    return <EmptyState message="선택한 조건에 해당하는 리뷰가 없습니다." />;
  }

  return (
    <div className="review-list">
      {reviews.map((review) => (
        <ReviewCard
          key={review.review_id}
          review={review}
          otherReviewCount={Math.max(0, (authorReviewCounts.get(review.author_id) ?? 1) - 1)}
        />
      ))}
    </div>
  );
}
