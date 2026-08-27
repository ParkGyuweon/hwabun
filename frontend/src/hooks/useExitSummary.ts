import { useEffect, useRef } from 'react';
import { flush, track } from '../lib/logger';
import { dominantRegion } from '../lib/section';

/**
 * 페이지 이탈 요약.
 *
 * 어느 지점에서 얼마나 머무르다 나갔는지는 이탈 분석의 출발점이다.
 * 탭이 숨겨지는 시점에 남기고, 남은 큐를 sendBeacon 으로 밀어낸다.
 * (unload 시점의 일반 fetch 는 브라우저가 취소할 수 있다)
 */
/**
 * 이 시간을 못 채우고 정리되면 실제 방문이 아니라 리마운트로 본다.
 * React StrictMode 는 개발 중 이펙트를 두 번 실행해서 마운트 직후 정리 함수를 한 번 호출한다.
 * 그대로 두면 페이지에 들어오자마자 이탈 로그가 한 건 섞여 QA 가 어려워진다.
 */
const MIN_DWELL_MS = 300;

export function useExitSummary(pageViewKey: string) {
  // 렌더 중에는 Date.now() 를 부르지 않는다. 실제 진입 시각은 이펙트에서 채운다
  const enteredAtRef = useRef(0);
  const sentRef = useRef(false);

  useEffect(() => {
    enteredAtRef.current = Date.now();
    sentRef.current = false;

    /**
     * 도달한 최대 깊이를 따로 들고 있는다.
     * 이탈 순간의 스크롤 위치로 계산하면, 끝까지 읽고 맨 위로 올려둔 채 나간 방문이
     * "조금 보다 나갔다" 로 기록된다.
     */
    let maxDepthPercent = 0;
    /** 마지막으로 머물던 섹션. 어디서 끊겼는지 보려고 남긴다 */
    let lastRegion = dominantRegion();

    const measure = () => {
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - window.innerHeight;
      const depth =
        scrollable > 0
          ? Math.min(100, Math.round(((window.scrollY + window.innerHeight) / doc.scrollHeight) * 100))
          : 100;

      if (depth > maxDepthPercent) maxDepthPercent = depth;

      const region = dominantRegion();
      if (region.section_id !== null) lastRegion = region;
    };

    const send = (reason: string) => {
      if (sentRef.current) return;
      const dwellMs = Date.now() - enteredAtRef.current;
      if (dwellMs < MIN_DWELL_MS) return;
      sentRef.current = true;

      measure();

      track('exit_summary', {
        reason,
        dwell_ms: dwellMs,
        max_scroll_percent: maxDepthPercent,
        last_section_id: lastRegion.section_id,
        last_content_kind: lastRegion.content_kind,
      });

      flush(true);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        send('tab_hidden');
      }
    };

    const onPageHide = () => send('page_hide');

    window.addEventListener('scroll', measure, { passive: true });
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);
    measure();

    return () => {
      window.removeEventListener('scroll', measure);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onPageHide);
      // 상품을 바꿔 다른 상세로 이동하는 것도 이 페이지에서의 이탈이다
      send('navigate');
    };
  }, [pageViewKey]);
}
