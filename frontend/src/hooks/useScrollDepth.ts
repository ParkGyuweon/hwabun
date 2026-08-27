import { useEffect } from 'react';
import { track, trackOnce } from '../lib/logger';
import { dominantSection, scrollPercent } from '../lib/section';

/**
 * 스크롤 기반 주목 신호.
 *
 * 세 가지를 남긴다.
 *
 * 1. scroll_depth  — 어디까지 내려갔나 (방문당 구간별 1회)
 * 2. scroll_pause  — 내리다 멈춘 지점 (멈출 때마다)
 * 3. scroll_backtrack — 내려갔다가 다시 올려본 지점 (되돌아볼 때마다)
 *
 * 도달 깊이만 남기면 "끝까지 봤다" 는 알아도 **어디서 붙잡혔는지**를 모른다.
 * 멈춘 지점이 곧 관심 지점이라, 추천 입력으로는 이쪽이 더 쓸모가 있다.
 * 되돌아보기는 비교·확신 부족의 신호라 이탈 분석에서 따로 본다.
 */

/**
 * 25% 단위는 8000px 짜리 상세 페이지에서 한 칸이 2000px 이라 너무 성기다.
 * 10% 단위로 좁혀 어느 구간에서 멈췄는지 볼 수 있게 한다.
 */
const MILESTONE_STEP = 10;

/**
 * 스크롤이 이만큼 멈추면 "멈췄다" 로 본다.
 *
 * 1초는 사람이 훑어보다 잠깐 시선을 두는 시간보다 길어서, 쭉 훑는 동안에는
 * 아무것도 안 남고 완전히 멈춰야만 찍혔다. 300ms 대로 낮추면 스크롤 한 번에
 * 여러 건이 남을 수 있지만, 어차피 멈출 때만 발생하므로 스크롤 중에는 늘지 않는다.
 */
const PAUSE_MS = 320;

/** 멈춤 직전 이동 거리가 이보다 짧으면 손떨림으로 보고 버린다 */
const MIN_BURST_PX = 24;

/** 아래로 보던 중 이만큼 다시 올라가면 되돌아본 것으로 본다 */
const BACKTRACK_PX = 240;

export function useScrollDepth(pageViewKey: string) {
  useEffect(() => {
    let lastY = window.scrollY;
    /** 마지막 멈춤 이후 이동을 한 덩어리로 묶어 속도를 낸다 */
    let burstStartY = window.scrollY;
    let burstStartAt = Date.now();
    let burstMoved = false;

    /** 방향이 바뀐 뒤 누적 이동 거리. 되돌아보기 판정용 */
    let reversalDistance = 0;
    let lastDirection: 'up' | 'down' | null = null;

    let pauseTimer: number | undefined;

    const measureDepth = () => {
      const doc = document.documentElement;
      // 화면보다 짧은 페이지는 스크롤 깊이가 의미 없다
      if (doc.scrollHeight - window.innerHeight <= 0) return;

      const reached = ((window.scrollY + window.innerHeight) / doc.scrollHeight) * 100;

      for (let milestone = MILESTONE_STEP; milestone <= 100; milestone += MILESTONE_STEP) {
        if (reached >= milestone) {
          trackOnce(`scroll_depth:${pageViewKey}:${milestone}`, 'scroll_depth', {
            depth_percent: milestone,
            section_id: dominantSection(),
          });
        }
      }
    };

    const emitPause = () => {
      pauseTimer = undefined;
      if (!burstMoved) return;

      const distance = Math.abs(window.scrollY - burstStartY);
      if (distance < MIN_BURST_PX) {
        burstMoved = false;
        return;
      }

      const durationMs = Math.max(1, Date.now() - burstStartAt);

      track('scroll_pause', {
        section_id: dominantSection(),
        depth_percent: scrollPercent(),
        direction: window.scrollY >= burstStartY ? 'down' : 'up',
        distance_px: Math.round(distance),
        duration_ms: durationMs,
        // 빠르게 지나친 구간과 천천히 읽은 구간을 구분하는 값
        velocity_px_per_sec: Math.round((distance / durationMs) * 1000),
      });

      burstMoved = false;
      burstStartY = window.scrollY;
      burstStartAt = Date.now();
    };

    const onScroll = () => {
      const y = window.scrollY;
      const delta = y - lastY;

      if (delta !== 0) {
        const direction = delta > 0 ? 'down' : 'up';

        if (direction !== lastDirection) {
          reversalDistance = 0;
          lastDirection = direction;
        }
        reversalDistance += Math.abs(delta);

        if (direction === 'up' && reversalDistance >= BACKTRACK_PX) {
          track('scroll_backtrack', {
            section_id: dominantSection(),
            depth_percent: scrollPercent(),
            distance_px: Math.round(reversalDistance),
          });
          // 계속 올리는 동안 매 프레임 찍히지 않도록 기준점을 다시 잡는다
          reversalDistance = 0;
        }

        if (!burstMoved) {
          burstMoved = true;
          burstStartY = lastY;
          burstStartAt = Date.now();
        }
        lastY = y;
      }

      measureDepth();

      if (pauseTimer !== undefined) window.clearTimeout(pauseTimer);
      pauseTimer = window.setTimeout(emitPause, PAUSE_MS);
    };

    /**
     * requestAnimationFrame 으로 묶지 않는다.
     * 탭이 숨겨지면 브라우저가 rAF 를 멈추는데, 그 사이 예약된 콜백이 실행되지 않으면
     * 스로틀 플래그가 켜진 채로 남아 탭이 다시 보여도 스크롤 측정이 되살아나지 않는다.
     * 측정 자체가 숫자 비교 몇 번이라 매 스크롤마다 돌려도 부담이 없다.
     */
    window.addEventListener('scroll', onScroll, { passive: true });
    // 첫 화면이 이미 100% 인 경우도 있으므로 한 번 측정하고 시작한다
    measureDepth();

    return () => {
      window.removeEventListener('scroll', onScroll);
      if (pauseTimer !== undefined) window.clearTimeout(pauseTimer);
    };
  }, [pageViewKey]);
}
