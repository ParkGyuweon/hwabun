import { useEffect, useRef } from 'react';
import StarRating from '../common/StarRating';
import { formatCount, formatPrice } from '../../lib/format';
import { IMAGE_WIDTH_CARD, sizedImage } from '../../lib/image';
import { track, trackOnce } from '../../lib/logger';
import type { Product } from '../../types/product';

const PLACEHOLDER = '/images/product-placeholder.svg';
const IMPRESSION_RATIO = 0.5;
const IMPRESSION_DWELL_MS = 1000;

interface SimilarProductsProps {
  products: Product[];
  /** 이 목록이 어떤 자리인지. 추천 성능을 목록별로 나눠 보기 위해 필요하다 */
  listId: string;
  /** 추천 응답 단위 식별자. 노출과 클릭을 같은 요청으로 묶는다 */
  recommendationId: string;
  /** 어떤 로직이 만든 목록인지 */
  algorithm: string;
  onSelect: (productId: string) => void;
}

/**
 * 추천 상품 캐러셀.
 *
 * CTR 을 계산하려면 클릭한 상품뿐 아니라 클릭하지 않은 노출 상품도 있어야 해서
 * 카드가 실제로 보였을 때 recommendation_impression 을 남긴다.
 */
export default function SimilarProducts({
  products,
  listId,
  recommendationId,
  algorithm,
  onSelect,
}: SimilarProductsProps) {
  const trackRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const root = trackRef.current;
    if (!root) return;

    const timers = new Map<Element, number>();
    const cards = root.querySelectorAll<HTMLElement>('[data-product-id]');

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const element = entry.target as HTMLElement;
          const productId = element.dataset.productId;
          const position = Number(element.dataset.position);
          if (!productId) continue;

          if (!entry.isIntersecting || entry.intersectionRatio < IMPRESSION_RATIO) {
            const pending = timers.get(element);
            if (pending !== undefined) {
              window.clearTimeout(pending);
              timers.delete(element);
            }
            continue;
          }

          if (timers.has(element)) continue;

          const timer = window.setTimeout(() => {
            timers.delete(element);
            trackOnce(
              `rec_impression:${recommendationId}:${productId}`,
              'recommendation_impression',
              { recommendation_id: recommendationId, list_id: listId, algorithm, product_id: productId, position },
            );
          }, IMPRESSION_DWELL_MS);

          timers.set(element, timer);
        }
      },
      { threshold: [IMPRESSION_RATIO] },
    );

    for (const card of cards) {
      observer.observe(card);
    }

    return () => {
      observer.disconnect();
      for (const timer of timers.values()) {
        window.clearTimeout(timer);
      }
    };
  }, [recommendationId, listId, algorithm, products]);

  if (products.length === 0) {
    return null;
  }

  const select = (product: Product, position: number) => {
    // 노출 이벤트와 같은 recommendation_id / position 을 실어야 CTR 을 계산할 수 있다
    track('recommendation_click', {
      recommendation_id: recommendationId,
      list_id: listId,
      algorithm,
      product_id: product.product_id,
      position,
    });
    track('product_click', { product_id: product.product_id, entry_source: listId });
    onSelect(product.product_id);
  };

  return (
    <div className="similar">
      <ul className="similar__track" ref={trackRef}>
        {products.map((product, index) => (
          <li
            key={product.product_id}
            className="similar__item"
            data-product-id={product.product_id}
            data-position={index + 1}
            data-log-content="recommendation_card"
            data-log-ref={product.product_id}
          >
            <button
              type="button"
              className="similar__link"
              data-log-action="recommendation_click"
              onClick={() => select(product, index + 1)}
            >
              <span className="similar__thumb">
                <img
                  src={sizedImage(product.image_url, IMAGE_WIDTH_CARD) ?? PLACEHOLDER}
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                />
              </span>
              <span className="similar__brand">{product.brand_name}</span>
              <span className="similar__name">{product.product_name}</span>
              {product.rating !== null ? (
                <span className="similar__rating">
                  <StarRating value={product.rating} size="sm" />
                  {product.review_count !== null ? (
                    <span className="similar__count">{formatCount(product.review_count)}</span>
                  ) : null}
                </span>
              ) : null}
              <span className="similar__price">{formatPrice(product.price_usd)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
