/**
 * 쇼핑몰 진열 설정 — 소상공인이 고르고, 고객이 본다.
 *
 * HWABUN 은 브랜드 50개가 나눠 쓰는 공유 인프라다. 화면 하나를 모두에게 강요하면
 * 상품이 12개인 브랜드와 200개인 브랜드가 같은 진열을 쓰게 된다. 그래서 가입할 때
 * 자기 쇼핑몰의 진열을 고른다.
 *
 * 고르는 곳은 브랜드 대시보드(dashboard.html)이고, 적용되는 곳은 쇼핑몰(index.html)이다.
 * 둘은 같은 origin 이라 localStorage 로 건너간다. 쇼핑몰 탭은 storage 이벤트를 들어
 * 대시보드에서 바꾸면 새로고침 없이 따라온다.
 *
 * ## 왜 완성된 템플릿을 늘어놓지 않았나
 *
 * 템플릿을 N 개 만들면 CSS 가 N 벌이 되고, 사장님은 "3번인데 모서리만 각졌으면" 을
 * 표현할 수 없다. 그래서 서로 독립인 축으로 쪼갰다. 축은 각각 한 벌의 규칙만 있으면 된다.
 *
 *   layout   배열 — 상품을 어떻게 늘어놓나  grid · showcase · catalog · list
 *   promo    위치 — 기획전을 어디에 두나    top · side · bottom · off
 *   density  크기 — 얼마나 촘촘하게         airy · cozy · compact
 *   corner   모서리 — 각지게 · 둥글게       sharp · soft · round
 *   card     카드 — 테두리 · 그림자 · 민무늬 line · shadow · plain
 *   font     글꼴 — 기본 · 명조 · 넓은 자간  sans · serif · wide
 *   header   헤더 — 로고 자리와 높이         plain · center · mini
 *   theme    색                            9종
 *
 * 4 x 4 x 3 x 3 x 3 x 3 x 3 x 9 = 104,976 가지. 규칙은 축마다 한 벌씩,
 * 전부 src/styles/storefront.css 안에 있다.
 *
 * 축이 여덟이면 고르는 화면이 서류가 된다. 그래서 **시작점(프리셋)** 을 따로 둔다.
 * 하나 누르면 뼈대 축이 한 번에 정해지고, 거기서 마음에 안 드는 축만 손대면 된다.
 * 색과 브랜드 이름은 프리셋이 건드리지 않는다 — 그건 브랜드마다 다른 것이지
 * 스타일의 일부가 아니다.
 *
 * ## 이벤트를 건드리지 않는 이유
 *
 * 모든 축을 **CSS 로만** 구현한다. ProductListPage 도 ProductCard 도 자기가 어떤 진열에
 * 놓였는지 모른다. 로그가 붙잡는 것이 좌표가 아니라 의미이기 때문에 이것이 성립한다.
 *
 *   data-log-section/content/ref  section.ts 가 closest() 로 조상을 타고 올라가 찾는다.
 *                                 grid-area 로 자리를 옮겨도 조상은 그대로다.
 *   data-position                 화면상의 위치가 아니라 **데이터 배열의 순위**다.
 *
 * 그래서 지켜야 할 선도 분명하다.
 *
 *   해도 되는 것  자리 이동, 순서 바꾸기, 열 수, 여백, 크기, 모서리, 글꼴, 섹션 숨김
 *   하면 안 되는 것  1) 카드를 data-log-section 밖으로 옮기는 JSX 개편 — section_id 가 끊긴다
 *                    2) CSS order/dense 로 **카드**의 시각 순서 바꾸기 — position 이 거짓말한다
 *
 * 섹션끼리 자리를 바꾸는 것은 2번에 걸리지 않는다. 섹션에는 순위가 없다.
 *
 * 계정·권한이 백엔드에 생기면 저장소만 그쪽으로 옮긴다. 타입과 함수는 그대로다.
 */

export type StorefrontLayout = 'grid' | 'showcase' | 'catalog' | 'list';
export type StorefrontPromo = 'top' | 'side' | 'bottom' | 'off';
export type StorefrontDensity = 'airy' | 'cozy' | 'compact';
export type StorefrontCorner = 'sharp' | 'soft' | 'round';
export type StorefrontCard = 'line' | 'shadow' | 'plain';
export type StorefrontFont = 'sans' | 'serif' | 'wide';
export type StorefrontHeader = 'plain' | 'center' | 'mini';
export type StorefrontTheme =
  | 'bloom'
  | 'rose'
  | 'coral'
  | 'lavender'
  | 'mint'
  | 'earth'
  | 'sand'
  | 'clinic'
  | 'mono';

