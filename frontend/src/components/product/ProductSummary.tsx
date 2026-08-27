import { useState } from 'react';
import StarRating from '../common/StarRating';
import VariantPicker from './VariantPicker';
import { formatCount, formatPrice } from '../../lib/format';
import { track } from '../../lib/logger';
import type { Product, ProductVariant } from '../../types/product';

interface ProductSummaryProps {
  product: Product;
  /** 선택된 옵션의 SKU. 옵션이 없는 상품이면 null */
  selectedSkuId: string | null;
  onVariantSelect: (variant: ProductVariant) => void;
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
  onReviewLinkClick,
}: ProductSummaryProps) {
  const [quantity, setQuantity] = useState(1);
  const [loved, setLoved] = useState(false);
  const [addedAt, setAddedAt] = useState<number | null>(null);

  const changeQuantity = (next: number) => {
    const clamped = Math.min(99, Math.max(1, next));
    if (clamped === quantity) return;
    setQuantity(clamped);
    track('quantity_change', { product_id: product.product_id, quantity: clamped });
  };

  const toggleWishlist = () => {
    const next = !loved;
    setLoved(next);
    track('wishlist_toggle', { product_id: product.product_id, action: next ? 'add' : 'remove' });
  };

  const addToCart = () => {
    // 실패했을 때 성공 로그가 나가지 않도록, 장바구니 API 가 붙으면 성공 응답 후에만 track 한다
    setAddedAt(Date.now());
    track('add_to_cart', {
      product_id: product.product_id,
      sku_id: selectedSkuId,
      quantity,
      price_usd: product.price_usd,
    });
  };

  return (
    <div className="summary">
      <p className="summary__brand">{product.brand_name}</p>
      <h1 className="summary__name">{product.product_name}</h1>

      {product.rating !== null && product.review_count !== null ? (
        <div className="summary__rating">
          <StarRating value={product.rating} />
          <span className="summary__rating-value">{product.rating.toFixed(2)}</span>
          <button
            type="button"
            className="link-button"
            data-log-action="jump_to_reviews"
            onClick={onReviewLinkClick}
          >
            리뷰 {formatCount(product.review_count)}건
          </button>
        </div>
      ) : (
        <p className="summary__rating summary__rating--empty">아직 등록된 평점이 없습니다</p>
      )}

      <div className="summary__price" data-log-content="price">
        <strong>{formatPrice(product.price_usd)}</strong>
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

        <button type="button" className="btn btn--primary" data-log-action="add_to_cart" onClick={addToCart}>
          Add to Basket
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

      {addedAt !== null ? (
        <p className="summary__toast" role="status">
          장바구니에 담았습니다 · 수량 {quantity}
        </p>
      ) : null}

      <p className="summary__meta">Item {product.product_id}</p>
    </div>
  );
}
