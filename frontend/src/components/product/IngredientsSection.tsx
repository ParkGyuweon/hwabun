import { useMemo, useState } from 'react';
import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';
import { splitIngredients } from '../../lib/format';

interface IngredientsSectionProps {
  ingredients: string[];
}

const CHIP_PREVIEW_COUNT = 12;

/**
 * 성분 영역.
 *
 * 원본은 원소 하나에 전 성분이 쉼표로 이어붙은 통짜 문자열이라
 * 원문 그대로 보기와 칩으로 나눠 보기를 모두 제공한다.
 */
export default function IngredientsSection({ ingredients }: IngredientsSectionProps) {
  const [mode, setMode] = useState<'chip' | 'raw'>('chip');
  const [expanded, setExpanded] = useState(false);

  const parsed = useMemo(() => splitIngredients(ingredients), [ingredients]);

  if (parsed.length === 0) {
    return <EmptyState message="등록된 성분 정보가 없습니다." />;
  }

  const visible = expanded ? parsed : parsed.slice(0, CHIP_PREVIEW_COUNT);
  const hidden = parsed.length - visible.length;

  return (
    <div className="ingredients">
      <div className="ingredients__toolbar">
        <span className="ingredients__count">총 {parsed.length}개 성분</span>
        <div className="segmented" role="group" aria-label="성분 표시 방식">
          <button
            type="button"
            className={mode === 'chip' ? 'is-active' : ''}
            onClick={() => setMode('chip')}
          >
            나눠 보기
          </button>
          <button
            type="button"
            className={mode === 'raw' ? 'is-active' : ''}
            onClick={() => setMode('raw')}
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
            <button type="button" className="link-button" onClick={() => setExpanded(true)}>
              성분 {hidden}개 더 보기
            </button>
          ) : null}
        </>
      ) : (
        <p className="ingredients__raw">{ingredients.join('\n\n')}</p>
      )}
    </div>
  );
}
