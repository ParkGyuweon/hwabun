import type { LogContentKind, LogSection } from '../types/log';

/**
 * "지금 보고 있는 곳이 어디이고, 거기 무슨 콘텐츠가 있었나" 를 알아내는 유틸.
 *
 * 주목 신호(스크롤 멈춤, 텍스트 드래그, 호버)는 클릭과 달리 발생 지점이 정해져 있지 않다.
 * 픽셀 좌표를 그대로 남기면 레이아웃이 바뀌는 순간 과거 로그를 해석할 수 없게 되므로,
 * 두 가지 의미 값으로 환산해서 남긴다.
 *
 * - `data-log-section`  화면 구조상의 구역 (About the Product, Reviews ...)
 * - `data-log-content`  그 자리에 있던 콘텐츠 종류 (성분 목록, 임상 근거, 사용법 ...)
 *
 * 구역만으로는 부족하다. About the Product 안에는 개요·성분·임상 근거·사용법이
 * 같이 들어 있고 구매 판단에서 하는 역할이 서로 다르다.
 * 콘텐츠 종류를 따로 남겨야 화면 배치를 바꿔도 같은 질문에 답할 수 있다.
 */

const SECTION_ATTRIBUTE = 'data-log-section';
const CONTENT_ATTRIBUTE = 'data-log-content';
/** 콘텐츠 하나를 특정하는 값. 리뷰 ID, SKU, 이미지 번호 등 */
const REF_ATTRIBUTE = 'data-log-ref';

export interface Region {
  section_id: LogSection | null;
  content_kind: LogContentKind | null;
  content_ref: string | null;
}

const EMPTY_REGION: Region = { section_id: null, content_kind: null, content_ref: null };

function toElement(node: Node | null): Element | null {
  if (node === null) return null;
  return node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
}

/** 노드가 속한 구역. 텍스트 선택·클릭처럼 대상 노드가 분명할 때 쓴다 */
export function regionOfNode(node: Node | null): Region {
  const element = toElement(node);
  if (element === null) return EMPTY_REGION;

  const contentHolder = element.closest(`[${CONTENT_ATTRIBUTE}]`);

  return {
    section_id:
      (element.closest(`[${SECTION_ATTRIBUTE}]`)?.getAttribute(SECTION_ATTRIBUTE) as
        | LogSection
        | null) ?? null,
    content_kind:
      (contentHolder?.getAttribute(CONTENT_ATTRIBUTE) as LogContentKind | null) ?? null,
    content_ref: contentHolder?.getAttribute(REF_ATTRIBUTE) ?? null,
  };
}

/** 요소가 화면에 실제로 걸쳐 있는 높이 */
function visibleHeight(element: Element): number {
  const rect = element.getBoundingClientRect();
  return Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0);
}

/**
 * 화면에서 가장 크게 보이는 구역. 스크롤처럼 대상 노드가 없을 때 쓴다.
 *
 * 뷰포트 중앙 한 점으로 판정하면 경계에서 값이 튀어서,
 * 실제로 화면을 많이 차지한 쪽을 고른다.
 */
export function dominantRegion(): Region {
  let bestSection: { id: LogSection; area: number } | null = null;
  let bestContent: { element: Element; area: number } | null = null;

  for (const element of document.querySelectorAll<HTMLElement>(`[${SECTION_ATTRIBUTE}]`)) {
    const id = element.dataset.logSection as LogSection | undefined;
    if (!id) continue;

    const area = visibleHeight(element);
    if (area > 0 && (bestSection === null || area > bestSection.area)) {
      bestSection = { id, area };
    }
  }

  for (const element of document.querySelectorAll<HTMLElement>(`[${CONTENT_ATTRIBUTE}]`)) {
    const area = visibleHeight(element);
    if (area > 0 && (bestContent === null || area > bestContent.area)) {
      bestContent = { element, area };
    }
  }

  return {
    section_id: bestSection?.id ?? null,
    content_kind:
      (bestContent?.element.getAttribute(CONTENT_ATTRIBUTE) as LogContentKind | null) ?? null,
    content_ref: bestContent?.element.getAttribute(REF_ATTRIBUTE) ?? null,
  };
}

/** 화면에 함께 떠 있는 콘텐츠 종류. 한 화면에 여러 개면 귀속이 흐려진다는 것도 정보다 */
export function visibleContentKinds(): LogContentKind[] {
  const kinds = new Set<LogContentKind>();

  for (const element of document.querySelectorAll<HTMLElement>(`[${CONTENT_ATTRIBUTE}]`)) {
    const kind = element.dataset.logContent as LogContentKind | undefined;
    if (kind && visibleHeight(element) > 0) kinds.add(kind);
  }

  return [...kinds];
}

/** 문서 기준 현재 스크롤 위치를 0~100 으로 환산한다 */
export function scrollPercent(): number {
  const doc = document.documentElement;
  const scrollable = doc.scrollHeight - window.innerHeight;
  if (scrollable <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round((window.scrollY / scrollable) * 100)));
}
