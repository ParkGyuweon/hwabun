/**
 * 추천 서버 클라이언트 · `GET /api/recommend` (batch/serving/recommend_server.py, 8300 · Vite 프록시 `/api/recommend`).
 *
 * 계약: contracts/recommendation-io-spec.md §5 · §5-1. 서버 응답을 화면이 이미 쓰는 모양(`RecommendResponse`)으로 바꾼다.
 * 목(`recommendMock.buildRecommendation`)과 같은 모양이라 화면 코드는 어느 쪽이 왔는지 몰라도 된다.
 *
 * 규칙
 *   - **식별자가 없으면 부르지 않는다** (계약 §5 운영 합의 09-10: 추천은 로그인 회원에게만). 호출부(useRecommendation)가 지킨다.
 *     식별자 = 회원 accountId 또는 시뮬레이션 페르소나 id. 서버는 페르소나 표에 없는 값도 받고 404 를 내지 않는다 (Jira 214).
 *   - `recommendation_id`·`algorithm` 은 **응답 값을 그대로** 로그에 싣는다. 화면이 지어내지 않는다.
 *   - `axes` 는 서버가 받는 여섯 축만 보낸다. `new_brand` 는 축이 아니라 자리라 빼야 한다 (422 INVALID_AXES).
 *   - 실패(네트워크·4xx·5xx·타임아웃)는 null. 호출부가 목으로 물러난다.
 */
import type { BannerType } from '../types/log';
import { authFetch } from './auth';
import type { MemberProfile } from './memberProfile';
import type { HeroPolicy, LongTermTrait, RecommendBanner, RecommendHero, RecommendItem, RecommendResponse } from '../types/recommendation';

/** 서버가 받는 축. 계약 §5 `axes` */
const SERVER_AXES: ReadonlySet<string> = new Set(['concern', 'ingredient', 'clean', 'price_bin', 'category', 'segment']);

const TIMEOUT_MS = 4000;

export interface RecommendQuery {
  /** 회원 accountId 또는 페르소나 id. 서버 `persona_id` */
  personaId: string;
  size: number;
  bannerSlots: number;
  reserved: number;
  axes: BannerType[];
  hero: HeroPolicy;
  /**
   * 실회원 피부 프로필 (AI 회신 2026-09-11). `skin_type` · `skin_tone` · `hair_color` · `eye_color` 를 계약 enum 값 그대로 쿼리에 싣는다.
   * "선택 안 함" 은 **키를 생략**한다 (빈 문자열·null 문자 금지). 서버는 있는 속성만으로 가중치를 다시 나눈다.
   * `persona_id` 가 페르소나 표에 있으면 서버가 표를 우선하고 쿼리는 무시한다 — 그래서 실회원일 때만 넣는다.
   */
  profile?: MemberProfile | null;
}

/* ---------- 서버 응답 (계약 §5 응답 예시 그대로) ---------- */

interface ServerItem {
  product_id: string;
  score?: number;
  position?: number;
  reserved?: boolean;
  product_source?: string;
  product_name?: string;
  brand_name?: string;
}

interface ServerHero {
  product_id: string;
  banner_type: string;
  banner_value?: string | null;
  trait_source?: string;
  hero_policy?: string;
  /** 히어로 축 선택 규칙의 판 (Jira 307). 현재 `hero-2026-09-15` */
  hero_policy_version?: string;
  reserved?: boolean;
  product_name?: string;
  brand_name?: string;
  score?: number;
  reason?: Record<string, string>;
  product_source?: string;
}

interface ServerBanner {
  banner_slot: number;
  banner_type: string;
  banner_value?: string | null;
  product_id: string;
  score?: number;
  reserved?: boolean;
}

export interface ServerRecommendResponse {
  persona_id: string | null;
  persona_known?: boolean;
  recommendation_id: string;
  list_id?: string;
  algorithm?: string;
  state_source?: string;
  items: ServerItem[];
  banner_slots?: number;
  banner_list_id?: string;
  hero_policy?: string;
  hero?: ServerHero | null;
  banners?: ServerBanner[] | null;
  /** 마트 행이 없으면 null. `useRecommendation` 이 `setTraitProfile({ longTerm })` 로 세션 점수에 섞는다 */
  long_term_trait?: LongTermTrait | null;
}

