import { useState } from 'react';
import { Heatmap, Kpi, Panel } from '../components';
import { PRICE_BIN_ORDER, SKIN_TONE_ORDER, SKIN_TYPE_KO, fmt, priceBinKo } from '../lib/metrics';
import type { CohortM, SegmentByType } from '../lib/behavior';
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
        <p className="cohort__line" title={`비슷한 브랜드(${group})가 5곳 미만이거나 한 곳에 치우쳐 숫자를 내지 않습니다. 다른 브랜드 이름·숫자는 보이지 않습니다`}>
          <strong>비교할 브랜드가 부족합니다</strong> · 비슷한 브랜드가 아직 5곳 미만
        </p>
      </section>
    );
  }
  return (
    <section className={`cohort${cohort.sampleSufficient ? '' : ' is-thin'}`} aria-label="비슷한 브랜드와 비교">
      <p
        className="cohort__eyebrow"
        title={
          cohort.sampleSufficient
            ? '비슷한 브랜드 범위 = 한 줄로 세웠을 때 가운데 절반이 드는 구간. 다른 브랜드 이름·개별 숫자는 보이지 않습니다'
            : '이 주는 비슷한 브랜드의 방문이 적어 참고만 해 주세요. 다른 브랜드 이름·개별 숫자는 보이지 않습니다'
        }
      >
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
                {m.p25 !== null && m.p75 !== null
                  ? ` · 비슷한 브랜드 ${fmt.pct(m.p25)}~${fmt.pct(m.p75)}${m.p50 !== null ? ` (중간 ${fmt.pct(m.p50)})` : ''}`
                  : m.p50 !== null
                    ? ` · 비슷한 브랜드 중간값 ${fmt.pct(m.p50)}`
                    : ''}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** 피부 타입·톤 한 축 표. 두 표가 모양이 같다 */
function AxisTable({ head, rows, label }: { head: string; rows: SegmentByType[]; label: (key: string) => string }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>{head}</th>
          <th title="이 기간에 들른 횟수 · 같은 고객이 여러 번 오면 따로 셉니다">방문</th>
          <th title="상세를 연 방문 수. 한 고객이 여러 번 오면 여러 건입니다">상세 방문</th>
          <th title="상세를 본 뒤 담은 비율">담기</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.type} className={s.sessions < THIN_VISITS ? 'is-thin' : ''}>
            <td>{label(s.type)}</td>
            {/* 방문은 하루 단위로 센 합이라 같은 고객이 여러 번 오면 따로 센다 */}
            <td>{fmt.int(s.visits)}건</td>
            <td>{fmt.int(s.sessions)}건</td>
            <td>
              <strong>{fmt.pct(s.cartRate)}</strong>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SegmentsScreen() {
  const [priceMetric, setPriceMetric] = useState<'cart' | 'purchase'>('cart');
  const { segmentMatrix, segmentByType, segmentByTone, segmentTopContent, sameSkinFilterRate, priceBands, segmentPriceGrid, cohort, source } = useBehavior();

  /** 가격대 표. 정해진 5구간 순서 + 가격 미입력 행은 맨 아래 */
  const binIndex = (bin: string | null) => (bin === null ? 99 : (PRICE_BIN_ORDER as readonly string[]).indexOf(bin));
  const bandRows = [...priceBands].sort((a, b) => binIndex(a.bin) - binIndex(b.bin));
  const bandBest = bandRows.filter((b) => b.sessions >= THIN_VISITS && (b.cartRate ?? 0) > 0).sort((a, b) => (b.cartRate ?? 0) - (a.cartRate ?? 0))[0] ?? null;

  /** 피부 타입 × 가격대 칸. 가격 미입력 칸은 격자에 넣지 않는다 (열이 없다) */
  const priceCells: Record<string, Record<string, { value: number; n: number }>> = {};
  for (const r of segmentPriceGrid) {
    priceCells[r.type] = {};
    for (const c of r.cells) if (c.bin !== null) priceCells[r.type][c.bin] = { value: priceMetric === 'cart' ? c.cartRate : c.purchaseRate ?? 0, n: c.sessions };
  }
  const priceGridFilled = segmentPriceGrid.flatMap((r) => r.cells).filter((c) => c.bin !== null && c.sessions >= MIN_CELL_VISITS).length;

  // 표본 50 미만 칸은 비교에서 뺀다 (명세 §3-1)
  const shown = segmentMatrix.flatMap((r) => r.cells.map((c) => ({ type: r.type, ...c }))).filter((c) => c.sessions >= MIN_CELL_VISITS);
  // 0 끼리는 순위가 없다. 담기율이 전부 0 이면 "최고 전환 고객군"도 없다 (2026-09-18)
  const converting = shown.filter((c) => c.cartRate > 0);
  const best = converting.length > 0 ? converting.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;
  const typesConverting = (segmentByType ?? []).filter((t) => t.cartRate > 0);
  const bestType = typesConverting.length > 0 ? typesConverting.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;
  const tonesConverting = segmentByTone.filter((t) => t.cartRate > 0 && t.sessions >= MIN_CELL_VISITS);
  const bestTone = tonesConverting.length > 0 ? tonesConverting.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b)) : null;

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
            sub={`상세 ${fmt.int(best.sessions)}건 중 ${fmt.pct(best.cartRate)}`}
            source="real"
          />
        ) : bestType ? (
          <Kpi
            label="가장 많이 담는 피부 타입"
            value={SKIN_TYPE_KO[bestType.type] ?? bestType.type}
            sub={`상세 ${fmt.int(bestType.sessions)}건 중 ${fmt.pct(bestType.cartRate)}`}
            source="real"
          />
        ) : best ? (
          <Kpi
            label="가장 많이 담는 고객군"
            value={cellName(best.type, best.tone)}
            sub={`상세 ${fmt.int(best.sessions)}건 중 ${fmt.pct(best.cartRate)}`}
            source="none"
          />
        ) : (
          <Kpi
            label="가장 많이 담는 고객군"
            value="-"
            sub={noSegments ? '아직 기록 없음' : shown.length > 0 ? '담은 고객 아직 없음' : `방문 ${MIN_CELL_VISITS}건 넘는 칸 없음`}
            source={source.grid}
          />
        )}
        <Kpi
          label="내 피부 타입 리뷰만 골라 본 고객"
          value={fmt.pct(sameSkinFilterRate)}
          sub={sameSkinFilterRate === 0 ? '아직 기록 없음' : '리뷰 걸러 본 방문 중'}
          source={source.behaviors}
        />
        <Kpi
          label="가장 많이 담는 피부 톤"
          value={bestTone ? TONE_KO[bestTone.type] ?? bestTone.type : '-'}
          sub={bestTone ? `상세 ${fmt.int(bestTone.sessions)}건 중 ${fmt.pct(bestTone.cartRate)}` : noSegments ? '아직 기록 없음' : '담은 고객 아직 없음'}
          source={source.segments}
        />
      </div>

      <Panel
        title="피부 타입 × 피부 톤 · 장바구니에 담은 비율"
        source={source.grid}
        aside={`방문 ${MIN_CELL_VISITS}건 미만 칸은 비움 · ${THIN_VISITS}건 미만은 흐리게`}
      >
        {segmentMatrix.length === 0 ? (
          <p className="note">{noSegments ? '아직 기록이 없습니다' : '계산 준비 중입니다'}</p>
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
        <p className="note">복합성 행은 톤끼리 비교하세요</p>
        {source.segments === 'real' && ((segmentByType?.length ?? 0) > 0 || segmentByTone.length > 0) ? (
          <div className="grid grid--2">
            {segmentByType && segmentByType.length > 0 ? <AxisTable head="피부 타입" rows={segmentByType} label={(k) => SKIN_TYPE_KO[k] ?? k} /> : null}
            {segmentByTone.length > 0 ? <AxisTable head="피부 톤" rows={segmentByTone} label={(k) => TONE_KO[k] ?? k} /> : null}
          </div>
        ) : null}
      </Panel>

      <Panel
        title="가격대별 반응"
        source={source.priceBands}
        aside={bandBest ? `최고 ${priceBinKo(bandBest.bin)} · ${fmt.pct(bandBest.cartRate ?? 0)}` : '내 상품을 가격대로 나눔'}
      >
        {bandRows.length === 0 ? (
          <p className="note">{source.priceBands === 'none' ? '계산 준비 중입니다' : '아직 기록이 없습니다'}</p>
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th title="'가격 미입력'은 가격이 등록되지 않은 상품">가격대</th>
                  <th>내 상품</th>
                  <th title="한 고객이 여러 가격대를 보면 가격대마다 한 번씩 셉니다. 더해서 전체 방문으로 읽지 마세요">상세 방문</th>
                  <th title="상품을 보고 상세까지 들어온 비율">상세로 들어옴</th>
                  <th title="상세를 본 뒤 담은 비율 · 아래는 담은 방문 수">담기</th>
                  <th title="상세를 본 뒤 구매한 비율 · 아래는 구매한 방문 수">구매</th>
                </tr>
              </thead>
              <tbody>
                {bandRows.map((b) => (
                  <tr
                    key={b.bin ?? 'null'}
                    className={b.sessions < THIN_VISITS ? 'is-thin' : ''}
                    title={b.sessions < THIN_VISITS ? `방문 ${THIN_VISITS}건 미만 · 참고만` : undefined}
                  >
                    <td>{priceBinKo(b.bin)}</td>
                    <td>{fmt.int(b.productCount)}개</td>
                    <td>{fmt.int(b.sessions)}</td>
                    <td>{b.detailEntryRate === null ? '-' : fmt.pct(b.detailEntryRate)}</td>
                    <td>
                      <strong>{b.cartRate === null ? '-' : fmt.pct(b.cartRate)}</strong>
                      <span className="diag-hint">{fmt.int(b.cartSessions)}건</span>
                    </td>
                    <td>
                      {b.purchaseRate === null ? '-' : fmt.pct(b.purchaseRate)}
                      <span className="diag-hint">{fmt.int(b.purchaseSessions)}건</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Panel>

      <Panel
        title={`피부 타입 × 가격대 · ${priceMetric === 'cart' ? '장바구니에 담은' : '구매한'} 비율`}
        source={source.segmentPriceGrid}
        aside={
          <span className="chips chips--inline" title={`20칸 중 ${priceGridFilled}칸에 숫자가 있어요. 방문이 ${MIN_CELL_VISITS}건이 안 되면 비우고 ${THIN_VISITS}건이 안 되면 흐리게 보여요`}>
            {(
              [
                ['cart', '담기'],
                ['purchase', '구매'],
              ] as const
            ).map(([k, label]) => (
              <button key={k} type="button" className={`chip${priceMetric === k ? ' chip--hit' : ''}`} onClick={() => setPriceMetric(k)}>
                {label}
              </button>
            ))}
          </span>
        }
      >
        {segmentPriceGrid.length === 0 ? (
          <p className="note">{source.segmentPriceGrid === 'none' ? '계산 준비 중입니다' : '아직 기록이 없습니다'}</p>
        ) : (
          <Heatmap
            rows={segmentPriceGrid.map((r) => ({ key: r.type, label: SKIN_TYPE_KO[r.type] ?? r.type }))}
            cols={PRICE_BIN_ORDER.map((b) => ({ key: b, label: priceBinKo(b) }))}
            cells={priceCells}
            format={(v) => fmt.pct(v)}
          />
        )}
      </Panel>

      <Panel title="고객군별 가장 오래 본 글" source={source.topContent} fold aside="고객군별로 나눠 봄">
        <table className="table">
          <thead>
            <tr>
              <th>고객군</th>
              <th>가장 오래 본 글</th>
              <th>그다음</th>
              <th title="그 고객군이 글을 읽은 전체 시간 중 가장 오래 본 글에 쓴 몫">시간 비중</th>
            </tr>
          </thead>
          <tbody>
            {segmentTopContent.length === 0 ? (
              <tr>
                <td colSpan={4} className="note">
                  {noSegments ? '아직 기록이 없습니다' : '계산 준비 중입니다'}
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
        <p className="note">고객군마다 다르면 문구를 나눠 쓰세요</p>
      </Panel>
    </div>
  );
}
