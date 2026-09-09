import { useCallback, useEffect, useMemo, useState } from 'react';
import ProductCard from '../components/product/ProductCard';
import QuickLook from '../components/product/QuickLook';
import EmptyState from '../components/common/EmptyState';
import { useImpression } from '../hooks/useImpression';
import { useTrait } from '../hooks/useTrait';
import { BANNER_RESERVED, BANNER_SLOTS, MAIN_SLOTS } from '../lib/bannerConfig';
import { buildRecommendation } from '../lib/recommendMock';
import { useSectionView } from '../hooks/useSectionView';
import { useScrollDepth } from '../hooks/useScrollDepth';
import { useTextSelection } from '../hooks/useTextSelection';
import { useInteractionSignals } from '../hooks/useInteractionSignals';
import { useExitSummary } from '../hooks/useExitSummary';
import { setNextProductViewEntry, track } from '../lib/logger';
import { labelKo } from '../lib/formLabels';
import AdBanner from '../components/banner/AdBanner';
import type { BannerAxis } from '../lib/bannerCreative';
import { deriveSkinTypesFromReviews, skinTypeLabel } from '../lib/format';
import type { PersonaProfile } from '../types/persona';
import type { Product, SkinType } from '../types/product';
import type { Review } from '../types/review';
import type { CartItem } from '../types/cart';

/** 기획전(메인 칸)에 올리는 상품 수. 계약 §5 `k` */
const PROMO_SIZE = MAIN_SLOTS;
/**
 * 한 번에 그리는 카드 수. 200개를 한 번에 그리면 노출 로그가 의미를 잃는다.
 * 넓은 화면의 열 수(5)의 배수로 둬서 마지막 줄이 꽉 차게 한다.
 */
const PAGE_SIZE = 25;

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

/** 인기순 정렬 키. 순위 없는 신상품 −1, 순위 있는 상품은 그 순위, 그 밖은 999 */
function popularKey(p: Product): number {
  if (p.rank !== undefined) return p.rank;
  return (p.badges ?? []).includes('new') ? -1 : 999;
}

