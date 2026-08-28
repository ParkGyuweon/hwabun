import { useEffect, useRef } from 'react';
import { trackOnce } from '../lib/logger';
import type { EventName } from '../types/log';

/** 카드 면적의 이 비율 이상이 화면에 들어와야 노출로 본다 */
const VISIBLE_RATIO = 0.5;

/**
 * 스쳐 지나간 것을 노출로 세지 않기 위한 최소 유지 시간.
 * 목록을 빠르게 훑어 내리면 모든 카드가 순간적으로 화면을 지나간다.
 * 그걸 다 노출로 세면 클릭률의 분모가 부풀어서 지표가 못 쓰게 된다.
 */
const HOLD_MS = 300;

interface UseImpressionOptions {
  /** 방문이 바뀌면 노출을 다시 셀 수 있도록 하는 키 */
  pageViewKey: string;
  /** 남길 이벤트 이름 */
  eventName: Extract<EventName, 'product_impression' | 'recommendation_impression'>;
  /** 어느 목록에서 노출됐는지 (`similar_products`, `list_grid` 등) */
  listId: string;
  /** 추천 목록이면 어떤 알고리즘이 뽑았는지 */
  algorithm?: string;
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
 * 대상 요소는 `data-product-id` 와 `data-position` 을 갖고 있어야 한다.
 * 컨테이너 ref 를 돌려주므로 목록 루트에 붙이면 된다.
 */
export function useImpression({
  pageViewKey,
  eventName,
  listId,
  algorithm,
}: UseImpressionOptions) {
  const containerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    // 카드마다 "충분히 오래 보였는가" 를 재는 타이머
    const timers = new Map<Element, number>();

    const clearTimer = (el: Element) => {
      const id = timers.get(el);
      if (id !== undefined) {
        window.clearTimeout(id);
        timers.delete(el);
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const el = entry.target as HTMLElement;

          if (!entry.isIntersecting) {
            clearTimer(el);
            continue;
          }
          if (timers.has(el)) continue;

          const id = window.setTimeout(() => {
            timers.delete(el);

            const productId = el.dataset.productId;
            if (!productId) return;

            trackOnce(`${eventName}:${pageViewKey}:${listId}:${productId}`, eventName, {
              product_id: productId,
              list_id: listId,
              position: Number(el.dataset.position) || null,
              ...(algorithm ? { algorithm } : {}),
            });
          }, HOLD_MS);

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
      mutation.disconnect();
      observer.disconnect();
      timers.forEach((id) => window.clearTimeout(id));
      timers.clear();
    };
  }, [pageViewKey, eventName, listId, algorithm]);

  return containerRef;
}
