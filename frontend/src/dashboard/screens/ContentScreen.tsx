import { BarList, Kpi, Panel, Scatter } from '../components';
import { contentAttention, fmt, scrapedIngredients, validationBehaviors } from '../lib/metrics';
import { labelKo } from '../../lib/formLabels';

/**
 * ③ 정보 관심도 · 이 대시보드의 존재 이유.
 *
 * 일반 웹 분석은 "상세 이탈률이 높다" 에서 멈춘다. 이 화면은 그 다음을 말한다 ·
 * **무엇을 보여줘야 사는가.** 콘텐츠 단위 체류(`section_dwell` + `content_kind`)를
 * 수집하는 우리만 만들 수 있는 화면이다.
 *
 * 체류 시간만 세우지 않고 전환 기여를 나란히 둔다. 오래 보는 것과 사게 만드는 것은
 * 다른 축이고, 그 어긋남(오래 보는데 전환이 낮다 = 설명이 어렵다)이 바로
 * 브랜드에 파는 인사이트다.
 */
export default function ContentScreen() {
  const topLift = [...contentAttention].sort((a, b) => b.conversionLift - a.conversionLift)[0];
  const longButWeak = contentAttention.find((c) => c.avgDwellMs > 10000 && c.conversionLift < 1);

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label="전환 기여 1위 콘텐츠"
          value={topLift.ko}
          sub={`본 방문의 담기율이 평균의 ${topLift.conversionLift.toFixed(1)}배`}
          source="mock"
        />
        <Kpi
          label="개선 필요 콘텐츠"
          value={longButWeak ? longButWeak.ko : '없음'}
          sub={longButWeak ? '오래 보는데 전환이 낮다. 설명이 어렵다는 신호' : ''}
          source="mock"
        />
        <Kpi
          label="사용자가 가장 많이 드래그한 성분"
          value={labelKo(scrapedIngredients[0].name)}
          sub={`${fmt.int(scrapedIngredients[0].count)}회 · 가장 관심이 큰 성분`}
          source="mock"
        />
        <Kpi
          label="검증 행동 실행률"
          value={fmt.pct(validationBehaviors[0].doneRate)}
          sub="전성분 펼쳐 보기 기준"
          source="mock"
        />
      </div>

      <Panel
        title="콘텐츠별 주목도 × 전환 기여"
        source="mock"
        aside="co_visible_blocks ≤ 2 인 체류만 집계 · 겹쳐 보인 체류는 귀속 불가"
      >
        <Scatter
          points={contentAttention.map((c) => ({ label: c.ko, x: c.avgDwellMs / 1000, y: c.conversionLift, n: c.sampleSize }))}
        />
        <p className="note">
          오른쪽 아래 칸(오래 보지만 안 산다)이 손볼 곳, 왼쪽 위 칸(짧게 보지만 결정에 기여)이 위로 올릴 것. 점 크기는 표본.
        </p>
        <details className="fold">
          <summary>표로 보기</summary>
        <table className="table">
          <thead>
            <tr>
              <th>콘텐츠</th>
              <th>평균 체류</th>
              <th>열람률</th>
              <th>전환 기여</th>
              <th>표본</th>
            </tr>
          </thead>
          <tbody>
            {contentAttention.map((c) => (
              <tr key={c.kind} className={c.sampleSize < 500 ? 'is-thin' : ''}>
                <td>
                  {c.ko} <span className="table__code">{c.kind}</span>
                </td>
                <td>{(c.avgDwellMs / 1000).toFixed(1)}초</td>
                <td>{fmt.pct(c.viewRate)}</td>
                <td>
                  <strong>{c.conversionLift.toFixed(1)}×</strong>
                  {c.conversionLift < 1 ? ' ↓' : ''}
                </td>
                <td>{fmt.int(c.sampleSize)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">전환 기여 = 본 방문 담기율 ÷ 평균. 흐린 행은 표본 부족.</p>
        </details>
      </Panel>

      <div className="grid grid--2">
        <Panel
          title="사용자가 드래그한 성분 TOP 10"
          source="mock"
          aside="원문 미저장 · 성분 사전 표준명만 (vocab 0.4)"
        >
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: labelKo(i.name),
              value: i.count,
              hint: `복사 ${i.copyCount}`,
            }))}
          />
          <p className="note">드래그 횟수는 관심의 크기입니다. 설명이 어려운지는 이 성분 구간의 되돌아 읽기·이탈·담기율을 함께 봐야 알 수 있고, 그 집계는 데이터 마트가 만들면 여기에 붙습니다.</p>
        </Panel>

        <Panel title="검증 행동 × 전환" source="mock" aside="한 방문 vs 안 한 방문">
          <table className="table">
            <thead>
              <tr>
                <th>행동</th>
                <th>실행률</th>
                <th>했을 때 담기율</th>
                <th>안 했을 때</th>
              </tr>
            </thead>
            <tbody>
              {validationBehaviors.map((v) => (
                <tr key={v.event}>
                  <td>
                    {v.ko} <span className="table__code">{v.event}</span>
                  </td>
                  <td>{fmt.pct(v.doneRate)}</td>
                  <td>
                    <strong>{fmt.pct(v.cartRateWith)}</strong>
                  </td>
                  <td>{fmt.pct(v.cartRateWithout)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">상관이지 인과는 아니다.</p>
        </Panel>
      </div>
    </div>
  );
}
