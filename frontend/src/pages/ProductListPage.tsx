import { useMemo, useState } from 'react';
import ProductCard from '../components/product/ProductCard';
import QuickLook from '../components/product/QuickLook';
import EmptyState from '../components/common/EmptyState';
import { useImpression } from '../hooks/useImpression';
import { useSectionView } from '../hooks/useSectionView';
import { useScrollDepth } from '../hooks/useScrollDepth';
import { useTextSelection } from '../hooks/useTextSelection';
import { useInteractionSignals } from '../hooks/useInteractionSignals';
import { useExitSummary } from '../hooks/useExitSummary';
import { track } from '../lib/logger';
import { deriveSkinTypesFromReviews, skinTypeLabel } from '../lib/format';
import type { PersonaProfile } from '../types/persona';
import type { Product, SkinType } from '../types/product';
import type { Review } from '../types/review';
import type { CartItem } from '../types/cart';

/** 기획전에 올리는 상품 수 */
const PROMO_SIZE = 10;
/** 한 번에 그리는 카드 수. 200개를 한 번에 그리면 노출 로그가 의미를 잃는다 */
const PAGE_SIZE = 24;

type SortKey = 'popular' | 'rating' | 'reviews' | 'price_asc' | 'price_desc';

const SORT_LABEL: Record<SortKey, string> = {
  popular: '인기순',
  rating: '평점 높은순',
  reviews: '리뷰 많은순',
  price_asc: '가격 낮은순',
  price_desc: '가격 높은순',
};

/** 가격 구간. 데이터 분포(최저 $3 ~ 최고 $300)를 보고 잡았다 */
const PRICE_BANDS = [
  { key: 'all', label: '전체', test: () => true },
  { key: 'under20', label: '$20 이하', test: (p: Product) => p.price_usd <= 20 },
  { key: '20to50', label: '$20~50', test: (p: Product) => p.price_usd > 20 && p.price_usd <= 50 },
  { key: '50to100', label: '$50~100', test: (p: Product) => p.price_usd > 50 && p.price_usd <= 100 },
  { key: 'over100', label: '$100 이상', test: (p: Product) => p.price_usd > 100 },
] as const;

type PriceKey = (typeof PRICE_BANDS)[number]['key'];

interface ProductListPageProps {
  products: Product[];
  /** 페르소나 맞춤 추천 근거로 쓴다 */
  reviews: Review[];
  persona: PersonaProfile | null;
  onSelectProduct: (productId: string) => void;
  onAddToCart: (item: CartItem) => void;
  /** 헤더 메뉴에서도 카테고리를 바꾸므로 소유권을 App 에 둔다 */
  category: string;
  onCategoryChange: (category: string) => void;
}

/**
 * 상품 목록 홈.
 *
 * 목록 화면이 없으면 **노출(`product_impression`)과 목록 클릭 신호가 아예 안 생긴다.**
 * 클릭률의 분모가 없다는 뜻이고, 추천이 먹혔는지 판단할 수 없다.
 * 그래서 화면을 화려하게 만드는 것보다 **노출·클릭·좁히기**를 정확히 남기는 데 맞췄다.
 *
 * 기능은 데이터가 받쳐주는 것만 넣었다.
 * 할인·재고·배송은 원본에 값이 없어서 만들지 않는다.
 */
