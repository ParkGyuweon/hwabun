import { Heatmap, Kpi, Panel } from '../components';
import { SKIN_TONE_ORDER, SKIN_TYPE_KO, fmt } from '../lib/metrics';
import { useBehavior } from '../lib/useBehavior';

const TONE_KO: Record<string, string> = {
  fair: '가장 밝은 톤',
  light: '밝은 톤',
  medium: '중간 톤',
  tan: '어두운 톤',
  deep: '가장 어두운 톤',
};

/** 이 수보다 방문이 적은 칸은 비교에서 뺀다 (명세 §3-1). Heatmap 도 같은 수로 칸을 비운다 */
const MIN_CELL_VISITS = 50;
/** 이 수보다 적으면 흐리게. 판단은 하되 조심해서 */
const THIN_VISITS = 200;

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
 * 격자만 없을 때는 KPI 한 칸을 단일 축으로 채우고 격자는 비워 둔다 (계약 E4).
 */
export default function SegmentsScreen() {
  const { segmentMatrix, segmentByType, segmentTopContent, sameSkinFilterRate, source } = useBehavior();

  // 표본 50 미만 칸은 비교에서 뺀다 (명세 §3-1)
  const shown = segmentMatrix.flatMap((r) => r.cells.map((c) => ({ type: r.type, ...c }))).filter((c) => c.sessions >= MIN_CELL_VISITS);
  // 0 끼리는 순위가 없다. 담기율이 전부 0 이면 "최고 전환 고객군"도 없다 (2026-09-18)
  const converting = shown.filter((c) => c.cartRate > 0);
  const best = converting.length > 0 ? converting.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;
  const typesConverting = (segmentByType ?? []).filter((t) => t.cartRate > 0);
  const bestType = typesConverting.length > 0 ? typesConverting.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;

  const cells: Record<string, Record<string, { value: number; n: number }>> = {};
  for (const r of segmentMatrix) {
    cells[r.type] = {};
    for (const c of r.cells) cells[r.type][c.tone] = { value: c.cartRate, n: c.sessions };
  }
  const topContentOf = (type: string) => segmentTopContent.find((s) => s.type === type);
  const cellName = (type: string, tone: string) => `${SKIN_TYPE_KO[type] ?? type} · ${TONE_KO[tone] ?? tone}`;
  const noSegments = source.segments === 'none';

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        {source.grid === 'real' && best ? (
          <Kpi
            label="가장 많이 담는 고객군"
            value={cellName(best.type, best.tone)}
            sub={`상세를 본 방문 ${fmt.int(best.sessions)}건 중 ${fmt.pct(best.cartRate)}가 담았습니다`}
            source="real"
          />
        ) : bestType ? (
          <Kpi
            label="가장 많이 담는 피부 타입"
            value={SKIN_TYPE_KO[bestType.type] ?? bestType.type}
            sub={`상세를 본 방문 ${fmt.int(bestType.sessions)}건 중 ${fmt.pct(bestType.cartRate)}가 담았습니다 · 피부 톤까지 나눈 표는 준비 중`}
            source="real"
          />
        ) : best ? (
          <Kpi
            label="가장 많이 담는 고객군"
            value={cellName(best.type, best.tone)}
            sub={`상세를 본 방문 ${fmt.int(best.sessions)}건 중 ${fmt.pct(best.cartRate)}가 담았습니다`}
            source="none"
          />
        ) : (
          <Kpi
            label="가장 많이 담는 고객군"
            value="-"
            sub={
              noSegments
                ? '고객군별 기록을 아직 받지 못했습니다'
                : shown.length > 0
                  ? `방문 ${MIN_CELL_VISITS}건이 넘는 고객군 중 장바구니에 담은 고객이 아직 없습니다`
                  : `방문 ${MIN_CELL_VISITS}건이 넘는 고객군이 아직 없어 판단하지 않습니다`
            }
            source={source.grid}
          />
        )}
        <Kpi
          label="내 피부 타입 리뷰만 골라 본 고객"
          value={fmt.pct(sameSkinFilterRate)}
          sub={sameSkinFilterRate === 0 ? '리뷰를 걸러 본 기록이 아직 없습니다' : "리뷰를 걸러 본 방문 중 '나와 같은 피부 타입'을 고른 비율"}
          source={source.behaviors}
        />
        <Kpi label="고객군을 나누는 기준" value="4 × 5" sub="피부 타입 4가지 × 피부 톤 5단계 = 20칸" source="real" />
      </div>

      <Panel
        title="피부 타입 × 피부 톤 · 장바구니에 담은 비율"
        source={source.grid}
        aside={`방문 ${MIN_CELL_VISITS}건 미만인 칸은 비움 · ${THIN_VISITS}건 미만은 흐림`}
      >
        {segmentMatrix.length === 0 ? (
          <p className="note">
            {noSegments
              ? '고객군별 기록을 아직 받지 못했습니다. 피부 정보를 등록한 고객이 내 상품 상세를 보면 여기에 칸이 채워집니다.'
              : '피부 타입과 톤까지 나눈 표는 계산이 아직 준비되지 않았습니다. 준비되면 자동으로 채워집니다.'}
          </p>
        ) : (
          <Heatmap
            rows={segmentMatrix.map((r) => ({ key: r.type, label: SKIN_TYPE_KO[r.type] }))}
            cols={SKIN_TONE_ORDER.map((t) => ({ key: t, label: TONE_KO[t] }))}
            cells={cells}
            format={(v) => fmt.pct(v)}
            rowNote={(type) => {
              const t = topContentOf(type);
              const top = t && t.top !== '-' ? t.top : null;
              if (type === 'combination') return `톤끼리 비교${top ? ` · 가장 오래 보는 글: ${top}` : ''}`;
              return top ? `가장 오래 보는 글: ${top}` : null;
            }}
          />
        )}
        <p className="note">
          칸의 숫자는 그 고객군이 상세를 본 뒤 장바구니에 담은 비율입니다. 복합성 고객은 피부 타입보다 피부 톤에 따라 반응이 더 갈리는
          편이라, 복합성 행은 톤 칸끼리 비교하세요. 비어 있는 칸은 방문이 {MIN_CELL_VISITS}건이 안 돼 아직 판단하기 이릅니다.
        </p>
        {source.segments === 'real' && segmentByType && segmentByType.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>피부 타입만으로 나눔</th>
                <th>상세를 본 방문</th>
                <th>담은 비율</th>
              </tr>
            </thead>
            <tbody>
              {segmentByType.map((s) => (
                <tr key={s.type} className={s.sessions < THIN_VISITS ? 'is-thin' : ''}>
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

      <Panel title="고객군별 가장 오래 본 글" source={source.topContent} fold aside="'무엇을 보고 사나' 화면을 고객군별로 나눈 것">
        <table className="table">
          <thead>
            <tr>
              <th>고객군</th>
              <th>가장 오래 본 글</th>
              <th>그다음</th>
              <th>가장 오래 본 글에 쓴 시간 비중</th>
            </tr>
          </thead>
          <tbody>
            {segmentTopContent.length === 0 ? (
              <tr>
                <td colSpan={4} className="note">
                  {noSegments
                    ? '고객군별 기록을 아직 받지 못했습니다. 피부 정보를 등록한 고객이 상세페이지 글을 읽으면 채워집니다.'
                    : '고객군별로 어떤 글을 오래 봤는지 계산이 아직 준비되지 않았습니다. 준비되면 자동으로 채워집니다.'}
                </td>
              </tr>
            ) : null}
            {segmentTopContent.map((s) => (
              <tr key={s.type}>
                <td>{SKIN_TYPE_KO[s.type]}</td>
                <td>
                  <strong>{s.top === '-' ? '아직 기록 없음' : s.top}</strong>
                </td>
                <td>{s.second === '-' ? '-' : s.second}</td>
                <td>{s.top === '-' ? '-' : fmt.pct(s.dwellShare)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">
          시간 비중은 그 고객군이 상세페이지 글을 읽은 전체 시간 중 가장 오래 본 글에 쓴 몫입니다. 고객군마다 오래 보는 글이 다르면,
          고객군별로 다른 상세페이지·광고 문구를 쓸 근거가 됩니다.
        </p>
      </Panel>
    </div>
  );
}
