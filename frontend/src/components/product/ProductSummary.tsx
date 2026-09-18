import { useState } from 'react';
import { variantIdOf } from '../../lib/discount';
import PriceTag from './PriceTag';
import { unitMoneyProps } from '../../lib/checkout';
import StarRating from '../common/StarRating';
import VariantPicker from './VariantPicker';
import { formatCount } from '../../lib/format';
import { track } from '../../lib/logger';
import { setWished, useWished } from '../../lib/wishlist';
import { displayReviewCount, useReviewCounts } from '../../lib/reviewStore';
import type { Product, ProductVariant } from '../../types/product';
import { MAX_CART_QUANTITY } from '../../types/cart';
import type { CartItem } from '../../types/cart';

interface ProductSummaryProps {
  product: Product;
  /** 선택된 옵션의 SKU. 옵션이 없는 상품이면 null */
  selectedSkuId: string | null;
  onVariantSelect: (variant: ProductVariant) => void;
  /** 실제 장바구니에 넣는다. 로그는 여기서 남기고 담기는 App 이 한다 */
  onAddToCart: (item: CartItem) => void;
  /**
   * 장바구니를 거치지 않고 이 상품 하나만 주문한다. 로그인 판단·주문은 App 이 한다.
   * `addToCartProps` 는 App 이 로그인 확인을 **통과한 뒤에** 남길 `add_to_cart` 의 속성이다 — 여기서 먼저 찍으면
   * 로그인 모달만 보고 끝난 클릭이 장바구니 전환으로 집계된다 (리뷰 !286).
   */
  onBuyNow: (item: CartItem, addToCartProps: Record<string, unknown>) => void;
  /** 결제창이 떠 있거나 서버 확인 중 */
  buying: boolean;
  /** 리뷰 섹션으로 스크롤 이동 */
  onReviewLinkClick: () => void;
}

/**
 * 세포라 상세 페이지 우측 상단의 구매 정보 블록.
 *
 * 찜과 장바구니는 관심 강도가 가장 높은 신호라 여기 트리거가 몰려 있다.
 */
