import { BarList, Kpi, Panel } from '../components';
import { contentAttention, fmt, scrapedIngredients, validationBehaviors } from '../lib/metrics';

/**
 * ③ 정보 관심도 — 이 대시보드의 존재 이유.
 *
 * 일반 웹 분석은 "상세 이탈률이 높다" 에서 멈춘다. 이 화면은 그 다음을 말한다 —
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
          sub={longButWeak ? '오래 보는데 전환이 낮다 — 설명이 어렵다는 신호' : ''}
          source="mock"
        />
        <Kpi
          label="가장 많이 긁힌 성분"
          value={scrapedIngredients[0].name}
          sub={`${fmt.int(scrapedIngredients[0].count)}회 — 설명 부족 신호`}
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
        aside="co_visible_blocks ≤ 2 인 체류만 집계 — 겹쳐 보인 체류는 귀속 불가"
      >
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
        <p className="note">
          전환 기여 = 그 콘텐츠를 본 방문의 장바구니 담기율 ÷ 전체 평균. 흐린 행은 표본
          500건 미만 — 아직 판단 근거로 쓰지 말 것.
        </p>
      </Panel>

      <div className="grid grid--2">
        <Panel
          title="긁어간 성분 TOP 10"
          source="mock"
          aside="원문 미저장 — 성분 사전 표준명만 (vocab 0.4)"
        >
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: i.name,
              value: i.count,
              hint: `복사 ${i.copyCount}`,
            }))}
          />
          <p className="note">
            사용자는 모르는 성분명을 만나면 그 부분만 긁어 밖에서 검색한다. 반복해서 긁히는
            성분은 상세페이지가 그 성분을 설명하지 못하고 있다는 뜻 — 가장 직접적인
            상세페이지 개선 지시다. 성분 사전은 추천 엔진과 같은 파일을 쓰므로 "이 성분을
            긁은 사람" 과 "이 성분이 든 상품" 이 같은 이름으로 조인된다.
          </p>
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
          <p className="note">
            검증 행동을 한 방문의 담기율이 2~3배 높다. 다만 이것은 상관이지 인과가 아니다 —
            살 사람이 검증하는 것일 수 있다. 인과는 정보 배치를 바꾼 A/B 로만 확인된다.
          </p>
        </Panel>
      </div>
    </div>
  );
}
