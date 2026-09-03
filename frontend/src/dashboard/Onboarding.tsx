import { useState } from 'react';
import {
  STOREFRONT_CARDS,
  STOREFRONT_CORNERS,
  STOREFRONT_DENSITIES,
  STOREFRONT_FONTS,
  STOREFRONT_LAYOUTS,
  STOREFRONT_PROMOS,
  STOREFRONT_THEMES,
} from '../lib/storefront';
import type {
  StorefrontCard,
  StorefrontCorner,
  StorefrontDensity,
  StorefrontFont,
  StorefrontLayout,
  StorefrontPrefs,
  StorefrontPromo,
  StorefrontTheme,
} from '../lib/storefront';
import { MotifLine } from './components';

/**
 * 가입 화면 — 내 쇼핑몰의 진열을 고른다.
 *
 * 여기서 고르는 것은 **고객이 보는 쇼핑몰**이다. 대시보드는 사이드바 고정이고 색도 HWABUN 이다.
 *
 * 축이 여섯(배열·위치·크기·모서리·카드·글꼴)에 색이 아홉이라 조합이 34,992 가지다.
 * 조합마다 견본을 늘어놓을 수는 없다. 대신
 * **왼쪽에 지금 고른 조합의 쇼핑몰을 통째로 그린다.** 옵션을 누를 때마다 그 그림이 바뀐다.
 * 사장님이 알고 싶은 것은 "내 상품이 어디에 몇 열로 놓이는가" 이므로, 그림에는 실제 요소
 * 이름을 그대로 적는다 — 메뉴 · 기획전 · 카테고리 · 필터 · 상품 카드 · 몇 열인지.
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
  const [promo, setPromo] = useState<StorefrontPromo>(initial.promo);
  const [density, setDensity] = useState<StorefrontDensity>(initial.density);
  const [corner, setCorner] = useState<StorefrontCorner>(initial.corner);
  const [card, setCard] = useState<StorefrontCard>(initial.card);
  const [font, setFont] = useState<StorefrontFont>(initial.font);
  const [theme, setTheme] = useState<StorefrontTheme>(initial.theme);
  const [brandName, setBrandName] = useState(initial.brandName);

  const prefs: StorefrontPrefs = { layout, promo, density, corner, card, font, theme, brandName };

  return (
    <div className="onboard">
      <div className="onboard__card">
        <header className="onboard__head">
          <img src="/brand/hwabun-mark.png" alt="" width="40" height="40" />
          <div>
            <p className="onboard__eyebrow">HWABUN · 내 쇼핑몰 만들기</p>
            <h1>고객이 볼 쇼핑몰을 고릅니다</h1>
            <p className="onboard__lead">
              상품을 어떻게 늘어놓을지, 기획전을 어디에 둘지, 얼마나 촘촘하게 보일지 정하세요.
              데이터 수집과 분석은 어떤 진열을 골라도 똑같이 됩니다. 나중에 바꿀 수 있고, 바꾸면
              쇼핑몰에 바로 반영됩니다.
            </p>
          </div>
        </header>

        <MotifLine variant="divider" />

        <div className="onboard__split">
          <div className="onboard__preview">
            <StorefrontPreview prefs={prefs} />
            <p className="onboard__hint">
              고객이 보게 될 화면입니다. 오른쪽에서 고를 때마다 여기가 바뀝니다.
            </p>
          </div>

          <div className="onboard__options">
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
                <span className="onboard__step">2</span> 상품 배열
              </h2>
              <div className="onboard__opts">
                {STOREFRONT_LAYOUTS.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt ${layout === o.key ? 'is-active' : ''}`}
                    onClick={() => setLayout(o.key)}
                    aria-pressed={layout === o.key}
                  >
                    <Glyph kind="layout" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                      <small className="onboard__fit">{o.fit}</small>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">3</span> 기획전 위치
              </h2>
              <div className="onboard__opts onboard__opts--2">
                {STOREFRONT_PROMOS.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt ${promo === o.key ? 'is-active' : ''}`}
                    onClick={() => setPromo(o.key)}
                    aria-pressed={promo === o.key}
                  >
                    <Glyph kind="promo" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">4</span> 크기
              </h2>
              <div className="onboard__opts onboard__opts--3">
                {STOREFRONT_DENSITIES.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt onboard__opt--stack ${density === o.key ? 'is-active' : ''}`}
                    onClick={() => setDensity(o.key)}
                    aria-pressed={density === o.key}
                  >
                    <Glyph kind="density" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">5</span> 모서리
              </h2>
              <div className="onboard__opts onboard__opts--3">
                {STOREFRONT_CORNERS.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt onboard__opt--stack ${corner === o.key ? 'is-active' : ''}`}
                    onClick={() => setCorner(o.key)}
                    aria-pressed={corner === o.key}
                  >
                    <Glyph kind="corner" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <p className="onboard__hint">
                카테고리 칩, 상품 사진, 버튼의 모서리가 한꺼번에 바뀝니다.
              </p>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">6</span> 카드 모양
              </h2>
              <div className="onboard__opts onboard__opts--3">
                {STOREFRONT_CARDS.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt onboard__opt--stack ${card === o.key ? 'is-active' : ''}`}
                    onClick={() => setCard(o.key)}
                    aria-pressed={card === o.key}
                  >
                    <Glyph kind="card" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">7</span> 글꼴
              </h2>
              <div className="onboard__opts onboard__opts--3">
                {STOREFRONT_FONTS.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={`onboard__opt onboard__opt--stack ${font === o.key ? 'is-active' : ''}`}
                    onClick={() => setFont(o.key)}
                    aria-pressed={font === o.key}
                  >
                    <Glyph kind="font" value={o.key} />
                    <span className="onboard__opt-text">
                      <strong>{o.label}</strong>
                      <span>{o.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <p className="onboard__hint">브랜드 이름과 기획전 제목에 적용됩니다.</p>
            </section>

            <section className="onboard__section">
              <h2>
                <span className="onboard__step">8</span> 색
              </h2>
              <div className="onboard__opts onboard__opts--3">
                {STOREFRONT_THEMES.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    className={`onboard__opt onboard__opt--theme ${theme === t.key ? 'is-active' : ''}`}
                    onClick={() => setTheme(t.key)}
                    aria-pressed={theme === t.key}
                    title={t.desc}
                  >
                    <span className="onboard__swatch" aria-hidden="true">
                      {t.swatch.map((c) => (
                        <i key={c} style={{ background: c }} />
                      ))}
                    </span>
                    <strong>{t.label}</strong>
                  </button>
                ))}
              </div>
              <p className="onboard__hint">
                버튼·별점·배지 색만 바뀝니다. 글자와 바탕의 중립색은 어느 색을 골라도 그대로예요.
              </p>
            </section>
          </div>
        </div>

        <footer className="onboard__foot">
          {onCancel ? (
            <button type="button" className="onboard__btn onboard__btn--ghost" onClick={onCancel}>
              취소
            </button>
          ) : null}
          <button
            type="button"
            className="onboard__btn"
            onClick={() => onDone({ ...prefs, brandName: brandName.trim() })}
          >
            {onCancel ? '쇼핑몰에 적용' : '이 설정으로 시작'}
          </button>
        </footer>
      </div>
    </div>
  );
}

/* ---------- 미리보기 ---------- */

