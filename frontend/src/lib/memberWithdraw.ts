/**
 * 회원 탈퇴 — shop_backend `DELETE /api/members/me` 계약 (2026-09-29).
 *
 *   DELETE /api/members/me   { password }   (MEMBER JWT)
 *     204  탈퇴 완료
 *     400  비밀번호 없음
 *     401 · 403  비밀번호가 틀림 (서버 문구 "비밀번호가 맞지 않아요.")
 *     409  진행 중인 주문이 있어 막힘 (서버 문구가 한국어로 온다)
 *
 * 실패 본문은 shop_backend 의 두 모양 중 하나다.
 *   · 핸들러가 직접 만든 것 (`ApiExceptionHandler`) — `{ "error": "conflict", "message": "..." }`
 *   · `ResponseStatusException` 이 `/error` 로 간 것 — `{ timestamp, status, error: "Bad Request", message, path }`
 *     (`server.error.include-message` 를 켜지 않으면 message 가 비어 온다)
 *   · 토큰이 없거나 틀리면 보안 필터가 `{ "error": "unauthorized" }` 만 쓴다 — 비밀번호가 아니라 로그인 문제다.
 * 그래서 `message` → `error` 순으로 **한글이 든 문장만** 골라 그대로 보여 주고, 없으면 응답 코드별 문구로 대신한다.
 * 영어 원문이나 응답 코드는 화면에 내보내지 않는다.
 */
import { authFetch, logout, sessionSnapshot } from './auth';
import { clearMemberProfile } from './memberProfile';
import { clearPendingPayment } from './payment';
import { clearWishlist } from './wishlist';

export type WithdrawResult =
  | { ok: true }
  | {
      ok: false;
      /** 화면에 그대로 보여 줄 문장 */
      reason: string;
      /** password 면 입력칸을 비우고 다시 포커스한다. login 이면 다시 로그인해야 한다 */
      kind: 'password' | 'blocked' | 'login' | 'other';
    };

const MESSAGE = {
  missing: '비밀번호를 입력해 주세요.',
  password: '비밀번호가 맞지 않아요.',
  blocked: '아직 끝나지 않은 주문이 있어 지금은 탈퇴할 수 없어요. 주문이 마무리된 뒤 다시 해 주세요.',
  login: '로그인이 끝났어요. 다시 로그인한 뒤 탈퇴해 주세요.',
  offline: '연결이 잠시 끊겼어요. 잠시 뒤 다시 해 주세요.',
  other: '탈퇴를 마치지 못했어요. 잠시 뒤 다시 해 주세요.',
};

const HANGUL = /[가-힣]/;

/** 본문에서 사람에게 보여 줄 한국어 문장을 꺼낸다. 없으면 null */
function koreanMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const b = body as Record<string, unknown>;
  for (const key of ['message', 'error', 'detail']) {
    const v = b[key];
    if (typeof v === 'string' && HANGUL.test(v)) return v.trim();
  }
  return null;
}

export async function withdrawMember(password: string): Promise<WithdrawResult> {
  if (!password) return { ok: false, reason: MESSAGE.missing, kind: 'password' };
  // 토큰이 이미 만료됐으면 authFetch 가 부르지도 않고 401 을 흉내 낸다 — 비밀번호 탓으로 읽히면 안 된다
  if (!sessionSnapshot('MEMBER')) return { ok: false, reason: MESSAGE.login, kind: 'login' };

  let res: Response;
  try {
    res = await authFetch('MEMBER', '/api/members/me', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
  } catch {
    return { ok: false, reason: MESSAGE.offline, kind: 'other' };
  }
  if (res.ok) return { ok: true };

  let body: unknown = null;
  try {
    const text = await res.text();
    body = text ? JSON.parse(text) : null;
  } catch {
    /* JSON 이 아니면 코드별 문구로 */
  }
  const said = koreanMessage(body);
  // 보안 필터의 401 (`{"error":"unauthorized"}`) — 비밀번호 검사까지 가지도 못했다
  const tokenRejected =
    res.status === 401 && !said && (body as { error?: unknown } | null)?.error === 'unauthorized';

  if (tokenRejected) return { ok: false, reason: MESSAGE.login, kind: 'login' };
  if (res.status === 400) return { ok: false, reason: said ?? MESSAGE.missing, kind: 'password' };
  if (res.status === 401 || res.status === 403) return { ok: false, reason: said ?? MESSAGE.password, kind: 'password' };
  if (res.status === 409) return { ok: false, reason: said ?? MESSAGE.blocked, kind: 'blocked' };
  if (res.status === 502 || res.status === 503 || res.status === 504) return { ok: false, reason: MESSAGE.offline, kind: 'other' };
  return { ok: false, reason: said ?? MESSAGE.other, kind: 'other' };
}

/** 탈퇴가 끝난 뒤 App 이 장바구니 같은 화면 상태를 비우도록 알리는 이벤트 */
export const MEMBER_WITHDRAWN_EVENT = 'bloom:member-withdrawn';

/**
 * 탈퇴 뒤 이 브라우저에 남은 회원 흔적을 지우고 로그아웃한다.
 * 피부 정보 사본(`bloom.profile.v1.<id>`) · 찜(`bloom.wishlist.v1`) · 결제 대기(`bloom.payment.pending.v1`).
 * 로그인 세션을 지우면 `storage` 이벤트로 같은 브라우저의 다른 탭도 함께 로그아웃된다 (lib/auth subscribeSession).
 */
export function finishWithdrawal(accountId: string): void {
  clearMemberProfile(accountId);
  clearWishlist();
  clearPendingPayment();
  logout('MEMBER');
  try {
    window.dispatchEvent(new CustomEvent(MEMBER_WITHDRAWN_EVENT));
  } catch {
    /* 이벤트를 못 쓰는 환경이면 장바구니만 남는다 */
  }
}
