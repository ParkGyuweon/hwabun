/**
 * shop_backend(8090) 어댑터 · 프론트 선에서 붙일 수 있는 것은 전부 여기로 붙인다 (2026-09-10).
 *
 * 원칙
 *   · 백엔드가 있으면 쓰고, 없거나 거절하면 **지금까지의 목(mock) 경로로 조용히 물러난다.**
 *     시연이 백엔드 상태에 볼모로 잡히지 않아야 한다. 어느 경로를 탔는지는 화면에 밝힌다.
 *   · 세포라 200개·SSAFY Beauty 시드는 백엔드 DB 에 없다. 그 상품은 장바구니·주문·피드백 API 를
 *     탈 수 없으므로 목 경로다. 백엔드에서 온 상품(`source: 'backend'`)만 API 를 탄다.
 *   · 이벤트 로그(`/api/events`, 8080)는 이 파일과 무관하다. 그대로 나간다.
 *
 * 백엔드 응답 모양은 shop_backend/…/CatalogController · CommerceController · FeedbackController 의
 * record 정의를 그대로 옮겼다. 필드 이름이 camelCase 인 이유다.
 *
 * 알려진 백엔드 제약 (요청 메시지에 적어 보냄)
 *   · 모든 4xx 가 401 {"error":"unauthorized"} 로 바뀐다. /error 가 permitAll 이 아니라서다.
 *     그래서 여기서는 상태 코드로만 분기하고 401 을 "인증 실패" 로 단정하지 않는다.
 *   · category 시드가 없어 POST /api/products 는 지금 항상 실패한다. 실패하면 로컬 등록으로 물러난다.
 *   · 새 상품은 DRAFT 로 만들어져 목록에 안 뜬다. 등록 성공 직후 ACTIVE 로 바꾸는 요청을 한 번 더 보낸다.
 */
import { authFetch, sessionSnapshot } from './auth';
import { loadBrandId } from './brands';
import { KRW_PER_USD } from './localize';
import { isNewRegistered } from './newBrandRule';
import { axisLabel, categoryLabel } from '../types/feedback';
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

/** 실패 응답을 한 문장으로. 백엔드가 4xx 를 401 로 바꾸는 버그가 있어 상태 코드만 믿지 않는다 */
async function reasonOf(res: Response): Promise<string> {
  let text = '';
  try {
    text = await res.text();
  } catch {
    /* 본문 없음 */
  }
  if (res.status === 401 && text.includes('unauthorized')) {
    return '백엔드가 요청을 거절했습니다 (401). 로그인 만료이거나, 백엔드가 4xx 를 401 로 돌려주는 알려진 문제일 수 있습니다';
  }
  if (res.status === 403) return '권한이 없습니다 (403). 구매한 상품에만 남길 수 있거나, 다른 역할의 계정입니다';
  if (res.status === 404) return '백엔드에 없는 상품입니다 (404)';
  if (res.status === 409) return '이미 있는 항목입니다 (409)';
  if (res.status >= 500) return `백엔드 오류 (${res.status})`;
  try {
    const j = JSON.parse(text) as { message?: string; error?: string };
    if (j.message) return j.message;
    if (j.error) return j.error;
  } catch {
    /* 텍스트 본문 */
  }
  return text ? text.slice(0, 120) : `요청 실패 (${res.status})`;
}

const fail = async (res: Response): Promise<ApiFailure> => ({ ok: false, status: res.status, reason: await reasonOf(res) });
const offline = (): ApiFailure => ({ ok: false, status: 0, reason: '백엔드에 연결할 수 없습니다' });

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
}
interface ProductDetailDto {
  product: ProductSummaryDto;
  variants: VariantDto[];
  ingredients: string | null;
  description: Record<string, unknown> | null;
}

