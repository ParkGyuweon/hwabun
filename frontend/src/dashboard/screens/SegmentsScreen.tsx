import { Heatmap, Kpi, Panel } from '../components';
import { PRICE_BIN_ORDER, SKIN_TONE_ORDER, SKIN_TYPE_KO, fmt, priceBinKo } from '../lib/metrics';
import type { CohortM } from '../lib/behavior';
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
/** 코호트 지표 이름 → 사장님 말 */
const COHORT_METRIC_KO: Record<string, string> = {
  detail_entry_rate: '상품을 보고 상세까지 들어온 비율',
  view_to_cart_rate: '상세를 보고 장바구니에 담은 비율',
  information_view_rate: '성분·리뷰까지 읽은 비율',
};

/** 분위 위치 → 한 마디. 비교 대상은 이름을 모르는 비슷한 브랜드들이다 */
const POSITION_KO: Record<NonNullable<CohortM['metrics'][number]['position']>, { label: string; tone: 'high' | 'mid' | 'low' }> = {
  above_p75: { label: '상위 25% 안', tone: 'high' },
  p50_p75: { label: '중간보다 위', tone: 'mid' },
  p25_p50: { label: '중간보다 아래', tone: 'mid' },
  below_p25: { label: '하위 25%', tone: 'low' },
};