export default function ProductListPage({
  products,
  reviews,
  persona,
  onSelectProduct,
  onAddToCart,
  category,
  onCategoryChange,
}: ProductListPageProps) {
  const [sort, setSort] = useState<SortKey>('popular');
  const [concern, setConcern] = useState('all');
  const [price, setPrice] = useState<PriceKey>('all');
  const [shown, setShown] = useState(PAGE_SIZE);
  /** 요약 창에 띄운 상품. 세포라 Quicklook */
  const [quickLook, setQuickLook] = useState<Product | null>(null);

  /** 카테고리 탭. 실제 데이터에 있는 값만 쓰고 개수를 함께 보여준다 */
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of products) {
      // category = [대분류, 중분류, ...] 이므로 중분류를 탭으로 쓴다
      const key = p.category[1];
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [products]);

  /** 고민 필터 후보. "Good for:" 에서 파생된 값만 존재한다 (156/200) */
  const concerns = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of products) {
      for (const c of p.skincare_concerns) counts.set(c, (counts.get(c) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [products]);

  /**
   * 상품별 리뷰어 피부 타입. 원본 표기(suitable_skin_types)가 없는 132개 상품의
   * 매칭 근거로 쓴다 (AboutProduct 의 파생 표시와 같은 계산이다).
   */
  const reviewSkinTypes = useMemo(() => {
    const byProduct = new Map<string, Review[]>();
    for (const review of reviews) {
      const bucket = byProduct.get(review.product_id) ?? [];
      bucket.push(review);
      byProduct.set(review.product_id, bucket);
    }
    const result = new Map<string, SkinType[]>();
    for (const [pid, list] of byProduct) result.set(pid, deriveSkinTypesFromReviews(list).types);
    return result;
  }, [reviews]);

  /**
   * 기획전. 페르소나가 있으면 그 피부 타입에 맞는 상품을 올린다.
   *
   * 추천 API 가 붙기 전까지의 규칙 기반 대체다. 점수는 설명 가능한 두 축만 쓴다.
   *   피부 타입 일치 +2 (원본 표기 우선, 없으면 리뷰어 분포)
   *   품질 사전확률: 평점(0~1) + 리뷰 수 로그 스케일(0~1)
   * 페르소나가 없으면 이전처럼 신제품·한정판·단독을 인기순으로 올린다.
   */
  const promo = useMemo(() => {
    if (!persona) {
      return products
        .filter((p) => (p.badges ?? []).length > 0)
        .sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
        .slice(0, PROMO_SIZE);
    }

    const score = (p: Product): number => {
      const types = p.suitable_skin_types.length
        ? p.suitable_skin_types
        : (reviewSkinTypes.get(p.product_id) ?? []);
      const match = types.includes(persona.skin_type) ? 2 : 0;
      const quality =
        (p.rating ?? 0) / 5 + Math.min(1, Math.log10((p.review_count ?? 0) + 1) / 5);
      return match + quality;
    };

    return [...products].sort((a, b) => score(b) - score(a)).slice(0, PROMO_SIZE);
  }, [products, persona, reviewSkinTypes]);

  /** 맞춤 기획전은 추천이다. 노출·클릭을 추천 이벤트로 묶는 식별자와 알고리즘 이름 */
  const promoAlgorithm = persona ? 'skin_match_v0' : 'badge_rank_v0';
  const promoRecommendationId = persona ? `rec-promo-${persona.persona_id}` : undefined;

  const filtered = useMemo(() => {
    const band = PRICE_BANDS.find((b) => b.key === price) ?? PRICE_BANDS[0];

    const list = products.filter((p) => {
      if (category !== 'all' && p.category[1] !== category) return false;
      if (concern !== 'all' && !p.skincare_concerns.includes(concern)) return false;
      return band.test(p);
    });

    const sorted = [...list];
    switch (sort) {
      case 'rating':
        sorted.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
        break;
      case 'reviews':
        sorted.sort((a, b) => (b.review_count ?? 0) - (a.review_count ?? 0));
        break;
      case 'price_asc':
        sorted.sort((a, b) => a.price_usd - b.price_usd);
        break;
      case 'price_desc':
        sorted.sort((a, b) => b.price_usd - a.price_usd);
        break;
      default:
        sorted.sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
    }
    return sorted;
  }, [products, category, concern, price, sort]);

  const visible = filtered.slice(0, shown);

  /**
   * 목록 조건이 바뀌면 새 화면으로 본다.
   * 필터를 바꾸면 목록 길이와 내용이 달라지므로 스크롤 도달 깊이와 섹션 노출을
   * 처음부터 다시 세야 한다.
   */
  const pageViewKey = `list:${category}|${concern}|${price}|${sort}`;

  /**
   * 상세 페이지와 같은 훅을 붙인다.
   *
   * 목록은 사용자가 가장 오래 머무는 화면인데 여기에 훅이 없으면
   * **200개를 훑어보는 구간이 로그에서 통째로 빈다.**
   * 어디까지 내려갔는지(scroll_depth), 기획전과 그리드 중 어디에 머물렀는지
   * (section_dwell), 목록에서 막혔는지(dead_click) 를 남긴다.
   */
  useSectionView(pageViewKey);
  useScrollDepth(pageViewKey);
  useTextSelection(pageViewKey);
  useInteractionSignals(pageViewKey);
  useExitSummary(pageViewKey);

  // 목록이 바뀌면 노출을 처음부터 다시 센다
  const promoRef = useImpression({
    // 페르소나가 바뀌면 다른 추천이므로 노출을 다시 센다
    pageViewKey: `promo:${persona?.persona_id ?? 'anonymous'}`,
    eventName: persona ? 'recommendation_impression' : 'product_impression',
    listId: 'promo_pick',
    algorithm: promoAlgorithm,
    recommendationId: promoRecommendationId,
  });
  const gridRef = useImpression({
    pageViewKey,
    eventName: 'product_impression',
    listId: 'list_grid',
  });

  /** 카드 위 Quick Look 버튼. 어느 목록의 몇 번째에서 열었는지 함께 남긴다 */
  const quickLookFrom = (listId: string) => (productId: string) => {
    const source = listId === 'promo_pick' ? promo : visible;
    const position = source.findIndex((p) => p.product_id === productId);
    track('quick_look', {
      product_id: productId,
      entry_source: listId,
      position: position + 1,
    });
    setQuickLook(products.find((p) => p.product_id === productId) ?? null);
  };

  /** 요약 창에서 상세로. 카드 클릭과 같은 이벤트를 남기되 출처만 다르다 */
  const openDetailFromQuickLook = (productId: string) => {
    track('product_click', { product_id: productId, entry_source: 'quick_look' });
    setQuickLook(null);
    onSelectProduct(productId);
  };

  const selectFrom = (listId: string) => (productId: string) => {
    const position = (listId === 'promo_pick' ? promo : visible).findIndex(
      (p) => p.product_id === productId,
    );

    // 맞춤 기획전 클릭은 추천 클릭이기도 하다. 노출과 같은 식별자로 CTR 을 계산한다
    if (listId === 'promo_pick' && promoRecommendationId) {
      track('recommendation_click', {
        recommendation_id: promoRecommendationId,
        list_id: listId,
        algorithm: promoAlgorithm,
        product_id: productId,
        position: position + 1,
      });
    }

    track('product_click', {
      product_id: productId,
      entry_source: listId,
      position: position + 1,
    });
    onSelectProduct(productId);
  };

  /** 무엇으로 좁혔는지가 취향을 말해준다. 필터 종류를 함께 남긴다 */
  const applyFilter = (kind: string, value: string, reset = true) => {
    track('filter_change', { filter_kind: kind, filter_value: value });
    if (reset) setShown(PAGE_SIZE);
  };

  return (
    <main className="page list">
      <section className="list__promo" data-log-section="promo_row">
        <header className="list__promo-head">
          <h2>지금 주목할 상품</h2>
          <p>
            {persona
              ? `${skinTypeLabel(persona.skin_type)} 피부에 맞춘 추천`
              : '신제품 · 한정판 · 세포라 단독'}
          </p>
        </header>
        <ul className="list__row" ref={promoRef as React.Ref<HTMLUListElement>}>
          {promo.map((product, index) => (
            <ProductCard
              key={product.product_id}
              product={product}
              position={index + 1}
              contentKind="product_card"
              onSelect={selectFrom('promo_pick')}
              onQuickLook={quickLookFrom('promo_pick')}
            />
          ))}
        </ul>
      </section>

      <section className="list__catalog" data-log-section="product_grid">
        <nav className="list__tabs" aria-label="카테고리">
          <button
            type="button"
            className={category === 'all' ? 'is-active' : ''}
            onClick={() => {
              onCategoryChange('all');
              applyFilter('category', 'all');
            }}
          >
            전체 <span>{products.length}</span>
          </button>
          {categories.map(([name, count]) => (
            <button
              key={name}
              type="button"
              className={category === name ? 'is-active' : ''}
              onClick={() => {
                onCategoryChange(name);
                applyFilter('category', name);
              }}
            >
              {name} <span>{count}</span>
            </button>
          ))}
        </nav>

        <div className="list__controls" data-log-section="list_controls">
          <div className="list__filters">
            <label>
              고민
              <select
                value={concern}
                onChange={(event) => {
                  setConcern(event.target.value);
                  applyFilter('concern', event.target.value);
                }}
              >
                <option value="all">전체</option>
                {concerns.map(([name, count]) => (
                  <option key={name} value={name}>
                    {name} ({count})
                  </option>
                ))}
              </select>
            </label>

            <div className="list__bands" role="group" aria-label="가격대">
              {PRICE_BANDS.map((band) => (
                <button
                  key={band.key}
                  type="button"
                  className={price === band.key ? 'is-active' : ''}
                  onClick={() => {
                    setPrice(band.key);
                    applyFilter('price', band.key);
                  }}
                >
                  {band.label}
                </button>
              ))}
            </div>
          </div>

          <label className="list__sort">
            정렬
            <select
              value={sort}
              onChange={(event) => {
                const next = event.target.value as SortKey;
                setSort(next);
                setShown(PAGE_SIZE);
                track('sort_change', { sort_key: next });
              }}
            >
              {Object.entries(SORT_LABEL).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="list__count" aria-live="polite">
          {filtered.length}개 상품
        </p>

        {visible.length === 0 ? (
          <EmptyState message="조건에 맞는 상품이 없습니다. 필터를 넓혀 보세요." />
        ) : (
          <ul className="list__grid" ref={gridRef as React.Ref<HTMLUListElement>}>
            {visible.map((product, index) => (
              <ProductCard
                key={product.product_id}
                product={product}
                position={index + 1}
                onSelect={selectFrom('list_grid')}
                onQuickLook={quickLookFrom('list_grid')}
              />
            ))}
          </ul>
        )}

        {shown < filtered.length ? (
          <button
            type="button"
            className="list__more"
            onClick={() => setShown((prev) => prev + PAGE_SIZE)}
          >
            더 보기 ({filtered.length - shown}개 남음)
          </button>
        ) : null}
      </section>

      {quickLook ? (
        <QuickLook
          product={quickLook}
          onAddToCart={onAddToCart}
          onClose={() => setQuickLook(null)}
          onOpenDetail={openDetailFromQuickLook}
        />
      ) : null}
    </main>
  );
}
