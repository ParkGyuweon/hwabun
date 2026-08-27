import { useEffect } from 'react';
import { track } from '../lib/logger';
import { sectionOfNode } from '../lib/section';

/**
 * 클릭 주변의 망설임 / 마찰 신호.
 *
 * - hover_dwell : 버튼 위에 올려두고 안 누른 시간. 담을까 말까 재는 구간이다
 * - rage_click  : 같은 자리를 연타. 반응 없는 UI 를 만났다는 뜻
 * - dead_click  : 누를 수 없는 곳을 누름. 눌릴 거라 기대한 지점을 알려준다
 *
 * dead_click 이 특히 쓸모 있다. 사용성 조사에서 상품 이미지 확대가 안 되는 문제가
 * 반복해서 지적되는데, 확대되길 기대하고 이미지를 누른 사용자는 아무 로그도 남기지
 * 않고 사라진다. 그 클릭을 잡아야 "여기서 막혔다" 를 알 수 있다.
 */

/** 이보다 오래 올려두면 망설임으로 본다 */
const HOVER_DWELL_MS = 600;

/** 연타 판정 */
const RAGE_CLICK_COUNT = 3;
const RAGE_WINDOW_MS = 800;
const RAGE_RADIUS_PX = 40;

/** 눌릴 만한 요소로 취급할 선택자 */
const INTERACTIVE = 'a, button, input, select, textarea, summary, [role="button"], [data-log-action]';

export function useInteractionSignals(pageViewKey: string) {
  useEffect(() => {
    let hoverTarget: Element | null = null;
    let hoverStartedAt = 0;

    let clickTimes: number[] = [];
    let clickAnchor: { x: number; y: number } | null = null;
    let rageReported = false;

    const onPointerOver = (event: PointerEvent) => {
      const target = (event.target as Element | null)?.closest('[data-log-action]') ?? null;
      if (target === null || target === hoverTarget) return;

      hoverTarget = target;
      hoverStartedAt = Date.now();
    };

    const onPointerOut = (event: PointerEvent) => {
      if (hoverTarget === null) return;

      // 자식 요소로 옮겨간 것뿐이면 벗어난 게 아니다
      const next = event.relatedTarget as Node | null;
      if (next !== null && hoverTarget.contains(next)) return;

      const dwellMs = Date.now() - hoverStartedAt;
      const target = hoverTarget;
      hoverTarget = null;

      if (dwellMs < HOVER_DWELL_MS) return;

      track('hover_dwell', {
        section_id: sectionOfNode(target),
        action: target.getAttribute('data-log-action'),
        dwell_ms: dwellMs,
      });
    };

    const onClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const now = Date.now();
      const point = { x: event.clientX, y: event.clientY };

      // --- 연타 판정 ---
      const nearAnchor =
        clickAnchor !== null &&
        Math.abs(point.x - clickAnchor.x) <= RAGE_RADIUS_PX &&
        Math.abs(point.y - clickAnchor.y) <= RAGE_RADIUS_PX;

      if (!nearAnchor) {
        clickAnchor = point;
        clickTimes = [];
        rageReported = false;
      }

      clickTimes = [...clickTimes, now].filter((at) => now - at <= RAGE_WINDOW_MS);

      if (clickTimes.length >= RAGE_CLICK_COUNT && !rageReported) {
        rageReported = true;
        track('rage_click', {
          section_id: sectionOfNode(target),
          action: target?.closest('[data-log-action]')?.getAttribute('data-log-action') ?? null,
          click_count: clickTimes.length,
        });
      }

      // --- 헛클릭 판정 ---
      if (target?.closest(INTERACTIVE) == null) {
        track('dead_click', {
          section_id: sectionOfNode(target),
          // 무엇을 누르려 했는지 좁히기 위해 태그만 남긴다
          target_tag: target?.tagName.toLowerCase() ?? null,
        });
      }
    };

    document.addEventListener('pointerover', onPointerOver);
    document.addEventListener('pointerout', onPointerOut);
    document.addEventListener('click', onClick);

    return () => {
      document.removeEventListener('pointerover', onPointerOver);
      document.removeEventListener('pointerout', onPointerOut);
      document.removeEventListener('click', onClick);
    };
  }, [pageViewKey]);
}
