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
    <div className="variants">
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
              <img
                src={sizedImage(variant.image_url, IMAGE_WIDTH_SWATCH) ?? PLACEHOLDER}
                alt=""
                aria-hidden="true"
                loading="lazy"
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
