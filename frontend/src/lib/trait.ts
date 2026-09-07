/**
 * 세션 성향 — "무엇을 좋아하나" 가 아니라 "어떻게 고르나".
 *
 * 추천 API 의 사용자 벡터는 상품 벡터의 가중 평균이라 취향은 알지만
 * **결정할 때 무엇을 보는지**는 담지 않는다. 가격 필터를 켜는 사람과 전성분을 펼치는
 * 사람은 같은 세럼을 다른 이유로 산다. 그 차이를 이 세션 안에서 잡아
 * 추천 배너의 **축**(어떤 문구로 말할지)을 고르는 데 쓴다.
 *
 * AI 파트가 "무엇을 샀나"(시드)에서 축 선호를 읽으려다 기각한 것(시드 일관성
 * concern 0.336 · ingredient 0.155)과는 다른 신호다. 여기는 행동이다. 다만 이것도
 * 정확도가 아니라 **축별 배너 클릭률 차이**로만 검증한다 — 차이가 없으면 접는다.
 * 설계는 docs/dashboard/personalized-banner-plan.md §2·§10-4.
 *
 * ## 왜 프론트에서 계산하나
 *
 * Spark 마트는 세션 안에 돌아오지 않는다. 이벤트를 발행하는 바로 그 자리
 * (`logger.track`)에서 같이 누적하면 지연이 0 이다. 장기 성향(마트)은 나중에
 * `setTraitProfile` 로 덧입힌다.
 *
 * ## 새 이벤트는 없다
 *
 * 이미 나가는 이벤트 34종 중 "고르는 방식" 을 드러내는 것만 골라 가중한다.
 * 노출(`*_impression`)은 여기서도 신호가 아니다.
 */

import type { BannerType, EventName, TraitSource } from '../types/log';

export type TraitKind = 'price' | 'ingredient' | 'review' | 'concern' | 'participate';

export const TRAIT_KINDS: readonly TraitKind[] = [
  'price',
  'ingredient',
  'review',
  'concern',
  'participate',
];

export type TraitScores = Record<TraitKind, number>;

/**
 * 이 값 미만이면 "성향 없음" 으로 본다. AI 기본축(concern·segment)으로 간다.
 * 필터 한 번(1.0)으로는 못 넘고, 필터 + 문구 선택이나 체류 몇 초가 쌓여야 넘는다.
 * 측정 전 초기값이다 — `trait_snapshot` 이 쌓이면 재조정한다.
 */
export const TRAIT_THRESHOLD = 2.0;

/**
 * 성향을 알아도 이 비율은 다른 축을 준다 (`trait_source: 'explore'`).
 * 이게 없으면 "성향 추정이 맞았는지" 를 영영 못 가린다. AI 파트도 20% 면 충분하다고 했다.
 * 세션당 한 번 정해 고정한다 — 새로고침마다 바뀌면 같은 사람의 배너가 흔들린다.
 */
export const EXPLORE_RATIO = 0.2;

/** 최근 5분은 그대로, 30분이면 0.3. 세션 초반에 본 것보다 방금 한 행동이 더 말해 준다 */
const DECAY_FULL_MS = 5 * 60_000;
const DECAY_HALF_LIFE_MS = 30 * 60_000;
const DECAY_FLOOR_AT_HALF = 0.3;

/** 체류 가중은 초당이라 오래 열어 두면 폭주한다. 한 건당 상한 */
const DWELL_CAP_SECONDS = 60;

/** 성향 → 배너 축. 성향이 고르는 것은 "어느 축을 먼저 올리나" 지 상품이 아니다 */
const TRAIT_AXES: Record<TraitKind, BannerType[]> = {
  price: ['price_bin'],
  ingredient: ['ingredient', 'clean'],
  review: ['segment'],
  concern: ['concern'],
  // 참여형은 축이 아니라 신규 브랜드 전용 칸을 앞으로 당긴다. 축은 기본값
  participate: [],
};

/** 성향이 없거나 남는 칸을 채우는 순서. AI 권고(concern·segment 먼저) */
const DEFAULT_AXES: BannerType[] = ['concern', 'segment', 'price_bin', 'ingredient'];

const STORAGE_KEY = 'hwabun.trait.v1';
const MAX_ENTRIES = 400;

interface Entry {
  k: TraitKind;
  w: number;
  /** epoch ms */
  t: number;
}

interface Stored {
  entries: Entry[];
  /** 세션당 한 번 정한 탐색 여부 */
  explore: boolean;
}

export interface TraitProfile {
  /** 페르소나·가입 정보에 피부 타입이 있으면 concern 에 고정 가점 */
  hasSkinProfile: boolean;
  /** 장기 성향(마트). 아직 없으면 null */
  longTerm: Partial<TraitScores> | null;
}

export interface TraitDecision {
  trait: TraitKind | null;
  /** 추천 API `axes` 파라미터. 4칸 */
  axes: BannerType[];
  trait_source: TraitSource;
  /** 소수 둘째 자리. 로그 property `trait_snapshot` */
  snapshot: TraitScores;
  /** participate 성향이면 전용 칸을 앞 slot 으로 */
  reservedFirst: boolean;
}

