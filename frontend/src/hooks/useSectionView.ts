import { useEffect, useRef } from 'react';
import { trackOnce } from '../lib/logger';
import type { LogSection } from '../types/log';

/** 섹션 면적의 50% 이상이 */
const VISIBLE_RATIO = 0.5;
/** 1초 이상 노출되면 조회로 인정한다 */
const DWELL_MS = 1000;

/**
 * 상세 페이지의 각 섹션이 실제로 읽혔는지 감지한다.
 *
 * 스쳐 지나간 것을 조회로 잡으면 "성분을 봤다" 같은 신호가 오염되므로
 * 노출 비율과 체류 시간을 모두 만족할 때만 section_view 를 남긴다.
 * 페이지 방문당 1회이며, 스크롤을 왕복해도 중복 발생하지 않는다.
 */
export function useSectionView(pageViewKey: string) {
  const timersRef = useRef(new Map<Element, number>());

  useEffect(() => {
    const timers = timersRef.current;
    const targets = document.querySelectorAll<HTMLElement>('[data-log-section]');
    if (targets.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const element = entry.target as HTMLElement;
          const sectionId = element.dataset.logSection as LogSection | undefined;
          if (!sectionId) continue;

          const visible = entry.isIntersecting && entry.intersectionRatio >= VISIBLE_RATIO;

          if (!visible) {
            // 1초를 채우기 전에 벗어났으면 조회로 인정하지 않는다
            const pending = timers.get(element);
            if (pending !== undefined) {
              window.clearTimeout(pending);
              timers.delete(element);
            }
            continue;
          }

          if (timers.has(element)) continue;

          const timer = window.setTimeout(() => {
            timers.delete(element);
            trackOnce(`section_view:${pageViewKey}:${sectionId}`, 'section_view', {
              section_id: sectionId,
              visible_ratio: Number(entry.intersectionRatio.toFixed(2)),
              visible_duration_ms: DWELL_MS,
            });
          }, DWELL_MS);

          timers.set(element, timer);
        }
      },
      { threshold: [VISIBLE_RATIO] },
    );

    for (const target of targets) {
      observer.observe(target);
    }

    return () => {
      observer.disconnect();
      for (const timer of timers.values()) {
        window.clearTimeout(timer);
      }
      timers.clear();
    };
  }, [pageViewKey]);
}
