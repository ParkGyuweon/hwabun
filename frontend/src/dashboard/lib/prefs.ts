/**
 * 브랜드 담당자가 고르는 화면 설정 — 레이아웃과 색.
 *
 * HWABUN 은 브랜드 50개가 나눠 쓰는 공유 인프라다. 화면 하나를 모두에게 강요하면
 * 어떤 담당자에게는 맞고 어떤 담당자에게는 안 맞는다. 그래서 첫 진입에서 고르게 한다.
 *
 * 저장은 브라우저(localStorage)에 한다. 계정·권한이 백엔드에 생기면 그쪽으로 옮긴다.
 * 그때까지는 이 브라우저에서 이 브랜드 담당자가 고른 값이다.
 */

export type LayoutKey = 'sidebar' | 'topbar' | 'compact';
export type ThemeKey = 'hwabun' | 'blossom' | 'earth' | 'mint' | 'mono';

export interface Prefs {
  layout: LayoutKey;
  theme: ThemeKey;
  /** 담당자가 적은 자기 브랜드 이름. 사이드바에 표시한다 */
  brandName: string;
}

export const LAYOUTS: Array<{ key: LayoutKey; label: string; desc: string }> = [
  {
    key: 'sidebar',
    label: '사이드바',
    desc: '왼쪽 메뉴에서 화면을 오가며 본다. 매일 여러 화면을 확인하는 분께',
  },
  {
    key: 'topbar',
    label: '상단 탭',
    desc: '메뉴는 위에 한 줄, 본문은 넓게. 표와 그래프를 크게 보고 싶은 분께',
  },
  {
    key: 'compact',
    label: '컴팩트',
    desc: '좁은 메뉴, 촘촘한 카드. 한 화면에서 숫자를 많이 훑는 분께',
  },
];

/**
 * 색 테마. 브랜드 팔레트 네 색(Fresh Green · Blossom Pink · Earthy Brown · Soft Mint)의
 * 역할을 바꾸는 방식이다. 팔레트 밖의 색은 쓰지 않는다 — 어느 테마를 골라도 HWABUN 이다.
 *
 * `mono` 는 예외로 무채색이다. 지표를 색으로 읽고 싶지 않은 담당자를 위한 것이다.
 * 실측/모의 배지와 감점·경고 같은 의미 색은 테마와 무관하게 유지된다.
 */
export const THEMES: Array<{
  key: ThemeKey;
  label: string;
  desc: string;
  /** 미리보기 스와치. [주색, 강조, 보조] */
  swatch: [string, string, string];
}> = [
  { key: 'hwabun', label: '화분', desc: '기본. Fresh Green 이 자료, Blossom Pink 가 강조', swatch: ['#a8c96e', '#e68fa1', '#7a5b43'] },
  { key: 'blossom', label: '블라썸', desc: 'Blossom Pink 를 앞에. 부드럽고 따뜻하게', swatch: ['#e68fa1', '#a8c96e', '#7a5b43'] },
  { key: 'earth', label: '어스', desc: 'Earthy Brown 이 자료. 차분하고 안정적으로', swatch: ['#7a5b43', '#e68fa1', '#a8c96e'] },
  { key: 'mint', label: '민트', desc: 'Soft Mint 계열. 밝고 가볍게', swatch: ['#9cc08a', '#e68fa1', '#6b7280'] },
  { key: 'mono', label: '모노', desc: '무채색. 색이 판단을 앞지르지 않게', swatch: ['#2b2b2b', '#6b7280', '#9aa0a6'] },
];

export const DEFAULT_PREFS: Prefs = { layout: 'sidebar', theme: 'hwabun', brandName: '' };

const STORAGE_KEY = 'hwabun.prefs.v1';

const isLayout = (v: unknown): v is LayoutKey => LAYOUTS.some((l) => l.key === v);
const isTheme = (v: unknown): v is ThemeKey => THEMES.some((t) => t.key === v);

/** 저장된 설정. 없거나 깨져 있으면 null — 그때는 선택 화면을 띄운다 */
export function loadPrefs(): Prefs | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    if (!isLayout(parsed.layout) || !isTheme(parsed.theme)) return null;
    return {
      layout: parsed.layout,
      theme: parsed.theme,
      brandName: typeof parsed.brandName === 'string' ? parsed.brandName : '',
    };
  } catch {
    return null;
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // 사생활 보호 모드 등에서 저장이 막힐 수 있다. 화면은 그대로 동작한다
  }
}

/**
 * 문서 루트에 테마를 건다. CSS 가 `:root[data-theme]` 로 토큰을 바꾼다.
 * 레이아웃은 `.console[data-layout]` 에 걸어서 대시보드 안에서만 작용한다.
 */
export function applyTheme(theme: ThemeKey): void {
  document.documentElement.dataset.theme = theme;
}
