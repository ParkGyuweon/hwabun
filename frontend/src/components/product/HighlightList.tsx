import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';

interface HighlightListProps {
  highlights: string[];
}

export default function HighlightList({ highlights }: HighlightListProps) {
  if (highlights.length === 0) {
    return <EmptyState message="등록된 하이라이트가 없습니다." />;
  }

  return (
    <ul className="chip-list">
      {highlights.map((item) => (
        <li key={item}>
          <Chip>{item}</Chip>
        </li>
      ))}
    </ul>
  );
}
