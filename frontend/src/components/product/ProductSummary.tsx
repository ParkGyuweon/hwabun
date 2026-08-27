import { useState } from 'react';
import StarRating from '../common/StarRating';
import { formatCount, formatPrice } from '../../lib/format';
import type { Product } from '../../types/product';

interface ProductSummaryProps {
  product: Product;
  /** 리뷰 섹션으로 스크롤 이동 */
  onReviewLinkClick: () => void;
}

/**
 * 세포라 상세 페이지 우측 상단의 구매 정보 블록.
 */
export default function ProductSummary({ product, onReviewLinkClick }: ProductSummaryProps) {
  const [quantity, setQuantity] = useState(1);
  const [loved, setLoved] = useState(false);

  return (
    <div className="summary">
      <p className="summary__brand">{product.brand_name}</p>
      <h1 className="summary__name">{product.product_name}</h1>

      {product.rating !== null && product.review_count !== null ? (
        <div className="summary__rating">
          <StarRating value={product.rating} />
          <span className="summary__rating-value">{product.rating.toFixed(2)}</span>
          <button type="button" className="link-button" onClick={onReviewLinkClick}>
            리뷰 {formatCount(product.review_count)}건
          </button>
        </div>
      ) : (
        <p className="summary__rating summary__rating--empty">아직 등록된 평점이 없습니다</p>
      )}

      <div className="summary__price">
        <strong>{formatPrice(product.price_usd)}</strong>
        {/* size 는 자유 텍스트라 파싱하지 않고 그대로 노출한다 */}
        {product.size ? <span className="summary__size">{product.size}</span> : null}
      </div>

      <div className="summary__actions">
        <div className="qty" role="group" aria-label="수량 선택">
          <button type="button" onClick={() => setQuantity((n) => Math.max(1, n - 1))} aria-label="수량 감소">
            −
          </button>
          <span aria-live="polite">{quantity}</span>
          <button type="button" onClick={() => setQuantity((n) => Math.min(99, n + 1))} aria-label="수량 증가">
            +
          </button>
        </div>

        <button type="button" className="btn btn--primary">
          장바구니 담기
        </button>

        <button
          type="button"
          className={`btn btn--icon${loved ? ' is-active' : ''}`}
          aria-pressed={loved}
          aria-label={loved ? '찜 해제' : '찜하기'}
          onClick={() => setLoved((prev) => !prev)}
        >
          {loved ? '♥' : '♡'}
        </button>
      </div>

      <p className="summary__meta">상품 코드 {product.product_id}</p>
    </div>
  );
}
