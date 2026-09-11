/**
 * 브랜드 상품 등록 — 폼 입력이 쇼핑몰 상품(`Product`)이 되는 자리.
 *
 * 계약 `contracts/product-registration-spec.md` 를 따른다.
 *   §3  입력 필드: product_name · brand_name · secondary/tertiary_category · highlights(30종)
 *       · ingredients(자유 텍스트, 한글·영문) · price_krw
 *   §4  파이프라인이 채우는 값: price_usd(고정 환율) · rating(주입) · loves_count 0 · product_id
 *   §5  어휘 밖 값은 거부하지 않고 경고 + unmapped
 *   §7  원천 카탈로그와 같은 dim_product. product_source = brand_registered
 *
 * 백엔드 Product API(Jira 140)가 생기기 전까지 localStorage 에 둔다. 쇼핑몰(index.html)이
 * 같은 origin 이라 등록 즉시 목록·상세에 뜨고, **초안(draft)** 은 저장 전에도 쇼핑몰 상세
 * 페이지가 그대로 읽는다 — 등록 폼 옆의 미리보기가 그 페이지를 iframe 으로 띄운 것이다.
 * 폼과 소비자 화면이 같은 컴포넌트를 쓰니 미리보기와 실제가 한 픽셀도 다르지 않다.
 */
import { DEMO_BRAND, sampleProducts, seedProducts } from '../mocks/products';
import { KRW_PER_USD as KRW_PER_USD_DISPLAY } from './localize';
import { listBackendProducts, registerProductBackend } from './shopApi';
import type { RegisterResult } from './shopApi';
import { CONCERN_VALUES, HIGHLIGHT_VALUES, SECONDARY_CATEGORIES, TERTIARY_CATEGORIES } from './formLabels';
import type { Product } from '../types/product';

export const REGISTERED_KEY = 'hwabun.products.v1';
export const DRAFT_KEY = 'hwabun.product-draft.v1';
/** 초안의 product_id. 쇼핑몰이 `?product=DRAFT` 로 열면 초안을 보여 준다 */
export const DRAFT_PRODUCT_ID = 'DRAFT';

/**
 * 등록 시점 고정 환율 `[추정]`. 계약 §4.1 — 가격 구간(USD 0/20/35/50/80)이 넓어
 * 환율이 조금 달라져도 구간이 바뀌지 않으므로 실시간 환율을 쓰지 않는다.
 */
/**
 * 원화 → 달러. 표시(lib/localize toKrw)와 같은 환율이어야 사장님이 입력한 원화가 화면에 그대로 나온다.
 * 예전 1400 을 쓰면 29,500원을 넣고 28,300원이 떠서 등록 폼과 쇼핑몰 가격이 어긋났다 (2026-09-10 수정).
 */
export const KRW_PER_USD = KRW_PER_USD_DISPLAY;

/**
 * 추천 서버가 가격 구간을 자를 때 쓰는 환율 (계약 §4.1 · `catalog_registry.py:43`). 표시 환율과 다르다.
 *
 * 세 곳이 달랐다 (AI 요청 2026-09-10 §2.3-1): 프론트 표시 1,340.86 · 백엔드 1,300 · 추천 1,400. 순위는 추천 서버 값으로
 * 정해지므로 **구간 힌트는 이 값**으로 보여준다. 표시 가격은 그대로 1,340.86 이어야 사장님이 넣은 원화가 화면에 그대로 나온다.
 * 27,000원이면 1,400 기준 $19.3(~20 구간), 1,300 기준 $20.8(20~35 구간)로 구간이 갈린다.
 */
export const KRW_PER_USD_RECOMMEND = 1400;

/** 계약 §4.1 가격 구간 경계 (USD). 0~20 · 20~35 · 35~50 · 50~80 · 80~ */
const PRICE_BIN_EDGES = [20, 35, 50, 80];
const PRICE_BIN_KO = ['2만원 이하', '2~3만원대', '3만원대 후반~5만원', '5~8만원', '8만원 이상'];

/** 원화 → 추천이 읽는 가격 구간 이름과 달러 값 */
export function recommendPriceBin(priceKrw: number): { usd: number; bin: string } {
  const usd = priceKrw / KRW_PER_USD_RECOMMEND;
  const idx = PRICE_BIN_EDGES.findIndex((edge) => usd < edge);
  return { usd, bin: PRICE_BIN_KO[idx === -1 ? PRICE_BIN_KO.length - 1 : idx] };
}

