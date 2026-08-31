import type { ReactNode } from 'react';

/**
 * 대시보드 공용 조각.
 *
 * 차트 라이브러리를 쓰지 않는다. 필요한 그림이 선·막대·깔때기 세 종류뿐이라
 * 인라인 SVG 와 div 로 충분하고, 흑백 단색이라 라이브러리 테마 싸움도 없다.
 */

/** 값의 출처. 모의값은 반드시 표시한다 — 검토자가 진짜 수치로 착각하면 안 된다 */
export function SourceBadge({ kind }: { kind: 'real' | 'mock' }) {
  return (
    <span className={`badge badge--${kind}`}>{kind === 'real' ? '실측' : '모의'}</span>
  );
}

export function Panel({
  title,
  source,
  aside,
  children,
}: {
  title: string;
  source?: 'real' | 'mock';
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel__head">
        <h2>{title}</h2>
        {source ? <SourceBadge kind={source} /> : null}
        {aside ? <div className="panel__aside">{aside}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function Kpi({
  label,
  value,
  sub,
  source,
}: {
  label: string;
  value: string;
  sub?: string;
  source?: 'real' | 'mock';
}) {
  return (
    <div className="kpi">
      <p className="kpi__label">
        {label}
        {source ? <SourceBadge kind={source} /> : null}
      </p>
      <p className="kpi__value">{value}</p>
      {sub ? <p className="kpi__sub">{sub}</p> : null}
    </div>
  );
}

/** 가로 막대 목록. 최댓값 기준 상대 폭 */
export function BarList({
  items,
  format,
}: {
  items: Array<{ label: string; value: number; hint?: string }>;
  format?: (value: number) => string;
}) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <ul className="bars">
      {items.map((item) => (
        <li key={item.label} className="bars__row">
          <span className="bars__label" title={item.label}>
            {item.label}
          </span>
          <span className="bars__track">
            <span className="bars__fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </span>
          <span className="bars__value">
            {format ? format(item.value) : item.value.toLocaleString('ko-KR')}
            {item.hint ? <em>{item.hint}</em> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 깔때기. 단계 사이 전환율을 함께 보여준다 */
export function Funnel({ steps }: { steps: Array<{ label: string; value: number; note?: string }> }) {
  const max = Math.max(1, ...steps.map((step) => step.value));
  return (
    <div className="funnel">
      {steps.map((step, index) => {
        const prev = index > 0 ? steps[index - 1].value : null;
        const rate = prev ? step.value / prev : null;
        return (
          <div key={step.label} className="funnel__step">
            {rate !== null ? (
              <p className="funnel__rate">↓ {(rate * 100).toFixed(1)}%</p>
            ) : null}
            <div className="funnel__bar" style={{ width: `${(step.value / max) * 100}%` }}>
              <span className="funnel__label">
                {step.label}
                {step.note ? <em>{step.note}</em> : null}
              </span>
              <span className="funnel__value">{step.value.toLocaleString('ko-KR')}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 단순 선 그래프. 면을 옅게 깔고 마지막 점만 강조한다 */
export function LineChart({
  points,
  height = 160,
}: {
  points: Array<{ label: string; value: number }>;
  height?: number;
}) {
  const width = 640;
  const pad = 6;
  const max = Math.max(1, ...points.map((p) => p.value));
  const min = Math.min(...points.map((p) => p.value), max * 0.6);
  const x = (i: number) => pad + (i / Math.max(1, points.length - 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - min) / Math.max(1, max - min)) * (height - pad * 2);
  const path = points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ');
  const last = points[points.length - 1];

  return (
    <svg
      className="line-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="기간별 추이"
    >
      <polygon
        points={`${pad},${height - pad} ${path} ${width - pad},${height - pad}`}
        className="line-chart__area"
      />
      <polyline points={path} className="line-chart__line" />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r={4} className="line-chart__dot" />
    </svg>
  );
}
