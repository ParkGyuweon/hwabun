import type { CartItem } from '../types/cart';
import { effectivePrice } from './discount';

/**
 * 테스트 주문.
 *
 * 결제 연동은 없다. PG 가맹점 계약도, 결제 개발자 계정도, 카드 정보를 받는 화면도 없다.
 * 이 흐름의 목적은 **전환 신호**다 — 담기까지만 있는 로그로는 "담고 안 산 사람" 과
 * "산 사람" 을 구분할 수 없어서 관심도 점수가 그 둘을 같은 무게로 센다.
 *
 * ## order_id 를 프론트가 만드는 이유
 *
 * 여기서 `order_id` 가 하는 일은 조인 키 하나다. `purchase` 와
 * `purchase_reason_select` 를 묶고, 마트에서 `order_id + product_id` 로
 * `purchase_fact` 를 만든다. 결제도, 주문 테이블도, 고객에게 보여주는 번호도 아니다.
 *
 * 그런데 프론트는 이미 `session_id` · `page_view_id` · `event_id` 를 같은 방식으로
 * 만들어 싣고 있고 파이프라인이 그걸 조인 키로 쓴다. `order_id` 만 서버에 다녀와야 할
 * 이유가 없다. 계약도 `order_id: string` 이라고만 하지 누가 발급하는지는 안 정한다.
 *
 * 서버 발급으로 옮겨야 하는 선은 분명하다.
 *
 *   주문 번호를 고객에게 보여주거나 환불·문의 조회에 쓸 때
 *   서버에서 중복 주문을 막아야 할 때
 *   분석 결과를 실제 주문 테이블과 대조해야 할 때 (두 곳의 id 가 같아야 한다)
 *
 * 그때는 이 파일의 `createOrderId` 자리에서 API 를 부르면 되고 이벤트 계약은 안 바뀐다.
 */

export interface OrderItem {
  product_id: string;
  quantity: number;
  /** 계약 §6 의 items[] 필수 child. DW 의 item_revenue 는 unit_price x quantity 로 파생 */
  unit_price: number;
  sku_id?: string;
}

export interface PlacedOrder {
  orderId: string;
  items: OrderItem[];
  /** 상품 종류가 아니라 수량 합 */
  count: number;
  total: number;
  /** 할인 적용 합계. 화면 표시용 */
  paid: number;
  /** 서버 주문(PAID)인지, 로컬 테스트 주문인지. 화면에 그대로 밝힌다 */
  mode: 'backend' | 'local';
  /** 로컬로 물러난 이유. 서버 주문이면 null */
  note: string | null;
}

/**
 * 주문 번호.
 *
 * **주문당 한 번만 부른다.** 버튼을 두 번 누를 때마다 새로 만들면 한 주문이 두 건으로
 * 샌다 — 이건 서버 발급이어도 똑같아서, 막는 자리는 발급 주체가 아니라 호출부다.
 */
export function createOrderId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `order-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export function toOrderItems(items: CartItem[]): OrderItem[] {
  return items.map((item) => ({
    product_id: item.product_id,
    quantity: item.quantity,
    unit_price: item.price_usd,
    ...(item.sku_id ? { sku_id: item.sku_id } : {}),
  }));
}

/**
 * `total` 은 정가 합계다. 이벤트의 cart_value·order_value 가 이 값을 쓰고, 그 뜻은 바뀌지 않는다.
 * `paid` 는 할인 적용 합계로 화면에 보여주고 이벤트에는 paid_value 로 덧붙인다 (lib/discount.ts 원칙).
 */
export function orderTotals(items: CartItem[]): { count: number; total: number; paid: number } {
  return {
    count: items.reduce((sum, item) => sum + item.quantity, 0),
    total: items.reduce((sum, item) => sum + item.price_usd * item.quantity, 0),
    paid: items.reduce((sum, item) => sum + effectivePrice(item) * item.quantity, 0),
  };
}

/**
 * 구매 이유 열 가지.
 *
 * 왜 샀는지는 행동 로그가 답하지 못하는 유일한 질문이다. 성분을 오래 봤다는 것과
 * 성분 때문에 샀다는 것은 다르고, 전자로 후자를 추론하면 추천이 그쪽으로 쏠린다.
 *
 * 자유 입력은 받지 않는다. 원문을 저장하지 않는 것이 이 프로젝트의 원칙이고,
 * 분류만 남길 거면 애초에 고르게 하는 편이 낫다.
 * `restock` 은 재구매의 선언 신호라 행동으로 잡은 재구매와 교차 검증에 쓴다.
 */
export const PURCHASE_REASONS: Array<{ key: string; label: string }> = [
  { key: 'ingredient', label: '성분이 마음에 들어서' },
  { key: 'skin_fit', label: '내 피부 타입·톤에 맞아서' },
  { key: 'reviews', label: '리뷰가 좋아서' },
  { key: 'review_same_skin', label: '나와 같은 피부 리뷰를 보고' },
  { key: 'price', label: '가격이 맞아서' },
  { key: 'brand_trust', label: '이 브랜드를 믿어서' },
  { key: 'texture_finish', label: '제형·마감이 좋아서' },
  { key: 'clean_claim', label: '무향·비건 등 성분 배제 조건 때문에' },
  { key: 'recommendation', label: '추천을 받아서' },
  { key: 'restock', label: '쓰던 걸 다시 사서' },
];

/** 한 번에 고를 수 있는 최대 개수. 다 고르면 아무 말도 안 하는 것과 같다 */
export const MAX_REASONS = 2;
