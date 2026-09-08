import { BarList, Funnel, Kpi, Panel } from '../components';
import {
  eventVolumes,
  fmt,
  frictionByLocation,
  frictionCounts,
  intentFunnel,
  overview,
  skinTypeSegments,
  standardFunnel,
} from '../lib/metrics';

const SKIN_LABEL: Record<string, string> = {
  dry: '건성',
  oily: '지성',
  combination: '복합성',
  normal: '중성',
};

/** 어떤 순서로 행동하고 어디서 빠지는지. intent 퍼널이 이 화면의 중심이다 */
export default function BehaviorScreen() {
  return (
    <div className="stack">
      <div className="grid grid--2">
        <Panel
          title="의도(intent) 퍼널"
          source="mock"
          aside="이벤트가 늘어도 단계 정의가 흔들리지 않는다"
        >
          <Funnel
            steps={intentFunnel.map((s) => ({ label: s.ko, note: s.label, value: s.value }))}
          />
        </Panel>

        <Panel title="표준 퍼널 · 단계별 이탈" source="mock" aside="GA4 기준 단계">
          <Funnel steps={standardFunnel} />
          <p className="note">구매 이벤트 없음. 장바구니가 마지막 단계.</p>
        </Panel>
      </div>

      <div className="grid grid--kpi">
        <Kpi
          label="rage_click"
          value={fmt.int(frictionCounts.rage_click)}
          sub="같은 자리 연타 — 반응 없는 UI"
          source="mock"
        />
        {/*
          dead_click 은 실사용자 전용이다. 프론트 훅은 정상 동작하지만
          가상 사용자가 이 행동을 만들지 못한다 — 러너는 유효한 요소만
          클릭하고, 코드 생성기에는 이 행동이 없다. 합성 로그만 도는 동안
          이 값은 항상 0 이므로, 그 0 이 "마찰 없음" 으로 읽히면 안 된다.
        */}
        <Kpi
          label="dead_click"
          value={fmt.int(frictionCounts.dead_click)}
          sub="눌리지 않는 곳 클릭 — 실사용자 전용"
          source="mock"
        />
        <Kpi
          label="scroll_backtrack"
          value={fmt.int(frictionCounts.scroll_backtrack)}
          sub="되돌아 읽기 — 비교·재확인"
          source="mock"
        />
        <Kpi
          label="장바구니 제거율"
          value={fmt.pct(overview.removalRate)}
          sub="담기 대비 제거"
          source="mock"
        />
      </div>

      <Panel
        title="마찰 위치 — 어디서 막히는가"
        source="mock"
        aside="좌절 신호는 상품이 아니라 화면의 문제일 수 있다"
      >
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
        <p className="note">좌절이 몰린 위치가 할 일이다.</p>
      </Panel>

      <div className="grid grid--2">
        <Panel title="이벤트 발생량 상위" source="mock" aside="36종 중 상위 13">
          <BarList
            items={eventVolumes.map((e) => ({ label: e.name, value: e.count }))}
            format={fmt.compact}
          />
        </Panel>

        <Panel title="피부 타입 세그먼트" aside="분포는 리뷰 실측 · 전환율은 모의">
          <BarList
            items={skinTypeSegments.map((s) => ({
              label: SKIN_LABEL[s.type] ?? s.type,
              value: s.share * 100,
              hint: `장바구니 ${fmt.pct(s.cartRate)}`,
            }))}
            format={(v) => `${v.toFixed(1)}%`}
          />
        </Panel>
      </div>
    </div>
  );
}
