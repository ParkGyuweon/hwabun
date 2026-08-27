import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';
import { skinTypeLabel } from '../../lib/format';
import type { Product } from '../../types/product';

interface SkinMatchSectionProps {
  product: Product;
}

/**
 * 피부 타입 / 피부 고민 매칭 영역.
 *
 * suitable_skin_types 는 highlights 에서 파생된 필드라 절반 가까운 상품이 빈 배열이다.
 * 섹션을 통째로 숨기지 않고 비어 있다는 사실을 드러내는 쪽으로 처리한다.
 */
export default function SkinMatchSection({ product }: SkinMatchSectionProps) {
  return (
    <div className="skin-match">
      <div className="skin-match__block">
        <h3>적합 피부 타입</h3>
        {product.suitable_skin_types.length > 0 ? (
          <ul className="chip-list">
            {product.suitable_skin_types.map((type) => (
              <li key={type}>
                <Chip tone="accent">{skinTypeLabel(type)}</Chip>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message="상품 정보에 피부 타입 표기가 없습니다. 리뷰 통계로 보완 예정입니다." />
        )}
      </div>

      <div className="skin-match__block">
        <h3>피부 고민</h3>
        {product.skincare_concerns.length > 0 ? (
          <ul className="chip-list">
            {product.skincare_concerns.map((concern) => (
              <li key={concern}>
                <Chip tone="muted">{concern}</Chip>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message="등록된 피부 고민 정보가 없습니다." />
        )}
      </div>
    </div>
  );
}
