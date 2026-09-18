import StarRating from '../common/StarRating';
import type { ReviewStats } from '../../lib/format';

interface ReviewSummaryProps {
  stats: ReviewStats;
  /**
   * 이 상품이 가진 리뷰 수 (`lib/reviewStore.displayReviewCount`).
   *
   * 화면이 그리는 건수(`stats.total`)와 **같은 것이 정상**이다. 다를 때만 둘 다 적는다 — 백엔드 상품처럼
   * 목록을 다 받지 못하는 경우가 있다. 전에는 여기에 원천 사이트의 리뷰 수(16,118 같은 값)가 들어와
   * 카드와 상세가 늘 어긋나 보였다 (2026-09-18).
   */
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
          {totalReviewCount !== null && totalReviewCount !== stats.total
            ? `표시 중인 리뷰 ${stats.total}건 / 전체 ${totalReviewCount.toLocaleString('en-US')}건`
            : `리뷰 ${stats.total.toLocaleString('en-US')}건`}
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
