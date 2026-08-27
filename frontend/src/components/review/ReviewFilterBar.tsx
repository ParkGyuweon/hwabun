import { skinTypeLabel } from '../../lib/format';
import type { SkinType } from '../../types/product';

export type ReviewSort = 'recent' | 'rating-desc' | 'rating-asc';

interface ReviewFilterBarProps {
  skinTypes: SkinType[];
  selectedSkinType: SkinType | 'all';
  onSkinTypeChange: (value: SkinType | 'all') => void;
  sort: ReviewSort;
  onSortChange: (value: ReviewSort) => void;
  resultCount: number;
}

/**
 * 리뷰 필터.
 *
 * 세포라는 피부 타입 외에 skin_tone / eye_color / hair_color 필터도 제공하지만,
 * eye_color 에 Grey 와 gray 가 섞여 있어(정규화 전) 우선 skin_type 만 노출한다.
 */
export default function ReviewFilterBar({
  skinTypes,
  selectedSkinType,
  onSkinTypeChange,
  sort,
  onSortChange,
  resultCount,
}: ReviewFilterBarProps) {
  return (
    <div className="review-filter">
      <div className="review-filter__chips" role="group" aria-label="피부 타입 필터">
        <button
          type="button"
          className={selectedSkinType === 'all' ? 'is-active' : ''}
          onClick={() => onSkinTypeChange('all')}
        >
          전체
        </button>
        {skinTypes.map((type) => (
          <button
            key={type}
            type="button"
            className={selectedSkinType === type ? 'is-active' : ''}
            onClick={() => onSkinTypeChange(type)}
          >
            {skinTypeLabel(type)}
          </button>
        ))}
      </div>

      <div className="review-filter__right">
        <span className="review-filter__count">{resultCount}건</span>
        <label className="review-filter__sort">
          <span className="sr-only">리뷰 정렬</span>
          <select value={sort} onChange={(event) => onSortChange(event.target.value as ReviewSort)}>
            <option value="recent">최신순</option>
            <option value="rating-desc">평점 높은순</option>
            <option value="rating-asc">평점 낮은순</option>
          </select>
        </label>
      </div>
    </div>
  );
}
