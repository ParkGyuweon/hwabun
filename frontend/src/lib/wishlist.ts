/**
 * 찜 표시 · 세션 동안만 기억한다.
 *
 * 백엔드에 찜 API 가 없어 저장할 곳이 없다. 그래도 "찜 눌렀다 → 뒤로 → 목록이 바뀌었다" 시연 흐름에서
 * 상세로 다시 들어갔을 때 하트가 꺼져 있으면 눌린 게 맞는지 헷갈린다 (AI 파트 요청 2026-09-14 §3).
 * 그래서 이 탭이 살아 있는 동안 `sessionStorage` 에 product_id 집합을 둔다. 이벤트(`wishlist_toggle`)는
 * 여기와 무관하게 호출부가 그대로 남긴다 — 저장은 표시용이지 신호가 아니다.
 *
 * **계정마다 따로 둔다** (2026-09-30). 전에는 탭 하나에 키 하나(`bloom.wishlist.v1`)라, 같은 탭에서 로그아웃하고
 * 새 계정을 만들면 앞 사람의 하트가 눌린 채 보였다. 새 계정이 그 하트를 누르면 '찜 취소(remove)' 가 나가
 * 추천 서버에는 좋아요가 한 번도 안 쌓였다 — 시연의 "좋아요 → 싸피뷰티가 추천에 올라온다" 가 죽었다.
 * 이제 키가 `bloom.wishlist.v1:<회원 id | guest>` 이고, App 이 로그인한 사람이 바뀔 때 `setWishlistOwner` 를 부른다.
 *
 * 찜 API 가 생기면 `load`/`persist` 두 함수 본문만 바뀐다.
 */
import { useSyncExternalStore } from 'react';

const BASE = 'bloom.wishlist.v1';
const GUEST = 'guest';
const listeners = new Set<() => void>();
let owner = GUEST;
let cache: Set<string> | null = null;

const keyOf = (who: string) => `${BASE}:${who}`;

function notify(): void {
  for (const l of listeners) l();
}

function load(): Set<string> {
  if (cache) return cache;
  try {
    const raw = typeof window !== 'undefined' ? window.sessionStorage.getItem(keyOf(owner)) : null;
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
    window.sessionStorage.setItem(keyOf(owner), JSON.stringify([...next]));
  } catch {
    /* 저장 불가(시크릿 모드 등)면 메모리만 */
  }
  notify();
}

/**
 * 지금 찜을 보는 사람. 로그인한 회원 id, 로그인 안 했으면 null(비회원). 바뀌면 그 사람의 찜으로 갈아 끼운다.
 * 계정마다 키가 다르니 새로 가입한 계정은 늘 빈 찜으로 시작한다.
 */
export function setWishlistOwner(memberId: string | null): void {
  const next = memberId || GUEST;
  if (next === owner) return;
  owner = next;
  cache = null;
  notify();
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

/** 지금 사람의 찜을 전부 지운다. 회원 탈퇴 뒤 이 탭에 남기지 않기 위해서다 (lib/memberWithdraw) */
export function clearWishlist(): void {
  cache = new Set();
  try {
    window.sessionStorage.removeItem(keyOf(owner));
    window.sessionStorage.removeItem(BASE); // 계정별로 나누기 전(09-30 이전)의 옛 키
  } catch {
    /* 저장소를 못 쓰면 메모리만 비운다 */
  }
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 이 상품이 찜돼 있나. 다른 화면(퀵룩·상세)에서 바꿔도, 로그인한 사람이 바뀌어도 따라온다 */
export function useWished(productId: string): boolean {
  return useSyncExternalStore(
    subscribe,
    () => isWished(productId),
    () => false,
  );
}