export interface StorefrontPrefs {
  layout: StorefrontLayout;
  promo: StorefrontPromo;
  density: StorefrontDensity;
  corner: StorefrontCorner;
  card: StorefrontCard;
  font: StorefrontFont;
  header: StorefrontHeader;
  theme: StorefrontTheme;
  /** 쇼핑몰 헤더에 표시되는 브랜드 이름. 비우면 BLOOM 워드마크 */
  brandName: string;
  /**
   * 이 쇼핑몰이 **누구 것인가** — 이벤트 봉투의 `tenant_id` (계약 §1.1).
   *
   * 표시명(`brandName`)에서 한 번 만든 slug 다. 상품 브랜드(`brand_id`)와 다른 값이고,
   * 격리·파티션 키는 이것만 쓴다. 표시명을 고칠 때마다 다시 계산하지 않는다 —
   * 규칙이 바뀌거나 이름이 바뀌면 파티션이 조용히 갈라지기 때문이다. 계정·백엔드가
   * 생기면 서버가 발급한 값을 여기 넣는다. 형식은 그대로다.
   */
  tenantId: string;
}

/** 계약 `event-schema.json` 이 `tenant_id` 에 직접 거는 정규식 */
export const TENANT_ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** 표시명이 비어 있을 때의 테넌트. 기본 쇼핑몰 이름과 같다 */
export const DEFAULT_TENANT_ID = 'bloom';

/**
 * 표시명 → `tenant_id` slug. 계약 §1.1.1 의 생성 규칙 그대로다.
 *
 *   NFKD 로 악센트를 떼고 ASCII 로 접는다 → 영숫자 아닌 구간을 하이픈으로 → 앞뒤 하이픈 제거
 *
 *   Estée Lauder → estee-lauder   Lancôme → lancome   Dr. Jart+ → dr-jart
 *
 * 한글처럼 ASCII 로 접히지 않는 이름은 비어서 기본값이 된다. 그런 이름은 서버 발급
 * (순번 부여) 이 생기기 전까지는 한 테넌트로 뭉친다는 뜻이라, 시연용 브랜드는 영문
 * 표시명을 쓴다. 충돌 시 순번을 붙이는 것은 Dimension 이 할 일이고 프론트는 모른다.
 */
export function slugifyTenant(name: string): string {
  const slug = name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return TENANT_ID_PATTERN.test(slug) ? slug : DEFAULT_TENANT_ID;
}

/** 봉투에 실을 값. 저장된 slug 가 형식에 맞으면 그것, 아니면 표시명에서 만든다 */
export function tenantIdOf(prefs: Pick<StorefrontPrefs, 'tenantId' | 'brandName'>): string {
  return TENANT_ID_PATTERN.test(prefs.tenantId) ? prefs.tenantId : slugifyTenant(prefs.brandName);
}

interface Option<K> {
  key: K;
  label: string;
  desc: string;
}

export const STOREFRONT_LAYOUTS: Array<Option<StorefrontLayout> & { fit: string }> = [
  {
    key: 'grid',
    label: '그리드',
    desc: '위에 카테고리 탭, 아래로 카드가 균일하게 채워진다',
    fit: '상품 30~200개 · 가장 익숙한 진열',
  },
  {
    key: 'showcase',
    label: '쇼케이스',
    desc: '카드를 크게 키우고 열을 줄인다. 사진이 주인공',
    fit: '상품이 적고 사진이 좋은 브랜드',
  },
  {
    key: 'catalog',
    label: '카탈로그',
    desc: '왼쪽에 카테고리·고민·가격대를 세우고 오른쪽에 촘촘한 목록',
    fit: '상품이 많고 성분·고민으로 찾는 고객',
  },
  {
    key: 'list',
    label: '리스트',
    desc: '한 줄에 하나씩. 사진은 왼쪽, 이름·가격·별점은 오른쪽',
    fit: '이름과 가격을 눈으로 비교하며 고르는 고객',
  },
];