/** 서버 → 화면 모양. 필드 이름만 바뀐다 (position→rank · algorithm→model_version · banner_slot→slot) */
export function fromServer(body: ServerRecommendResponse, personaId: string): RecommendResponse {
  const items: RecommendItem[] = (body.items ?? []).map((it, i) => ({
    product_id: it.product_id,
    score: it.score ?? 0,
    rank: it.position ?? i + 1,
    ...(it.reserved !== undefined ? { reserved: it.reserved } : {}),
  }));

  const hero: RecommendHero | null = body.hero
    ? {
        product_id: body.hero.product_id,
        banner_type: body.hero.banner_type as BannerType,
        banner_value: body.hero.banner_type === 'new_brand' ? null : (body.hero.banner_value ?? null),
        ...(body.hero.product_name ? { product_name: body.hero.product_name } : {}),
        ...(body.hero.brand_name ? { brand_name: body.hero.brand_name } : {}),
        ...(body.hero.score !== undefined ? { score: body.hero.score } : {}),
        ...(body.hero.reason ? { reason: Object.values(body.hero.reason).join(' · ') } : {}),
        ...(body.hero.product_source ? { product_source: body.hero.product_source } : {}),
        ...(body.hero.reserved !== undefined ? { reserved: body.hero.reserved } : {}),
        ...(body.hero.hero_policy_version ? { hero_policy_version: body.hero.hero_policy_version } : {}),
      }
    : null;

  const banners: RecommendBanner[] = (body.banners ?? []).map((b) => ({
    slot: b.banner_slot,
    banner_type: b.banner_type as BannerType,
    banner_value: b.banner_type === 'new_brand' ? null : (b.banner_value ?? null),
    product_id: b.product_id,
    score: b.score ?? 0,
    ...(b.reserved !== undefined ? { reserved: b.reserved } : {}),
  }));

  const heroPolicy = body.hero_policy === 'new_brand' || body.hero_policy === 'top' ? body.hero_policy : undefined;

  return {
    user_id: body.persona_id ?? personaId,
    generated_at: new Date().toISOString(),
    model_version: body.algorithm ?? 'server',
    recommendation_id: body.recommendation_id,
    list_id: body.list_id ?? 'main',
    banner_list_id: body.banner_list_id ?? 'banner_row',
    items,
    hero,
    banners,
    ...(heroPolicy ? { hero_policy: heroPolicy } : {}),
    // 이름·모양이 계약과 같아 그대로 통과시킨다. 쓰는 곳은 useRecommendation 하나다
    ...(body.long_term_trait !== undefined ? { long_term_trait: body.long_term_trait } : {}),
  };
}

export function buildRecommendUrl(q: RecommendQuery): string {
  const axes = q.axes.filter((a) => SERVER_AXES.has(a));
  const params = new URLSearchParams({
    persona_id: q.personaId,
    size: String(q.size),
    banner_slots: String(q.bannerSlots),
    reserved: String(q.reserved),
    hero: q.hero,
  });
  if (axes.length > 0) params.set('axes', axes.join(','));
  if (q.profile) {
    for (const field of ['skin_type', 'skin_tone', 'hair_color', 'eye_color'] as const) {
      const v = q.profile[field];
      if (v) params.set(field, v);
    }
  }
  return `/api/recommend?${params.toString()}`;
}

/** 실패는 null. 호출부가 목으로 물러난다 */
export async function fetchRecommendation(q: RecommendQuery, signal?: AbortSignal): Promise<RecommendResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const onOuterAbort = () => controller.abort();
  signal?.addEventListener('abort', onOuterAbort);
  try {
    const res = await authFetch('MEMBER', buildRecommendUrl(q), { signal: controller.signal });
    if (!res.ok) {
      if (import.meta.env.DEV) console.info(`[recommend] ${res.status} · 목으로 물러남`);
      return null;
    }
    const body = (await res.json()) as ServerRecommendResponse;
    if (!body || !Array.isArray(body.items) || typeof body.recommendation_id !== 'string') return null;
    return fromServer(body, q.personaId);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onOuterAbort);
  }
}
