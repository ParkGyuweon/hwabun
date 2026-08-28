import { useCallback, useEffect, useMemo, useState } from 'react';
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

  // 브라우저 뒤로/앞으로. 화면 안 클릭과 구분해서 남긴다
  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const next = (event.state?.productId as string | null | undefined) ?? null;
      track('scroll_backtrack', { reason: 'history_back', to: next ? 'detail' : 'list' });
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
    startPageView(productId);
  }, [productId]);

  return (
    <>
      <SiteHeader
        personas={personas}
        persona={persona}
        onPersonaChange={setPersonaId}
        onHome={goHome}
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
        <ProductListPage products={products} onSelectProduct={openProduct} />
      )}

      <LogPanel />
    </>
  );
}
