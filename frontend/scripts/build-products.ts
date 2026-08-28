/**
 * 상품 목 데이터를 만든다.
 *
 * 입력
 *   batch/ingest/data/products_200.json  데이터 담당자가 정제한 상품 200개
 *   scratchpad/skus.json                 아카이브에서 찾아낸 세포라 SKU (이미지 URL 조립 키)
 *   src/mocks/products.collected.json    손으로 모은 이미지·옵션·설명 (상품 ID 기준)
 *
 * 출력
 *   src/mocks/products.sample.json
 *
 * 수집 자산을 **출력 파일과 분리해 둔 이유**가 있다.
 * 상품 200개 목록은 데이터 담당자가 정하고 바뀔 수 있는데, 자산을 출력 파일에만
 * 두면 목록에서 빠진 상품의 수집 결과가 그대로 사라진다.
 * 실제로 P450271(단종 점보)과 P443349(먹는 보충제)가 200개에서 제외됐다.
 * 자산을 따로 두면 나중에 목록에 다시 들어와도 알아서 붙는다.
 *
 *   npx tsx scripts/build-products.ts <skus.json 경로>
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');

const CDN = 'https://www.sephora.com/productimages/sku';

interface RawProduct {
  rank: number;
  product_id: string;
  product_name: string;
  brand_name: string;
  loves_count: number | null;
  rating: number | null;
  reviews: number | null;
  size: string | null;
  ingredients: string[] | null;
  price_usd: number;
  limited_edition: number;
  new: number;
  online_only: number;
  sephora_exclusive: number;
  highlights: string[] | null;
  primary_category: string | null;
  secondary_category: string | null;
  tertiary_category: string | null;
}

const raw = JSON.parse(
  readFileSync(join(root, 'batch', 'ingest', 'data', 'products_200.json'), 'utf8'),
) as RawProduct[];

const skuPath = process.argv[2];
const skus: Record<string, { sku: string | null }> = skuPath
  ? JSON.parse(readFileSync(skuPath, 'utf8'))
  : {};

const mockPath = join(here, '..', 'src', 'mocks', 'products.sample.json');

interface Collected {
  sku_id: string | null;
  image_url: string | null;
  images: string[];
  variants: unknown[];
  description: unknown;
}

const collected = JSON.parse(
  readFileSync(join(here, '..', 'src', 'mocks', 'products.collected.json'), 'utf8'),
) as Record<string, Collected>;

/** "Best for Dry, Combo, Normal Skin" → ['dry','combination','normal'] */
const SKIN_WORD: Record<string, string> = {
  dry: 'dry',
  oily: 'oily',
  normal: 'normal',
  combo: 'combination',
  combination: 'combination',
};

function deriveSkinTypes(highlights: string[]): string[] {
  const line = highlights.find((h) => /^Best for/i.test(h));
  if (!line) return [];

  const found = line
    .replace(/^Best for\s*/i, '')
    .replace(/\bskin\b/i, '')
    .split(/[,/]| and /i)
    .map((part) => SKIN_WORD[part.trim().toLowerCase()])
    .filter((v): v is string => Boolean(v));

  return [...new Set(found)];
}

/** "Good for: Dryness" → 'Dryness' */
function deriveConcerns(highlights: string[]): string[] {
  const found = highlights
    .filter((h) => /^Good for:/i.test(h))
    .map((h) => h.replace(/^Good for:\s*/i, '').trim())
    .filter(Boolean);

  return [...new Set(found)];
}

/**
 * 화면 배지.
 * 원본 플래그를 그대로 옮긴다. 할인율은 만들지 않는다 —
 * `sale_price_usd` 가 200개 중 198개 비어 있어서 근거가 없다.
 */
function deriveBadges(p: RawProduct): string[] {
  const badges: string[] = [];
  if (p.new) badges.push('new');
  if (p.limited_edition) badges.push('limited');
  if (p.sephora_exclusive) badges.push('exclusive');
  if (p.online_only) badges.push('online_only');
  return badges;
}

/** 계층 카테고리를 배열로. 같은 값이 반복되면 접는다 */
function deriveCategory(p: RawProduct): string[] {
  const parts = [p.primary_category, p.secondary_category, p.tertiary_category];
  const out: string[] = [];
  for (const part of parts) {
    if (part && out[out.length - 1] !== part) out.push(part);
  }
  return out;
}

let withImage = 0;
let keptRich = 0;

const products = raw.map((p) => {
  const highlights = p.highlights ?? [];
  const prev = collected[p.product_id];

  // 이미 수집해 둔 상품이면 그 SKU 를 그대로 쓴다
  const skuId = prev?.sku_id ?? skus[p.product_id]?.sku ?? null;
  const imageUrl = prev?.image_url ?? (skuId ? `${CDN}/s${skuId}-main-zoom.jpg` : null);

  if (imageUrl) withImage += 1;
  if (prev?.images?.length) keptRich += 1;

  return {
    product_id: p.product_id,
    product_name: p.product_name,
    brand_name: p.brand_name,
    category: deriveCategory(p),

    image_url: imageUrl,
    sku_id: skuId,
    // 수집해 둔 상세 이미지·옵션·설명은 절대 덮어쓰지 않는다
    images: prev?.images ?? [],
    variants: prev?.variants ?? [],
    description: prev?.description ?? null,

    price_usd: p.price_usd,
    size: p.size,
    rating: p.rating === null ? null : Math.round(p.rating * 100) / 100,
    review_count: p.reviews,

    // 목록 화면용
    rank: p.rank,
    loves_count: p.loves_count,
    badges: deriveBadges(p),

    // "Good for:" 는 concerns 로 따로 빼므로 배지 목록에서 제거한다
    highlights: highlights.filter((h) => !/^Good for:/i.test(h)),
    ingredients: p.ingredients ?? [],
    suitable_skin_types: deriveSkinTypes(highlights),
    skincare_concerns: deriveConcerns(highlights),
  };
});

writeFileSync(mockPath, `${JSON.stringify(products, null, 2)}\n`, 'utf8');

const skinTyped = products.filter((p) => p.suitable_skin_types.length).length;
const concerned = products.filter((p) => p.skincare_concerns.length).length;

console.log(`상품 ${products.length}개 작성 → src/mocks/products.sample.json`);
console.log(`  대표 이미지 확보   ${withImage}`);
console.log(`  상세까지 수집된 것 ${keptRich}`);
console.log(`  피부타입 파생      ${skinTyped}`);
console.log(`  고민 파생          ${concerned}`);

const dropped = Object.keys(collected).filter((id) => !raw.some((p) => p.product_id === id));
if (dropped.length) {
  console.log('');
  console.log(`  200개 목록에 없어 제외된 수집 상품: ${dropped.join(', ')}`);
  console.log('  (자산은 products.collected.json 에 남아 있어 목록에 다시 들어오면 붙는다)');
}
