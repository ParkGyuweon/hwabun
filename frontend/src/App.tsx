import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SiteHeader from './components/layout/SiteHeader';
import LogPanel from './components/devtools/LogPanel';
import Breadcrumb from './components/product/Breadcrumb';
import ProductDetailPage from './pages/ProductDetailPage';
import ProductListPage from './pages/ProductListPage';
import { buildPersonas } from './lib/persona';
import { setLoggerContext, startPageView, startSession, track } from './lib/logger';
import productsData from './mocks/products.sample.json';
import reviewsData from './mocks/reviews.sample.json';
import type { Product } from './types/product';
import type { Review } from './types/review';
import './styles/product-detail.css';
import './styles/product-list.css';

// JSON 목업은 리터럴 타입으로 추론되므로 unknown 을 거쳐 캐스팅한다.
const products = productsData as unknown as Product[];
const reviews = reviewsData as unknown as Review[];
const personas = buildPersonas(reviews);

/** 상세 페이지에서 유사·추천 자리에 올릴 개수 */
const SIMILAR_SIZE = 6;

/**
 * 헤더 메뉴에 걸 카테고리.
 * 데이터에 실제로 있는 중분류만 쓴다. 상품 수가 많은 순서.
 */
const HEADER_CATEGORIES = (() => {
  const counts = new Map<string, number>();
  for (const p of products) {
    const key = p.category[1];
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([name]) => name);
})();

/** 첫 진입 주소에 상품이 있으면 그 상세로 시작한다 */
function initialProductId(): string | null {
  const requested = new URLSearchParams(window.location.search).get('product');
  return requested && products.some((p) => p.product_id === requested) ? requested : null;
}

/**
 * 라우터는 아직 붙이지 않았다.
 *
 * 화면이 목록과 상세 둘뿐이라 상태 전환으로 충분하다.
 * 다만 **뒤로가기는 그 자체가 행동 신호**이므로 History API 는 쓴다.
 * 목록으로 돌아간 것이 브라우저 뒤로가기인지 화면 안의 링크인지 구분해서 남긴다.
 */
export default function App() {
  // effect 로 늦게 세팅하면 목록을 한 번 그린 뒤 상세로 바뀌어서
  // page_view 가 목록·상세 두 번 찍힌다. 처음부터 올바른 값으로 시작한다.
  const [productId, setProductId] = useState<string | null>(initialProductId);
  const [personaId, setPersonaId] = useState(personas[0]?.persona_id ?? '');
  // 헤더 메뉴와 목록 탭이 같은 값을 바꾸므로 여기서 소유한다
  const [listCategory, setListCategory] = useState('all');
  /** 다음 page_view 가 어떻게 발생했는지. 뒤로가기와 화면 안 이동을 구분한다 */
  const navigationSourceRef = useRef('in_app');

  const persona = useMemo(
    () => personas.find((item) => item.persona_id === personaId) ?? null,
    [personaId],
  );

  const product = useMemo(
    () => (productId ? (products.find((item) => item.product_id === productId) ?? null) : null),
    [productId],
  );

  const productReviews = useMemo(
    () => (productId ? reviews.filter((review) => review.product_id === productId) : []),
    [productId],
  );

  /**
   * 유사 상품.
   * 같은 중분류에서 뽑는다. 대분류는 200개가 전부 Skincare 라 구분이 안 된다.
   */
  const similar = useMemo(() => {
    if (!product) return [];
    const key = product.category[1];
    return products
      .filter((item) => item.product_id !== product.product_id && item.category[1] === key)
      .slice(0, SIMILAR_SIZE);
  }, [product]);

  const openProduct = useCallback((nextId: string) => {
    window.history.pushState({ productId: nextId }, '', `?product=${nextId}`);
    setProductId(nextId);
  }, []);

  const goHome = useCallback(() => {
    track('product_click', { product_id: null, entry_source: 'breadcrumb_home' });
    window.history.pushState({ productId: null }, '', '/');
    setProductId(null);
  }, []);

  /** 헤더 메뉴로 카테고리를 고르면 목록으로 돌아가 그 카테고리를 펼친다 */
  const selectCategory = useCallback((category: string) => {
    track('list_filter_apply', { filter_kind: 'category', filter_value: category, from: 'header' });
    setListCategory(category);
    window.history.pushState({ productId: null }, '', '/');
    setProductId(null);
  }, []);

  /**
   * 브라우저 뒤로/앞으로.
   *
   * 처음에는 이걸 scroll_backtrack 으로 남겼는데 잘못이었다.
   * 그 이벤트는 가중 -1.0 의 좌절 신호인데, 목록으로 돌아가는 것은
   * 정상적인 탐색이다. 정상 행동에 감점을 주면 추천이 틀어진다.
   *
   * 이동 자체는 page_view 가 이미 남기므로, 어떻게 왔는지만 속성으로 구분한다.
   */
  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const next = (event.state?.productId as string | null | undefined) ?? null;
      navigationSourceRef.current = 'history_back';
      setProductId(next);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    setLoggerContext({ actorType: 'user', environment: 'local' });
  }, []);

  // 페르소나가 바뀌면 새 방문으로 본다
  useEffect(() => {
    startSession(personaId || null);
  }, [personaId]);

  // 목록과 상세는 다른 page_type 이다. 화면이 바뀔 때마다 새 페이지 조회로 남긴다
  useEffect(() => {
    setLoggerContext({ pageType: productId ? 'product_detail' : 'product_list' });
    startPageView(productId, navigationSourceRef.current);
    navigationSourceRef.current = 'in_app';
  }, [productId]);

  return (
    <>
      <SiteHeader
        personas={personas}
        persona={persona}
        onPersonaChange={setPersonaId}
        onHome={goHome}
        categories={HEADER_CATEGORIES}
        onCategorySelect={selectCategory}
      />

      {product ? (
        <>
          <Breadcrumb items={product.category} onHome={goHome} />
          <ProductDetailPage
            product={product}
            reviews={productReviews}
            allReviews={reviews}
            similar={similar}
            persona={persona}
            onSelectProduct={openProduct}
          />
        </>
      ) : (
        <ProductListPage
          products={products}
          onSelectProduct={openProduct}
          category={listCategory}
          onCategoryChange={setListCategory}
        />
      )}

      <LogPanel />
    </>
  );
}
