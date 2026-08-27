interface EmptyStateProps {
  message: string;
}

/**
 * suitable_skin_types 처럼 빈 배열이 흔한 필드용.
 * 섹션 자체를 숨기지 않고 비어 있다는 사실을 드러낸다.
 */
export default function EmptyState({ message }: EmptyStateProps) {
  return <p className="empty-state">{message}</p>;
}
