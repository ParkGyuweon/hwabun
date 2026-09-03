import { useState } from 'react';
import {
  DEFAULT_STOREFRONT,
  STOREFRONT_CARDS,
  STOREFRONT_CORNERS,
  STOREFRONT_DENSITIES,
  STOREFRONT_FONTS,
  STOREFRONT_HEADERS,
  STOREFRONT_LAYOUTS,
  STOREFRONT_PRESETS,
  STOREFRONT_PROMOS,
  STOREFRONT_THEMES,
  matchPreset,
} from '../lib/storefront';
import type {
  StorefrontDensity,
  StorefrontLayout,
  StorefrontPrefs,
  StorefrontPromo,
} from '../lib/storefront';
import { MotifLine } from './components';

/**
 * 가입 화면 — 내 쇼핑몰의 진열을 고른다.
 *
 * 축이 여덟(배열·기획전·크기·모서리·카드·글꼴·헤더·색)이라 조합이 10만 가지가 넘는다.
 * 앞선 화면은 축마다 큰 카드 목록을 세로로 늘어놓았는데, 고르는 화면이 아니라 서류가
 * 됐다. 자유도를 줄이지 않고 화면만 줄이려고 세 가지를 쓴다.
 *
 *   시작점      프리셋 다섯. 하나 누르면 뼈대 축이 한 번에 정해진다. 대부분은 여기서
 *               끝내고, 마음에 안 드는 축만 손대면 된다
 *   한 줄 축     축 하나가 한 줄이다. 설명을 지우고 도식과 이름만 남겼다.
 *               설명은 손이 닿은 것 하나만 아래 한 줄에 뜬다
 *   끌어 옮기기   기획전 덩어리를 미리보기 안에서 끌어 위·옆·아래로 옮긴다.
 *               "어디에 둘까" 는 목록에서 고르는 것보다 옮겨 보는 게 빠르다
 *
 * 미리보기는 진짜 화면과 같은 방식으로 그린다(자기 data 속성 + grid-template-areas).
 * 그래서 둘이 어긋나지 않는다.
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
  const [prefs, setPrefs] = useState<StorefrontPrefs>(initial);
  /** 손이 닿은 옵션의 설명. 축마다 설명을 달면 화면이 다시 길어진다 */
  const [hint, setHint] = useState<string | null>(null);

  const set = <K extends keyof StorefrontPrefs>(axis: K, value: StorefrontPrefs[K]) =>
    setPrefs((prev) => ({ ...prev, [axis]: value }));

  const preset = matchPreset(prefs);

  return (
    <div className="onboard">
      <div className="onboard__card">
        <header className="onboard__head">
          <img src="/brand/hwabun-mark.png" alt="" width="36" height="36" />
          <div>
            <p className="onboard__eyebrow">HWABUN · 내 쇼핑몰 만들기</p>
            <h1>고객이 볼 쇼핑몰을 고릅니다</h1>
          </div>
        </header>

        <div className="onboard__split">
          <div className="onboard__preview">
            <StorefrontPreview prefs={prefs} onPromoChange={(v) => set('promo', v)} />
          </div>

          <div className="onboard__rail">
            <label className="ax ax--name">
              <span className="ax__label">이름</span>
              <input
                className="onboard__input"
                type="text"
                value={prefs.brandName}
                onChange={(e) => set('brandName', e.target.value)}
                placeholder="예: 그린 티 랩"
                maxLength={40}
              />
            </label>

            <div className="ax">
              <span className="ax__label">시작점</span>
              <div className="ax__opts ax__opts--wrap" role="group" aria-label="시작점">
                {STOREFRONT_PRESETS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    className={`ax__preset ${preset === p.key ? 'is-on' : ''}`}
                    onClick={() => setPrefs((prev) => ({ ...prev, ...p.style }))}
                    onMouseEnter={() => setHint(p.desc)}
                    onFocus={() => setHint(p.desc)}
                    aria-pressed={preset === p.key}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <MotifLine variant="divider" compact />

            <AxisRow
              label="배열"
              kind="layout"
              options={STOREFRONT_LAYOUTS}
              value={prefs.layout}
              onChange={(v) => set('layout', v)}
              onHint={setHint}
            />
            <AxisRow
              label="기획전"
              kind="promo"
              options={STOREFRONT_PROMOS}
              value={prefs.promo}
              onChange={(v) => set('promo', v)}
              onHint={setHint}
            />
            <AxisRow
              label="크기"
              kind="density"
              options={STOREFRONT_DENSITIES}
              value={prefs.density}
              onChange={(v) => set('density', v)}
              onHint={setHint}
            />
            <AxisRow
              label="모서리"
              kind="corner"
              options={STOREFRONT_CORNERS}
              value={prefs.corner}
              onChange={(v) => set('corner', v)}
              onHint={setHint}
            />
            <AxisRow
              label="카드"
              kind="card"
              options={STOREFRONT_CARDS}
              value={prefs.card}
              onChange={(v) => set('card', v)}
              onHint={setHint}
            />
            <AxisRow
              label="글꼴"
              kind="font"
              options={STOREFRONT_FONTS}
              value={prefs.font}
              onChange={(v) => set('font', v)}
              onHint={setHint}
            />
            <AxisRow
              label="헤더"
              kind="header"
              options={STOREFRONT_HEADERS}
              value={prefs.header}
              onChange={(v) => set('header', v)}
              onHint={setHint}
            />

            <div className="ax">
              <span className="ax__label">색</span>
              <div className="ax__opts ax__opts--wrap" role="group" aria-label="색">
                {STOREFRONT_THEMES.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    className={`ax__swatch ${prefs.theme === t.key ? 'is-on' : ''}`}
                    style={
                      { ['--sw' as string]: t.swatch[0], ['--sw2' as string]: t.swatch[1] } as React.CSSProperties
                    }
                    onClick={() => set('theme', t.key)}
                    onMouseEnter={() => setHint(`${t.label} — ${t.desc}`)}
                    onFocus={() => setHint(`${t.label} — ${t.desc}`)}
                    aria-label={t.label}
                    aria-pressed={prefs.theme === t.key}
                  />
                ))}
              </div>
            </div>

            <p className="onboard__hint" aria-live="polite">
              {hint ?? '기획전 덩어리는 미리보기 안에서 끌어서 옮길 수 있습니다.'}
            </p>
          </div>
        </div>

        <footer className="onboard__foot">
          <button
            type="button"
            className="onboard__reset"
            onClick={() => setPrefs({ ...DEFAULT_STOREFRONT, brandName: prefs.brandName })}
          >
            처음으로
          </button>
          {onCancel ? (
            <button type="button" className="onboard__btn onboard__btn--ghost" onClick={onCancel}>
              취소
            </button>
          ) : null}
          <button
            type="button"
            className="onboard__btn"
            onClick={() => onDone({ ...prefs, brandName: prefs.brandName.trim() })}
          >
            {onCancel ? '쇼핑몰에 적용' : '이 설정으로 시작'}
          </button>
        </footer>
      </div>
    </div>
  );
}

