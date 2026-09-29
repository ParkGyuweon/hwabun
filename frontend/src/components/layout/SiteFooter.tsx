import type { MouseEvent } from 'react';
import type { LegalPage } from '../../lib/legalRoute';

/**
 * 쇼핑몰 하단. 약관 두 개와 운영 주체 안내.
 *
 * 사업자등록번호 같은 칸은 일부러 두지 않는다. 시연용 몰이라 채울 값이 없고,
 * 그럴듯한 가짜 번호를 넣으면 실제 사업자처럼 보인다.
 */
export default function SiteFooter({ onOpenLegal }: { onOpenLegal: (page: LegalPage) => void }) {
  const open = (page: LegalPage) => (event: MouseEvent<HTMLAnchorElement>) => {
    // 새 탭 열기(Ctrl/⌘·가운데 클릭)는 브라우저에 맡긴다
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onOpenLegal(page);
  };

  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <nav className="site-footer__links" aria-label="약관">
          <a href="?terms=1" onClick={open('terms')}>
            이용약관
          </a>
          <a href="?privacy=1" onClick={open('privacy')} className="site-footer__privacy">
            개인정보처리방침
          </a>
        </nav>
        <div className="site-footer__info">
          <p className="site-footer__brand">BLOOM</p>
          <p>SSAFY 15기 프로젝트 시연용 쇼핑몰 · 실제로 판매하지 않습니다.</p>
          <p>주문과 결제는 테스트로만 진행되며 실제 청구가 없습니다.</p>
        </div>
      </div>
    </footer>
  );
}
