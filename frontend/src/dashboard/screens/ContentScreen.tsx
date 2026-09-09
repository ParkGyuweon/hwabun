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
        <p className="panel__lead">
          내 브랜드 상품의 <b>상세페이지 안</b> 콘텐츠 10종만 봅니다. 목록·장바구니 요소는 상세 결정과 무관해 제외했습니다.
        </p>
        <Scatter
          points={contentAttention.map((c) => ({ label: c.ko, x: c.avgDwellMs / 1000, y: c.conversionLift, n: c.sampleSize }))}
        />
        <p className="note">
          오른쪽 아래 칸(오래 보지만 안 산다)이 손볼 곳, 왼쪽 위 칸(짧게 보지만 결정에 기여)이 위로 올릴 것. 점 크기는 표본.
        </p>

        <details className="defn">
          <summary>이 그래프의 정의와 선정 기준</summary>
          <dl className="defn__list">
            <dt>무엇을 그리나</dt>
            <dd>
              상세페이지 콘텐츠 <b>10종</b>. 계약 <code>content_kind</code> 21종 중 상품 상세 안에서 읽는 것만 골랐습니다.
              넣은 것은 성분 목록·성분 특징·임상 결과·사용자 리뷰·평점 분포·제품 소개·추가 설명·사용법·브랜드 소개·상품 이미지입니다.
              제외한 것은 목록·장바구니·내비게이션 요소(<code>product_card</code>·<code>cart_item</code>·<code>navigation</code> 등)입니다.
            </dd>
            <dt>가로 · 주목도</dt>
            <dd>
              그 콘텐츠의 체류 시간 합계 ÷ 상세 조회 세션 수. <code>section_dwell</code> 이벤트를 <code>content_kind</code> 별로 합산합니다.
              한 화면에 블록이 3개 이상 겹쳐 보인 체류(<code>co_visible_blocks &gt; 2</code>)는 어느 콘텐츠를 향한 것인지 단정할 수 없어 뺍니다.
            </dd>
            <dt>세로 · 담기 기여</dt>
            <dd>
              그 콘텐츠를 본 세션의 담기율 ÷ 내 브랜드 전체 담기율. 1.0×이면 평균과 같고, 1.6×이면 그 콘텐츠를 본 사람이
              평균보다 1.6배 더 담았다는 뜻입니다. <b>상관이지 인과가 아닙니다</b> — 살 마음이 큰 사람이 성분을 더 볼 수도 있습니다.
            </dd>
            <dt>원 크기 · 표본</dt>
            <dd>그 콘텐츠가 한 번이라도 보인 세션 수. 200 미만은 흐리게, 50 미만은 그리지 않습니다.</dd>
            <dt>기준선</dt>
            <dd>세로 점선은 담기 기여 1.0×. 가로 점선은 콘텐츠 10종의 주목도 단순 평균입니다.</dd>
            <dt>지금 상태</dt>
            <dd>
              체류·표본은 계약에 정의가 있고(<code>content_daily_kpi</code>), <b>담기 기여와 콘텐츠 선정 목록은 아직 계약에 없습니다</b>.
              지금 화면 값은 모의 집계이고, 데이터 파트에 마트를 요청해 둔 상태입니다.
            </dd>
          </dl>
        </details>
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
