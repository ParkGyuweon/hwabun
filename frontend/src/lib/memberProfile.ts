/**
 * 회원 피부 프로필 · 가입할 때 받는 속성 4개 (AI 파트 요청 2026-09-10 §1).
 *
 * 추천 서버는 `persona_id` 로 페르소나 표를 찾아 속성을 읽는데, 실회원 `accountId` 는 표에 없어
 * 속성 친화도(LTR 피처 #1)가 통째로 빠진다. 그래서 가입에서 페르소나와 **같은 값 체계**로 받는다.
 * 페르소나 100명을 회원으로 일괄 가입시킬 때도 이 네 값이 그대로 들어간다 (scripts/register-personas.ts).
 *
 * 값(`value`)은 계약 enum 문자열 그대로 보내고 화면은 `ko` 만 보인다. 한 글자도 바꾸지 않는다.
 * 어휘는 `contracts/product-form-labels-ko.json` 의 `segment` 와 같고, 모발색 `gray` 만 그 파일에 빠져 있어
 * 여기서 보충한다 (`persona-schema.md` §3.1 은 6종).
 *
 * "선택 안 함" 은 null. 서버는 NULL 속성의 가중치를 0 으로 두고 나머지를 합 1.0 으로 다시 나눈다
 * (`persona-schema.md` §8.2). 억지로 채우게 하지 않는다.
 *
 * 저장: 백엔드 프로필 API 가 아직 없어(요청 문서 §3) 이 브라우저에 계정별로 둔다. 가입 요청에는
 * 함께 실어 보내므로 백엔드가 컬럼을 받기 시작하면 서버에도 남는다 (`member.skin_type_code` 등 컬럼은 이미 있다).
 */
import labels from '../../../contracts/product-form-labels-ko.json';
import type { PersonaProfile } from '../types/persona';
import type { SkinType } from '../types/product';

export type ProfileField = 'skin_type' | 'skin_tone' | 'hair_color' | 'eye_color';

export interface MemberProfile {
  skin_type: SkinType | null;
  skin_tone: string | null;
  hair_color: string | null;
  eye_color: string | null;
}

export const EMPTY_PROFILE: MemberProfile = { skin_type: null, skin_tone: null, hair_color: null, eye_color: null };

export interface ProfileOption {
  value: string;
  ko: string;
}

interface SegmentLabel {
  value: string;
  ko: string;
  field: string;
}

const SEGMENT = (labels as unknown as { segment: SegmentLabel[] }).segment;

function optionsOf(field: ProfileField): ProfileOption[] {
  const out = SEGMENT.filter((s) => s.field === field).map(({ value, ko }) => ({ value, ko }));
  // 어휘 파일에 빠진 값 보충 (persona-schema.md §3.1)
  if (field === 'hair_color' && !out.some((o) => o.value === 'gray')) out.push({ value: 'gray', ko: '회색 모발' });
  return out;
}

/** 필드별 선택지. 순서는 어휘 파일 순서 */
export const PROFILE_OPTIONS: Record<ProfileField, ProfileOption[]> = {
  skin_type: optionsOf('skin_type'),
  skin_tone: optionsOf('skin_tone'),
  hair_color: optionsOf('hair_color'),
  eye_color: optionsOf('eye_color'),
};

export const PROFILE_FIELD_KO: Record<ProfileField, string> = {
  skin_type: '피부 타입',
  skin_tone: '피부 톤',
  hair_color: '모발색',
  eye_color: '눈동자색',
};

/** 필수 권장 둘. 나머지는 선택 (AI 요청 §1.2) */
export const PROFILE_RECOMMENDED: ProfileField[] = ['skin_type', 'skin_tone'];
export const PROFILE_FIELDS: ProfileField[] = ['skin_type', 'skin_tone', 'hair_color', 'eye_color'];

export function profileLabel(field: ProfileField, value: string | null): string {
  if (!value) return '선택 안 함';
  return PROFILE_OPTIONS[field].find((o) => o.value === value)?.ko ?? value;
}

