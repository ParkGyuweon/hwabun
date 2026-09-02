import { useState } from 'react';
import { STOREFRONT_LAYOUTS, STOREFRONT_THEMES } from '../lib/storefront';
import type { StorefrontLayout, StorefrontPrefs, StorefrontTheme } from '../lib/storefront';
import { MotifLine } from './components';

/**
 * 가입 화면 — 내 쇼핑몰의 진열 레이아웃과 색을 고른다.
 *
 * 여기서 고르는 것은 **고객이 보는 쇼핑몰**이다. 대시보드는 사이드바 고정이고 색도 HWABUN 이다.
 * 그래서 미리보기는 쇼핑몰 와이어프레임이다 — 메뉴가 어디, 기획전이 어디, 상품 카드가
 * 몇 열로 서는지, 필터가 위인지 왼쪽인지. 고른 색은 미리보기의 CTA·배지에 바로 입는다.
 *
 * 나중에 다시 열 수 있다(사이드바 "쇼핑몰 설정"). 그래서 `initial` 을 받는다.
 */
export default function Onboarding({
  initial,
  onDone,
  onCancel,
}: {
  initial: StorefrontPrefs;
  onDone: (prefs: StorefrontPrefs) => void;
  /** 설정 변경으로 열었을 때만 있다. 가입 때는 취소가 없다 */
  onCancel?: () => void;
}) {
  const [layout, setLayout] = useState<StorefrontLayout>(initial.layout);
  const [theme, setTheme] = useState<StorefrontTheme>(initial.theme);
  const [brandName, setBrandName] = useState(initial.brandName);

  const swatch = STOREFRONT_THEMES.find((t) => t.key === theme)?.swatch ?? STOREFRONT_THEMES[0].swatch;

  return (
    <div className="onboard">
      <div className="onboard__card">
        <header className="onboard__head">
          <img src="/brand/hwabun-mark.png" alt="" width="40" height="40" />
          <div>
            <p className="onboard__eyebrow">HWABUN · 내 쇼핑몰 만들기</p>
            <h1>고객이 볼 쇼핑몰을 고릅니다</h1>
            <p className="onboard__lead">
              상품이 어떻게 진열될지, 어떤 색으로 보일지 정하세요. 데이터 수집과 분석은 어떤 진열을
              골라도 똑같이 됩니다. 나중에 바꿀 수 있고, 바꾸면 쇼핑몰에 바로 반영됩니다.
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
          <p className="onboard__hint">쇼핑몰 헤더와 대시보드 상단에 표시됩니다.</p>
        </section>

        <section className="onboard__section">
          <h2>
            <span className="onboard__step">2</span> 진열 레이아웃
          </h2>
          <div className="onboard__grid onboard__grid--3">
            {STOREFRONT_LAYOUTS.map((l) => (
              <button
                key={l.key}
                type="button"
                className={`onboard__opt ${layout === l.key ? 'is-active' : ''}`}
                onClick={() => setLayout(l.key)}
                aria-pressed={layout === l.key}
              >
                <StorefrontThumb layout={l.key} swatch={swatch} brandName={brandName} />
                <strong>{l.label}</strong>
                <span>{l.desc}</span>
                <small className="onboard__fit">{l.fit}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="onboard__section">
          <h2>
            <span className="onboard__step">3</span> 색
          </h2>
          <div className="onboard__grid onboard__grid--5">
            {STOREFRONT_THEMES.map((t) => (
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
          <p className="onboard__hint">위 레이아웃 미리보기의 버튼·배지 색이 고른 색으로 바뀝니다.</p>
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
            {onCancel ? '쇼핑몰에 적용' : '이 설정으로 시작'}
          </button>
        </footer>
      </div>
    </div>
  );
}

/**
 * 쇼핑몰 와이어프레임.
 *
 * 실제 쇼핑몰의 요소 이름을 그대로 적는다 — 메뉴 · 기획전 · 카테고리 · 필터 · 상품 카드.
 * 사장님이 고르는 것은 도형이 아니라 "내 상품이 어떻게 놓이는가" 다.
 * 색은 고른 테마의 스와치를 CSS 변수로 넘겨 CTA·배지·리본에 입힌다.
 */
function StorefrontThumb({
  layout,
  swatch,
  brandName,
}: {
  layout: StorefrontLayout;
  swatch: [string, string, string];
  brandName: string;
}) {
  const style = {
    '--t-brand': swatch[0],
    '--t-accent': swatch[1],
    '--t-soft': swatch[2],
  } as React.CSSProperties;
  const cards = layout === 'showcase' ? 2 : layout === 'catalog' ? 6 : 8;
  const heroCards = layout === 'showcase' ? 2 : 4;

  return (
    <span className={`sthumb sthumb--${layout}`} style={style} aria-hidden="true">
      <i className="sthumb__ribbon">무료배송 · 기간 한정</i>
      <i className="sthumb__header">
        <b className="sthumb__logo">
          <u />
          {brandName || 'BLOOM'}
        </b>
        <b className="sthumb__menu">
          <em>메뉴</em>
          <small>Moisturizers</small>
          <small>Treatments</small>
          <small>Cleansers</small>
        </b>
        <b className="sthumb__cart">장바구니</b>
      </i>
      <i className="sthumb__hero">
        <em>기획전</em>
        <b className="sthumb__hero-title">지금 주목할 상품</b>
        <span className="sthumb__row">
          {Array.from({ length: heroCards }, (_, k) => (
            <b key={k} className="sthumb__card">
              <u className="sthumb__img" />
              <small>상품명</small>
              <strong>₩28,000</strong>
            </b>
          ))}
        </span>
      </i>
      <i className="sthumb__body">
        <b className="sthumb__side">
          <em>{layout === 'catalog' ? '카테고리 · 필터' : '카테고리'}</em>
          <span className="sthumb__chips">
            <small className="is-on">전체</small>
            <small>보습</small>
            <small>클렌저</small>
            <small>선케어</small>
          </span>
          {layout === 'catalog' ? (
            <span className="sthumb__filters">
              <small>고민 ▾</small>
              <small>가격대 ▾</small>
              <small>정렬 ▾</small>
            </span>
          ) : null}
        </b>
        <b className="sthumb__grid">
          <em>상품 카드</em>
          <span className="sthumb__cards">
            {Array.from({ length: cards }, (_, k) => (
              <b key={k} className="sthumb__card">
                <u className="sthumb__img">{k === 0 ? <small className="sthumb__badge">단독</small> : null}</u>
                <small>상품명</small>
                <strong>₩28,000</strong>
              </b>
            ))}
          </span>
        </b>
      </i>
    </span>
  );
}