interface ProductListPageProps {
  products: Product[];
  /** 페르소나 맞춤 추천 근거로 쓴다 */
  reviews: Review[];
  persona: PersonaProfile | null;
  onSelectProduct: (productId: string) => void;
  onAddToCart: (item: CartItem) => void;
  /** 장바구니에 담긴 상품. 맞춤 기획전(추천)에서 뺀다 */
  cartProductIds: Set<string>;
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
  cartProductIds,
  category,
  onCategoryChange,
}: ProductListPageProps) {
  const [sort, setSort] = useState<SortKey>('popular');
  const [concern, setConcern] = useState('all');
  const [price, setPrice] = useState<PriceKey>('all');
  const [shown, setShown] = useState(PAGE_SIZE);
  /**
   * 그리드 노드와 실제 열 수.
   * 열 수를 auto-fill 로 잡아서 화면 폭마다 달라진다. 그리는 개수를 고정해 두면
   * 마지막 줄에 빈 자리가 남아 진열이 끊긴 것처럼 보인다.
   */
  const [gridNode, setGridNode] = useState<HTMLUListElement | null>(null);
  const [columns, setColumns] = useState(1);
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
   * 추천 응답 — 히어로 1 + 배너 6 + 메인 10 이 **한 응답**에서 나온다 (계약 §5-1).
   *
   * 백엔드 서빙이 없어 프론트 목(`lib/recommendMock`)이 같은 형태를 만든다.
   * 어느 축을 배너에 올릴지는 세션 성향(`useTrait`)이 정해 `axes` 로 넘긴다.
   * 담은 상품은 후보에서 뺀다. 빼면 다음 순위가 올라와 칸 수는 유지된다.
   */
  const trait = useTrait();
  const recommendation = useMemo(
    () =>
      buildRecommendation({
        products,
        persona,
        excluded: cartProductIds,
        reviewSkinTypes,
        axes: trait.axes,
        k: PROMO_SIZE,
        bannerSlots: BANNER_SLOTS,
        reserved: BANNER_RESERVED,
      }),
    [products, persona, reviewSkinTypes, cartProductIds, trait.axes],
  );

  const productsById = useMemo(() => new Map(products.map((p) => [p.product_id, p])), [products]);

  const promo = useMemo(
    () =>
      recommendation.items
        .map((item) => productsById.get(item.product_id))
        .filter((p): p is Product => p !== undefined),
    [recommendation, productsById],
  );

  /**
   * 광고 배너 칸.
   *
   * 무엇을 올릴지는 추천 응답(`recommendation.hero` · `recommendation.banners`)이 정하고,
   * 어떻게 보일지는 `AdBanner` 가 정한다. 뽑는 규칙과 그림을 한 파일에 두면 API 가 붙을 때
   * 그림까지 같이 뜯어야 한다. 그래서 여기서는 응답을 배너 칸으로 옮기기만 한다.
   *
   * 축(`banner_type`)은 세션 성향이 고르고, 전용 칸 2개는 신규 브랜드가 받는다 (계약 §5-1).
   * `/api/recommend` 가 붙으면 `buildRecommendation` 자리만 fetch 로 바뀐다.
   */
  const bannerSlots = useMemo(() => {
    const slots: Array<{ product: Product; banner_type: BannerAxis; banner_value: string | null }> = [];
    if (recommendation.hero) {
      const hero = productsById.get(recommendation.hero.product_id);
      if (hero) {
        slots.push({
          product: hero,
          banner_type: recommendation.hero.banner_type as BannerAxis,
          banner_value: recommendation.hero.banner_value,
        });
      }
    }
    for (const b of recommendation.banners) {
      const product = productsById.get(b.product_id);
      if (product) {
        slots.push({ product, banner_type: b.banner_type as BannerAxis, banner_value: b.banner_value });
      }
    }
    return slots;
  }, [recommendation, productsById]);

  /** 맞춤 기획전은 추천이다. 노출·클릭을 추천 이벤트로 묶는 식별자와 알고리즘 이름 */
  const promoAlgorithm = recommendation.model_version;
  const promoRecommendationId = persona ? `rec-promo-${persona.persona_id}` : undefined;
  /** 배너·히어로는 별도 목록으로 센다. 같은 응답이라 식별자는 공유한다 */
  const bannerAlgorithm = `${recommendation.model_version}/banner`;

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
        /**
         * 인기순. 순위가 없는 상품은 둘로 나뉜다.
         *   - `new` 배지가 있는 상품(브랜드가 방금 등록한 것, 시드 브랜드)은 **맨 앞**.
         *     사장님이 등록하면 쇼핑몰에 바로 보여야 "등록했다" 는 게 성립한다.
         *   - 그 밖에 순위가 없는 상품은 맨 뒤.
         * 점수순 정렬이 아니다 — 추천 점수로 목록을 줄세우면 교차 브랜드 발견이 죽는다(exposure-role.md).
         */
        sorted.sort((a, b) => popularKey(a) - popularKey(b));
    }
    return sorted;
  }, [products, category, concern, price, sort]);

  /**
   * 마지막 줄을 채우고 끊는다.
   * 다 보여줄 수 있으면 자르지 않는다. 남는 게 열 수보다 적어도 최소 한 줄은 그린다.
   */
  const visibleCount =
    shown >= filtered.length
      ? filtered.length
      : Math.min(filtered.length, Math.max(columns, Math.floor(shown / columns) * columns));
  const visible = filtered.slice(0, visibleCount);

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
  const impressionRef = useImpression({
    pageViewKey,
    eventName: 'product_impression',
    listId: 'list_grid',
  });
  /**
   * 배너 노출. `banner_impression` 은 계약 enum 등록 전이라 (lib/bannerConfig)
   * `recommendation_impression` 에 배너 property 를 얹어 보낸다. 노출은 분모일 뿐이다.
   */
  const heroRef = useImpression({
    pageViewKey: `hero:${persona?.persona_id ?? 'anonymous'}:${trait.trait_source}`,
    eventName: 'recommendation_impression',
    listId: 'hero_banner',
    algorithm: bannerAlgorithm,
    recommendationId: promoRecommendationId,
  });
  const bannerRef = useImpression({
    pageViewKey: `banner:${persona?.persona_id ?? 'anonymous'}:${trait.trait_source}`,
    eventName: 'recommendation_impression',
    listId: 'banner_row',
    algorithm: bannerAlgorithm,
    recommendationId: promoRecommendationId,
  });

  /** 배너·히어로 클릭. 추천 클릭 + 상품 클릭. entry_source 는 계약 enum 안의 promo_pick 을 쓴다 */
  const selectFromBanner = (listId: 'hero_banner' | 'banner_row') => (productId: string) => {
    const banner =
      listId === 'hero_banner'
        ? recommendation.hero && recommendation.hero.product_id === productId
          ? { ...recommendation.hero, slot: 0 }
          : null
        : (recommendation.banners.find((b) => b.product_id === productId) ?? null);

    track('recommendation_click', {
      ...(promoRecommendationId ? { recommendation_id: promoRecommendationId } : {}),
      list_id: listId,
      algorithm: bannerAlgorithm,
      product_id: productId,
      position: banner ? banner.slot : null,
      ...(banner
        ? {
            banner_type: banner.banner_type,
            ...(banner.banner_value !== null ? { banner_value: banner.banner_value } : {}),
            banner_slot: banner.slot,
            trait_source: trait.trait_source,
          }
        : {}),
    });
    track('product_click', { product_id: productId, entry_source: 'promo_pick', position: banner ? banner.slot : null });
    onSelectProduct(productId);
  };

  /**
   * 그리드의 실제 열 수.
   *
   * 열 수를 auto-fill 로 잡아서 화면 폭마다 달라진다. 그리는 개수를 고정해 두면
   * 마지막 줄에 빈 자리가 남아 진열이 끊긴 것처럼 보인다. CSS 에서 계산된
   * 열 수를 직접 읽어서 그 배수만큼만 그린다.
   */
  // useImpression 의 ref 와 측정용 상태에 같은 노드를 함께 넘긴다
  const setGridRef = useCallback(
    (node: HTMLUListElement | null) => {
      (impressionRef as React.MutableRefObject<HTMLElement | null>).current = node;
      setGridNode(node);
    },
    [impressionRef],
  );

  useEffect(() => {
    if (!gridNode) return;

    const measure = () => {
      const tracks = window.getComputedStyle(gridNode).gridTemplateColumns;
      setColumns(Math.max(1, tracks.split(' ').filter(Boolean).length));
    };

    measure();

    /**
     * 화면 폭이 바뀌면 열 수도 바뀐다.
     * ResizeObserver 는 필터를 접었다 펴는 것처럼 창 크기와 무관한 변화까지 잡고,
     * resize 는 관찰자가 깨어나지 않는 환경을 위한 보완이다.
     */
    const observer = new ResizeObserver(measure);
    observer.observe(gridNode);
    window.addEventListener('resize', measure);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [gridNode]);

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
      // 곧 열릴 상세의 product_view 에 같은 식별자를 싣는다 (Jira 210)
      setNextProductViewEntry({
        product_id: productId,
        recommendation_id: promoRecommendationId,
        list_id: listId,
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
      {/*
        배너 영역에는 data-log-section 을 붙이지 않는다. 계약 `section_id` enum
        (event-properties-schema §3.1) 에 배너 값이 없고, 아래 상품 줄과 같은 `promo_row` 를
        쓰면 section_view 가 두 번 세어진다. 배너는 `banner_slot`·`banner_type` 으로 이미
        식별된다. enum 에 `banner_row` 가 추가되면 그때 붙인다 (데이터 파트 요청 목록).
      */}
      {bannerSlots.length > 0 ? (
        <section className="ads">
          <div className="ads__hero" ref={heroRef as React.Ref<HTMLDivElement>}>
            <AdBanner
              product={bannerSlots[0].product}
              axis={bannerSlots[0].banner_type}
              value={bannerSlots[0].banner_value}
              shape="hero"
              skinTone={persona?.skin_tone}
              slot={1}
              onSelect={selectFromBanner('hero_banner')}
            />
          </div>
          {bannerSlots.length > 1 ? (
            <ul className="ads__row" ref={bannerRef as React.Ref<HTMLUListElement>}>
              {bannerSlots.slice(1).map((b, i) => (
                <li key={b.product.product_id}>
                  <AdBanner
                    product={b.product}
                    axis={b.banner_type}
                    value={b.banner_value}
                    shape="card"
                    skinTone={persona?.skin_tone}
                    slot={i + 2}
                    onSelect={selectFromBanner('banner_row')}
                  />
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <section className="list__promo" data-log-section="promo_row">
        <header className="list__promo-head">
          <h2>지금 주목할 상품</h2>
          <p>
            {persona
              ? `${skinTypeLabel(persona.skin_type)} 피부에 맞춘 추천`
              : '신제품 · 한정판 · BLOOM 단독'}
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
                    {labelKo(name)} ({count})
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

          <div className="list__right">
            <p className="list__count" aria-live="polite">
              {filtered.length}개 상품
            </p>
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
        </div>

        {visible.length === 0 ? (
          <EmptyState message="조건에 맞는 상품이 없습니다. 필터를 넓혀 보세요." />
        ) : (
          <ul className="list__grid" ref={setGridRef}>
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

        {visibleCount < filtered.length ? (
          <button
            type="button"
            className="list__more"
            onClick={() => setShown(visibleCount + PAGE_SIZE)}
          >
            더 보기 ({filtered.length - visibleCount}개 남음)
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