/** 어휘에 있는 값만 남긴다. 페르소나 파일·URL 등 밖에서 온 값을 그대로 믿지 않는다 */
export function sanitizeProfile(raw: Partial<Record<ProfileField, unknown>> | null | undefined): MemberProfile {
  const pick = (field: ProfileField): string | null => {
    const v = raw?.[field];
    if (typeof v !== 'string') return null;
    return PROFILE_OPTIONS[field].some((o) => o.value === v) ? v : null;
  };
  return {
    skin_type: pick('skin_type') as SkinType | null,
    skin_tone: pick('skin_tone'),
    hair_color: pick('hair_color'),
    eye_color: pick('eye_color'),
  };
}

export function isEmptyProfile(p: MemberProfile): boolean {
  return PROFILE_FIELDS.every((f) => p[f] === null);
}

/**
 * 가입·프로필 API 본문 필드. shop_backend `member` 테이블 컬럼(`skin_type_code` …)을 camelCase 로.
 * 백엔드 `RegisterMember` 가 아직 이 필드를 안 받아도 무시될 뿐 실패하지 않는다 (요청 문서 §3).
 */
export function profileToApi(p: MemberProfile): Record<string, string | null> {
  return {
    skinTypeCode: p.skin_type,
    skinToneCode: p.skin_tone,
    hairColorCode: p.hair_color,
    eyeColorCode: p.eye_color,
  };
}

/**
 * 화면이 쓰는 페르소나 모양으로. 피부 타입이 없으면 null — 리뷰 필터·"내 피부 타입 일치" 칩은
 * 피부 타입이 있어야 뜻이 있다. `persona_id` 는 회원 accountId (09-09 합의: 추천 `persona_id` 에 그대로 보낸다).
 */
export function profileToPersona(accountId: string, p: MemberProfile): PersonaProfile | null {
  if (!p.skin_type) return null;
  return {
    persona_id: accountId,
    skin_type: p.skin_type,
    skin_tone: p.skin_tone ?? '',
    eye_color: p.eye_color ?? '',
    hair_color: p.hair_color ?? '',
    n_reviews: 0,
  };
}

/* ---------- 저장 (이 브라우저 · 계정별) ---------- */

const KEY_PREFIX = 'bloom.profile.v1.';
const listeners = new Set<() => void>();

function keyFor(accountId: string): string {
  return `${KEY_PREFIX}${accountId}`;
}

/**
 * 같은 저장본이면 같은 객체를 돌려준다. `useSyncExternalStore` 의 getSnapshot 은 값이 안 바뀌었을 때 **같은 참조**를
 * 줘야 한다 — 매번 새 객체를 만들면 React 가 무한 재렌더로 판단해 화면이 죽는다.
 */
const snapshotCache = new Map<string, { raw: string | null; value: MemberProfile }>();

export function loadMemberProfile(accountId: string | null | undefined): MemberProfile {
  if (!accountId) return EMPTY_PROFILE;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(keyFor(accountId));
  } catch {
    return EMPTY_PROFILE;
  }
  const hit = snapshotCache.get(accountId);
  if (hit && hit.raw === raw) return hit.value;
  let value = EMPTY_PROFILE;
  if (raw) {
    try {
      value = sanitizeProfile(JSON.parse(raw) as Partial<Record<ProfileField, unknown>>);
    } catch {
      value = EMPTY_PROFILE;
    }
  }
  snapshotCache.set(accountId, { raw, value });
  return value;
}

export function saveMemberProfile(accountId: string, profile: MemberProfile): void {
  try {
    const clean = sanitizeProfile(profile);
    if (isEmptyProfile(clean)) window.localStorage.removeItem(keyFor(accountId));
    else window.localStorage.setItem(keyFor(accountId), JSON.stringify(clean));
  } catch {
    /* 저장 불가 — 이번 탭에서만 유지 */
  }
  for (const l of listeners) l();
}

/** useSyncExternalStore 용. 다른 탭의 변경도 따라온다 */
export function subscribeMemberProfile(listener: () => void): () => void {
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
