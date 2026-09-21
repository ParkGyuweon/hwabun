/**
 * 회원 피부 프로필 · 서버 저장 (shop_backend `MemberProfileController`, 2026-09-21).
 *
 *   GET /api/members/me/profile   → { skinTypeCode, skinToneCode, hairColorCode, eyeColorCode }
 *   PUT /api/members/me/profile   같은 모양 → 저장된 값
 *
 * 전에는 프로필 API 가 없어 마이페이지가 이 브라우저에만 저장했다. 가입 때 보낸 값은 서버 `member` 컬럼에 있었는데
 * 화면이 한 번도 읽지 않아 "선택 안 함" 으로 보였다 (유림님 제보). 이제 **서버가 정본**이고 브라우저 저장본
 * (lib/memberProfile)은 서버 값을 그대로 비춰 두는 사본이다 — 추천·리뷰 필터가 그 사본을 동기적으로 읽기 때문이다.
 *
 * 못 읽으면(서버 없음·개발자 모드·401) null 을 돌려주고 사본을 건드리지 않는다.
 */
import { useEffect } from 'react';
import { authFetch } from './auth';
import { EMPTY_PROFILE, isEmptyProfile, loadMemberProfile, profileToApi, sanitizeProfile, saveMemberProfile } from './memberProfile';
import type { MemberProfile } from './memberProfile';

interface ProfileDto {
  skinTypeCode?: string | null;
  skinToneCode?: string | null;
  hairColorCode?: string | null;
  eyeColorCode?: string | null;
}

function fromApi(d: ProfileDto | null | undefined): MemberProfile {
  if (!d) return EMPTY_PROFILE;
  return sanitizeProfile({
    skin_type: d.skinTypeCode ?? null,
    skin_tone: d.skinToneCode ?? null,
    hair_color: d.hairColorCode ?? null,
    eye_color: d.eyeColorCode ?? null,
  });
}

export async function fetchMemberProfile(): Promise<MemberProfile | null> {
  try {
    const res = await authFetch('MEMBER', '/api/members/me/profile');
    if (!res.ok) return null;
    return fromApi((await res.json()) as ProfileDto);
  } catch {
    return null;
  }
}

export type ProfileSaveResult = { ok: true; profile: MemberProfile } | { ok: false; reason: string };

export async function saveMemberProfileServer(profile: MemberProfile): Promise<ProfileSaveResult> {
  try {
    const res = await authFetch('MEMBER', '/api/members/me/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profileToApi(profile)),
    });
    if (res.status === 503) return { ok: false, reason: '개발자 모드' };
    if (!res.ok) return { ok: false, reason: `서버 응답 ${res.status}` };
    return { ok: true, profile: fromApi((await res.json()) as ProfileDto) };
  } catch {
    return { ok: false, reason: '서버에 연결할 수 없습니다' };
  }
}

/**
 * 로그인한 회원의 서버 프로필을 받아 브라우저 사본에 쓴다. 헤더(AccountMenu)처럼 늘 떠 있는 곳에서 한 번 부르면
 * 추천·리뷰 필터·마이페이지가 전부 서버 값을 본다.
 *
 * 서버가 비어 있고 브라우저 사본만 있으면(API 가 없던 시절에 저장한 것) 사본을 서버에 한 번 올린다 — 사장님이 다시
 * 고르게 하지 않는다. 그 뒤로는 서버가 정본이다.
 */
export function useSyncMemberProfile(accountId: string | null | undefined): void {
  useEffect(() => {
    if (!accountId) return;
    let alive = true;
    void fetchMemberProfile().then(async (server) => {
      if (!alive || server === null) return;
      const local = loadMemberProfile(accountId);
      if (isEmptyProfile(server) && !isEmptyProfile(local)) {
        const up = await saveMemberProfileServer(local);
        if (alive && up.ok) saveMemberProfile(accountId, up.profile);
        return;
      }
      saveMemberProfile(accountId, server);
    });
    return () => {
      alive = false;
    };
  }, [accountId]);
}
