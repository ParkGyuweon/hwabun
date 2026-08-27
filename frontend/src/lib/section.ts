import type { LogSection } from '../types/log';

/**
 * "지금 보고 있는 곳이 어느 섹션인가" 를 알아내는 유틸.
 *
 * 주목 신호(스크롤 멈춤, 텍스트 드래그, 호버)는 클릭과 달리 발생 지점이 정해져 있지 않다.
 * 픽셀 좌표를 그대로 남기면 레이아웃이 바뀌는 순간 과거 로그를 해석할 수 없게 되므로,
 * 항상 `data-log-section` 의 의미 단위 값으로 환산해서 남긴다.
 */

const SECTION_ATTRIBUTE = 'data-log-section';

/** 노드가 속한 섹션. 텍스트 선택·클릭처럼 대상 노드가 분명할 때 쓴다 */
export function sectionOfNode(node: Node | null): LogSection | null {
  const element =
    node === null
      ? null
      : node.nodeType === Node.ELEMENT_NODE
        ? (node as Element)
        : node.parentElement;

  const holder = element?.closest(`[${SECTION_ATTRIBUTE}]`);
  return (holder?.getAttribute(SECTION_ATTRIBUTE) as LogSection | null) ?? null;
}

/**
 * 화면에서 가장 크게 보이는 섹션. 스크롤처럼 대상 노드가 없을 때 쓴다.
 *
 * 뷰포트 중앙 한 점으로 판정하면 섹션 경계에서 값이 튀어서,
 * 실제로 화면을 많이 차지한 쪽을 고른다.
 */
export function dominantSection(): LogSection | null {
  const viewportHeight = window.innerHeight;
  let best: { id: LogSection; area: number } | null = null;

  for (const element of document.querySelectorAll<HTMLElement>(`[${SECTION_ATTRIBUTE}]`)) {
    const id = element.dataset.logSection as LogSection | undefined;
    if (!id) continue;

    const rect = element.getBoundingClientRect();
    const visible = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);
    if (visible <= 0) continue;

    if (best === null || visible > best.area) {
      best = { id, area: visible };
    }
  }

  return best?.id ?? null;
}

/** 문서 기준 현재 스크롤 위치를 0~100 으로 환산한다 */
export function scrollPercent(): number {
  const doc = document.documentElement;
  const scrollable = doc.scrollHeight - window.innerHeight;
  if (scrollable <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round((window.scrollY / scrollable) * 100)));
}