export interface RegistrationForm {
  product_name: string;
  brand_name: string;
  secondary_category: string;
  tertiary_category: string;
  /** 어휘집 원문 값. concern 9 · clean 16 · texture 5 */
  highlights: string[];
  /** 전성분 자유 텍스트. 쉼표 구분, 한글·영문 모두 */
  ingredients: string;
  price_krw: number | '';
  size: string;
  /** 상세 페이지 About 블록. 계약 밖 선택 항목이라 벡터에는 안 들어간다 */
  what_it_is: string;
  suggested_usage: string;
  /** 줄마다 "성분명: 설명" */
  highlighted_ingredients: string;
  ingredient_callouts: string;
  brand_story: string;
  /** 대표 이미지 URL 또는 data URL. 없으면 플레이스홀더 */
  image_url: string;
}

export const EMPTY_FORM: RegistrationForm = {
  product_name: '',
  brand_name: DEMO_BRAND,
  secondary_category: '',
  tertiary_category: '',
  highlights: [],
  ingredients: '',
  price_krw: '',
  size: '',
  what_it_is: '',
  suggested_usage: '',
  highlighted_ingredients: '',
  ingredient_callouts: '',
  brand_story: '',
  image_url: '',
};

/**
 * 카테고리 2단계 짝. 어휘집은 두 목록을 따로 주고 짝은 주지 않아서 카탈로그(세포라 200 +
 * 시드)에서 실제로 같이 쓰인 조합을 읽는다. 카탈로그에 없는 tertiary 는 어느 secondary 에도
 * 붙지 않으므로 "기타" 로 전부 보여 준다.
 */
export const CATEGORY_TREE: ReadonlyMap<string, string[]> = (() => {
  const tree = new Map<string, Set<string>>();
  for (const s of SECONDARY_CATEGORIES) tree.set(s.value, new Set());
  for (const p of [...seedProducts, ...sampleProducts]) {
    const [, secondary, tertiary] = p.category;
    if (!secondary || !tree.has(secondary)) continue;
    if (tertiary) tree.get(secondary)!.add(tertiary);
  }
  const known = new Set([...tree.values()].flatMap((s) => [...s]));
  const orphans = TERTIARY_CATEGORIES.map((t) => t.value).filter((v) => !known.has(v));
  const out = new Map<string, string[]>();
  for (const [k, v] of tree) out.set(k, [...v, ...orphans].sort());
  return out;
})();

/* ───────────────────────── 검증 (계약 §6) ───────────────────────── */

export interface ValidationResult {
  /** 있으면 저장 불가 */
  errors: string[];
  /** 저장은 되지만 알려 준다 (계약 §3.3 · §5) */
  warnings: string[];
}

export function validateForm(form: RegistrationForm): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!form.product_name.trim()) errors.push('상품명을 입력해 주세요.');
  if (!form.brand_name.trim()) errors.push('브랜드명이 비어 있습니다.');
  if (!SECONDARY_CATEGORIES.some((c) => c.value === form.secondary_category)) errors.push('대분류를 골라 주세요.');
  if (!TERTIARY_CATEGORIES.some((c) => c.value === form.tertiary_category)) errors.push('세부 분류를 골라 주세요.');
  if (!form.ingredients.trim()) errors.push('전성분을 붙여 넣어 주세요. 추천은 전성분에서 성분을 읽습니다.');
  if (form.price_krw === '' || !(Number(form.price_krw) > 0)) errors.push('가격(원)은 0보다 커야 합니다.');

  const outside = form.highlights.filter((h) => !HIGHLIGHT_VALUES.has(h));
  if (outside.length) errors.push(`어휘에 없는 태그: ${outside.join(', ')}`);

  if (form.highlights.length === 0) {
    warnings.push('태그가 없으면 피부 고민·성분 표방·제형 세 블록이 0이 되어 추천 노출에 크게 불리합니다. 해당하는 것을 골라 주세요.');
  } else if (!form.highlights.some((h) => CONCERN_VALUES.has(h))) {
    warnings.push('피부 고민 태그가 하나도 없습니다. 고민 축은 추천 가중치가 가장 큽니다.');
  }
  if (form.secondary_category === 'Sunscreen' && !form.ingredients.match(/spf|titanium|zinc oxide|triazone|avobenzone|homosalate|octocrylene|methoxyphenyl/i)) {
    // 전성분에 차단 성분이 없으면 추천은 제품명의 `SPF nn` 표기로 SPF 축을 켠다 (Jira 243, 계약 §3.1)
    warnings.push('선케어인데 전성분에서 자외선 차단 성분을 찾지 못했습니다. 제품명에 "SPF 50" 처럼 표기하면 추천이 자외선 차단 상품으로 읽습니다.');
  }
  if (!form.image_url.trim()) warnings.push('대표 이미지가 없어 플레이스홀더로 보입니다.');

  return { errors, warnings };
}