export default function ProductSummary({
  product,
  selectedSkuId,
  onVariantSelect,
  onAddToCart,
  onBuyNow,
  buying,
  onReviewLinkClick,
}: ProductSummaryProps) {
  const [quantity, setQuantity] = useState(1);
  // 세션 동안 기억한다 — 찜 뒤 뒤로 갔다 와도 하트가 켜져 있어야 한다 (lib/wishlist)
  const loved = useWished(product.product_id);
  // 리뷰 절이 실제로 그리는 건수와 같은 숫자여야 한다 (lib/reviewStore)
  const reviewCount = displayReviewCount(product.product_id, product.review_count, useReviewCounts());
  const [addedAt, setAddedAt] = useState<number | null>(null);

  const changeQuantity = (next: number) => {
    const clamped = Math.min(MAX_CART_QUANTITY, Math.max(1, next));
    if (clamped === quantity) return;
    setQuantity(clamped);
    track('quantity_change', { product_id: product.product_id, quantity: clamped });
  };

  /** 마지막 찜 동작. 담기와 같은 자리에 같은 방식으로 알린다 — 눌렀는데 아무 말 없으면 dead_click 으로 보인다 */
  const [wishNotice, setWishNotice] = useState<'add' | 'remove' | null>(null);

  const toggleWishlist = () => {
    const next = !loved;
    setWished(product.product_id, next);
    setWishNotice(next ? 'add' : 'remove');
    track('wishlist_toggle', { product_id: product.product_id, action: next ? 'add' : 'remove' });
  };

  /** 지금 화면 상태(옵션·수량)로 만든 장바구니 품목. 담기와 바로 구매가 같은 값을 쓴다 */
  const cartItem = (): CartItem => ({
    product_id: product.product_id,
    sku_id: selectedSkuId,
    variant_label: product.variants.find((v) => v.sku_id === selectedSkuId)?.label ?? null,
    brand_name: product.brand_name,
    product_name: product.product_name,
    image_url: product.image_url,
    price_usd: product.price_usd,
    sale_price_usd: product.sale_price_usd ?? null,
    variant_id: variantIdOf(product, selectedSkuId),
    quantity,
  });

  /** 담기 이벤트 속성. 담기 버튼과 바로 구매가 같은 모양으로 남긴다 — `entry_source` 만 다르다 */
  const addToCartProps = (entrySource?: string): Record<string, unknown> => ({
    product_id: product.product_id,
    sku_id: selectedSkuId,
    quantity,
    // 원화 정가 unit_price + currency:'KRW' (계약 §4.5). 할인은 sale_price·discount_rate 로 덧붙는다
    ...unitMoneyProps(product),
    ...(entrySource ? { entry_source: entrySource } : {}),
  });

  const addToCart = () => {
    // 실패했을 때 성공 로그가 나가지 않도록, 장바구니 API 가 붙으면 성공 응답 후에만 track 한다
    setAddedAt(Date.now());
    track('add_to_cart', addToCartProps());
    onAddToCart(cartItem());
  };

  /**
   * 바로 구매 — 장바구니를 거치지 않고 이 상품 하나만 주문한다.
   *
   * **`add_to_cart` 를 먼저 남긴다. 장바구니에 담지는 않는다** (AI 파트 확정 2026-09-16).
   * 단, 찍는 자리는 여기가 아니라 App 이다 — 비로그인이면 App 이 로그인 모달만 열고 끝나는데, 그 클릭까지
   * 담기로 남기면 `add_to_cart_sessions` 와 장바구니 이탈률이 부풀어 오른다 (리뷰 !286). 속성만 만들어 넘긴다.
   *
   * 처음에는 "담은 적이 없으니 담기 이벤트도 없다" 로 두었는데, 그러면 퍼널이 깨진다.
   * `funnel_daily_kpi`(dw-schema §4.5)의 `cart_to_purchase_rate` 와 `dropoff_after_cart_rate` 가
   * `add_to_cart_sessions` 를 분모로 쓰기 때문에, 담기 없이 구매만 있는 세션이 생기면 **분자가 분모를
   * 넘는다** — Jira 277 에서 담기율이 1.0 을 넘었던 것과 같은 종류의 결함이다.
   *
   * 퍼널상 바로 구매는 담기 단계를 **건너뛴 것이 아니라 한 번에 통과한 것**이라, 단계를 비우는 쪽이
   * 사실과 더 멀다. 새 이벤트 이름을 만들지 않은 것도 같은 이유다 — 계약에 등록되기 전까지는
   * `unregistered_event` 로 거절되고, 등록해도 기존 퍼널 마트가 그 이름을 모른다.
   *
   * 구분은 `entry_source: 'buy_now'` 로 한다. `add_to_cart` 의 선택 속성으로 이미 계약에 있고
   * (event-properties-schema §4), 퀵룩이 `'quick_look'` 으로 같은 자리를 쓰고 있다.
   * 다만 **값 `buy_now` 는 §3.3 enum 에 아직 없다** — 데이터 파트에 추가 요청해 둔 상태다.
   */
  const buyNow = () => {
    onBuyNow(cartItem(), addToCartProps('buy_now'));
  };

  return (
    <div className="summary">
      <p className="summary__brand">{product.brand_name}</p>
      <h1 className="summary__name">{product.product_name}</h1>

      {product.rating !== null && reviewCount !== null ? (
        <div className="summary__rating">
          <StarRating value={product.rating} />
          <span className="summary__rating-value">{product.rating.toFixed(2)}</span>
          <button
            type="button"
            className="link-button"
            data-log-action="jump_to_reviews"
            onClick={onReviewLinkClick}
          >
            리뷰 {formatCount(reviewCount)}건
          </button>
        </div>
      ) : (
        <p className="summary__rating summary__rating--empty">아직 등록된 평점이 없습니다</p>
      )}

      <div className="summary__price" data-log-content="price">
        <PriceTag product={product} size="md" showLabel />
        {/* size 는 자유 텍스트라 파싱하지 않고 그대로 노출한다 */}
        {product.size ? <span className="summary__size">{product.size}</span> : null}
      </div>

      <VariantPicker
        productId={product.product_id}
        variants={product.variants}
        selectedSkuId={selectedSkuId}
        onSelect={onVariantSelect}
      />

      <div className="summary__actions" data-log-content="cta">
        <div className="qty" role="group" aria-label="수량 선택">
          <button
            type="button"
            data-log-action="quantity_decrease"
            aria-label="수량 감소"
            onClick={() => changeQuantity(quantity - 1)}
          >
            −
          </button>
          <span aria-live="polite">{quantity}</span>
          <button
            type="button"
            data-log-action="quantity_increase"
            aria-label="수량 증가"
            onClick={() => changeQuantity(quantity + 1)}
          >
            +
          </button>
        </div>

        <button type="button" className="btn btn--secondary" data-log-action="add_to_cart" onClick={addToCart}>
          Add to Basket
        </button>

        {/*
          바로 구매. 비로그인이어도 **버튼은 보인다** — 누르면 App 이 로그인 모달을 띄운다.
          숨기면 "이 가게는 바로 구매가 없다" 로 읽히고, 로그인해도 뭐가 달라지는지 알 수 없다.
        */}
        <button
          type="button"
          className="btn btn--primary"
          data-log-action="buy_now"
          disabled={buying}
          onClick={buyNow}
        >
          {buying ? '주문 진행 중…' : '바로 구매'}
        </button>

        <button
          type="button"
          className={`btn btn--icon${loved ? ' is-active' : ''}`}
          aria-pressed={loved}
          aria-label={loved ? '찜 해제' : '찜하기'}
          data-log-action="wishlist_toggle"
          onClick={toggleWishlist}
        >
          {loved ? '♥' : '♡'}
        </button>
      </div>

      {wishNotice !== null ? (
        <p className="summary__toast summary__toast--wish" role="status">
          {wishNotice === 'add' ? '찜 목록에 담았습니다 ♥' : '찜을 해제했습니다'}
        </p>
      ) : null}
      {addedAt !== null ? (
        <p className="summary__toast" role="status">
          장바구니에 담았습니다 · 수량 {quantity}
        </p>
      ) : null}

      <p className="summary__meta">Item {product.product_id}</p>
    </div>
  );
}
