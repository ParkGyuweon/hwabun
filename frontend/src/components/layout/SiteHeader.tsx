import PersonaSwitcher from './PersonaSwitcher';
import type { PersonaProfile } from '../../types/persona';

interface SiteHeaderProps {
  personas: PersonaProfile[];
  persona: PersonaProfile | null;
  onPersonaChange: (personaId: string) => void;
  /** 로고를 누르면 상품 목록으로 */
  onHome: () => void;
  /** 데이터에 실제로 존재하는 카테고리. 없는 메뉴를 걸어두지 않는다 */
  categories: string[];
  onCategorySelect: (category: string) => void;
  /** 장바구니에 담긴 총 수량 */
  cartCount: number;
  onCart: () => void;
}

/**
 * BLOOM 상단 바.
 *
 * 계정 자리에는 접속 중인 페르소나를 올린다. 이 사이트에서는 페르소나가 곧 사용자다.
 *
 * 카테고리 메뉴는 **데이터에 실제로 있는 값만** 건다.
 * 처음에는 Makeup·Hair 같은 항목을 span 으로 두었는데 두 가지 문제가 있었다.
 *
 * 1. 우리 상품 200개는 전부 Skincare 라 그 메뉴에 보여줄 것이 없다.
 * 2. span 은 눌러도 아무 일이 없어서 **누를 때마다 `dead_click` 이 찍혔다.**
 *    좌절 신호는 감점(-1.5)으로 들어가는데, 헤더를 누르는 건 자연스러운 행동이다.
 *    그걸 "이 상품에 좌절했다" 로 기록하면 추천이 틀어진다.
 */
export default function SiteHeader({
  personas,
  persona,
  onPersonaChange,
  onHome,
  categories,
  onCategorySelect,
  cartCount,
  onCart,
}: SiteHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header__promo">
        <strong>취향이 피어나는 뷰티 쇼핑 공간</strong> · 오늘 담은 상품은 무료배송{' '}
        <span className="site-header__promo-terms">*3만원 이상 · 기간 한정</span>
      </div>

      <div className="site-header__main">
        <button type="button" className="site-header__logo" onClick={onHome} aria-label="BLOOM 홈">
          {/* 파비콘용으로 줄인 마크(192px). 표시 28px 라 충분하고 원본은 2450px 다 */}
          <img src="/brand/bloom-mark.png" alt="" width="28" height="28" />
          <span>BLOOM</span>
        </button>

        <nav className="site-header__nav" aria-label="주요 카테고리">
          {categories.map((category) => (
            <button key={category} type="button" onClick={() => onCategorySelect(category)}>
              {category}
            </button>
          ))}
        </nav>

        <div className="site-header__account">
          <button
            type="button"
            className="site-header__basket"
            data-log-action="view_cart"
            onClick={onCart}
          >
            장바구니
            <span className="site-header__basket-count">{cartCount}</span>
          </button>
          <PersonaSwitcher personas={personas} persona={persona} onPersonaChange={onPersonaChange} />
        </div>
      </div>
    </header>
  );
}
