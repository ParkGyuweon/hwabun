import StarRating from '../common/StarRating';
import { formatCount, formatPrice } from '../../lib/format';
import type { Product } from '../../types/product';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface SimilarProductsProps {
  products: Product[];
}

/**
 * 유사 상품 캐러셀.
 *
 * 지금은 같은 상위 카테고리 상품을 단순 나열한다.
 * CBF 추천 결과를 붙이는 자리이므로 목록만 교체하면 되도록 데이터 의존을 Product[] 하나로 둔다.
 */
export default function SimilarProducts({ products }: SimilarProductsProps) {
  if (products.length === 0) {
    return null;
  }

  return (
    <div className="similar">
      <ul className="similar__track">
        {products.map((product) => (
          <li key={product.product_id} className="similar__item">
            <a href="#" className="similar__link">
              <span className="similar__thumb">
                <img src={product.image_url ?? PLACEHOLDER} alt="" aria-hidden="true" />
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
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