/* ---------- 축 한 줄 ---------- */

type GlyphKind = 'layout' | 'promo' | 'density' | 'corner' | 'card' | 'font' | 'header';

function AxisRow<K extends string>({
  label,
  kind,
  options,
  value,
  onChange,
  onHint,
}: {
  label: string;
  kind: GlyphKind;
  options: ReadonlyArray<{ key: K; label: string; desc: string }>;
  value: K;
  onChange: (value: K) => void;
  onHint: (hint: string) => void;
}) {
  return (
    <div className="ax">
      <span className="ax__label">{label}</span>
      <div className="ax__opts" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            className={`ax__opt ${value === o.key ? 'is-on' : ''}`}
            onClick={() => onChange(o.key)}
            onMouseEnter={() => onHint(`${o.label} — ${o.desc}`)}
            onFocus={() => onHint(`${o.label} — ${o.desc}`)}
            aria-pressed={value === o.key}
            aria-label={`${label} ${o.label}`}
          >
            <Glyph kind={kind} value={o.key} />
            <em>{o.label}</em>
          </button>
        ))}
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

/** 끌어다 놓을 자리 */
const DROP_ZONES: Array<{ key: StorefrontPromo; label: string }> = [
  { key: 'top', label: '맨 위' },
  { key: 'side', label: '오른쪽' },
  { key: 'bottom', label: '맨 아래' },
  { key: 'off', label: '빼기' },
];

