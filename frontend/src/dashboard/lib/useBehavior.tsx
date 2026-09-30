/**
 * 행동 지표 컨텍스트 · 화면은 `useBehavior()` 하나만 부른다.
 *
 * 브랜드·기간이 정해지면 마트 API 여섯 개를 병렬로 한 번 부르고(계약 §7), 응답을 화면 모양으로 바꿔 내려준다.
 * 서버가 없거나 이 브랜드 행이 없으면 모의 묶음 그대로다. 응답을 기다리는 동안도 모의 묶음을 먼저 그린다.
 * 화면이 비어 있는 순간이 없어야 시연에서 흔들리지 않는다.
 *
 * 마트 응답은 브랜드·기간별로 이 탭 안에서만 캐시한다. 화면을 오갈 때마다 다시 부르지 않는다.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Product } from '../../types/product';
import { type BehaviorMetrics, emptyBehavior } from './behavior';
import { fetchMartBundle, type MartBundle } from './martApi';
import { fromMart } from './martAdapter';
import { catalogProducts } from './metrics';
import { useBrandProducts } from './useBrandProducts';

export type MartState = 'idle' | 'loading' | 'ready' | 'unavailable';

interface BehaviorContextValue {
  metrics: BehaviorMetrics;
  /** 마트 호출 상태. 사이드바 문구에 쓴다 */
  martState: MartState;
  /** 화면을 "불러오는 중" 으로 가려 둘지. 받는 중이어도 오래 걸리면 false 가 된다 (useMartWaiting) */
  waiting: boolean;
  days: number;
}

/**
 * 행동 기록이 이만큼 안 오면 기다리기를 그만두고 받은 것만으로 그린다. 마트 호출에는 제한 시간이 없어서,
 * 서버 하나가 늦으면 화면이 "불러오는 중" 에 영영 멈춘다 (2026-09-30). 늦게 오면 그때 숫자가 채워진다
 */
const GATE_TIMEOUT_MS = 8000;

const Ctx = createContext<BehaviorContextValue | null>(null);

/** 브랜드:기간 → 응답. 한 탭 안에서만 산다 */
const cache = new Map<string, MartBundle>();
const pending = new Set<string>();

export function BehaviorProvider({
  brandId,
  brandName,
  days,
  children,
}: {
  /** shop_backend 브랜드 id. 없으면(서버 미연결) 마트를 부르지 않는다 */
  brandId: string | null;
  /** 성분 갭의 "내 라인" 판정용. 카탈로그에 같은 이름 브랜드가 있으면 그 상품들 */
  brandName: string | null;
  days: number;
  children: ReactNode;
}) {
  const key = brandId ? `${brandId}:${days}` : null;
  /**
   * 마지막으로 받은 응답을 컴포넌트 상태로도 든다. 모듈 캐시만 믿으면 개발 중 HMR 로 모듈이 다시 실행될 때
   * 캐시는 비고 effect 는 의존성이 안 바뀌어 다시 안 돌아 "받는 중" 에 갇힌다. 상태는 Fast Refresh 가 보존한다
   */
  const [fetched, setFetched] = useState<{ key: string; bundle: MartBundle } | null>(null);

  useEffect(() => {
    if (!key || !brandId || cache.has(key) || pending.has(key)) return;
    pending.add(key);
    let alive = true;
    void fetchMartBundle({ brandId, days }).then((b) => {
      cache.set(key, b);
      pending.delete(key);
      if (alive) setFetched({ key, bundle: b });
    });
    return () => {
      alive = false;
    };
  }, [key, brandId, days]);

  // 쇼핑몰에 등록된 이 브랜드 상품. 번들 카탈로그에 없는 새 상품도 이름을 붙이려고 받는다
  const { products: serverProducts } = useBrandProducts(brandId, brandName);

  const bundle = key ? (cache.get(key) ?? (fetched?.key === key ? fetched.bundle : null)) : null;
  const martState: MartState = !key ? 'idle' : bundle ? (anyPayload(bundle) ? 'ready' : 'unavailable') : 'loading';

  // 받는 중으로 GATE_TIMEOUT_MS 가 지난 key. 이 key 는 더 가리지 않는다
  const [slowKey, setSlowKey] = useState<string | null>(null);
  useEffect(() => {
    if (martState !== 'loading' || !key) return;
    const t = window.setTimeout(() => setSlowKey(key), GATE_TIMEOUT_MS);
    return () => window.clearTimeout(t);
  }, [martState, key]);
  const waiting = martState === 'loading' && slowKey !== key;

  const metrics = useMemo(() => {
    const base = emptyBehavior();
    if (!bundle || !anyPayload(bundle)) return base;
    const bundled: Product[] = brandName ? catalogProducts.filter((p) => p.brand_name === brandName) : [];
    // 서버 목록이 정본. 번들에만 있는 상품은 뒤에 붙인다 (같은 id 는 한 번만)
    const server = serverProducts ?? [];
    const seen = new Set(server.map((p) => p.product_id));
    const mine = [...server, ...bundled.filter((p) => !seen.has(p.product_id))];
    return fromMart(bundle, base, mine);
  }, [bundle, days, brandName, serverProducts]);

  const value = useMemo(() => ({ metrics, martState, waiting, days }), [metrics, martState, waiting, days]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function anyPayload(b: MartBundle): boolean {
  return Object.values(b).some((p) => p !== null);
}

/** 화면이 읽는 행동 지표. Provider 밖에서 부르면(테스트·스토리) 모의 14일 */
export function useBehavior(): BehaviorMetrics {
  const v = useContext(Ctx);
  return v ? v.metrics : FALLBACK;
}

export function useMartState(): MartState {
  return useContext(Ctx)?.martState ?? 'idle';
}

/** 행동 기록을 아직 기다리는 중인지. 받는 중이라도 오래 걸리면 false — 화면을 영영 가리지 않는다 */
export function useMartWaiting(): boolean {
  return useContext(Ctx)?.waiting ?? false;
}

/**
 * 행동 기록을 받는 동안에는 감싼 부분 대신 "불러오는 중" 만 그린다. 받기 전 빈 묶음을 그대로 그리면
 * "0.0%"·"아직 기록이 없습니다" 가 잠깐 떴다 바뀌어, 사장님은 그 0 을 진짜로 읽는다 (2026-09-29).
 * 행동 기록에서 나온 부분만 감싼다 — 주문·매출처럼 따로 받는 숫자는 먼저 온 대로 바로 보여야 한다 (2026-09-30)
 */
export function BehaviorGate({ children }: { children: ReactNode }) {
  if (!useMartWaiting()) return <>{children}</>;
  return (
    <div className="stack" aria-busy="true">
      <p className="loading-state" role="status" aria-live="polite">
        고객 행동 기록을 불러오는 중…
      </p>
      <div className="grid grid--kpi" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="loading-block" />
        ))}
      </div>
      <div className="loading-block loading-block--tall" aria-hidden="true" />
    </div>
  );
}

const FALLBACK = emptyBehavior();
