/**
 * "로그인이 필요합니다" 를 화면 아무 데서나 띄우기 위한 작은 store.
 *
 * 로그인 모달은 헤더의 `AccountMenu` 안에 있다. 쇼핑몰은 로그인 없이 둘러볼 수 있어야 해서
 * `AuthGate`(전체 화면 게이트)를 쓰지 않기 때문이다. 그런데 상품 상세의 "바로 구매" 처럼
 * **로그인이 있어야만 되는 동작**이 헤더 밖에 생기면, 그 자리에서 모달을 열 방법이 없었다.
 *
 * 그래서 호출부는 `requestLogin(이유)` 만 부르고, 모달을 실제로 여는 것은 `AccountMenu` 가 한다.
 * 모달을 두 벌 만들지 않기 위해서다 — 로그인 폼이 두 군데 있으면 가입·에러 문구가 조용히 갈라진다.
 *
 * `이유` 는 모달 위에 한 줄로 뜬다. 왜 갑자기 로그인 창이 떴는지 모르면 닫아 버린다.
 */
import { useSyncExternalStore } from 'react';

const listeners = new Set<() => void>();
let reason: string | null = null;

/** 로그인 모달을 열어 달라고 요청한다. `reason` 은 모달에 그대로 적힌다 */
export function requestLogin(why: string): void {
  reason = why;
  for (const l of listeners) l();
}

/** 모달이 닫혔거나 로그인에 성공했을 때. 같은 이유가 다시 뜨지 않게 지운다 */
export function clearLoginPrompt(): void {
  if (reason === null) return;
  reason = null;
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 지금 요청된 로그인 이유. 없으면 null */
export function useLoginPrompt(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => reason,
    () => null,
  );
}
