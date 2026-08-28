interface BreadcrumbProps {
  /** category 는 길이 2~3 가변이라 인덱스로 접근하지 않고 그대로 순회한다 */
  items: string[];
  /** 목록으로 돌아간다 */
  onHome: () => void;
}

export default function Breadcrumb({ items, onHome }: BreadcrumbProps) {
  return (
    <nav className="breadcrumb" aria-label="카테고리 경로" data-log-content="navigation">
      <ol>
        <li>
          <button type="button" className="breadcrumb__home" onClick={onHome}>
            Home
          </button>
        </li>
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>
            {index === items.length - 1 ? <span aria-current="page">{item}</span> : <a href="#">{item}</a>}
          </li>
        ))}
      </ol>
    </nav>
  );
}
