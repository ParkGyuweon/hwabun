import { useState } from 'react';
import { anyBannerImage, creativeFor } from '../../lib/bannerCreative';
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
  /**
   * 클릭. 두 번째 인자는 **로그에 적을** 축·값이다 — 화면의 축(`axis`)과 다를 수 있다.
   * 완성형 배너가 실제로 그려졌으면 `new_brand` · null 이고, 조립 배너면 `axis` · `value` 그대로다.
   */
  onSelect: (productId: string, logged: BannerLog) => void;
}

/** 배너 이벤트에 실리는 축·값 */
export interface BannerLog {
  banner_type: BannerAxis;
  banner_value: string | null;
}

/**
 * 광고 배너 한 칸 — **완성형 이미지만** 그린다.
 *
 * 2026-09-18: CSS 로 조립하던 배너(파스텔 배경 · 헤드라인 · 흰 단 위 제품 컷 · 소품)를 걷어냈다. 그 조립 배너가
 * 세포라 카탈로그 상품(에스티로더 등)을 옛 벡터 이미지 느낌으로 띄우고 있었다. 배너는 팀이 글자까지 넣어 만든
 * 완성형 한 장(`banner-images.json` 에 등록된 SSAFY Beauty 상품군)이 있을 때만 존재한다. 이미지가 없거나 404 면
 * 아무것도 그리지 않는다 — 조립 배너로 물러나지 않는다.
 *
 * 변형(price·ingredient·concern·segment·story)은 세션 성향이 고르고(`creativeFor`), 그 변형 이미지가 없으면 같은
 * 상품의 다른 변형을 쓴다. 다른 상품으로는 넘어가지 않는다.
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
   * 등록돼 있어도 파일이 없을 수 있다. `banner-images.json` 은 목록일 뿐 파일 존재를 보장하지 않는다.
   * 404 를 받으면 그 주소만 기억해 두고 이 칸을 비운다.
   */
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const picked = anyBannerImage(product.product_id, c.variant);
  const image = picked !== null && picked.src !== failedSrc ? picked : null;
  if (image === null) return null;

  /**
   * 로그에 적는 축 (AI 회신 2026-09-10 · bannerConfig 판 이력 banner-2026-09-11).
   * 완성형 배너는 브랜드 크리에이티브라 축 문구 배너가 아니다. `banner_type=new_brand` · `banner_value` 없음으로 기록한다.
   */
  const logged: BannerLog = { banner_type: 'new_brand', banner_value: null };

  return (
    <article
      className={`ad ad--${shape} ad--${image.variant} ad--image`}
      data-variant={image.variant}
      data-concern={c.axis === 'concern' && value ? value : undefined}
      data-product-id={product.product_id}
      // useImpression 이 읽는 필수 `position`(계약 §4.2). 클릭이 slot 을 position 으로 싣으므로 같은 값이어야 노출·클릭이 조인된다
      data-position={slot}
      data-banner-slot={slot}
      data-trait-source={traitSource}
      data-banner-type={logged.banner_type}
      data-banner-value={logged.banner_value ?? undefined}
      data-log-content="recommendation_card"
      data-log-ref={product.product_id}
    >
      <button type="button" className="ad__hit" onClick={() => onSelect(product.product_id, logged)}>
        {/* 완성형 한 장. 글자·가격·배지가 이미지 안에 있다. 접근성 문구만 따로 */}
        <img
          className="ad__image"
          src={image.src}
          alt={`${product.brand_name} ${product.product_name} · ${c.kicker} ${c.head.mark}${c.head.rest}`}
          onError={() => setFailedSrc(image.src)}
        />
      </button>
    </article>
  );
}
