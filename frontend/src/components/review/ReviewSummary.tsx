import StarRating from '../common/StarRating';
import type { ReviewStats } from '../../lib/format';

interface ReviewSummaryProps {
  stats: ReviewStats;
  /** 상품 데이터에 실린 전체 리뷰 수. 샘플에는 상품당 5건만 들어있다 */
  totalReviewCount: number | null;
}

export default function ReviewSummary({ stats, totalReviewCount }: ReviewSummaryProps) {
  const scores = [5, 4, 3, 2, 1];

  return (
    <div className="review-summary" data-log-content="review_stats">
      <div className="review-summary__score">
        <strong>{stats.average.toFixed(2)}</strong>
        <StarRating value={stats.average} size="lg" />
        <p>
          표시 중인 리뷰 {stats.total}건
          {totalReviewCount !== null ? ` / 전체 ${totalReviewCount.toLocaleString('en-US')}건` : ''}
        </p>
        {stats.recommendRate !== null ? (
          <p className="review-summary__recommend">
            <strong>{stats.recommendRate}%</strong> 가 이 상품을 추천합니다
          </p>
        ) : null}
      </div>

      <ul className="review-summary__dist">
        {scores.map((score, index) => {
          const count = stats.distribution[index];
          const percent = stats.total ? (count / stats.total) * 100 : 0;
          return (
            <li key={score}>
              <span className="review-summary__dist-label">{score}점</span>
              <span className="review-summary__dist-bar">
                <span style={{ width: `${percent}%` }} />
              </span>
              <span className="review-summary__dist-count">{count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
