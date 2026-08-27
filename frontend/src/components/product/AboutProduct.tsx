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
 * 설명 문단은 세포라 원문(영문)을 그대로 싣고,
 * 그 아래에 이 프로젝트의 목적인 "내 피부와 맞는가" 판정용 속성을 붙인다.
 */
export default function AboutProduct({ product, persona }: AboutProductProps) {
  const hasSkinTypeInfo = product.suitable_skin_types.length > 0;
  const description = product.description;

  return (
    <div className="about">
      {description ? (
        <div className="about__prose">
          {description.what_it_is ? (
            <section>
              <h3>What it is</h3>
              <p>{description.what_it_is}</p>
            </section>
          ) : null}

          {description.highlighted_ingredients.length > 0 ? (
            <section>
              <h3>Highlighted Ingredients</h3>
              <ul>
                {description.highlighted_ingredients.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {description.ingredient_callouts ? (
            <section>
              <h3>Ingredient Callouts</h3>
              <p>{description.ingredient_callouts}</p>
            </section>
          ) : null}

          {description.what_else ? (
            <section>
              <h3>What Else You Need to Know</h3>
              <p>{description.what_else}</p>
            </section>
          ) : null}

          {description.clinical_results ? (
            <section>
              <h3>Clinical Results</h3>
              <p className="about__pre">{description.clinical_results}</p>
            </section>
          ) : null}
        </div>
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
