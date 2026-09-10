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
import { type BehaviorMetrics, mockBehavior } from './behavior';
import { fetchMartBundle, type MartBundle } from './martApi';
import { fromMart } from './martAdapter';
import { catalogProducts } from './metrics';

export type MartState = 'idle' | 'loading' | 'ready' | 'unavailable';

interface BehaviorContextValue {
  metrics: BehaviorMetrics;
  /** 마트 호출 상태. 사이드바 문구에 쓴다 */
  martState: MartState;
  days: number;
}

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

  const bundle = key ? (cache.get(key) ?? (fetched?.key === key ? fetched.bundle : null)) : null;
  const martState: MartState = !key ? 'idle' : bundle ? (anyPayload(bundle) ? 'ready' : 'unavailable') : 'loading';

  const metrics = useMemo(() => {
    const mock = mockBehavior(days);
    if (!bundle || !anyPayload(bundle)) return mock;
    const mine: Product[] = brandName ? catalogProducts.filter((p) => p.brand_name === brandName) : [];
    return fromMart(bundle, mock, mine);
  }, [bundle, days, brandName]);

  const value = useMemo(() => ({ metrics, martState, days }), [metrics, martState, days]);
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

const FALLBACK = mockBehavior(14);
