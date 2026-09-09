import EmptyState from '../common/EmptyState';
import { highlightKo } from '../../lib/localize';

interface HighlightGridProps {
  highlights: string[];
}

/**
 * 세포라의 Highlights 영역.
 *
 * 원본은 아이콘 + 문구 그리드인데, 데이터에 아이콘 정보가 없어서
 * 문구의 첫 글자를 대신 넣고 배지 모양만 맞춘다.
 */
export default function HighlightGrid({ highlights }: HighlightGridProps) {
  if (highlights.length === 0) {
    return <EmptyState message="등록된 하이라이트가 없습니다." />;
  }

  return (
    <ul className="highlight-grid" data-log-content="highlight_badge">
      {highlights.map((item) => (
        <li key={item}>
          <span className="highlight-grid__icon" aria-hidden="true">
            {item.trim().charAt(0).toUpperCase()}
          </span>
          <span className="highlight-grid__label">{highlightKo(item)}</span>
        </li>
      ))}
    </ul>
  );
}
