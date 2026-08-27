import PersonaSwitcher from './PersonaSwitcher';
import type { PersonaProfile } from '../../types/persona';

interface SiteHeaderProps {
  personas: PersonaProfile[];
  persona: PersonaProfile | null;
  onPersonaChange: (personaId: string) => void;
}

/**
 * 세포라 상단 바를 단순화한 형태.
 *
 * 검색·매장 영역은 이번 범위가 아니라 자리만 잡아둔다.
 * 계정 자리에는 접속 중인 페르소나를 올린다. 이 사이트에서는 페르소나가 곧 사용자다.
 */
export default function SiteHeader({ personas, persona, onPersonaChange }: SiteHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header__promo">
        <strong>Get up to 3 Free* Trial Sizes</strong> with min. spend.{' '}
        <strong>Use code SCOREMORE.</strong>{' '}
        <span className="site-header__promo-terms">*Terms apply. APP ONLY.</span>{' '}
        <strong>LEARN MORE ›</strong>
      </div>

      <div className="site-header__main">
        <span className="site-header__logo">SEPHORA</span>

        <nav className="site-header__nav" aria-label="주요 카테고리">
          <span>New</span>
          <span>Makeup</span>
          <span>Skincare</span>
          <span>Fragrance</span>
          <span>Hair</span>
          <span>Bath &amp; Body</span>
          <span>Brands</span>
        </nav>

        <div className="site-header__account">
          <PersonaSwitcher personas={personas} persona={persona} onPersonaChange={onPersonaChange} />
        </div>
      </div>
    </header>
  );
}
