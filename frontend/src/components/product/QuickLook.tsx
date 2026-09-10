import { useEffect, useRef, useState } from 'react';
import { variantIdOf } from '../../lib/discount';
import PriceTag from './PriceTag';
import { hasDiscount } from '../../lib/discount';
import StarRating from '../common/StarRating';
import VariantPicker from './VariantPicker';
import { IMAGE_WIDTH_MAIN, sizedImage } from '../../lib/image';
import { formatCount } from '../../lib/format';
import { track } from '../../lib/logger';
import type { Product, ProductVariant } from '../../types/product';
import type { CartItem } from '../../types/cart';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface QuickLookProps {
  product: Product;
  onClose: () => void;
  onAddToCart: (item: CartItem) => void;
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
export default function QuickLook({ product, onClose, onAddToCart, onOpenDetail }: QuickLookProps) {
  const [variant, setVariant] = useState<ProductVariant | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedAt, setAddedAt] = useState<number | null>(null);
  const [loved, setLoved] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // 렌더 중에는 Date.now() 를 부르지 않는다. 실제 진입 시각은 이펙트에서 채운다 (useExitSummary 와 동일)
  const openedAtRef = useRef(0);
  /** 창 안에서 살펴본 옵션 수 */
  const viewedSkusRef = useRef(new Set<string>());
  const closedRef = useRef(false);
  /**
   * state 대신 ref 로도 든다. 담기 직후 같은 틱에 닫히면(연타 등)
   * 리렌더 전 클로저가 잡혀 added_to_cart 가 false 로 나간다.
   */
  const addedRef = useRef(false);
  const lovedRef = useRef(false);

  /**
   * 닫힘 요약. 열림(quick_look)과 짝이다.
   * 창이 떠 있는 동안은 섹션 체류 훅의 사정권 밖이라, 여기서 직접 재서 보낸다.
   * 체류만으로는 자리 비움과 구분이 안 되므로 창 안에서 한 행동을 같이 싣는다.
   */
  const emitClose = (reason: string) => {
    if (closedRef.current) return;
    closedRef.current = true;
    track('quick_look_close', {
      product_id: product.product_id,
      close_reason: reason,
      dwell_ms: Date.now() - openedAtRef.current,
      variants_viewed: viewedSkusRef.current.size,
      added_to_cart: addedRef.current,
      wishlisted: lovedRef.current,
    });
  };

  const handleClose = (reason: string) => {
    emitClose(reason);
    onClose();
  };

  // ESC 핸들러가 최신 상태를 보게 한다. 렌더 중 ref 할당은 lint 가 막으므로 이펙트에서 한다
  const handleCloseRef = useRef(handleClose);
  useEffect(() => {
    handleCloseRef.current = handleClose;
  });

  const skuId = variant?.sku_id ?? product.sku_id;
  const imageUrl = variant?.image_url ?? product.image_url;

  useEffect(() => {
    openedAtRef.current = Date.now();
    closeRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') handleCloseRef.current('escape');
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
    addedRef.current = true;
    setAddedAt(Date.now());
    track('add_to_cart', {
      product_id: product.product_id,
      sku_id: skuId,
      quantity,
      price_usd: product.price_usd,
      ...(hasDiscount(product) ? { sale_price_usd: product.sale_price_usd, discount_rate: product.discount_rate } : {}),
      entry_source: 'quick_look',
    });
    onAddToCart({
      product_id: product.product_id,
      sku_id: skuId,
      variant_label: variant?.label ?? null,
      brand_name: product.brand_name,
      product_name: product.product_name,
      image_url: imageUrl,
      price_usd: product.price_usd,
      sale_price_usd: product.sale_price_usd ?? null,
      variant_id: variantIdOf(product, skuId),
      quantity,
    });
  };

  const [wishNotice, setWishNotice] = useState<'add' | 'remove' | null>(null);

  const toggleWishlist = () => {
    const next = !loved;
    lovedRef.current = next;
    setLoved(next);
    setWishNotice(next ? 'add' : 'remove');
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
        if (event.target === event.currentTarget) handleClose('backdrop');
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
          onClick={() => handleClose('close_button')}
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
            onClick={() => {
              emitClose('open_detail');
              onOpenDetail(product.product_id);
            }}
          >
            상세 페이지 보기
          </button>

          {product.size ? <p className="qlook__size">Size: {product.size}</p> : null}

          <VariantPicker
            productId={product.product_id}
            variants={product.variants}
            selectedSkuId={skuId}
            onSelect={(next) => {
              viewedSkusRef.current.add(next.sku_id);
              setVariant(next);
            }}
          />

          <div className="qlook__buy">
            <PriceTag product={product} size="md" className="qlook__price" />

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

            {wishNotice !== null ? (
              <p className="qlook__toast qlook__toast--wish" role="status">
                {wishNotice === 'add' ? '찜 목록에 담았습니다 ♥' : '찜을 해제했습니다'}
              </p>
            ) : null}
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
