/**
 * 장바구니 항목.
 *
 * 서버 장바구니가 없으므로 App 메모리에만 산다. 새로고침하면 비워진다.
 * 이 화면의 목적은 구매 기능이 아니라 `view_cart` / `remove_from_cart` 신호다.
 * 담을 때의 상품 정보를 복사해 들고 있어서 상품 목록을 다시 뒤지지 않는다.
 */
export interface CartItem {
  product_id: string;
  /** 담은 옵션. 옵션 없는 상품이면 대표 SKU 또는 null */
  sku_id: string | null;
  /** 옵션 표기명. 화면 표시용 */
  variant_label: string | null;
  brand_name: string;
  product_name: string;
  image_url: string | null;
  price_usd: number;
  /** 담을 때의 할인가. 없으면 정가로 계산한다 (lib/discount.ts effectivePrice) */
  sale_price_usd?: number | null;
  quantity: number;
}
