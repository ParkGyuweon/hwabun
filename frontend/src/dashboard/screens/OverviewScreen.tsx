import { useEffect, useMemo, useState } from 'react';
import { fetchSellerPulse } from '../../lib/shopApi';
import { loadBrandId } from '../../lib/brands';
import type { SellerPulse } from '../../lib/shopApi';
import { BarList, Funnel, Kpi, LineChart, OriginBadge, Panel } from '../components';
import { fmt } from '../lib/metrics';
import type { ProductMetrics } from '../lib/metrics';
import type { Repurchase } from '../lib/behavior';
import { rankInsights } from '../lib/insight';
import { useBehavior } from '../lib/useBehavior';
import { FEEDBACK_BRAND } from '../lib/scope';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand } from '../../lib/feedbackStore';
import { categoryLabel, labelsOf } from '../../types/feedback';

/**
 * 개요 (명세 §2-1). 역피라미드: 결론 한 줄 → 근거 배지 → 범용 지표(접힘).
 *
 * 결론은 insight.ts 가 후보를 점수로 골라 하나만 준다. 범용 KPI(방문·조회·이탈)는 신발 가게에도
 * 붙는 숫자라 접어 둔다. 5초 안에 읽어야 하는 것은 맨 위 문장 하나다.
 *
 * 숫자는 useBehavior() 가 준다. 마트가 붙어 있으면 실측, 아니면 모의. 배지가 그 차이를 적는다.
 */
/** 구매 고객 10명 이상인 상품 중 재구매율 최고. 표본이 얇은 상품이 1위에 오르는 것을 막는다 */
function bestRepurchaseName(rp: Repurchase, products: ProductMetrics[]): string {
  const best = [...rp.products.entries()]
    .filter(([, r]) => r.rate !== null && r.buyerCount >= 10)
    .sort((a, b) => (b[1].rate ?? 0) - (a[1].rate ?? 0))[0];
  if (!best) return '-';
  return products.find((x) => x.product.product_id === best[0])?.product.product_name ?? best[0];
}

