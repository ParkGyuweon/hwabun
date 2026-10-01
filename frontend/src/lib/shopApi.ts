/**
 * shop_backend(8090) 어댑터 · 프론트 선에서 붙일 수 있는 것은 전부 여기로 붙인다 (2026-09-10).
 *
 * 원칙
 *   · 결제와 주문은 백엔드 원장을 정본으로 사용하며, 실패를 로컬 주문 성공으로 바꾸지 않는다.
 *   · 세포라 200개·SSAFY Beauty 시드는 백엔드 DB 에 없다. 그 상품은 장바구니·주문·피드백 API 를
 *     탈 수 없으므로 목 경로다. 백엔드에서 온 상품(`source: 'backend'`)만 API 를 탄다.
 *   · 이벤트 로그(`/api/events`, 8080)는 이 파일과 무관하다. 그대로 나간다.
 *
 * 백엔드 응답 모양은 shop_backend/…/CatalogController · CommerceController · FeedbackController 의
 * record 정의를 그대로 옮겼다. 필드 이름이 camelCase 인 이유다.
 *
 * 알려진 백엔드 제약 (요청 메시지에 적어 보냄)
 *   · 401 {"error":"unauthorized"} 는 인증 진입점이 돌려주는 것으로, 토큰 만료·무효라는 뜻이다. 예전에는
 *     /error 가 permitAll 이 아니라서 모든 4xx 가 이 401 로 바뀌었지만 지금은 풀렸다 (SecurityConfig).
 *     이 401 이면 authFetch 가 그 역할의 세션을 지운다.
 *   · category 는 secondary_category 코드로 시드돼 있다 (shop_backend_seed.sql). POST /api/products 가
 *     실패하면 로컬 등록으로 물러난다.
 *   · 새 상품은 DRAFT 로 만들어져 목록에 안 뜬다. 등록 성공 직후 ACTIVE 로 바꾸는 요청을 한 번 더 보낸다.
 */
import { signalNotificationsChanged } from './notifySignal';
import { authFetch, sessionSnapshot } from './auth';
import type { AccountRole } from './auth';
import { loadBrandId } from './brands';
import { KRW_PER_USD } from './localize';
import { isNewRegistered } from './newBrandRule';
import { axisLabel, categoryLabel } from '../types/feedback';
import { statusOfHandling } from '../types/feedback';
import type { FeedbackResponseAction } from '../types/feedback';
import type { CartItem } from '../types/cart';
import type { Feedback } from '../types/feedback';
import type { Product, ProductDescription, ProductVariant } from '../types/product';
import type { Review } from '../types/review';
import type { RegistrationForm } from './productRegistry';

/* ------------------------------------------------------------------ 공통 */

export interface ApiFailure {
  ok: false;
  status: number;
  /** 사람이 읽는 이유. 화면에 그대로 보여도 되는 문장 */
  reason: string;
}

const round2 = (n: number) => Math.round(n * 100) / 100;
const krwToUsd = (krw: number | string | null | undefined): number =>
  krw === null || krw === undefined ? 0 : round2(Number(krw) / KRW_PER_USD);

/**
 * 실패 응답을 화면에 보여 줄 한 문장으로. 같은 상태 코드도 API 마다 뜻이 달라 본문 문구까지 본다.
 * 화면 문장에는 상태 코드·서버 원문을 넣지 않는다 (고객이 읽는 말). 원문은 개발 중에만 콘솔에 남긴다.
 */
async function reasonOf(res: Response): Promise<string> {
  let text = '';
  try {
    text = await res.text();
  } catch {
    /* 본문 없음 */
  }
  if (import.meta.env.DEV) console.warn(`[shopApi] ${res.status} ${res.url}`, text.slice(0, 300));
  if (res.status === 401) {
    // 서버의 /error 수정 뒤로 401 은 실제 로그인 만료다 (예전엔 다른 4xx 도 401 로 왔다)
    return '로그인이 끝났습니다. 다시 로그인한 뒤 시도해 주세요.';
  }
  /*
   * 403·409 는 **어느 API 인지에 따라 뜻이 다르다.** 전에는 둘 다 피드백 화면 문장으로 고정돼 있어서 결제 403 이
   * "구매한 상품에만 남길 수 있다" 로, 품절 409 가 "이미 있는 항목" 으로 떴다 (계약 대조 2026-09-17). 서버 본문의
   * 문구(CommerceController · FeedbackController)로 가른다.
   */
  const lower = text.toLowerCase();
  if (res.status === 403) {
    if (lower.includes('paid purchase')) return '구매한 상품에만 남길 수 있습니다.';
    // 테스트 결제(/pay)는 에이전트 러너 계정만 쓸 수 있다
    if (lower.includes('test payment')) return '이 결제 방법은 쓸 수 없습니다. 카카오페이로 결제해 주세요.';
    if (lower.includes('brand')) return '내 브랜드 상품이 아닙니다.';
    return '이 계정으로는 할 수 없습니다. 다시 로그인해 주세요.';
  }
  if (res.status === 404) return '상품이나 주문 정보를 찾을 수 없습니다.';
  if (res.status === 409) {
    if (lower.includes('inactive') || lower.includes('unavailable')) return '품절되었거나 판매가 멈춘 상품이 장바구니에 있습니다. 그 상품을 빼고 다시 주문해 주세요.';
    if (lower.includes('idempotency')) return '장바구니 내용이 바뀌었습니다. 장바구니를 다시 열어 주문해 주세요.';
    if (lower.includes('feedback') || lower.includes('duplicate')) return '이미 남긴 의견입니다.';
    return '이미 처리된 요청입니다.';
  }
  if (res.status >= 500) return '일시적인 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.';
  return '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';
}

const fail = async (res: Response): Promise<ApiFailure> => ({ ok: false, status: res.status, reason: await reasonOf(res) });
const offline = (): ApiFailure => ({ ok: false, status: 0, reason: '지금은 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.' });

export const hasMemberSession = (): boolean => sessionSnapshot('MEMBER') !== null;
export const hasSellerSession = (): boolean => sessionSnapshot('SELLER') !== null;

