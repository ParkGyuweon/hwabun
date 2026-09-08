import { BarList, Funnel, Kpi, Panel } from '../components';
import {
  entryConversion,
  eventVolumes,
  fmt,
  frictionByLocation,
  frictionCounts,
  intentFunnel,
  overview,
  quickExitRate,
} from '../lib/metrics';

/**
 * 행동·마찰 (명세 §2-7). 화면이 막는 곳을 본다.
 *
 * 마찰 신호(rage·dead·backtrack)는 상품 선호가 아니라 화면 문제로 먼저 읽는다 (규칙 R-8).
 * 그래서 이 화면은 뒤에 있고, 상품·성분 화면과 축을 섞지 않는다.
 */
export default function BehaviorScreen() {
  // hover_dwell 은 망설임이라 마찰(rage·dead·backtrack)과 다른 축. 결론은 마찰 신호만 본다
  const worst = [...frictionByLocation].filter((f) => f.event !== 'hover_dwell').sort((a, b) => b.count - a.count)[0];
  const best = [...entryConversion].sort((a, b) => b.cartRate - a.cartRate)[0];
  const base = entryConversion.find((e) => e.source === 'list_grid') ?? entryConversion[0];

  return (
    <div className="stack">
      <section className="verdict">
        <p className="verdict__eyebrow">화면이 막는 곳</p>
        <h2 className="verdict__headline">
          {worst.where}에서 마찰이 가장 많습니다
        </h2>
        <ul className="verdict__reasons">
          <li>
            {worst.event} {fmt.int(worst.count)}건 · {worst.meaning}
          </li>
          <li>마찰 신호는 상품이 아니라 화면 구성의 문제로 먼저 봅니다. 상품 선호 점수에는 넣지 않습니다.</li>
        </ul>
        <p className="verdict__action">
          <span className="verdict__unit">상세페이지</span>
          {worst.where} 요소의 반응(확대·클릭·로딩)을 먼저 점검하세요
        </p>
      </section>

      <div className="grid grid--kpi">
        <Kpi label="3초 안에 나간 방문" value={fmt.pct(quickExitRate)} sub={quickExitRate > 0.4 ? '40% 초과 · 첫 화면 기대 불일치 가능성' : '40% 이하'} source="mock" />
        <Kpi label="rage_click" value={fmt.int(frictionCounts.rage_click)} sub="같은 자리 연타 · 반응 없는 UI" source="mock" />
        <Kpi label="scroll_backtrack" value={fmt.int(frictionCounts.scroll_backtrack)} sub="되돌아 읽기 · 비교·재확인" source="mock" />
        <Kpi label="장바구니 제거율" value={fmt.pct(overview.removalRate)} sub="담기 대비 제거" source="mock" />
      </div>

      <Panel title="마찰 위치" source="mock" aside="좌절이 몰린 위치가 할 일">
        <table className="table">
          <thead>
            <tr>
              <th>위치</th>
              <th>신호</th>
              <th>건수</th>
              <th>해석</th>
            </tr>
          </thead>
          <tbody>
            {frictionByLocation.map((f) => (
              <tr key={f.where + f.event}>
                <td>{f.where}</td>
                <td>
                  <span className="table__code">{f.event}</span>
                </td>
                <td>{fmt.int(f.count)}</td>
                <td>{f.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">
          dead_click 은 실사용자만 만든다. 합성 로그(생성기·PA 러너)는 유효한 요소만 누르므로 이 값이 0 이어도 마찰 없음이 아니다.
        </p>
      </Panel>

      <div className="grid grid--2">
        <Panel title="진입 경로별 상세 → 담기" source="mock" aside={`${best.ko} 진입이 목록 대비 ${(best.cartRate / base.cartRate).toFixed(1)}배`}>
          <BarList
            items={entryConversion.map((e) => ({ label: e.ko, value: e.cartRate * 100, hint: `n=${fmt.compact(e.sessions)}` }))}
            format={(v) => `${v.toFixed(1)}%`}
          />
          <p className="note">추천 카드로 들어온 방문이 더 담는다면 추천 노출을 넓힐 근거. 노출 정책이 섞인 기간은 비교하지 않는다.</p>
        </Panel>

        <Panel title="의도(intent) 퍼널" source="mock" aside="이벤트가 늘어도 단계 정의가 흔들리지 않는다">
          <Funnel steps={intentFunnel.map((s) => ({ label: s.ko, note: s.label, value: s.value }))} />
        </Panel>
      </div>

      <details className="fold">
        <summary>이벤트 발생량 상위 13 · 36종 중</summary>
        <Panel title="이벤트 발생량" source="mock">
          <BarList items={eventVolumes.map((e) => ({ label: e.name, value: e.count }))} format={fmt.compact} />
        </Panel>
      </details>
    </div>
  );
}
