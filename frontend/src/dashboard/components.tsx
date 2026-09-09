import type { ReactNode } from 'react';

/**
 * 대시보드 공용 조각.
 *
 * 차트 라이브러리를 쓰지 않는다. 필요한 그림이 선·막대·깔때기 세 종류뿐이라
 * 인라인 SVG 와 div 로 충분하고, 흑백 단색이라 라이브러리 테마 싸움도 없다.
 */

/** 값의 출처. 모의값은 반드시 표시한다. 검토자가 진짜 수치로 착각하면 안 된다 */
export function SourceBadge({ kind }: { kind: 'real' | 'mock' }) {
  return (
    <span className={`badge badge--${kind}`}>{kind === 'real' ? '실측' : '모의'}</span>
  );
}

/**
 * 화면 맨 위에 놓는 한 문장.
 *
 * 5초 테스트는 화면을 잠깐 보여주고 가린 뒤 "무엇을 봤고 다음에 무엇을 할지" 를
 * 묻는다. 지표 카드만 늘어놓은 화면은 그 답을 못 준다. 그래서 지표보다 위에
 * 결론을 문장으로 둔다. 숫자는 아래에서 근거를 댄다.
 *
 * 표본 수를 함께 보여준다. 몇 건을 보고 낸 판단인지 모르면 그 판단을 믿을 수 없다.
 */