/* ------------------------------------------------------------------ 상품 */

interface ProductSummaryDto {
  productId: string;
  brandId: string;
  brandName: string | null;
  categoryId: string;
  productName: string;
  secondaryCategory: string;
  tertiaryCategory: string;
  priceKrw: number | string | null;
  priceBin: string;
  rating: number | null;
  lovesCount: number | null;
  primaryImageUrl: string | null;
  highlights: string[] | null;
  /** 목록에서도 구매 단위 ID를 받아 장바구니 API로 바로 전달한다. */
  variants?: VariantDto[] | null;
  /** 요청서 9-11 — 백엔드가 아직 안 내려준다. 오면 14일 신규 판정에 쓴다 */
  createdAt?: string | null;
}
interface VariantDto {
  variantId: string;
  skuId: string;
  label: string;
  size: string | null;
  priceKrw: number | string;
  salePriceKrw: number | string | null;
  status: string;
  /** 옵션 이미지·스와치. `product_variant.image_url · swatch_url` 컬럼은 있는데 `VariantView` 가 아직 안 준다 — 오면 바로 쓴다 */
  imageUrl?: string | null;
  swatchUrl?: string | null;
}
interface ProductDetailDto {
  product: ProductSummaryDto;
  variants: VariantDto[];
  ingredients: string | null;
  description: Record<string, unknown> | null;
  /** 상품 이미지 여러 장 (`product_image` 테이블, sort_order 순). `ProductDetail` 이 아직 안 준다 — 오면 갤러리에 그대로 들어간다 */
  images?: Array<string | { url: string }> | null;
}

function mapVariant(v: VariantDto, fallbackImage: string | null): ProductVariant {
  return {
    sku_id: v.skuId,
    label: v.label,
    image_url: v.imageUrl ?? fallbackImage ?? '',
    swatch_url: v.swatchUrl ?? null,
    variant_id: v.variantId,
    // 옵션 가격. 대용량·리필처럼 옵션마다 값이 다르다 — 전에는 버려서 어느 옵션을 골라도 상품 값 하나만 보였다 (2026-09-22)
    price_krw: v.priceKrw === null || v.priceKrw === undefined ? null : Number(v.priceKrw),
    sale_price_krw: v.salePriceKrw === null || v.salePriceKrw === undefined ? null : Number(v.salePriceKrw),
    size: v.size ?? null,
  };
}

function mapSummary(s: ProductSummaryDto): Product {
  const active = (s.variants ?? []).filter((v) => v.status === 'ACTIVE');
  return {
    product_id: s.productId,
    product_name: s.productName,
    brand_name: s.brandName ?? '',
    category: ['Skincare', s.secondaryCategory, s.tertiaryCategory].filter(Boolean),
    image_url: s.primaryImageUrl,
    sku_id: active[0]?.skuId ?? null,
    images: s.primaryImageUrl ? [s.primaryImageUrl] : [],
    variants: active.map((v) => mapVariant(v, s.primaryImageUrl)),
    description: null,
    // 기본 옵션(첫 ACTIVE 옵션)의 값을 상품 값으로 삼는다. 상품 행의 priceKrw 가 옵션과 어긋난 상품이 있어서
    // (SB000007: 상품 24,000 · 기본 옵션 32,200) 옵션 쪽을 정본으로 본다. 옵션 값이 없으면 상품 행 값
    price_usd: krwToUsd(active[0]?.priceKrw ?? s.priceKrw),
    // 원화 원본. 화면·결제는 이 값을 그대로 쓴다 (types/product.ts price_krw)
    price_krw: active[0]?.priceKrw != null ? Number(active[0].priceKrw) : s.priceKrw === null || s.priceKrw === undefined ? null : Number(s.priceKrw),
    size: null,
    rating: s.rating ?? null,
    review_count: null,
    loves_count: s.lovesCount ?? 0,
    badges: isNewRegistered(s.productId, s.createdAt) ? ['new'] : [],
    created_at: s.createdAt ?? null,
    highlights: s.highlights ?? [],
    ingredients: [],
    suitable_skin_types: [],
    skincare_concerns: [],
    source: 'backend',
    backend_brand_id: s.brandId,
  };
}

function mapDescription(d: Record<string, unknown> | null): ProductDescription | null {
  if (!d) return null;
  const str = (k: string) => (typeof d[k] === 'string' && (d[k] as string).trim() ? (d[k] as string) : null);
  const arr = (k: string) => (Array.isArray(d[k]) ? (d[k] as unknown[]).map(String) : []);
  return {
    what_it_is: str('what_it_is'),
    skin_type: str('skin_type'),
    concerns_text: str('concerns_text'),
    highlighted_ingredients: arr('highlighted_ingredients'),
    ingredient_callouts: str('ingredient_callouts'),
    what_else: str('what_else'),
    clinical_results: str('clinical_results'),
    suggested_usage: str('suggested_usage'),
    brand_story: str('brand_story'),
  };
}

function mapDetail(d: ProductDetailDto): Product {
  const base = mapSummary(d.product);
  const active = d.variants.filter((v) => v.status === 'ACTIVE');
  const variants: ProductVariant[] = active.map((v) => mapVariant(v, base.image_url));
  const extraImages = (d.images ?? []).map((i) => (typeof i === 'string' ? i : i?.url)).filter((u): u is string => Boolean(u));
  const images = [...new Set([...base.images, ...extraImages])];
  const first = active[0];
  const sale = first?.salePriceKrw != null ? krwToUsd(first.salePriceKrw) : null;
  return {
    ...base,
    images,
    variants,
    size: first?.size ?? null,
    description: mapDescription(d.description),
    ingredients: d.ingredients && d.ingredients.trim() ? [d.ingredients.trim()] : [],
    sale_price_usd: sale && sale < base.price_usd ? sale : null,
    sale_price_krw: sale && sale < base.price_usd && first?.salePriceKrw != null ? Number(first.salePriceKrw) : null,
    discount_label: sale && sale < base.price_usd ? '할인' : undefined,
  };
}

