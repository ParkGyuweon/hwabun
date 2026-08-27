import { useEffect } from 'react';
import { trackOnce } from '../lib/logger';

const MILESTONES = [25, 50, 75, 100] as const;

/**
 * 스크롤 깊이 이벤트.
 *
 * 스크롤할 때마다 보내면 데이터가 폭증하므로
 * 25/50/75/100% 최초 도달 시 한 번씩만 남긴다.
 */
export function useScrollDepth(pageViewKey: string) {
  useEffect(() => {
    const measure = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      // 화면보다 짧은 페이지는 스크롤 깊이가 의미 없다
      if (scrollable <= 0) return;

      const percent = ((window.scrollY + window.innerHeight) / document.documentElement.scrollHeight) * 100;

      for (const milestone of MILESTONES) {
        if (percent >= milestone) {
          trackOnce(`scroll_depth:${pageViewKey}:${milestone}`, 'scroll_depth', {
            depth_percent: milestone,
          });
        }
      }
    };

    /**
     * requestAnimationFrame 으로 묶지 않는다.
     * 탭이 숨겨지면 브라우저가 rAF 를 멈추는데, 그 사이 예약된 콜백이 실행되지 않으면
     * 스로틀 플래그가 켜진 채로 남아 탭이 다시 보여도 스크롤 측정이 되살아나지 않는다.
     * 측정 자체가 숫자 비교 몇 번이라 매 스크롤마다 돌려도 부담이 없다.
     */
    window.addEventListener('scroll', measure, { passive: true });
    // 첫 화면이 이미 100% 인 경우도 있으므로 한 번 측정하고 시작한다
    measure();

    return () => window.removeEventListener('scroll', measure);
  }, [pageViewKey]);
}
