import { useState } from 'react';
import ProductDetailPage from './pages/ProductDetailPage';
import productsData from './mocks/products.sample.json';
import type { Product } from './types/product';
import './styles/product-detail.css';

// JSON 목업은 리터럴 타입으로 추론되므로 unknown 을 거쳐 캐스팅한다.
const products = productsData as unknown as Product[];

/**
 * 라우터는 아직 붙이지 않았다.
 * 상세 페이지 하나를 먼저 완성하는 단계라, 상품 전환은 헤더의 셀렉트로 대신한다.
 * 목록 페이지가 생기면 react-router-dom 으로 교체할 자리.
 */
export default function App() {
  const [productId, setProductId] = useState(products[0].product_id);

  return (
    <>
      <header className="site-header">
        <div className="site-header__inner">
          <span className="site-header__logo">BEAUTY LAB</span>
          <label>
            <span className="sr-only">상품 선택</span>
            <select value={productId} onChange={(event) => setProductId(event.target.value)}>
              {products.map((product) => (
                <option key={product.product_id} value={product.product_id}>
                  {product.brand_name} — {product.product_name}
                </option>
              ))}
            </select>
          </label>
          <span className="site-header__note">샘플 데이터 {products.length}개 / 라우터 미연결</span>
        </div>
      </header>

      <ProductDetailPage productId={productId} />
    </>
  );
}
