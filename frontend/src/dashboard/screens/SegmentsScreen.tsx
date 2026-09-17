import { Heatmap, Kpi, Panel } from '../components';
import { SKIN_TONE_ORDER, SKIN_TYPE_KO, fmt } from '../lib/metrics';
import { useBehavior } from '../lib/useBehavior';

const TONE_KO: Record<string, string> = {
  fair: '밝은 톤',
  light: '라이트',
  medium: '미디엄',
  tan: '탠',
  deep: '딥',
};

/**
 * ④ 고객군 · 누가 사는가.
 *
 * 주 축은 피부 타입 × 톤이다. 화장품 시장 세분화의 표준 축이고,
 * 페르소나가 4종 × 5종으로 균등이라 어느 칸을 비교해도 성립한다.
 *
 * 핵심은 전환율 표가 아니라 그 아래 · **고객군별로 보는 콘텐츠가 다른가**다.
 * "건성은 성분을, 지성은 임상 근거를 오래 본다" 가 데이터로 나오면
 * 브랜드는 고객군마다 다른 상세페이지·광고 소재를 쓸 근거를 얻는다.
 *
 * 마트가 붙으면 격자(grid)는 교차 축 마트에서, 단일 축은 persona_segment_daily_kpi 에서 온다.
 * 격자만 없을 때는 KPI 한 칸을 단일 축으로 채우고 격자는 모의로 남긴다 (계약 E4).
 */
export default function SegmentsScreen() {
  const { segmentMatrix, segmentByType, segmentTopContent, sameSkinFilterRate, source } = useBehavior();

  // 표본 50 미만 칸은 비교에서 뺀다 (명세 §3-1)
  const shown = segmentMatrix.flatMap((r) => r.cells.map((c) => ({ type: r.type, ...c }))).filter((c) => c.sessions >= 50);
  const best = shown.length > 0 ? shown.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;
  const bestType = segmentByType && segmentByType.length > 0 ? segmentByType.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;

  const cells: Record<string, Record<string, { value: number; n: number }>> = {};
  for (const r of segmentMatrix) {
    cells[r.type] = {};
    for (const c of r.cells) cells[r.type][c.tone] = { value: c.cartRate, n: c.sessions };
  }
  const topContentOf = (type: string) => segmentTopContent.find((s) => s.type === type);

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        {source.grid === 'real' && best ? (
          <Kpi
            label="최고 전환 고객군"
            value={best.type === 'combination' ? `복합성 · ${TONE_KO[best.tone]}` : `${SKIN_TYPE_KO[best.type]} · ${TONE_KO[best.tone]}`}
            sub={`담기율 ${fmt.pct(best.cartRate)} · n=${fmt.int(best.sessions)}`}
            source="real"
          />
        ) : bestType ? (
          <Kpi
            label="최고 전환 피부 타입"
            value={SKIN_TYPE_KO[bestType.type] ?? bestType.type}
            sub={`담기율 ${fmt.pct(bestType.cartRate)} · n=${fmt.int(bestType.sessions)} · 톤 교차는 마트 요청 중`}
            source="real"
          />
        ) : best ? (
          <Kpi
            label="최고 전환 고객군"
            value={best.type === 'combination' ? `복합성 · ${TONE_KO[best.tone]}` : `${SKIN_TYPE_KO[best.type]} · ${TONE_KO[best.tone]}`}
            sub={`담기율 ${fmt.pct(best.cartRate)} · n=${fmt.int(best.sessions)}`}
            source="mock"
          />
        ) : (
          <Kpi label="최고 전환 고객군" value="-" sub="표본 50 이상인 칸이 없습니다" source={source.grid} />
        )}
        <Kpi
          label="내 피부 타입 리뷰 필터"
          value={fmt.pct(sameSkinFilterRate)}
          sub="필터 사용 방문 중 '나와 같은 타입' 선택"
          source={source.behaviors}
        />
        <Kpi label="고객군 구성" value="4 × 5" sub="타입 × 톤, 칸마다 균등 표본" source="real" />
      </div>

      <Panel title="피부 타입 × 톤 · 장바구니 전환율" source={source.grid} aside="n<50 비움 · n<200 흐림">
        <Heatmap
          rows={segmentMatrix.map((r) => ({ key: r.type, label: SKIN_TYPE_KO[r.type] }))}
          cols={SKIN_TONE_ORDER.map((t) => ({ key: t, label: TONE_KO[t] }))}
          cells={cells}
          format={(v) => fmt.pct(v)}
          rowNote={(type) => {
            const t = topContentOf(type);
            if (type === 'combination') return `톤으로 비교${t ? ` · 가장 오래 보는 것: ${t.top}` : ''}`;
            return t ? `가장 오래 보는 것: ${t.top}` : null;
          }}
        />
        <p className="note">
          복합성 고객(전체의 55%)은 피부 타입으로는 반응이 갈리지 않고 톤으로 갈립니다(실측: 타입 편차 0.053, 톤 0.269). 복합성 행은 톤 칸만 비교하세요.
        </p>
        {source.segments === 'real' && segmentByType ? (
          <table className="table">
            <thead>
              <tr>
                <th>피부 타입 (마트 단일 축)</th>
                <th>상세 조회 세션</th>
                <th>담기율</th>
              </tr>
            </thead>
            <tbody>
              {segmentByType.map((s) => (
                <tr key={s.type} className={s.sessions < 200 ? 'is-thin' : ''}>
                  <td>{SKIN_TYPE_KO[s.type] ?? s.type}</td>
                  <td>{fmt.int(s.sessions)}</td>
                  <td>
                    <strong>{fmt.pct(s.cartRate)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Panel>

      <Panel title="고객군별 가장 오래 본 콘텐츠" source={source.topContent} fold aside="③ 콘텐츠 주목도를 고객군으로 쪼갠 것">
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
