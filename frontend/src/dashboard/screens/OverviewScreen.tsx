import { BarList, Funnel, Kpi, LineChart, Panel } from '../components';
import { dailySeries, fmt, overview, productMetrics, standardFunnel } from '../lib/metrics';

/** 처음 들어왔을 때 전체 성과를 한눈에. 판단은 숫자가 아니라 보는 사람이 한다 */
export default function OverviewScreen({ days }: { days: number }) {
  const series = dailySeries(days);

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi label="방문" value={fmt.int(overview.sessions)} source="mock" />
        <Kpi label="상세 조회" value={fmt.int(overview.detailViews)} source="mock" />
        <Kpi
          label="상세 진입률"
          value={fmt.pct(overview.detailRate)}
          sub="노출 대비"
          source="mock"
        />
        <Kpi
          label="성분 열람률"
          value={fmt.pct(overview.ingredientViewRate)}
          sub="상세 조회 대비"
          source="mock"
        />
        <Kpi
          label="리뷰 열람률"
          value={fmt.pct(overview.reviewViewRate)}
          sub="상세 조회 대비"
          source="mock"
        />
        <Kpi
          label="장바구니 전환율"
          value={fmt.pct(overview.cartRate)}
          sub="상세 조회 대비"
          source="mock"
        />
        <Kpi
          label="장바구니 재고율"
          value={fmt.pct(overview.removalRate)}
          sub="담기 대비 제거 — remove_from_cart"
          source="mock"
        />
        <Kpi
          label="상세 이탈률"
          value={fmt.pct(overview.bounceRate)}
          sub="추가 행동 없이 이탈"
          source="mock"
        />
      </div>

      <div className="grid grid--2">
        <Panel title={`기간별 추이 · 최근 ${days}일`} source="mock" aside="방문 기준">
          <LineChart points={series.map((d) => ({ label: d.label, value: d.visits }))} />
        </Panel>

        <Panel title="전환 퍼널 요약" source="mock" aside="구매는 범위 밖 — 장바구니까지">
          <Funnel steps={standardFunnel} />
        </Panel>
      </div>

      <Panel
        title="인기 상품 TOP 5 · 행동 가중 관심도"
        source="mock"
        aside="EVENT_WEIGHT 합산 (담기 4.0 · 클릭 1.0 · 제거 −2.0)"
      >
        <BarList
          items={productMetrics.slice(0, 5).map((m) => ({
            label: `${m.product.brand_name} — ${m.product.product_name}`,
            value: m.interestScore,
            hint: `담기 ${m.addToCart}`,
          }))}
        />
        <p className="note">
          관심도 = 행동별 발생 수 × 가중치. 가중치의 단일 출처는 frontend/src/types/log.ts 이며
          값은 초기 가설이다 (Ablation 검증 전).
        </p>
      </Panel>
    </div>
  );
}