/** "2026-09-07" → "9월 7일" */
function dateKo(iso: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[1])}월 ${Number(m[2])}일` : iso;
}

/**
 * 비슷한 브랜드 대비 내 위치 (계약 §3 E4 cohort). 상품 수 구간과 주력 가격대가 같은 브랜드들과 비교한다.
 * 다른 브랜드가 누구인지는 응답에 없고, 화면도 묻지 않는다. 억제(is_suppressed)면 숫자 없이 "표본 부족" 만 적는다.
 */
function CohortBadge({ cohort }: { cohort: CohortM }) {
  const group = `상품 ${cohort.productBand.replace('-', '~')}개 · 주력 가격대 ${priceBinKo(cohort.priceBin)}`;
  const week = `${dateKo(cohort.weekStart)}~${dateKo(cohort.weekEnd)} 한 주`;
  if (cohort.suppressed) {
    return (
      <section className="cohort cohort--suppressed" aria-label="비슷한 브랜드와 비교">
        <p className="cohort__eyebrow">비슷한 브랜드와 비교 · {week}</p>
        <p className="cohort__line">
          <strong>표본 부족</strong> · 나와 비슷한 브랜드({group})가 아직 5곳이 안 되거나 한 브랜드에 치우쳐 있어 비교 숫자를 내지 않습니다.
        </p>
        <p className="note">비슷한 브랜드가 더 모이면 여기에 내 위치가 보입니다. 다른 브랜드의 이름이나 숫자는 어디에도 보이지 않습니다.</p>
      </section>
    );
  }
  return (
    <section className={`cohort${cohort.sampleSufficient ? '' : ' is-thin'}`} aria-label="비슷한 브랜드와 비교">
      <p className="cohort__eyebrow">
        비슷한 브랜드 {fmt.int(cohort.brandCount)}곳과 비교 · {group} · {week}
      </p>
      <ul className="cohort__metrics">
        {cohort.metrics.map((m) => {
          const pos = m.position ? POSITION_KO[m.position] : null;
          return (
            <li key={m.name} className={`cohort__metric${pos ? ` cohort__metric--${pos.tone}` : ''}`}>
              <span className="cohort__name">{COHORT_METRIC_KO[m.name] ?? m.name}</span>
              <strong className="cohort__pos">{pos ? pos.label : '비교 불가'}</strong>
              <span className="cohort__nums">
                {m.mine !== null ? `내 브랜드 ${fmt.pct(m.mine)}` : '내 값 없음'}
                {m.p50 !== null ? ` · 비슷한 브랜드 중간값 ${fmt.pct(m.p50)}` : ''}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="note">
        {cohort.sampleSufficient
          ? '중간값은 비슷한 브랜드들을 한 줄로 세웠을 때 가운데 브랜드의 값입니다. 다른 브랜드의 이름이나 개별 숫자는 보이지 않습니다.'
          : '이 주에는 비슷한 브랜드들의 방문이 적어 참고만 해 주세요. 다른 브랜드의 이름이나 개별 숫자는 보이지 않습니다.'}
      </p>
    </section>
  );
}

export default function SegmentsScreen() {
  const { segmentMatrix, segmentByType, segmentTopContent, sameSkinFilterRate, priceBands, segmentPriceGrid, cohort, source } = useBehavior();

  /** 가격대 표. 정해진 5구간 순서 + 가격 미입력 행은 맨 아래 */
  const binIndex = (bin: string | null) => (bin === null ? 99 : (PRICE_BIN_ORDER as readonly string[]).indexOf(bin));
  const bandRows = [...priceBands].sort((a, b) => binIndex(a.bin) - binIndex(b.bin));
  const bandBest = bandRows.filter((b) => b.sessions >= THIN_VISITS && (b.cartRate ?? 0) > 0).sort((a, b) => (b.cartRate ?? 0) - (a.cartRate ?? 0))[0] ?? null;

  /** 피부 타입 × 가격대 칸. 가격 미입력 칸은 격자에 넣지 않는다 (열이 없다) */
  const priceCells: Record<string, Record<string, { value: number; n: number }>> = {};
  for (const r of segmentPriceGrid) {
    priceCells[r.type] = {};
    for (const c of r.cells) if (c.bin !== null) priceCells[r.type][c.bin] = { value: c.cartRate, n: c.sessions };
  }
  const priceGridFilled = segmentPriceGrid.flatMap((r) => r.cells).filter((c) => c.bin !== null && c.sessions >= MIN_CELL_VISITS).length;

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
      {/* 비슷한 브랜드 대비 내 위치. 마트가 없으면(null) 자리도 없다 — 다른 브랜드와의 비교는 흉내 내지 않는다 */}
      {cohort ? <CohortBadge cohort={cohort} /> : null}

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

      <Panel
        title="가격대별 반응"
        source={source.priceBands}
        aside={bandBest ? `가장 잘 담는 가격대: ${priceBinKo(bandBest.bin)} · ${fmt.pct(bandBest.cartRate ?? 0)}` : '내 상품을 가격대로 나눠 본 것'}
      >
        {bandRows.length === 0 ? (
          <p className="note">
            {source.priceBands === 'none'
              ? '가격대별 기록은 계산이 아직 준비되지 않았습니다. 준비되면 자동으로 채워집니다.'
              : '이 기간에 가격대별로 셀 기록이 아직 없습니다. 고객이 내 상품 상세를 보면 채워집니다.'}
          </p>
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>가격대</th>
                  <th>내 상품</th>
                  <th>상세를 본 방문</th>
                  <th>상세까지 들어온 비율</th>
                  <th>담은 비율</th>
                  <th>구매한 비율</th>
                </tr>
              </thead>
              <tbody>
                {bandRows.map((b) => (
                  <tr
                    key={b.bin ?? 'null'}
                    className={b.sessions < THIN_VISITS ? 'is-thin' : ''}
                    title={b.sessions < THIN_VISITS ? `상세를 본 방문 ${fmt.int(b.sessions)}건 · ${THIN_VISITS}건이 안 돼 참고만 해 주세요` : undefined}
                  >
                    <td>{priceBinKo(b.bin)}</td>
                    <td>{fmt.int(b.productCount)}개</td>
                    <td>{fmt.int(b.sessions)}</td>
                    <td>{b.detailEntryRate === null ? '-' : fmt.pct(b.detailEntryRate)}</td>
                    <td>
                      <strong>{b.cartRate === null ? '-' : fmt.pct(b.cartRate)}</strong>
                    </td>
                    <td>{b.purchaseRate === null ? '-' : fmt.pct(b.purchaseRate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note">
              내 상품을 가격대로 나눠, 각 가격대 상품의 상세를 본 고객 중 장바구니에 담거나 구매한 비율입니다. 한 고객이 여러 가격대 상품을 보면
              가격대마다 한 번씩 세므로 방문 수를 더해 전체 방문으로 읽지 마세요. 흐린 줄은 방문이 {THIN_VISITS}건이 안 돼 참고만 해 주세요.
              {bandRows.some((b) => b.bin === null) ? ' "가격 미입력"은 가격이 등록되지 않은 상품들의 반응입니다.' : ''}
            </p>
          </>
        )}
      </Panel>

      <Panel
        title="피부 타입 × 가격대 · 장바구니에 담은 비율"
        source={source.segmentPriceGrid}
        aside={`방문 ${MIN_CELL_VISITS}건 미만인 칸은 비움 · ${THIN_VISITS}건 미만은 흐림`}
      >
        {segmentPriceGrid.length === 0 ? (
          <p className="note">
            {source.segmentPriceGrid === 'none'
              ? '피부 타입과 가격대를 함께 나눈 표는 계산이 아직 준비되지 않았습니다. 준비되면 자동으로 채워집니다.'
              : '이 기간에 피부 타입과 가격대로 나눠 셀 기록이 아직 없습니다.'}
          </p>
        ) : (
          <>
            <Heatmap
              rows={segmentPriceGrid.map((r) => ({ key: r.type, label: SKIN_TYPE_KO[r.type] ?? r.type }))}
              cols={PRICE_BIN_ORDER.map((b) => ({ key: b, label: priceBinKo(b) }))}
              cells={priceCells}
              format={(v) => fmt.pct(v)}
            />
            <p className="note">
              {priceGridFilled === 0
                ? `20칸 중 방문 ${MIN_CELL_VISITS}건이 넘는 칸이 아직 없습니다. 피부 정보를 등록한 고객이 더 다녀가면 채워집니다.`
                : priceGridFilled < 8
                  ? `20칸 중 ${priceGridFilled}칸만 찼습니다. 피부 정보를 등록한 고객이 아직 일부 타입에 몰려 있어 비어 있는 칸이 많은 것이 정상입니다.`
                  : '어느 피부 타입 고객이 어느 가격대에서 잘 담는지 봅니다. 비어 있는 칸은 방문이 적어 아직 판단하기 이릅니다.'}
            </p>
          </>
        )}
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
