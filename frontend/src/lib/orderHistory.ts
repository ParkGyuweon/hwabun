/**
 * 주문 내역 · 마이페이지가 읽는다.
 *
 * shop_backend 에 주문 **목록** API 가 없다 (`POST /api/orders` · `POST /api/orders/{id}/pay` 만 있다,
 * `docs/shop-backend-requests.md` 8번 요청). 그래서 주문 완료 화면이 받은 결과(PlacedOrder)를
 * 이 브라우저에 계정별로 쌓아 두고 보여준다. 서버 주문(`mode: backend`)이든 로컬 테스트 주문이든
 * 한 줄로 밝혀 적는다. `GET /api/orders` 가 생기면 그 응답을 앞에 두고 여기 것은 로컬 표시로 남긴다.
 *
 * 비로그인 주문은 `anonymous` 키에 쌓인다. 로그인하면 그 사람 것으로 옮기지 않는다 —
 * 누구 것인지 알 수 없어서다.
 */
import type { PlacedOrder } from './checkout';

export interface OrderRecord extends PlacedOrder {
  /** ISO. 화면 정렬·표시용 */
  placed_at: string;
}

const KEY_PREFIX = 'bloom.orders.v1.';
const MAX_KEEP = 50;
const listeners = new Set<() => void>();

const keyFor = (accountId: string | null) => `${KEY_PREFIX}${accountId ?? 'anonymous'}`;

const EMPTY: OrderRecord[] = [];
/** 같은 저장본 → 같은 배열 참조. useSyncExternalStore 의 getSnapshot 규칙 (memberProfile.ts 와 같은 이유) */
const snapshotCache = new Map<string, { raw: string | null; value: OrderRecord[] }>();

export function loadOrders(accountId: string | null): OrderRecord[] {
  const key = keyFor(accountId);
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    return EMPTY;
  }
  const hit = snapshotCache.get(key);
  if (hit && hit.raw === raw) return hit.value;
  let value = EMPTY;
  if (raw) {
    try {
      const rows = JSON.parse(raw) as OrderRecord[];
      value = Array.isArray(rows) ? rows : EMPTY;
    } catch {
      value = EMPTY;
    }
  }
  snapshotCache.set(key, { raw, value });
  return value;
}

export function appendOrder(accountId: string | null, order: PlacedOrder): void {
  const rows = loadOrders(accountId);
  if (rows.some((r) => r.orderId === order.orderId)) return; // 같은 주문 두 번 저장 금지
  const next: OrderRecord[] = [{ ...order, placed_at: new Date().toISOString() }, ...rows].slice(0, MAX_KEEP);
  try {
    window.localStorage.setItem(keyFor(accountId), JSON.stringify(next));
  } catch {
    /* 저장 불가 */
  }
  for (const l of listeners) l();
}

export function subscribeOrders(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key && e.key.startsWith(KEY_PREFIX)) listener();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}