/* ───────────────────────── 폼 → Product (계약 §4) ───────────────────────── */

export function toProduct(form: RegistrationForm, productId: string): Product {
  const concerns = form.highlights.filter((h) => CONCERN_VALUES.has(h));
  const priceKrw = Number(form.price_krw) || 0;
  const highlighted = form.highlighted_ingredients
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const image = form.image_url.trim() || null;

  return {
    product_id: productId,
    product_name: form.product_name.trim(),
    brand_name: form.brand_name.trim(),
    category: ['Skincare', form.secondary_category, form.tertiary_category].filter(Boolean),
    image_url: image,
    sku_id: null,
    images: image ? [image] : [],
    variants: [],
    description: {
      what_it_is: form.what_it_is.trim() || null,
      skin_type: null,
      concerns_text: concerns.length ? concerns.join(', ') : null,
      highlighted_ingredients: highlighted,
      ingredient_callouts: form.ingredient_callouts.trim() || null,
      what_else: null,
      clinical_results: null,
      suggested_usage: form.suggested_usage.trim() || null,
      brand_story: form.brand_story.trim() || null,
    },
    // §4.1 고정 환율. 소수 둘째 자리
    price_usd: Math.round((priceKrw / KRW_PER_USD) * 100) / 100,
    size: form.size.trim() || null,
    /**
     * §4.2 의 rating 주입은 **인코더 입력**이지 화면 값이 아니다. 화면에 주입값을 보이면
     * 실측 평점과 섞인다(rating_source 분리 원칙). 프론트는 null 로 두고 파이프라인이 채운다.
     */
    rating: null,
    review_count: 0,
    loves_count: 0,
    badges: ['new'],
    highlights: [...form.highlights],
    ingredients: form.ingredients.trim() ? [form.ingredients.trim()] : [],
    suitable_skin_types: [],
    skincare_concerns: concerns,
  };
}

/** Product → 폼 (수정할 때) */
export function fromProduct(p: Product): RegistrationForm {
  return {
    product_name: p.product_name,
    brand_name: p.brand_name,
    secondary_category: p.category[1] ?? '',
    tertiary_category: p.category[2] ?? '',
    highlights: [...p.highlights],
    ingredients: p.ingredients.join(', '),
    price_krw: Math.round(p.price_usd * KRW_PER_USD),
    size: p.size ?? '',
    what_it_is: p.description?.what_it_is ?? '',
    suggested_usage: p.description?.suggested_usage ?? '',
    highlighted_ingredients: (p.description?.highlighted_ingredients ?? []).join('\n'),
    ingredient_callouts: p.description?.ingredient_callouts ?? '',
    brand_story: p.description?.brand_story ?? '',
    image_url: p.image_url ?? '',
  };
}

/* ───────────────────────── 저장소 ───────────────────────── */

export interface RegisteredProduct {
  product: Product;
  /** 계약 §7 product_source */
  product_source: 'brand_registered';
  registered_at: string;
  updated_at: string;
}

const listeners = new Set<() => void>();
let registered: RegisteredProduct[] | null = null;
let draft: Product | null | undefined; // undefined = 아직 안 읽음
let version = 0;
let snapshotVersion = -1;
let snapshot: Product[] = [];

function bump(): void {
  version += 1;
  for (const l of listeners) l();
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function writeJson(key: string, value: unknown): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장이 막힌 환경이면 메모리로만 산다
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === REGISTERED_KEY) registered = null;
    else if (e.key === DRAFT_KEY) draft = undefined;
    else return;
    bump();
  });
}

export function registeredProducts(): RegisteredProduct[] {
  if (registered === null) {
    const list = readJson<RegisteredProduct[]>(REGISTERED_KEY, []);
    registered = Array.isArray(list) ? list : [];
  }
  return registered;
}

export function draftProduct(): Product | null {
  if (draft === undefined) draft = readJson<Product | null>(DRAFT_KEY, null);
  return draft;
}

