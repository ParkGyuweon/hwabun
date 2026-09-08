/**
 * 대시보드 브랜드 스코프 — 결정 A (dashboard-redesign-spec.md §0-2, 2026-09-08).
 *
 * 행동 로그(PC 9,900명)와 리뷰(2,000건)는 세포라 카탈로그 55개 브랜드에만 있고,
 * 고객 피드백(99건)과 상품 등록은 시연 브랜드 SSAFY Beauty 에만 있다. 한 브랜드로 전 화면을
 * 실측으로 채울 수 없어서 스코프를 둘로 나눈다. 화면 상단에 어느 쪽 데이터인지 항상 적는다.
 *
 *   행동·리뷰  BEHAVIOR_BRAND  세포라 카탈로그의 실제 브랜드. 상품 16종·리뷰 160건으로 가장 크다
 *   피드백·등록 FEEDBACK_BRAND  SSAFY Beauty (mocks/products.ts DEMO_BRAND)
 *
 * 생성기가 SB 상품을 만들게 되면(결정 B) BEHAVIOR_BRAND 만 DEMO_BRAND 로 바꾸면 된다.
 */
import { DEMO_BRAND } from '../../mocks/products';

export const BEHAVIOR_BRAND = 'Drunk Elephant';
export const FEEDBACK_BRAND = DEMO_BRAND;

export type ScopeKind = 'behavior' | 'feedback';

export const SCOPE_LABEL: Record<ScopeKind, { brand: string; what: string; source: string }> = {
  behavior: {
    brand: BEHAVIOR_BRAND,
    what: '행동·리뷰 데이터',
    source: '세포라 카탈로그 · 페르소나 9,900명 로그 · 리뷰 160건',
  },
  feedback: {
    brand: FEEDBACK_BRAND,
    what: '피드백·상품 등록',
    source: '시연 브랜드 · 피드백 30건 분류',
  },
};
