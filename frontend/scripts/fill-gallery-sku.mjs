/**
 * 갤러리가 빈 상품을 SKU 경로로 채운다.
 *
 * 출력  src/mocks/products.collected.json 의 images
 *
 * 왜 필요한가.
 * 200개 중 45개가 갤러리 없이 남아 있었다. 상세페이지가 "이미지 확보 전" 배지를
 * 띄우고, 갤러리 썸네일을 누르는 행동(media_view)이 그 45개에서는 아예 발생하지
 * 않는다. 콘텐츠 주목도를 재는 화면이 이 상품들만 구조적으로 비게 된다.
 *
 * 왜 지금 되는가.
 * 앞선 수집은 갤러리를 **상품 ID 경로**로만 찾았다.
 *
 *   product/p<상품ID>-av-<NN>-zoom.jpg
 *
 * 그런데 세포라는 **SKU 경로에도** 갤러리를 둔다.
 *
 *   sku/s<SKU>-av-<NN>-zoom.jpg
 *
 * 예전 메모는 이 경로를 "표본 12개 중 2개" 로 보고 접었는데, sku_id 가
 * 181 -> 196 으로 늘어난 지금 다시 재보니 표본 6개 중 4개가 나왔다. 그때는
 * SKU 를 아는 상품이 적어서 표본이 편향됐던 것이다.
 *
 * 주의할 점 두 가지.
 *
 * 1. CDN 이 User-Agent 없는 요청을 403 으로 막는다.
 *    UA 를 안 붙이면 있는 이미지도 403 이 와서 "없음" 으로 기록된다.
 *    실측: 같은 URL 이 UA 없이 403, UA 를 주면 200.
 *
 * 2. 번호가 중간에 빈다.
 *    av-13 다음 av-14/15 가 없고 av-16 부터 다시 있는 상품이 있다.
 *    그래서 "404 나오면 중단" 이 아니라 **연속 3회 404** 를 종료 조건으로 쓴다.
 *
 * 조립으로 못 찾는 갤러리도 있다. `av-1202511121331491790800` 같은 긴 ID 를
 * 쓰는 이미지는 스냅샷의 alternateImages 에만 있어서 여기서는 못 만든다.
 *
 *   node scripts/fill-gallery-sku.mjs              갤러리 빈 상품 전부
 *   node scripts/fill-gallery-sku.mjs --limit 10
 *   node scripts/fill-gallery-sku.mjs --only P458219,P480612
 *   node scripts/fill-gallery-sku.mjs --dry-run    파일에 쓰지 않는다
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const COLLECTED = join(here, '..', 'src', 'mocks', 'products.collected.json');
const CATALOG = join(root, 'batch', 'ingest', 'data', 'products_200.json');

const SKU_CDN = 'https://www.sephora.com/productimages/sku';

/** CDN 이 UA 없는 요청을 403 으로 막는다. 안 붙이면 있는 이미지도 없음이 된다 */
const UA = 'Mozilla/5.0';
/** 연속 이만큼 404 면 그 상품은 끝난 것으로 본다. 번호가 중간에 비기 때문이다 */
const MISS_STREAK = 3;
/** 번호 상한. 실측 최대 27장이라 넉넉히 둔다 */
const MAX_INDEX = 40;
/** CDN 에 부담을 주지 않도록 한 장마다 쉰다 */
const PAUSE_MS = 120;

const args = process.argv.slice(2);
const argOf = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};
const only = argOf('--only')?.split(',').map((s) => s.trim().toUpperCase()) ?? null;
const limit = Number(argOf('--limit') ?? Infinity);
const dryRun = args.includes('--dry-run');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const collected = JSON.parse(readFileSync(COLLECTED, 'utf8'));
const catalog = JSON.parse(readFileSync(CATALOG, 'utf8'));

/** 200개 목록 순서를 지킨다. 목록에 없는 수집분은 건드리지 않는다 */
const targets = catalog
  .map((p) => p.product_id)
  .filter((id) => {
    const entry = collected[id];
    if (!entry?.sku_id) return false;
    if (only) return only.includes(id);
    return !(entry.images?.length > 0);
  })
  .slice(0, limit);

console.log(`대상 ${targets.length}개\n`);

/**
 * 이미지가 있는지 본다.
 *
 * HEAD 를 쓴다. 본문을 받을 이유가 없고, 갤러리 한 장이 수백 KB 라
 * GET 으로 훑으면 45개 × 수십 장에서 수백 MB 를 받게 된다.
 */
async function exists(url) {
  try {
    const res = await fetch(url, { method: 'HEAD', headers: { 'User-Agent': UA } });
    if (res.status === 403) {
      // UA 를 붙였는데도 403 이면 차단이 바뀐 것이다. 없음으로 기록하면 안 된다
      throw new Error('CDN 이 403 을 준다 — 차단 정책이 바뀌었는지 확인 필요');
    }
    return res.status === 200;
  } catch (error) {
    if (String(error.message).includes('403')) throw error;
    return false;
  }
}

async function collectOne(productId) {
  const sku = collected[productId].sku_id;
  const found = [];
  let miss = 0;

  for (let n = 1; n <= MAX_INDEX && miss < MISS_STREAK; n += 1) {
    const url = `${SKU_CDN}/s${sku}-av-${String(n).padStart(2, '0')}-zoom.jpg`;
    if (await exists(url)) {
      found.push(url);
      miss = 0;
    } else {
      miss += 1;
    }
    await sleep(PAUSE_MS);
  }
  return found;
}

let filled = 0;
let empty = 0;
let shots = 0;

for (const [i, productId] of targets.entries()) {
  const head = `[${i + 1}/${targets.length}] ${productId}`;
  let images;
  try {
    images = await collectOne(productId);
  } catch (error) {
    console.log(`${head}  중단 — ${error.message}`);
    break;
  }

  if (images.length === 0) {
    empty += 1;
    console.log(`${head}  없음`);
    continue;
  }

  collected[productId].images = images;
  filled += 1;
  shots += images.length;
  console.log(`${head}  ${images.length}장`);

  // 중단해도 진행분이 남도록 한 건마다 쓴다
  if (!dryRun) {
    writeFileSync(COLLECTED, `${JSON.stringify(collected, null, 2)}\n`, 'utf8');
  }
}

console.log(`\n채움 ${filled} · 없음 ${empty} · 이미지 ${shots}장`);
if (dryRun) console.log('--dry-run 이라 파일에 쓰지 않았다');
else console.log('이어서 node scripts/build-products.ts 를 돌리면 화면 데이터에 반영된다');