export default function OverviewScreen({ days, onGo }: { days: number; onGo?: (screen: string) => void }) {
  const m = useBehavior();
  const { overview, previous, daily: series, standardFunnel, productMetrics, repurchase, source } = m;
  const insights = useMemo(() => rankInsights(m), [m]);
  const top = insights[0];
  const rest = insights.slice(1, 4);

  const all = useFeedback();
  const fb = useMemo(() => feedbackForBrand(all, FEEDBACK_BRAND), [all]);
  const fbTop = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of fb) for (const l of labelsOf(f)) map.set(l.category_id, (map.get(l.category_id) ?? 0) + 1);
    return [...map.entries()].sort((a, b) => b[1] - a[1])[0];
  }, [fb]);

  /** 직전 기간 대비. 마트만 준다 (계약 E1 previous). 없으면 문구 없음 */
  const delta = (cur: number, prev: number | undefined | null) => {
    if (prev === undefined || prev === null) return '';
    const d = (cur - prev) * 100;
    if (Math.abs(d) < 0.05) return ' · 직전 기간과 같음';
    return ` · 직전 기간 대비 ${d > 0 ? '+' : ''}${d.toFixed(1)}%p`;
  };

  /** 백엔드 실측 (GET /api/seller/dashboard). 있으면 맨 아래에 한 줄. 없으면 자리도 없다 */
  const [pulse, setPulse] = useState<SellerPulse | null>(null);
  useEffect(() => {
    const brandId = loadBrandId();
    if (!brandId) return;
    let alive = true;
    void fetchSellerPulse(brandId).then((p) => {
      if (alive) setPulse(p);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="stack">
      {pulse ? (
        <div className="grid grid--kpi">
          <Kpi label="백엔드 주문" value={fmt.int(pulse.orders)} sub="결제 완료 기준 · shop_backend 실측" source="real" />
          <Kpi label="백엔드 매출" value={`${Math.round(pulse.revenue).toLocaleString('ko-KR')}원`} sub="결제 완료 합계" source="real" />
          <Kpi label="백엔드 리뷰" value={fmt.int(pulse.reviews)} sub="구매 고객이 남긴 리뷰" source="real" />
          <Kpi label="백엔드 피드백" value={fmt.int(pulse.feedbacks)} sub="구매 고객이 남긴 의견" source="real" />
        </div>
      ) : null}
      {/*
        재구매 배지 · 단위 = 브랜드 (ai-insight-rules §2-1, 2026-09-10 확정). 상품이 달라도 같은 브랜드를 다시 사면 재구매다.
        마트(brand_repurchase_daily)가 있을 때만 그린다. 모의값을 두지 않는다 — 재구매를 흉내 내면 사장님이 진짜로 읽는다.
      */}
      {repurchase?.brand ? (
        <div className="grid grid--kpi">
          <Kpi
            label="브랜드 재구매율"
            value={repurchase.brand.rate === null ? '-' : fmt.pct(repurchase.brand.rate)}
            sub={`구매 고객 ${fmt.int(repurchase.brand.buyerCount)}명 중 ${fmt.int(repurchase.brand.repeatBuyerCount)}명이 다시 샀습니다 · 최근 ${repurchase.brand.windowDays}일`}
            source="real"
          />
          <Kpi
            label="재구매 간격"
            value={repurchase.brand.medianDays === null ? '-' : `${Math.round(repurchase.brand.medianDays)}일`}
            sub="다시 산 고객의 구매 사이 간격 중앙값"
            source="real"
          />
          <Kpi
            label="다시 사려고 산 주문"
            value={fmt.int(repurchase.brand.declaredRestockOrders)}
            sub={`설문에서 "다시 사려고" 를 고른 주문 · 관측 재구매 ${fmt.int(repurchase.brand.repeatBuyerCount)}명과 갈리는 만큼이 행동 추론의 한계`}
            source="real"
          />
          <Kpi
            label="상품 재구매 최고"
            value={bestRepurchaseName(repurchase, productMetrics)}
            sub="구매 고객 10명 이상인 상품 중"
            source="real"
          />
        </div>
      ) : null}
      {top ? (
        <section className={`verdict verdict--${top.origin}`}>
          <p className="verdict__eyebrow">
            지금 손봐야 할 것 <OriginBadge kind={top.origin} />
          </p>
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
        <Kpi
          label="상세 → 담기 전환율"
          value={fmt.pct(overview.cartRate)}
          sub={`상세 조회 ${fmt.int(overview.detailViews)} 기준${delta(overview.cartRate, previous?.cartRate)}`}
          source={source.overview}
        />
        <Kpi
          label="정보 확인 도달률"
          value={fmt.pct(overview.infoRate)}
          sub={`상세에서 성분·리뷰를 확인한 비율. 우리만 재는 값${delta(overview.infoRate, previous?.infoRate)}`}
          source={source.overview}
        />
        <Kpi
          label="담았다 뺀 비율"
          value={fmt.pct(overview.removalRate)}
          sub={`가장 명확한 부정 신호${delta(overview.removalRate, previous?.removalRate)}`}
          source={source.overview}
        />
        <Kpi
          label="피드백 최다 언급"
          value={fbTop ? categoryLabel(fbTop[0]) : '없음'}
          sub={fbTop ? `언급 ${fbTop[1]} · ${FEEDBACK_BRAND} ${fb.length}건` : ''}
          source="real"
        />
      </div>

      {rest.length > 0 ? (
        <Panel title="다음 후보" source={source.content} aside="점수 = 편차 × ln(표본)">
          <ul className="insight-list">
            {rest.map((i) => (
              <li key={i.id}>
                <button type="button" className={`insight-list__item insight-list__item--${i.origin}`} onClick={() => onGo?.(i.screen)}>
                  <span className="insight-list__head">{i.headline}</span>
                  <span className="insight-list__meta">
                    <OriginBadge kind={i.origin} /> {i.unit} · 표본 {fmt.int(i.n)} · {i.confidence}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <div className="grid grid--2">
        <Panel title={`방문 추이 · 최근 ${days}일`} source={source.overview} aside="축은 0부터">
          <LineChart points={series.map((d) => ({ label: d.label, value: d.visits }))} />
        </Panel>
        <Panel
          title="퍼널"
          source={source.funnel}
          aside={source.funnel === 'real' ? '상품 합산 세션 · 구매 이벤트 생성 전이라 장바구니까지' : '구매 이벤트 생성 전이라 장바구니까지'}
        >
          <Funnel steps={standardFunnel} />
        </Panel>
      </div>

      <details className="fold">
        <summary>
          범용 지표 · 방문 {fmt.int(overview.sessions)} · 상세 조회 {fmt.int(overview.detailViews)} · 이탈률{' '}
          {overview.bounceRate === null ? '-' : fmt.pct(overview.bounceRate)}
        </summary>
        <div className="grid grid--kpi fold__body">
          <Kpi label="방문" value={fmt.int(overview.sessions)} sub="기간 합계" />
          <Kpi label="상세 조회" value={fmt.int(overview.detailViews)} />
          <Kpi label="상세 진입률" value={fmt.pct(overview.detailRate)} sub="노출 대비" />
          <Kpi
            label="상세 이탈률"
            value={overview.bounceRate === null ? '-' : fmt.pct(overview.bounceRate)}
            sub={overview.bounceRate === null ? '마트에 이탈률이 없습니다. 3초 이탈이 오면 여기에 씁니다' : '추가 행동 없이 이탈'}
          />
        </div>
        <Panel title="관심도 TOP 5" source={source.products} fold aside="행동 가중 합산 (담기 3.0 · 클릭 1.0 · 제거 −2.0)">
          <BarList
            items={productMetrics.slice(0, 5).map((p) => ({
              label: p.product.product_name,
              sub: p.product.brand_name,
              value: p.interestScore,
              hint: `담기 ${p.addToCart}`,
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
