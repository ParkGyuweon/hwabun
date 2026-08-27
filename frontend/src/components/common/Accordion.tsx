import { useState } from 'react';
import type { ReactNode } from 'react';
import { track } from '../../lib/logger';
import type { LogSection } from '../../types/log';

interface AccordionProps {
  title: string;
  /** 접힌 상태에서 제목 옆에 보여줄 보조 텍스트 */
  hint?: string;
  defaultOpen?: boolean;
  /** 어느 섹션의 아코디언인지. accordion_toggle 로그에 실린다 */
  sectionId: LogSection;
  children: ReactNode;
}

/**
 * 성분·사용법처럼 접어두는 섹션.
 *
 * 펼치는 행동은 단순 스크롤보다 훨씬 강한 관심 신호라서 열고 닫음을 구분해 기록한다.
 */
export default function Accordion({
  title,
  hint,
  defaultOpen = false,
  sectionId,
  children,
}: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    track('accordion_toggle', { section_id: sectionId, action: next ? 'expand' : 'collapse' });
  };

  return (
    <div className="accordion">
      <button
        type="button"
        className="accordion__head"
        aria-expanded={open}
        data-log-action="accordion_toggle"
        onClick={toggle}
      >
        <span className="accordion__title">{title}</span>
        {hint ? <span className="accordion__hint">{hint}</span> : null}
        <span className="accordion__icon" aria-hidden="true">
          {open ? '−' : '+'}
        </span>
      </button>
      {open ? <div className="accordion__body">{children}</div> : null}
    </div>
  );
}
