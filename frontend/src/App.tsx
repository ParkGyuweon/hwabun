import { useEffect, useMemo, useState } from 'react';
import SiteHeader from './components/layout/SiteHeader';
import DevToolbar from './components/devtools/DevToolbar';
import LogPanel from './components/devtools/LogPanel';
import ProductDetailPage from './pages/ProductDetailPage';
import { buildPersonas } from './lib/persona';
import { setLoggerContext, startPageView, startSession } from './lib/logger';
import productsData from './mocks/products.sample.json';
import reviewsData from './mocks/reviews.sample.json';
import type { Product } from './types/product';
import type { Review } from './types/review';
import './styles/product-detail.css';

// JSON 목업은 리터럴 타입으로 추론되므로 unknown 을 거쳐 캐스팅한다.
const products = productsData as unknown as Product[];
const reviews = reviewsData as unknown as Review[];
const personas = buildPersonas(reviews);

/**
 * 라우터는 아직 붙이지 않았다.
 * 상세 페이지 하나를 먼저 완성하는 단계라 상품 전환은 헤더 셀렉트로 대신한다.
 * 목록 페이지가 생기면 react-router-dom 으로 교체할 자리.
 */
export default function App() {
  const [productId, setProductId] = useState(products[0].product_id);
  const [personaId, setPersonaId] = useState(personas[0]?.persona_id ?? '');

  const persona = useMemo(
    () => personas.find((item) => item.persona_id === personaId) ?? null,
    [personaId],
  );

  const product = useMemo(
    () => products.find((item) => item.product_id === productId) ?? products[0],
    [productId],
  );

  const productReviews = useMemo(
    () => reviews.filter((review) => review.product_id === productId),
    [productId],
  );

  const similar = useMemo(
    () =>
      products
        .filter((item) => item.product_id !== product.product_id && item.category[0] === product.category[0])
        .slice(0, 6),
    [product],
  );

  useEffect(() => {
    setLoggerContext({ pageType: 'product_detail', actorType: 'user', environment: 'local' });
  }, []);

  // 페르소나가 바뀌면 새 방문으로 본다
  useEffect(() => {
    startSession(personaId || null);
  }, [personaId]);

  // 상품이 바뀌면 새 페이지 조회로 본다
  useEffect(() => {
    startPageView(productId);
  }, [productId]);

  return (
    <>
      <SiteHeader personas={personas} persona={persona} onPersonaChange={setPersonaId} />

      <DevToolbar products={products} productId={productId} onProductChange={setProductId} />

      <ProductDetailPage
        product={product}
        reviews={productReviews}
        allReviews={reviews}
        similar={similar}
        persona={persona}
        onSelectProduct={setProductId}
      />

      <LogPanel />
    </>
  );
}
