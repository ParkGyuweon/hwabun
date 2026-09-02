import Chip from '../common/Chip';
import EmptyState from '../common/EmptyState';
import { deriveSkinTypesFromReviews, skinTypeLabel } from '../../lib/format';
import type { PersonaProfile } from '../../types/persona';
import type { Product } from '../../types/product';
import type { Review } from '../../types/review';

interface AboutProductProps {
  product: Product;
  persona: PersonaProfile | null;
  /** 상품 정보에 피부 타입 표기가 없을 때 분포를 뽑아 쓴다 */
  reviews: Review[];
}

/**
 * 세포라의 About the Product 영역.
 *
 * 설명 문단은 세포라 원문(영문)을 그대로 싣고,
 * 그 아래에 이 프로젝트의 목적인 "내 피부와 맞는가" 판정용 속성을 붙인다.
 */
export default function AboutProduct({ product, persona, reviews }: AboutProductProps) {
  const hasSkinTypeInfo = product.suitable_skin_types.length > 0;
  // 상품 200개 중 132개에 표기가 없다. 그 자리는 리뷰어 분포로 대신한다
  const derivedSkinTypes = hasSkinTypeInfo
    ? null
    : deriveSkinTypesFromReviews(reviews);
  const description = product.description;

  return (
    <div className="about">
      {description ? (
        <div className="about__prose">
          {description.what_it_is ? (
            <section data-log-content="what_it_is">
              <h3>What it is</h3>
              <p>{description.what_it_is}</p>
            </section>
          ) : null}

          {/*
            키가 아예 없는 상품이 65 / 200 이다. 옵셔널 체크 없이 .length 를
            부르면 렌더가 던지고 React 가 트리를 통째로 버려서 화면이 완전히
            빈다. 위아래 블록은 모두 존재 확인을 하는데 이 줄만 빠져 있었다.
          */}
          {description.highlighted_ingredients?.length ? (
            <section data-log-content="ingredient_list" data-log-ref="highlighted">
              <h3>Highlighted Ingredients</h3>
              <ul>
                {description.highlighted_ingredients.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {description.ingredient_callouts ? (
            <section data-log-content="ingredient_callout">
              <h3>Ingredient Callouts</h3>
              <p>{description.ingredient_callouts}</p>
            </section>
          ) : null}

          {description.what_else ? (
            <section data-log-content="what_else">
              <h3>What Else You Need to Know</h3>
              <p>{description.what_else}</p>
            </section>
          ) : null}

          {description.clinical_results ? (
            <section data-log-content="clinical_claim">
              <h3>Clinical Results</h3>
              <p className="about__pre">{description.clinical_results}</p>
            </section>
          ) : null}

          {/*
           * 브랜드 소개.
           *
           * 데이터에 들어 있는데 화면에 없었다. AI 파트가 상품 벡터에 brand 블록을
           * 넣어 추천 정확도를 11.4% -> 23.6% 로 올렸는데, 정작 브랜드 콘텐츠를
           * 얼마나 보는지는 아무도 수집하고 있지 않았다.
           * content_kind 21종 중 brand_story 만 화면에 없어서 대시보드의 콘텐츠
           * 주목도 표에서도 이 줄만 영원히 비어 있었다.
           */}
          {description.brand_story ? (
            <section data-log-content="brand_story">
              <h3>About the Brand</h3>
              <p className="about__pre">{description.brand_story}</p>
            </section>
          ) : null}
        </div>
      ) : null}

      <dl className="about__list">
        <div data-log-content="persona_match" data-log-ref="skin_type">
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
            ) : derivedSkinTypes && derivedSkinTypes.types.length > 0 ? (
              /**
               * 브랜드 표기가 아니라 리뷰어 분포다.
               * 같은 칩으로 보이면 출처를 착각하므로 근거를 반드시 같이 적는다.
               */
              <>
                <ul className="chip-list">
                  {derivedSkinTypes.types.map((type) => (
                    <li key={type}>
                      <Chip tone={persona?.skin_type === type ? 'accent' : 'default'}>
                        {skinTypeLabel(type)}{' '}
                        {Math.round((derivedSkinTypes.shares.get(type) ?? 0) * 100)}%
                      </Chip>
                    </li>
                  ))}
                </ul>
                <p className="about__derived-note">
                  상품 정보에 표기가 없어 리뷰 {derivedSkinTypes.sampleSize}건의 작성자
                  피부 타입으로 대신 보여줍니다.
                </p>
              </>
            ) : (
              <EmptyState message="상품 정보에 피부 타입 표기가 없고, 리뷰에도 피부 타입 정보가 없습니다." />
            )}
          </dd>
        </div>

        <div data-log-content="persona_match" data-log-ref="concerns">
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

        <div data-log-content="product_meta" data-log-ref="category">
          <dt>Category</dt>
          <dd>
            <p className="about__text">{product.category.join(' › ')}</p>
          </dd>
        </div>

        {product.size ? (
          <div data-log-content="product_meta" data-log-ref="size">
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
