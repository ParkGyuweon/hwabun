/**
 * 약관 화면의 주소 계약. **다른 브랜치(가입 폼 등)가 이 주소로 링크하므로 바꾸지 않는다.**
 *   `?terms=1`    이용약관
 *   `?privacy=1`  개인정보처리방침
 */
export type LegalPage = 'terms' | 'privacy';

export const LEGAL_QUERY: Record<LegalPage, string> = {
  terms: '?terms=1',
  privacy: '?privacy=1',
};

/** 현재 주소가 약관 화면이면 그 종류, 아니면 null */
export function legalPageFromUrl(search: string = window.location.search): LegalPage | null {
  const params = new URLSearchParams(search);
  if (params.get('terms') === '1') return 'terms';
  if (params.get('privacy') === '1') return 'privacy';
  return null;
}

/** history.state 에 실어 둔 값을 읽는다. 모르는 값은 null */
export function legalPageFromState(value: unknown): LegalPage | null {
  return value === 'terms' || value === 'privacy' ? value : null;
}
