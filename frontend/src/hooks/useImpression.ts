import { useEffect, useRef } from 'react';
import { hasTrackedOnce, track, trackOnce } from '../lib/logger';
import type { EventName } from '../types/log';

/** 카드 면적의 이 비율 이상이 화면에 들어와야 노출로 본다 */
const VISIBLE_RATIO = 0.5;

/**
 * 스쳐 지나간 것을 노출로 세지 않기 위한 최소 유지 시간의 기본값.
 * 목록을 빠르게 훑어 내리면 모든 카드가 순간적으로 화면을 지나간다.
 * 그걸 다 노출로 세면 클릭률의 분모가 부풀어서 지표가 못 쓰게 된다.
 *
 * 목록 카드는 작고 스캔이 빨라 300ms, 추천 카드는 1000ms 를 쓴다.
 * **기준이 다르므로 두 CTR 을 직접 비교하면 안 된다** — 그래서 판정 기준
 * (hold_ms, visible_ratio)을 모든 노출 이벤트에 실어 보낸다. 집계 쪽이
 * 기준을 맞춰 비교할 수 있고, 나중에 값을 바꿔도 과거 로그가 해석된다.
 */
const DEFAULT_HOLD_MS = 300;

interface UseImpressionOptions {
  /** 방문이 바뀌면 노출을 다시 셀 수 있도록 하는 키 */
  pageViewKey: string;
  /** 남길 이벤트 이름 */
  eventName: Extract<EventName, 'product_impression' | 'recommendation_impression' | 'banner_impression'>;
  /** 어느 목록에서 노출됐는지 (`similar_products`, `list_grid` 등) */
  listId: string;
  /** 노출 판정 유지 시간. 추천 카드는 1000ms 를 넘긴다 */
  holdMs?: number;
  /** 추천 목록이면 어떤 알고리즘이 뽑았는지 */
  algorithm?: string;
  /** 노출과 클릭을 같은 추천 요청으로 묶는 식별자 */
  recommendationId?: string;
  /**
   * 목록 전체에 공통으로 얹을 property. 카드마다 다른 값은 `data-*` 로 읽으므로
   * 여기에는 목록 단위로 같은 것만 둔다 (예: 배너의 `policy_version`).
   * 값이 undefined 인 키는 싣지 않는다.
   */
  extraProps?: Record<string, string | number | null | undefined>;
}

/**
 * 목록·추천 카드의 **노출**을 남긴다.
 *
 * 클릭만 남기면 분모가 없어서 클릭률을 계산할 수 없다. 추천이 실제로 먹혔는지
 * 판단하려면 "몇 번 보여줬는데 몇 번 눌렸나" 가 필요하다.
 *
 * 노출 자체는 사용자의 의지가 아니므로 선호도 가중치는 0 이다
 * (`EVENT_WEIGHT`). 분모로만 쓴다.
 *
 * 노출이 확정된 카드가 화면을 벗어날 때는 그 구간의 실제 유지 시간을
 * `impression_dwell` 로 남긴다. 판정 기준(300/1000ms)을 나중에 바꾸고 싶을 때
 * 코드 수정 없이 과거 로그를 재집계할 수 있다.
 *
 * 대상 요소는 `data-product-id` 와 `data-position` 을 갖고 있어야 한다.
 * 컨테이너 ref 를 돌려주므로 목록 루트에 붙이면 된다.
 */
/** 한 방문 안에서 같은 카드의 노출을 한 번만 세는 키. 훅과 클릭 확정이 같은 키를 써야 둘이 겹치지 않는다 */
const impressionKey = (eventName: string, pageViewKey: string, listId: string, productId: string) =>
  `${eventName}:${pageViewKey}:${listId}:${productId}`;

interface ConfirmByClickInput {
  pageViewKey: string;
  eventName: UseImpressionOptions['eventName'];
  listId: string;
  productId: string;
  position: number | null;
  algorithm?: string;
  recommendationId?: string;
  extraProps?: Record<string, string | number | null | undefined>;
}

/**
 * **클릭했다면 본 것이다.** 클릭 직전에 그 카드의 노출이 아직 안 남았으면 여기서 먼저 남긴다.
 *
 * 노출은 카드가 `holdMs`(300·1000ms) 동안 보여야 확정되는데 클릭은 그 자리에서 남는다. 카드가 나타나고
 * 300ms 안에 누르면 클릭만 있고 노출이 없어서, 마트의 클릭률이 1 을 넘고 Q5 검사가
 * `product_daily_rates_follow_contract` 로 그 날 배치를 막는다 (데이터 파트 2026-09-18).
 * 빨리 누르는 사람도, 스크롤 직후 바로 누르는 에이전트도 같은 틈에 들어간다. 로거 단계에서
 * 노출 ≥ 클릭을 보장하는 것이 가장 작은 수정이다 — 이벤트 이름·필수 속성은 그대로다.
 *
 * `hold_ms: 0` 으로 남긴다. 판정 기준을 함께 싣는 규칙(위 DEFAULT_HOLD_MS 설명) 그대로, "시간이 아니라
 * 클릭으로 확정된 노출" 이라는 뜻이다. 재집계 때 300ms 기준으로 걸러내고 싶으면 이 값으로 가를 수 있다.
 *
 * 같은 키를 훅이 쓰므로 뒤늦게 타이머가 돌아도 두 번 남지 않는다.
 */
