/**
 * 결제 — 포트원 V2 + 카카오페이 (테스트 채널). AI 파트 정리 2026-09-14 · 코치 안내(help.portone.io/content/kakaopay).
 *
 * 흐름 (App.placeOrder)
 *   1. POST /api/orders                → 서버가 주문 생성, totalAmount(KRW 정수) 응답
 *   2. PortOne.requestPayment(...)     → 카카오페이 결제창. PC 는 IFRAME, 모바일은 REDIRECTION (채널 정책, 우리가 못 고른다)
 *   3. POST /api/orders/{id}/confirm   → 서버가 포트원 조회 + 금액 대조 → PAID. **이 응답이 정본**이고 purchase 이벤트도 그 뒤에 남긴다
 *
 * 켜지는 조건: `VITE_PORTONE_STORE_ID` · `VITE_PORTONE_CHANNEL_KEY` 둘 다 있고 **테스트 주문 스위치가
 * 꺼져 있을 때** (자동화 브라우저가 아니고 `?pay=test` 도 없을 때).
 * API Secret 은 서버 전용이라 프론트에 없다. 키가 없으면 백엔드 테스트 주문(`/pay`)으로 간다 — 없는 기능을
 * 있는 것처럼 두지 않는다.
 *
 * 금액은 **서버가 준 KRW 정수만** 넘긴다. 표시가(달러 × 1,340.86)와 1원 차이가 나도 결제는 서버 값이고, 서버가 confirm 에서
 * 포트원 `amount.total` 과 대조하므로 위변조가 막힌다.
 */
import type { PaymentRequest, PaymentResponse } from '@portone/browser-sdk/v2';

export const PORTONE_STORE_ID: string = (import.meta.env.VITE_PORTONE_STORE_ID as string | undefined) ?? '';
export const PORTONE_CHANNEL_KEY: string = (import.meta.env.VITE_PORTONE_CHANNEL_KEY as string | undefined) ?? '';

/**
 * 에이전트용 테스트 주문 스위치 (AI 파트 요청 2026-09-16 · 방식 확정 (다) 2026-09-16).
 *
 * PA 러너(Playwright)는 카카오페이 창을 넘을 수 없다 — 카카오 로그인·QR 승인이 필요해 자동화가 막힌다.
 * 그래서 배포본에서 에이전트는 `begin_checkout` 까지만 가고 `purchase` 가 안 남는다. 재구매 지표는
 * "같은 사람·같은 상품·다른 주문 2건" 이라 에이전트가 배포본에서 주문을 **끝까지** 내야 마트에 잡힌다.
 *
 * **자동으로 켜지고, 주소로 덮어쓸 수 있다.**
 *
 * | 상태 | 판정 | 언제 |
 * | --- | --- | --- |
 * | 주소 `?pay=test` | 강제로 켬 (저장) | 사람이 에이전트 경로를 그대로 재현할 때 |
 * | 주소 `?pay=live` (`?pay=off`) | 강제로 끔 (저장) | 러너 브라우저에서 결제창까지 눈으로 볼 때 |
 * | 저장값 없음 | `navigator.webdriver` | 평소. **러너는 아무것도 안 바꿔도 켜진다** |
 *
 * 자동 판별을 기본으로 둔 이유는 둘이다. 러너가 URL 을 관리하지 않아도 되고, **사람은 켤 수 없다** —
 * 일반 브라우저는 `navigator.webdriver` 가 참이 되지 않으므로 배포본에 두어도 결제 우회 통로가 열리지
 * 않는다. `?dev=1`(`devtools.ts`)이 페르소나 선택기·로그 창을 켜는 것과 같은 신호·같은 방식이다.
 *
 * 저장값이 `live` 면 `webdriver` 여도 끈다. 강제가 자동보다 세다 — 그래야 러너 브라우저로 결제창을
 * 확인할 길이 남는다.
 *
 * `pay=return` 은 건드리지 않는다. 모바일 결제창 복귀 쿼리라(`parsePaymentReturn`) 뜻이 다르고,
 * 이 스위치가 켜지면 결제창 자체를 열지 않아 복귀도 없다.
 *
 * 일반 사용자 경로는 그대로다. 이 값이 하는 일은 **결제 키가 없던 때로 되돌리는 것뿐**이라 없는 기능을
 * 있는 것처럼 만들지 않는다. 완료 화면 문구와 `purchase` 이벤트의 `payment_method` 는 지금처럼 `test` 로
 * 남아 마트에서 카카오페이 주문과 구분된다.
 */
const PAY_MODE_KEY = 'hwabun.pay';

/** 자동화 브라우저인가. Playwright 러너는 항상 참, 사람 브라우저는 절대 참이 되지 않는다 */
const isAutomatedBrowser = (): boolean => typeof navigator !== 'undefined' && navigator.webdriver === true;

export function isTestPayForced(): boolean {
  if (typeof window === 'undefined') return false;
  const q = new URLSearchParams(window.location.search).get('pay');
  try {
    if (q === 'test') window.localStorage.setItem(PAY_MODE_KEY, 'test');
    if (q === 'live' || q === 'off') window.localStorage.setItem(PAY_MODE_KEY, 'live');
    const saved = window.localStorage.getItem(PAY_MODE_KEY);
    // 강제가 자동보다 세다. 저장값이 없을 때만 브라우저를 본다
    if (saved === 'test') return true;
    if (saved === 'live') return false;
  } catch {
    // 저장이 막힌 환경(사생활 보호 창 등)이면 주소와 브라우저만 본다
    if (q === 'test') return true;
    if (q === 'live' || q === 'off') return false;
  }
  return isAutomatedBrowser();
}

/** 결제 연동이 켜져 있나 (콘솔 값 둘 다 있음 · 테스트 주문 스위치가 꺼져 있음) */
export function isPaymentEnabled(): boolean {
  if (isTestPayForced()) return false;
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
    customData: { orderId: input.orderId },
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
