/**
 * 대시보드 브랜드 스코프 — 결정 A (dashboard-redesign-spec.md §0-2, 2026-09-08).
 *
 * 행동 로그(PC 9,900명)와 리뷰(2,000건)는 세포라 카탈로그 55개 브랜드에만 있고,
 * 고객 피드백(99건)과 상품 등록은 시연 브랜드 SSAFY Beauty 에만 있다. 한 브랜드로 전 화면을
 * 실측으로 채울 수 없어서 스코프를 둘로 나눈다. 화면 상단에 어느 쪽 데이터인지 항상 적는다.
 *
 *   행동·리뷰  마트를 로그인한 brandId 로 조회한다. 라벨도 로그인한 브랜드 이름이다
 *   피드백·등록 FEEDBACK_BRAND  SSAFY Beauty (mocks/products.ts DEMO_BRAND)
 *
 * 2026-09-18: 행동 스코프의 고정 브랜드(`BEHAVIOR_BRAND` = Drunk Elephant)를 없앴다. 대시보드가 적는 브랜드는
 * 언제나 로그인한 브랜드다 — 값이 없으면 남의 브랜드로 물러나지 않고 없다고 적는다.
 */
import { DEMO_BRAND } from '../../mocks/products';

export const FEEDBACK_BRAND = DEMO_BRAND;

export type ScopeKind = 'behavior' | 'feedback';

export const SCOPE_LABEL: Record<ScopeKind, { brand: string; what: string; source: string }> = {
  behavior: {
    brand: '',
    what: '행동 데이터',
    source: '행동 마트 · 로그인한 브랜드',
  },
  feedback: {
    brand: FEEDBACK_BRAND,
    what: '피드백·상품 등록',
    source: '시연 브랜드 · 피드백 30건 분류',
  },
};
