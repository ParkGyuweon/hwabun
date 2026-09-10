import { useState } from 'react';
import { effectivePrice, hasDiscount } from '../lib/discount';
import EmptyState from '../components/common/EmptyState';
import PurchaseSurvey from '../components/cart/PurchaseSurvey';
import { IMAGE_WIDTH_SWATCH, sizedImage } from '../lib/image';
import { formatPrice } from '../lib/format';
import { useSectionView } from '../hooks/useSectionView';
import { useTextSelection } from '../hooks/useTextSelection';
import { useInteractionSignals } from '../hooks/useInteractionSignals';
import { useExitSummary } from '../hooks/useExitSummary';
import type { CartItem } from '../types/cart';
import type { PlacedOrder } from '../lib/checkout';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface CartPageProps {
  items: CartItem[];
  onQuantityChange: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  /** 행을 누르면 그 상품 상세로 */
  onSelectProduct: (productId: string) => void;
  /** 비었을 때 목록으로 돌려보낸다 */
  onContinue: () => void;
  /** 주문 확인 단계에 들어섰다. begin_checkout 은 App 이 남긴다 */
  onBeginCheckout: () => void;
  /** 확인 화면에서 되돌아왔다. 이벤트는 없다 — 취소는 화면 상태일 뿐이다 */
  onCancelCheckout: () => void;
  /** 주문 완료. purchase 는 App 이 남기고 order_id 도 App 이 만든다 */
  onPlaceOrder: () => void;
  /** 완료 화면이 떠 있으면 그 주문. 없으면 null */
  order: PlacedOrder | null;
  onSurveySubmit: (reasons: string[]) => void;
  onSurveySkip: () => void;
}

/**
 * 장바구니.
 *
 * 구매 기능이 아니라 **신호 수집이 목적**이다. 조사(7-2)에서 지적된
 * 가장 명확한 상품 특정 부정 신호 `remove_from_cart` 가 여기서 나온다.
 * 그래서 결제 흐름 없이 담은 목록·수량 조절·삭제만 둔다.
 *
 * 이벤트는 담당 핸들러(App)가 남긴다. 화면은 콜백만 부른다.
 */
