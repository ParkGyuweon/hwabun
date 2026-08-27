interface StarRatingProps {
  /** 0 ~ 5 */
  value: number;
  size?: 'sm' | 'md' | 'lg';
}

/**
 * 소수점 평점을 그라디언트로 부분 채움 처리한 별점.
 */
export default function StarRating({ value, size = 'md' }: StarRatingProps) {
  const percent = Math.max(0, Math.min(100, (value / 5) * 100));

  return (
    <span className={`stars stars--${size}`} role="img" aria-label={`5점 만점에 ${value.toFixed(2)}점`}>
      <span className="stars__track" aria-hidden="true">
        ★★★★★
      </span>
      <span className="stars__fill" style={{ width: `${percent}%` }} aria-hidden="true">
        ★★★★★
      </span>
    </span>
  );
}
