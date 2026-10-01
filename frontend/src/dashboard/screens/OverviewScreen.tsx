import { useEffect, useMemo, useRef, useState } from 'react';
import { SELLER_ORDER_LIMIT, fetchSellerFeedback, fetchSellerOrders, fetchSellerPulse } from '../../lib/shopApi';
import { loadBrandId } from '../../lib/brands';
import type { SellerOrder, SellerPulse } from '../../lib/shopApi';
import { rangeOf } from '../lib/martApi';
import { BarList, Funnel, Kpi, LineChart, OriginBadge, Panel } from '../components';
import { fmt, periodLabel } from '../lib/metrics';
import type { ProductMetrics } from '../lib/metrics';
import type { Repurchase } from '../lib/behavior';
import { rankInsights } from '../lib/insight';
import { BehaviorGate, useBehavior, useMartWaiting } from '../lib/useBehavior';
import { buildOverviewHeadlineRequest, headlineOrigin, lineOrigin, useHeadlineState } from '../lib/headlineApi';
import { useFeedback } from '../../hooks/useFeedback';
import { dropSamplesIfReal, feedbackForBrand, feedbackSource } from '../../lib/feedbackStore';
import { categoryLabel, labelsOf } from '../../types/feedback';
import type { Feedback } from '../../types/feedback';
import { PURCHASE_REASONS } from '../../lib/checkout';
import { onOrdersChanged } from '../../lib/notifySignal';

/**
 * AI 한 마디를 못 받았을 때의 기본 문장 — 숫자와 무관하게 늘 맞는 말만 쓴다 (2026-10-01 유림님).
 * 숫자를 넣으면 카드와 어긋날 수 있고, "방문의 방문은…" 같은 되읊기가 된다.
 */
const HEADLINE_FALLBACK = {
  line: '방문부터 담기·주문까지, 고객이 어디서 머물고 어디서 떠나는지 아래에 정리했습니다.',
  hint: '"첫 번째 할 일" 부터 보시면 지금 가장 먼저 손볼 곳을 알 수 있습니다.',
};

/** 화면이 보이는 동안 주문·매출을 다시 받는 간격. 다른 기기에서 들어온 주문용 — 같은 브라우저의 결제는 신호로 바로 온다 */
const ORDERS_REFRESH_MS = 10_000;