export function confirmImpressionByClick({
  pageViewKey,
  eventName,
  listId,
  productId,
  position,
  algorithm,
  recommendationId,
  extraProps,
}: ConfirmByClickInput): boolean {
  return trackOnce(impressionKey(eventName, pageViewKey, listId, productId), eventName, {
    product_id: productId,
    list_id: listId,
    position,
    ...(algorithm ? { algorithm } : {}),
    ...(recommendationId ? { recommendation_id: recommendationId } : {}),
    ...Object.fromEntries(Object.entries(extraProps ?? {}).filter(([, v]) => v !== undefined)),
    hold_ms: 0,
    visible_ratio: VISIBLE_RATIO,
  });
}

export function useImpression({
  pageViewKey,
  eventName,
  listId,
  holdMs = DEFAULT_HOLD_MS,
  algorithm,
  recommendationId,
  extraProps,
}: UseImpressionOptions) {
  const containerRef = useRef<HTMLElement | null>(null);
  const extraPropsKey = JSON.stringify(extraProps ?? null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    // 카드마다 "충분히 오래 보였는가" 를 재는 타이머
    const timers = new Map<Element, number>();
    /** 보이기 시작한 시각. 벗어날 때 구간 유지 시간을 계산한다 */
    const visibleSince = new Map<Element, number>();
    /** 이 관찰 주기 안에서 노출이 확정된 카드 */
    const impressed = new Set<Element>();

    const baseProps = (el: HTMLElement) => ({
      product_id: el.dataset.productId,
      list_id: listId,
      position: Number(el.dataset.position) || null,
      ...(algorithm ? { algorithm } : {}),
      ...(recommendationId ? { recommendation_id: recommendationId } : {}),
      /**
       * 배너 카드는 어떤 축·값·칸에서 노출됐는지를 함께 남긴다 (log.ts BannerEventProperties).
       * `banner_value` 는 어휘집 원문이다. `new_brand` 는 값이 없어 키를 싣지 않는다.
       */
      ...(el.dataset.bannerType
        ? {
            banner_type: el.dataset.bannerType,
            // 계약 §3.13: 값이 없는 new_brand 는 키를 빼는 게 아니라 null 을 싣는다 (로거 NULLABLE_PROPERTIES 가 통과시킨다)
            banner_value: el.dataset.bannerValue ?? null,
            banner_slot: Number(el.dataset.bannerSlot ?? 0),
            ...(el.dataset.traitSource ? { trait_source: el.dataset.traitSource } : {}),
          }
        : {}),
      ...Object.fromEntries(
        Object.entries(extraProps ?? {}).filter(([, v]) => v !== undefined),
      ),
    });

    const clearTimer = (el: Element) => {
      const id = timers.get(el);
      if (id !== undefined) {
        window.clearTimeout(id);
        timers.delete(el);
      }
    };

    /** 노출 확정 카드가 화면을 벗어났다. 구간(delta) 유지 시간을 남긴다 */
    const emitDwell = (el: HTMLElement) => {
      const since = visibleSince.get(el);
      visibleSince.delete(el);
      if (since === undefined || !impressed.has(el)) return;

      track('impression_dwell', {
        ...baseProps(el),
        visible_ms: Date.now() - since,
      });
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const el = entry.target as HTMLElement;

          if (!entry.isIntersecting) {
            clearTimer(el);
            emitDwell(el);
            continue;
          }

          if (!visibleSince.has(el)) visibleSince.set(el, Date.now());
          if (timers.has(el)) continue;

          const id = window.setTimeout(() => {
            timers.delete(el);

            const productId = el.dataset.productId;
            if (!productId) return;

            const fired = trackOnce(
              impressionKey(eventName, pageViewKey, listId, productId),
              eventName,
              {
                ...baseProps(el),
                // 판정 기준을 같이 남긴다. 목록(300)과 추천(1000)은 분모 정의가 다르다
                hold_ms: holdMs,
                visible_ratio: VISIBLE_RATIO,
              },
            );
            // 클릭이 먼저 노출을 확정했으면(confirmImpressionByClick) 이미 남아 있다. 체류는 계속 잰다
            if (fired || hasTrackedOnce(impressionKey(eventName, pageViewKey, listId, productId))) impressed.add(el);
          }, holdMs);

          timers.set(el, id);
        }
      },
      { threshold: VISIBLE_RATIO },
    );

    /**
     * 카드는 데이터가 바뀌면 다시 그려지므로 새로 생긴 것도 관찰해야 한다.
     * MutationObserver 로 목록 변화를 따라간다.
     */
    const observeCards = () => {
      root.querySelectorAll<HTMLElement>('[data-product-id]').forEach((el) => {
        observer.observe(el);
      });
    };

    observeCards();
    const mutation = new MutationObserver(observeCards);
    mutation.observe(root, { childList: true, subtree: true });

    return () => {
      // 화면을 떠나는 시점에 아직 보이던 카드들의 구간도 마감한다
      for (const el of [...visibleSince.keys()]) emitDwell(el as HTMLElement);
      mutation.disconnect();
      observer.disconnect();
      timers.forEach((id) => window.clearTimeout(id));
      timers.clear();
    };
    // extraProps 는 매 렌더 새 객체라 의존성에 그대로 두면 관찰자가 계속 재설치된다.
    // 값이 바뀌었는지만 본다.
  }, [pageViewKey, eventName, listId, holdMs, algorithm, recommendationId, extraPropsKey]);

  return containerRef;
}
