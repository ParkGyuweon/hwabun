import { BarList, Funnel, Kpi, LineChart, Panel, VerdictBanner } from '../components';
import {
  dailySeries,
  fmt,
  leakVerdict,
  overview,
  productMetrics,
  standardFunnel,
} from '../lib/metrics';

/**
 * 첫 화면.
 *
 * 배치는 역피라미드다 — 결론 → 추세 → 표.
 * 결론부터 말하고 근거를 아래로 펼친다.
 *
 * 요약 지표를 4개로 줄였다. 뷰티 브랜드 대시보드의 의사결정 지원 상한이
 * 8~12개로 제시되는데, 예전에는 8개를 첫 줄에 늘어놓아서 무엇이 주 지표인지
 * 알 수 없었다. 나머지는 보조로 내렸다.
 */
export default function OverviewScreen({ days }: { days: number }) {
  const series = dailySeries(days);
  const verdict = leakVerdict();

  return (
    <div className="stack">
      <VerdictBanner {...verdict} />

      <div className="grid grid--kpi">
        <Kpi label="상세 조회" value={fmt.int(overview.detailViews)} source="mock" />
        <Kpi
          label="상세 진입률"
          value={fmt.pct(overview.detailRate)}
          sub="노출 대비"
          source="mock"
        />
        <Kpi
          label="장바구니 전환율"
          value={fmt.pct(overview.cartRate)}
          sub="상세 조회 대비"
          source="mock"
        />
        <Kpi
          label="성분 열람률"
          value={fmt.pct(overview.ingredientViewRate)}
          sub="상세 조회 대비 — 우리만 잴 수 있는 값"
          source="mock"
        />
      </div>

      {/* 보조 지표. 주 지표와 같은 크기로 늘어놓으면 무엇이 중요한지 알 수 없다 */}
      <Panel title="보조 지표" source="mock" aside="주 지표를 설명하는 값들">
        <div className="grid grid--kpi">
          <Kpi label="리뷰 열람률" value={fmt.pct(overview.reviewViewRate)} sub="상세 조회 대비" />
          <Kpi
            label="담았다 뺀 비율"
            value={fmt.pct(overview.removalRate)}
            sub="가장 명확한 부정 신호"
          />
          <Kpi label="상세 이탈률" value={fmt.pct(overview.bounceRate)} sub="추가 행동 없이 이탈" />
          <Kpi label="방문" value={fmt.int(overview.sessions)} sub="기간 합계" />
        </div>
      </Panel>

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
        aside="EVENT_WEIGHT 합산 (담기 3.0 · 클릭 1.0 · 제거 −2.0)"
      >
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
          관심도 = 행동별 발생 수 × 가중치. 가중치의 단일 출처는 frontend/src/types/log.ts 이며
          값은 초기 가설이다 (Ablation 검증 전).
        </p>
      </Panel>
    </div>
  );
}
