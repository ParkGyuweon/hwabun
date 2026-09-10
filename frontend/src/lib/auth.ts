/**
 * 로그인 — shop_backend(`feat/shop-backend`, 머지 전) 의 `/api/auth` 계약에 맞춘다.
 *
 *   POST /api/auth/login    { email, password, role }        → 200 AccountResponse · 401
 *   POST /api/auth/members  { email, password, nickname }    → 201 AccountResponse · 409 (이미 가입)
 *   POST /api/auth/sellers  { email, password, name }        → 201 AccountResponse · 409
 *   AccountResponse = { id, email, name, role, status, token }
 *
 * 토큰은 JWT(HS256, 기본 15분). 보호된 API 는 `Authorization: Bearer <token>` 이 없으면
 * 401 `{"error":"unauthorized"}` 로 돌려준다. 백엔드 `SecurityConfig` 가 `/api/auth/**` 와
 * `GET /api/products/**` 만 열어 두고 나머지는 전부 인증을 요구한다.
 *
 * 역할마다 세션을 따로 둔다. 시연에서 같은 브라우저에 쇼핑몰(MEMBER)·대시보드(SELLER)·
 * 플랫폼(ADMIN) 탭을 나란히 여는데, 하나로 두면 서로 로그아웃시킨다.
 *
 * 서버가 없을 때(프록시 502·연결 실패)는 그 사실을 그대로 보여준다 — 로그인을 흉내 내지 않는다.
 */

export type AccountRole = 'MEMBER' | 'SELLER' | 'ADMIN';

export interface AccountSession {
  id: string;
  email: string;
  name: string;
  role: AccountRole;
  status: 'ACTIVE' | 'INACTIVE' | 'LOCKED' | string;
  token: string;
  /** JWT `exp` (epoch ms). 못 읽으면 null — 만료는 서버 401 로 안다 */
  expires_at: number | null;
}

export const ROLE_LABEL: Record<AccountRole, string> = {
  MEMBER: '고객',
  SELLER: '브랜드 담당자',
  ADMIN: '플랫폼 운영자',
};

const keyFor = (role: AccountRole) => `bloom.auth.${role.toLowerCase()}.v1`;

/** 화면에 보여줄 수 있는 실패 이유. 서버 응답 코드별로 나눈다 */
export type AuthErrorKind = 'credentials' | 'conflict' | 'validation' | 'forbidden' | 'unavailable' | 'unknown';

export class AuthError extends Error {
  readonly kind: AuthErrorKind;
  readonly status: number | null;

  constructor(message: string, kind: AuthErrorKind, status: number | null = null) {
    super(message);
    this.name = 'AuthError';
    this.kind = kind;
    this.status = status;
  }
}

// ---------------------------------------------------------------- 세션 저장소

const listeners = new Set<() => void>();
const cache = new Map<AccountRole, AccountSession | null>();