/**
 * 백엔드 카탈로그 **목록** — `GET /api/products` 한 번, 요약만.
 *
 * 예전에는 여기서 상품마다 `GET /api/products/{id}` 를 다시 불렀다. 백엔드 상품이 사장님 등록분 몇 개일 때 짠 것인데,
 * 시드 208개가 들어가자 상세 진입 한 번에 요청 459건 · 46MB · 19초가 됐다 (백엔드 지적 2026-09-14, N+1).
 * 목록·추천 카드는 요약으로 충분하다. 상세는 사용자가 실제로 연 상품만 `fetchBackendProductDetail` 로 받는다
 * (`productRegistry.ensureBackendDetail`).
 */
export async function listBackendProducts(): Promise<Product[] | null> {
  let res: Response;
  try {
    res = await fetch('/api/products', { headers: { Accept: 'application/json' } });
  } catch {
    return null;
  }
  if (!res.ok) return null;
  let rows: ProductSummaryDto[];
  try {
    rows = (await res.json()) as ProductSummaryDto[];
  } catch {
    return null;
  }
  if (!Array.isArray(rows)) return null;
  return rows.map(mapSummary);
}

/** `GET /api/products/{id}` — 옵션·전성분·설명·(오면) 이미지 여러 장. 실패하면 null 이고 호출부가 요약을 그대로 쓴다 */
export async function fetchBackendProductDetail(productId: string): Promise<Product | null> {
  try {
    const r = await fetch(`/api/products/${encodeURIComponent(productId)}`, { headers: { Accept: 'application/json' } });
    if (!r.ok) return null;
    return mapDetail((await r.json()) as ProductDetailDto);
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ 상품 등록 (판매자) */

export type RegisterResult = { ok: true; product: Product; activated: boolean } | ApiFailure;

/**
 * POST /api/products. 폼(snake_case)을 백엔드 record(camelCase)로 옮긴다.
 *
 * categoryId 는 백엔드 `category` 테이블의 id 다. 그 테이블은 secondary_category 코드를 id 로 시드돼 있어
 * (shop_backend_seed.sql) 폼의 2차 카테고리 코드를 그대로 보낸다.
 */
export async function registerProductBackend(form: RegistrationForm): Promise<RegisterResult> {
  const brandId = loadBrandId();
  if (!brandId) return { ok: false, status: 0, reason: '브랜드 id 가 없습니다. 대시보드에 판매자로 로그인해 브랜드를 먼저 만들어야 합니다' };
  if (!hasSellerSession()) return { ok: false, status: 0, reason: '판매자 로그인이 없습니다' };

  const body = {
    brandId,
    categoryId: form.secondary_category,
    productName: form.product_name.trim(),
    secondaryCategory: form.secondary_category,
    tertiaryCategory: form.tertiary_category,
    highlights: form.highlights,
    ingredients: form.ingredients.trim(),
    priceKrw: Number(form.price_krw) || 0,
    /**
     * 용량. 백엔드 ProductRequest 에 아직 없는 필드다 (docs/shop-backend-requests.md 9번). Jackson 3 기본이
     * 미등록 필드를 버리므로 지금 보내도 실패하지 않고, 백엔드가 기본 옵션 variant.size 로 받기 시작하면 그대로 붙는다
     */
    size: form.size.trim() || null,
    primaryImageUrl: form.image_url.trim() || null,
    description: {
      what_it_is: form.what_it_is.trim() || null,
      suggested_usage: form.suggested_usage.trim() || null,
      highlighted_ingredients: form.highlighted_ingredients.split('\n').map((s) => s.trim()).filter(Boolean),
      ingredient_callouts: form.ingredient_callouts.trim() || null,
      brand_story: form.brand_story.trim() || null,
    },
  };

  let res: Response;
  try {
    res = await authFetch('SELLER', '/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    return offline();
  }
  if (!res.ok) return fail(res);
  const detail = (await res.json()) as ProductDetailDto;
  const product = mapDetail(detail);

  // 새 상품은 DRAFT 다. 목록(ACTIVE만)에 뜨게 바로 올린다. 실패해도 등록 자체는 성공이다
  let activated = false;
  try {
    const act = await authFetch('SELLER', `/api/products/${encodeURIComponent(product.product_id)}/status?value=ACTIVE`, { method: 'PATCH' });
    activated = act.ok;
  } catch {
    activated = false;
  }
  return { ok: true, product, activated };
}

/* ------------------------------------------------------------------ 장바구니·주문·결제 (고객) */

export type CheckoutResult = { ok: true; orderId: string; status: string } | ApiFailure;
/**
 * `status` 는 서버 주문 상태(`CREATED` · `PAID` …). 같은 주문 번호로 다시 보내면 서버가 **이미 있는 주문**을
 * 그대로 돌려주므로, 앞선 시도에서 결제까지 끝났으면 여기서 `PAID` 가 온다 — 그때 결제창을 또 열면 안 된다.
 */
export type CreateOrderResult = { ok: true; orderId: string; totalAmountKrw: number | null; status: string | null; paidAt: string | null } | ApiFailure;
export type ConfirmResult = { ok: true; orderId: string; status: string; paidAt: string | null } | ApiFailure;

/** 주문에 든 품목. 리뷰를 쓰려면 `orderItemId` 가 필요하다 */
export interface BackendOrderItem {
  orderItemId: string;
  productId: string;
  productName: string;
  variantLabel: string | null;
  quantity: number;
  lineAmount: number;
  /** 이미 리뷰를 쓴 품목. 한 품목에 리뷰는 하나다 (서버가 409 로 막는다) */
  reviewed: boolean;
}

export interface BackendOrder {
  orderId: string;
  status: string;
  totalAmount: number;
  paidAmount: number;
  currency: string;
  paymentId: string | null;
  paymentProvider: string | null;
  paidAt: string | null;
  createdAt: string;
  itemCount: number;
  /** 옛 서버(품목을 안 주는 판본)와도 돌아야 해서 없으면 빈 배열 */
  items: BackendOrderItem[];
}

export type OrderListResult = { ok: true; orders: BackendOrder[] } | ApiFailure;

/** 결제 완료된 내 주문 목록. 브라우저 localStorage 주문 내역은 사용하지 않는다. */
export async function fetchBackendOrders(): Promise<OrderListResult> {
  if (!hasMemberSession()) return { ok: false, status: 401, reason: '로그인이 필요합니다.' };
  try {
    const res = await authFetch('MEMBER', '/api/orders');
    if (!res.ok) return fail(res);
    const rows = (await res.json()) as BackendOrder[];
    if (!Array.isArray(rows)) return { ok: true, orders: [] };
    // 품목을 안 주는 옛 서버와도 돌아야 한다 — 없으면 빈 배열로 채워 화면이 `undefined` 를 훑지 않게 한다
    return { ok: true, orders: rows.map((o) => ({ ...o, items: Array.isArray(o.items) ? o.items : [] })) };
  } catch {
    return offline();
  }
}

export type ReviewSubmitResult = { ok: true; reviewId: string } | ApiFailure;

/**
 * `POST /api/reviews` — 산 사람만 쓸 수 있다. 서버가 그 `orderItemId` 가 이 회원의 결제 완료 주문인지
 * 직접 확인하고, 아니면 403 이다. 이미 쓴 품목이면 409.
 */
export async function submitReview(input: {
  orderItemId: string;
  rating: number;
  isRecommended: boolean | null;
  title: string | null;
  body: string;
}): Promise<ReviewSubmitResult> {
  if (!hasMemberSession()) return { ok: false, status: 401, reason: '로그인이 필요합니다.' };
  try {
    const res = await authFetch('MEMBER', '/api/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!res.ok) return fail(res);
    const body = (await res.json()) as { reviewId?: string };
    return { ok: true, reviewId: String(body.reviewId ?? '') };
  } catch {
    return offline();
  }
}

/** 장바구니 전부가 백엔드 상품(옵션 id 있음)이고 고객 로그인이 있을 때만 API 를 탈 수 있다 */
export function canCheckoutOnBackend(items: CartItem[]): boolean {
  return items.length > 0 && hasMemberSession() && items.every((i) => Boolean(i.variant_id));
}

/**
 * 서버 장바구니를 비운다. **"바로 구매" 전에만 부른다.**
 *
 * `POST /api/orders` 는 요청 본문의 품목이 아니라 **서버 장바구니에 든 것 전부**를 주문한다
 * (`CommerceController.order` — `cartItems.findByCartId`). 정상 주문은 끝나면 서버가 장바구니를
 * 비우므로(`deleteByCartId`) 보통은 비어 있지만, 담기까지 갔다가 주문이 실패한 시도가 있으면
 * 그 품목이 남는다. 그 상태에서 "이 상품만" 을 주문하면 남아 있던 것까지 같이 결제된다.
 *
 * 그래서 바로 구매는 **비우고 → 그 상품 하나만 담고 → 주문**한다. 화면의 장바구니(로컬 상태)는
 * 건드리지 않는다 — 서버 장바구니는 주문 직전에만 채워지는 임시 자리다.
 *
 * **실패를 삼키지 않는다** (백엔드 리뷰 2026-09-17). 조회나 삭제 하나라도 실패한 뒤 주문을 계속하면
 * **서버에 남아 있던 기존 상품까지 같이 결제된다.** "이 상품만" 이라고 적힌 버튼이 다른 것도 사는
 * 셈이라, 호출부가 결과를 보고 멈출 수 있게 성공·실패를 돌려준다. 삭제 응답도 하나하나 확인한다.
 */
export type ClearCartResult = { ok: true; removed: number } | ApiFailure;

export async function clearBackendCart(): Promise<ClearCartResult> {
  try {
    const res = await authFetch('MEMBER', '/api/cart');
    if (!res.ok) return fail(res);
    const body = (await res.json()) as { items?: Array<{ id?: string }> };
    const items = body.items ?? [];
    let removed = 0;
    for (const item of items) {
      /*
       * id 가 없으면 지울 방법이 없다. "없는 셈 치고 넘어가면" 그 품목이 그대로 주문에 실린다 —
       * 비우지 못한 것을 비웠다고 보고하는 셈이라 여기서 멈춘다.
       */
      if (!item.id) {
        return { ok: false, status: 0, reason: '장바구니를 정리하지 못했습니다.' };
      }
      const del = await authFetch('MEMBER', `/api/cart/items/${encodeURIComponent(item.id)}`, {
        method: 'DELETE',
      });
      if (!del.ok) return fail(del);
      removed += 1;
    }
    return { ok: true, removed };
  } catch {
    return offline();
  }
}

/**
 * 서버 장바구니에 담고 → 주문 생성. 응답의 `totalAmount`(KRW) 가 결제 금액의 정본이다 (AI 정리 2026-09-14 §4).
 * 주문 번호 필드가 `id` 라 `orderId ?? id` 로 읽는다 (요청서 9-7).
 */
export async function createBackendOrder(items: CartItem[], idempotencyKey: string): Promise<CreateOrderResult> {
  try {
    for (const item of items) {
      const r = await authFetch('MEMBER', '/api/cart/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variantId: item.variant_id, quantity: item.quantity }),
      });
      if (!r.ok) return fail(r);
    }
    const created = await authFetch('MEMBER', '/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idempotencyKey }),
    });
    if (!created.ok) return fail(created);
    const order = (await created.json()) as Record<string, unknown>;
    const orderId = String(order.orderId ?? order.id ?? order.order_id ?? '');
    if (!orderId) return { ok: false, status: created.status, reason: '주문 번호를 받지 못했습니다.' };
    const amt = Number(order.totalAmount ?? order.total_amount);
    const status = typeof order.status === 'string' ? order.status : null;
    const paidAt = typeof order.paidAt === 'string' ? order.paidAt : typeof order.paid_at === 'string' ? order.paid_at : null;
    return { ok: true, orderId, totalAmountKrw: Number.isFinite(amt) && amt > 0 ? Math.round(amt) : null, status, paidAt };
  } catch {
    return offline();
  }
}

/** `POST /api/orders/{id}/pay` — 결제 연동 없이 PAID 표시 (테스트 주문). 백엔드가 PAYMENT_MODE=test 일 때만 허용할 예정 */
export async function payBackendOrder(orderId: string): Promise<CheckoutResult> {
  try {
    const paid = await authFetch('MEMBER', `/api/orders/${encodeURIComponent(orderId)}/pay`, { method: 'POST' });
    if (!paid.ok) return fail(paid);
    const body = (await paid.json()) as Record<string, unknown>;
    return { ok: true, orderId, status: String(body.status ?? 'PAID') };
  } catch {
    return offline();
  }
}

/**
 * `POST /api/orders/{id}/confirm { paymentId }` — 서버가 포트원 `GET /payments/{paymentId}` 로 조회해
 * status==PAID · amount.total==주문 totalAmount 를 대조하고 PAID 로 바꾼다 (요청서 10번). **이 응답이 결제의 정본**이다.
 */
export async function confirmBackendOrder(orderId: string, paymentId: string): Promise<ConfirmResult> {
  try {
    const res = await authFetch('MEMBER', `/api/orders/${encodeURIComponent(orderId)}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paymentId }),
    });
    if (!res.ok) return fail(res);
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const paidAt = typeof body.paidAt === 'string' ? body.paidAt : typeof body.paid_at === 'string' ? body.paid_at : null;
    return { ok: true, orderId, status: String(body.status ?? 'PAID'), paidAt };
  } catch {
    return offline();
  }
}

/**
 * 결제 연동이 꺼져 있을 때의 서버 주문: 담기 → 주문 → /pay. 예전 흐름 그대로다.
 * 그래야 피드백·리뷰 API 의 "구매 이력" 조건이 성립한다.
 */
export async function checkoutOnBackend(items: CartItem[], idempotencyKey: string): Promise<CheckoutResult> {
  const created = await createBackendOrder(items, idempotencyKey);
  if (!created.ok) return created;
  // 같은 주문 번호의 앞선 시도가 이미 끝났으면 다시 표시하지 않는다
  if (created.status === 'PAID') return { ok: true, orderId: created.orderId, status: 'PAID' };
  return payBackendOrder(created.orderId);
}

/* ------------------------------------------------------------------ 피드백 */

export type FeedbackSubmitResult = { ok: true; feedbackId: string } | ApiFailure;

/** POST /api/feedback. 백엔드가 이 고객의 PAID 주문을 직접 확인한다. 없으면 403 이 정상이다 */
export async function submitFeedbackBackend(input: { productId: string; axisId: string; body: string }): Promise<FeedbackSubmitResult> {
  if (!hasMemberSession()) return { ok: false, status: 0, reason: '로그인이 필요합니다.' };
  try {
    const res = await authFetch('MEMBER', '/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!res.ok) return fail(res);
    const j = (await res.json()) as { feedbackId: string };
    // 서버가 같은 요청 안에서 판매자 알림을 만든다 — 옆에 떠 있는 대시보드 종이 바로 다시 받게
    signalNotificationsChanged();
    return { ok: true, feedbackId: j.feedbackId };
  } catch {
    return offline();
  }
}

interface SellerFeedbackRow {
  feedbackId: string;
  productId: string;
  productName?: string;
  /** 내 피드백 응답에는 없다 (내 것이니까) */
  authorMemberId?: string;
  /** 산 사람의 의견인지. 옛 서버는 안 준다 */
  purchased?: boolean;
  authorSkinTypeCode?: string | null;
  authorSkinToneCode?: string | null;
  axisId: string;
  body: string;
  status?: string;
  createdAt: string;
  labels?: Array<{ axisId: string; categoryId: string }>;
  primary?: { axisId: string; categoryId: string } | null;
  offAxisHint?: string | null;
  classifier?: string | null;
  vocabVersion?: string | null;
  classifiedAt?: string | null;
  bannedTerms?: string[];
  classificationStatus?: string;
  hiddenByDefault?: boolean;
  /** 업체 처리 상태 (2026-09-18). 옛 서버는 안 준다 */
  handlingStatus?: string | null;
  lastRespondedAt?: string | null;
  latestResponse?: { action: string; body: string | null; createdAt: string } | null;
  /** 내 피드백(`/api/feedback/mine`)은 응답 이력 전부를 준다. 오래된 것부터 */
  responses?: Array<{ action: string; body: string | null; createdAt: string }> | null;
  /** 판매자 목록 쿼리의 이름. `purchased` 와 같은 뜻 */
  isPurchaser?: boolean;
}

/**
 * 분류 시작 결과.
 *
 * `started` 는 이번 호출로 분류가 걸렸다는 뜻이고 `running` 은 이미 돌고 있다는 뜻이다. 둘 다 정상이라
 * 화면은 구분 없이 "결과를 기다린다" 로 이어간다. `unavailable` 은 서버가 이 엔드포인트를 아직 안 주는
 * 경우(404)까지 포함한다 — 그때도 화면은 죽지 않고 지금 있는 데이터를 그대로 그린다.
 */
export type ClassifyStart = 'started' | 'running' | 'unavailable';

/**
 * POST /api/seller/feedback/classify?brandId=
 *
 * 202 든 409 든 **오류가 아니다**. 409 는 다른 탭·다른 사장님이 이미 돌리고 있다는 뜻이라,
 * 실패로 적으면 정상 상황에 오류가 뜬다.
 */
export async function startFeedbackClassification(brandId: string): Promise<ClassifyStart> {
  try {
    const res = await authFetch('SELLER', `/api/seller/feedback/classify?brandId=${encodeURIComponent(brandId)}`, { method: 'POST' });
    if (res.status === 202) return 'started';
    if (res.status === 409) return 'running';
    return 'unavailable';
  } catch {
    return 'unavailable';
  }
}

/** true/false 또는 1/0 → boolean. 그 외(없음)는 "모른다" */
const boolish = (v: unknown): boolean | undefined =>
  typeof v === 'boolean' ? v : typeof v === 'number' ? v !== 0 : undefined;

/** 서버 행 → 화면 타입(Feedback). 판매자 목록과 "내 피드백" 이 같은 모양이라 같이 쓴다. 분류 전이면 labels 가 빈 배열로 온다 */
function feedbackFromRow(r: SellerFeedbackRow, brandName: string): Feedback {
  /*
   * 응답 이력. 판매자 목록은 `latestResponse` 하나, 내 피드백(`/api/feedback/mine`)은 `responses[]` 전부를 준다 (백엔드 요청
   * 2026-10-01). 소비자에게 보이는 답글은 **가장 최근 REPLIED** 의 본문이다 — 그 뒤에 "반영했어요" 가 와도 답글 문장은 남는다.
   */
  // 이력이 비어 있으면(`[]`) latestResponse 로 물러난다. 순서는 서버가 어느 쪽으로 주든 createdAt 으로 오래된 것부터 맞춘다
  const src = r.responses?.length ? r.responses : r.latestResponse ? [r.latestResponse] : [];
  const responses = [...src].sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
  const latest = responses.length > 0 ? responses[responses.length - 1] : null;
  const replied = [...responses].reverse().find((x) => x.action === 'REPLIED' && x.body);
  return {
    feedback_id: r.feedbackId,
    user_id: r.authorMemberId ?? null,
    product_id: r.productId,
    body: r.body,
    created_at: r.createdAt,
    axis_id: r.axisId,
    axis: axisLabel(r.axisId),
    // 백엔드는 id 만 준다 (계약 0.2.0). 표시 라벨은 어휘집에서 여기서 붙인다 — 화면이 label.axis·label.category 를 바로 읽는다
    labels: (r.labels ?? []).map((l) => ({ axis_id: l.axisId, axis: axisLabel(l.axisId), category_id: l.categoryId, category: categoryLabel(l.categoryId) })) as Feedback['labels'],
    primary: r.primary
      ? ({ axis_id: r.primary.axisId, axis: axisLabel(r.primary.axisId), category_id: r.primary.categoryId, category: categoryLabel(r.primary.categoryId) } as Feedback['primary'])
      : null,
    off_axis_hint: r.offAxisHint ?? null,
    category_id: r.primary?.categoryId ?? null,
    category: null,
    classifier: r.classifier ?? null,
    vocab_version: r.vocabVersion ?? null,
    classified_at: r.classifiedAt ?? null,
    banned_terms: r.bannedTerms ?? [],
    hidden_by_default: Boolean(r.hiddenByDefault),
    brand_name: brandName,
    profile: r.authorSkinTypeCode ? { skin_type: r.authorSkinTypeCode, skin_tone: r.authorSkinToneCode ?? '' } : null,
    // 옛 서버는 이 값을 안 준다. 그때는 `undefined` 로 두어 화면이 "모른다" 로 읽게 한다
    // 판매자 목록은 `isPurchaser` 로 주고(SQL case 식이라 드라이버에 따라 0/1 로도 온다), 옛 이름 `purchased` 도 받는다
    purchased: boolish(r.purchased ?? r.isPurchaser),
    classification_status: r.classificationStatus ?? null,
    // 처리 상태는 서버 것이다. 옛 서버(handlingStatus 없음)는 전부 '업체 확인 대기'
    status: statusOfHandling(r.handlingStatus),
    handling_status: (r.handlingStatus as Feedback['handling_status']) ?? null,
    latest_response: latest
      ? { action: latest.action as FeedbackResponseAction, body: latest.body ?? null, created_at: latest.createdAt }
      : null,
    reply: replied?.body ?? null,
    replied_at: r.lastRespondedAt ?? null,
    source: 'backend',
  };
}

/** GET /api/seller/feedback?brandId= 를 화면 타입(Feedback)으로 */
export async function fetchSellerFeedback(brandId: string, brandName: string): Promise<Feedback[] | null> {
  try {
    const res = await authFetch('SELLER', `/api/seller/feedback?brandId=${encodeURIComponent(brandId)}`);
    if (!res.ok) return null;
    const rows = (await res.json()) as SellerFeedbackRow[];
    if (!Array.isArray(rows)) return null;
    return rows.map((r) => feedbackFromRow(r, brandName));
  } catch {
    return null;
  }
}

/**
 * `GET /api/feedback/mine?productId=` — **내가** 보낸 의견과 사장님 응답 (백엔드 요청 2026-10-01).
 *
 * 전에는 서버 상품의 의견을 서버로 보내고 나면 읽을 길이 없어, "내가 보낸 의견" 목록 · 보냄 ✓ · 반영 건수 · 사장님 답글이
 * 전부 빈 채였다 (localStorage 사본은 서버 상품에는 안 쓴다). `null` 은 "못 받았다" — 아직 없는 서버(404)·로그인 없음·연결
 * 실패 전부. 화면은 그때 지금처럼 빈 채로 두고 오류를 띄우지 않는다.
 */
export async function fetchMyFeedback(productId: string, brandName: string): Promise<Feedback[] | null> {
  if (!hasMemberSession()) return null;
  try {
    const res = await authFetch('MEMBER', `/api/feedback/mine?productId=${encodeURIComponent(productId)}`);
    if (!res.ok) return null;
    const body = (await res.json()) as SellerFeedbackRow[] | { items?: SellerFeedbackRow[] };
    const rows = Array.isArray(body) ? body : Array.isArray(body.items) ? body.items : null;
    if (!rows) return null;
    // 서버가 productId 필터를 아직 안 받으면 전부 올 수 있다 — 여기서 한 번 더 거른다
    return rows.filter((r) => r.productId === productId).map((r) => feedbackFromRow(r, brandName));
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ 리뷰 (읽기) */

interface ReviewRow {
  reviewId: string;
  rating: number;
  isRecommended: boolean | number | null;
  title: string | null;
  body: string | null;
  createdAt: string;
}

/** GET /api/products/{id}/reviews. 작성자 피부 속성은 백엔드가 주지 않아 빈 값이다 */
export async function fetchBackendReviews(productId: string): Promise<Review[]> {
  try {
    const res = await fetch(`/api/products/${encodeURIComponent(productId)}/reviews`, { headers: { Accept: 'application/json' } });
    if (!res.ok) return [];
    const rows = (await res.json()) as ReviewRow[];
    if (!Array.isArray(rows)) return [];
    return rows.map((r) => ({
      review_id: r.reviewId,
      product_id: productId,
      author_id: 'member',
      rating: Number(r.rating),
      is_recommended: r.isRecommended === null || r.isRecommended === undefined ? null : Boolean(r.isRecommended),
      review_title: r.title,
      review_text: r.body,
      submission_time: String(r.createdAt).slice(0, 10),
      skin_type: 'normal' as Review['skin_type'],
      skin_tone: '',
      eye_color: '',
      hair_color: '',
    }));
  } catch {
    return [];
  }
}

/* ------------------------------------------------------------------ 판매자 대시보드 실측 */

export interface SellerPulse {
  orders: number;
  revenue: number;
  /** 팔린 개수 합계. 주문 수와 다르다 — 한 주문에 3개가 들어가면 주문 1, 수량 3 */
  units: number;
  /** 한 번이라도 팔린 상품 가짓수 */
  soldProducts: number;
  /** 주문 줄 수 (주문 × 상품). 주문 수와 상품 가짓수 사이를 메운다 */
  orderItems: number;
  reviews: number;
  feedbacks: number;
}

/* ------------------------------------------------------------------ 판매자 주문 목록 */

export interface SellerOrderItem {
  product_id: string;
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price: number;
  line_amount: number;
}

export interface SellerOrder {
  order_id: string;
  buyer_id: string;
  buyer_nickname: string | null;
  status: string;
  currency: string;
  /** 결제 시각 (없으면 생성 시각). ISO 문자열 */
  ordered_at: string | null;
  /** **내 브랜드 줄의 합.** 주문 총액이 아니다 — 다른 브랜드가 섞인 주문에서 남의 몫을 빼고 센다 */
  brand_amount: number;
  item_count: number;
  items: SellerOrderItem[];
}

/**
 * 한 번에 받는 주문 수. 서버 상한(MAX_LIMIT 1000)에 맞춘다. 서버 기본값 200 에 맡기면 주문이 200건을 넘는 순간
 * 기간 매출·누적 판매량이 조용히 줄어든다. 이 수만큼 돌아오면 잘렸을 수 있다 — 화면이 그렇게 적는다.
 * 합계를 서버가 따로 주면 이 상한과 무관해진다 (백엔드 요청 2026-09-23).
 */
export const SELLER_ORDER_LIMIT = 1000;

/**
 * `GET /api/seller/orders?brandId=&from=&to=&limit=` (docs/dashboard/seller-console-gaps.md §4).
 *
 * 못 읽으면 null 이다. 화면은 그때 "-" 를 적는다 — 빈 배열로 바꿔 돌려주면 "주문이 없다" 와 구분이 안 된다.
 */
export async function fetchSellerOrders(
  brandId: string,
  range?: { from: string; to: string },
): Promise<SellerOrder[] | null> {
  const query = new URLSearchParams({ brandId, limit: String(SELLER_ORDER_LIMIT) });
  if (range) {
    query.set('from', range.from);
    query.set('to', range.to);
  }
  try {
    const res = await authFetch('SELLER', `/api/seller/orders?${query.toString()}`);
    if (!res.ok) return null;
    const body = (await res.json()) as { orders?: unknown };
    if (!Array.isArray(body.orders)) return null;
    return body.orders as SellerOrder[];
  } catch {
    return null;
  }
}

export async function fetchSellerPulse(brandId: string): Promise<SellerPulse | null> {
  try {
    const res = await authFetch('SELLER', `/api/seller/dashboard?brandId=${encodeURIComponent(brandId)}`);
    if (!res.ok) return null;
    // 서버 컬럼 이름은 snake_case 다. 예전 서버(새 컬럼이 없는 판본)와도 돌아야 해서 없으면 0 이다.
    const j = (await res.json()) as Record<string, unknown>;
    const n = (v: unknown) => Number(v ?? 0);
    return {
      orders: n(j.orders),
      revenue: n(j.revenue),
      units: n(j.units),
      soldProducts: n(j.sold_products),
      orderItems: n(j.order_items),
      reviews: n(j.reviews),
      feedbacks: n(j.feedbacks),
    };
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ 정산 (판매자) */

/**
 * `settlement` 한 행. 서버(`GET /api/settlements`)가 테이블 컬럼을 그대로 준다 (snake_case).
 * `settlement_month` 는 그 달 1일 (`2026-09-01`). 수수료는 기획상 0% 라 `net_amount === gross_amount` 다.
 */
export interface Settlement {
  settlement_id: string;
  brand_id: string;
  settlement_month: string;
  currency: string;
  gross_amount: number;
  fee_amount: number;
  net_amount: number;
  status: 'PENDING' | 'COMPLETED';
  completed_at: string | null;
  completed_by: string | null;
}

/** 월별 정산 목록. 최신 달이 앞. 못 읽으면 null — 빈 배열은 "정산이 없다" 라서 구분한다 */
export async function fetchSettlements(brandId: string): Promise<Settlement[] | null> {
  try {
    const res = await authFetch('SELLER', `/api/settlements?brandId=${encodeURIComponent(brandId)}`);
    if (!res.ok) return null;
    const rows = (await res.json()) as Array<Record<string, unknown>>;
    if (!Array.isArray(rows)) return null;
    return rows.map((r) => ({
      settlement_id: String(r.settlement_id ?? ''),
      brand_id: String(r.brand_id ?? ''),
      settlement_month: String(r.settlement_month ?? '').slice(0, 10),
      currency: String(r.currency ?? 'KRW'),
      gross_amount: Number(r.gross_amount ?? 0),
      fee_amount: Number(r.fee_amount ?? 0),
      net_amount: Number(r.net_amount ?? 0),
      status: r.status === 'COMPLETED' ? 'COMPLETED' : 'PENDING',
      completed_at: r.completed_at ? String(r.completed_at) : null,
      completed_by: r.completed_by ? String(r.completed_by) : null,
    }));
  } catch {
    return null;
  }
}

export type GenerateSettlementResult =
  | { kind: 'ok'; settlementId: string; netAmount: number }
  /** 이미 완료된 달. 서버가 409 를 준다 — 완료된 정산은 다시 계산하지 않는다 */
  | { kind: 'completed' }
  | { kind: 'failed' };

/**
 * `POST /api/settlements/generate?brandId=&month=YYYY-MM`.
 * 그 달의 결제 완료 품목 중 아직 정산에 안 들어간 것을 더한다. 매일 02:00 배치가 같은 일을 하므로
 * 이 버튼은 "지금 바로 다시 세기" 다.
 */
export async function generateSettlement(brandId: string, month: string): Promise<GenerateSettlementResult> {
  try {
    const q = new URLSearchParams({ brandId, month });
    const res = await authFetch('SELLER', `/api/settlements/generate?${q.toString()}`, { method: 'POST' });
    if (res.status === 409) return { kind: 'completed' };
    if (!res.ok) return { kind: 'failed' };
    const j = (await res.json()) as { settlementId?: string; netAmount?: number };
    return { kind: 'ok', settlementId: String(j.settlementId ?? ''), netAmount: Number(j.netAmount ?? 0) };
  } catch {
    return { kind: 'failed' };
  }
}

/* ------------------------------------------------------------------ 판매자 피드백 처리 (2026-09-18) */

export interface FeedbackResponseResult {
  feedbackId: string;
  handlingStatus: string;
  lastRespondedAt: string | null;
  response: { feedbackResponseId: string; action: string; body: string | null; createdAt: string };
}

/**
 * `POST /api/seller/feedback/{feedbackId}/responses` — 확인(ACKNOWLEDGED) · 반영(IMPLEMENTED) · 답변(REPLIED, body 필수).
 * 201 이면 그 응답으로 목록의 행을 바로 갱신한다. 못 하면 null — 화면은 행을 그대로 두고 그렇다고 적는다.
 */
export async function respondToFeedback(
  feedbackId: string,
  action: FeedbackResponseAction,
  body?: string,
): Promise<FeedbackResponseResult | null> {
  try {
    const res = await authFetch('SELLER', `/api/seller/feedback/${encodeURIComponent(feedbackId)}/responses`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action === 'REPLIED' ? { action, body: body ?? '' } : { action }),
    });
    if (!res.ok) return null;
    const result = (await res.json()) as FeedbackResponseResult;
    // 서버가 같은 요청 안에서 고객 알림을 만든다 — 옆에 떠 있는 쇼핑몰 종에 빨간 점이 바로 뜨게 (2026-10-01)
    signalNotificationsChanged();
    return result;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ 인앱 알림 (2026-09-18) */

export type NotificationType = 'FEEDBACK_CREATED' | 'FEEDBACK_ACKNOWLEDGED' | 'FEEDBACK_REPLIED' | 'FEEDBACK_IMPLEMENTED';

export interface AppNotification {
  notificationId: string;
  type: NotificationType | string;
  title: string;
  body: string;
  feedbackId: string | null;
  payload: { productId?: string; productName?: string } | null;
  /** null 이면 안 읽음 */
  readAt: string | null;
  createdAt: string;
}

/**
 * 알림 API. 회원·판매자가 같은 경로를 쓰고 누구에게 어떤 알림이 가는지는 서버가 거른다.
 * 세션 복원 · 탭 복귀 · 창 포커스 · 종 클릭 · 같은 브라우저의 알림 신호(lib/notifySignal) · 보이는 동안 3초마다 부른다.
 * 전부 못 읽으면 null 이다. 0 과 "못 읽음" 을 화면이 구분해야 배지를 잘못 지우지 않는다.
 */
export async function fetchNotifications(role: AccountRole, limit = 20): Promise<AppNotification[] | null> {
  try {
    const res = await authFetch(role, `/api/notifications?limit=${limit}`);
    if (!res.ok) return null;
    const body = (await res.json()) as { items?: unknown };
    if (!Array.isArray(body.items)) return null;
    return (body.items as Array<Record<string, unknown>>).map((n) => ({
      notificationId: String(n.notificationId ?? ''),
      type: String(n.type ?? ''),
      title: typeof n.title === 'string' ? n.title : '',
      body: typeof n.body === 'string' ? n.body : '',
      feedbackId: typeof n.feedbackId === 'string' ? n.feedbackId : null,
      payload: n.payload && typeof n.payload === 'object' ? (n.payload as AppNotification['payload']) : null,
      readAt: typeof n.readAt === 'string' ? n.readAt : null,
      createdAt: typeof n.createdAt === 'string' ? n.createdAt : '',
    }));
  } catch {
    return null;
  }
}

export async function fetchUnreadCount(role: AccountRole): Promise<number | null> {
  try {
    const res = await authFetch(role, '/api/notifications/unread-count');
    if (!res.ok) return null;
    const body = (await res.json()) as { count?: unknown };
    return typeof body.count === 'number' ? body.count : null;
  } catch {
    return null;
  }
}

/** 읽음 처리. 서버가 찍은 readAt 을 돌려준다. 못 하면 null */
export async function markNotificationRead(role: AccountRole, notificationId: string): Promise<string | null> {
  try {
    const res = await authFetch(role, `/api/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'PATCH' });
    if (!res.ok) return null;
    const body = (await res.json()) as { readAt?: unknown };
    return typeof body.readAt === 'string' ? body.readAt : new Date().toISOString();
  } catch {
    return null;
  }
}

/** 전부 읽음. 바뀐 건수를 돌려준다. 못 하면 null */
export async function markAllNotificationsRead(role: AccountRole): Promise<number | null> {
  try {
    const res = await authFetch(role, '/api/notifications/read-all', { method: 'PATCH' });
    if (!res.ok) return null;
    const body = (await res.json()) as { updatedCount?: unknown };
    return typeof body.updatedCount === 'number' ? body.updatedCount : 0;
  } catch {
    return null;
  }
}
