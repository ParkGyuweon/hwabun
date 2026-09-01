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
          <p className="note">
            모든 이벤트에 발생 시점의 의미(intent)가 실려 온다. 단계는 이벤트 이름이 아니라
            이 값으로 센다. friction(마찰)은 단계가 아니라 어느 구간에서든 새는 구멍이라
            아래에 따로 둔다.
          </p>
        </Panel>

        <Panel title="표준 퍼널 · 단계별 이탈" source="mock" aside="GA4 기준 단계">
          <Funnel steps={standardFunnel} />
          <p className="note">구매는 이 테스트 쇼핑몰의 범위 밖이라 장바구니가 마지막 단계다.</p>
        </Panel>
      </div>

      <div className="grid grid--kpi">
        <Kpi
          label="rage_click"
          value={fmt.int(frictionCounts.rage_click)}
          sub="같은 자리 연타 — 반응 없는 UI"
          source="mock"
        />
        <Kpi
          label="dead_click"
          value={fmt.int(frictionCounts.dead_click)}
          sub="눌리지 않는 곳 클릭"
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
        <p className="note">
          위치가 없는 좌절 건수는 할 일이 되지 못한다. dead_click 이 상품 이미지에 몰리면
          확대 기능을 넣으면 되고, scroll_backtrack 이 성분에 몰리면 성분 설명을 쉽게
          고치면 된다. 이 신호들은 상품 선호 벡터에 넣지 않는다 — UI 품질과 상품 선호는
          다른 축이다.
        </p>
      </Panel>

      <div className="grid grid--2">
        <Panel title="이벤트 발생량 상위" source="mock" aside="35종 중 상위 13">
          <BarList
            items={eventVolumes.map((e) => ({ label: e.name, value: e.count }))}
            format={fmt.compact}
          />
          <p className="note">
            section_dwell 이 압도적인 것은 실측과 같다 — 섹션을 벗어날 때마다 구간 체류가
            한 건씩 나간다. 집계 시 같은 섹션은 합산해야 한다 (최댓값이 아니다).
          </p>
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
          <p className="note">
            같은 콘텐츠라도 피부 타입에 따라 머무는 곳이 다르면 그것이 인사이트다.
            콘텐츠별 체류 × 세그먼트 교차는 수집 연결 후 제공한다.
          </p>
        </Panel>
      </div>
    </div>
  );
}
