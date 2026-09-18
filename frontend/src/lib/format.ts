import type { Review } from '../types/review';
import type { SkinType } from '../types/product';

import { toKrw } from './localize';

/**
 * 가격은 원화로 **표시만** 한다. 데이터는 `price_usd` 그대로다.
 * 환율·반올림은 번역 데이터(products-ko.json 의 price_krw)와 같은 식이라 표시가 어긋나지 않는다.
 * 이벤트 금액도 2026-09-17 부터 같은 식으로 원화다 (lib/checkout unitMoneyProps · orderTotalsKrw, 계약 §4.5).
 */
export function formatPrice(usd: number): string {
  return `${toKrw(usd).toLocaleString('ko-KR')}원`;
}

export function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${y}.${m}.${d}`;
}

const SKIN_TYPE_LABEL: Record<SkinType, string> = {
  combination: '복합성',
  dry: '건성',
  normal: '중성',
  oily: '지성',
};

export function skinTypeLabel(value: string): string {
  return SKIN_TYPE_LABEL[value as SkinType] ?? value;
}

/**
 * skin_tone / eye_color / hair_color 는 lightMedium 같은 camelCase 와
 * Grey/gray 처럼 표기가 섞여 있다. 정규화 전이므로 표시용으로만 다듬는다.
 * (docs/data/README.md - 알려진 데이터 이슈 1번)
 */
export function humanizeAttribute(value: string): string {
  const spaced = value.replace(/([a-z])([A-Z])/g, '$1 $2');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

/**
 * 전성분 구분자. 쉼표 뒤에 **숫자가 바로 오면 성분 이름 안의 위치 번호**다 (`1,2-Hexanediol` · `1,3-Butylene Glycol` ·
 * `2,3-Butanediol`). 목록 구분 쉼표는 뒤에 공백이나 글자가 온다. 그래서 "쉼표 뒤가 숫자가 아닐 때만" 자른다.
 * `Ceramide 3, Cholesterol` 처럼 쉼표 **앞**이 숫자인 경우는 정상 구분이라 그대로 잘린다.
 */
export const INGREDIENT_SEPARATOR = /,(?!\d)/;

/**
 * ingredients 는 형식만 배열이고 원소 하나에 전 성분이 쉼표로 이어붙어 있다.
 * 칩으로 뿌리기 위해 분리한다. 데이터 담당자가 정규화해서 주기 전까지의 임시 처리.
 * 성분 수 세기·함량 위치가중(dashboard/lib/metrics)도 이 함수를 써야 화면과 지표의 성분 개수가 같다.
 */
export function splitIngredients(ingredients: string[]): string[] {
  return ingredients
    .flatMap((block) => block.split(INGREDIENT_SEPARATOR))
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export interface ReviewStats {
  total: number;
  average: number;
  /** 5점 -> 1점 순서의 개수 */
  distribution: number[];
  recommendRate: number | null;
}

export function calcReviewStats(reviews: Review[]): ReviewStats {
  const total = reviews.length;
  if (total === 0) {
    return { total: 0, average: 0, distribution: [0, 0, 0, 0, 0], recommendRate: null };
  }

  const distribution = [5, 4, 3, 2, 1].map(
    (score) => reviews.filter((review) => review.rating === score).length,
  );
  const average = reviews.reduce((sum, review) => sum + review.rating, 0) / total;

  const answered = reviews.filter((review) => review.is_recommended !== null);
  const recommendRate = answered.length
    ? Math.round((answered.filter((review) => review.is_recommended).length / answered.length) * 100)
    : null;

  return { total, average, distribution, recommendRate };
}

/** 리뷰어 피부 타입 파생. 플러그인과 같이 쓰려고 lib/skinTypes.ts 로 옮겼다 — 여기서 다시 내보낸다 */
export { deriveSkinTypesFromReviews } from './skinTypes';
export type { DerivedSkinTypes } from './skinTypes';

/**
 * 조사. 앞말의 받침을 보고 을/를 · 이/가 · 은/는 · 과/와 · 으로/로 를 고른다.
 *
 * 화면 문장에 상품·콘텐츠 이름이 끼어들 때 `${name}을` 처럼 박아 두면 "평점 분포을 손보세요" 가 된다 (2026-09-18 지적).
 * 한글이면 종성으로, 숫자면 읽는 소리로(0·1·3·6·7·8 받침 있음), 그 밖(영문 등)은 받침 없는 쪽으로 간다.
 * 으로/로 는 ㄹ 받침이면 '로' 다.
 */
export function josa(word: string, pair: '을/를' | '이/가' | '은/는' | '과/와' | '으로/로'): string {
  const [withFinal, withoutFinal] = pair.split('/');
  const trimmed = word.replace(/[\s)\]}'"”’·]+$/u, '');
  const last = trimmed.charAt(trimmed.length - 1);
  let hasFinal = false;
  let finalIsRieul = false;
  const code = last.charCodeAt(0);
  if (code >= 0xac00 && code <= 0xd7a3) {
    const jong = (code - 0xac00) % 28;
    hasFinal = jong !== 0;
    finalIsRieul = jong === 8;
  } else if (/[0-9]/.test(last)) {
    hasFinal = '013678'.includes(last);
    finalIsRieul = last === '1' || last === '7' || last === '8';
  }
  if (pair === '으로/로') return `${word}${hasFinal && !finalIsRieul ? withFinal : withoutFinal}`;
  return `${word}${hasFinal ? withFinal : withoutFinal}`;
}
