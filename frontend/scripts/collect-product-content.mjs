/**
 * 상품 상세 콘텐츠를 아카이브 스냅샷에서 수집한다.
 *
 * 출력  src/mocks/products.collected.json  (sku_id / description 를 채운다)
 *
 * 왜 필요한가.
 * 상세페이지의 콘텐츠 블록이 200개 중 1~13% 에만 있었다. 성분·임상 근거·브랜드
 * 소개가 비어 있으면 `section_dwell` 은 "빈 아코디언을 열어봤다" 를 재는 것이 되고,
 * 대시보드의 콘텐츠 주목도 화면이 표본 2~25개로 만들어진다. 이 프로젝트가 파는 것이
 * "성분을 보고 샀나 리뷰를 보고 샀나" 라서, 콘텐츠가 없으면 그 주장을 못 한다.
 *
 * 어디서 가져오나.
 * 세포라는 실시간 접근을 막는다. 공개 아카이브(web.archive.org) 스냅샷을 쓴다.
 * 스냅샷 HTML 안에 상품 JSON 이 그대로 들어 있어서 파싱만 하면 된다.
 * 봇 차단을 우회하지 않는다 — 아카이브가 공개한 것을 읽을 뿐이다.
 *
 * 한 스냅샷에서 세 가지가 같이 나온다.
 *   skuId            이미지 URL 을 만드는 열쇠 (sku/s{id}-main-zoom.jpg)
 *   longDescription  what_it_is / 성분 / 임상 결과 등 상세 블록
 *   brand.description 브랜드 소개
 *
 * 아카이브가 자주 느려지고 간헐적으로 offline 을 뱉는다. 그래서
 *   - 한 건 끝날 때마다 파일에 쓴다 (중단해도 진행분이 남는다)
 *   - 이미 채워진 상품은 건너뛴다 (다시 돌리면 이어서 한다)
 *   - 실패는 기록만 하고 넘어간다
 *
 *   node scripts/collect-product-content.mjs            남은 것 전부
 *   node scripts/collect-product-content.mjs --limit 20 20개만
 *   node scripts/collect-product-content.mjs --only P458219,P426340
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const COLLECTED = join(here, '..', 'src', 'mocks', 'products.collected.json');

const UA = 'Mozilla/5.0';
/** 아카이브에 부담을 주지 않도록 한 건마다 쉰다 */
const PAUSE_MS = 1500;

const args = process.argv.slice(2);
const argOf = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};
const limit = Number(argOf('--limit')) || Infinity;
const only = argOf('--only')?.split(',').map((s) => s.trim().toUpperCase()) ?? null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 아카이브가 흔들려서 한 번 실패했다고 포기하지 않는다 */
async function get(url, { tries = 3, timeout = 90_000 } = {}) {
  for (let i = 1; i <= tries; i += 1) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      const res = await fetch(url, { headers: { 'User-Agent': UA }, signal: controller.signal });
      clearTimeout(timer);
      if (res.ok) {
        const text = await res.text();
        // 아카이브가 점검 중이면 200 에 안내 페이지를 준다
        if (!text.includes('Temporarily Offline')) return text;
      }
    } catch {
      /* 재시도 */
    }
    await sleep(i * 5000);
  }
  return null;
}

/** 상품 ID 로 세포라 상품 URL(슬러그) 을 찾는다 */
async function findProductUrl(productId) {
  const low = productId.toLowerCase();
  const cdx =
    'http://web.archive.org/cdx/search/cdx' +
    `?url=sephora.com/product/*&filter=urlkey:.*${low}.*&limit=25&fl=original&collapse=urlkey`;

  const body = await get(cdx, { timeout: 60_000 });
  if (!body) return null;

  return (
    body
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('https://www.sephora.com/product/'))
      // 쿼리스트링이 붙은 것과 미니·트라이얼 사이즈는 본품이 아니다
      .filter((line) => !line.includes('&') && !line.includes('?'))
      .filter((line) => !/\b(mini|trial|value-set|travel-size)\b/i.test(line))[0] ?? null
  );
}

