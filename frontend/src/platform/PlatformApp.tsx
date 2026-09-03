import { useState } from 'react';
import { BarList, Kpi, LineChart, MotifLine, Panel, SourceBadge } from '../dashboard/components';
import {
  badEvents,
  benchmark,
  fmt,
  histogram,
  pipeline,
  tenants,
  totals,
  tpsSeries,
} from './lib/tenants';
import type { Tenant, TenantStatus } from './lib/tenants';

type ScreenKey = 'overview' | 'tenants' | 'benchmark' | 'infra';

const SCREENS: Array<{ key: ScreenKey; label: string; title: string; desc: string }> = [
  { key: 'overview', label: '개요', title: '플랫폼 개요', desc: '참여 브랜드 전체의 지금' },
  { key: 'tenants', label: '참여 브랜드', title: '참여 브랜드', desc: '브랜드별 수집·전환 현황과 벤치마크 대비' },
  {
    key: 'benchmark',
    label: '벤치마크',
    title: '업계 벤치마크',
    desc: '한 브랜드로는 답할 수 없는 질문 — 모였을 때 보이는 것',
  },
  { key: 'infra', label: '인프라', title: '수집·처리 인프라', desc: '파이프라인 상태와 처리량' },
];

const STATUS_LABEL: Record<TenantStatus, string> = { ok: '정상', watch: '주의', stale: '수집 지연' };

/**
 * HWABUN Platform — 운영자(우리 팀) 화면.
 *
 * 브랜드 대시보드(dashboard.html)가 한 브랜드의 "왜 안 팔리는지" 를 말한다면,
 * 이 화면은 그 브랜드 50개를 **한 인프라가 받고 있는가** 를 본다.
 *
 *   개요        지금 살아 있는 브랜드 수, 오늘 이벤트, 파이프라인 상태
 *   참여 브랜드  55개 표. 벤치마크 대비 위치와 수집 상태
 *   벤치마크    "모여야 하는 이유". 분포와 중앙값
 *   인프라      TPS 추이, 단계별 상태, 격리된 이벤트
 *
 * 화면 설정(레이아웃·색)은 두지 않는다. 운영자는 한 팀이고 화면도 하나면 된다.
 * 테마는 브랜딩 가이드 기본('화분')으로 고정한다.
 */
