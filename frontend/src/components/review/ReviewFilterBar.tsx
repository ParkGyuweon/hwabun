import { track } from '../../lib/logger';
import type { PersonaProfile } from '../../types/persona';

export type ReviewFilter = 'all' | 'same_skin_type' | 'same_skin_tone' | 'recommended';
export type ReviewSort = 'recent' | 'rating-desc' | 'rating-asc';

interface ReviewFilterBarProps {
  persona: PersonaProfile | null;
  filter: ReviewFilter;
  onFilterChange: (value: ReviewFilter) => void;
  sort: ReviewSort;
  onSortChange: (value: ReviewSort) => void;
  resultCount: number;
}

/**
 * 리뷰 필터.
 *
 * 세포라 데이터의 가장 큰 강점이 리뷰 작성자의 피부 프로필이라서
 * "나와 같은 피부 타입" 필터를 전면에 둔다.
 * 이 필터를 쓰는 행동은 일반 스크롤보다 훨씬 강한 관심 신호다.
 *
 * eye_color 에 Grey 와 gray 가 섞여 있어(정규화 전) 눈/머리색 필터는 아직 노출하지 않는다.
 */
export default function ReviewFilterBar({
  persona,
  filter,
  onFilterChange,
  sort,
  onSortChange,
  resultCount,
}: ReviewFilterBarProps) {
  const options: Array<{ value: ReviewFilter; label: string; disabled?: boolean }> = [
    { value: 'all', label: '전체' },
    { value: 'same_skin_type', label: '나와 같은 피부 타입', disabled: !persona },
    { value: 'same_skin_tone', label: '피부 톤 유사', disabled: !persona },
    { value: 'recommended', label: '추천 리뷰' },
  ];

  const apply = (value: ReviewFilter) => {
    if (value === filter) return;
    onFilterChange(value);
    track('review_filter_apply', {
      filter: value,
      persona_skin_type: persona?.skin_type ?? null,
      persona_skin_tone: persona?.skin_tone ?? null,
    });
  };

  const changeSort = (value: ReviewSort) => {
    if (value === sort) return;
    onSortChange(value);
    track('review_filter_apply', { sort: value });
  };

  return (
    <div className="review-filter">
      <div className="review-filter__chips" role="group" aria-label="리뷰 필터">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={filter === option.value ? 'is-active' : ''}
            disabled={option.disabled}
            data-log-action="review_filter_apply"
            onClick={() => apply(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="review-filter__right">
        <span className="review-filter__count">{resultCount}건</span>
        <label className="review-filter__sort">
          <span className="sr-only">리뷰 정렬</span>
          <select value={sort} onChange={(event) => changeSort(event.target.value as ReviewSort)}>
            <option value="recent">최신순</option>
            <option value="rating-desc">평점 높은순</option>
            <option value="rating-asc">평점 낮은순</option>
          </select>
        </label>
      </div>
    </div>
  );
}
