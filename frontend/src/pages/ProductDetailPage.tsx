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
import { displayReviewCount, useReviewCounts } from '../lib/reviewStore';
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
  /** 작성자별 리뷰 수 (전체 샘플 기준). "이 리뷰어의 다른 리뷰" 노출 판단에 쓴다 */
  authorReviewCounts: Map<string, number>;
  similar: Product[];
  persona: PersonaProfile | null;
  onSelectProduct: (productId: string) => void;
  onAddToCart: (item: CartItem) => void;
  /** 장바구니를 거치지 않고 이 상품 하나만 주문한다. 로그인 판단과 `add_to_cart` 기록은 App 이 한다 */
  onBuyNow: (item: CartItem, addToCartProps: Record<string, unknown>) => void;
  /** 결제창이 떠 있거나 서버 확인 중. 버튼 연타 방지 */
  buying: boolean;
}

export default function ProductDetailPage({
  product,
  reviews,
  authorReviewCounts,
  similar,
  persona,
  onSelectProduct,
  onAddToCart,
  onBuyNow,
  buying,
}: ProductDetailPageProps) {
  const [filter, setFilter] = useState<ReviewFilter>('all');
  const [sort, setSort] = useState<ReviewSort>('recent');
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const reviewSectionRef = useRef<HTMLElement>(null);

  // 상품이 바뀌면 새 페이지 방문이므로 트리거 상태도 함께 초기화된다
  const pageViewKey = `${product.product_id}:${persona?.persona_id ?? 'anonymous'}`;

  // 클릭 로그만으로는 구매까지 안 간 방문이 빈 세션으로 남아서, 주목 신호를 함께 남긴다
  useSectionView(pageViewKey);
  useScrollDepth(pageViewKey, product.product_id);
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

  const visibleReviews = useMemo(() => {
    const filtered = reviews.filter((review) => {
      if (filter === 'same_skin_type') return persona !== null && review.skin_type === persona.skin_type;
      if (filter === 'same_skin_tone') return persona !== null && review.skin_tone === persona.skin_tone;
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
  // 카드에 적힌 숫자와 같은 값 (lib/reviewStore). 목록에서 본 건수와 상세가 다르면 안 된다
  const catalogReviewCount = displayReviewCount(product.product_id, product.review_count, useReviewCounts());
  /**
   * 고객이 실제로 쓴 리뷰(백엔드)가 정적 표본 위에 더해지면 화면 목록이 카드 숫자보다 많아진다 (2026-09-21).
   * 그때 "표시 중 1건 / 전체 0건" 처럼 적으면 거꾸로 읽힌다. 받은 것을 전부 그리고 있으면 총계는 목록 길이다.
   */
  const reviewCount = catalogReviewCount !== null && reviews.length >= catalogReviewCount ? null : catalogReviewCount;
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
            onBuyNow={onBuyNow}
            buying={buying}
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

      {/*
       * 성분·사용법 섹션은 `data-log-content` 를 섹션 자체에도 단다 (2026-09-21, 데이터 요청).
       * 전에는 아코디언을 펼친 안쪽 블록에만 있어서 섹션의 section_view·section_dwell 은 content_kind 가 비고
       * 같은 섹션의 text_selection·text_copy 만 ingredient_list 를 실었다. content_kind 가 마트 grain 이라
       * 한 섹션이 두 행(18,694명 / 0명)으로 갈렸다. about_product 는 안쪽 블록마다 라벨이 있어 문제가 없다.
       */}
      <section
        className="pdp__section pdp__section--tight"
        data-log-section="ingredients"
        data-log-content="ingredient_list"
      >
        <Accordion
          title="Ingredients"
          hint={ingredientCount > 0 ? `${ingredientCount}개` : '정보 없음'}
          sectionId="ingredients"
        >
          <IngredientsSection
          ingredients={product.ingredients_ko ?? product.ingredients} productId={product.product_id} />
        </Accordion>
      </section>

      <section className="pdp__section pdp__section--tight" data-log-section="how_to_use" data-log-content="usage_guide">
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

        <ReviewSummary stats={stats} totalReviewCount={reviewCount} />

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
