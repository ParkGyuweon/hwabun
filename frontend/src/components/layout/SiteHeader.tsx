import AccountMenu from '../auth/AccountMenu';
import NotificationBell from '../notifications/NotificationBell';
import PersonaSwitcher from './PersonaSwitcher';
import { isDevtoolsOn } from '../../lib/devtools';
import type { PersonaProfile } from '../../types/persona';

interface SiteHeaderProps {
  personas: PersonaProfile[];
  persona: PersonaProfile | null;
  onPersonaChange: (personaId: string) => void;
  /** 로고를 누르면 상품 목록으로 */
  onHome: () => void;
  /** 장바구니에 담긴 총 수량 */
  cartCount: number;
  onCart: () => void;
  /** 소상공인이 가입할 때 적은 브랜드 이름. 비어 있으면 BLOOM 워드마크 */
  brandName?: string;
  /** 알림(의견 확인·답변·반영)을 누르면 그 상품 상세로 */
  onOpenProduct: (productId: string) => void;
}

/**
 * BLOOM 상단 바.
 *
 * 계정 자리에는 둘이 나란히 있다. 페르소나는 행동 로그의 주체(시뮬레이션 신원)이고,
 * 로그인 계정(AccountMenu)은 백엔드 주문·리뷰·피드백의 주체다. 로그인 없이도 둘러볼 수 있다.
 *
 * 카테고리 메뉴는 **여기 두지 않는다** (2026-09-17). 목록 화면 맨 위에 같은 중분류 탭이 상품 수까지 달고
 * 이미 있어서, 헤더의 같은 줄은 고르는 자리를 둘로 나누기만 했다. 어느 쪽을 눌렀느냐로 집계도 갈렸다.
 * 카테고리는 목록 탭 하나로 고른다.
 */
export default function SiteHeader({
  personas,
  persona,
  onPersonaChange,
  onHome,
  cartCount,
  onCart,
  brandName,
  onOpenProduct,
}: SiteHeaderProps) {
  return (
    <header className="site-header">
      {/* 상단 홍보 띠("취향이 피어나는 … 무료배송")는 2026-09-21 에 뗐다. 몰이 하나고 무료배송 약속도 실제 정책이 아니었다 */}
      <div className="site-header__main">
        <button type="button" className="site-header__logo" onClick={onHome} aria-label="BLOOM 홈">
          {/* 파비콘용으로 줄인 마크(192px). 표시 28px 라 충분하고 원본은 2450px 다 */}
          <img src="/brand/bloom-mark.png" alt="" width="28" height="28" />
          <span>{brandName || 'BLOOM'}</span>
        </button>

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
          {/* 페르소나 선택기는 개발·에이전트용. 고객에게는 로그인이 그 자리다 */}
          {isDevtoolsOn() ? (
            <PersonaSwitcher personas={personas} persona={persona} onPersonaChange={onPersonaChange} />
          ) : null}
          {/* 인앱 알림함. 로그인 전에는 안 그린다. 회원은 자기 의견의 확인·답변·반영 알림을 받는다 */}
          <NotificationBell
            role="MEMBER"
            onOpen={(n) => {
              if (n.payload?.productId) onOpenProduct(n.payload.productId);
            }}
          />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
