/**
 * 쇼핑몰 진열 설정 — 소상공인이 고르고, 고객이 본다.
 *
 * HWABUN 은 브랜드 50개가 나눠 쓰는 공유 인프라다. 화면 하나를 모두에게 강요하면
 * 상품이 12개인 브랜드와 200개인 브랜드가 같은 진열을 쓰게 된다. 그래서 가입할 때
 * 자기 쇼핑몰의 **진열 레이아웃과 색**을 고른다.
 *
 * 고르는 곳은 브랜드 대시보드(dashboard.html)이고, 적용되는 곳은 쇼핑몰(index.html)이다.
 * 둘은 같은 origin 이라 localStorage 로 건너간다. 쇼핑몰 탭은 storage 이벤트를 들어
 * 대시보드에서 바꾸면 새로고침 없이 따라온다 — 시연에서 두 탭을 나란히 놓을 수 있다.
 *
 * 계정·권한이 백엔드에 생기면 저장소만 그쪽으로 옮긴다. 이 파일의 타입과 함수는 그대로다.
 */

export type StorefrontLayout = 'grid' | 'showcase' | 'catalog';
export type StorefrontTheme = 'bloom' | 'rose' | 'earth' | 'mint' | 'mono';

export interface StorefrontPrefs {
  layout: StorefrontLayout;
  theme: StorefrontTheme;
  /** 쇼핑몰 헤더에 표시되는 브랜드 이름. 비우면 BLOOM 워드마크 */
  brandName: string;
}

export const STOREFRONT_LAYOUTS: Array<{
  key: StorefrontLayout;
  label: string;
  desc: string;
  /** 어떤 브랜드에 맞는가 */
  fit: string;
}> = [
  {
    key: 'grid',
    label: '그리드',
    desc: '위에 카테고리 탭, 아래 4열 카드. 가장 익숙한 진열',
    fit: '상품 30~200개',
  },
  {
    key: 'showcase',
    label: '쇼케이스',
    desc: '큰 기획전과 2열 큼직한 카드. 사진이 주인공',
    fit: '상품이 적고 사진이 좋은 브랜드',
  },
  {
    key: 'catalog',
    label: '카탈로그',
    desc: '왼쪽에 필터, 오른쪽에 3열 촘촘한 목록. 고민·가격대로 바로 좁힌다',
    fit: '상품이 많고 성분·고민으로 찾는 고객',
  },
];

/**
 * 색 테마. BLOOM 팔레트 네 색(Fresh Green · Blossom Pink · Earthy Brown · Soft Mint)의
 * 역할만 바꾼다. 어느 테마를 골라도 팔레트 밖으로 나가지 않는다.
 * `mono` 만 무채색 — 상품 사진 색을 그대로 살리고 싶은 브랜드용.
 */
export const STOREFRONT_THEMES: Array<{
  key: StorefrontTheme;
  label: string;
  desc: string;
  /** [주색(CTA·별점), 강조(배지), 리본] */
  swatch: [string, string, string];
}> = [
  { key: 'bloom', label: '블룸', desc: 'Fresh Green CTA · Blossom Pink 배지 (기본)', swatch: ['#a8c96e', '#e68fa1', '#d8e9c3'] },
  { key: 'rose', label: '로즈', desc: 'Blossom Pink 를 앞에. 부드럽고 따뜻하게', swatch: ['#e68fa1', '#a8c96e', '#f7dfe4'] },
  { key: 'earth', label: '어스', desc: 'Earthy Brown CTA. 차분한 클린 뷰티', swatch: ['#7a5b43', '#e68fa1', '#efe6dc'] },
  { key: 'mint', label: '민트', desc: 'Soft Mint 계열. 맑고 가볍게', swatch: ['#8fb889', '#e68fa1', '#e4f0d6'] },
  { key: 'mono', label: '모노', desc: '무채색. 상품 사진 색만 살린다', swatch: ['#1d1d1f', '#6e6e73', '#e8e8ed'] },
];

export const DEFAULT_STOREFRONT: StorefrontPrefs = { layout: 'grid', theme: 'bloom', brandName: '' };

export const STOREFRONT_KEY = 'bloom.storefront.v1';

const isLayout = (v: unknown): v is StorefrontLayout => STOREFRONT_LAYOUTS.some((l) => l.key === v);
const isTheme = (v: unknown): v is StorefrontTheme => STOREFRONT_THEMES.some((t) => t.key === v);

/** 저장된 설정. 없거나 깨져 있으면 null — 대시보드는 그때 가입 화면을 띄운다 */
export function loadStorefront(): StorefrontPrefs | null {
  try {
    const raw = window.localStorage.getItem(STOREFRONT_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<StorefrontPrefs>;
    if (!isLayout(p.layout) || !isTheme(p.theme)) return null;
    return { layout: p.layout, theme: p.theme, brandName: typeof p.brandName === 'string' ? p.brandName : '' };
  } catch {
    return null;
  }
}

export function saveStorefront(prefs: StorefrontPrefs): void {
  try {
    window.localStorage.setItem(STOREFRONT_KEY, JSON.stringify(prefs));
  } catch {
    // 사생활 보호 모드 등에서 저장이 막힐 수 있다. 화면은 그대로 동작한다
  }
}

/**
 * 쇼핑몰 문서에 설정을 건다. storefront.css 가
 *   :root[data-storefront]  진열 레이아웃
 *   :root[data-theme]       색 토큰
 * 을 읽는다. 쇼핑몰(App.tsx)만 부른다 — 대시보드 화면은 이 설정에 안 흔들린다.
 */
export function applyStorefront(prefs: StorefrontPrefs): void {
  document.documentElement.dataset.storefront = prefs.layout;
  document.documentElement.dataset.theme = prefs.theme;
}
