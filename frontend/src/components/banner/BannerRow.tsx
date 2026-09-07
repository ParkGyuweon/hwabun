import { IMAGE_WIDTH_CARD, sizedImage } from '../../lib/image';
import { formatPrice } from '../../lib/format';
import { bannerCopy } from './bannerCopy';
import type { TraitSource } from '../../types/log';
import type { Product } from '../../types/product';
import type { RecommendBanner } from '../../types/recommendation';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface BannerRowProps {
  banners: RecommendBanner[];
  productsById: Map<string, Product>;
  traitSource: TraitSource;
  /** 전용 칸을 앞으로 당길지 (participate 성향) */
  reservedFirst?: boolean;
  onSelect: (productId: string) => void;
}

/**
 * 배너 행 — 축 배너 4칸 + 신규 브랜드 전용 2칸 (칸 수는 lib/bannerConfig).
 *
 * 카드마다 `data-banner-*` 를 실어 두면 `useImpression` 이 노출 property 로 읽어 간다.
 * `banner_value` 는 어휘집 원문 그대로 싣는다. 화면 라벨은 `bannerCopy` 가 바꾼다.
 */
export default function BannerRow({ banners, productsById, traitSource, reservedFirst = false, onSelect }: BannerRowProps) {
  const ordered = reservedFirst
    ? [...banners.filter((b) => b.reserved), ...banners.filter((b) => !b.reserved)]
    : banners;

  return (
    <ul className="banner-row">
      {ordered.map((banner, index) => {
        const product = productsById.get(banner.product_id);
        if (!product) return null;
        const copy = bannerCopy(banner.banner_type, banner.banner_value);
        return (
          <li
            key={`${banner.slot}-${banner.product_id}`}
            className={`banner-card${banner.reserved ? ' banner-card--reserved' : ''}`}
            data-product-id={product.product_id}
            data-position={index + 1}
            data-log-content="recommendation_card"
            data-log-ref={product.product_id}
            data-banner-type={banner.banner_type}
            data-banner-value={banner.banner_value ?? undefined}
            data-banner-slot={banner.slot}
            data-trait-source={traitSource}
          >
            <button type="button" className="banner-card__link" onClick={() => onSelect(product.product_id)}>
              <span className="banner-card__kicker">{copy.kicker}</span>
              <span className="banner-card__headline">{copy.headline}</span>
              <span className="banner-card__media">
                <img src={sizedImage(product.image_url, IMAGE_WIDTH_CARD) ?? PLACEHOLDER} alt="" loading="lazy" />
              </span>
              <span className="banner-card__brand">{product.brand_name}</span>
              <span className="banner-card__name">{product.product_name}</span>
              <span className="banner-card__price">{formatPrice(product.price_usd)}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