export const STOREFRONT_PROMOS: Array<Option<StorefrontPromo>> = [
  { key: 'top', label: '맨 위', desc: '들어오자마자 기획전부터 본다' },
  { key: 'side', label: '오른쪽', desc: '목록을 보는 내내 옆에 따라붙는다' },
  { key: 'bottom', label: '맨 아래', desc: '상품을 다 훑은 사람에게 마지막으로 권한다' },
  { key: 'off', label: '없음', desc: '상품 목록만. 기획전을 안 쓰는 브랜드' },
];

export const STOREFRONT_DENSITIES: Array<Option<StorefrontDensity>> = [
  { key: 'airy', label: '넉넉하게', desc: '카드가 크고 여백이 넓다' },
  { key: 'cozy', label: '보통', desc: '기본' },
  { key: 'compact', label: '촘촘하게', desc: '한 화면에 더 많이' },
];

export const STOREFRONT_CORNERS: Array<Option<StorefrontCorner>> = [
  { key: 'sharp', label: '각지게', desc: '모서리 0. 편집숍처럼 단정하게' },
  { key: 'soft', label: '기본', desc: '살짝 둥근 모서리' },
  { key: 'round', label: '둥글게', desc: '많이 둥글게. 부드럽고 친근하게' },
];

export const STOREFRONT_CARDS: Array<Option<StorefrontCard>> = [
  { key: 'line', label: '테두리', desc: '카드마다 얇은 선' },
  { key: 'shadow', label: '그림자', desc: '선 대신 그림자로 띄운다' },
  { key: 'plain', label: '민무늬', desc: '선도 상자도 없이 사진만' },
];

export const STOREFRONT_FONTS: Array<Option<StorefrontFont>> = [
  { key: 'sans', label: '기본', desc: '고딕. 읽기 쉽다' },
  { key: 'serif', label: '명조', desc: '제목이 명조체로. 고급스럽게' },
  { key: 'wide', label: '넓게', desc: '자간을 넓혀 잡지처럼' },
];

export const STOREFRONT_HEADERS: Array<Option<StorefrontHeader>> = [
  { key: 'plain', label: '왼쪽 로고', desc: '로고 왼쪽, 메뉴 옆에. 가장 익숙하다' },
  { key: 'center', label: '가운데 로고', desc: '로고를 가운데 세운다. 브랜드를 앞세울 때' },
  { key: 'mini', label: '얇게', desc: '띠 배너를 빼고 높이를 줄인다. 상품이 먼저 보인다' },
];

/**
 * 색 9종.
 *
 * 앞 넷은 BLOOM 팔레트(Fresh Green · Blossom Pink · Earthy Brown · Soft Mint)의 역할만
 * 바꾼 것이고, 뒤 다섯은 뷰티 브랜드가 실제로 많이 쓰는 색맥을 더한 것이다.
 * 어느 테마든 바뀌는 것은 브랜드 토큰 일곱 개뿐 — 글자·선·바탕 중립색은 그대로다.
 * 그래서 색을 아무거나 골라도 화면이 무너지지 않는다.
 */
export const STOREFRONT_THEMES: Array<
  Option<StorefrontTheme> & { /** [주색(CTA·별점), 강조(배지), 리본] */ swatch: [string, string, string] }
> = [
  { key: 'bloom', label: '블룸', desc: 'Fresh Green CTA · Blossom Pink 배지', swatch: ['#a8c96e', '#e68fa1', '#d8e9c3'] },
  { key: 'rose', label: '로즈', desc: 'Blossom Pink 를 앞에. 부드럽고 따뜻하게', swatch: ['#e68fa1', '#a8c96e', '#f7dfe4'] },
  { key: 'coral', label: '코랄', desc: '산호빛. 생기 있고 눈에 띈다', swatch: ['#ef7f5e', '#7a5b43', '#fde3d8'] },
  { key: 'lavender', label: '라벤더', desc: '연보라. 진정·수면 계열에 잘 붙는다', swatch: ['#9184c4', '#e68fa1', '#ece8f7'] },
  { key: 'mint', label: '민트', desc: 'Soft Mint 계열. 맑고 가볍게', swatch: ['#8fb889', '#e68fa1', '#e4f0d6'] },
  { key: 'earth', label: '어스', desc: 'Earthy Brown CTA. 차분한 클린 뷰티', swatch: ['#7a5b43', '#e68fa1', '#efe6dc'] },
  { key: 'sand', label: '샌드', desc: '베이지 골드. 고급스럽고 조용하게', swatch: ['#b9944f', '#7a5b43', '#f4ead4'] },
  { key: 'clinic', label: '클리닉', desc: '딥 블루. 임상 근거를 앞세우는 더마 브랜드', swatch: ['#35618f', '#8fb889', '#dfe9f4'] },
  { key: 'mono', label: '모노', desc: '무채색. 상품 사진 색만 살린다 (기본)', swatch: ['#1d1d1f', '#6e6e73', '#e8e8ed'] },
];

