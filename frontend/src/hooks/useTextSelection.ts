import { useEffect } from 'react';
import { track } from '../lib/logger';
import { regionOfNode } from '../lib/section';
import vocab from '../../../contracts/product-feature-vocab.json';

/**
 * 텍스트 드래그 / 복사.
 *
 * 화장품에서 성분은 구매 판단의 상위 요인이고, 사용자는 모르는 성분명을 만나면
 * 그 부분만 긁어서 따로 검색한다. 그래서 "어느 문장을 긁었는가" 는
 * 클릭보다 관심 대상을 정확히 짚어주는 신호다.
 * 복사(text_copy)는 페이지 밖으로 들고 나갈 만큼 관심이 있었다는 뜻이라 더 세게 본다.
 *
 * **긁은 원문은 남기지 않는다** (데이터 계약).
 * 대신 긁은 구간에 우리 성분 사전의 성분이 들어 있으면 **그 표준 명칭**을 남긴다.
 * 사용자가 친 글자가 아니라 우리가 가진 값이라 원문 저장이 아니다.
 *
 * 사전은 `contracts/product-feature-vocab.json` 을 그대로 쓴다. AI 파트가 상품
 * 벡터를 만들 때 쓰는 것과 같은 사전이라, "이 성분을 긁은 사람" 과 "이 성분이 든
 * 상품" 이 같은 이름으로 조인된다. 프론트가 따로 사전을 만들면 그 조인이 깨진다.
 *
 * 이 값으로 어떤 성분이 설명이 부족한지가 드러난다. 반복해서 긁히는 성분은
 * 상세페이지에서 그 성분을 제대로 설명하지 못하고 있다는 뜻이다.
 *
 * 사용자가 입력한 값도 남기지 않는다 (입력 요소는 아래에서 제외한다).
 */

/** 표준 성분명 → 실제 표기들. 값이 소문자라 비교 전에 본문도 소문자로 만든다 */
const INGREDIENT_SYNONYMS = vocab.ingredient_source.synonyms as Record<string, string[]>;

/**
 * 어느 판 사전으로 맞힌 결과인지 같이 남긴다.
 * 사전이 바뀌면 같은 문장이 다른 성분으로 걸린다. 판을 모르면 과거 로그와
 * 지금 로그를 같은 기준으로 비교할 수 없다.
 */
const VOCAB_VERSION = vocab.version as string;

/**
 * 긁은 문장에 들어 있는 성분을 찾는다.
 * 한 문장에 여러 개가 걸릴 수 있어 전부 남긴다. 없으면 빈 배열이다.
 */
function matchIngredients(text: string): string[] {
  const haystack = text.toLowerCase();
  return Object.entries(INGREDIENT_SYNONYMS)
    .filter(([, aliases]) => aliases.some((alias) => haystack.includes(alias)))
    .map(([standardName]) => standardName);
}

/**
 * 긁은 문장이 어떤 종류의 정보인지 (계약 §3.6 `selection_kind`: ingredient · claim · usage · price · other).
 *
 * 성분은 사전 매칭이 있으면 그것이 우선이다 — 리뷰 문장에서 성분명을 긁어도 성분 관심이다.
 * 나머지는 긁은 자리의 content_kind 로 정한다. 성향 표(contracts/user-trait-weights.json)가 이 값으로
 * 가격(price 1.5/2.0)·고민(claim 1.0)·성분(ingredient 1.5/2.0) 성향을 센다. 값이 없으면 마트는
 * content_kind 폴백 규칙으로만 잡아 usage·other 가 구분되지 않는다.
 */
function selectionKindOf(contentKind: string | null, matchedCount: number): 'ingredient' | 'claim' | 'usage' | 'price' | 'other' {
  if (matchedCount > 0) return 'ingredient';
  switch (contentKind) {
    case 'ingredient_list':
    case 'ingredient_callout':
      return 'ingredient';
    case 'price':
      return 'price';
    case 'clinical_claim':
    case 'highlight_badge':
    case 'what_it_is':
      return 'claim';
    case 'usage_guide':
      return 'usage';
    default:
      return 'other';
  }
}

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

      // 원문 대신 사전에 걸린 성분의 표준 명칭만 싣는다 (데이터 계약)
      const matched = matchIngredients(current.text);
      const region = regionOfNode(current.anchor);

      track(eventName, {
        ...region,
        selection_kind: selectionKindOf(region.content_kind, matched.length),
        text_length: current.text.length,
        matched_ingredients: matched,
        matched_count: matched.length,
        vocab_version: VOCAB_VERSION,
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
