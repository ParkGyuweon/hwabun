import { useEffect, useRef } from 'react';
import { flush, track } from '../lib/logger';

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
  const enteredAtRef = useRef(Date.now());
  const sentRef = useRef(false);

  useEffect(() => {
    enteredAtRef.current = Date.now();
    sentRef.current = false;

    const send = (reason: string) => {
      if (sentRef.current) return;
      const dwellMs = Date.now() - enteredAtRef.current;
      if (dwellMs < MIN_DWELL_MS) return;
      sentRef.current = true;

      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const maxDepth = scrollable > 0
        ? Math.min(100, Math.round(((window.scrollY + window.innerHeight) / document.documentElement.scrollHeight) * 100))
        : 100;

      track('exit_summary', {
        reason,
        dwell_ms: dwellMs,
        max_scroll_percent: maxDepth,
      });

      flush(true);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        send('tab_hidden');
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', () => send('page_hide'));

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      // 상품을 바꿔 다른 상세로 이동하는 것도 이 페이지에서의 이탈이다
      send('navigate');
    };
  }, [pageViewKey]);
}
