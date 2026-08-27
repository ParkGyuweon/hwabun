import StarRating from '../common/StarRating';
import { formatDate, humanizeAttribute, skinTypeLabel } from '../../lib/format';
import type { Review } from '../../types/review';

interface ReviewCardProps {
  review: Review;
  /** 이 작성자가 샘플 안에서 남긴 다른 리뷰 수 */
  otherReviewCount: number;
}

/**
 * 리뷰 카드.
 *
 * review_title 은 약 31% 가 null 이라 제목 없는 레이아웃이 기본 형태에 가깝다.
 */
export default function ReviewCard({ review, otherReviewCount }: ReviewCardProps) {
  const attributes = [
    ['피부 타입', skinTypeLabel(review.skin_type)],
    ['피부 톤', humanizeAttribute(review.skin_tone)],
    ['눈동자', humanizeAttribute(review.eye_color)],
    ['머리색', humanizeAttribute(review.hair_color)],
  ];

  return (
    <article className="review-card">
      <header className="review-card__head">
        <div className="review-card__author">
          <span className="review-card__avatar" aria-hidden="true">
            {review.author_id.slice(-2)}
          </span>
          <div>
            <p className="review-card__id">사용자 {review.author_id.slice(0, 6)}···</p>
            <p className="review-card__date">{formatDate(review.submission_time)}</p>
          </div>
        </div>
        <StarRating value={review.rating} size="sm" />
      </header>

      <ul className="review-card__attrs">
        {attributes.map(([label, value]) => (
          <li key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </li>
        ))}
      </ul>

      {review.review_title ? <h4 className="review-card__title">{review.review_title}</h4> : null}
      {review.review_text ? <p className="review-card__text">{review.review_text}</p> : null}

      <footer className="review-card__foot">
        {review.is_recommended !== null ? (
          <span className={`review-card__recommend${review.is_recommended ? ' is-yes' : ''}`}>
            {review.is_recommended ? '✓ 이 상품을 추천합니다' : '이 상품을 추천하지 않습니다'}
          </span>
        ) : null}
        {otherReviewCount > 0 ? (
          <button type="button" className="link-button">
            이 리뷰어의 다른 리뷰 {otherReviewCount}건 보기
          </button>
        ) : null}
      </footer>
    </article>
  );
}
