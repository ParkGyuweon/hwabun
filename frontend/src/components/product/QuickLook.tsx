import { useEffect, useRef, useState } from 'react';
import StarRating from '../common/StarRating';
import VariantPicker from './VariantPicker';
import { IMAGE_WIDTH_MAIN, sizedImage } from '../../lib/image';
import { formatCount, formatPrice } from '../../lib/format';
import { track } from '../../lib/logger';
import type { Product, ProductVariant } from '../../types/product';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface QuickLookProps {
  product: Product;
  onClose: () => void;
  /** 상세로 이동. 닫기와 클릭 로그는 호출한 쪽이 처리한다 */
  onOpenDetail: (productId: string) => void;
}

/**
 * 목록에서 상세로 가지 않고 여는 요약 창. 세포라의 Quicklook 을 따랐다.
 *
 * 행동 로그 관점에서 이 창은 두 가지를 새로 잡는다.
 * - 상세까지 갈 정도는 아니지만 들여다본 상품 (`quick_look`)
 * - 상세를 거치지 않는 장바구니 담기 (`add_to_cart`, entry_source=quick_look)
 *
 * 열림 이벤트는 여는 쪽(목록)에서 남긴다. 여기서 effect 로 남기면
 * StrictMode 가 두 번 실행해 중복이 생긴다.
 */
export default function QuickLook({ product, onClose, onOpenDetail }: QuickLookProps) {
  const [variant, setVariant] = useState<ProductVariant | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedAt, setAddedAt] = useState<number | null>(null);
  const [loved, setLoved] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const skuId = variant?.sku_id ?? product.sku_id;
  const imageUrl = variant?.image_url ?? product.image_url;

  useEffect(() => {
    closeRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);

    // 창이 떠 있는 동안 뒤 목록이 스크롤되면 그 시간이 목록 체류로 잘못 쌓인다
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const addToCart = () => {
    // 장바구니 API 가 붙으면 성공 응답 뒤로 옮긴다 (ProductSummary 와 동일)
    setAddedAt(Date.now());
    track('add_to_cart', {
      product_id: product.product_id,
      sku_id: skuId,
      quantity,
      price_usd: product.price_usd,
      entry_source: 'quick_look',
    });
  };

  const toggleWishlist = () => {
    const next = !loved;
    setLoved(next);
    track('wishlist_toggle', {
      product_id: product.product_id,
      action: next ? 'add' : 'remove',
      entry_source: 'quick_look',
    });
  };

  return (
    <div
      className="qlook"
      data-log-action="quick_look_close"
      onClick={(event) => {
        // 흐린 배경을 누르면 닫는다. 창 안쪽 클릭은 여기까지 안 올라온다
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="qlook__dialog"
        role="dialog"
        aria-modal="true"
        aria-label={product.product_name}
      >
        <button
          ref={closeRef}
          type="button"
          className="qlook__close"
          aria-label="닫기"
          data-log-action="quick_look_close"
          onClick={onClose}
        >
          ×
        </button>

        <div className="qlook__media">
          <img src={sizedImage(imageUrl, IMAGE_WIDTH_MAIN) ?? PLACEHOLDER} alt={product.product_name} />

          {product.rating !== null ? (
            <p className="qlook__meta">
              <StarRating value={product.rating} size="sm" />
              {product.review_count !== null ? (
                <span>리뷰 {formatCount(product.review_count)}건</span>
              ) : null}
            </p>
          ) : null}
        </div>

        <div className="qlook__info">
          <p className="qlook__brand">{product.brand_name}</p>
          <h2 className="qlook__name">{product.product_name}</h2>
          <p className="qlook__item">ITEM {skuId ?? product.product_id}</p>

          {product.description?.what_it_is ? (
            <p className="qlook__desc">{product.description.what_it_is}</p>
          ) : null}

          <button
            type="button"
            className="qlook__details link-button"
            data-log-action="quick_look_detail"
            onClick={() => onOpenDetail(product.product_id)}
          >
            상세 페이지 보기
          </button>

          {product.size ? <p className="qlook__size">Size: {product.size}</p> : null}

          <VariantPicker
            productId={product.product_id}
            variants={product.variants}
            selectedSkuId={skuId}
            onSelect={setVariant}
          />

          <div className="qlook__buy">
            <strong className="qlook__price">{formatPrice(product.price_usd)}</strong>

            <div className="qlook__actions">
              <label className="qlook__qty">
                수량
                <select
                  value={quantity}
                  onChange={(event) => {
                    const next = Number(event.target.value);
                    setQuantity(next);
                    track('quantity_change', {
                      product_id: product.product_id,
                      quantity: next,
                      entry_source: 'quick_look',
                    });
                  }}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="button"
                className="qlook__cta"
                data-log-action="add_to_cart"
                onClick={addToCart}
              >
                Add to Basket
              </button>

              <button
                type="button"
                className={`qlook__lists${loved ? ' is-active' : ''}`}
                aria-pressed={loved}
                data-log-action="wishlist_toggle"
                onClick={toggleWishlist}
              >
                {loved ? '♥' : '♡'} 리스트에 담기
              </button>
            </div>

            {addedAt !== null ? (
              <p className="qlook__toast" role="status">
                장바구니에 담았습니다 · 수량 {quantity}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
