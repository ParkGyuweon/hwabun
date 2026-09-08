import { useEffect, useMemo, useRef, useState } from 'react';
import ProductGallery from '../components/product/ProductGallery';
import ProductSummary from '../components/product/ProductSummary';
import HighlightGrid from '../components/product/HighlightGrid';
import AboutProduct from '../components/product/AboutProduct';
import IngredientsSection from '../components/product/IngredientsSection';
import SimilarProducts from '../components/product/SimilarProducts';
import Accordion from '../components/common/Accordion';
import ReviewSummary from '../components/review/ReviewSummary';
import ReviewFilterBar from '../components/review/ReviewFilterBar';
import type { ReviewFilter, ReviewSort } from '../components/review/ReviewFilterBar';
import ReviewList from '../components/review/ReviewList';
import FeedbackPanel from '../components/feedback/FeedbackPanel';
import { calcReviewStats, splitIngredients } from '../lib/format';
import { track } from '../lib/logger';
import { useSectionView } from '../hooks/useSectionView';
import { useScrollDepth } from '../hooks/useScrollDepth';
import { useTextSelection } from '../hooks/useTextSelection';
import { useInteractionSignals } from '../hooks/useInteractionSignals';
import { useExitSummary } from '../hooks/useExitSummary';
import type { PersonaProfile } from '../types/persona';
import type { Product, ProductVariant } from '../types/product';
import type { Review } from '../types/review';
import type { CartItem } from '../types/cart';

interface ProductDetailPageProps {
  product: Product;
  reviews: Review[];
  allReviews: Review[];
  similar: Product[];
  persona: PersonaProfile | null;
  onSelectProduct: (productId: string) => void;
  onAddToCart: (item: CartItem) => void;
}