function mapSummary(s: ProductSummaryDto): Product {
  return {
    product_id: s.productId,
    product_name: s.productName,
    brand_name: s.brandName ?? '',
    category: ['Skincare', s.secondaryCategory, s.tertiaryCategory].filter(Boolean),
    image_url: s.primaryImageUrl,
    sku_id: null,
    images: s.primaryImageUrl ? [s.primaryImageUrl] : [],
    variants: [],
    description: null,
    price_usd: krwToUsd(s.priceKrw),
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
  const variants: ProductVariant[] = active.map((v) => ({
    sku_id: v.skuId,
    label: v.label,
    image_url: base.image_url ?? '',
    swatch_url: null,
    variant_id: v.variantId,
  }));
  const first = active[0];
  const sale = first?.salePriceKrw != null ? krwToUsd(first.salePriceKrw) : null;
  return {
    ...base,
    variants,
    size: first?.size ?? null,
    description: mapDescription(d.description),
    ingredients: d.ingredients && d.ingredients.trim() ? [d.ingredients.trim()] : [],
    sale_price_usd: sale && sale < base.price_usd ? sale : null,
    discount_label: sale && sale < base.price_usd ? '할인' : undefined,
  };
}

/**
 * 백엔드 카탈로그. 목록은 요약만 주므로 상세를 상품마다 한 번 더 부른다.
 * 백엔드 상품은 사장님이 직접 등록한 것뿐이라 수가 작다. 실패한 상세는 요약으로 대신한다.
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
  const details = await Promise.all(
    rows.map(async (s) => {
      try {
        const r = await fetch(`/api/products/${encodeURIComponent(s.productId)}`, { headers: { Accept: 'application/json' } });
        if (!r.ok) return mapSummary(s);
        return mapDetail((await r.json()) as ProductDetailDto);
      } catch {
        return mapSummary(s);
      }
    }),
  );
  return details;
}

/* ------------------------------------------------------------------ 상품 등록 (판매자) */

export type RegisterResult = { ok: true; product: Product; activated: boolean } | ApiFailure;

/**
 * POST /api/products. 폼(snake_case)을 백엔드 record(camelCase)로 옮긴다.
 *
 * categoryId 는 백엔드 `category` 테이블의 id 인데 시드가 비어 있어 무엇을 보내도 지금은 400 이다.
 * 2차 카테고리 코드를 보낸다. 백엔드에 "category 를 secondary_category 코드로 시드해 달라" 고 요청했다.
 * 그 시드가 들어오면 이 함수는 손대지 않아도 통과한다.
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

/** 장바구니 전부가 백엔드 상품(옵션 id 있음)이고 고객 로그인이 있을 때만 API 를 탈 수 있다 */
export function canCheckoutOnBackend(items: CartItem[]): boolean {
  return items.length > 0 && hasMemberSession() && items.every((i) => Boolean(i.variant_id));
}

/**
 * 서버 장바구니에 담고 → 주문 만들고 → 결제까지. 셋을 한 번에 한다.
 * 결제 연동은 없고 백엔드가 PAID 로 표시만 한다. 그래야 피드백·리뷰 API 의 "구매 이력" 조건이 성립한다.
 */
export async function checkoutOnBackend(items: CartItem[], idempotencyKey: string): Promise<CheckoutResult> {
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
    if (!orderId) return { ok: false, status: created.status, reason: '주문 응답에 주문 번호가 없습니다' };
    const paid = await authFetch('MEMBER', `/api/orders/${encodeURIComponent(orderId)}/pay`, { method: 'POST' });
    if (!paid.ok) return fail(paid);
    const paidBody = (await paid.json()) as Record<string, unknown>;
    return { ok: true, orderId, status: String(paidBody.status ?? 'PAID') };
  } catch {
    return offline();
  }
}

/* ------------------------------------------------------------------ 피드백 */

export type FeedbackSubmitResult = { ok: true; feedbackId: string } | ApiFailure;

/** POST /api/feedback. 백엔드가 이 고객의 PAID 주문을 직접 확인한다. 없으면 403 이 정상이다 */
export async function submitFeedbackBackend(input: { productId: string; axisId: string; body: string }): Promise<FeedbackSubmitResult> {
  if (!hasMemberSession()) return { ok: false, status: 0, reason: '고객 로그인이 없습니다' };
  try {
    const res = await authFetch('MEMBER', '/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!res.ok) return fail(res);
    const j = (await res.json()) as { feedbackId: string };
    return { ok: true, feedbackId: j.feedbackId };
  } catch {
    return offline();
  }
}

interface SellerFeedbackRow {
  feedbackId: string;
  productId: string;
  productName: string;
  authorMemberId: string;
  authorSkinTypeCode: string | null;
  authorSkinToneCode: string | null;
  axisId: string;
  body: string;
  status: string;
  createdAt: string;
  labels: Array<{ axisId: string; categoryId: string }>;
  primary: { axisId: string; categoryId: string } | null;
  offAxisHint: string | null;
  classifier: string | null;
  vocabVersion: string | null;
  classifiedAt: string | null;
  bannedTerms: string[];
  classificationStatus: string;
  hiddenByDefault: boolean;
}

/** GET /api/seller/feedback?brandId= 를 화면 타입(Feedback)으로. 분류 전이면 labels 가 빈 배열로 온다 */
export async function fetchSellerFeedback(brandId: string, brandName: string): Promise<Feedback[] | null> {
  try {
    const res = await authFetch('SELLER', `/api/seller/feedback?brandId=${encodeURIComponent(brandId)}`);
    if (!res.ok) return null;
    const rows = (await res.json()) as SellerFeedbackRow[];
    if (!Array.isArray(rows)) return null;
    return rows.map((r) => ({
      feedback_id: r.feedbackId,
      user_id: r.authorMemberId,
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
      off_axis_hint: r.offAxisHint,
      category_id: r.primary?.categoryId ?? null,
      category: null,
      classifier: r.classifier,
      vocab_version: r.vocabVersion,
      classified_at: r.classifiedAt,
      banned_terms: r.bannedTerms ?? [],
      hidden_by_default: Boolean(r.hiddenByDefault),
      brand_name: brandName,
      profile: r.authorSkinTypeCode ? { skin_type: r.authorSkinTypeCode, skin_tone: r.authorSkinToneCode ?? '' } : null,
      status: 'new',
      reply: null,
      replied_at: null,
      source: 'backend',
    }));
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
  reviews: number;
  feedbacks: number;
}

export async function fetchSellerPulse(brandId: string): Promise<SellerPulse | null> {
  try {
    const res = await authFetch('SELLER', `/api/seller/dashboard?brandId=${encodeURIComponent(brandId)}`);
    if (!res.ok) return null;
    const j = (await res.json()) as Partial<SellerPulse>;
    return { orders: Number(j.orders ?? 0), revenue: Number(j.revenue ?? 0), reviews: Number(j.reviews ?? 0), feedbacks: Number(j.feedbacks ?? 0) };
  } catch {
    return null;
  }
}