async function findSnapshot(productUrl) {
  const body = await get(
    `https://archive.org/wayback/available?url=${productUrl.replace(/^https:\/\//, '')}`,
    { timeout: 45_000 },
  );
  if (!body) return null;
  try {
    return JSON.parse(body).archived_snapshots?.closest?.url ?? null;
  } catch {
    return null;
  }
}

/**
 * HTML 안에 박힌 JSON 문자열 값을 읽는다.
 *
 * 정규식으로 따옴표까지 긁으면 본문에 든 escape 된 따옴표에서 잘린다.
 * 여는 따옴표부터 한 글자씩 훑어 escape 를 존중하며 끝을 찾은 뒤 JSON.parse 한다.
 */
function readJsonString(html, key, fromIndex = 0) {
  const at = html.indexOf(`"${key}":"`, fromIndex);
  if (at < 0) return { value: null, end: -1 };

  const start = at + key.length + 4; // "key":" 다음
  let i = start;
  while (i < html.length) {
    const ch = html[i];
    if (ch === '\\') {
      i += 2;
      continue;
    }
    if (ch === '"') break;
    i += 1;
  }

  try {
    return { value: JSON.parse(`"${html.slice(start, i)}"`), end: i };
  } catch {
    return { value: null, end: i };
  }
}

const stripTags = (s) =>
  s
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\t+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+\n/g, '\n')
    .trim();

/** 상세 설명은 `<b>제목:</b> 내용` 이 이어 붙은 한 덩어리다. 제목으로 잘라 나눈다 */
const HEADINGS = [
  [/what it is/i, 'what_it_is'],
  [/skin type/i, 'skin_type'],
  [/skincare concerns|hair type|concerns/i, 'concerns_text'],
  [/highlighted ingredients/i, 'highlighted_ingredients'],
  [/ingredient callouts/i, 'ingredient_callouts'],
  [/what else you need to know/i, 'what_else'],
  [/clinical results|research results/i, 'clinical_results'],
];

function parseLongDescription(raw) {
  if (!raw) return {};

  const parts = [];
  const re = /<b>\s*([^<:]{3,60}?)\s*:\s*(?:<br\s*\/?>)?\s*<\/b>/gi;
  let match;
  while ((match = re.exec(raw)) !== null) {
    // start 는 다음 제목이 시작하는 자리. 여기까지가 앞 절의 본문이다.
    // lastIndex 로 자르면 다음 제목 글자가 앞 절 끝에 딸려 들어간다.
    parts.push({ title: match[1], start: match.index, from: re.lastIndex });
  }
  if (parts.length === 0) return { what_it_is: stripTags(raw) || null };

  const out = {};
  parts.forEach((part, index) => {
    const body = raw.slice(part.from, parts[index + 1]?.start ?? raw.length);
    const text = stripTags(body);
    if (!text) return;

    const key = HEADINGS.find(([pattern]) => pattern.test(part.title))?.[1];
    if (!key || out[key]) return;

    if (key === 'highlighted_ingredients') {
      // "- 성분: 설명" 이 줄마다 하나씩 온다
      const items = text
        .split('\n')
        .map((line) => line.replace(/^[-•]\s*/, '').trim())
        .filter((line) => line.length > 3);
      if (items.length) out[key] = items;
      return;
    }
    out[key] = text;
  });

  return out;
}

