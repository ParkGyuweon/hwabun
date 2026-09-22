import { IMAGE_WIDTH_SWATCH, sizedImage } from '../../lib/image';
import { formatKrw } from '../../lib/format';
import { variantLabelKo } from '../../lib/localize';
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
 * 옵션 종류 (계약 event-properties-schema §3.7 `variant_kind`: size · shade · other).
 *
 * 계약은 원천의 `variation_type`(Size → size, Color → shade)을 매핑하라고 하는데, 수집본·백엔드 옵션 어디에도
 * 그 필드가 없다. 그래서 라벨에서 용량 단위(ml · oz · g · Mini/Standard/Jumbo 등)가 읽히면 `size`, 아니면
 * `other` 로 둔다. `shade` 는 근거가 없어 붙이지 않는다 — 틀린 톤 신호보다 빈 값이 낫다.
 * `size` 는 성향 표(contracts/user-trait-weights.json)에서 가격 성향 +0.5 다.
 */
const SIZE_LABEL = /(\d+(\.\d+)?\s*(ml|oz|fl\.? ?oz|g|kg|l)\b)|\b(mini|standard|jumbo|travel|full[- ]size|refill|value size|size)\b/i;

export function variantKindOf(label: string): 'size' | 'shade' | 'other' {
  return SIZE_LABEL.test(label) ? 'size' : 'other';
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
      previous_sku_id: selected.sku_id,
      variant_kind: variantKindOf(variant.label),
    });
  };

  return (
    <div className="variants" data-log-content="variant_option">
      <p className="variants__label">
        <span>옵션</span>
        <strong>{variantLabelKo(selected.label)}</strong>
        {/* 옵션마다 값이 다르면(대용량·리필) 고른 옵션 값을 이름 옆에. 위의 큰 가격도 같은 값으로 바뀐다 */}
        {typeof selected.price_krw === 'number' && selected.price_krw > 0 && variants.some((v) => v.price_krw !== selected.price_krw) ? (
          <span className="variants__price">{formatKrw(selected.sale_price_krw && selected.sale_price_krw < selected.price_krw ? selected.sale_price_krw : selected.price_krw)}</span>
        ) : null}
      </p>

      <ul className="variants__list">
        {variants.map((variant) => (
          <li key={variant.sku_id}>
            <button
              type="button"
              className={variant.sku_id === selected.sku_id ? 'is-active' : ''}
              aria-pressed={variant.sku_id === selected.sku_id}
              aria-label={variantLabelKo(variant.label)}
              title={variantLabelKo(variant.label)}
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