function decodeExp(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof json.exp === 'number' ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

function read(role: AccountRole): AccountSession | null {
  try {
    const raw = window.localStorage.getItem(keyFor(role));
    if (!raw) return null;
    const s = JSON.parse(raw) as AccountSession;
    if (!s || typeof s.token !== 'string' || s.role !== role) return null;
    if (s.expires_at !== null && s.expires_at <= Date.now()) {
      window.localStorage.removeItem(keyFor(role));
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

function write(role: AccountRole, session: AccountSession | null): void {
  try {
    if (session) window.localStorage.setItem(keyFor(role), JSON.stringify(session));
    else window.localStorage.removeItem(keyFor(role));
  } catch {
    /* 저장 불가(사파리 프라이빗 등) — 메모리 캐시로만 이번 탭에서 유지 */
  }
  cache.set(role, session);
  listeners.forEach((l) => l());
}

/** useSyncExternalStore 용. 같은 역할·같은 값이면 같은 객체를 돌려준다 */
export function sessionSnapshot(role: AccountRole): AccountSession | null {
  if (!cache.has(role)) cache.set(role, read(role));
  const s = cache.get(role) ?? null;
  if (s && s.expires_at !== null && s.expires_at <= Date.now()) {
    write(role, null);
    return null;
  }
  return s;
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key && e.key.startsWith('bloom.auth.')) {
      cache.clear();
      listener();
    }
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

export function loadSession(role: AccountRole): AccountSession | null {
  return sessionSnapshot(role);
}

export function logout(role: AccountRole): void {
  write(role, null);
}

// ---------------------------------------------------------------- API

interface AccountResponse {
  id: string;
  email: string;
  name: string;
  role: string;
  status: string;
  token: string;
}

async function post(path: string, body: unknown): Promise<Response> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError('서버에 연결할 수 없습니다. 백엔드(8090)가 떠 있는지 확인해 주세요.', 'unavailable');
  }
}

async function toSession(res: Response, role: AccountRole): Promise<AccountSession> {
  if (res.status === 401) throw new AuthError('이메일 또는 비밀번호가 맞지 않습니다.', 'credentials', 401);
  if (res.status === 403) throw new AuthError('이 계정으로는 들어갈 수 없습니다.', 'forbidden', 403);
  if (res.status === 409) throw new AuthError('이미 가입된 이메일입니다. 로그인해 주세요.', 'conflict', 409);
  if (res.status === 400) throw new AuthError('입력값을 확인해 주세요. 비밀번호는 8자 이상입니다.', 'validation', 400);
  if (res.status === 502 || res.status === 503 || res.status === 504)
    throw new AuthError('서버에 연결할 수 없습니다. 백엔드(8090)가 떠 있는지 확인해 주세요.', 'unavailable', res.status);
  if (!res.ok) throw new AuthError(`요청이 실패했습니다 (${res.status}).`, 'unknown', res.status);

  const a = (await res.json()) as AccountResponse;
  if (a.role !== role) throw new AuthError('역할이 다른 계정입니다.', 'forbidden', res.status);
  return {
    id: a.id,
    email: a.email,
    name: a.name,
    role,
    status: a.status,
    token: a.token,
    expires_at: decodeExp(a.token),
  };
}

export async function login(role: AccountRole, email: string, password: string): Promise<AccountSession> {
  const res = await post('/api/auth/login', { email: email.trim(), password, role });
  const session = await toSession(res, role);
  write(role, session);
  return session;
}

/** MEMBER 는 nickname, SELLER 는 name. ADMIN 은 가입 API 가 없다 (운영자가 직접 만든다) */
export async function register(
  role: Exclude<AccountRole, 'ADMIN'>,
  email: string,
  password: string,
  name: string,
): Promise<AccountSession> {
  const path = role === 'MEMBER' ? '/api/auth/members' : '/api/auth/sellers';
  const body =
    role === 'MEMBER'
      ? { email: email.trim(), password, nickname: name.trim() }
      : { email: email.trim(), password, name: name.trim() };
  const res = await post(path, body);
  const session = await toSession(res, role);
  write(role, session);
  return session;
}

/**
 * 보호된 API 호출. Bearer 를 붙이고, 401 이면 세션을 지운다 (만료·서버 재기동으로 키가 바뀐 경우).
 * 세션이 없으면 호출하지 않고 401 짜리 Response 를 흉내 내 돌려준다 — 호출부가 한 갈래로 처리한다.
 */
export async function authFetch(role: AccountRole, input: string, init: RequestInit = {}): Promise<Response> {
  const s = sessionSnapshot(role);
  if (!s) return new Response('{"error":"unauthorized"}', { status: 401, headers: { 'Content-Type': 'application/json' } });
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${s.token}`);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  const res = await fetch(input, { ...init, headers });
  /**
   * 401 이면 세션을 지운다. 단, **인증 확인용 호출(GET /api/brands)에서만.**
   * shop_backend 는 /error 가 permitAll 이 아니라서 어떤 4xx 도 401 {"error":"unauthorized"} 로
   * 바뀐다 (2026-09-10 실측). 상품 등록 400 한 번에 판매자가 로그아웃되는 걸 막기 위해, 다른
   * 경로의 401 은 세션을 건드리지 않고 호출부가 실패로 처리한다. 토큰이 정말 만료됐으면
   * 대시보드가 첫 화면에서 부르는 /api/brands 가 401 을 돌려 그때 지워진다.
   */
  const probe = input.startsWith('/api/brands') && (init.method ?? 'GET').toUpperCase() === 'GET';
  if (res.status === 401 && probe) write(role, null);
  return res;
}

/**
 * 개발용 모의 세션. 백엔드(feat/shop-backend)가 머지되기 전에 대시보드·플랫폼 화면을 보기 위한 것.
 * 토큰이 가짜라 보호된 API 는 401 이 나고, 그 순간 세션이 지워져 게이트로 돌아간다 — 흉내는 화면까지만.
 * 프로덕션 빌드에서는 호출하는 버튼 자체가 없다 (import.meta.env.DEV).
 */
export function devSession(role: AccountRole): void {
  const name = role === 'MEMBER' ? '개발용 고객' : role === 'SELLER' ? '개발용 담당자' : '개발용 운영자';
  write(role, {
    id: `dev-${role.toLowerCase()}`,
    email: `dev-${role.toLowerCase()}@local`,
    name,
    role,
    status: 'ACTIVE',
    token: 'dev.local.token',
    expires_at: null,
  });
}