/** 배열 x 크기 → 상품이 몇 열로 서는가. storefront.css 의 --sf-cols 와 같은 표다 */
const PREVIEW_COLS: Record<StorefrontLayout, Record<StorefrontDensity, number>> = {
  grid: { airy: 3, cozy: 4, compact: 5 },
  showcase: { airy: 2, cozy: 2, compact: 3 },
  catalog: { airy: 2, cozy: 3, compact: 4 },
  list: { airy: 1, cozy: 1, compact: 1 },
};

/**
 * 쇼핑몰 와이어프레임.
 *
 * 실제 쇼핑몰과 **같은 모양의 규칙**으로 그린다. 진짜 화면이 <html> 의 data 속성을 보고
 * grid-template-areas 로 섹션 자리를 잡듯, 이 그림도 자기 data 속성을 보고 같은 방식으로
 * 잡는다. 그래서 둘이 어긋나지 않는다.
 */
function StorefrontPreview({ prefs }: { prefs: StorefrontPrefs }) {
  const { layout, promo, density, corner, card, font, theme, brandName } = prefs;
  const swatch = STOREFRONT_THEMES.find((t) => t.key === theme)?.swatch ?? STOREFRONT_THEMES[0].swatch;

  const style = {
    '--t-brand': swatch[0],
    '--t-accent': swatch[1],
    '--t-soft': swatch[2],
  } as React.CSSProperties;

  const cols = PREVIEW_COLS[layout][density];
  const rows = layout === 'list' ? 3 : 2;
  const cards = cols * rows;
  const promoCards = promo === 'side' || layout === 'showcase' ? 2 : 3;

  return (
    <div
      className="sfp"
      data-layout={layout}
      data-promo={promo}
      data-density={density}
      data-corner={corner}
      data-card={card}
      data-font={font}
      style={{ ...style, ['--sfp-cols' as string]: cols }}
      aria-hidden="true"
    >
      <div className="sfp__ribbon">무료배송 · 기간 한정</div>

      <div className="sfp__header">
        <span className="sfp__logo">
          <i />
          {brandName || 'BLOOM'}
        </span>
        <span className="sfp__menu">
          <em>메뉴</em>
          <b>Moisturizers</b>
          <b>Treatments</b>
          <b>Cleansers</b>
        </span>
        <span className="sfp__cart">장바구니</span>
      </div>

      <div className="sfp__page">
        <section className="sfp__promo">
          <span className="sfp__tag">기획전</span>
          <b className="sfp__h2">지금 주목할 상품</b>
          <div className="sfp__promo-row">
            {Array.from({ length: promoCards }, (_, k) => (
              <PreviewCard key={k} />
            ))}
          </div>
        </section>

        <section className="sfp__catalog">
          <div className="sfp__side">
            <span className="sfp__tag">{layout === 'catalog' ? '카테고리 · 필터' : '카테고리'}</span>
            <span className="sfp__chips">
              <i className="is-on">전체</i>
              <i>보습</i>
              <i>클렌저</i>
              <i>선케어</i>
            </span>
            {layout === 'catalog' ? (
              <span className="sfp__filters">
                <i>고민 ▾</i>
                <i>가격대 ▾</i>
                <i>정렬 ▾</i>
              </span>
            ) : null}
          </div>

          <div className="sfp__main">
            <span className="sfp__tag">
              상품 카드 {layout === 'list' ? '· 한 줄에 하나' : `· ${cols}열`}
            </span>
            <div className="sfp__cards">
              {Array.from({ length: cards }, (_, k) => (
                <PreviewCard key={k} badge={k === 0} />
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function PreviewCard({ badge = false }: { badge?: boolean }) {
  return (
    <b className="sfp__card">
      <u className="sfp__img">{badge ? <i className="sfp__badge">단독</i> : null}</u>
      <span className="sfp__card-text">
        <small>상품명</small>
        <strong>₩28,000</strong>
      </span>
    </b>
  );
}

/**
 * 옵션 버튼에 붙는 작은 도식.
 *
 * 큰 미리보기가 조합 전체를 설명하므로 여기서는 그 축 **하나만** 보여준다.
 * 기획전 위치 도식은 진짜 화면과 같은 grid-area 방식으로 자리를 잡는다.
 */
function Glyph({
  kind,
  value,
}: {
  kind: 'layout' | 'promo' | 'density' | 'corner' | 'card' | 'font';
  value: string;
}) {
  // 글꼴은 도형으로 보여줄 수 없다. 글자를 그대로 보여준다
  if (kind === 'font') {
    return (
      <span className="sfg sfg--text" data-kind={kind} data-value={value} aria-hidden="true">
        가Aa
      </span>
    );
  }

  const cells =
    kind === 'layout'
      ? { grid: 8, showcase: 2, catalog: 6, list: 3 }[value] ?? 8
      : kind === 'density'
        ? { airy: 3, cozy: 8, compact: 15 }[value] ?? 8
        : kind === 'corner' || kind === 'card'
          ? 4
          : 4;

  return (
    <span className="sfg" data-kind={kind} data-value={value} aria-hidden="true">
      {kind === 'layout' && value === 'catalog' ? <i className="sfg__rail" /> : null}
      {kind === 'promo' ? <i className="sfg__band" /> : null}
      <span className="sfg__cells">
        {Array.from({ length: cells }, (_, k) => (
          <i key={k} />
        ))}
      </span>
    </span>
  );
}
