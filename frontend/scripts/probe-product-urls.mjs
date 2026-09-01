/**
 * 사이트맵에 없는 상품의 주소를 후보로 찔러서 찾는다.
 *
 * 사이트맵에 없는 상품이 있다. 단종되었거나 지금 미노출이라 현재 사이트맵에서
 * 빠진 것들인데, 아카이브에는 옛날 스냅샷이 남아 있는 경우가 많다.
 *
 * 주소만 알면 조회는 3초대다. 문제는 주소를 모른다는 것뿐이라, 슬러그 규칙
 * 몇 가지로 후보를 만들어 정확 조회로 찔러 본다. 있으면 CDX 가 행을 준다.
 *
 * 와일드카드 검색을 쓰지 않는 이유는 서버가 60초에서 잘라 504 를 주기 때문이다.
 * 후보 하나당 3초면 열 개를 찔러도 그보다 싸다.
 *
 *   node scripts/probe-product-urls.mjs                 주소 모르는 상품 전부
 *   node scripts/probe-product-urls.mjs --only P394639
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const URL_MAP_PATH = join(here, 'data', 'sephora-product-urls.json');

const args = process.argv.slice(2);
const only = args.includes('--only')
  ? args[args.indexOf('--only') + 1].split(',').map((s) => s.trim().toUpperCase())
  : null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const slugify = (text) =>
  String(text)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // Lancôme -> lancome
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

/**
 * 브랜드 이름이 주소에서 다르게 쓰이는 경우가 있다.
 * 붙여 쓴 이름을 세포라가 띄어 쓰거나, 모브랜드 이름을 붙이기도 한다.
 */
const BRAND_ALIASES = {
  OLEHENRIKSEN: ['ole-henriksen', 'olehenriksen'],
  Wishful: ['wishful-by-huda', 'wishful'],
  'Dr. Dennis Gross Skincare': ['dr-dennis-gross-skincare', 'dr-dennis-gross'],
  'MILK MAKEUP': ['milk-makeup'],
  'SEPHORA COLLECTION': ['sephora-collection', 'sephora-favorites'],
  'IT Cosmetics': ['it-cosmetics'],
};

function candidates(product) {
  const pid = product.product_id;
  const name = slugify(product.product_name);
  const noThe = name.replace(/^the-/, '');
  const brands = BRAND_ALIASES[product.brand_name] ?? [slugify(product.brand_name)];

  const out = [name, noThe];
  for (const brand of brands) {
    out.push(`${brand}-${name}`, `${brand}-${noThe}`);
  }
  // "with ..." 뒤를 떼면 맞는 경우가 있다 (with Squalane, with SPF 30 등)
  const short = name.replace(/-with-.*$/, '');
  if (short !== name) {
    out.push(short);
    for (const brand of brands) out.push(`${brand}-${short}`);
  }

  return [...new Set(out)].map((slug) => `https://www.sephora.com/product/${slug}-${pid}`);
}

/**
 * 아카이브에 이 주소가 있나.
 *
 * 세 가지를 구분해서 돌려준다. 없는 것과 물어보지 못한 것은 다르다.
 * 아카이브가 점검 중이면 200 에 안내 페이지를 주는데, 그걸 "없음" 으로
 * 처리하면 멀쩡한 주소를 없다고 기록하고 다시 찾지 않게 된다.
 *   'hit'   있다
 *   'miss'  물어봤고 없다
 *   'down'  아카이브가 답을 못 준다 — 판단 보류
 */
async function probe(url) {
  const cdx =
    'https://web.archive.org/cdx/search/cdx' +
    `?url=${url.replace(/^https?:\/\//, '')}&limit=2&fl=timestamp`;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45_000);
    const res = await fetch(cdx, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return 'down';

    const body = await res.text();
    if (body.includes('Temporarily Offline') || body.includes('<html')) return 'down';
    return /^\d{14}/m.test(body) ? 'hit' : 'miss';
  } catch {
    return 'down';
  }
}

const map = JSON.parse(readFileSync(URL_MAP_PATH, 'utf8'));
const catalog = JSON.parse(
  readFileSync(join(root, 'batch', 'ingest', 'data', 'products_200.json'), 'utf8'),
);

const targets = catalog.filter((p) =>
  only ? only.includes(p.product_id) : !map[p.product_id],
);

console.log(`주소 모르는 상품 ${targets.length}개를 찔러 본다\n`);

let found = 0;
let unknown = 0;

for (const [index, product] of targets.entries()) {
  const head = `[${index + 1}/${targets.length}] ${product.product_id}`;
  let hit = null;
  let downCount = 0;

  for (const url of candidates(product)) {
    const result = await probe(url);
    if (result === 'hit') {
      hit = url;
      break;
    }
    if (result === 'down') downCount += 1;
    await sleep(600);
  }

  if (hit) {
    map[product.product_id] = hit;
    writeFileSync(URL_MAP_PATH, `${JSON.stringify(map)}\n`);
    found += 1;
    console.log(`${head}  찾음  ${hit.replace('https://www.sephora.com/product/', '')}`);
  } else if (downCount > 0) {
    // 없다고 단정하면 안 된다. 아카이브가 답을 못 준 것뿐이다
    unknown += 1;
    console.log(`${head}  판단 보류 — 아카이브 응답 없음 (${downCount}회)`);
  } else {
    console.log(`${head}  못 찾음  ${product.brand_name} / ${product.product_name}`);
  }
}

console.log(
  `\n찾음 ${found} · 판단 보류 ${unknown} · 없음 ${targets.length - found - unknown} / ${targets.length}`,
);
if (unknown > 0) console.log('보류된 것은 아카이브가 살아난 뒤 다시 돌리면 된다.');