/* ───────────────────────── 이벤트 → 성향 가중 ───────────────────────── */

type Props = Record<string, unknown>;

const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

/** 체류는 초당 가중. 짧은 스침(2초 미만)은 세지 않는다 */
function dwell(props: Props, perSecond: number): number {
  const seconds = Math.min(DWELL_CAP_SECONDS, num(props.dwell_ms) / 1000);
  return seconds < 2 ? 0 : seconds * perSecond;
}

/**
 * 이벤트 하나가 어느 성향에 얼마를 보태나. 표는 personalized-banner-plan.md §2.
 *
 * 값은 `SECTION_DWELL_WEIGHT` 와 방향을 맞췄다 (ingredients·reviews 가 가장 높다).
 * 한 이벤트가 두 성향에 걸칠 수 있다 — 리뷰에서 성분 얘기를 긁어 가는 사람처럼.
 */
export function traitContribution(eventName: EventName, props: Props): Array<[TraitKind, number]> {
  const section = str(props.section_id);
  const content = str(props.content_kind);
  const out: Array<[TraitKind, number]> = [];

  switch (eventName) {
    case 'filter_change': {
      const kind = str(props.filter_kind);
      if (kind === 'price') out.push(['price', 1.0]);
      if (kind === 'concern') out.push(['concern', 1.5]);
      break;
    }
    case 'sort_change': {
      const key = str(props.sort_key) ?? '';
      if (key.startsWith('price')) out.push(['price', 1.0]);
      if (key === 'rating' || key === 'reviews') out.push(['review', 0.5]);
      break;
    }
    case 'variant_select':
      if (str(props.variant_kind) === 'size') out.push(['price', 0.5]);
      break;

    case 'ingredient_view_mode_change':
      out.push(['ingredient', 1.5]);
      break;
    case 'accordion_toggle':
      if (section === 'ingredients' && str(props.action) !== 'collapse') out.push(['ingredient', 1.0]);
      break;
    case 'text_selection':
    case 'text_copy': {
      const base = eventName === 'text_copy' ? 2.0 : 1.5;
      const kind = str(props.selection_kind);
      // selection_kind 가 아직 안 실리는 화면에서는 성분 매칭 수로 대신 본다
      const isIngredient = kind === 'ingredient' || (kind === null && num(props.matched_count) > 0);
      if (isIngredient) out.push(['ingredient', base]);
      if (kind === 'price' || (kind === null && content === 'price')) out.push(['price', base]);
      if (kind === 'claim' || (kind === null && content === 'clinical_claim')) out.push(['concern', 1.0]);
      break;
    }

    case 'review_expand': {
      const target = str(props.target);
      // ingredients 로 점프한 것은 리뷰 행동이 아니다 (계약 §3.9)
      if (target === 'ingredients') out.push(['ingredient', 0.5]);
      else out.push(['review', 1.0]);
      break;
    }
    case 'review_filter_apply':
      out.push(['review', 1.5]);
      break;

    case 'section_dwell': {
      if (section === 'ingredients') out.push(['ingredient', dwell(props, 1.0)]);
      if (section === 'reviews') out.push(['review', dwell(props, 1.0)]);
      if (content === 'review_stats') out.push(['review', dwell(props, 0.5)]);
      if (content === 'price') out.push(['price', dwell(props, 0.5)]);
      if (content === 'highlight_badge' || content === 'clinical_claim') {
        out.push(['concern', dwell(props, 0.5)]);
      }
      if (content === 'brand_story') out.push(['participate', dwell(props, 1.0)]);
      break;
    }

    case 'purchase_reason_select': {
      const reasons = Array.isArray(props.reasons) ? (props.reasons as unknown[]) : [];
      // 이유 선언은 상품 선호(EVENT_WEIGHT 0)는 아니지만 "어떻게 고르나" 로는 가장 직접적이다
      if (reasons.includes('price')) out.push(['price', 2.0]);
      if (reasons.includes('ingredient') || reasons.includes('clean_claim')) out.push(['ingredient', 2.0]);
      if (reasons.includes('reviews') || reasons.includes('review_same_skin')) out.push(['review', 2.0]);
      if (reasons.includes('skin_fit')) out.push(['concern', 2.0]);
      if (reasons.includes('brand_trust')) out.push(['participate', 2.0]);
      break;
    }
    default:
      break;
  }

  return out.filter(([, w]) => w > 0);
}

/* ───────────────────────── 저장·감쇠 ───────────────────────── */

function readStore(): Stored | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Stored>;
    if (!Array.isArray(parsed.entries) || typeof parsed.explore !== 'boolean') return null;
    return { entries: parsed.entries, explore: parsed.explore };
  } catch {
    return null;
  }
}

function writeStore(s: Stored): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // 저장이 막힌 환경(프라이빗 창 등)이면 메모리로만 산다
  }
}

let store: Stored = readStore() ?? { entries: [], explore: Math.random() < EXPLORE_RATIO };
let profile: TraitProfile = { hasSkinProfile: false, longTerm: null };

const listeners = new Set<() => void>();
let version = 0;
function notify(): void {
  version += 1;
  for (const l of listeners) l();
}

