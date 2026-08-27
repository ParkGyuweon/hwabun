import { useMemo, useState } from 'react';
import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';
import { splitIngredients } from '../../lib/format';
import { track } from '../../lib/logger';

interface IngredientsSectionProps {
  ingredients: string[];
  productId: string;
}

const CHIP_PREVIEW_COUNT = 12;

/**
 * 성분 영역.
 *
 * 원본은 원소 하나에 전 성분이 쉼표로 이어붙은 통짜 문자열이라
 * 원문 그대로 보기와 칩으로 나눠 보기를 모두 제공한다.
 * 성분에 민감한 유저를 구분하는 데 쓰이는 구간이라 조작 로그를 남긴다.
 */
export default function IngredientsSection({ ingredients, productId }: IngredientsSectionProps) {
  const [mode, setMode] = useState<'chip' | 'raw'>('chip');
  const [expanded, setExpanded] = useState(false);

  const parsed = useMemo(() => splitIngredients(ingredients), [ingredients]);

  if (parsed.length === 0) {
    return <EmptyState message="등록된 성분 정보가 없습니다." />;
  }

  const visible = expanded ? parsed : parsed.slice(0, CHIP_PREVIEW_COUNT);
  const hidden = parsed.length - visible.length;

  const changeMode = (next: 'chip' | 'raw') => {
    if (next === mode) return;
    setMode(next);
    track('ingredient_view_mode_change', { product_id: productId, mode: next });
  };

  const showAll = () => {
    setExpanded(true);
    track('review_expand', {
      product_id: productId,
      target: 'ingredients',
      revealed_count: hidden,
    });
  };

  return (
    <div className="ingredients" data-log-content="ingredient_list" data-log-ref="full">
      <div className="ingredients__toolbar">
        <span className="ingredients__count">총 {parsed.length}개 성분</span>
        <div className="segmented" role="group" aria-label="성분 표시 방식">
          <button
            type="button"
            className={mode === 'chip' ? 'is-active' : ''}
            data-log-action="ingredient_view_chip"
            onClick={() => changeMode('chip')}
          >
            나눠 보기
          </button>
          <button
            type="button"
            className={mode === 'raw' ? 'is-active' : ''}
            data-log-action="ingredient_view_raw"
            onClick={() => changeMode('raw')}
          >
            원문 보기
          </button>
        </div>
      </div>

      {mode === 'chip' ? (
        <>
          <ul className="chip-list">
            {visible.map((item, index) => (
              <li key={`${item}-${index}`}>
                <Chip tone="muted">{item}</Chip>
              </li>
            ))}
          </ul>
          {hidden > 0 ? (
            <button type="button" className="link-button" data-log-action="ingredient_expand" onClick={showAll}>
              성분 {hidden}개 더 보기
            </button>
          ) : null}
        </>
      ) : (
        /* 여러 원소가 있는 상품은 원소마다 문단으로 나눈다 */
        <div className="ingredients__raw">
          {ingredients.map((block, index) => (
            <p key={index}>{block}</p>
          ))}
        </div>
      )}
    </div>
  );
}
