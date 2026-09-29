import type { ReactNode } from 'react';

/** 약관·방침의 한 조항. id 는 목차 앵커로 쓴다 */
export interface LegalSection {
  id: string;
  title: string;
  body: ReactNode;
}

export interface LegalDocumentProps {
  title: string;
  /** 문서 판. 바뀌면 올린다 */
  version: string;
  /** 시행일 (YYYY-MM-DD) */
  effectiveDate: string;
  intro?: ReactNode;
  sections: LegalSection[];
}

/**
 * 이용약관·개인정보처리방침이 같이 쓰는 틀. 목차 + 조항 + 시행일.
 * 목차 링크는 주소를 바꾸지 않고 해당 조항으로 스크롤만 한다 — `#id` 로 이동하면
 * 쿼리(`?terms=1`)가 유지되긴 하지만 히스토리 항목이 하나 늘어 뒤로가기가 두 번 필요해진다.
 */
export default function LegalDocument({ title, version, effectiveDate, intro, sections }: LegalDocumentProps) {
  return (
    <main className="legal">
      <header className="legal__head">
        <h1 className="legal__title">{title}</h1>
        <p className="legal__meta">
          시행일 {effectiveDate} · {version}
        </p>
        {intro ? <div className="legal__intro">{intro}</div> : null}
      </header>

      <nav className="legal__toc" aria-label="목차">
        <ol>
          {sections.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }}
              >
                {section.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="legal__body">
        {sections.map((section) => (
          <section key={section.id} id={section.id} className="legal__section">
            <h2>{section.title}</h2>
            {section.body}
          </section>
        ))}
      </div>

      <p className="legal__foot">
        이 문서는 {effectiveDate}부터 적용합니다. ({version})
      </p>
    </main>
  );
}
