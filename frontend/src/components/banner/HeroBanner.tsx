import { IMAGE_WIDTH_MAIN, sizedImage } from '../../lib/image';
import { formatPrice } from '../../lib/format';
import { bannerCopy } from './bannerCopy';
import type { TraitSource } from '../../types/log';
import type { Product } from '../../types/product';
import type { RecommendHero } from '../../types/recommendation';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface HeroBannerProps {
  hero: RecommendHero;
  product: Product;
  traitSource: TraitSource;
  /** 추천 API `reason` 이 오면 그대로 붙인다. 목에서는 없다 */
  reason?: string | null;
  onSelect: (productId: string) => void;
}

/**
 * 히어로 — 추천 1위(`items[0]`)에 축 문구를 얹은 한 칸.
 *
 * 노출·클릭은 부모의 `useImpression`/클릭 핸들러가 `data-*` 로 읽는다.
 * 카드는 `data-log-section="promo_row"` 안에 있어야 한다 (계약에 hero 섹션 enum 이 아직 없다).
 */
export default function HeroBanner({ hero, product, traitSource, reason, onSelect }: HeroBannerProps) {
  const copy = bannerCopy(hero.banner_type, hero.banner_value);
  return (
    <article
      className="hero-banner"
      data-product-id={product.product_id}
      data-position={0}
      data-log-content="recommendation_card"
      data-log-ref={product.product_id}
      data-banner-type={hero.banner_type}
      data-banner-value={hero.banner_value ?? undefined}
      data-banner-slot={0}
      data-trait-source={traitSource}
    >
      <button type="button" className="hero-banner__link" onClick={() => onSelect(product.product_id)}>
        <div className="hero-banner__media">
          <img
            src={sizedImage(product.image_url, IMAGE_WIDTH_MAIN) ?? PLACEHOLDER}
            alt=""
            loading="eager"
          />
        </div>
        <div className="hero-banner__body">
          <span className="hero-banner__kicker">{copy.kicker}</span>
          <h2 className="hero-banner__headline">{copy.headline}</h2>
          <p className="hero-banner__product">
            <span className="hero-banner__brand">{product.brand_name}</span>
            <span className="hero-banner__name">{product.product_name}</span>
          </p>
          <p className="hero-banner__meta">
            <span>{formatPrice(product.price_usd)}</span>
            {product.size ? <span>{product.size}</span> : null}
          </p>
          {reason ? <p className="hero-banner__reason">{reason}</p> : null}
        </div>
      </button>
    </article>
  );
}
