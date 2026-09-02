import { IMAGE_WIDTH_SWATCH, sizedImage } from '../../lib/image';
import { track } from '../../lib/logger';
import type { ProductVariant } from '../../types/product';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface VariantPickerProps {
  productId: string;
  variants: ProductVariant[];
  selectedSkuId: string | null;
  onSelect: (variant: ProductVariant) => void;
}

/**
 * 세포라 상세 페이지의 색상/향 옵션 선택 줄.
 *
 * 옵션 전환은 구매 의도가 뚜렷한 신호라 별도 이벤트로 남긴다.
 */
export default function VariantPicker({
  productId,
  variants,
  selectedSkuId,
  onSelect,
}: VariantPickerProps) {
  if (variants.length <= 1) return null;

  const selected = variants.find((variant) => variant.sku_id === selectedSkuId) ?? variants[0];

  const select = (variant: ProductVariant) => {
    if (variant.sku_id === selected.sku_id) return;
    onSelect(variant);
    track('variant_select', {
      product_id: productId,
      sku_id: variant.sku_id,
      label: variant.label,
    });
  };

  return (
    <div className="variants" data-log-content="variant_option">
      <p className="variants__label">
        <span>Color</span>
        <strong>{selected.label}</strong>
      </p>

      <ul className="variants__list">
        {variants.map((variant) => (
          <li key={variant.sku_id}>
            <button
              type="button"
              className={variant.sku_id === selected.sku_id ? 'is-active' : ''}
              aria-pressed={variant.sku_id === selected.sku_id}
              aria-label={variant.label}
              title={variant.label}
              data-log-action="variant_select"
              onClick={() => select(variant)}
            >
              {/*
                스와치는 첫 화면 오른쪽에 그대로 보인다. lazy 를 걸면 배치가
                끝난 뒤에 받아서 빈 원이 잠깐 보였다가 채워진다. 장당 7KB 라
                한꺼번에 받아도 부담이 없다.
              */}
              <img
                src={sizedImage(variant.swatch_url ?? variant.image_url, IMAGE_WIDTH_SWATCH) ?? PLACEHOLDER}
                alt=""
                aria-hidden="true"
                loading="eager"
                decoding="async"
                onError={(event) => {
                  event.currentTarget.src = PLACEHOLDER;
                }}
              />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
