import { useMemo } from 'react';
import { BarList, Funnel, Kpi, LineChart, Panel } from '../components';
import { dailySeries, fmt, overview, productMetrics, standardFunnel } from '../lib/metrics';
import { rankInsights } from '../lib/insight';
import { FEEDBACK_BRAND } from '../lib/scope';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand } from '../../lib/feedbackStore';
import { categoryLabel, labelsOf } from '../../types/feedback';

/**
 * 개요 (명세 §2-1). 역피라미드: 결론 한 줄 → 근거 배지 → 범용 지표(접힘).
 *
 * 결론은 insight.ts 가 후보를 점수로 골라 하나만 준다. 범용 KPI(방문·조회·이탈)는 신발 가게에도
 * 붙는 숫자라 접어 둔다. 5초 안에 읽어야 하는 것은 맨 위 문장 하나다.
 */
export default function OverviewScreen({ days, onGo }: { days: number; onGo?: (screen: string) => void }) {
  const series = dailySeries(days);
  const insights = useMemo(() => rankInsights(), []);
  const top = insights[0];
  const rest = insights.slice(1, 4);

  const all = useFeedback();
  const fb = useMemo(() => feedbackForBrand(all, FEEDBACK_BRAND), [all]);
  const fbTop = useMemo(() => {
    const m = new Map<string, number>();
    for (const f of fb) for (const l of labelsOf(f)) m.set(l.category_id, (m.get(l.category_id) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1])[0];
  }, [fb]);

  const infoRate = (overview.ingredientViewRate + overview.reviewViewRate) / 2;

  return (
    <div className="stack">
      {top ? (
        <section className="verdict">
          <p className="verdict__eyebrow">지금 손봐야 할 것</p>
          <h2 className="verdict__headline">{top.headline}</h2>
          <ul className="verdict__reasons">
            {top.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="verdict__action">
            <span className="verdict__unit">{top.unit}</span>
            {top.action}
          </p>
          <p className="verdict__sample">
            표본 {fmt.int(top.n)} · 신뢰도 {top.confidence}
            {onGo ? (
              <button type="button" className="verdict__go" onClick={() => onGo(top.screen)}>
                근거 화면으로
              </button>
            ) : null}
          </p>
        </section>
      ) : null}

      <div className="grid grid--kpi">
        <Kpi label="상세 → 담기 전환율" value={fmt.pct(overview.cartRate)} sub={`상세 조회 ${fmt.int(overview.detailViews)} 기준`} source="mock" />
        <Kpi label="정보 확인 도달률" value={fmt.pct(infoRate)} sub="상세에서 성분·리뷰를 확인한 비율. 우리만 재는 값" source="mock" />
        <Kpi label="담았다 뺀 비율" value={fmt.pct(overview.removalRate)} sub="가장 명확한 부정 신호" source="mock" />
        <Kpi
          label="피드백 최다 언급"
          value={fbTop ? categoryLabel(fbTop[0]) : '없음'}
          sub={fbTop ? `언급 ${fbTop[1]} · ${FEEDBACK_BRAND} ${fb.length}건` : ''}
          source="real"
        />
      </div>

      {rest.length > 0 ? (
        <Panel title="다음 후보" source="mock" aside="점수 = 편차 × ln(표본)">
          <ul className="insight-list">
            {rest.map((i) => (
              <li key={i.id}>
                <button type="button" className="insight-list__item" onClick={() => onGo?.(i.screen)}>
                  <span className="insight-list__head">{i.headline}</span>
                  <span className="insight-list__meta">
                    {i.unit} · 표본 {fmt.int(i.n)} · {i.confidence}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <div className="grid grid--2">
        <Panel title={`방문 추이 · 최근 ${days}일`} source="mock" aside="축은 0부터">
          <LineChart points={series.map((d) => ({ label: d.label, value: d.visits }))} />
        </Panel>
        <Panel title="퍼널" source="mock" aside="구매 이벤트 생성 전이라 장바구니까지">
          <Funnel steps={standardFunnel} />
        </Panel>
      </div>

      <details className="fold">
        <summary>범용 지표 · 방문 {fmt.int(overview.sessions)} · 상세 조회 {fmt.int(overview.detailViews)} · 이탈률 {fmt.pct(overview.bounceRate)}</summary>
        <div className="grid grid--kpi fold__body">
          <Kpi label="방문" value={fmt.int(overview.sessions)} sub="기간 합계" />
          <Kpi label="상세 조회" value={fmt.int(overview.detailViews)} />
          <Kpi label="상세 진입률" value={fmt.pct(overview.detailRate)} sub="노출 대비" />
          <Kpi label="상세 이탈률" value={fmt.pct(overview.bounceRate)} sub="추가 행동 없이 이탈" />
        </div>
        <Panel title="관심도 TOP 5" source="mock" aside="행동 가중 합산 (담기 3.0 · 클릭 1.0 · 제거 −2.0)">
          <BarList
            items={productMetrics.slice(0, 5).map((m) => ({
              label: m.product.product_name,
              sub: m.product.brand_name,
              value: m.interestScore,
              hint: `담기 ${m.addToCart}`,
            }))}
            rank
          />
          <p className="note">
            관심도 = 행동별 발생 수 × 가중치. 가중치의 단일 출처는 frontend/src/types/log.ts 이며 값은 초기 가설입니다.
          </p>
        </Panel>
      </details>
    </div>
  );
}
