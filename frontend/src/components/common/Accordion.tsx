import { useState } from 'react';
import type { ReactNode } from 'react';

interface AccordionProps {
  title: string;
  /** 접힌 상태에서 제목 옆에 보여줄 보조 텍스트 */
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * 성분처럼 길이가 긴 섹션을 접어두기 위한 컴포넌트.
 *
 * 펼침 동작은 이후 로그 수집 대상이 된다.
 * 이벤트 이름과 payload 는 [정의] UX 행동 로그 이벤트 명세 확정 이슈에서 결정하므로
 * 지금은 onToggle 이라는 확장 지점만 열어둔다.
 */
export default function Accordion({ title, hint, defaultOpen = false, children }: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="accordion">
      <button
        type="button"
        className="accordion__head"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="accordion__title">{title}</span>
        {hint ? <span className="accordion__hint">{hint}</span> : null}
        <span className="accordion__icon" aria-hidden="true">
          {open ? '−' : '+'}
        </span>
      </button>
      {open ? <div className="accordion__body">{children}</div> : null}
    </section>
  );
}
