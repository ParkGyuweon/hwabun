/**
 * 할인 · 표시 전용 레이어 (결정 2026-09-10, 프론트).
 *
 * 원칙 하나. **이벤트와 추천은 지금처럼 정가(`price_usd`)를 본다. 할인은 화면과 열린 속성에만 있다.**
 *   · 데이터 파트: 바꿀 것 없음. `cart_value`·`order_value`·`price_usd` 의 뜻이 그대로다.
 *     할인 정보는 `sale_price_usd`·`discount_rate`·`paid_value` 를 properties 에 **덧붙여** 보낸다.
 *     properties 는 계약상 열린 객체라 키를 더해도 검증기·마트가 깨지지 않는다.
 *   · AI 파트: 바꿀 것 없음. 페르소나 가격 민감도와 추천 가격대 축은 정가를 본다.
 *   · 백엔드: 목록 응답(`ProductSummary`)에 `salePriceKrw` 한 칸만 더하면 된다. 상세에는 이미 있다.
 *
 * 할인 데이터의 단일 출처는 `mocks/discounts.json`. 백엔드 카탈로그가 붙으면 옵션의 `salePriceKrw` 로
 * 바꿔 끼우고 이 파일의 함수는 그대로 쓴다.
 */
import discountsData from '../mocks/discounts.json';
import { toKrw } from './localize';
import type { Product } from '../types/product';

type Priced = Pick<Product, 'price_usd' | 'sale_price_usd' | 'price_krw' | 'sale_price_krw'>;

/**
 * 원화 정가. **원화 원본이 있으면 그대로**, 없을 때만 달러를 100원 단위로 환산한다 (2026-09-21).
 * 표시(PriceTag·장바구니)·이벤트 금액(checkout)·목록 가격 필터가 전부 이 함수를 써야 값이 한 곳에서 갈리지 않는다.
 */
export const listPriceKrw = (p: Priced): number =>
  typeof p.price_krw === 'number' && p.price_krw > 0 ? Math.round(p.price_krw) : toKrw(p.price_usd);

/** 고객이 실제로 내는 원화. 할인 없으면 정가 */
export const effectivePriceKrw = (p: Priced): number => {
  if (!hasDiscount(p)) return listPriceKrw(p);
  if (typeof p.sale_price_krw === 'number' && p.sale_price_krw > 0) return Math.round(p.sale_price_krw);
  return toKrw(p.sale_price_usd as number);
};

interface DiscountEntry {
  /** 0~1. 0.15 = 15% */
  rate: number;
  /** 배지 옆 짧은 이유. "입점 기념" 처럼 */
  label: string;
}

const TABLE = discountsData as unknown as Record<string, DiscountEntry | Record<string, unknown>>;
const isEntry = (v: unknown): v is DiscountEntry =>
  typeof v === 'object' && v !== null && typeof (v as DiscountEntry).rate === 'number';

/** 할인가는 달러 소수 둘째 자리. 원화 표시는 formatPrice 가 100원 단위로 반올림한다 */
const round2 = (n: number) => Math.round(n * 100) / 100;

/** 상품에 할인 필드를 채운다. 표에 없으면 그대로 */
export function applyDiscount(p: Product): Product {
  const d = TABLE[p.product_id];
  if (!isEntry(d) || d.rate <= 0 || d.rate >= 1) return p;
  return {
    ...p,
    sale_price_usd: round2(p.price_usd * (1 - d.rate)),
    // 원화 원본이 있으면 할인가도 원화로 낸다 (100원 단위). 표시와 결제가 같은 수를 본다
    ...(typeof p.price_krw === 'number' && p.price_krw > 0 ? { sale_price_krw: Math.round((p.price_krw * (1 - d.rate)) / 100) * 100 } : {}),
    discount_rate: d.rate,
    discount_label: d.label,
  };
}

export const hasDiscount = (p: Pick<Product, 'price_usd' | 'sale_price_usd'>): boolean =>
  typeof p.sale_price_usd === 'number' && p.sale_price_usd > 0 && p.sale_price_usd < p.price_usd;

/** 고객이 실제로 내는 값. 할인 없으면 정가 */
export const effectivePrice = (p: Pick<Product, 'price_usd' | 'sale_price_usd'>): number =>
  hasDiscount(p) ? (p.sale_price_usd as number) : p.price_usd;

/** 배지에 쓰는 정수 % */
export const discountPercent = (p: Pick<Product, 'price_usd' | 'sale_price_usd'>): number =>
  hasDiscount(p) ? Math.round((1 - (p.sale_price_usd as number) / p.price_usd) * 100) : 0;

/**
 * 고른 옵션의 백엔드 옵션 id. 옵션을 안 고르면 첫 옵션. 목 상품은 없다(undefined).
 * 장바구니 API 가 variantId 로만 담기 때문에 담을 때 같이 싣는다.
 */
export function variantIdOf(p: Product, skuId: string | null): string | undefined {
  const v = (skuId ? p.variants.find((x) => x.sku_id === skuId) : undefined) ?? p.variants[0];
  return v?.variant_id;
}
