import StarRating from '../common/StarRating';
import PriceTag from './PriceTag';
import { badgeKo } from '../../lib/localize';
import { IMAGE_WIDTH_CARD, sizedImage } from '../../lib/image';
import { formatCount } from '../../lib/format';
import type { Product } from '../../types/product';
import type { LogContentKind } from '../../types/log';

const PLACEHOLDER = '/images/product-placeholder.svg';

// 배지 문구는 사이트 라벨(contracts/localization/labels-ko.json)을 쓴다. 할인율 배지는 데이터가 없어 만들지 않는다

interface ProductCardProps {
  product: Product;
  /** 목록 안에서의 순번. 1부터. 노출·클릭 로그에 실린다 */
  position: number;
  /**
   * 이 카드가 어떤 자리에 있는지.
   * 목록 카드와 추천 카드를 구분해야 추천 성과를 따로 집계할 수 있다.
   */
  contentKind?: LogContentKind;
  onSelect: (productId: string) => void;
  /** 있으면 이미지 위에 Quick Look 버튼이 뜬다 */
  onQuickLook?: (productId: string) => void;
}

/**
 * 목록·기획전 공용 상품 카드.
 *
 * `data-product-id` 와 `data-position` 을 노출한다.
 * `useImpression` 이 이 속성을 읽어 노출 로그를 남기므로 이름을 바꾸면 안 된다.
 */
export default function ProductCard({
  product,
  position,
  contentKind = 'product_card',
  onSelect,
  onQuickLook,
}: ProductCardProps) {
  const badges = product.badges ?? [];

  return (
    <li
      className="card"
      data-product-id={product.product_id}
      data-position={position}
      data-log-content={contentKind}
      data-log-ref={product.product_id}
    >
      <button type="button" className="card__link" onClick={() => onSelect(product.product_id)}>
        <span className="card__thumb">
          <img
            src={sizedImage(product.image_url, IMAGE_WIDTH_CARD) ?? PLACEHOLDER}
            alt=""
            aria-hidden="true"
            loading="lazy"
          />
          {badges.length > 0 ? (
            <span className="card__badges">
              {badges.map((badge) => (
                <span key={badge} className={`card__badge card__badge--${badge}`}>
                  {badgeKo(badge)}
                </span>
              ))}
            </span>
          ) : null}
        </span>

        <span className="card__brand">{product.brand_name}</span>
        <span className="card__name">{product.product_name}</span>
        <PriceTag product={product} size="sm" className="card__price" />

        {product.rating !== null ? (
          <span className="card__rating">
            <StarRating value={product.rating} size="sm" />
            {product.review_count !== null ? (
              <span className="card__count">{formatCount(product.review_count)}</span>
            ) : null}
          </span>
        ) : (
          // 평점이 없어도 카드 높이가 흔들리지 않게 자리를 잡아둔다
          <span className="card__rating card__rating--empty" aria-hidden="true" />
        )}
      </button>

      {onQuickLook ? (
        /*
         * 카드 전체가 이미 button 이라 안에 버튼을 중첩할 수 없다.
         * 형제로 두고 이미지 영역(정사각형) 위에만 겹친다.
         */
        <span className="card__hover">
          <button
            type="button"
            className="card__quicklook"
            data-log-action="quick_look"
            onClick={() => onQuickLook(product.product_id)}
          >
            Quick Look
          </button>
        </span>
      ) : null}
    </li>
  );
}
