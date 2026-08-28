import { useMemo, useState } from 'react';
import ProductCard from '../components/product/ProductCard';
import EmptyState from '../components/common/EmptyState';
import { useImpression } from '../hooks/useImpression';
import { track } from '../lib/logger';
import type { Product } from '../types/product';

/** 기획전에 올리는 상품 수. 한 화면에 다 보이는 만큼만 */
const PROMO_SIZE = 6;
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
  onSelectProduct: (productId: string) => void;
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
export default function ProductListPage({ products, onSelectProduct }: ProductListPageProps) {
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<SortKey>('popular');
  const [concern, setConcern] = useState('all');
  const [price, setPrice] = useState<PriceKey>('all');
  const [shown, setShown] = useState(PAGE_SIZE);

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

  /** 기획전. 신제품·한정판·단독 상품을 인기순으로 올린다 */
  const promo = useMemo(
    () =>
      products
        .filter((p) => (p.badges ?? []).length > 0)
        .sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
        .slice(0, PROMO_SIZE),
    [products],
  );

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

  // 목록이 바뀌면 노출을 처음부터 다시 센다
  const promoRef = useImpression({
    pageViewKey: 'promo',
    eventName: 'product_impression',
    listId: 'promo_pick',
  });
  const gridRef = useImpression({
    pageViewKey: `${category}|${concern}|${price}|${sort}`,
    eventName: 'product_impression',
    listId: 'list_grid',
  });

  const selectFrom = (listId: string) => (productId: string) => {
    const position = (listId === 'promo_pick' ? promo : visible).findIndex(
      (p) => p.product_id === productId,
    );
    track('product_click', {
      product_id: productId,
      entry_source: listId,
      position: position + 1,
    });
    onSelectProduct(productId);
  };

  /** 무엇으로 좁혔는지가 취향을 말해준다. 필터 종류를 함께 남긴다 */
  const applyFilter = (kind: string, value: string, reset = true) => {
    track('list_filter_apply', { filter_kind: kind, filter_value: value });
    if (reset) setShown(PAGE_SIZE);
  };

  return (
    <main className="page list">
      <section className="list__promo" data-log-section="highlights">
        <header className="list__promo-head">
          <h2>지금 주목할 상품</h2>
          <p>신제품 · 한정판 · 세포라 단독</p>
        </header>
        <ul className="list__row" ref={promoRef as React.Ref<HTMLUListElement>}>
          {promo.map((product, index) => (
            <ProductCard
              key={product.product_id}
              product={product}
              position={index + 1}
              onSelect={selectFrom('promo_pick')}
            />
          ))}
        </ul>
      </section>

      <section className="list__catalog" data-log-section="about_product">
        <nav className="list__tabs" aria-label="카테고리">
          <button
            type="button"
            className={category === 'all' ? 'is-active' : ''}
            onClick={() => {
              setCategory('all');
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
                setCategory(name);
                applyFilter('category', name);
              }}
            >
              {name} <span>{count}</span>
            </button>
          ))}
        </nav>

        <div className="list__controls">
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
                track('list_sort_change', { sort_key: next });
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
    </main>
  );
}
