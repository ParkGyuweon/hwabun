import { useState } from 'react';
import StarRating from '../common/StarRating';
import { formatDate, humanizeAttribute, skinTypeLabel } from '../../lib/format';
import { track } from '../../lib/logger';
import type { PersonaProfile } from '../../types/persona';
import type { Review } from '../../types/review';

/** 이 길이를 넘으면 접어두고 더보기를 노출한다 */
const CLAMP_LENGTH = 180;

interface ReviewCardProps {
  review: Review;
  persona: PersonaProfile | null;
  /** 이 작성자가 샘플 안에서 남긴 다른 리뷰 수 */
  otherReviewCount: number;
}

/**
 * 리뷰 카드.
 *
 * review_title 은 약 31% 가 null 이라 제목 없는 레이아웃이 기본 형태에 가깝다.
 * 피부 프로필은 페르소나 대표값이 아니라 그 리뷰가 작성될 당시의 값을 그대로 보여준다.
 */
export default function ReviewCard({ review, persona, otherReviewCount }: ReviewCardProps) {
  const [expanded, setExpanded] = useState(false);

  const text = review.review_text ?? '';
  const needsClamp = text.length > CLAMP_LENGTH;
  const shown = needsClamp && !expanded ? `${text.slice(0, CLAMP_LENGTH)}…` : text;

  const sameSkinType = persona?.skin_type === review.skin_type;

  const attributes = [
    ['피부 타입', skinTypeLabel(review.skin_type)],
    ['피부 톤', humanizeAttribute(review.skin_tone)],
    ['눈동자', humanizeAttribute(review.eye_color)],
    ['머리색', humanizeAttribute(review.hair_color)],
  ];

  const expand = () => {
    setExpanded(true);
    track('review_expand', {
      review_id: review.review_id,
      product_id: review.product_id,
      target: 'review_text',
    });
  };

  return (
    <article className="review-card">
      <header className="review-card__head">
        <div className="review-card__author">
          <span className="review-card__avatar" aria-hidden="true">
            {review.author_id.slice(-2)}
          </span>
          <div>
            <p className="review-card__id">
              사용자 {review.author_id.slice(0, 6)}···
              {sameSkinType ? <span className="review-card__badge">같은 피부 타입</span> : null}
            </p>
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
      {shown ? <p className="review-card__text">{shown}</p> : null}

      {needsClamp && !expanded ? (
        <button type="button" className="link-button" data-log-action="review_expand" onClick={expand}>
          더 보기
        </button>
      ) : null}

      <footer className="review-card__foot">
        {review.is_recommended !== null ? (
          <span className={`review-card__recommend${review.is_recommended ? ' is-yes' : ''}`}>
            {review.is_recommended ? '✓ 이 상품을 추천합니다' : '이 상품을 추천하지 않습니다'}
          </span>
        ) : null}
        {otherReviewCount > 0 ? (
          <span className="review-card__other">이 리뷰어의 다른 리뷰 {otherReviewCount}건</span>
        ) : null}
      </footer>
    </article>
  );
}
