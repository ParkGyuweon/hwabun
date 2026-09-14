/**
 * 결제 — 포트원 V2 + 카카오페이 (테스트 채널). AI 파트 정리 2026-09-14 · 코치 안내(help.portone.io/content/kakaopay).
 *
 * 흐름 (App.placeOrder)
 *   1. POST /api/orders                → 서버가 주문 생성, totalAmount(KRW 정수) 응답
 *   2. PortOne.requestPayment(...)     → 카카오페이 결제창. PC 는 IFRAME, 모바일은 REDIRECTION (채널 정책, 우리가 못 고른다)
 *   3. POST /api/orders/{id}/confirm   → 서버가 포트원 조회 + 금액 대조 → PAID. **이 응답이 정본**이고 purchase 이벤트도 그 뒤에 남긴다
 *
 * 켜지는 조건: `VITE_PORTONE_STORE_ID` · `VITE_PORTONE_CHANNEL_KEY` 둘 다 있을 때. 둘은 공개 가능한 값이다.
 * API Secret 은 서버 전용이라 프론트에 없다. 키가 없으면 지금까지의 테스트 주문(`/pay` · 로컬)으로 간다 — 없는 기능을
 * 있는 것처럼 두지 않는다.
 *
 * 금액은 **서버가 준 KRW 정수만** 넘긴다. 표시가(달러 × 1,340.86)와 1원 차이가 나도 결제는 서버 값이고, 서버가 confirm 에서
 * 포트원 `amount.total` 과 대조하므로 위변조가 막힌다.
 */
import type { PaymentRequest, PaymentResponse } from '@portone/browser-sdk/v2';

export const PORTONE_STORE_ID: string = (import.meta.env.VITE_PORTONE_STORE_ID as string | undefined) ?? '';
export const PORTONE_CHANNEL_KEY: string = (import.meta.env.VITE_PORTONE_CHANNEL_KEY as string | undefined) ?? '';

/** 결제 연동이 켜져 있나 (콘솔 값 둘 다 있음) */
export function isPaymentEnabled(): boolean {
  return PORTONE_STORE_ID.length > 0 && PORTONE_CHANNEL_KEY.length > 0;
}

/** 시연은 포트원 테스트 채널이다. 완료 화면 문구가 이 값을 본다 */
export const PAYMENT_PROVIDER = 'portone' as const;
export type PaymentMethod = 'kakaopay' | 'card' | 'test';

/**
 * `payment_failed` 이벤트 스위치. 계약(event-properties-schema §6 · event-schema.json)과 수집기 INTENTS 에 등록되기 전에
 * 보내면 `unregistered_event` 로 거절된다 (데이터·AI 파트가 넣기로 함, 2026-09-14). 등록되면 true 로.
 */
export const PAYMENT_FAILED_EVENT_ENABLED = false;

/** 포트원 paymentId. 주문 1건당 고유 — 중복 결제 방지 키 */
export const paymentIdFor = (orderId: string): string => `hwabun-${orderId}`;

/** 모바일 REDIRECTION 복귀 주소. 쿼리로 돌아온다 (`/?order=…&pay=return&paymentId=…` 또는 `&code=…&message=…`) */
export function paymentReturnUrl(orderId: string): string {
  const u = new URL(window.location.origin + '/');
  u.searchParams.set('order', orderId);
  u.searchParams.set('pay', 'return');
  return u.toString();
}

export type PaymentResult =
  | { ok: true; paymentId: string; txId: string | null }
  | { ok: false; code: string; message: string };

export interface KakaoPayInput {
  orderId: string;
  /** 서버가 준 KRW 정수 */
  totalAmountKrw: number;
  /** 결제창에 보이는 주문 이름 (예: "BLOOM 주문 3건") */
  orderName: string;
  customer?: { fullName?: string; email?: string };
}

/**
 * 카카오페이 결제창. SDK 는 결제할 때만 내려받는다 (동적 import) — 목록·상세 번들에 안 들어간다.
 * PC 에서는 이 Promise 가 결제창 결과로 풀리고, 모바일에서는 리다이렉트돼 돌아오지 않는다 (복귀는 `parsePaymentReturn`).
 */
export async function requestKakaoPay(input: KakaoPayInput): Promise<PaymentResult> {
  if (!isPaymentEnabled()) return { ok: false, code: 'NOT_CONFIGURED', message: '결제 키가 설정되지 않았습니다' };
  let PortOne: typeof import('@portone/browser-sdk/v2');
  try {
    PortOne = await import('@portone/browser-sdk/v2');
  } catch {
    return { ok: false, code: 'SDK_LOAD_FAILED', message: '결제 모듈을 불러오지 못했습니다' };
  }
  const request: PaymentRequest = {
    storeId: PORTONE_STORE_ID,
    channelKey: PORTONE_CHANNEL_KEY,
    paymentId: paymentIdFor(input.orderId),
    orderName: input.orderName,
    totalAmount: Math.round(input.totalAmountKrw),
    currency: 'CURRENCY_KRW',
    // 카카오페이는 EASY_PAY 고정. easyPayProvider 는 채널이 정해 무시된다
    payMethod: 'EASY_PAY',
    customer: input.customer,
    redirectUrl: paymentReturnUrl(input.orderId),
  };
  let res: PaymentResponse | undefined;
  try {
    res = await PortOne.requestPayment(request);
  } catch (e) {
    return { ok: false, code: 'SDK_ERROR', message: e instanceof Error ? e.message : '결제창을 열지 못했습니다' };
  }
  if (!res) return { ok: false, code: 'NO_RESPONSE', message: '결제 응답이 없습니다' };
  if (res.code) return { ok: false, code: String(res.code), message: res.message ?? '결제가 완료되지 않았습니다' };
  return { ok: true, paymentId: res.paymentId ?? paymentIdFor(input.orderId), txId: res.txId ?? null };
}

/** 모바일 리다이렉트 복귀 쿼리. 아니면 null */
export function parsePaymentReturn(search: string = window.location.search): {
  orderId: string;
  paymentId: string | null;
  code: string | null;
  message: string | null;
} | null {
  const q = new URLSearchParams(search);
  const orderId = q.get('order');
  if (!orderId || q.get('pay') !== 'return') return null;
  return {
    orderId,
    paymentId: q.get('paymentId'),
    code: q.get('code'),
    message: q.get('message'),
  };
}

/* ---------- 리다이렉트를 건너는 주문 임시 저장 ----------
 * 모바일은 결제창으로 페이지가 떠났다 돌아오므로 React 상태(장바구니·주문 번호·금액)가 사라진다.
 * 결제창을 열기 직전에 여기 두고, 돌아오면 꺼내 confirm 을 부른다. 같은 탭에서만 유효하다.
 */
const PENDING_KEY = 'bloom.payment.pending.v1';

export interface PendingPayment {
  orderId: string;
  items: Array<{ product_id: string; quantity: number; unit_price: number; sku_id?: string }>;
  count: number;
  total: number;
  paid: number;
  totalAmountKrw: number;
}

export function savePendingPayment(p: PendingPayment): void {
  try {
    window.sessionStorage.setItem(PENDING_KEY, JSON.stringify(p));
  } catch {
    /* 저장 불가면 복귀 후 주문 확인만 못 한다 */
  }
}

export function takePendingPayment(orderId: string): PendingPayment | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as PendingPayment;
    if (p.orderId !== orderId) return null;
    window.sessionStorage.removeItem(PENDING_KEY);
    return p;
  } catch {
    return null;
  }
}

export function clearPendingPayment(): void {
  try {
    window.sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* 무시 */
  }
}
