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
import { buildOverviewHeadlineRequest, headlineOrigin, lineOrigin, useHeadline } from '../lib/headlineApi';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand, feedbackSource } from '../../lib/feedbackStore';
import { categoryLabel, labelsOf } from '../../types/feedback';

/**
 * 개요 (명세 §2-1). 역피라미드: 결론 한 줄 → 근거 배지 → 범용 지표(접힘).
 *
 * 결론은 insight.ts 가 후보를 점수로 골라 하나만 준다. 범용 KPI(방문·조회·이탈)는 신발 가게에도
 * 붙는 숫자라 접어 둔다. 5초 안에 읽어야 하는 것은 맨 위 문장 하나다.
 *
 * 숫자는 useBehavior() 가 준다. 마트가 붙어 있으면 실측, 아니면 모의. 배지가 그 차이를 적는다.
 */
/**
 * 구매 고객 10명 이상인 상품 중 재구매율 최고. 표본이 얇은 상품이 1위에 오르는 것을 막는다.
 *
 * **재구매가 한 건도 없으면 1위도 없다.** 전에는 rate 가 전부 0 이어도 정렬 첫 번째 상품을 "최고"로 적어서,
 * 브랜드 재구매율 0.0% 옆에 상품 이름이 실측 배지를 달고 떴다 (2026-09-18). 0% 끼리는 순위가 없다.
 */
function bestRepurchase(rp: Repurchase, products: ProductMetrics[]): { name: string; rate: number } | null {
  const best = [...rp.products.entries()]
    .filter(([, r]) => r.rate !== null && r.rate > 0 && r.buyerCount >= 10)
    .sort((a, b) => (b[1].rate ?? 0) - (a[1].rate ?? 0))[0];
  if (!best) return null;
  return {
    name: products.find((x) => x.product.product_id === best[0])?.product.product_name ?? best[0],
    rate: best[1].rate ?? 0,
  };
}

/** 100만 원 이상은 "387만원" 처럼 줄여 카드 한 줄에 들어가게. 정확한 값은 카드 아래 줄에 적는다 */
function wonCompact(krw: number): string {
  const n = Math.round(krw);
  if (n >= 1_000_000) return `${Math.round(n / 10_000).toLocaleString('ko-KR')}만원`;
  return `${n.toLocaleString('ko-KR')}원`;
}

