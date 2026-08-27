import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';
import { skinTypeLabel } from '../../lib/format';
import type { PersonaProfile } from '../../types/persona';
import type { Product } from '../../types/product';

interface AboutProductProps {
  product: Product;
  persona: PersonaProfile | null;
}

/**
 * 세포라의 About the Product 영역.
 *
 * 원본에는 설명 문단 + Skin Type + Skincare Concerns 가 들어간다.
 * 데이터셋에 설명 문단이 없어서 그 자리는 비워두고,
 * 대신 이 프로젝트의 목적인 "내 피부와 맞는가" 판정을 앞에 세운다.
 */
export default function AboutProduct({ product, persona }: AboutProductProps) {
  const hasSkinTypeInfo = product.suitable_skin_types.length > 0;
  const matched = persona !== null && product.suitable_skin_types.includes(persona.skin_type);

  return (
    <div className="about">
      {persona ? (
        <p className={`about__match${matched ? ' is-matched' : ''}`}>
          {!hasSkinTypeInfo
            ? `상품에 피부 타입 표기가 없어 ${skinTypeLabel(persona.skin_type)} 적합 여부를 판단할 수 없습니다`
            : matched
              ? `내 피부 타입(${skinTypeLabel(persona.skin_type)})에 적합한 상품입니다`
              : `내 피부 타입(${skinTypeLabel(persona.skin_type)})은 적합 대상에 포함되어 있지 않습니다`}
        </p>
      ) : null}

      <dl className="about__list">
        <div>
          <dt>Skin Type</dt>
          <dd>
            {hasSkinTypeInfo ? (
              <ul className="chip-list">
                {product.suitable_skin_types.map((type) => (
                  <li key={type}>
                    <Chip tone={persona?.skin_type === type ? 'accent' : 'default'}>
                      {skinTypeLabel(type)}
                    </Chip>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="상품 정보에 피부 타입 표기가 없습니다. 리뷰 통계로 보완 예정입니다." />
            )}
          </dd>
        </div>

        <div>
          <dt>Skincare Concerns</dt>
          <dd>
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
          </dd>
        </div>

        <div>
          <dt>Category</dt>
          <dd>
            <p className="about__text">{product.category.join(' › ')}</p>
          </dd>
        </div>

        {product.size ? (
          <div>
            <dt>Size</dt>
            <dd>
              <p className="about__text">{product.size}</p>
            </dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
