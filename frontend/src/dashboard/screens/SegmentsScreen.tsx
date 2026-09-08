import { Kpi, Panel } from '../components';
import {
  SKIN_TYPE_KO,
  fmt,
  sameSkinFilterRate,
  segmentMatrix,
  segmentTopContent,
} from '../lib/metrics';

const TONE_KO: Record<string, string> = {
  fair: 'Fair',
  light: 'Light',
  medium: 'Medium',
  tan: 'Tan',
  deep: 'Deep',
};

/**
 * ④ 고객군 · 누가 사는가.
 *
 * 주 축은 피부 타입 × 톤이다. 화장품 시장 세분화의 표준 축이고,
 * 페르소나 100명이 4종 × 5종으로 정확히 균등이라 어느 칸을 비교해도 성립한다.
 *
 * 핵심은 전환율 표가 아니라 그 아래 · **고객군별로 보는 콘텐츠가 다른가**다.
 * "건성은 성분을, 지성은 임상 근거를 오래 본다" 가 데이터로 나오면
 * 브랜드는 고객군마다 다른 상세페이지·광고 소재를 쓸 근거를 얻는다.
 */
export default function SegmentsScreen() {
  /** 전 칸 중 최댓값. 셀 배경 농도의 기준선이다 */
  const maxRate = Math.max(...segmentMatrix.flatMap((r) => r.cells.map((c) => c.cartRate)));
  const best = segmentMatrix
    .flatMap((r) => r.cells.map((c) => ({ type: r.type, ...c })))
    .reduce((a, b) => (a.cartRate >= b.cartRate ? a : b));

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label="최고 전환 고객군"
          value={`${SKIN_TYPE_KO[best.type]} · ${TONE_KO[best.tone]}`}
          sub={`담기율 ${fmt.pct(best.cartRate)}`}
          source="mock"
        />
        <Kpi
          label="내 피부 타입 리뷰 필터"
          value={fmt.pct(sameSkinFilterRate)}
          sub="필터 사용 방문 중 '나와 같은 타입' 선택"
          source="mock"
        />
        <Kpi label="고객군 구성" value="4 × 5" sub="타입 × 톤, 칸마다 균등 표본" source="real" />
      </div>

      <Panel
        title="피부 타입 × 톤 · 장바구니 전환율"
        source="mock"
        aside="농도 = 전환율. 색이 아니라 진하기로만 읽는다"
      >
        <table className="table table--matrix">
          <thead>
            <tr>
              <th>타입 \ 톤</th>
              {segmentMatrix[0].cells.map((c) => (
                <th key={c.tone}>{TONE_KO[c.tone]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segmentMatrix.map((row) => (
              <tr key={row.type}>
                <td>{SKIN_TYPE_KO[row.type]}</td>
                {row.cells.map((cell) => (
                  <td
                    key={cell.tone}
                    className="matrix__cell"
                    style={{
                      // 브랜드 초록 한 색의 농도로만 표현한다. 다색 히트맵은
                      // 좋고 나쁨을 화면이 단정해 버린다
                      // 테마가 바뀌면 같이 바뀌어야 한다. 값을 박아두면 테마 색과 어긋난다
                      background: `rgb(var(--brand-rgb) / ${(cell.cartRate / maxRate) * 0.85})`,
                    }}
                    title={`표본 ${cell.sessions}건`}
                  >
                    {fmt.pct(cell.cartRate)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">칸에 올리면 표본 수</p>
      </Panel>

      <Panel
        title="고객군별 가장 오래 본 콘텐츠"
        source="mock"
        aside="③ 콘텐츠 주목도를 고객군으로 쪼갠 것"
      >
        <table className="table">
          <thead>
            <tr>
              <th>고객군</th>
              <th>1위 콘텐츠</th>
              <th>2위</th>
              <th>1위 체류 비중</th>
            </tr>
          </thead>
          <tbody>
            {segmentTopContent.map((s) => (
              <tr key={s.type}>
                <td>{SKIN_TYPE_KO[s.type]}</td>
                <td>
                  <strong>{s.top}</strong>
                </td>
                <td>{s.second}</td>
                <td>{fmt.pct(s.dwellShare)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
