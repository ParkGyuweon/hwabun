/**
 * 고객 피드백 — 참여 루프 ①(남김) → ②(사장이 분류별로 본다) → ③(고친다) → ④(반영됐다고 돌려준다).
 *
 * 리뷰(평점 + 구매자만)와 다르다. 피드백은 **제품의 어느 부분** 에 대한 의견인지가 핵심이라
 * 분류(aspect)를 먼저 고르게 한다. 사장님은 "향 3건, 용기 1건" 처럼 나눠서 받는다.
 *
 * 서버가 생기면 백엔드 Review·Feedback API(Jira 146)로 옮긴다. 그때까지 localStorage 공유.
 * 로그에는 원문을 싣지 않는다 (behavior-log-design "일부러 안 남기는 것").
 */

/** 사장님 입장에서 고칠 수 있는 단위로 나눈다. 성분·제형·향·용기는 각각 다른 담당(처방·포장)이다 */
export type FeedbackAspect =
  | 'scent'
  | 'packaging'
  | 'texture'
  | 'ingredient'
  | 'effect'
  | 'usage'
  | 'price'
  | 'other';

export const FEEDBACK_ASPECTS: ReadonlyArray<{ key: FeedbackAspect; label: string; hint: string }> = [
  { key: 'scent', label: '향', hint: '강하다 · 인공적이다 · 무향이면 좋겠다' },
  { key: 'packaging', label: '용기', hint: '펌프 · 스포이드 · 뚜껑 · 용량 · 위생' },
  { key: 'texture', label: '제형', hint: '끈적임 · 흡수 · 밀림 · 백탁' },
  { key: 'ingredient', label: '성분', hint: '자극 · 빼 줬으면 하는 성분 · 함량' },
  { key: 'effect', label: '효과', hint: '기대와 달랐다 · 이 부분은 좋았다' },
  { key: 'usage', label: '사용법', hint: '설명이 부족하다 · 순서를 모르겠다' },
  { key: 'price', label: '가격·구성', hint: '부담 · 소용량이 있었으면 · 세트' },
  { key: 'other', label: '기타', hint: '' },
];

export type FeedbackStatus = 'new' | 'read' | 'reflected';

export interface Feedback {
  feedback_id: string;
  product_id: string;
  brand_name: string;
  /** 없으면 비로그인 방문자 */
  persona_id: string | null;
  aspects: FeedbackAspect[];
  /** 자유 텍스트. 서버로만 가고 로그에는 안 싣는다 */
  text: string;
  /** 결제 완료 사용자인지. 지금은 장바구니 담기 여부로 대신하지 않고 false 고정 — 백엔드 PAID 연결 후 */
  purchased: boolean;
  created_at: string;
  status: FeedbackStatus;
  /** 사장님이 반영하며 남긴 한 줄. 소비자에게 그대로 보인다 (루프 ④) */
  reply: string | null;
  replied_at: string | null;
}
