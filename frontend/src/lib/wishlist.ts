/**
 * 찜 표시 · 세션 동안만 기억한다.
 *
 * 백엔드에 찜 API 가 없어 저장할 곳이 없다. 그래도 "찜 눌렀다 → 뒤로 → 목록이 바뀌었다" 시연 흐름에서
 * 상세로 다시 들어갔을 때 하트가 꺼져 있으면 눌린 게 맞는지 헷갈린다 (AI 파트 요청 2026-09-14 §3).
 * 그래서 이 탭이 살아 있는 동안 `sessionStorage` 에 product_id 집합을 둔다. 이벤트(`wishlist_toggle`)는
 * 여기와 무관하게 호출부가 그대로 남긴다 — 저장은 표시용이지 신호가 아니다.
 *
 * 찜 API 가 생기면 `load`/`persist` 두 함수 본문만 바뀐다.
 */
import { useSyncExternalStore } from 'react';

const KEY = 'bloom.wishlist.v1';
const listeners = new Set<() => void>();
let cache: Set<string> | null = null;

function load(): Set<string> {
  if (cache) return cache;
  try {
    const raw = typeof window !== 'undefined' ? window.sessionStorage.getItem(KEY) : null;
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    cache = new Set(Array.isArray(arr) ? arr.filter((v): v is string => typeof v === 'string') : []);
  } catch {
    cache = new Set();
  }
  return cache;
}

function persist(next: Set<string>): void {
  cache = next;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify([...next]));
  } catch {
    /* 저장 불가(시크릿 모드 등)면 메모리만 */
  }
  for (const l of listeners) l();
}

export function isWished(productId: string): boolean {
  return load().has(productId);
}

export function setWished(productId: string, on: boolean): void {
  const next = new Set(load());
  if (on) next.add(productId);
  else next.delete(productId);
  persist(next);
}

/** 찜을 전부 지운다. 회원 탈퇴 뒤 이 탭에 남기지 않기 위해서다 (lib/memberWithdraw) */
export function clearWishlist(): void {
  cache = new Set();
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* 저장소를 못 쓰면 메모리만 비운다 */
  }
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 이 상품이 찜돼 있나. 다른 화면(퀵룩·상세)에서 바꿔도 따라온다 */
export function useWished(productId: string): boolean {
  return useSyncExternalStore(
    subscribe,
    () => isWished(productId),
    () => false,
  );
}