export function VerdictBanner({
  headline,
  reason,
  action,
  sampleSize,
}: {
  headline: string;
  reason: string;
  action: string;
  sampleSize: number;
}) {
  return (
    <section className="verdict">
      <p className="verdict__eyebrow">지금 손봐야 할 것</p>
      <h2 className="verdict__headline">{headline}</h2>
      <p className="verdict__reason">{reason}</p>
      <p className="verdict__action">{action}</p>
      <p className="verdict__sample">표본 {sampleSize.toLocaleString()}건</p>
    </section>
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
/**
 * 순위 목록.
 *
 * 막대가 주인공이 아니다. 상위 다섯 개의 값은 대개 서로 비슷해서(872 · 799 · 796 …)
 * 막대 길이로는 차이를 못 읽는다. 길게 늘린 막대는 가로 공간만 먹고 답을 안 준다.
 * 그래서 **이름과 숫자를 앞세우고 막대는 짧게 옆에 둔다.**
 *
 * 이름도 둘로 나눈다. "브랜드 · 상품명" 을 한 줄에 붙이면 폭이 모자라 상품명이 잘리는데,
 * 정작 알아야 할 것이 상품명이다. 상품명을 위에 크게, 브랜드를 아래 작게 둔다.
 */
export function BarList({
  items,
  format,
  rank = false,
}: {
  items: Array<{ label: string; value: number; hint?: string; sub?: string }>;
  format?: (value: number) => string;
  /** 순위 번호를 붙인다. TOP N 목록에만 쓰고 분포 목록에는 쓰지 않는다 */
  rank?: boolean;
}) {
  const values = items.map((item) => item.value);
  const max = Math.max(1, ...values);
  const min = Math.min(...values);
  const mean = values.reduce((a, b) => a + b, 0) / Math.max(1, values.length);
  /*
   * 차이가 작은데 막대만 길면 시각적으로 아무 정보가 없다 (명세 §3-1).
   *   spread < 15%  → 막대를 그리지 않고 숫자만 (flat)
   *   15~40%        → 점 + 평균 기준선 (dots). 기준선에서 얼마나 떨어졌는지가 보인다
   *   ≥ 40%         → 막대. 축은 0 부터
   */
  const spread = max > 0 ? (max - min) / max : 0;
  const mode: 'flat' | 'dots' | 'bars' =
    items.length < 2 ? 'bars' : spread < 0.15 ? 'flat' : spread < 0.4 ? 'dots' : 'bars';
  const fmt = (v: number) => (format ? format(v) : v.toLocaleString('ko-KR'));
  // dots 좌표: 축을 [min·0.9, max·1.05] 로 잡되, 축을 잘랐다는 것을 기준선과 주석으로 드러낸다
  const lo = min * 0.9;
  const hi = max * 1.05;
  const pos = (v: number) => `${((v - lo) / Math.max(1e-9, hi - lo)) * 100}%`;

  return (
    <>
      <ul className={`bars bars--${mode}${rank ? ' bars--rank' : ''}`}>
        {items.map((item, index) => (
          <li key={item.label} className="bars__row">
            {rank ? <span className="bars__rank">{index + 1}</span> : null}
            <span className="bars__name">
              <b title={item.label}>{item.label}</b>
              {item.sub ? <small title={item.sub}>{item.sub}</small> : null}
            </span>
            {mode === 'bars' ? (
              <span className="bars__track" aria-hidden="true">
                <span className="bars__fill" style={{ width: `${(item.value / max) * 100}%` }} />
              </span>
            ) : null}
            {mode === 'dots' ? (
              <span className="bars__track" aria-hidden="true" title={`평균 ${fmt(mean)}`}>
                <span className="bars__baseline" style={{ left: pos(mean) }} />
                <span
                  className={`bars__dot${item.value < mean ? ' is-below' : ''}`}
                  style={{ left: pos(item.value) }}
                />
              </span>
            ) : null}
            <span className="bars__value">
              {fmt(item.value)}
              {item.hint ? <em>{item.hint}</em> : null}
            </span>
          </li>
        ))}
      </ul>
      {mode === 'flat' ? (
        <p className="bars__flat-note">
          항목 간 차이가 {Math.round(spread * 100)}%로 작아 막대를 생략했습니다. 숫자로 비교하세요.
        </p>
      ) : null}
      {mode === 'dots' ? (
        <p className="bars__flat-note">
          세로선은 평균 {fmt(mean)}. 점이 왼쪽이면 평균 아래입니다. 축은 0이 아니라 값 범위입니다.
        </p>
      ) : null}
    </>
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

/**
 * HWABUN 그래픽 모티프 · "Data Point & Connection".
 *
 * 브랜딩 가이드의 핵심 모티프다. 채운 원은 있음, 빈 원은 없음(또는 아직)을 뜻하고,
 * 실선은 연결된 것, 점선은 아직 이어지지 않은 것이다. 색은 팔레트 토큰을 그대로 써서
 * 테마가 바뀌면 같이 바뀐다.
 *
 * divider: 구역 사이 구분선. empty: 자료가 없을 때 빈 자리 그래픽.
 */
export function MotifLine({
  variant = 'divider',
  compact = false,
}: {
  variant?: 'divider' | 'empty';
  compact?: boolean;
}) {
  const w = compact ? 160 : 320;
  const cy = 12;
  const r = compact ? 5 : 7;
  // 노드 x 좌표. 브랜딩 가이드의 Core Motif 순서: 주색 → 빈원 → 강조 → 점선 → 빈원(회색)
  const xs = [0.06, 0.32, 0.58, 0.9].map((f) => Math.round(w * f));
  return (
    <svg
      className={`motif motif--${variant}`}
      viewBox={`0 0 ${w} ${cy * 2}`}
      width={w}
      height={cy * 2}
      role="img"
      aria-hidden="true"
    >
      <line className="motif__line" x1={xs[0]} y1={cy} x2={xs[2]} y2={cy} />
      <line className="motif__line motif__line--dashed" x1={xs[2]} y1={cy} x2={xs[3]} y2={cy} />
      <circle className="motif__node motif__node--brand" cx={xs[0]} cy={cy} r={r} />
      <circle className="motif__node motif__node--hollow" cx={xs[1]} cy={cy} r={r} />
      <circle className="motif__node motif__node--accent" cx={xs[2]} cy={cy} r={r} />
      <circle className="motif__node motif__node--faint" cx={xs[3]} cy={cy} r={r} />
    </svg>
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
  // 축은 0 부터. 아래를 잘라 내면 작은 흔들림이 큰 변화처럼 보인다 (명세 §3-1)
  const min = 0;
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


/* ---------- 산점도 (명세 §3-1: 두 지표 관계는 산점도. 막대 2개 나열 금지) ---------- */

export interface ScatterPoint {
  label: string;
  /** 가로: 주목도 (평균 체류 초) */
  x: number;
  /** 세로: 전환 기여 lift. 1.0 이 기준선 */
  y: number;
  /** 표본. 200 미만은 흐림, 50 미만은 그리지 않는다 */
  n: number;
}

/**
 * 주목도 × 전환 기여.
 *
 * 체류가 길다 ≠ 좋다 (규칙 R-1a). 가로축 평균선과 세로축 lift=1 선으로 네 칸을 만들면
 *   우상: 오래 보고 결정에도 기여 → 지금처럼
 *   좌상: 짧게 보지만 결정에 기여 → 위로 올려라
 *   우하: 오래 보지만 안 산다 → 설명 문제
 *   좌하: 안 보고 안 산다 → 있어야 하나
 * 로 읽힌다. 점 크기는 표본, 축은 0 부터.
 */
export function Scatter({ points, height = 420 }: { points: ScatterPoint[]; height?: number }) {
  const width = 760;
  const pad = { l: 56, r: 28, t: 44, b: 62 };
  const x0 = pad.l;
  const x1 = width - pad.r;
  const y0 = pad.t;
  const y1 = height - pad.b;

  const shown = points.filter((p) => p.n >= 50);
  if (shown.length === 0) return <p className="note">표본 50 이상인 콘텐츠가 없습니다.</p>;

  // 축 범위. 세로는 lift 1.0 이 항상 가운데 쪽에 오도록 위아래로 같은 폭을 준다
  const maxX = Math.max(...shown.map((p) => p.x)) * 1.12;
  const loY = Math.min(0.6, Math.min(...shown.map((p) => p.y)) * 0.9);
  const hiY = Math.max(1.5, Math.max(...shown.map((p) => p.y)) * 1.1);
  const meanX = shown.reduce((s, p) => s + p.x, 0) / shown.length;

  const sx = (v: number) => x0 + (v / maxX) * (x1 - x0);
  const sy = (v: number) => y1 - ((v - loY) / (hiY - loY)) * (y1 - y0);
  // 점 크기는 표본. 너무 크면 서로 닿고 위치를 못 읽는다. 반지름 4.5~9px 로 묶는다
  const rOf = (n: number) => 4.5 + Math.min(4.5, Math.log10(Math.max(10, n)) * 1.5);

  const cx = sx(meanX);
  const cy = sy(1);

  /*
   * 라벨 겹침 회피. 표본이 큰 점부터 자리를 잡고, 이미 놓인 라벨·점과 겹치지 않는
   * 첫 후보 위치를 쓴다. 전부 겹치면 아래쪽에 두고 얇은 지시선을 그린다.
   * 왼쪽 아래에 점이 몰려서 그냥 오른쪽에 붙이면 글자가 서로 포개진다.
   */
  const placed: Array<{ x: number; y: number; w: number; h: number }> = [];
  const hit = (a: { x: number; y: number; w: number; h: number }) =>
    placed.some((b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) ||
    shown.some((p) => {
      const r = rOf(p.n) + 3;
      return a.x < sx(p.x) + r && a.x + a.w > sx(p.x) - r && a.y < sy(p.y) + r && a.y + a.h > sy(p.y) - r;
    });

  const labels = [...shown]
    .sort((a, b) => b.n - a.n)
    .map((p) => {
      const w = p.label.length * 12 + 6;
      const h = 17;
      const r = rOf(p.n);
      const px = sx(p.x);
      const py = sy(p.y);
      const cands: Array<[number, number, 'start' | 'end']> = [
        [px + r + 7, py + 5, 'start'],
        [px - r - 7 - w, py + 5, 'end'],
        [px - w / 2, py - r - 8, 'start'],
        [px - w / 2, py + r + 17, 'start'],
        [px + r + 7, py - r - 6, 'start'],
        [px + r + 7, py + r + 16, 'start'],
        [px - r - 7 - w, py - r - 6, 'end'],
        [px - r - 7 - w, py + r + 16, 'end'],
      ];
      let pick = cands[0];
      let found = false;
      for (const c of cands) {
        const box = { x: c[0], y: c[1] - 13, w, h };
        if (box.x < x0 - 4 || box.x + box.w > x1 + 4 || box.y < y0 - 6 || box.y + box.h > y1 + 6) continue;
        if (!hit(box)) {
          pick = c;
          found = true;
          break;
        }
      }
      placed.push({ x: pick[0], y: pick[1] - 13, w, h });
      const anchor = pick[2];
      const tx = anchor === 'end' ? pick[0] + w : pick[0];
      // 지시선: 자리를 못 찾아 멀리 밀린 라벨만
      const far = Math.abs(tx - px) > r + 30 || Math.abs(pick[1] - py) > r + 22;
      return { p, px, py, r, tx, ty: pick[1], anchor, leader: !found || far };
    });

  return (
    <div className="scatter-wrap">
      <svg
        className="scatter"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="콘텐츠별 주목도와 전환 기여 산점도"
      >
        <defs>
          <clipPath id="scatter-plot">
            <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx="14" />
          </clipPath>
        </defs>

        {/* 사분면 바탕. 손볼 곳(오래 보지만 안 산다)과 올릴 것(짧게 보지만 기여)만 색을 준다 */}
        <g clipPath="url(#scatter-plot)">
          <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} className="scatter__field" />
          <rect x={x0} y={y0} width={cx - x0} height={cy - y0} className="scatter__q scatter__q--lift" />
          <rect x={cx} y={cy} width={x1 - cx} height={y1 - cy} className="scatter__q scatter__q--fix" />
        </g>

        {/* 격자 */}
        {[0.5, 1, 1.5, 2, 2.5].filter((v) => v > loY && v < hiY).map((v) => (
          <g key={v}>
            <line className="scatter__grid" x1={x0} y1={sy(v)} x2={x1} y2={sy(v)} />
            <text className="scatter__tick" x={x0 - 10} y={sy(v) + 4} textAnchor="end">
              {v.toFixed(1)}×
            </text>
          </g>
        ))}

        {/* 기준선 */}
        <line className="scatter__ref scatter__ref--strong" x1={x0} y1={cy} x2={x1} y2={cy} />
        <line className="scatter__ref" x1={cx} y1={y0} x2={cx} y2={y1} />
        <text className="scatter__ref-label" x={x1 - 6} y={cy - 8} textAnchor="end">
          기여 1.0× 기준
        </text>
        <text className="scatter__ref-label" x={cx + 6} y={y1 + 16}>
          평균 체류 {meanX.toFixed(0)}초
        </text>

        {/* 사분면 이름 */}
        <text className="scatter__quad" x={x0 + 14} y={y0 + 22}>
          짧게 보지만 결정에 기여 · 위로 올릴 것
        </text>
        <text className="scatter__quad scatter__quad--fix" x={x1 - 14} y={y1 - 14} textAnchor="end">
          오래 보지만 안 산다 · 손볼 곳
        </text>

        {/* 축 */}
        <line className="scatter__axis" x1={x0} y1={y1} x2={x1} y2={y1} />
        <text className="scatter__tick" x={x1} y={y1 + 16} textAnchor="end">
          {maxX.toFixed(0)}초
        </text>
        <text className="scatter__axis-name" x={x0} y={height - 8}>
          가로 · 평균 체류 시간
        </text>
        <text className="scatter__axis-name" x={x0 - 44} y={y0 - 22}>
          세로 · 담기 기여
        </text>

        {/* 점 */}
        {labels.map(({ p, px, py, r, tx, ty, anchor, leader }) => {
          const below = p.y < 1;
          return (
            <g
              key={p.label}
              className={`scatter__pt${below ? ' is-below' : ''}${p.n < 200 ? ' is-thin' : ''}`}
            >
              {leader ? <line className="scatter__leader" x1={px} y1={py} x2={anchor === 'end' ? tx : tx} y2={ty - 4} /> : null}
              <circle className="scatter__halo" cx={px} cy={py} r={r + 3} />
              <circle className="scatter__dot" cx={px} cy={py} r={r}>
                <title>{`${p.label} · 체류 ${p.x.toFixed(1)}초 · 기여 ${p.y.toFixed(1)}× · n=${p.n.toLocaleString('ko-KR')}`}</title>
              </circle>
              <text className="scatter__name" x={tx} y={ty} textAnchor={anchor}>
                {p.label}
                <tspan className="scatter__lift" dx="6">
                  {p.y.toFixed(1)}×
                </tspan>
              </text>
            </g>
          );
        })}
      </svg>

      <p className="scatter-legend">
        <span className="scatter-legend__key scatter-legend__key--lift" /> 담기 기여 1.0× 이상
        <span className="scatter-legend__key scatter-legend__key--fix" /> 1.0× 미만
        <span className="scatter-legend__size" /> 원 크기 = 표본, 흐린 것은 200 미만
      </p>
    </div>
  );
}

/* ---------- 히트맵 (명세 §3-1: 격자. 셀마다 값 + n. n<50 빈칸, n<200 흐림) ---------- */

export interface HeatCell {
  value: number;
  n: number;
}

export function Heatmap({
  rows,
  cols,
  cells,
  format,
  rowNote,
}: {
  rows: Array<{ key: string; label: string }>;
  cols: Array<{ key: string; label: string }>;
  /** cells[rowKey][colKey] */
  cells: Record<string, Record<string, HeatCell>>;
  format: (v: number) => string;
  /** 행 오른쪽 한 줄 (예: 이 고객군은 성분을 가장 오래 본다) */
  rowNote?: (rowKey: string) => string | null;
}) {
  const valid = rows.flatMap((r) => cols.map((c) => cells[r.key]?.[c.key])).filter((c) => c && c.n >= 50) as HeatCell[];
  const max = Math.max(1e-9, ...valid.map((c) => c.value));
  return (
    <div className="table-wrap">
      <table className="heat">
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
            {rowNote ? <th className="heat__note-head" /> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              {cols.map((c) => {
                const cell = cells[r.key]?.[c.key];
                if (!cell || cell.n < 50) {
                  return (
                    <td key={c.key} className="heat__cell is-empty" title="표본 50 미만 · 표시하지 않음">
                      <span className="heat__value">–</span>
                    </td>
                  );
                }
                const thin = cell.n < 200;
                return (
                  <td
                    key={c.key}
                    className={`heat__cell${thin ? ' is-thin' : ''}`}
                    style={{ background: `rgb(var(--brand-rgb) / ${0.08 + (cell.value / max) * 0.72})` }}
                    title={thin ? `n=${cell.n} · 표본 200 미만` : `n=${cell.n}`}
                  >
                    <span className="heat__value">{format(cell.value)}</span>
                    <span className="heat__n">n={cell.n.toLocaleString('ko-KR')}</span>
                  </td>
                );
              })}
              {rowNote ? <td className="heat__note">{rowNote(r.key)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * 할 일 목록
 * ------------------------------------------------------------------ */

export interface ActionItem {
  /** 무엇을 해야 하나. 색과 말이 여기서 갈린다 */
  verb: 'up' | 'fix' | 'keep';
  /** 대상 이름. 콘텐츠 이름, 상품 이름처럼 짧은 명사 */
  what: string;
  /** 왜 그래야 하나. 한 문장, 숫자를 품는다 */
  why: string;
  /** 오른쪽에 세우는 근거 숫자 */
  num: string;
  /** 그 숫자가 무엇인지 */
  unit: string;
  /** 무엇을 어떻게. 위치·형식·개수까지 적은 명령 */
  how?: string;
  /** 그 명령을 지지하는 근거. 어느 화면에서 가져왔는지 함께 */
  basis?: Array<{ from: string; text: string }>;
  /** 무엇이 얼마나 바뀌면 성공인가 */
  verify?: string;
}

const VERB_KO: Record<ActionItem['verb'], string> = {
  up: '위로 올리세요',
  fix: '손보세요',
  keep: '그대로 두세요',
};

/**
 * 화면 맨 위에 놓는 할 일 목록.
 *
 * 지표를 늘어놓으면 사장님이 "그래서 뭘 하지" 를 스스로 풀어야 한다. 그 계산을
 * 화면이 대신한다. 한 줄에 **동작 하나 · 대상 하나 · 근거 숫자 하나**만 둔다.
 *
 * 동작 이름만으로는 안 된다. "위로 올리세요" 다음에 **무엇을 어떻게**(`how`) 가
 * 붙고, 그 지시가 어느 화면의 어떤 숫자에서 나왔는지(`basis`)와 다음 주에 무엇으로
 * 채점할지(`verify`)를 접어 둔다. 근거를 접어 두는 이유는 감추려는 게 아니라
 * 지시부터 읽게 하려는 것이다.
 *
 * 그래프는 이 판단이 어디서 나왔는지 확인하고 싶을 때 펼쳐 보는 부록으로 내린다.
 */
export function Actions({ items }: { items: ActionItem[] }) {
  return (
    <ol className="acts">
      {items.map((a) => (
        <li key={a.what} className={`act act--${a.verb}`}>
          <div className="act__row">
            <span className="act__verb">{VERB_KO[a.verb]}</span>
            <div className="act__body">
              <p className="act__what">{a.what}</p>
              <p className="act__why">{a.why}</p>
            </div>
            <div className="act__fig">
              <strong className="act__num">{a.num}</strong>
              <span className="act__unit">{a.unit}</span>
            </div>
          </div>

          {a.how ? (
            <div className="act__rx">
              <p className="act__how">
                <span className="act__rx-tag">이렇게 하세요</span>
                {a.how}
              </p>
              {a.basis && a.basis.length > 0 ? (
                <details className="act__more">
                  <summary>왜 이렇게 하라는 건지 · 다른 화면에서 모은 근거 {a.basis.length}개</summary>
                  <ul className="act__basis">
                    {a.basis.map((b) => (
                      <li key={b.from + b.text}>
                        <span className="act__from">{b.from}</span>
                        {b.text}
                      </li>
                    ))}
                  </ul>
                  {a.verify ? (
                    <p className="act__verify">
                      <b>다음 주에 이걸로 채점하세요</b> {a.verify}
                    </p>
                  ) : null}
                </details>
              ) : null}
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
