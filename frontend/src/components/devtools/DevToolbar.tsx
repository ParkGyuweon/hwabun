import type { Product } from '../../types/product';

interface DevToolbarProps {
  products: Product[];
  productId: string;
  onProductChange: (productId: string) => void;
}

/**
 * 임시 내비게이션.
 *
 * 상품 목록 페이지가 아직 없어서 상세 페이지를 바꿔 볼 수단이 필요하다.
 * 목록 페이지와 라우터가 붙으면 통째로 제거한다.
 * 페르소나 전환은 QA 도구가 아니라 이 사이트의 로그인에 해당하므로 헤더에 있다.
 */
export default function DevToolbar({ products, productId, onProductChange }: DevToolbarProps) {
  return (
    <div className="dev-toolbar">
      <span className="dev-toolbar__tag">임시</span>

      <label className="field">
        <span className="field__label">상품 이동</span>
        <select value={productId} onChange={(event) => onProductChange(event.target.value)}>
          {products.map((product) => (
            <option key={product.product_id} value={product.product_id}>
              {product.brand_name} — {product.product_name}
            </option>
          ))}
        </select>
      </label>

      <span className="dev-toolbar__note">
        상품 목록 페이지가 생기면 제거 · 로그 이벤트 목록은 마케팅 조사 결과 반영 전 초안
      </span>
    </div>
  );
}
