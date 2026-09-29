/**
 * 로그인 — shop_backend(`feat/shop-backend`, 머지 전) 의 `/api/auth` 계약에 맞춘다.
 *
 *   POST /api/auth/login    { email, password, role }        → 200 AccountResponse · 401
 *   POST /api/auth/members  { email, password, nickname, agreeTerms, agreePrivacy, agreeSkinInfo?, agreeBehaviorLink? }
 *                                                            → 201 AccountResponse · 409 (이미 가입) · 400 consent_required
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
  /**
   * 둘러본 기록을 이 계정과 이어도 되나 (서버 `behaviorLinked`). 가입 때 연결에 동의하지 않은 회원만 false.
   * 이 필드가 생기기 전에 저장된 세션은 값이 없고, 없으면 지금처럼 이어진 것으로 본다.
   */
  behavior_linked?: boolean;
}

/** 행동 로그를 이 회원 계정과 이을지. 값이 없는(예전) 세션은 이어진 것으로 본다 */
export function isBehaviorLinked(session: AccountSession | null): boolean {
  return session !== null && session.behavior_linked !== false;
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
  behaviorLinked?: boolean;
}

async function post(path: string, body: unknown): Promise<Response> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError('지금은 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.', 'unavailable');
  }
}

/** 429 {"error":"too_many_attempts","message":…}. 서버 문구가 한국어면 그대로, 아니면 같은 뜻의 기본 문장 */
async function tooManyMessage(res: Response): Promise<string> {
  const fallback = '로그인 시도가 너무 많아요. 잠시 후 다시 시도해 주세요.';
  try {
    const body = (await res.json()) as { message?: unknown } | null;
    const m = body?.message;
    return typeof m === 'string' && /[가-힣]/.test(m) ? m : fallback;
  } catch {
    return fallback;
  }
}

async function toSession(res: Response, role: AccountRole): Promise<AccountSession> {
  if (res.status === 401) throw new AuthError('이메일 또는 비밀번호가 맞지 않습니다.', 'credentials', 401);
  if (res.status === 403) throw new AuthError('이 계정으로는 들어갈 수 없습니다.', 'forbidden', 403);
  if (res.status === 409) throw new AuthError('이미 가입된 이메일입니다. 로그인해 주세요.', 'conflict', 409);
  if (res.status === 400) {
    // 필수 동의가 빠지면 서버가 { error: 'consent_required', message } 로 돌려준다. 그 문장을 그대로 보여 준다
    const body = (await res.json().catch(() => null)) as { error?: string; message?: string } | null;
    if (body?.error === 'consent_required' && body.message) throw new AuthError(body.message, 'validation', 400);
    throw new AuthError('입력값을 확인해 주세요. 비밀번호는 8자 이상입니다.', 'validation', 400);
  }
  if (res.status === 429) throw new AuthError(await tooManyMessage(res), 'unknown', 429);
  if (res.status === 502 || res.status === 503 || res.status === 504)
    throw new AuthError('지금은 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.', 'unavailable', res.status);
  if (!res.ok) throw new AuthError('요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.', 'unknown', res.status);

  const a = (await res.json()) as AccountResponse;
  if (a.role !== role) throw new AuthError('이 화면에서는 쓸 수 없는 계정입니다.', 'forbidden', res.status);
  return {
    id: a.id,
    email: a.email,
    name: a.name,
    role,
    status: a.status,
    token: a.token,
    expires_at: decodeExp(a.token),
    behavior_linked: a.behaviorLinked !== false,
  };
}

export async function login(role: AccountRole, email: string, password: string): Promise<AccountSession> {
  const res = await post('/api/auth/login', { email: email.trim(), password, role });
  const session = await toSession(res, role);
  write(role, session);
  return session;
}