const REASON_KO = new Map(PURCHASE_REASONS.map((r) => [r.key, r.label]));

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
  const { overview, previous, daily: series, standardFunnel, funnelNote, productMetrics, repurchase, source } = m;
  const best = repurchase ? bestRepurchase(repurchase, productMetrics) : null;
  const insights = useMemo(() => rankInsights(m), [m]);
  const top = insights[0];
  const rest = insights.slice(1, 4);
  const [trend, setTrend] = useState<'visits' | 'carts'>('visits');
  // 결제할 때 고른 "왜 샀나요" 답. 답을 안 고른 주문(reason null)은 비율에서 빠진다 (서버 reason_share 와 같은 규칙)
  const reasons = (repurchase?.reasons ?? [])
    .filter((r): r is typeof r & { reason: string } => r.reason !== null && r.orderCount > 0)
    .sort((a, b) => b.orderCount - a.orderCount);
  const reasonOrders = reasons.reduce((s, r) => s + r.orderCount, 0);
  const cartSessions = standardFunnel.find((s) => s.label === '장바구니에 담음')?.value ?? 0;

  /*
   * 서버 피드백(GET /api/seller/feedback) + 이 브라우저에서 쓴 글. 고객의 말 화면과 같은 규칙이다.
   * 전에는 브라우저 저장본만 읽어서, 서버에 의견이 쌓여 있어도 이 카드는 "아직 없음" 이었다 (2026-09-23 명세 대조).
   */
  const all = useFeedback();
  const [remote, setRemote] = useState<{ brand: string; rows: Feedback[] } | null>(null);
  useEffect(() => {
    const brandId = loadBrandId();
    if (!brandId || !brandName) return;
    let alive = true;
    void fetchSellerFeedback(brandId, brandName).then((rows) => {
      if (alive && rows) setRemote({ brand: brandName, rows });
    });
    return () => {
      alive = false;
    };
  }, [brandName]);
  const fb = useMemo(() => {
    const local = brandName ? feedbackForBrand(all, brandName) : [];
    const server = remote && remote.brand === brandName ? remote.rows : [];
    const seen = new Set(local.map((f) => f.feedback_id));
    // 진짜 의견이 있으면 번들 샘플은 "가장 많이 나온 말" 에서 뺀다
    return dropSamplesIfReal([...server.filter((f) => !seen.has(f.feedback_id)), ...local]);
  }, [all, remote, brandName]);
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
    return ` · 앞 기간보다 ${Math.abs(d).toFixed(1)}포인트 ${d > 0 ? '올라감' : '내려감'}`;
  };
  /** 행동 기록이 하나도 없을 때 비율 카드 아래에 적는 이유. 0.0% 를 "정말 0" 으로 읽지 않게 한다 */
  const noBehavior = overview.detailViews === 0 && overview.sessions === 0;
  const emptyWhy = '아직 기록이 없습니다';

  /**
   * 백엔드 실측 (GET /api/seller/dashboard). 있으면 맨 아래에 한 줄. 없으면 자리도 없다.
   * `undefined` 는 아직 답을 못 받은 상태다. 한 마디 요청은 이 값이 정해진 뒤에 만든다 — 먼저 마트만으로 부르고
   * 주문이 도착해 다시 부르면 입력이 달라져 LLM 을 두 번 태운다.
   */
  /*
   * 주문은 실시간이어야 한다 (2026-10-01 유림님). 전에는 화면을 열 때 한 번만 받아, 열어 둔 채 들어온 주문은 새로고침 전까지
   * 안 보였다. 이 숫자가 바뀔 때마다 주문·매출을 다시 받는다 — 같은 브라우저의 결제 신호(lib/notifySignal) · 창 복귀 ·
   * 보이는 동안 ORDERS_REFRESH_MS 마다. 숨은 탭은 묻지 않는다.
   */
  const [ordersTick, setOrdersTick] = useState(0);
  useEffect(() => {
    const bump = () => setOrdersTick((n) => n + 1);
    let timer: number | null = null;
    const start = () => {
      if (timer === null && document.visibilityState === 'visible') timer = window.setInterval(bump, ORDERS_REFRESH_MS);
    };
    const stop = () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        bump();
        start();
      } else stop();
    };
    start();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', bump);
    const off = onOrdersChanged(bump);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', bump);
      off();
    };
  }, []);

  const [pulse, setPulse] = useState<SellerPulse | null | undefined>(() => (loadBrandId() ? undefined : null));
  useEffect(() => {
    const brandId = loadBrandId();
    if (!brandId) return;
    let alive = true;
    void fetchSellerPulse(brandId).then((p) => {
      // 다시 받다가 한 번 실패하면 전에 받은 값을 지우지 않는다 — 숫자가 사라졌다 돌아오면 결함처럼 보인다
      if (alive) setPulse((cur) => (p === null && cur ? cur : p));
    });
    return () => {
      alive = false;
    };
    // 브랜드를 바꾸면(brandName) 다시 받는다. 전에는 처음 한 번만 받아 다른 브랜드의 주문 수가 남아 있었다
  }, [brandName, ordersTick]);

  /**
   * **고른 기간**의 주문·매출·판매 수량 (2026-10-01). 위 `pulse` 는 `GET /api/seller/dashboard` 가 기간을 받지 않아 전체 합이다 —
   * 그래서 7일·14일을 바꿔도 주문 수가 그대로였다 (유림님 제보). 쇼핑몰 원장 `GET /api/seller/orders?from&to` 가 결제 시각으로
   * 거르므로 그걸로 센다. 기간은 행동 지표와 같은 `rangeOf(days)` (오늘까지 N일). 전체 합은 아래 줄에 참고로 남긴다.
   * `undefined` 는 받는 중, `null` 은 못 받음 — 그때는 전체 합을 그대로 보여 주고 그렇게 적는다.
   */
  const brandIdNow = loadBrandId();
  const salesKey = brandIdNow ? `${brandIdNow}:${days}` : null;
  const [periodSales, setPeriodSales] = useState<{ key: string; days: number; value: PeriodSales | null } | null>(null);
  useEffect(() => {
    if (!salesKey || !brandIdNow) return;
    let alive = true;
    void fetchSellerOrders(brandIdNow, rangeOf(days)).then((rows) => {
      if (!alive) return;
      // 같은 기간을 다시 받다가 실패하면 전에 받은 값을 둔다
      setPeriodSales((cur) => (rows === null && cur?.key === salesKey && cur.value ? cur : { key: salesKey, days, value: rows ? summarizeOrders(rows) : null }));
    });
    return () => {
      alive = false;
    };
  }, [salesKey, brandIdNow, days, ordersTick]);
  /** 지금 고른 기간의 합계. `undefined` 는 받는 중 */
  const sales: PeriodSales | null | undefined = salesKey && periodSales?.key === salesKey ? periodSales.value : undefined;
  /**
   * 화면에 그릴 기간 합계. 기간을 바꿔 새 값을 받는 동안은 **직전에 받은 기간 값**을 그 기간 표시 그대로 둔다 —
   * 그 사이 전체 합으로 바뀌었다 돌아오면 숫자가 1,2xx → 12 로 튀어 발표 중에 결함처럼 보인다. 한 번도 못 받았거나 실패했을 때만 전체 합이다.
   */
  const shownSales = sales !== undefined ? sales : (periodSales?.value ?? null);
  const shownDays = sales !== undefined ? days : (periodSales?.days ?? days);

  /*
   * 맨 위 "오늘" 숫자 넷(오늘 방문·담기·주문·매출)은 뺐다 (2026-10-01 유림님: 정신없다). 대신 기간 필터에 "오늘" 이 있어
   * 그걸 고르면 아래 주문·매출·행동 숫자가 모두 오늘 것으로 바뀐다. 주문·매출은 실시간, 행동 기록은 새벽에 하루치가 들어온다.
   */
  const waiting = useMartWaiting();

  /**
   * AI 한 마디 (contracts/headline-api-spec.md) — 2026-10-01 오후에 되살렸다 (팀 의견: AI 가 요약해 주는 자리가 있는 게 낫다).
   * 오전에 뺀 이유였던 규칙 문장("…방문의 방문은 1,170건입니다")은 그대로 숨기고, **첫 문장을 AI 가 쓴 때만** 맨 위에 그린다.
   * 자리는 **처음부터** 잡아 둔다 (2026-10-01 유림님: 답이 온 뒤 위에서 끼어들어 아래가 밀리면 안 된다). 기다리는 동안은
   * "AI가 분석 중입니다", 못 받거나 AI 가 못 쓰면 숫자와 무관한 기본 문장(HEADLINE_FALLBACK)을 둔다.
   * 주문·매출은 카드와 같은 **기간 합계**로 보낸다 (전체 합을 보내면 문장과 카드 숫자가 어긋난다). 기간 합계를 받는 중이면 기다린다.
   */
  const brand = useMemo(() => ({ name: brandName ?? '', productCount: productMetrics.length }), [brandName, productMetrics.length]);
  const salesSettled = salesKey === null || sales !== undefined;
  /*
   * 한 마디에 넣는 주문 숫자는 **그 기간을 처음 받은 값**으로 묶는다. 주문 칸은 실시간으로 다시 받는데, 그때마다 한 마디를
   * 새로 부르면 카드가 "분석 중" 으로 깜빡이고 LLM 을 주문마다 태운다. 기간·브랜드를 바꾸면 다시 묶는다.
   */
  const headlineSalesRef = useRef<{ key: string | null; pulse: SellerPulse | null; sales: PeriodSales | null } | null>(null);
  if (pulse !== undefined && salesSettled && headlineSalesRef.current?.key !== salesKey) {
    headlineSalesRef.current = { key: salesKey, pulse, sales: sales ?? null };
  }
  const frozen = headlineSalesRef.current?.key === salesKey ? headlineSalesRef.current : null;
  const headlineReq = useMemo(
    () => {
      // 행동 기록을 기다리는 동안에는 빈 숫자로 부르지 않는다 — 받은 뒤 다시 부르면 LLM 을 두 번 태운다
      if (!frozen || waiting) return null;
      const forHeadline = frozen.pulse && frozen.sales ? { ...frozen.pulse, orders: frozen.sales.orders, revenue: frozen.sales.revenue, units: frozen.sales.units } : frozen.pulse;
      return buildOverviewHeadlineRequest(m, brand, days, forHeadline);
    },
    [m, brand, days, frozen, waiting],
  );
  const { loading: headlineLoading, env: headline } = useHeadlineState(headlineReq);
  // 요청을 만들 재료(행동 기록·주문 합계)를 아직 받는 중이면 그것도 "분석 중" 이다
  const headlinePending = headlineLoading || (!!brandName && (pulse === undefined || !salesSettled || waiting));
  /*
   * AI 가 쓴 줄만 쓴다. 서버는 걸린 줄만 규칙 문장(숫자 나열)으로 바꿔 `mixed` 로 돌려주는데, 첫 문장만 걸려도 카드째 기본 문장이
   * 되면 통과한 AI 줄까지 버린다 (2026-10-01 실측: "크게 늘었" 이 unsupported_comparison 으로 걸려 첫 문장이 "…방문의 방문은
   * 1,170건입니다" 가 됐고, 서버가 그 결과를 저장해 새로고침해도 같았다). 첫 문장이 걸렸으면 통과한 AI 줄 첫째를 맨 위로 올린다.
   * 규칙 줄은 "자세히" 에서도 뺀다 — "찾아온 방문은 방문 1,170건" 같은 되읊기다.
   */
  const headlineAi = useMemo(() => {
    if (!headline) return null;
    const lines = headline.sections.filter((s) => s.line && lineOrigin(headline, s) === 'llm');
    if (headline.headline && headlineOrigin(headline) === 'llm') return { line: headline.headline, more: lines };
    if (lines.length === 0) return null;
    return { line: lines[0].line, more: lines.slice(1) };
  }, [headline]);
  const sectionLabel = useMemo(() => new Map((headlineReq?.sections ?? []).map((s) => [s.id, s.label_ko])), [headlineReq]);

  return (
    <div className="stack">
      {/*
        주문·매출은 맨 위 (2026-10-01 유림님). 사장님이 제일 먼저 보는 숫자다.
        주문·매출·판매 수량은 **고른 기간(최근 N일)** 으로 센다 (2026-10-01). 기간 집계를 못 받았거나 아직 받는 중이면
        전체 합(pulse)을 그대로 두고 "전체 기간" 이라고 적는다 — 묶음마다 기간을 적어 아래 행동 숫자와 섞어 읽지 않게 한다 (2026-09-29)
      */}
      {shownSales || pulse ? <p className="kpi-period">{shownSales ? `주문·매출 · ${periodLabel(shownDays)}` : '주문·매출 · 전체 기간'}</p> : null}
      {shownSales ? (
        <div className="grid grid--kpi">
          <Kpi
            label="주문"
            value={`${fmt.int(shownSales.orders)}건`}
            sub={shownSales.truncated ? `${fmt.int(SELLER_ORDER_LIMIT)}건까지만 셌습니다` : pulse ? `전체 기간 ${fmt.int(pulse.orders)}건` : shownSales.orders > 0 ? '결제 완료' : '이 기간에는 주문이 없습니다'}
            source="real"
          />
          {/* 원 단위 그대로 적으면 카드에서 줄이 넘어간다. 100만 원 넘으면 만 원 단위로 줄이고 정확한 값은 아래 한 줄에 */}
          <Kpi
            label="매출"
            value={wonCompact(shownSales.revenue)}
            sub={shownSales.truncated ? `${fmt.int(SELLER_ORDER_LIMIT)}건까지의 합입니다` : shownSales.revenue >= 1_000_000 ? `${Math.round(shownSales.revenue).toLocaleString('ko-KR')}원` : pulse ? `전체 기간 ${wonCompact(pulse.revenue)}` : shownSales.revenue > 0 ? '결제 완료' : '이 기간에는 매출이 없습니다'}
            source="real"
          />
          <Kpi
            label="판매 수량"
            value={`${fmt.int(shownSales.units)}개`}
            sub={shownSales.truncated ? `${fmt.int(SELLER_ORDER_LIMIT)}건까지의 합입니다` : shownSales.orders > 0 ? `한 주문에 평균 ${(shownSales.units / shownSales.orders).toFixed(1)}개` : pulse ? `전체 기간 ${fmt.int(pulse.units)}개` : '이 기간에는 팔린 수량이 없습니다'}
            source="real"
          />
        </div>
      ) : pulse ? (
        <div className="grid grid--kpi">
          <Kpi label="주문" value={`${fmt.int(pulse.orders)}건`} sub={pulse.orders > 0 ? '결제 완료' : '아직 주문이 없습니다'} source="real" />
          <Kpi label="매출" value={wonCompact(pulse.revenue)} sub={pulse.revenue >= 1_000_000 ? `${Math.round(pulse.revenue).toLocaleString('ko-KR')}원` : pulse.revenue > 0 ? '결제 완료' : '아직 매출이 없습니다'} source="real" />
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
        머리말("지금 무슨 일이")과 "AI가 쓴 문장" 꼬리표는 달지 않는다 — 발표 화면에서 거슬리고, 사장님에게는 문장 자체가 중요하다.
        출처는 title 로 남겨 마우스를 올리면 보인다. 섹션 줄은 "자세히" 로 접어 둔다 (2026-09-21 유림님: 글이 너무 많다).
      */}
      {headlineAi ? (
        <section className="headline" aria-label="지금 상황 한 마디" title="아래 숫자를 보고 AI가 문장으로 풀어 썼습니다">
          <p className="headline__line">{headlineAi.line}</p>
          {headlineAi.more.length > 0 ? (
            <details className="headline__more">
              <summary>자세히</summary>
              <ul className="headline__sections">
                {headlineAi.more.map((s) => (
                  <li key={s.id}>
                    <span className="headline__label">{sectionLabel.get(s.id) ?? ''}</span>
                    <span>{s.line}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="headline__hint">{HEADLINE_FALLBACK.hint}</p>
          )}
        </section>
      ) : headlinePending ? (
        <section className="headline headline--loading" aria-label="지금 상황 한 마디" aria-busy="true">
          <p className="headline__line headline__line--loading">
            <span className="ai__dot" aria-hidden="true" />
            AI가 분석 중입니다<span className="headline__dots" aria-hidden="true" />
          </p>
          <span className="headline__skeleton" aria-hidden="true" />
        </section>
      ) : (
        <section className="headline" aria-label="지금 상황 한 마디">
          <p className="headline__line">{HEADLINE_FALLBACK.line}</p>
          <p className="headline__hint">{HEADLINE_FALLBACK.hint}</p>
        </section>
      )}
      {/* 여기부터는 고객 행동 기록에서 나온 숫자다. 맨 위 주문·매출은 기다리지 않고 먼저 보인다 (2026-09-30) */}
      <BehaviorGate>
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

      <p className="kpi-period">고객 행동 · {periodLabel(days)}</p>
      <div className="grid grid--kpi">
        <Kpi
          label="상세를 보고 담은 비율"
          value={fmt.pct(overview.cartRate)}
          sub={noBehavior ? emptyWhy : `상세를 연 방문 ${fmt.int(overview.detailSessions)}건 중${delta(overview.cartRate, previous?.cartRate)}`}
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
          sub={fbTop ? `${fbTop[1]}번 · 의견 ${fb.length}건 · 기간 없이 전체` : '아직 의견이 없습니다'}
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

      {reasons.length > 0 ? (
        <Panel title="고객이 고른 구매 이유" source={source.purchase} aside={`결제할 때 답한 주문 ${fmt.int(reasonOrders)}건`}>
          <BarList
            items={reasons.map((r) => ({
              label: REASON_KO.get(r.reason) ?? r.reason,
              value: r.share ?? r.orderCount / reasonOrders,
              hint: `${fmt.int(r.orderCount)}건`,
            }))}
            format={(v) => fmt.pct(v, 0)}
          />
        </Panel>
      ) : null}
      <div className="grid grid--2">
        <Panel
          title={`날짜별 ${trend === 'visits' ? '방문' : '담기'} · ${periodLabel(days)}`}
          source={source.overview}
          aside={
            <span className="chips chips--inline">
              {(
                [
                  ['visits', '방문'],
                  ['carts', '담기'],
                ] as const
              ).map(([k, label]) => (
                <button key={k} type="button" className={`chip${trend === k ? ' chip--hit' : ''}`} onClick={() => setTrend(k)}>
                  {label}
                </button>
              ))}
            </span>
          }
        >
          <LineChart
            points={series.map((d) => ({ label: d.label, value: trend === 'visits' ? d.visits : d.carts }))}
            label={trend === 'visits' ? '날짜별 방문 수 변화' : '날짜별 장바구니 담기 변화'}
            emptyText={trend === 'visits' ? '아직 방문 기록이 없습니다' : '아직 담기 기록이 없습니다'}
          />
        </Panel>
        <Panel title="구매까지 가는 단계" source={source.funnel} aside="단계마다 남은 방문">
          <Funnel steps={standardFunnel} />
          {/*
            클릭은 퍼널 칸이 아니라 곁가지다 (은솔님 2026-09-22). 목록의 빠른 보기는 클릭을 남기지 않아 클릭과 빠른 보기가
            병렬 경로이고, 실제 주 동선은 빠른 보기다. 퍼널에 클릭 칸이 있으면 "대부분 클릭으로 들어온다" 로 거꾸로 읽힌다.
          */}
          {funnelNote && funnelNote.impressionSessions > 0 ? (
            <p className="funnel__aside" title="목록의 빠른 보기는 상품을 누른 것으로 세지 않습니다">
              <span>상품을 누른 방문</span>
              <b>{fmt.pct(funnelNote.clickSessions / funnelNote.impressionSessions)}</b>
              <em>
                보인 {fmt.int(funnelNote.impressionSessions)}건 중 {fmt.int(funnelNote.clickSessions)}건
                {funnelNote.quickLookSessions !== null
                  ? ` · 상세를 연 ${fmt.int(funnelNote.detailSessions)}건은 빠른 보기 ${fmt.int(funnelNote.quickLookSessions)} · 상품 상세 ${fmt.int(funnelNote.productViewSessions)}`
                  : ''}
              </em>
            </p>
          ) : null}
          {/*
            성분·리뷰 확인은 단계가 아니라 곁가지다 — 퀵룩으로 담은 방문은 볼 기회가 없었다. 퍼널에 끼우면
            "성분·리뷰 → 담기" 가 154% 로 나온다. 분모를 상품 상세 방문으로 맞춰 옆에 적는다 (2026-09-22).
          */}
          {funnelNote?.quickLookCartSessions && cartSessions > 0 ? (
            <p className="funnel__aside" title="상품 상세를 열지 않고 빠른 보기 창에서 바로 담은 방문">
              <span>빠른 보기에서 바로 담음</span>
              <b>{fmt.pct(funnelNote.quickLookCartSessions / cartSessions)}</b>
              <em>
                담은 {fmt.int(cartSessions)}건 중 {fmt.int(funnelNote.quickLookCartSessions)}건
              </em>
            </p>
          ) : null}
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
          <Kpi label="방문" value={`${fmt.int(overview.sessions)}번`} sub={noBehavior ? emptyWhy : periodLabel(days)} />
          <Kpi label="상품 상세 본 횟수" value={`${fmt.int(overview.detailViews)}번`} sub={noBehavior ? emptyWhy : periodLabel(days)} />
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
      </BehaviorGate>
    </div>
  );
}

/** 고른 기간의 주문 합계. `truncated` 는 서버 상한(SELLER_ORDER_LIMIT)만큼 돌아와 더 있을 수 있다는 뜻 */
interface PeriodSales {
  orders: number;
  revenue: number;
  units: number;
  truncated: boolean;
  /** 결제 시각이 오늘(로컬)인 주문만 */
  today: { orders: number; revenue: number };
}

/** 로컬(Asia/Seoul) 기준 YYYY-MM-DD. ISO 를 UTC 로 자르면 자정 근처 주문이 어제로 간다 (MyProducts 와 같은 규칙) */
function localDay(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 결제 완료 주문 목록 → 주문 수 · 내 브랜드 줄의 매출 합 · 팔린 개수. 다른 브랜드가 섞인 주문은 서버가 내 몫만 준다 (brand_amount) */
function summarizeOrders(rows: SellerOrder[]): PeriodSales {
  const today = localDay(new Date().toISOString());
  let revenue = 0;
  let units = 0;
  const todaySum = { orders: 0, revenue: 0 };
  for (const o of rows) {
    const amount = Number(o.brand_amount) || 0;
    revenue += amount;
    units += Number(o.item_count) || 0;
    if (localDay(o.ordered_at) === today) {
      todaySum.orders += 1;
      todaySum.revenue += amount;
    }
  }
  return { orders: rows.length, revenue, units, truncated: rows.length >= SELLER_ORDER_LIMIT, today: todaySum };
}
