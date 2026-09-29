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
            홈
          </button>
        </li>
        {/*
          중간 분류는 글자로만 둔다. 예전에는 `<a href="#">` 라 누르면 맨 위로 튀고 주소에 # 만 붙었다 —
          분류별 목록 화면이 따로 없어서 갈 곳이 없다.
        */}
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>
            <span aria-current={index === items.length - 1 ? 'page' : undefined}>{item}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