export default function ProductDetailPage({
  product,
  reviews,
  allReviews,
  similar,
  persona,
  onSelectProduct,
  onAddToCart,
}: ProductDetailPageProps) {
  const [filter, setFilter] = useState<ReviewFilter>('all');
  const [sort, setSort] = useState<ReviewSort>('recent');
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const reviewSectionRef = useRef<HTMLElement>(null);

  // 상품이 바뀌면 새 페이지 방문이므로 트리거 상태도 함께 초기화된다
  const pageViewKey = `${product.product_id}:${persona?.persona_id ?? 'anonymous'}`;

  // 클릭 로그만으로는 구매까지 안 간 방문이 빈 세션으로 남아서, 주목 신호를 함께 남긴다
  useSectionView(pageViewKey);
  useScrollDepth(pageViewKey);
  useTextSelection(pageViewKey);
  useInteractionSignals(pageViewKey);
  useExitSummary(pageViewKey);

  useEffect(() => {
    setFilter('all');
    setSort('recent');
    setSelectedVariant(null);
  }, [product.product_id]);

  /** 옵션을 고르면 그 옵션 이미지가 대표 이미지 자리를 대신한다 */
  const heroImageUrl = selectedVariant?.image_url ?? product.image_url;
  const selectedSkuId = selectedVariant?.sku_id ?? product.sku_id;

  /** 샘플 전체 기준 작성자별 리뷰 수. "이 리뷰어의 다른 리뷰" 노출 판단에 쓴다 */
  const authorReviewCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const review of allReviews) {
      counts.set(review.author_id, (counts.get(review.author_id) ?? 0) + 1);
    }
    return counts;
  }, [allReviews]);

  const visibleReviews = useMemo(() => {
    const filtered = reviews.filter((review) => {
      if (filter === 'same_skin_type') return persona !== null && review.skin_type === persona.skin_type;
      if (filter === 'same_skin_tone') return persona !== null && review.skin_tone === persona.skin_tone;
      if (filter === 'recommended') return review.is_recommended === true;
      return true;
    });

    const sorted = [...filtered];
    sorted.sort((a, b) => {
      if (sort === 'rating-desc') return b.rating - a.rating;
      if (sort === 'rating-asc') return a.rating - b.rating;
      return b.submission_time.localeCompare(a.submission_time);
    });
    return sorted;
  }, [reviews, filter, sort, persona]);

  const stats = useMemo(() => calcReviewStats(reviews), [reviews]);
  const ingredientCount = splitIngredients(product.ingredients).length;

  /** 추천 노출과 클릭을 같은 요청으로 묶는 식별자. 추천 API 가 붙으면 서버 발급값으로 교체한다 */
  const recommendationId = `rec-${product.product_id}-${persona?.persona_id ?? 'anonymous'}`;

  return (
    <main className="page">

      <section className="pdp" data-log-section="product_hero">
        <div className="pdp__media">
          <ProductGallery
            imageUrl={heroImageUrl}
            images={product.images}
            productName={product.product_name}
            productId={product.product_id}
          />
        </div>

        <div className="pdp__info">
          <ProductSummary
            product={product}
            selectedSkuId={selectedSkuId}
            onVariantSelect={setSelectedVariant}
            onAddToCart={onAddToCart}
            onReviewLinkClick={() => {
              track('review_expand', { product_id: product.product_id, target: 'jump_to_reviews' });
              reviewSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          />
        </div>
      </section>

      <section className="pdp__section" data-log-section="highlights">
        <h2 className="pdp__section-title">Highlights</h2>
        <HighlightGrid highlights={product.highlights} />
      </section>

      <section className="pdp__section" data-log-section="about_product">
        <h2 className="pdp__section-title">About the Product</h2>
        <AboutProduct product={product} persona={persona} reviews={reviews} />
      </section>

      <section className="pdp__section pdp__section--tight" data-log-section="ingredients">
        <Accordion
          title="Ingredients"
          hint={ingredientCount > 0 ? `${ingredientCount}개` : '정보 없음'}
          sectionId="ingredients"
        >
          <IngredientsSection ingredients={product.ingredients} productId={product.product_id} />
        </Accordion>
      </section>

      <section className="pdp__section pdp__section--tight" data-log-section="how_to_use">
        <Accordion title="How to Use" sectionId="how_to_use" contentKind="usage_guide">
          {product.description?.suggested_usage ? (
            <p className="pdp__prose pdp__prose--pre">{product.description.suggested_usage}</p>
          ) : (
            <p className="pdp__prose">등록된 사용 방법 정보가 없습니다.</p>
          )}
        </Accordion>
      </section>

      {similar.length > 0 ? (
        <section className="pdp__section" data-log-section="similar_products">
          <h2 className="pdp__section-title">More Like This</h2>
          <SimilarProducts
            products={similar}
            listId="similar_products"
            recommendationId={recommendationId}
            algorithm="same_category_v0"
            onSelect={onSelectProduct}
          />
        </section>
      ) : null}

      <section
        className="pdp__section"
        data-log-section="reviews"
        ref={reviewSectionRef}
        aria-labelledby="review-heading"
      >
        <h2 id="review-heading" className="pdp__section-title">
          Ratings &amp; Reviews
        </h2>

        <ReviewSummary stats={stats} totalReviewCount={product.review_count} />

        <ReviewFilterBar
          persona={persona}
          filter={filter}
          onFilterChange={setFilter}
          sort={sort}
          onSortChange={setSort}
          resultCount={visibleReviews.length}
        />

        <ReviewList
          reviews={visibleReviews}
          persona={persona}
          authorReviewCounts={authorReviewCounts}
        />
      </section>

      {/*
        의견 남기기 — 리뷰 섹션 안에 두지 않는다. 리뷰는 구매자의 평가이고 이건 누구나 남기는
        제품 개선 의견이라 성격이 다르다. 로그 섹션은 계약 enum 안의 about_product 를 재사용한다
        (content_kind=brand_story: 브랜드와의 관계를 다루는 자리라는 뜻).
      */}
      <section className="pdp__section" data-log-section="about_product" aria-labelledby="feedback-heading">
        <h2 id="feedback-heading" className="pdp__section-title">
          사장님께 의견 보내기
        </h2>
        <FeedbackPanel product={product} persona={persona} />
      </section>
    </main>
  );
}