/** 프리셋이 정하는 축. 색과 이름은 뺀다 */
export type StorefrontStyle = Omit<StorefrontPrefs, 'theme' | 'brandName' | 'tenantId'>;

export const STOREFRONT_PRESETS: Array<{
  key: string;
  label: string;
  desc: string;
  style: StorefrontStyle;
}> = [
  {
    key: 'clean',
    label: '심플',
    desc: '4열 그리드에 기획전이 맨 위. 무난하고 익숙하다',
    style: { layout: 'grid', promo: 'top', density: 'cozy', corner: 'soft', card: 'line', font: 'sans', header: 'plain' },
  },
  {
    key: 'magazine',
    label: '매거진',
    desc: '큰 사진 2열, 상자 없이 사진만. 각진 모서리에 명조 제목',
    style: { layout: 'showcase', promo: 'top', density: 'airy', corner: 'sharp', card: 'plain', font: 'serif', header: 'center' },
  },
  {
    key: 'boutique',
    label: '부티크',
    desc: '기획전을 옆에 세우고 카드를 크게. 둥근 모서리와 그림자',
    style: { layout: 'showcase', promo: 'side', density: 'airy', corner: 'round', card: 'shadow', font: 'wide', header: 'center' },
  },
  {
    key: 'catalog',
    label: '카탈로그',
    desc: '왼쪽 필터에 4열 촘촘한 목록. 기획전 없이 상품만',
    style: { layout: 'catalog', promo: 'off', density: 'compact', corner: 'sharp', card: 'line', font: 'sans', header: 'mini' },
  },
  {
    key: 'market',
    label: '마켓',
    desc: '한 줄에 하나씩 훑어보고 기획전은 맨 아래',
    style: { layout: 'list', promo: 'bottom', density: 'compact', corner: 'soft', card: 'line', font: 'sans', header: 'plain' },
  },
];

/** 지금 설정이 어느 프리셋과 같은가. 없으면 null (직접 고른 조합) */
export function matchPreset(prefs: StorefrontPrefs): string | null {
  const found = STOREFRONT_PRESETS.find((preset) =>
    (Object.keys(preset.style) as Array<keyof StorefrontStyle>).every(
      (axis) => preset.style[axis] === prefs[axis],
    ),
  );
  return found?.key ?? null;
}

export const DEFAULT_STOREFRONT: StorefrontPrefs = {
  layout: 'grid',
  promo: 'top',
  density: 'cozy',
  corner: 'soft',
  card: 'line',
  font: 'sans',
  header: 'plain',
  /** 아무것도 안 골랐을 때는 무채색 — 처음 세포라 모양. 색은 사장님이 진열 설정에서 고른다 */
  theme: 'mono',
  brandName: '',
  tenantId: DEFAULT_TENANT_ID,
};

export const STOREFRONT_KEY = 'bloom.storefront.v1';

const keyOf = <K,>(options: Array<Option<K>>, value: unknown, fallback: K): K =>
  options.some((o) => o.key === value) ? (value as K) : fallback;

/**
 * 저장된 설정. 없거나 깨져 있으면 null — 대시보드는 그때 가입 화면을 띄운다.
 *
 * 축이 늘어나도 저장 키는 올리지 않는다. 먼저 가입한 사장님의 설정에는 새 축이 없는데,
 * 그걸 이유로 null 을 돌려주면 멀쩡히 쓰던 쇼핑몰이 가입 화면으로 되돌아간다.
 * 모르는 축은 기본값으로 채운다.
 */
