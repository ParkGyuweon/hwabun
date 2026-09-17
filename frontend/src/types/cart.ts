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
  /** 백엔드 옵션 id. 있으면 서버 장바구니를 탈 수 있다 */
  variant_id?: string | null;
  quantity: number;
}

/**
 * 한 품목에 담을 수 있는 최대 수량.
 *
 * 상품 화면(+/− 버튼)과 장바구니가 **같은 값을 봐야 한다.** 예전에는 상품 화면이 99 까지 올려 주는데
 * 장바구니 수량은 1~5 짜리 셀렉트였다. 10 을 담으면 그 값이 목록에 없어 브라우저가 첫 항목(1)을 그렸고,
 * 합계만 10개로 맞아 "수량 1 인데 10개 값" 으로 보였다. 손대면 조용히 1 로 떨어졌다.
 */
export const MAX_CART_QUANTITY = 99;
