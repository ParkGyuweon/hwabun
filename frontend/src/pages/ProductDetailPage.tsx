import { useMemo, useRef, useState } from 'react';
import Breadcrumb from '../components/product/Breadcrumb';
import ProductGallery from '../components/product/ProductGallery';
import ProductSummary from '../components/product/ProductSummary';
import HighlightList from '../components/product/HighlightList';
import SkinMatchSection from '../components/product/SkinMatchSection';
import IngredientsSection from '../components/product/IngredientsSection';
import SimilarProducts from '../components/product/SimilarProducts';
import Accordion from '../components/common/Accordion';
import ReviewSummary from '../components/review/ReviewSummary';
import ReviewFilterBar from '../components/review/ReviewFilterBar';
import type { ReviewSort } from '../components/review/ReviewFilterBar';
import ReviewList from '../components/review/ReviewList';
import { calcReviewStats, splitIngredients } from '../lib/format';
import productsData from '../mocks/products.sample.json';
import reviewsData from '../mocks/reviews.sample.json';
import type { Product, SkinType } from '../types/product';
import type { Review } from '../types/review';

// JSON 목업은 리터럴 타입으로 추론되므로 unknown 을 거쳐 캐스팅한다.
const products = productsData as unknown as Product[];
const reviews = reviewsData as unknown as Review[];

const SKIN_TYPES: SkinType[] = ['combination', 'dry', 'normal', 'oily'];

interface ProductDetailPageProps {
  productId: string;
}

export default function ProductDetailPage({ productId }: ProductDetailPageProps) {
  const [skinTypeFilter, setSkinTypeFilter] = useState<SkinType | 'all'>('all');
  const [sort, setSort] = useState<ReviewSort>('recent');
  const reviewSectionRef = useRef<HTMLElement>(null);

  const product = useMemo(
    () => products.find((item) => item.product_id === productId),
    [productId],
  );

  const productReviews = useMemo(
    () => reviews.filter((review) => review.product_id === productId),
    [productId],
  );

  /** 샘플 전체 기준 작성자별 리뷰 수. "이 리뷰어의 다른 리뷰" 노출 판단에 쓴다 */
  const authorReviewCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const review of reviews) {
      counts.set(review.author_id, (counts.get(review.author_id) ?? 0) + 1);
    }
    return counts;
  }, []);

  const visibleReviews = useMemo(() => {
    const filtered =
      skinTypeFilter === 'all'
        ? productReviews
        : productReviews.filter((review) => review.skin_type === skinTypeFilter);

    const sorted = [...filtered];
    sorted.sort((a, b) => {
      if (sort === 'rating-desc') return b.rating - a.rating;
      if (sort === 'rating-asc') return a.rating - b.rating;
      return b.submission_time.localeCompare(a.submission_time);
    });
    return sorted;
  }, [productReviews, skinTypeFilter, sort]);

  const stats = useMemo(() => calcReviewStats(productReviews), [productReviews]);

  const similar = useMemo(() => {
    if (!product) return [];
    const primaryCategory = product.category[0];
    return products
      .filter((item) => item.product_id !== product.product_id && item.category[0] === primaryCategory)
      .slice(0, 6);
  }, [product]);

  if (!product) {
    return (
      <main className="page">
        <p className="empty-state">상품을 찾을 수 없습니다. (product_id: {productId})</p>
      </main>
    );
  }

  const ingredientCount = splitIngredients(product.ingredients).length;

  return (
    <main className="page">
      <Breadcrumb items={product.category} />

      <div className="pdp">
        <div className="pdp__media">
          <ProductGallery imageUrl={product.image_url} productName={product.product_name} />
        </div>

        <div className="pdp__info">
          <ProductSummary
            product={product}
            onReviewLinkClick={() =>
              reviewSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }
          />

          <section className="pdp__block">
            <h2 className="pdp__block-title">하이라이트</h2>
            <HighlightList highlights={product.highlights} />
          </section>

          <section className="pdp__block">
            <h2 className="pdp__block-title">내 피부와의 매칭</h2>
            <SkinMatchSection product={product} />
          </section>

          <Accordion
            title="전 성분"
            hint={ingredientCount > 0 ? `${ingredientCount}개` : '정보 없음'}
          >
            <IngredientsSection ingredients={product.ingredients} />
          </Accordion>

          <Accordion title="사용 방법">
            <p className="pdp__prose">
              데이터셋에 사용 방법 필드가 없습니다. 백엔드 연동 시 채워질 영역입니다.
            </p>
          </Accordion>
        </div>
      </div>

      <section className="pdp__section" ref={reviewSectionRef} aria-labelledby="review-heading">
        <h2 id="review-heading" className="pdp__section-title">
          평점 및 리뷰
        </h2>

        <ReviewSummary stats={stats} totalReviewCount={product.review_count} />

        <ReviewFilterBar
          skinTypes={SKIN_TYPES}
          selectedSkinType={skinTypeFilter}
          onSkinTypeChange={setSkinTypeFilter}
          sort={sort}
          onSortChange={setSort}
          resultCount={visibleReviews.length}
        />

        <ReviewList reviews={visibleReviews} authorReviewCounts={authorReviewCounts} />
      </section>

      {similar.length > 0 ? (
        <section className="pdp__section">
          <h2 className="pdp__section-title">비슷한 상품</h2>
          <SimilarProducts products={similar} />
        </section>
      ) : null}
    </main>
  );
}