/** 초안을 쇼핑몰이 읽을 수 있게 저장한다. 폼이 바뀔 때마다(디바운스) 부른다 */
export function setDraft(form: RegistrationForm | null): void {
  draft = form ? toProduct(form, DRAFT_PRODUCT_ID) : null;
  writeJson(DRAFT_KEY, draft);
  bump();
}

export function saveRegistered(form: RegistrationForm, existingId?: string): RegisteredProduct {
  const now = new Date().toISOString();
  const list = registeredProducts();
  const id = existingId ?? `BR${Date.now().toString(36).toUpperCase()}`;
  const prev = list.find((r) => r.product.product_id === id);
  const item: RegisteredProduct = {
    product: toProduct(form, id),
    product_source: 'brand_registered',
    registered_at: prev?.registered_at ?? now,
    updated_at: now,
  };
  registered = [item, ...list.filter((r) => r.product.product_id !== id)];
  writeJson(REGISTERED_KEY, registered);
  bump();
  return item;
}

export function removeRegistered(productId: string): void {
  registered = registeredProducts().filter((r) => r.product.product_id !== productId);
  writeJson(REGISTERED_KEY, registered);
  bump();
}

export function subscribeCatalog(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * 쇼핑몰이 읽는 카탈로그: 등록 상품 + 시드 + 세포라. **초안은 들어가지 않는다.**
 * 초안이 목록·추천에 섞이면 사장님이 타자 치는 동안 고객이 그걸 본다. 초안은
 * `resolveProduct(DRAFT)` 로 미리보기 주소에서만 연다.
 * 버전이 같으면 같은 배열을 돌려준다 (`useSyncExternalStore`).
 */
/* ---------- 백엔드 카탈로그 ----------
 * 첫 스냅샷 요청 때 한 번 받아 온다. 오면 bump 로 화면을 다시 그린다.
 * 백엔드가 없으면 빈 배열이고, 그러면 지금까지처럼 로컬 등록 + 시드 + 세포라만 보인다.
 */
let backend: Product[] = [];
let backendState: 'idle' | 'loading' | 'ready' | 'unavailable' = 'idle';

export function backendCatalogState(): typeof backendState {
  return backendState;
}

export async function refreshBackendCatalog(): Promise<void> {
  backendState = 'loading';
  const rows = await listBackendProducts();
  if (rows === null) {
    backendState = 'unavailable';
  } else {
    backend = rows;
    backendState = 'ready';
  }
  bump();
}

/**
 * 상품 등록. **백엔드 먼저, 안 되면 로컬.**
 * 백엔드에 들어간 상품은 카탈로그를 다시 받아 오면 보이고, 로컬 사본은 만들지 않는다.
 * 백엔드가 거절하면(지금은 category 시드가 없어 항상) 로컬에 저장하고 이유를 돌려준다.
 */
export async function registerProduct(
  form: RegistrationForm,
  existingId?: string,
): Promise<{ mode: 'backend'; product: Product; activated: boolean } | { mode: 'local'; product: Product; reason: string }> {
  if (!existingId) {
    const r: RegisterResult = await registerProductBackend(form);
    if (r.ok) {
      await refreshBackendCatalog();
      return { mode: 'backend', product: r.product, activated: r.activated };
    }
    const item = saveRegistered(form);
    return { mode: 'local', product: item.product, reason: r.reason };
  }
  // 수정은 로컬 상품에만 있다. 백엔드 상품 수정(PUT /api/products/{id})은 다음 단계
  const item = saveRegistered(form, existingId);
  return { mode: 'local', product: item.product, reason: '수정은 로컬 저장본에만 적용됩니다' };
}

export function catalogSnapshot(): Product[] {
  if (backendState === 'idle' && typeof window !== 'undefined') {
    backendState = 'loading';
    void refreshBackendCatalog();
  }
  if (snapshotVersion !== version) {
    const seen = new Set(backend.map((p) => p.product_id));
    snapshot = [
      ...backend,
      ...registeredProducts().map((r) => r.product).filter((p) => !seen.has(p.product_id)),
      ...seedProducts,
      ...sampleProducts,
    ];
    snapshotVersion = version;
  }
  return snapshot;
}

/** 주소의 상품 id 를 상품으로. 초안 id 면 초안, 아니면 카탈로그에서 찾는다 */
export function resolveProduct(
  productId: string | null,
  catalog: Product[],
  draft: Product | null = draftProduct(),
): Product | null {
  if (!productId) return null;
  if (productId === DRAFT_PRODUCT_ID) return draft;
  return catalog.find((p) => p.product_id === productId) ?? null;
}