function StorefrontPreview({
  prefs,
  onPromoChange,
}: {
  prefs: StorefrontPrefs;
  onPromoChange: (promo: StorefrontPromo) => void;
}) {
  const { layout, promo, density, corner, card, font, header, theme, brandName } = prefs;
  const [dragging, setDragging] = useState(false);
  const swatch =
    STOREFRONT_THEMES.find((t) => t.key === theme)?.swatch ?? STOREFRONT_THEMES[0].swatch;

  const cols = PREVIEW_COLS[layout][density];
  const rows = layout === 'list' ? 3 : 2;
  const promoCards = promo === 'side' || layout === 'showcase' ? 2 : 3;

  return (
    <div
      className={`sfp ${dragging ? 'is-dragging' : ''}`}
      data-layout={layout}
      data-promo={promo}
      data-density={density}
      data-corner={corner}
      data-card={card}
      data-font={font}
      data-header={header}
      style={
        {
          '--t-brand': swatch[0],
          '--t-accent': swatch[1],
          '--t-soft': swatch[2],
          '--sfp-cols': cols,
        } as React.CSSProperties
      }
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
        <section
          className="sfp__promo"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = 'move';
            // 데이터가 비어 있으면 일부 브라우저가 드래그를 시작하지 않는다
            e.dataTransfer.setData('text/plain', 'promo');
            setDragging(true);
          }}
          onDragEnd={() => setDragging(false)}
        >
          <span className="sfp__grip" title="끌어서 자리를 옮기세요">
            기획전 ⠿
          </span>
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
              {Array.from({ length: cols * rows }, (_, k) => (
                <PreviewCard key={k} badge={k === 0} />
              ))}
            </div>
          </div>
        </section>
      </div>

      {/* 끌기 시작할 때만 나타난다. 늘 떠 있으면 미리보기가 아니라 도구가 된다 */}
      {dragging ? (
        <div className="sfp__zones">
          {DROP_ZONES.map((zone) => (
            <div
              key={zone.key}
              className={`sfp__zone ${promo === zone.key ? 'is-current' : ''}`}
              data-zone={zone.key}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                onPromoChange(zone.key);
              }}
            >
              <span>{zone.label}</span>
            </div>
          ))}
        </div>
      ) : null}
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
 * 축 하나만 보여주는 작은 도식.
 * 큰 미리보기가 조합 전체를 설명하므로 여기서는 그 축의 차이만 그린다.
 */
function Glyph({ kind, value }: { kind: GlyphKind; value: string }) {
  if (kind === 'font') {
    return (
      <span className="sfg sfg--text" data-kind={kind} data-value={value} aria-hidden="true">
        가Aa
      </span>
    );
  }

  if (kind === 'header') {
    return (
      <span className="sfg" data-kind={kind} data-value={value} aria-hidden="true">
        <i className="sfg__dot" />
        <span className="sfg__cells">
          <i />
          <i />
          <i />
        </span>
      </span>
    );
  }

  const cells =
    kind === 'layout'
      ? ({ grid: 8, showcase: 2, catalog: 6, list: 3 }[value] ?? 8)
      : kind === 'density'
        ? ({ airy: 3, cozy: 8, compact: 15 }[value] ?? 8)
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
