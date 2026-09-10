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
 * 올리브영 기획전 배너의 틀을 따른다 (계획 §10, 참고 이미지 2026-09-10):
 *   파스텔 단색 배경 한 장 · 좌상단 작은 브랜드명 · 왼쪽에 큰 헤드라인 두 줄 · 그 아래 가격·용량
 *   · 오른쪽에 단(podium) 위로 올린 제품 컷 · 우상단 원형 스티커 배지
 *
 * 배경에 사진 타일을 깔지 않는다. 글자 뒤가 차분해야 큰 헤드라인이 읽히고, 제품 컷이
 * 배경과 싸우지 않는다. 변형마다 색 하나만 바꾼다 (`data-variant` → CSS 변수).
 *
 * 우리가 **하지 않는 것**: 할인율·취소선 가격(할인 데이터 없음), 순위·1위·수상 배지(순위 데이터
 * 없음), 효능 단정 문구(화장품법 표시·광고 금지 표현). 참고 배너의 "1등", "55% 할인" 자리는
 * 비워 둔다. 배너는 유료 광고가 아니라 추천 결과를 강조하는 자리라 "광고" 라는 말도 쓰지 않는다.
 *
 * 문구는 이미지에 굽지 않고 여기서 얹는다. 같은 상품이 성향에 따라 다른 배너가 되어야
 * 하므로, 이미지를 다시 만들지 않고 문구·색·소품만 바꾼다.
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
      data-variant={c.variant}
      data-concern={c.axis === 'concern' && value ? value : undefined}
      data-product-id={product.product_id}
      data-banner-slot={slot}
      data-banner-type={c.axis}
      data-banner-value={value ?? undefined}
      data-log-content="recommendation_card"
      data-log-ref={product.product_id}
    >
      <button type="button" className="ad__hit" onClick={() => onSelect(product.product_id)}>
        <span className="ad__brand">{product.brand_name}</span>
        <span className="ad__badge">{c.badge}</span>

        <div className="ad__copy">
          <p className="ad__kicker">{c.kicker}</p>
          <h3 className="ad__head">
            <span className="ad__head-em">{c.head.mark}</span>
            <span className="ad__head-rest">{c.head.rest}</span>
          </h3>
          <p className="ad__sub">
            <strong className={c.bigPrice ? 'ad__price ad__price--big' : 'ad__price'}>
              {formatPrice(product.price_usd)}
            </strong>
            {product.size ? <span className="ad__size">{product.size}</span> : null}
          </p>
          {c.foot && c.foot !== product.size ? <p className="ad__foot">{c.foot}</p> : null}
          <span className="ad__cta">
            {c.cta}
            <i aria-hidden="true">›</i>
          </span>
        </div>

        {/*
          흰 판 위의 제품. 상품 사진은 전부 흰 배경 팩샷이라(세포라 원본·SSAFY Beauty 마스터 컷)
          누끼를 따지 않고 흰 판에 그대로 올린다. 누끼는 제품의 흰 부분까지 뜯어내 구멍이 났다 (2026-09-10).
        */}
        <div className="ad__stage" aria-hidden="true">
          <img className="ad__product" src={packshot(product)} alt="" loading="lazy" />
          {c.prop ? <img className="ad__prop" src={c.prop} alt="" loading="lazy" /> : null}
        </div>
        <span className="sr-only">{product.product_name}</span>
      </button>
    </article>
  );
}
