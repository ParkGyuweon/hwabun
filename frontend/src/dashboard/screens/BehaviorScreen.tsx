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
              {fmt.int(worst.count)}번 일어났습니다. {worst.meaning}
            </li>
            <li>상품이 마음에 안 든다는 뜻이 아닙니다. 화면이 기대한 대로 반응하지 않았다는 뜻입니다.</li>
          </ul>
          <p className="verdict__action">
            <span className="verdict__unit">상세페이지</span>
            {josa(worst.where, '을/를')} 눌렀을 때 무엇이 일어나는지 먼저 확인해 보세요
          </p>
        </section>
      ) : (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            고객이 가장 많이 막힌 자리 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">{noFriction ? '막힌 자리 기록을 아직 받지 못했습니다' : '이 기간에 막힌 자리가 기록되지 않았습니다'}</h2>
          <ul className="verdict__reasons">
            <li>
              {noFriction
                ? '고객이 상세페이지에서 눌러도 반응이 없거나 위로 되돌아가 다시 읽으면 여기에 쌓입니다. 기록이 오면 가장 많이 막힌 자리를 알려 드립니다.'
                : '눌러도 반응이 없던 자리, 연달아 눌러댄 자리, 위로 되돌아가 다시 읽은 곳이 한 번도 없었습니다. 좋은 신호지만, 방문 자체가 적었는지도 함께 보세요.'}
            </li>
          </ul>
        </section>
      )}

      <div className="grid grid--kpi">
        <Kpi
          label="3초 안에 나간 방문"
          value={fmt.pct(quickExitRate)}
          sub={
            quickExitRate === 0
              ? '아직 기록이 없거나, 3초 안에 나간 방문이 없었습니다'
              : quickExitRate > 0.4
                ? '10명 중 4명 이상. 첫 화면이 기대와 다를 수 있습니다'
                : '10명 중 3명 안쪽. 심한 편은 아닙니다'
          }
          source={source.friction}
        />
        <Kpi
          label="연달아 눌러댄 자리"
          value={fmt.int(frictionCounts.rage_click)}
          sub={frictionCounts.rage_click === 0 ? '눌렀는데 반응이 없어 다시 누른 기록이 없습니다' : '눌렀는데 반응이 없어 다시 누른 횟수'}
          source={source.friction}
        />
        <Kpi
          label="위로 되돌아가 다시 읽은 곳"
          value={fmt.int(frictionCounts.scroll_backtrack)}
          sub={frictionCounts.scroll_backtrack === 0 ? '되돌아가 다시 읽은 기록이 없습니다' : '한 번 읽고 이해가 안 돼 되돌아간 횟수'}
          source={source.friction}
        />
        <Kpi
          label="담았다가 뺀 비율"
          value={fmt.pct(overview.removalRate)}
          sub={overview.removalRate === 0 ? '장바구니에 담은 뒤 다시 뺀 기록이 없습니다' : '장바구니에 넣고 다시 뺀 비율'}
          source={source.overview}
        />
      </div>

      <Panel title="어디서 막혔나" source={source.friction} aside="많이 막힌 자리부터 손보세요">
        <table className="table">
          <thead>
            <tr>
              <th>자리</th>
              <th>무슨 일이 있었나</th>
              <th>횟수</th>
              <th>왜 그럴 수 있나</th>
            </tr>
          </thead>
          <tbody>
            {frictionByLocation.length === 0 ? (
              <tr>
                <td colSpan={4} className="note">
                  {noFriction
                    ? '막힌 자리 기록을 아직 받지 못했습니다. 고객이 상세페이지에서 눌러도 반응이 없거나 위로 되돌아가 읽으면 여기에 자리별로 쌓입니다.'
                    : '이 기간에 막힌 자리가 기록되지 않았습니다.'}
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
        <p className="note">
          "눌러도 아무 일이 없었습니다" 는 실제 고객만 만듭니다. 가상 고객(테스트용 자동 방문)은 누를 수 있는 것만 누르기 때문에,
          이 값이 0이어도 문제가 없다는 뜻은 아닙니다.
        </p>
      </Panel>

      <div className="grid grid--2">
        <Panel
          title="어디서 들어온 고객이 더 담나"
          source={source.entry}
          aside={
            best && base && base.cartRate > 0 && best.source !== base.source
              ? `${best.ko}로 들어온 고객이 목록으로 들어온 고객보다 담기가 ${(best.cartRate / base.cartRate).toFixed(1)}배`
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
          <p className="note">
            막대는 그 길로 들어온 방문 중 장바구니에 담은 비율입니다. 추천 카드로 들어온 고객이 더 담으면 추천을 더 넓게 보여 줄 근거가 됩니다.
            다만 추천 방식이 바뀐 기간끼리는 비교하지 않습니다.
          </p>
        </Panel>

        <Panel title="고객이 지나온 단계" source={source.friction} fold aside="보임 → 열람 → 비교 → 확인 → 담기·구매">
          <Funnel steps={intentFunnel.map((s) => ({ label: s.ko, value: s.value }))} />
          <p className="note">각 단계에 해당하는 고객 행동이 몇 번 기록됐는지 셌습니다. 방문 수가 아니라 행동 횟수입니다.</p>
        </Panel>
      </div>

      <details className="fold">
        <summary>기록된 행동 종류 · 많이 일어난 순서 {eventVolumes.length}개</summary>
        <Panel title="행동별 기록 건수" source={source.friction} fold>
          <BarList items={eventVolumes.map((e) => ({ label: EVENT_KO[e.name] ?? e.name, value: e.count }))} format={fmt.compact} />
        </Panel>
      </details>
    </div>
  );
}