/**
 * MEMBER 는 nickname, SELLER 는 name. ADMIN 은 가입 API 가 없다 (운영자가 직접 만든다).
 *
 * MEMBER 는 피부 프로필 4개(`skinTypeCode` …)를 같이 싣는다 (AI 요청 2026-09-10 §1). 백엔드 `RegisterMember` 가
 * 아직 이 필드를 안 받으면 무시될 뿐 가입은 된다. 프론트는 같은 값을 이 브라우저에도 남긴다 (lib/memberProfile).
 *
 * 동의 4개도 extra 로 싣는다: `agreeTerms`·`agreePrivacy`(필수, 없으면 400), `agreeSkinInfo`·`agreeBehaviorLink`(선택).
 * 서버는 `agreeSkinInfo` 가 true 가 아니면 피부 프로필 4개를 저장하지 않는다.
 */
export async function register(
  role: Exclude<AccountRole, 'ADMIN'>,
  email: string,
  password: string,
  name: string,
  extra: Record<string, string | boolean | null> = {},
): Promise<AccountSession> {
  const path = role === 'MEMBER' ? '/api/auth/members' : '/api/auth/sellers';
  const body =
    role === 'MEMBER'
      ? { email: email.trim(), password, nickname: name.trim(), ...extra }
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
  // 개발자 모드(모의 세션)는 백엔드를 아예 부르지 않는다. 503 을 돌려 호출부가 "서버 없음" 갈래(모의 데이터)로 가게 한다
  if (s.token === DEV_TOKEN) return new Response('{"error":"dev_mode"}', { status: 503, headers: { 'Content-Type': 'application/json' } });
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${s.token}`);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401 && (await isTokenRejected(res, input, init))) write(role, null);
  return res;
}

/**
 * 이 401 이 "토큰이 틀렸다" 는 뜻인가.
 *
 * shop_backend 의 인증 진입점(SecurityConfig authenticationEntryPoint)은 401 `{"error":"unauthorized"}` 를
 * 돌려준다. 이 본문이면 어느 경로든 토큰이 만료·무효라는 뜻이라 세션을 지운다.
 * 예전에는 /error 가 permitAll 이 아니라서 모든 4xx 가 이 본문의 401 로 바뀌었기 때문에 GET /api/brands 에서만
 * 지웠는데, 백엔드가 /error 를 permitAll 로 연 뒤로(SecurityConfig) 그 문제는 없다.
 * 본문이 다른 401 은 예전처럼 인증 확인용 호출(GET /api/brands)에서만 세션을 지우고, 그 밖은 호출부가 실패로 처리한다.
 */
async function isTokenRejected(res: Response, input: string, init: RequestInit): Promise<boolean> {
  const probe = input.startsWith('/api/brands') && (init.method ?? 'GET').toUpperCase() === 'GET';
  if (probe) return true;
  try {
    const body = (await res.clone().json()) as { error?: unknown } | null;
    return body !== null && typeof body === 'object' && body.error === 'unauthorized';
  } catch {
    return false;
  }
}

/** 개발자 모드 세션의 토큰. 이 값이면 `authFetch` 가 백엔드를 부르지 않는다 */
export const DEV_TOKEN = 'dev.local.token';

/** 지금 이 역할이 개발자 모드(모의 세션)로 들어와 있나 */
export function isDevSession(session: AccountSession | null): boolean {
  return session !== null && session.token === DEV_TOKEN;
}

/**
 * 개발자 모드 · 모의 세션. 백엔드 없이 대시보드·플랫폼 화면을 전부 보기 위한 것.
 *
 * 버튼은 로컬 개발이거나 주소에 ?dev=1 이 있을 때만 보인다 (AuthGate, 2026-09-29). 배포 화면에서 누구나 누르면
 * 모의 화면을 실제 화면으로 오해할 수 있어서다. 이 세션이면 `authFetch` 가 서버를 부르지 않고 503 을 돌려주므로
 * 화면은 전부 모의 데이터(배지 "모의")로 그려지고, 401 로 튕기지도 않는다. 실제 계정으로 로그인하면 덮어써진다.
 */
export function devSession(role: AccountRole): void {
  const name = role === 'MEMBER' ? '개발용 고객' : role === 'SELLER' ? '개발용 담당자' : '개발용 운영자';
  write(role, {
    id: `dev-${role.toLowerCase()}`,
    email: `dev-${role.toLowerCase()}@local`,
    name,
    role,
    status: 'ACTIVE',
    token: DEV_TOKEN,
    expires_at: null,
  });
}
