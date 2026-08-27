interface BreadcrumbProps {
  /** category 는 길이 2~3 가변이라 인덱스로 접근하지 않고 그대로 순회한다 */
  items: string[];
}

export default function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav className="breadcrumb" aria-label="카테고리 경로" data-log-content="navigation">
      <ol>
        <li>
          <a href="#">Home</a>
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
