import EmptyState from '../components/common/EmptyState';
import { IMAGE_WIDTH_SWATCH, sizedImage } from '../lib/image';
import { formatPrice } from '../lib/format';
import { useSectionView } from '../hooks/useSectionView';
import { useTextSelection } from '../hooks/useTextSelection';
import { useInteractionSignals } from '../hooks/useInteractionSignals';
import { useExitSummary } from '../hooks/useExitSummary';
import type { CartItem } from '../types/cart';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface CartPageProps {
  items: CartItem[];
  onQuantityChange: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  /** 행을 누르면 그 상품 상세로 */
  onSelectProduct: (productId: string) => void;
  /** 비었을 때 목록으로 돌려보낸다 */
  onContinue: () => void;
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
}: CartPageProps) {
  useSectionView('cart');
  useTextSelection('cart');
  useInteractionSignals('cart');
  useExitSummary('cart');

  const subtotal = items.reduce((sum, item) => sum + item.price_usd * item.quantity, 0);
  const count = items.reduce((sum, item) => sum + item.quantity, 0);

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
                    {formatPrice(item.price_usd * item.quantity)}
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
                <dd>{formatPrice(subtotal)}</dd>
              </div>
              <div>
                <dt>배송</dt>
                <dd>무료</dd>
              </div>
              <div className="cart__total">
                <dt>합계</dt>
                <dd>{formatPrice(subtotal)}</dd>
              </div>
            </dl>
            {/* 결제는 프로젝트 범위 밖이다. 없는 기능을 있는 것처럼 두면 dead_click 만 쌓인다 */}
            <p className="cart__note">결제는 이 테스트 쇼핑몰의 범위 밖입니다.</p>
          </aside>
        </div>
      )}
    </main>
  );
}
