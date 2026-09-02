import { useEffect, useState } from 'react';
import { LAYOUTS, THEMES, applyTheme } from './lib/prefs';
import type { LayoutKey, Prefs, ThemeKey } from './lib/prefs';
import { MotifLine } from './components';

/**
 * 첫 진입 화면 — 레이아웃과 색을 고른다.
 *
 * 고르는 동안 테마를 실제 문서에 바로 건다. 미리보기 카드만 바뀌면 "실제로는
 * 어떻게 보일까" 를 한 번 더 상상해야 한다. 카드 뒤 배경까지 함께 바뀌면 그 단계가 없다.
 *
 * 나중에 다시 열 수 있다(사이드바 하단 "화면 설정"). 그래서 `initial` 을 받는다.
 */
export default function Onboarding({
  initial,
  onDone,
  onCancel,
}: {
  initial: Prefs;
  onDone: (prefs: Prefs) => void;
  /** 설정 변경으로 열었을 때만 있다. 첫 진입에는 취소가 없다 */
  onCancel?: () => void;
}) {
  const [layout, setLayout] = useState<LayoutKey>(initial.layout);
  const [theme, setTheme] = useState<ThemeKey>(initial.theme);
  const [brandName, setBrandName] = useState(initial.brandName);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <div className="onboard">
      <div className="onboard__card">
        <header className="onboard__head">
          <img src="/brand/hwabun-mark.png" alt="" width="40" height="40" />
          <div>
            <p className="onboard__eyebrow">HWABUN · 화분</p>
            <h1>브랜드에 맞는 화면으로 시작합니다</h1>
            <p className="onboard__lead">
              50개 브랜드가 같은 데이터를 나눠 쓰지만, 보는 화면은 각자 다를 수 있습니다.
              레이아웃과 색을 고르세요. 나중에 언제든 바꿀 수 있습니다.
            </p>
          </div>
        </header>

        <MotifLine variant="divider" />

        <section className="onboard__section">
          <h2>
            <span className="onboard__step">1</span> 브랜드 이름
          </h2>
          <input
            className="onboard__input"
            type="text"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
            placeholder="예: 그린 티 랩"
            maxLength={40}
            aria-label="브랜드 이름"
          />
          <p className="onboard__hint">사이드바 상단에 표시됩니다. 비워도 됩니다.</p>
        </section>

        <section className="onboard__section">
          <h2>
            <span className="onboard__step">2</span> 레이아웃
          </h2>
          <div className="onboard__grid onboard__grid--3">
            {LAYOUTS.map((l) => (
              <button
                key={l.key}
                type="button"
                className={`onboard__opt ${layout === l.key ? 'is-active' : ''}`}
                onClick={() => setLayout(l.key)}
                aria-pressed={layout === l.key}
              >
                <LayoutThumb layout={l.key} />
                <strong>{l.label}</strong>
                <span>{l.desc}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="onboard__section">
          <h2>
            <span className="onboard__step">3</span> 색
          </h2>
          <div className="onboard__grid onboard__grid--5">
            {THEMES.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`onboard__opt onboard__opt--theme ${theme === t.key ? 'is-active' : ''}`}
                onClick={() => setTheme(t.key)}
                aria-pressed={theme === t.key}
              >
                <span className="onboard__swatch" aria-hidden="true">
                  {t.swatch.map((c) => (
                    <i key={c} style={{ background: c }} />
                  ))}
                </span>
                <strong>{t.label}</strong>
                <span>{t.desc}</span>
              </button>
            ))}
          </div>
          <p className="onboard__hint">
            어느 테마를 골라도 실측/모의 배지와 감점·경고 표시는 같은 색으로 유지됩니다.
          </p>
        </section>

        <footer className="onboard__foot">
          {onCancel ? (
            <button type="button" className="onboard__btn onboard__btn--ghost" onClick={onCancel}>
              취소
            </button>
          ) : null}
          <button
            type="button"
            className="onboard__btn"
            onClick={() => onDone({ layout, theme, brandName: brandName.trim() })}
          >
            {onCancel ? '적용' : '시작하기'}
          </button>
        </footer>
      </div>
    </div>
  );
}

/** 레이아웃 미니어처. 실제 화면 구조를 도형으로 그린다 */
function LayoutThumb({ layout }: { layout: LayoutKey }) {
  return (
    <span className={`lthumb lthumb--${layout}`} aria-hidden="true">
      <i className="lthumb__nav" />
      <i className="lthumb__main">
        <b />
        <b />
        <b />
      </i>
    </span>
  );
}