export function loadStorefront(): StorefrontPrefs | null {
  try {
    const raw = window.localStorage.getItem(STOREFRONT_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<StorefrontPrefs>;
    if (!STOREFRONT_LAYOUTS.some((l) => l.key === p.layout)) return null;

    return {
      layout: p.layout as StorefrontLayout,
      promo: keyOf(STOREFRONT_PROMOS, p.promo, DEFAULT_STOREFRONT.promo),
      density: keyOf(STOREFRONT_DENSITIES, p.density, DEFAULT_STOREFRONT.density),
      corner: keyOf(STOREFRONT_CORNERS, p.corner, DEFAULT_STOREFRONT.corner),
      card: keyOf(STOREFRONT_CARDS, p.card, DEFAULT_STOREFRONT.card),
      font: keyOf(STOREFRONT_FONTS, p.font, DEFAULT_STOREFRONT.font),
      header: keyOf(STOREFRONT_HEADERS, p.header, DEFAULT_STOREFRONT.header),
      theme: keyOf(STOREFRONT_THEMES, p.theme, DEFAULT_STOREFRONT.theme),
      brandName: typeof p.brandName === 'string' ? p.brandName : '',
      // 0.3.0-draft 전에 가입한 설정에는 slug 가 없다. 표시명에서 한 번 만들어 채운다
      tenantId: tenantIdOf({
        tenantId: typeof p.tenantId === 'string' ? p.tenantId : '',
        brandName: typeof p.brandName === 'string' ? p.brandName : '',
      }),
    };
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

const labelOf = <K,>(options: Array<Option<K>>, key: K): string =>
  options.find((o) => o.key === key)?.label ?? String(key);

/** 사람이 읽는 한 줄 요약. 대시보드 사이드바가 쓴다 — 뼈대 축만 적는다 */
export function describeStorefront(prefs: StorefrontPrefs): string {
  return [
    labelOf(STOREFRONT_LAYOUTS, prefs.layout),
    `기획전 ${labelOf(STOREFRONT_PROMOS, prefs.promo)}`,
    labelOf(STOREFRONT_DENSITIES, prefs.density),
    labelOf(STOREFRONT_THEMES, prefs.theme),
  ].join(' · ');
}

/**
 * 모든 이벤트 봉투에 실을 진열 정보.
 *
 * 이벤트 정의는 하나도 바뀌지 않는다. `properties` 는 계약상 열린 객체라
 * (`contracts/event-schema.json` — `"properties": {"type": "object"}`) 필드를 더해도
 * 검증기·수집 서버·기존 소비자가 그대로 통과한다.
 *
 * 이걸 싣는 이유는 진열이 이제 브랜드마다 다르기 때문이다. 같은 `product_click` 이라도
 * 4열 그리드에서 나온 것과 옆에 붙은 기획전 레일에서 나온 것은 다른 화면의 결과다.
 * 진열을 안 실으면 브랜드 50개 로그를 합쳤을 때 그 차이가 노이즈로 남는다.
 * 실으면 "어느 진열이 더 잘 팔리나" 가 group by 한 줄이 된다 — 브랜드 하나로는
 * 답할 수 없고 모였을 때만 답이 나오는 질문, 우리가 하려는 바로 그것이다.
 */
export function storefrontEventProps(prefs: StorefrontPrefs): Record<string, string> {
  return {
    storefront_layout: prefs.layout,
    storefront_promo: prefs.promo,
    storefront_density: prefs.density,
    storefront_corner: prefs.corner,
    storefront_card: prefs.card,
    storefront_font: prefs.font,
    storefront_header: prefs.header,
    storefront_theme: prefs.theme,
  };
}

/**
 * 쇼핑몰 문서에 설정을 건다. storefront.css 가 이 속성들만 보고 진열을 바꾼다.
 * 쇼핑몰(App.tsx)만 부른다 — 대시보드 화면은 이 설정에 안 흔들린다.
 */
export function applyStorefront(prefs: StorefrontPrefs): void {
  const root = document.documentElement;
  root.dataset.storefront = prefs.layout;
  root.dataset.promo = prefs.promo;
  root.dataset.density = prefs.density;
  root.dataset.corner = prefs.corner;
  root.dataset.card = prefs.card;
  root.dataset.font = prefs.font;
  root.dataset.header = prefs.header;
  root.dataset.theme = prefs.theme;
}