function decay(ageMs: number): number {
  if (ageMs <= DECAY_FULL_MS) return 1;
  const k = Math.log(DECAY_FLOOR_AT_HALF) / (DECAY_HALF_LIFE_MS - DECAY_FULL_MS);
  return Math.exp(k * (ageMs - DECAY_FULL_MS));
}

function zero(): TraitScores {
  return { price: 0, ingredient: 0, review: 0, concern: 0, participate: 0 };
}

/* ───────────────────────── 공개 API ───────────────────────── */

/** `logger.track` 이 봉투를 만든 뒤 한 번 부른다. 여기 말고 다른 데서 부르지 않는다 */
export function ingestForTrait(eventName: EventName, props: Props, now = Date.now()): void {
  const contributions = traitContribution(eventName, props);
  if (contributions.length === 0) return;

  for (const [k, w] of contributions) store.entries.push({ k, w, t: now });
  if (store.entries.length > MAX_ENTRIES) store.entries = store.entries.slice(-MAX_ENTRIES);
  writeStore(store);
  notify();
}

export function setTraitProfile(patch: Partial<TraitProfile>): void {
  profile = { ...profile, ...patch };
  notify();
}

/** 감쇠 적용 후 점수. 장기 성향은 세션 신호의 절반 무게로 더한다 */
export function traitScores(now = Date.now()): TraitScores {
  const s = zero();
  for (const e of store.entries) s[e.k] += e.w * decay(now - e.t);
  if (profile.hasSkinProfile) s.concern += 1.0;
  if (profile.longTerm) {
    for (const k of TRAIT_KINDS) s[k] += (profile.longTerm[k] ?? 0) * 0.5;
  }
  return s;
}

function round2(s: TraitScores): TraitScores {
  const r = zero();
  for (const k of TRAIT_KINDS) r[k] = Math.round(s[k] * 100) / 100;
  return r;
}

function fillAxes(first: BannerType[]): BannerType[] {
  const out: BannerType[] = [];
  for (const a of [...first, ...DEFAULT_AXES]) {
    if (!out.includes(a)) out.push(a);
    if (out.length === 4) break;
  }
  return out;
}

/**
 * 지금 이 사람에게 배너 축을 어떤 순서로 올릴지.
 *
 * - 세션 점수가 임계를 넘으면 그 성향의 축 → `session`
 * - 세션은 약한데 장기 성향이 있으면 그것 → `profile`
 * - 둘 다 없으면 AI 기본값 → `coldstart`
 * - 성향이 있어도 탐색 세션이면 그 성향의 축을 **뒤로** 보낸다 → `explore`
 */
export function decideTrait(now = Date.now()): TraitDecision {
  const scores = traitScores(now);
  const snapshot = round2(scores);

  let best: TraitKind | null = null;
  let bestScore = 0;
  for (const k of TRAIT_KINDS) {
    if (scores[k] > bestScore) {
      best = k;
      bestScore = scores[k];
    }
  }

  const sessionOnly = (() => {
    const s = zero();
    for (const e of store.entries) s[e.k] += e.w * decay(now - e.t);
    return s;
  })();
  const sessionStrong = best !== null && sessionOnly[best] >= TRAIT_THRESHOLD;
  const profileStrong = best !== null && !sessionStrong && bestScore >= TRAIT_THRESHOLD;

  if (best === null || (!sessionStrong && !profileStrong)) {
    return { trait: null, axes: fillAxes([]), trait_source: 'coldstart', snapshot, reservedFirst: false };
  }

  const preferred = TRAIT_AXES[best];
  if (store.explore) {
    // 성향의 축을 빼고 채운 뒤 맨 뒤에 붙인다. 성향이 맞았다면 뒤쪽 배너가 더 눌릴 것이다
    const others = DEFAULT_AXES.filter((a) => !preferred.includes(a));
    return {
      trait: best,
      axes: fillAxes([...others, ...preferred]),
      trait_source: 'explore',
      snapshot,
      reservedFirst: false,
    };
  }

  return {
    trait: best,
    axes: fillAxes(preferred),
    trait_source: sessionStrong ? 'session' : 'profile',
    snapshot,
    reservedFirst: best === 'participate',
  };
}

/** React `useSyncExternalStore` 용 */
export function subscribeTrait(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function traitVersion(): number {
  return version;
}

/**
 * 버전이 같으면 같은 객체를 돌려준다. `useSyncExternalStore` 는 스냅샷 동일성으로
 * 재렌더를 정하므로 매번 새 객체를 만들면 무한 렌더가 된다.
 */
let cachedVersion = -1;
let cachedDecision: TraitDecision | null = null;
export function traitDecisionSnapshot(): TraitDecision {
  if (cachedDecision === null || cachedVersion !== version) {
    cachedDecision = decideTrait();
    cachedVersion = version;
  }
  return cachedDecision;
}

/** 새 세션·테스트용. 탐색 여부도 다시 뽑는다 */
export function resetTrait(): void {
  store = { entries: [], explore: Math.random() < EXPLORE_RATIO };
  writeStore(store);
  notify();
}