export default function CartPage({
  items,
  onQuantityChange,
  onRemove,
  onSelectProduct,
  onContinue,
  onBeginCheckout,
  onCancelCheckout,
  onPlaceOrder,
  order,
  onSurveySubmit,
  onSurveySkip,
}: CartPageProps) {
  /**
   * 주문 확인 단계에 있는지. 화면 상태라 여기서 들고 있는다.
   *
   * 담기 다음에 문턱을 하나 두는 이유는 `begin_checkout` 과 `purchase` 가 같은 순간에
   * 나가면 그 사이의 전환율이 항상 100% 라 아무 말도 안 하기 때문이다.
   * 확인까지 갔다가 되돌아간 사람이 잡혀야 문턱이 의미가 있다.
   */
  const [confirming, setConfirming] = useState(false);
  useSectionView('cart');
  useTextSelection('cart');
  useInteractionSignals('cart');
  useExitSummary('cart');

  // 화면은 할인가 합계. 정가 합계는 이벤트만 쓴다 (lib/checkout.ts orderTotals)
  const subtotal = items.reduce((sum, item) => sum + effectivePrice(item) * item.quantity, 0);
  const listTotal = items.reduce((sum, item) => sum + item.price_usd * item.quantity, 0);
  const saved = listTotal - subtotal;
  const count = items.reduce((sum, item) => sum + item.quantity, 0);

  if (order) {
    return (
      <main className="page cart">
        <section className="done" data-log-section="order_complete">
          <p className="done__eyebrow">주문 완료</p>
          <h1 className="done__title">주문이 접수되었습니다</h1>
          <p className="done__meta">
            주문번호 {order.orderId.slice(0, 8)} · 상품 {order.count}개 ·{' '}
            {formatPrice(order.paid)}
          </p>
          {/* 없는 기능을 있는 것처럼 두지 않는다. 여기서 멈추는 것이 이 쇼핑몰의 경계다 */}
          <p className="done__note">
            결제 연동이 없는 테스트 주문입니다. 카드 정보를 받지 않고 실제로 청구되지 않습니다.
          </p>

          <PurchaseSurvey onSubmit={onSurveySubmit} onSkip={onSurveySkip} />

          <button type="button" className="cart__continue" onClick={onContinue}>
            쇼핑 계속하기
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="page cart">
      <h1 className="cart__title">
        장바구니 <span className="cart__count">{count}개</span>
      </h1>

      {items.length === 0 ? (
        <div className="cart__empty">
          <EmptyState message="장바구니가 비어 있습니다." />
          <button type="button" className="cart__continue" onClick={onContinue}>
            쇼핑 계속하기
          </button>
        </div>
      ) : (
        <div className="cart__layout" data-log-section="cart_items">
          <ul className="cart__list">
            {items.map((item) => (
              <li
                key={`${item.product_id}:${item.sku_id ?? '-'}`}
                className="cart__item"
                data-log-content="cart_item"
                data-log-ref={item.product_id}
              >
                <button
                  type="button"
                  className="cart__thumb"
                  aria-label={`${item.product_name} 상세 보기`}
                  onClick={() => onSelectProduct(item.product_id)}
                >
                  <img
                    src={sizedImage(item.image_url, IMAGE_WIDTH_SWATCH) ?? PLACEHOLDER}
                    alt=""
                    aria-hidden="true"
                  />
                </button>

                <div className="cart__info">
                  <p className="cart__brand">{item.brand_name}</p>
                  <button
                    type="button"
                    className="cart__name"
                    onClick={() => onSelectProduct(item.product_id)}
                  >
                    {item.product_name}
                  </button>
                  {item.variant_label ? (
                    <p className="cart__variant">{item.variant_label}</p>
                  ) : null}
                </div>

                <div className="cart__controls">
                  <label className="cart__qty">
                    수량
                    <select
                      value={item.quantity}
                      onChange={(event) => onQuantityChange(item, Number(event.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>

                  <strong className="cart__price">
                    {formatPrice(effectivePrice(item) * item.quantity)}
                    {hasDiscount(item) ? <s className="cart__was">{formatPrice(item.price_usd * item.quantity)}</s> : null}
                  </strong>

                  <button
                    type="button"
                    className="cart__remove"
                    data-log-action="remove_from_cart"
                    onClick={() => onRemove(item)}
                  >
                    삭제
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <aside className="cart__summary">
            <h2>주문 요약</h2>
            <dl>
              <div>
                <dt>상품 {count}개</dt>
                <dd>{formatPrice(listTotal)}</dd>
              </div>
              {saved > 0 ? (
                <div className="cart__discount">
                  <dt>할인</dt>
                  <dd>-{formatPrice(saved)}</dd>
                </div>
              ) : null}
              <div>
                <dt>배송</dt>
                <dd>무료</dd>
              </div>
              <div className="cart__total">
                <dt>합계</dt>
                <dd>{formatPrice(subtotal)}</dd>
              </div>
            </dl>
            {confirming ? (
              <div className="cart__confirm">
                <p className="cart__confirm-title">이 주문으로 진행할까요?</p>
                <p className="cart__confirm-meta">
                  상품 {count}개 · {formatPrice(subtotal)}
                </p>
                <button
                  type="button"
                  className="btn btn--primary cart__order"
                  data-log-action="place_order"
                  onClick={() => {
                    setConfirming(false);
                    onPlaceOrder();
                  }}
                >
                  주문 완료
                </button>
                <button
                  type="button"
                  className="cart__back"
                  data-log-action="cancel_checkout"
                  onClick={() => {
                    setConfirming(false);
                    onCancelCheckout();
                  }}
                >
                  다시 담기로
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn--primary cart__order"
                data-log-action="begin_checkout"
                onClick={() => {
                  setConfirming(true);
                  onBeginCheckout();
                }}
              >
                주문하기
              </button>
            )}
            {/* 결제 연동은 없다. 없는 기능을 있는 것처럼 두면 dead_click 만 쌓인다 */}
            <p className="cart__note">
              결제 연동이 없는 테스트 주문입니다. 카드 정보를 받지 않습니다.
            </p>
          </aside>
        </div>
      )}
    </main>
  );
}
