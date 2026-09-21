/**
 * 개발·시연 도구 표시 여부 — 페르소나 선택기(헤더)와 로그 창(우하단).
 *
 * 둘 다 실제 고객용 기능이 아니다. 페르소나 선택기는 로그인이 없던 시절의 "로그인 대용"이고
 * PA 에이전트(Playwright)가 자기 페르소나를 고르는 데 쓴다. 로그 창은 수집 확인용이다.
 * 고객 로그인(MEMBER)이 생긴 뒤에는 사람에게 보일 이유가 없어서 아래 조건에서만 켠다.
 *
 *   - 자동화 브라우저: `navigator.webdriver` (PA 러너는 Playwright 라 항상 true)
 *   - 주소에 `?dev=1` (한 번 켜면 localStorage 에 남는다. `?dev=0` 으로 끈다)
 */
const KEY = 'bloom.devtools.v1';

export function isDevtoolsOn(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const q = new URLSearchParams(window.location.search).get('dev');
    if (q === '1') window.localStorage.setItem(KEY, '1');
    if (q === '0') window.localStorage.removeItem(KEY);
    if (window.localStorage.getItem(KEY) === '1') return true;
  } catch {
    // 저장이 막힌 환경이면 주소·webdriver 만 본다
  }
  return navigator.webdriver === true;
}

/**
 * 등록 폼 미리보기 (`?preview=1`). 대시보드 상품 등록 화면이 iframe 으로 띄운다.
 * 상세 페이지 본문만 그리고 사이트 껍데기(헤더·프로모·페르소나 스위처·로그 창)는 안 그린다. 로그는 environment=preview.
 */
export function isPreviewMode(): boolean {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('preview') === '1';
}
