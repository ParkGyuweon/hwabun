import { BarList, Funnel, Kpi, OriginBadge, Panel } from '../components';
import { fmt } from '../lib/metrics';
import { EVENT_KO } from '../lib/behavior';
import { josa } from '../../lib/format';
import { useBehavior } from '../lib/useBehavior';

/**
 * 막히는 곳 (명세 §2-7).
 *
 * 여기 숫자는 **상품이 싫다는 뜻이 아니다.** 반응하지 않는 버튼, 읽기 어려운 순서처럼
 * 화면 쪽 문제로 먼저 읽는다 (규칙 R-8). 그래서 상품·성분 화면과 축을 섞지 않고 뒤에 둔다.
 *
 * 문구에 업계 용어를 쓰지 않는다. 사장님이 UX 용어를 알아야 할 이유가 없다.
 * 이벤트 이름(rage_click 등)은 데이터 파트와 맞추는 값이라 화면에는 내지 않는다.
 *
 * 이 화면의 마트는 전부 신규 요청(계약 §6-5)이다. 올 때까지 0·빈 표이고 배지가 그렇게 적는다.
 */
export default function BehaviorScreen() {
  const { frictionByLocation, frictionCounts, entryConversion, intentFunnel, eventVolumes, quickExitRate, overview, source } = useBehavior();

  // 머뭇거림(hover_dwell)은 막힌 것과 다른 축이라 결론에서 뺀다
  // 0 끼리는 순위가 없다. 한 번도 안 일어난 자리를 "가장 많이 막힌 자리"로 세우지 않는다 (2026-09-18)
  const worst = [...frictionByLocation].filter((f) => f.event !== 'hover_dwell' && f.count > 0).sort((a, b) => b.count - a.count)[0];
  const best = [...entryConversion].filter((e) => e.cartRate > 0).sort((a, b) => b.cartRate - a.cartRate)[0];
  const base = entryConversion.find((e) => e.source === 'list_grid') ?? entryConversion[0];
  const noFriction = source.friction === 'none';

  return (
    <div className="stack">
      {worst ? (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            고객이 가장 많이 막힌 자리 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">
            {worst.where}에서 {worst.ko}
          </h2>
          <ul className="verdict__reasons">
            <li>
              {fmt.int(worst.count)}번 · {worst.meaning}
            </li>
            <li>상품이 싫다는 뜻이 아니라 화면이 반응하지 않은 것</li>
          </ul>
          <p className="verdict__action">
            <span className="verdict__unit">상세페이지</span>
            {josa(worst.where, '을/를')} 눌렀을 때 반응을 확인해 보세요
          </p>
        </section>
      ) : (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            고객이 가장 많이 막힌 자리 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">{noFriction ? '막힌 자리 기록을 아직 받지 못했습니다' : '이 기간에 막힌 자리가 기록되지 않았습니다'}</h2>
          <ul className="verdict__reasons">
            <li>{noFriction ? '기록이 오면 여기에 나옵니다' : '좋은 신호지만 방문 수도 함께 보세요'}</li>
          </ul>
        </section>
      )}

      <div className="grid grid--kpi">
        <Kpi
          label="3초 안에 나간 방문"
          value={fmt.pct(quickExitRate)}
          sub={quickExitRate === 0 ? '아직 기록 없음' : quickExitRate > 0.4 ? '첫 화면 점검 필요' : '심하지 않은 편'}
          source={source.friction}
        />
        <Kpi
          label="연달아 눌러댄 자리"
          value={fmt.int(frictionCounts.rage_click)}
          sub={frictionCounts.rage_click === 0 ? '아직 기록 없음' : '반응 없어 다시 누른 횟수'}
          source={source.friction}
        />
        <Kpi
          label="위로 되돌아가 다시 읽은 곳"
          value={fmt.int(frictionCounts.scroll_backtrack)}
          sub={frictionCounts.scroll_backtrack === 0 ? '아직 기록 없음' : '되돌아가 다시 읽은 횟수'}
          source={source.friction}
        />
        <Kpi
          label="담았다가 뺀 비율"
          value={fmt.pct(overview.removalRate)}
          sub={overview.removalRate === 0 ? '아직 기록 없음' : '담은 뒤 다시 뺀 비율'}
          source={source.overview}
        />
      </div>

      <Panel
        title="어디서 막혔나"
        source={source.friction}
        aside={<span title="'눌러도 반응 없음'은 실제 고객만 만듭니다. 0이어도 문제가 없다는 뜻은 아닙니다">많이 막힌 자리부터 손보세요</span>}
      >
        <table className="table">
          <thead>
            <tr>
              <th>자리</th>
              <th>무슨 일</th>
              <th>횟수</th>
              <th>가능한 이유</th>
            </tr>
          </thead>
          <tbody>
            {frictionByLocation.length === 0 ? (
              <tr>
                <td colSpan={4} className="note">
                  {noFriction ? '아직 기록을 받지 못했습니다' : '이 기간에 막힌 기록이 없습니다'}
                </td>
              </tr>
            ) : null}
            {frictionByLocation.map((f) => (
              <tr key={f.where + f.event}>
                <td>{f.where}</td>
                <td>{f.ko}</td>
                <td>{fmt.int(f.count)}</td>
                <td>{f.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div className="grid grid--2">
        <Panel
          title="어디서 들어온 고객이 더 담나"
          source={source.entry}
          aside={
            best && base && base.cartRate > 0 && best.source !== base.source
              ? `${best.ko} 진입이 목록의 ${(best.cartRate / base.cartRate).toFixed(1)}배`
              : undefined
          }
        >
          <BarList
            items={entryConversion.map((e) => ({
              label: e.ko,
              value: e.cartRate * 100,
              hint: `방문 ${fmt.compact(e.sessions)}건`,
            }))}
            format={(v) => `${v.toFixed(1)}%`}
          />
        </Panel>

        <Panel
          title="고객이 지나온 단계"
          source={source.friction}
          fold
          aside={<span title="방문 수가 아니라 행동 횟수입니다">보임 → 열람 → 비교 → 확인 → 담기·구매</span>}
        >
          <Funnel steps={intentFunnel.map((s) => ({ label: s.ko, value: s.value }))} />
        </Panel>
      </div>

      {/* 접힘 안에 또 접힌 패널이 있어 두 번 눌러야 했다 (2026-09-22 은솔님). 패널 하나만 접어 둔다 */}
      <Panel title={`행동 종류별 기록 건수 · ${eventVolumes.length}가지`} source={source.friction} fold aside="많이 일어난 순서">
        <BarList items={eventVolumes.map((e) => ({ label: EVENT_KO[e.name] ?? e.name, value: e.count }))} format={fmt.compact} />
      </Panel>
    </div>
  );
}
