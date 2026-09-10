import { formatPrice } from '../../lib/format';
import { discountPercent, effectivePrice, hasDiscount } from '../../lib/discount';
import type { Product } from '../../types/product';

interface PriceTagProps {
  product: Pick<Product, 'price_usd' | 'sale_price_usd' | 'discount_label'>;
  /** sm 카드 · md 요약·퀵룩 · lg 배너 가격 축 */
  size?: 'sm' | 'md' | 'lg';
  /** 할인 이유("입점 기념")까지 보일지. 카드에서는 자리가 없어 끈다 */
  showLabel?: boolean;
  className?: string;
}

/**
 * 가격 한 덩어리. 할인이 있으면 **할인율 · 할인가 · 취소선 정가** 순서다.
 *
 * 할인율을 앞에 두는 이유: 올리브영·세포라 모두 이 순서고, 사람 눈이 가격보다 %를 먼저 읽는다.
 * 할인이 없으면 가격 하나만 그린다. 가격 표기가 화면마다 흩어져 있으면 할인 방식이 바뀔 때
 * 여섯 군데를 고쳐야 해서 여기 한 곳으로 모았다.
 */
export default function PriceTag({ product, size = 'md', showLabel = false, className = '' }: PriceTagProps) {
  const now = formatPrice(effectivePrice(product));
  if (!hasDiscount(product)) {
    return (
      <span className={`price price--${size} ${className}`.trim()}>
        <strong className="price__now">{now}</strong>
      </span>
    );
  }
  return (
    <span className={`price price--${size} price--sale ${className}`.trim()}>
      <em className="price__rate">{discountPercent(product)}%</em>
      <strong className="price__now">{now}</strong>
      <s className="price__was">{formatPrice(product.price_usd)}</s>
      {showLabel && product.discount_label ? <span className="price__label">{product.discount_label}</span> : null}
    </span>
  );
}
