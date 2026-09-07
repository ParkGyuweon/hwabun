import { products as productsData } from '../../mocks/products';
import { fmt, hashString, rng } from '../../dashboard/lib/metrics';
import type { Product } from '../../types/product';

/**
 * 참여 브랜드(테넌트) 목록과 브랜드별 지표.
 *
 * 브랜드는 지어내지 않는다. 상품 200개의 brand_name 을 그대로 쓴다 — 실제로 55개다.
 * 발표의 "50개 브랜드" 는 이 수를 어림한 것이고, 표에는 실제 수를 적는다.
 *
 * 행동 지표는 브랜드 대시보드와 같은 방식의 **모의값**이다. 상품 수·리뷰 수·평점에
 * 비례하도록 시드를 고정해 만든다. 새로고침해도 안 바뀐다. 파이프라인이 붙으면
 * 이 파일의 함수 본문만 집계 API 호출로 바뀐다.
 */

const products = productsData as unknown as Product[];

export type TenantStatus = 'ok' | 'watch' | 'stale';

export interface Tenant {
  /** brand_name 을 그대로 식별자로 쓴다. 실데이터에는 brand_id 가 없다 */
  id: string;
  name: string;
  productCount: number;
  reviewCount: number;
  avgRating: number;
  /** 오늘 0시부터 지금까지 들어온 Event 수 */
  eventsToday: number;
  sessionsToday: number;
  detailRate: number;
  cartRate: number;
  ingredientViewRate: number;
  bounceRate: number;
  /** 마지막 Event 가 들어온 뒤 지난 초 */
  lastEventAgoSec: number;
  status: TenantStatus;
}

function build(): Tenant[] {
  const byBrand = new Map<string, Product[]>();
  for (const p of products) {
    const list = byBrand.get(p.brand_name) ?? [];
    list.push(p);
    byBrand.set(p.brand_name, list);
  }

  const out: Tenant[] = [];
  for (const [name, list] of byBrand) {
    const rand = rng(hashString(`tenant:${name}`));
    const reviewCount = list.reduce((s, p) => s + (p.review_count ?? 0), 0);
    const avgRating = list.reduce((s, p) => s + (p.rating ?? 0), 0) / list.length;

    // 인기(리뷰 수)에 비례. 로그 스케일로 눌러 상위 쏠림을 줄인다
    const popularity = Math.log10(reviewCount + 10) / 6;
    const sessionsToday = Math.round(120 + popularity * 2600 + rand() * 300);
    // 방문당 100~160건이 실측. 브랜드마다 조금씩 다르게
    const eventsToday = Math.round(sessionsToday * (100 + rand() * 60));

    const detailRate = 0.08 + popularity * 0.09 + rand() * 0.04;
    const cartRate = 0.06 + (avgRating / 5) * 0.09 + rand() * 0.05;
    const ingredientViewRate = 0.3 + (avgRating / 5) * 0.2 + rand() * 0.2;
    const bounceRate = 0.24 + (1 - popularity) * 0.2 + rand() * 0.1;

    // 대부분 실시간. 일부는 수 분 전, 소수는 수집이 끊긴 것처럼 보이게
    const r = rand();
    const lastEventAgoSec =
      r < 0.8 ? Math.round(rand() * 45) : r < 0.94 ? Math.round(120 + rand() * 900) : Math.round(3600 + rand() * 7200);

    let status: TenantStatus = 'ok';
    if (lastEventAgoSec > 1800) status = 'stale';
    else if (bounceRate > 0.42 || detailRate < 0.1) status = 'watch';

    out.push({
      id: name,
      name,
      productCount: list.length,
      reviewCount,
      avgRating,
      eventsToday,
      sessionsToday,
      detailRate,
      cartRate,
      ingredientViewRate,
      bounceRate,
      lastEventAgoSec,
      status,
    });
  }

  return out.sort((a, b) => b.eventsToday - a.eventsToday);
}

export const tenants: Tenant[] = build();

/* ---------- 전체 합계 ---------- */

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
};

/**
 * 업계 벤치마크. 참여 브랜드 전체의 중앙값이다.
 *
 * 이것이 "모여야 하는 이유" 다. 브랜드 하나는 자기 이탈률이 높은 편인지 알 수 없다 —
 * 비교 대상이 없다. 50개가 모이면 중앙값이 생기고, 자기 위치가 보인다.
 */
export const benchmark = {
  detailRate: median(tenants.map((t) => t.detailRate)),
  cartRate: median(tenants.map((t) => t.cartRate)),
  ingredientViewRate: median(tenants.map((t) => t.ingredientViewRate)),
  bounceRate: median(tenants.map((t) => t.bounceRate)),
};

export const totals = {
  tenants: tenants.length,
  products: tenants.reduce((s, t) => s + t.productCount, 0),
  eventsToday: tenants.reduce((s, t) => s + t.eventsToday, 0),
  sessionsToday: tenants.reduce((s, t) => s + t.sessionsToday, 0),
  live: tenants.filter((t) => t.lastEventAgoSec < 60).length,
  watch: tenants.filter((t) => t.status === 'watch').length,
  stale: tenants.filter((t) => t.status === 'stale').length,
};

/* ---------- 분포 (벤치마크 화면) ---------- */

/** 값을 구간으로 묶어 막대 높이를 만든다. 히스토그램 하나가 "분포" 를 말한다 */
export function histogram(values: number[], bins: number, min: number, max: number) {
  const width = (max - min) / bins;
  const counts = Array.from({ length: bins }, () => 0);
  for (const v of values) {
    const i = Math.min(bins - 1, Math.max(0, Math.floor((v - min) / width)));
    counts[i] += 1;
  }
  return counts.map((count, i) => ({
    from: min + i * width,
    to: min + (i + 1) * width,
    count,
  }));
}

/* ---------- 인프라 (모의) ---------- */

/**
 * 최근 24시간 이벤트 TPS. 새벽 골과 저녁 봉우리를 시드 고정으로 만든다.
 * 하루 합계가 totals.eventsToday 와 맞도록 정규화한다.
 */
export function tpsSeries(): Array<{ label: string; value: number }> {
  const rand = rng(20260902);
  const shape = Array.from({ length: 24 }, (_, h) => {
    const day = 0.35 + 0.65 * Math.max(0, Math.sin(((h - 6) / 24) * Math.PI * 2 * 0.5 + 0.2));
    return day * (0.9 + rand() * 0.2);
  });
  const sum = shape.reduce((a, b) => a + b, 0);
  // 하루 이벤트를 시간 분포대로 나누고, 초당으로 환산한다
  return shape.map((s, h) => ({
    label: `${String(h).padStart(2, '0')}시`,
    value: Math.round((totals.eventsToday * (s / sum)) / 3600),
  }));
}

export const pipeline = [
  { stage: 'Collector', detail: 'POST /api/events · 배치 20건/5초', state: 'ok' as const, metric: 'p95 38ms' },
  { stage: 'Kafka', detail: 'activity-events · 파티션 6', state: 'ok' as const, metric: 'lag 0' },
  { stage: 'Spark', detail: 'raw_sink · clean_events · derive_facts · build_marts', state: 'watch' as const, metric: '연결 검증 중' },
  { stage: 'Mart', detail: '일간 7 · 실시간 2', state: 'watch' as const, metric: '스키마 확정 · 적재 전' },
];

export const badEvents = [
  { reason: '필수 property 누락', count: 412 },
  { reason: 'enum 밖 값', count: 138 },
  { reason: 'schema_version 불일치', count: 27 },
  { reason: '봉투 필드 누락', count: 9 },
];

export { fmt };
