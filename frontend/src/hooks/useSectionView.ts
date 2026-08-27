import { useEffect } from 'react';
import { track, trackOnce } from '../lib/logger';
import type { LogSection } from '../types/log';

/**
 * 상세 페이지의 각 섹션을 얼마나 봤는지 감지한다.
 *
 * - section_view  : 처음으로 "읽었다" 고 볼 만큼 머문 시점 (방문당 1회)
 * - section_dwell : 그 섹션에 실제로 머문 누적 시간 (나갈 때마다)
 *
 * 체류 시간은 관심도의 대표적인 암묵 신호지만 그것만으로는 노이즈가 크다.
 * (탭만 띄워두고 안 보는 경우) 그래서 스크롤 신호와 함께 해석하도록
 * scroll_pause / scroll_backtrack 과 같은 section_id 를 쓴다.
 *
 * IntersectionObserver 의 intersectionRatio 를 쓰지 않는다.
 * ratio 는 "요소 면적 대비" 라서 뷰포트보다 긴 섹션은 값이 절대 0.5 를 못 넘는다.
 * 리뷰 섹션처럼 긴 구간이 통째로 기록되지 않던 원인이라, 판정을 두 갈래로 바꿨다.
 */

/** 짧은 섹션: 자기 면적의 이만큼이 보이면 인정 */
const SECTION_RATIO = 0.4;
/** 긴 섹션: 화면의 이만큼을 채우면 인정 */
const VIEWPORT_RATIO = 0.35;

/**
 * 이만큼 머무르면 조회로 인정한다.
 * 1초는 훑어보는 속도보다 길어서 스쳐 간 섹션뿐 아니라 실제로 읽은 섹션까지 놓쳤다.
 */
const VIEW_DWELL_MS = 400;

/** 이 미만은 스쳐 간 것으로 보고 dwell 을 남기지 않는다 */
const MIN_DWELL_EMIT_MS = 700;

/** 한 섹션에 오래 머물 때 중간 저장 주기. 이탈 시 통째로 유실되는 것을 막는다 */
const DWELL_CHECKPOINT_MS = 15000;

/** 스크롤 중 재계산 최소 간격 */
const EVALUATE_THROTTLE_MS = 100;

interface SectionState {
  id: LogSection;
  visibleSince: number | null;
  /** 아직 로그로 내보내지 않은 체류 시간 */
  pendingMs: number;
}

export function useSectionView(pageViewKey: string) {
  useEffect(() => {
    const targets = [...document.querySelectorAll<HTMLElement>('[data-log-section]')];
    if (targets.length === 0) return;

    const states = new Map<HTMLElement, SectionState>();
    for (const element of targets) {
      const id = element.dataset.logSection as LogSection | undefined;
      if (id) states.set(element, { id, visibleSince: null, pendingMs: 0 });
    }

    let lastEvaluatedAt = 0;
    let throttleTimer: number | undefined;

    const isVisible = (element: HTMLElement): boolean => {
      const rect = element.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const visibleHeight = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);
      if (visibleHeight <= 0) return false;

      // 짧은 섹션과 긴 섹션 중 어느 한쪽 기준만 넘으면 본 것으로 친다
      return (
        visibleHeight / Math.max(1, rect.height) >= SECTION_RATIO ||
        visibleHeight / viewportHeight >= VIEWPORT_RATIO
      );
    };

    const emitDwell = (state: SectionState, reason: string) => {
      if (state.pendingMs < MIN_DWELL_EMIT_MS) return;

      track('section_dwell', {
        section_id: state.id,
        dwell_ms: Math.round(state.pendingMs),
        reason,
      });
      state.pendingMs = 0;
    };

    const evaluate = () => {
      const now = Date.now();
      lastEvaluatedAt = now;

      for (const [element, state] of states) {
        const visible = isVisible(element);

        if (visible) {
          if (state.visibleSince === null) {
            state.visibleSince = now;
            continue;
          }

          const heldMs = now - state.visibleSince;

          if (heldMs >= VIEW_DWELL_MS) {
            trackOnce(`section_view:${pageViewKey}:${state.id}`, 'section_view', {
              section_id: state.id,
              visible_duration_ms: heldMs,
            });
          }

          // 오래 머무는 중이면 중간에 한 번씩 끊어서 남긴다
          if (state.pendingMs + heldMs >= DWELL_CHECKPOINT_MS) {
            state.pendingMs += heldMs;
            state.visibleSince = now;
            emitDwell(state, 'checkpoint');
          }
          continue;
        }

        if (state.visibleSince !== null) {
          state.pendingMs += now - state.visibleSince;
          state.visibleSince = null;
          emitDwell(state, 'left_viewport');
        }
      }
    };

    /** 스크롤 중에도 놓치지 않도록 일정 간격을 보장한다 */
    const onScroll = () => {
      const since = Date.now() - lastEvaluatedAt;
      if (since >= EVALUATE_THROTTLE_MS) {
        evaluate();
        return;
      }
      if (throttleTimer === undefined) {
        throttleTimer = window.setTimeout(() => {
          throttleTimer = undefined;
          evaluate();
        }, EVALUATE_THROTTLE_MS - since);
      }
    };

    /** 스크롤을 멈추고 가만히 읽는 동안에도 체류가 쌓여야 한다 */
    const ticker = window.setInterval(evaluate, 1000);

    const flushAll = (reason: string) => {
      const now = Date.now();
      for (const state of states.values()) {
        if (state.visibleSince !== null) {
          state.pendingMs += now - state.visibleSince;
          state.visibleSince = null;
        }
        emitDwell(state, reason);
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') flushAll('tab_hidden');
      else evaluate();
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', evaluate);
    document.addEventListener('visibilitychange', onVisibilityChange);
    evaluate();

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', evaluate);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.clearInterval(ticker);
      if (throttleTimer !== undefined) window.clearTimeout(throttleTimer);
      flushAll('page_leave');
    };
  }, [pageViewKey]);
}