function extract(html) {
  // longDescription 은 브랜드 것이 먼저 나오고 상품 것이 뒤에 온다
  const first = readJsonString(html, 'longDescription');
  const second = readJsonString(html, 'longDescription', first.end + 1);
  const productDescription = second.value ?? first.value;

  const description = parseLongDescription(productDescription);

  const usage = readJsonString(html, 'suggestedUsage').value;
  if (usage) {
    // 본문이 "Suggested Usage:" 로 시작하는 경우가 있어 제목을 걷어낸다
    const text = stripTags(usage).replace(/^suggested usage\s*:?\s*/i, '').trim();
    if (text) description.suggested_usage = text;
  }

  /**
   * 브랜드 소개.
   * 브랜드 블록의 description 이라 `"brandId":"6041", ... "description":"..."` 순서로
   * 나온다. brandId 이후 첫 description 을 집는다.
   */
  const brandAt = html.indexOf('"brandId":"');
  if (brandAt > 0) {
    const brand = readJsonString(html, 'description', brandAt);
    const text = brand.value ? stripTags(brand.value) : '';
    if (text.length > 40) description.brand_story = text;
  }

  const skuMatch =
    html.match(/"skuId":"?(\d{6,8})"?/) ?? html.match(/productimages\/sku\/s(\d{6,8})/);

  return {
    skuId: skuMatch?.[1] ?? null,
    description: Object.keys(description).length ? description : null,
  };
}

// ---------------------------------------------------------------- 실행

/**
 * 파서만 확인하는 경로.
 * 아카이브가 자주 흔들려서, 네트워크 없이 저장해 둔 스냅샷으로 추출 결과를 볼 수 있어야
 * 파싱 문제와 수집 문제를 구분할 수 있다.
 *
 *   node scripts/collect-product-content.mjs --from-file snap.html
 */
const fromFile = argOf('--from-file');
if (fromFile) {
  const { skuId, description } = extract(readFileSync(fromFile, 'utf8'));
  console.log('sku:', skuId);
  for (const [key, value] of Object.entries(description ?? {})) {
    const shown = Array.isArray(value)
      ? `${value.length}개: ${value[0].slice(0, 60)}`
      : String(value).replace(/\n/g, ' | ').slice(0, 100);
    console.log(`  ${key.padEnd(24)} ${shown}`);
  }
  process.exit(0);
}

const collected = JSON.parse(readFileSync(COLLECTED, 'utf8'));

const catalog = JSON.parse(
  readFileSync(join(root, 'batch', 'ingest', 'data', 'products_200.json'), 'utf8'),
);

const isBlank = (entry) =>
  !entry ||
  !entry.description ||
  Object.keys(entry.description).length === 0 ||
  !entry.sku_id ||
  !entry.image_url;

const targets = catalog
  .map((p) => p.product_id)
  .filter((id) => (only ? only.includes(id) : isBlank(collected[id])))
  .slice(0, limit);

console.log(`대상 ${targets.length}개\n`);

let filled = 0;
let failed = 0;

for (const [index, productId] of targets.entries()) {
  const head = `[${index + 1}/${targets.length}] ${productId}`;

  const productUrl = await findProductUrl(productId);
  if (!productUrl) {
    console.log(`${head}  주소 못 찾음`);
    failed += 1;
    await sleep(PAUSE_MS);
    continue;
  }

  const snapshot = await findSnapshot(productUrl);
  if (!snapshot) {
    console.log(`${head}  스냅샷 없음`);
    failed += 1;
    await sleep(PAUSE_MS);
    continue;
  }

  const html = await get(snapshot);
  if (!html) {
    console.log(`${head}  스냅샷 못 읽음`);
    failed += 1;
    await sleep(PAUSE_MS);
    continue;
  }

  const { skuId, description } = extract(html);
  const entry = collected[productId] ?? {
    sku_id: null,
    image_url: null,
    images: [],
    variants: [],
    description: null,
  };

  if (skuId && !entry.sku_id) entry.sku_id = skuId;
  if (description) entry.description = { ...(entry.description ?? {}), ...description };

  collected[productId] = entry;

  // 중단돼도 진행분이 남도록 한 건마다 저장한다
  writeFileSync(COLLECTED, `${JSON.stringify(collected, null, 2)}\n`);

  const blocks = description ? Object.keys(description).length : 0;
  console.log(`${head}  sku ${entry.sku_id ?? '없음'} · 블록 ${blocks}개`);
  if (blocks > 0 || skuId) filled += 1;
  else failed += 1;

  await sleep(PAUSE_MS);
}

console.log(`\n채움 ${filled} · 실패 ${failed}`);
console.log('이어서 node scripts/build-products.ts 를 돌리면 화면 데이터에 반영된다.');