export default function PlatformApp() {
  const [screen, setScreen] = useState<ScreenKey>('overview');
  const [selected, setSelected] = useState<string | null>(null);
  const active = SCREENS.find((s) => s.key === screen) ?? SCREENS[0];

  return (
    <div className="console">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <img src="/brand/hwabun-mark.png" alt="" width="34" height="34" />
          <div>
            <strong>HWABUN</strong>
            <span>Platform · 운영</span>
          </div>
        </div>

        <MotifLine variant="divider" compact />

        <nav className="sidebar__nav" aria-label="플랫폼 화면">
          {SCREENS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={s.key === screen ? 'is-active' : ''}
              onClick={() => setScreen(s.key)}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div className="sidebar__foot">
          <p>
            참여 브랜드 {totals.tenants}개 · 상품 {totals.products}개
            <br />
            브랜드별 행동 지표는 수집 API 연결 전까지 모의 집계입니다.
          </p>
        </div>
      </aside>

      <main className="main">
        <header className="main__head">
          <h1>{active.title}</h1>
          <p>{active.desc}</p>
        </header>

        {screen === 'overview' ? <OverviewScreen onPick={(id) => { setSelected(id); setScreen('tenants'); }} /> : null}
        {screen === 'tenants' ? <TenantsScreen selected={selected} onSelect={setSelected} /> : null}
        {screen === 'benchmark' ? <BenchmarkScreen selected={selected} /> : null}
        {screen === 'infra' ? <InfraScreen /> : null}
      </main>
    </div>
  );
}

/* ---------- 개요 ---------- */

function OverviewScreen({ onPick }: { onPick: (id: string) => void }) {
  const attention = tenants.filter((t) => t.status !== 'ok');

  return (
    <div className="stack">
      <section className="verdict">
        <p className="verdict__eyebrow">지금 인프라는</p>
        <h2 className="verdict__headline">
          브랜드 {totals.tenants}개 중 {totals.live}개가 1분 안에 이벤트를 보내고 있습니다
        </h2>
        <p className="verdict__reason">
          오늘 {fmt.int(totals.eventsToday)}건 · 세션 {fmt.int(totals.sessionsToday)}개.
          {totals.stale > 0 ? ` 수집이 끊긴 브랜드 ${totals.stale}개는 아래 목록에서 확인하세요.` : ' 수집이 끊긴 브랜드는 없습니다.'}
        </p>
        <p className="verdict__action">
          {totals.watch > 0
            ? `주의 ${totals.watch}개 브랜드는 이탈률이 벤치마크 밖입니다. 해당 브랜드 담당자에게 알림이 나갑니다.`
            : '벤치마크 밖으로 벗어난 브랜드가 없습니다.'}
        </p>
        <p className="verdict__sample">표본 브랜드 {totals.tenants}개 · 상품 {totals.products}개</p>
      </section>

      <div className="grid grid--kpi">
        <Kpi label="참여 브랜드" value={String(totals.tenants)} sub="상품 200개의 실제 브랜드 수" source="real" />
        <Kpi label="오늘 이벤트" value={fmt.compact(totals.eventsToday)} sub="브랜드 전체 합계" source="mock" />
        <Kpi label="오늘 세션" value={fmt.compact(totals.sessionsToday)} sub="방문당 100~160건 기준" source="mock" />
        <Kpi label="실시간 브랜드" value={`${totals.live} / ${totals.tenants}`} sub="마지막 이벤트 1분 이내" source="mock" />
      </div>

      <div className="grid grid--2">
        <Panel title="파이프라인 상태" source="mock" aside="Collector → Kafka → Spark → Mart">
          <ul className="pipe">
            {pipeline.map((p) => (
              <li key={p.stage} className={`pipe__row pipe__row--${p.state}`}>
                <span className="pipe__dot" aria-hidden="true" />
                <span className="pipe__stage">{p.stage}</span>
                <span className="pipe__detail">{p.detail}</span>
                <span className="pipe__metric">{p.metric}</span>
              </li>
            ))}
          </ul>
          <p className="note">
            Collector·Kafka 는 구현 완료. Spark 작업 5개는 작성됐고 연결 검증 중, Mart 는 스키마 확정 후 적재 전이다.
          </p>
        </Panel>

        <Panel title="살펴볼 브랜드" source="mock" aside={`${attention.length}개`}>
          {attention.length === 0 ? (
            <MotifLine variant="empty" />
          ) : (
            <ul className="tlist">
              {attention.slice(0, 8).map((t) => (
                <li key={t.id}>
                  <button type="button" className="tlist__row" onClick={() => onPick(t.id)}>
                    <StatusPill status={t.status} />
                    <span className="tlist__name">{t.name}</span>
                    <span className="tlist__why">
                      {t.status === 'stale'
                        ? `마지막 이벤트 ${Math.round(t.lastEventAgoSec / 60)}분 전`
                        : `이탈률 ${fmt.pct(t.bounceRate)} · 벤치마크 ${fmt.pct(benchmark.bounceRate)}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="오늘 이벤트 상위 브랜드" source="mock" aside="상위 10">
        <BarList
          items={tenants.slice(0, 10).map((t) => ({
            label: t.name,
            value: t.eventsToday,
            hint: `${t.productCount}개 상품`,
          }))}
          format={fmt.compact}
        />
      </Panel>
    </div>
  );
}

/* ---------- 참여 브랜드 ---------- */

function TenantsScreen({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [filter, setFilter] = useState<'all' | TenantStatus>('all');
  const rows = filter === 'all' ? tenants : tenants.filter((t) => t.status === filter);

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi label="정상" value={String(tenants.filter((t) => t.status === 'ok').length)} source="mock" />
        <Kpi label="주의" value={String(totals.watch)} sub="이탈률·진입률이 벤치마크 밖" source="mock" />
        <Kpi label="수집 지연" value={String(totals.stale)} sub="30분 이상 이벤트 없음" source="mock" />
      </div>

      <Panel
        title="브랜드별 현황"
        source="mock"
        aside={
          <div className="seg" role="group" aria-label="상태 필터">
            {(['all', 'ok', 'watch', 'stale'] as const).map((k) => (
              <button
                key={k}
                type="button"
                className={filter === k ? 'is-active' : ''}
                onClick={() => setFilter(k)}
              >
                {k === 'all' ? '전체' : STATUS_LABEL[k]}
              </button>
            ))}
          </div>
        }
      >
        <div className="table-wrap">
          <table className="data data--tenants">
            <thead>
              <tr>
                <th>브랜드</th>
                <th>상태</th>
                <th>상품</th>
                <th>오늘 이벤트</th>
                <th>상세 진입률</th>
                <th>장바구니 전환율</th>
                <th>성분 열람률</th>
                <th>이탈률</th>
                <th>마지막 이벤트</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr
                  key={t.id}
                  className={selected === t.id ? 'is-selected' : ''}
                  onClick={() => onSelect(selected === t.id ? null : t.id)}
                >
                  <td>{t.name}</td>
                  <td>
                    <StatusPill status={t.status} />
                  </td>
                  <td>{t.productCount}</td>
                  <td>{fmt.int(t.eventsToday)}</td>
                  <td>
                    <Delta value={t.detailRate} base={benchmark.detailRate} />
                  </td>
                  <td>
                    <Delta value={t.cartRate} base={benchmark.cartRate} />
                  </td>
                  <td>
                    <Delta value={t.ingredientViewRate} base={benchmark.ingredientViewRate} />
                  </td>
                  <td>
                    <Delta value={t.bounceRate} base={benchmark.bounceRate} lowerIsBetter />
                  </td>
                  <td>{ago(t.lastEventAgoSec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          비율 옆 ▲▼ 는 참여 브랜드 중앙값 대비다. 브랜드 하나만 보면 이 열이 있을 수 없다 — 비교 대상이 없기 때문이다.
          행을 누르면 벤치마크 화면에서 그 브랜드 위치를 표시한다.
        </p>
      </Panel>
    </div>
  );
}

/* ---------- 벤치마크 ---------- */

function BenchmarkScreen({ selected }: { selected: string | null }) {
  const me = tenants.find((t) => t.id === selected) ?? null;

  return (
    <div className="stack">
      <section className="verdict">
        <p className="verdict__eyebrow">왜 모여야 하는가</p>
        <h2 className="verdict__headline">각자의 데이터는 혼자 쓸 땐 노이즈, 합치면 신호입니다</h2>
        <p className="verdict__reason">
          브랜드 하나의 방문자 수백 명으로는 "건성 고객이 성분을 보고 사는가" 에 답할 수 없습니다.
          표본이 안 됩니다. {totals.tenants}개가 모이면 세션 {fmt.int(totals.sessionsToday)}개가 되고 답이 나옵니다.
        </p>
        <p className="verdict__action">
          아래 분포에서 {me ? `${me.name} 의 위치가 표시됩니다` : '참여 브랜드 화면에서 브랜드를 고르면 그 위치가 표시됩니다'}.
        </p>
        <p className="verdict__sample">표본 브랜드 {totals.tenants}개 · 세션 {fmt.int(totals.sessionsToday)}개</p>
      </section>

      <div className="grid grid--2">
        <Distribution
          title="상세 이탈률 분포"
          question="내 이탈률이 높은 편인가?"
          values={tenants.map((t) => t.bounceRate)}
          median={benchmark.bounceRate}
          mine={me?.bounceRate ?? null}
          min={0.2}
          max={0.6}
        />
        <Distribution
          title="성분 열람률 분포"
          question="성분 설명이 부족한 게 내 문제인가, 업계 공통인가?"
          values={tenants.map((t) => t.ingredientViewRate)}
          median={benchmark.ingredientViewRate}
          mine={me?.ingredientViewRate ?? null}
          min={0.25}
          max={0.75}
        />
        <Distribution
          title="상세 진입률 분포"
          question="목록 카드가 일하고 있는가?"
          values={tenants.map((t) => t.detailRate)}
          median={benchmark.detailRate}
          mine={me?.detailRate ?? null}
          min={0.06}
          max={0.24}
        />
        <Distribution
          title="장바구니 전환율 분포"
          question="상세까지 온 사람이 담는가?"
          values={tenants.map((t) => t.cartRate)}
          median={benchmark.cartRate}
          mine={me?.cartRate ?? null}
          min={0.04}
          max={0.22}
        />
      </div>

      <Panel title="한 브랜드로는 답할 수 없는 질문 세 가지" aside="발표의 논리 뼈대">
        <ol className="qlist">
          <li>
            <strong>"건성 고객은 성분을 보고 사나, 리뷰를 보고 사나?"</strong>
            <span>한 브랜드 방문자 300명으로는 표본이 안 된다. 모이면 고객군 × 콘텐츠 교차가 성립한다.</span>
          </li>
          <li>
            <strong>"내 상세페이지 이탈률이 높은 편인가?"</strong>
            <span>비교 대상이 없으면 높은지 낮은지 말할 수 없다. 위 분포의 중앙값이 그 기준선이다.</span>
          </li>
          <li>
            <strong>"나이아신아마이드 설명이 부족한 게 내 문제인가, 업계 공통인가?"</strong>
            <span>긁어간 성분(<code>matched_ingredients</code>)을 브랜드 전체로 합치면 공통인지 개별인지 갈린다.</span>
          </li>
        </ol>
        <p className="note">
          이 구조는 리테일 미디어 모델과 같다 — 유통이 브랜드에 파는 것은 광고 지면이 아니라 **합쳐진 행동 데이터**다.
          우리는 그것을 소규모 브랜드용으로 만든다. 50개분 트래픽을 실시간으로 합쳐 처리해야 하니 분산처리가 필요하다.
        </p>
      </Panel>
    </div>
  );
}

function Distribution({
  title,
  question,
  values,
  median,
  mine,
  min,
  max,
}: {
  title: string;
  question: string;
  values: number[];
  median: number;
  mine: number | null;
  min: number;
  max: number;
}) {
  const bins = histogram(values, 12, min, max);
  const peak = Math.max(1, ...bins.map((b) => b.count));
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100))}%`;

  return (
    <Panel title={title} source="mock" aside={question}>
      <div className="hist" role="img" aria-label={`${title}. 중앙값 ${fmt.pct(median)}`}>
        <div className="hist__bars">
          {bins.map((b) => (
            <span
              key={b.from}
              className="hist__bar"
              style={{ height: `${(b.count / peak) * 100}%` }}
              title={`${fmt.pct(b.from, 0)}–${fmt.pct(b.to, 0)} · ${b.count}개`}
            />
          ))}
        </div>
        <span className="hist__mark hist__mark--median" style={{ left: pos(median) }}>
          <em>중앙값 {fmt.pct(median)}</em>
        </span>
        {mine !== null ? (
          <span className="hist__mark hist__mark--mine" style={{ left: pos(mine) }}>
            <em>선택 브랜드 {fmt.pct(mine)}</em>
          </span>
        ) : null}
      </div>
      <div className="hist__axis">
        <span>{fmt.pct(min, 0)}</span>
        <span>{fmt.pct(max, 0)}</span>
      </div>
    </Panel>
  );
}

/* ---------- 인프라 ---------- */

function InfraScreen() {
  const series = tpsSeries();
  const peak = series.reduce((a, b) => (b.value > a.value ? b : a), series[0]);
  const badTotal = badEvents.reduce((s, b) => s + b.count, 0);

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi label="현재 TPS" value={fmt.int(series[new Date().getHours()]?.value ?? 0)} sub="이벤트/초 · 브랜드 전체" source="mock" />
        <Kpi label="오늘 최고 TPS" value={fmt.int(peak.value)} sub={peak.label} source="mock" />
        <Kpi label="격리된 이벤트" value={fmt.int(badTotal)} sub="계약 위반 · bad_events" source="mock" />
        <Kpi label="Kafka lag" value="0" sub="activity-events 6 파티션" source="mock" />
      </div>

      <Panel title="시간대별 처리량" source="mock" aside="최근 24시간 · 이벤트/초">
        <LineChart points={series} height={180} />
        <p className="note">
          10,000명 동시 접속 시 17,000 TPS 가 설계 목표다 (log-transport-contract). 지금 표시는 오늘 참여 브랜드 합계를 시간 분포로 나눈 값이다.
        </p>
      </Panel>

      <div className="grid grid--2">
        <Panel title="단계별 상태" source="mock">
          <ul className="pipe">
            {pipeline.map((p) => (
              <li key={p.stage} className={`pipe__row pipe__row--${p.state}`}>
                <span className="pipe__dot" aria-hidden="true" />
                <span className="pipe__stage">{p.stage}</span>
                <span className="pipe__detail">{p.detail}</span>
                <span className="pipe__metric">{p.metric}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="격리 사유" source="mock" aside="contracts/validate_events.py 기준">
          <BarList items={badEvents.map((b) => ({ label: b.reason, value: b.count }))} />
          <p className="note">
            봉투 검증은 Collector 가, 필수 property 검증은 Spark cleaned_events 단계가 맡는다. 둘 다 통과한 것만 Mart 로 간다.
          </p>
        </Panel>
      </div>
    </div>
  );
}

/* ---------- 조각 ---------- */

function StatusPill({ status }: { status: TenantStatus }) {
  return <span className={`pill pill--${status}`}>{STATUS_LABEL[status]}</span>;
}

/** 벤치마크 대비. ▲ 가 항상 좋은 뜻은 아니라 lowerIsBetter 로 방향을 정한다 */
function Delta({ value, base, lowerIsBetter = false }: { value: number; base: number; lowerIsBetter?: boolean }) {
  const diff = value - base;
  const good = lowerIsBetter ? diff <= 0 : diff >= 0;
  const arrow = diff >= 0 ? '▲' : '▼';
  return (
    <span className={`delta ${good ? 'delta--good' : 'delta--bad'}`}>
      {fmt.pct(value)}
      <em>
        {arrow} {fmt.pct(Math.abs(diff))}
      </em>
    </span>
  );
}

function ago(sec: number): string {
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.round(sec / 60)}분 전`;
  return `${Math.round(sec / 3600)}시간 전`;
}

export { SourceBadge, type Tenant };
