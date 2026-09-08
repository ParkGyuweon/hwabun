import { useCallback, useSyncExternalStore } from 'react';
import { sessionSnapshot, subscribeSession } from '../lib/auth';
import type { AccountRole, AccountSession } from '../lib/auth';

/** 역할별 로그인 세션. 다른 탭에서 로그인·로그아웃해도 따라온다 */
export function useAuth(role: AccountRole): AccountSession | null {
  const get = useCallback(() => sessionSnapshot(role), [role]);
  return useSyncExternalStore(subscribeSession, get, get);
}
