import { useEffect } from 'react';
import { useImpression } from '../../hooks/useImpression';
import StarRating from '../common/StarRating';
import { formatCount, formatPrice } from '../../lib/format';
import { IMAGE_WIDTH_CARD, sizedImage } from '../../lib/image';
import { setNextProductViewEntry, track } from '../../lib/logger';
import type { Product } from '../../types/product';

const PLACEHOLDER = '/images/product-placeholder.svg';
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

  /**
   * 노출은 공용 훅에 맡긴다. 판정 기준(hold_ms·visible_ratio)을 한 곳에서
   * 관리해야 목록(300ms)과 추천(1000ms)의 분모 차이를 로그로 설명할 수 있다.
   */
  const trackRef = useImpression({
    pageViewKey: recommendationId,
    eventName: 'recommendation_impression',
    listId,
    holdMs: IMPRESSION_DWELL_MS,
    algorithm,
    recommendationId,
  });

  /**
   * 목록이 다시 그려질 때마다 정렬 결과를 남긴다.
   * 추천이 갱신되면서 순위가 어떻게 움직이는지 실제 화면 기준으로 추적할 수 있다.
   * 노출·클릭과 같은 recommendation_id 로 묶인다.
   */
  useEffect(() => {
    if (products.length === 0) return;
    track('recommendation_snapshot', {
      recommendation_id: recommendationId,
      list_id: listId,
      algorithm,
      size: products.length,
      ranking: products.map((p, index) => ({ product_id: p.product_id, position: index + 1 })),
    });
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
    // 곧 열릴 상세의 product_view 에 같은 식별자를 싣는다 (Jira 210)
    setNextProductViewEntry({
      product_id: product.product_id,
      recommendation_id: recommendationId,
      list_id: listId,
      position,
    });
    onSelect(product.product_id);
  };

  return (
    <div className="similar">
      <ul className="similar__track" ref={trackRef as React.Ref<HTMLUListElement>}>
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