export default function OverviewScreen({
  days,
  brandName,
  onGo,
}: {
  days: number;
  /** 로그인한 브랜드 이름. 피드백 시드는 이 이름과 같은 것만 센다 — 못 받았으면 아무것도 안 센다 */
  brandName: string | null;
  onGo?: (screen: string) => void;
}) {
  const m = useBehavior();
  const { overview, previous, daily: series, standardFunnel, productMetrics, repurchase, source } = m;
  const best = repurchase ? bestRepurchase(repurchase, productMetrics) : null;
  const insights = useMemo(() => rankInsights(m), [m]);
  const top = insights[0];
  const rest = insights.slice(1, 4);

  const all = useFeedback();
  const fb = useMemo(() => (brandName ? feedbackForBrand(all, brandName) : []), [all, brandName]);
  const fbTop = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of fb) for (const l of labelsOf(f)) map.set(l.category_id, (map.get(l.category_id) ?? 0) + 1);
    return [...map.entries()].sort((a, b) => b[1] - a[1])[0];
  }, [fb]);

  /** 직전 기간 대비. 마트만 준다 (계약 E1 previous). 없으면 문구 없음 */
  const delta = (cur: number, prev: number | undefined | null) => {
    if (prev === undefined || prev === null) return '';
    const d = (cur - prev) * 100;
    if (Math.abs(d) < 0.05) return ' · 앞 기간과 같음';
    return ` · 앞 기간보다 ${Math.abs(d).toFixed(1)}%p ${d > 0 ? '↑' : '↓'}`;
  };
  /** 행동 기록이 하나도 없을 때 비율 카드 아래에 적는 이유. 0.0% 를 "정말 0" 으로 읽지 않게 한다 */
  const noBehavior = overview.detailViews === 0 && overview.sessions === 0;
  const emptyWhy = '아직 기록이 없습니다';

  /**
   * 백엔드 실측 (GET /api/seller/dashboard). 있으면 맨 아래에 한 줄. 없으면 자리도 없다.
   * `undefined` 는 아직 답을 못 받은 상태다. 한 마디 요청은 이 값이 정해진 뒤에 만든다 — 먼저 마트만으로 부르고
   * 주문이 도착해 다시 부르면 입력이 달라져 LLM 을 두 번 태운다.
   */
  const [pulse, setPulse] = useState<SellerPulse | null | undefined>(() => (loadBrandId() ? undefined : null));
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

  /**
   * 한 마디 (contracts/headline-api-spec.md). 이 화면의 숫자를 그대로 보내 서술문 한 줄과 섹션 줄을 받는다.
   * 마트가 실측일 때만 부르고, 못 받으면 자리도 없다 — 아래 숫자·결론이 그대로 남아 화면이 비지 않는다.
   * 개요에만 붙인다 (2026-09-21 결정, headlineApi.ts 머리말).
   */
  const brand = useMemo(() => ({ name: brandName ?? '', productCount: productMetrics.length }), [brandName, productMetrics.length]);
  const headlineReq = useMemo(() => (pulse === undefined ? null : buildOverviewHeadlineRequest(m, brand, days, pulse)), [m, brand, days, pulse]);
  const headline = useHeadline(headlineReq);
  const sectionLabel = useMemo(() => new Map((headlineReq?.sections ?? []).map((s) => [s.id, s.label_ko])), [headlineReq]);

  return (
    <div className="stack">
      {/*
        규칙 문장(origin rule)은 아래 카드 숫자를 한 줄로 되읊는 것뿐이라 그리지 않는다 (2026-09-21 유림님: 구구절절).
        LLM 이 쓴 문장(llm·mixed)만 보여 준다. 그때도 첫 문장만 펼치고 섹션 줄은 접는다.
      */}
      {headline && (headline.origin === 'llm' || headline.origin === 'mixed') && headline.headline ? (
        <section className="headline" aria-label="지금 상황 한 마디">
          <p className="headline__eyebrow">
            지금 무슨 일이 · 최근 {days}일
            {headlineOrigin(headline) === 'rule' ? <span className="headline__tag" title="이번에는 문장으로 풀지 못해 숫자만 그대로 적었습니다">숫자 그대로</span> : null}
          </p>
          <p className="headline__line">{headline.headline}</p>
          {/* 섹션 줄은 접어 둔다. 첫눈에 읽는 건 한 문장이고, 나머지는 원할 때만 (2026-09-21 유림님: 글이 너무 많다) */}
          {headline.sections.length > 0 ? (
            <details className="headline__more">
              <summary>자세히</summary>
              <ul className="headline__sections">
                {headline.sections.map((s) => (
                  <li key={s.id}>
                    <span className="headline__label">{sectionLabel.get(s.id) ?? s.id}</span>
                    <span>{s.line}</span>
                    {lineOrigin(headline, s) === 'rule' ? <span className="headline__tag" title="이 줄은 숫자만 그대로 적었습니다">숫자 그대로</span> : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}
      {pulse ? (
        <div className="grid grid--kpi">
          <Kpi label="주문" value={`${fmt.int(pulse.orders)}건`} sub={pulse.orders > 0 ? '결제 완료 · 전체 기간' : '아직 주문이 없습니다'} source="real" />
          {/* 원 단위 그대로 적으면 카드에서 줄이 넘어간다. 100만 원 넘으면 만 원 단위로 줄이고 정확한 값은 아래 한 줄에 */}
          <Kpi label="매출" value={wonCompact(pulse.revenue)} sub={pulse.revenue >= 1_000_000 ? `${Math.round(pulse.revenue).toLocaleString('ko-KR')}원` : pulse.revenue > 0 ? '결제 완료 · 전체 기간' : '아직 매출이 없습니다'} source="real" />
          {/*
            주문 수만 보면 "5건" 이 5개인지 50개인지 알 수 없다. 팔린 개수와 가짓수를 따로 적는다 —
            한 상품이 5번 팔린 것과 다섯 상품이 하나씩 팔린 것은 다음에 할 일이 다르다.
          */}
          <Kpi
            label="판매 수량"
            value={`${fmt.int(pulse.units)}개`}
            sub={pulse.orders > 0 ? `한 주문에 평균 ${(pulse.units / pulse.orders).toFixed(1)}개` : '아직 팔린 수량이 없습니다'}
            source="real"
          />
          {/*
            팔린 상품 가짓수·리뷰·받은 의견 칸은 뺐다 (2026-09-22 유림님). 요약에서 볼 만큼 중요한 숫자가 아니고
            가짓수는 상품 화면, 리뷰·의견은 고객의 말 화면에 그대로 있다.
          */}
        </div>
      ) : null}
      {/*
        재구매 배지 · 단위 = 브랜드 (ai-insight-rules §2-1, 2026-09-10 확정). 상품이 달라도 같은 브랜드를 다시 사면 재구매다.
        마트(brand_repurchase_daily)가 있을 때만 그린다. 모의값을 두지 않는다 — 재구매를 흉내 내면 사장님이 진짜로 읽는다.
      */}
      {repurchase?.brand ? (
        <div className="grid grid--kpi">
          <Kpi
            label="다시 산 고객 비율"
            value={repurchase.brand.rate === null ? '아직 없음' : fmt.pct(repurchase.brand.rate)}
            sub={
              repurchase.brand.rate === null
                ? `최근 ${repurchase.brand.windowDays}일 동안 산 고객이 없습니다`
                : `산 고객 ${fmt.int(repurchase.brand.buyerCount)}명 중 ${fmt.int(repurchase.brand.repeatBuyerCount)}명이 또 샀습니다 · 최근 ${repurchase.brand.windowDays}일`
            }
            source="real"
          />
          {/*
            간격 중앙값은 서버가 행이 하나일 때만 준다 (DashboardMartService.brandRepurchase — 중앙값은 합산할 수 없다).
            다시 산 고객은 있는데 간격이 null 이면 "고객이 없다" 가 아니라 "계산이 안 됐다" 다. 둘을 다르게 적는다 (2026-09-21).
          */}
          <Kpi
            label="다시 사기까지 걸린 날"
            value={repurchase.brand.medianDays === null ? (repurchase.brand.repeatBuyerCount > 0 ? '계산 전' : '아직 없음') : `${Math.round(repurchase.brand.medianDays)}일`}
            sub={
              repurchase.brand.medianDays !== null
                ? '처음 산 날부터 다시 산 날까지 · 고객마다 달라서 한가운데 값'
                : repurchase.brand.repeatBuyerCount > 0
                  ? '다시 산 고객은 있지만 날수 계산은 준비 중'
                  : '두 번 산 고객이 생기면 채워집니다'
            }
            source="real"
          />
          {/*
            결제할 때 "왜 샀나요" 물음에 "쓰던 걸 다시 사서" 를 고른 주문 수 (checkout.ts `restock`).
            고객이 스스로 한 말이라 위 칸(실제 주문 기록으로 센 재구매)과 다를 수 있고, 그래서 나란히 둔다.
          */}
          <Kpi
            label="'쓰던 걸 다시 사요'라고 답한 주문"
            value={`${fmt.int(repurchase.brand.declaredRestockOrders)}건`}
            sub={`결제할 때 고객이 직접 고른 답 · 주문 기록으로 센 다시 산 고객은 ${fmt.int(repurchase.brand.repeatBuyerCount)}명`}
            source="real"
          />
          <Kpi
            label="가장 많이 다시 사는 상품"
            value={best ? best.name : '아직 없음'}
            sub={best ? `산 고객 중 ${fmt.pct(best.rate)}가 또 샀습니다` : '다시 산 고객이 아직 없습니다'}
            source="real"
          />
        </div>
      ) : null}
      {top ? (
        <section className={`verdict verdict--${top.origin}`}>
          <p className="verdict__eyebrow">
            첫 번째 할 일 <OriginBadge kind={top.origin} />
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
            기록 {fmt.int(top.n)}건을 보고 낸 판단 · 믿을 만한 정도 {top.confidence}
            {onGo ? (
              <button type="button" className="verdict__go" onClick={() => onGo(top.screen)}>
                근거 화면으로
              </button>
            ) : null}
          </p>
        </section>
      ) : (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            첫 번째 할 일 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">아직 판단을 내릴 만큼 기록이 모이지 않았습니다</h2>
          <ul className="verdict__reasons">
            <li>
              {noBehavior
                ? '이 기간에는 내 상품을 본 고객 기록이 없습니다. 고객이 상품 상세를 보기 시작하면 결론이 생깁니다.'
                : '상세페이지 설명 글 하나를 200명 넘게 읽거나, 한 고객군의 방문이 200건을 넘으면 그때부터 결론을 냅니다.'}
            </li>
          </ul>
          <p className="verdict__action">지금은 아래 주문·매출 숫자와 방문 추이만 참고해 주세요.</p>
        </section>
      )}

      <div className="grid grid--kpi">
        <Kpi
          label="상세를 보고 담은 비율"
          value={fmt.pct(overview.cartRate)}
          sub={noBehavior ? emptyWhy : `상세 ${fmt.int(overview.detailViews)}번 중${delta(overview.cartRate, previous?.cartRate)}`}
          source={source.overview}
        />
        <Kpi
          label="성분·리뷰까지 읽은 비율"
          value={fmt.pct(overview.infoRate)}
          sub={noBehavior ? emptyWhy : `상세를 본 고객 기준${delta(overview.infoRate, previous?.infoRate)}`}
          source={source.overview}
        />
        <Kpi
          label="담았다가 뺀 비율"
          value={fmt.pct(overview.removalRate)}
          sub={noBehavior ? emptyWhy : `담은 뒤 마음을 바꾼 고객${delta(overview.removalRate, previous?.removalRate)}`}
          source={source.overview}
        />
        <Kpi
          label="고객 의견에서 가장 많이 나온 말"
          value={fbTop ? categoryLabel(fbTop[0]) : '아직 없음'}
          sub={fbTop ? `${fbTop[1]}번 · 의견 ${fb.length}건` : '아직 의견이 없습니다'}
          source={feedbackSource(fb)}
        />
      </div>

      {rest.length > 0 ? (
        <Panel title="그다음 할 일" source={source.content} aside="차이가 크고 기록이 많은 순서">
          <ul className="insight-list">
            {rest.map((i) => (
              <li key={i.id}>
                <button type="button" className={`insight-list__item insight-list__item--${i.origin}`} onClick={() => onGo?.(i.screen)}>
                  <span className="insight-list__head">{i.headline}</span>
                  <span className="insight-list__meta">
                    <OriginBadge kind={i.origin} /> {i.unit} · 기록 {fmt.int(i.n)}건 · 믿을 만한 정도 {i.confidence}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <div className="grid grid--2">
        <Panel title={`날짜별 방문 수 · 최근 ${days}일`} source={source.overview} aside="눈금은 0부터">
          <LineChart points={series.map((d) => ({ label: d.label, value: d.visits }))} />
        </Panel>
        <Panel title="구매까지 가는 단계" source={source.funnel} aside="단계마다 남은 방문">
          <Funnel steps={standardFunnel} />
          {/*
            성분·리뷰 확인은 단계가 아니라 곁가지다 — 퀵룩으로 담은 방문은 볼 기회가 없었다. 퍼널에 끼우면
            "성분·리뷰 → 담기" 가 154% 로 나온다. 분모를 상품 상세 방문으로 맞춰 옆에 적는다 (2026-09-22).
          */}
          {overview.sessions > 0 ? (
            <p className="funnel__aside" title="퀵룩에는 성분·리뷰가 없어 상품 상세를 연 방문만 분모로 씁니다">
              <span>성분·리뷰까지 확인</span>
              <b>{fmt.pct(overview.sessions === 0 ? 0 : overview.infoViews / overview.sessions)}</b>
              <em>
                상품 상세 {fmt.int(overview.sessions)}건 중 {fmt.int(overview.infoViews)}건
              </em>
            </p>
          ) : null}
        </Panel>
      </div>

      {/* 접지 않고 바로 보인다 (2026-09-22 은솔님). 접힌 제목이 안의 카드 숫자를 그대로 되읊어 펼칠 이유가 없었다 */}
      <section className="stack" aria-label="기본 숫자">
        <div className="grid grid--kpi">
          <Kpi label="방문" value={`${fmt.int(overview.sessions)}번`} sub={noBehavior ? emptyWhy : `최근 ${days}일`} />
          <Kpi label="상품 상세 본 횟수" value={`${fmt.int(overview.detailViews)}번`} sub={noBehavior ? emptyWhy : `최근 ${days}일`} />
          <Kpi label="목록에서 상세로 들어온 비율" value={fmt.pct(overview.detailRate)} sub={noBehavior ? emptyWhy : '목록에 보인 횟수 기준'} />
          <Kpi
            label="상세만 보고 그냥 나간 비율"
            value={overview.bounceRate === null ? '아직 없음' : fmt.pct(overview.bounceRate)}
            sub={overview.bounceRate === null ? '준비 중' : '아무 행동 없이 나감'}
          />
        </div>
        <Panel title="고객이 가장 관심 보인 상품 5개" source={source.products} fold aside="담기·누르기는 더하고 담았다 뺀 것은 빼서 매긴 점수">
          <BarList
            items={productMetrics.slice(0, 5).map((p) => ({
              label: p.product.product_name,
              sub: p.product.brand_name,
              value: p.interestScore,
              hint: `담기 ${p.addToCart}번`,
            }))}
            rank
          />
          <p className="note">
            관심 점수는 장바구니 담기 1번을 3점, 상품 누르기 1번을 1점으로 더하고, 담았다가 뺀 1번은 2점을 뺀 값입니다. 점수 자체보다 순서를 보시면 됩니다.
          </p>
        </Panel>
      </section>
    </div>
  );
}
