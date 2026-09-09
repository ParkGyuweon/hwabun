import { creativeFor, packshot } from '../../lib/bannerCreative';
import { formatPrice } from '../../lib/format';
import type { BannerAxis } from '../../lib/bannerCreative';
import type { Product } from '../../types/product';

interface AdBannerProps {
  product: Product;
  axis: BannerAxis;
  value: string | null;
  /** 히어로는 가로로 길고, 카드는 세로 4:5 */
  shape: 'hero' | 'card';
  /** 같은 피부 배너에 쓸 손 톤 */
  skinTone?: string;
  /** 배너 칸 번호. 로그 property `banner_slot` 과 같은 값 */
  slot: number;
  onSelect: (productId: string) => void;
}

/**
 * 광고 배너 한 칸.
 *
 * 올리브영 배너 관행을 따른다 (계획 §10-1·§10-5):
 *   상단 브랜드 워드마크 + 우상단 원형 배지 → 질문형 킥커 → 하이라이트 박스 헤드라인
 *   → 흰 판 위의 제품 컷아웃(+성분 원물·손) → 가격·용량 → 하단 풀폭 CTA 바
 *
 * 우리가 **하지 않는 것**: 할인율·취소선 가격(할인 데이터 없음), 순위·1등 배지(순위 데이터 없음),
 * 효능 단정 문구(화장품법 표시·광고 금지 표현). 배너는 유료 광고가 아니라 추천 결과를 강조하는
 * 자리라서 "광고" 라는 말도 쓰지 않는다.
 *
 * 문구는 이미지에 굽지 않고 여기서 얹는다. 사용자 성향에 따라 같은 상품이 다른 배너가 되어야
 * 하므로, 이미지를 다시 만들지 않고 문구·배경·소품만 바꾼다.
 */
export default function AdBanner({
  product,
  axis,
  value,
  shape,
  skinTone,
  slot,
  onSelect,
}: AdBannerProps) {
  const c = creativeFor(product, axis, value, skinTone);

  return (
    <article
      className={`ad ad--${shape} ad--${c.variant}`}
      data-product-id={product.product_id}
      data-banner-slot={slot}
      data-banner-type={c.axis}
      data-banner-value={value ?? undefined}
      data-log-content="recommendation_card"
      data-log-ref={product.product_id}
    >
      <button type="button" className="ad__hit" onClick={() => onSelect(product.product_id)}>
        <img className="ad__bg" src={c.bg} alt="" aria-hidden="true" />

        <div className="ad__top">
          <span className="ad__wordmark">{product.brand_name}</span>
          <span className="ad__badge">{c.badge}</span>
        </div>

        <div className="ad__copy">
          <p className="ad__kicker">{c.kicker}</p>
          <p className="ad__head">
            <mark className="ad__mark">{c.head.mark}</mark>
            <span className="ad__rest">{c.head.rest}</span>
          </p>
        </div>

        {/* 흰 판. 컷아웃 누끼가 용기의 흰 부분을 조금 깎아서 흰 바탕 위에 얹는다 */}
        <div className="ad__stage">
          <img className="ad__product" src={packshot(product)} alt={product.product_name} loading="lazy" />
          {c.prop ? <img className="ad__prop" src={c.prop} alt="" aria-hidden="true" loading="lazy" /> : null}
        </div>

        <div className="ad__price">
          {c.bigPrice ? (
            <strong className="ad__price-big">{formatPrice(product.price_usd)}</strong>
          ) : (
            <strong className="ad__price-num">{formatPrice(product.price_usd)}</strong>
          )}
          {product.size ? <span className="ad__size">{product.size}</span> : null}
          <span className="ad__name">{product.product_name}</span>
        </div>

        <p className="ad__foot">{c.foot}</p>
        <span className="ad__cta">
          {c.cta}
          <i aria-hidden="true">▾</i>
        </span>
      </button>
    </article>
  );
}
