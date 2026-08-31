import { useEffect } from 'react';
import { track } from '../lib/logger';
import { regionOfNode } from '../lib/section';

/**
 * 텍스트 드래그 / 복사.
 *
 * 화장품에서 성분은 구매 판단의 상위 요인이고, 사용자는 모르는 성분명을 만나면
 * 그 부분만 긁어서 따로 검색한다. 그래서 "어느 문장을 긁었는가" 는
 * 클릭보다 관심 대상을 정확히 짚어주는 신호다.
 * 복사(text_copy)는 페이지 밖으로 들고 나갈 만큼 관심이 있었다는 뜻이라 더 세게 본다.
 *
 * 긁은 구간의 텍스트를 남긴다. 상품 페이지에 이미 노출된 문구이고,
 * 다만 **긁은 원문은 남기지 않는다** (데이터 계약).
 * 어느 구역에서 얼마나 긴 문장을 긁었는지까지만 남긴다.
 * 사용자가 입력한 값도 남기지 않는다 (입력 요소는 아래에서 제외한다).
 */

/** 이보다 짧으면 드래그가 아니라 클릭하다 미끄러진 것으로 본다 */
const MIN_LENGTH = 2;


/** 드래그 도중 selectionchange 가 연달아 오므로 손을 뗀 뒤로 미룬다 */
const SETTLE_MS = 350;

function isFormField(node: Node | null): boolean {
  const element =
    node === null
      ? null
      : node.nodeType === Node.ELEMENT_NODE
        ? (node as Element)
        : node.parentElement;

  return element?.closest('input, textarea, [contenteditable="true"]') != null;
}

function readSelection(): { text: string; anchor: Node | null } | null {
  const selection = window.getSelection();
  if (selection === null || selection.isCollapsed) return null;

  const text = selection.toString().trim().replace(/\s+/g, ' ');
  if (text.length < MIN_LENGTH) return null;

  const anchor = selection.anchorNode;
  if (isFormField(anchor)) return null;

  return { text, anchor };
}

export function useTextSelection(pageViewKey: string) {
  useEffect(() => {
    let settleTimer: number | undefined;
    /** 같은 선택이 유지되는 동안 반복해서 남기지 않는다 */
    let lastReported = '';

    const emit = (eventName: 'text_selection' | 'text_copy') => {
      const current = readSelection();
      if (current === null) return;

      if (eventName === 'text_selection' && current.text === lastReported) return;
      lastReported = current.text;

      /*
       * 원문은 싣지 않는다 (데이터 계약).
       * 어느 구역에서 얼마나 긴 문장을 긁었는지까지만 남긴다.
       * 대시보드의 "긁어간 문장" 화면은 이 값으로는 만들 수 없다.
       */
      track(eventName, {
        ...regionOfNode(current.anchor),
        text_length: current.text.length,
      });
    };

    const onSelectionChange = () => {
      if (settleTimer !== undefined) window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        settleTimer = undefined;
        emit('text_selection');
      }, SETTLE_MS);
    };

    const onCopy = () => emit('text_copy');

    document.addEventListener('selectionchange', onSelectionChange);
    document.addEventListener('copy', onCopy);

    return () => {
      document.removeEventListener('selectionchange', onSelectionChange);
      document.removeEventListener('copy', onCopy);
      if (settleTimer !== undefined) window.clearTimeout(settleTimer);
    };
  }, [pageViewKey]);
}
