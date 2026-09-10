import { useState } from 'react';
import { bannerImage, creativeFor, packshot } from '../../lib/bannerCreative';
import PriceTag from '../product/PriceTag';
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
  /** 배너 칸 번호. 로그 property `banner_slot` 과 같은 값. 계약상 1 이상이다 */
  slot: number;
  /**
   * 이 세션이 20% 탐색군인지(`explore`). 노출 이벤트의 `trait_source` 로 나간다.
   *
   * 노출에 이 값이 없으면 탐색군 비중을 셀 분모가 없어진다. 검증 Job 이
   * 노출 100건 이상에서 explore 비중 10~30% 를 확인하므로, 노출과 클릭에
   * **같은 값**이 실려야 한다 (데이터 파트 회신 2026-09-10).
   */
  traitSource?: string;
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
 * 할인은 PriceTag 가 그린다 (할인율·할인가·취소선 정가, 결정 2026-09-10). 순위·1위·수상 배지는
 * 데이터가 없어 만들지 않고, 효능 단정 문구는 화장품법 표시·광고 금지 표현이라 쓰지 않는다. 배너는 유료 광고가 아니라 추천 결과를 강조하는 자리라 "광고" 라는 말도 쓰지 않는다.
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
  traitSource,
  onSelect,
}: AdBannerProps) {
  const c = creativeFor(product, axis, value, skinTone);

  /**
   * 완성형 배너가 등록돼 있어도 파일이 없을 수 있다. `banner-images.json` 은 목록일 뿐
   * 파일 존재를 보장하지 않는다 (브라우저가 미리 알 수 없어서 목록을 두는 것이다).
   * 실제로 SB000001·SB000002 는 목록에 올라간 채 파일이 없었고, 폴백이 없어서
   * 그 자리에 깨진 이미지 한 칸이 떴다.
   *
   * 404 를 받으면 그 주소만 기억해 두고 CSS 조립 배너로 돌아간다. 주소로 기억하므로
   * 다음 배너가 다른 상품·변형이면 다시 시도한다.
   */
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const registered = bannerImage(product.product_id, c.variant);
  const image = registered !== null && registered !== failedSrc ? registered : null;

  return (
    <article
      className={`ad ad--${shape} ad--${c.variant}${image ? ' ad--image' : ''}`}
      data-variant={c.variant}
      data-concern={c.axis === 'concern' && value ? value : undefined}
      data-product-id={product.product_id}
      data-banner-slot={slot}
      data-trait-source={traitSource}
      data-banner-type={c.axis}
      data-banner-value={value ?? undefined}
      data-log-content="recommendation_card"
      data-log-ref={product.product_id}
    >
      <button type="button" className="ad__hit" onClick={() => onSelect(product.product_id)}>
        {image ? (
          /* 완성형 한 장. 글자·가격·배지가 이미지 안에 있다. 접근성 문구만 따로 */
          <img
            className="ad__image"
            src={image}
            alt={`${product.brand_name} ${product.product_name} · ${c.kicker} ${c.head.mark}${c.head.rest}`}
            onError={() => setFailedSrc(image)}
          />
        ) : null}
        {image ? null : (
        <>
        <span className="ad__brand">{product.brand_name}</span>
        <span className="ad__badge">{c.badge}</span>

        <div className="ad__copy">
          <p className="ad__kicker">{c.kicker}</p>
          <h3 className="ad__head">
            <span className="ad__head-em">{c.head.mark}</span>
            <span className="ad__head-rest">{c.head.rest}</span>
          </h3>
          <p className="ad__sub">
            <PriceTag product={product} size={c.bigPrice ? 'lg' : 'md'} showLabel={c.bigPrice} />
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
        </>
        )}
      </button>
    </article>
  );
}
