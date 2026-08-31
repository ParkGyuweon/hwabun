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

/**
 * 목록에서 `count` 개를 시간대가 겹치지 않게 고른다.
 *
 * 최신 것만 연달아 집으면 며칠 사이에 찍힌 스냅샷을 여러 장 받게 되는데,
 * 그것들은 대개 같은 페이지라 같이 실패한다. 실제로 최신 세 장이 모두
 * 껍데기인 상품이 있었다. 시기를 흩어야 다른 렌더링을 만날 수 있다.
 */
function pickSpread(rows, count) {
  if (rows.length <= count) return rows;
  const step = (rows.length - 1) / (count - 1);
  return Array.from({ length: count }, (_, i) => rows[Math.round(i * step)]);
}

/**
 * 상품 ID 로 아카이브에 남은 주소와 시각을 찾는다.
 *
 * 시각까지 한 번에 받아서 가용성 API 호출을 없앴다. 상품당 요청이 3번에서
 * 2번으로 줄고, 아카이브가 흔들릴 기회도 그만큼 줄어든다.
 *
 * 부수입이 하나 있다. 광고 유입 주소에 `skuId=` 가 붙어 있는 경우가 있어서,
 * 스냅샷을 못 읽어도 이미지 URL 은 만들 수 있다.
 */
async function findArchived(productId) {
  const low = productId.toLowerCase();
  const cdx =
    'http://web.archive.org/cdx/search/cdx' +
    `?url=sephora.com/product/*&filter=urlkey:.*${low}.*&limit=40&fl=original,timestamp&collapse=urlkey`;

  /*
   * CDX 가 200 에 빈 본문을 주는 일이 잦다. 실패가 아니라 "결과 없음" 처럼 보여서
   * 그대로 믿으면 아카이브에 멀쩡히 남아 있는 상품을 못 찾았다고 넘긴다.
   * 실제로 이것 때문에 43% 가 주소 못 찾음으로 빠졌다. 비어 있으면 다시 묻는다.
   */
  let rows = [];
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const body = await get(cdx, { tries: 2, timeout: 60_000 });
    rows = (body ?? '')
      .split('\n')
      .map((line) => line.trim().split(/\s+/))
      .filter(([url]) => url?.startsWith('https://www.sephora.com/product/'))
      .map(([url, timestamp]) => ({ url, timestamp }));

    if (rows.length > 0) break;
    await sleep(attempt * 8000);
  }
  if (rows.length === 0) return null;

  // 광고 주소에 딸려 온 skuId 는 그 자체로 쓸모가 있다
  const skuFromUrl = rows.map((row) => row.url.match(/skuId=(\d{6,8})/)?.[1]).find(Boolean) ?? null;

  const usable = rows
    // 시각이 온전하지 않으면 주소를 만들 수 없다. 없는 채로 만들면 아카이브
    // 오류 페이지를 받아 놓고 "내용이 없다" 고 잘못 판단하게 된다
    .filter((row) => /^\d{14}$/.test(row.timestamp ?? ''))
    .filter((row) => !/\b(mini|trial|value-set|travel-size)\b/i.test(row.url))
    .sort((a, b) => Number(b.timestamp) - Number(a.timestamp));

  /*
   * 깔끔한 주소를 먼저 쓰되, 그것만 남은 게 없으면 쿼리스트링이 붙은 주소도 쓴다.
   * 광고 유입 주소로만 아카이브된 상품이 있는데, 가리키는 페이지는 같다.
   * 여기서 버리면 내용이 있는데도 빈칸으로 남는다.
   */
  const clean = usable.filter((row) => !row.url.includes('?'));
  const candidates = clean.length > 0 ? clean : usable;

  if (candidates.length === 0) return null;

  return {
    skuFromUrl,
    /*
     * 후보를 여러 개 준다.
     * 스냅샷마다 상세 JSON 이 담긴 것과 껍데기만 있는 것이 섞여 있다.
     * 하나 실패했다고 그 상품을 포기하면 내용이 있는데도 빈칸으로 남는다.
     * id_ 는 아카이브가 덧붙이는 배너·스크립트 없이 원본 그대로를 준다.
     */
    snapshots: pickSpread(candidates, 6).map(
      (row) => `https://web.archive.org/web/${row.timestamp}id_/${row.url}`,
    ),
  };
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
  // 페이지마다 제목을 <b> 로도 <strong> 으로도 감싼다. 둘 다 받는다
  const re = /<(b|strong)>\s*([^<:]{3,60}?)\s*:\s*(?:<br\s*\/?>)?\s*<\/\1>/gi;
  let match;
  while ((match = re.exec(raw)) !== null) {
    // start 는 다음 제목이 시작하는 자리. 여기까지가 앞 절의 본문이다.
    // lastIndex 로 자르면 다음 제목 글자가 앞 절 끝에 딸려 들어간다.
    parts.push({ title: match[2], start: match.index, from: re.lastIndex });
  }
  if (parts.length === 0) return { what_it_is: stripTags(raw) || null };

  const out = {};
  parts.forEach((part, index) => {
    const body = raw.slice(part.from, parts[index + 1]?.start ?? raw.length);
    /*
     * 제목이 본문 안에 한 번 더 들어 있는 페이지가 있다.
     * <p><strong>What it is: </strong>본문 처럼 태그 밖에 콜론이 남으면
     * "What it is: 본문" 이 그대로 저장된다. 앞머리에서만 걷어낸다.
     */
    const title = part.title.trim().toLowerCase();
    const text = stripTags(body).replace(/^([^:\n]{3,60}):\s*/, (whole, head) =>
      head.trim().toLowerCase() === title ? '' : whole,
    );
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
  /**
   * longDescription 이 여러 개 나온다. 브랜드 소개가 먼저 오는 페이지도 있고
   * 상품 설명 하나만 있는 페이지도 있다. 순서로 고르면 페이지마다 틀린다.
   * "What it is" 같은 절 제목이 들어 있는 쪽이 상품 설명이다.
   */
  const candidates = [];
  let cursor = 0;
  for (let i = 0; i < 5; i += 1) {
    const found = readJsonString(html, 'longDescription', cursor);
    if (found.end < 0) break;
    if (found.value) candidates.push(found.value);
    cursor = found.end + 1;
  }

  const looksLikeProduct = (text) => /what it is|highlighted ingredients|suggested usage/i.test(text);
  const productDescription =
    candidates.find(looksLikeProduct) ??
    candidates.sort((a, b) => b.length - a.length)[0] ??
    null;

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
    /*
     * 거리를 제한한다. brandId 뒤 아무 description 이나 집으면 4만 자 떨어진
     * 사이트 공통 안내문("Shop the best makeup now at Sephora...")을 브랜드
     * 소개로 저장하게 된다. 브랜드 블록의 description 은 brandId 바로 뒤에 온다.
     */
    const near = brand.end > 0 && brand.end - brandAt < 3000;
    const isBoilerplate = /Beauty Insider|earn points with every purchase|Shop the best/i.test(text);
    if (near && !isBoilerplate && text.length > 40) description.brand_story = text;
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
let done = 0;

async function collectOne(productId) {
  const found = await findArchived(productId);
  if (!found) return { productId, reason: '주소 못 찾음' };

  let parsed = { skuId: null, description: null };

  for (const snapshot of found.snapshots) {
    const html = await get(snapshot, { tries: 2 });
    // 상세 JSON 이 없는 스냅샷은 껍데기다. 다음 후보로 넘어간다
    if (!html || !html.includes('longDescription')) continue;

    parsed = extract(html);
    if (parsed.description) break;
  }

  // 스냅샷을 못 읽어도 광고 주소에서 얻은 sku 는 살린다
  const skuId = parsed.skuId ?? found.skuFromUrl;
  if (!skuId && !parsed.description) return { productId, reason: '스냅샷 못 읽음' };

  return { productId, skuId, description: parsed.description };
}

/**
 * 동시에 몇 건씩 처리한다.
 *
 * 한 건씩 돌리면 194개에 열여섯 시간이 걸린다. 대부분이 아카이브 응답을
 * 기다리는 시간이라 동시에 보내면 그만큼 줄어든다.
 * 다만 아카이브는 공용 자원이라 무한정 늘리지 않는다.
 */
const CONCURRENCY = 4;

const queue = [...targets];

async function worker() {
  while (queue.length > 0) {
    const productId = queue.shift();
    if (!productId) return;

    const result = await collectOne(productId);
    done += 1;
    const head = `[${done}/${targets.length}] ${productId}`;

    if (result.reason) {
      console.log(`${head}  ${result.reason}`);
      failed += 1;
    } else {
      const entry = collected[productId] ?? {
        sku_id: null,
        image_url: null,
        images: [],
        variants: [],
        description: null,
      };

      if (result.skuId && !entry.sku_id) entry.sku_id = result.skuId;
      if (result.description) {
        entry.description = { ...(entry.description ?? {}), ...result.description };
      }
      collected[productId] = entry;

      // 중단돼도 진행분이 남도록 한 건마다 저장한다
      writeFileSync(COLLECTED, `${JSON.stringify(collected, null, 2)}\n`);

      const blocks = result.description ? Object.keys(result.description).length : 0;
      console.log(`${head}  sku ${entry.sku_id ?? '없음'} · 블록 ${blocks}개`);
      filled += 1;
    }

    await sleep(PAUSE_MS);
  }
}

await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));

console.log(`\n채움 ${filled} · 실패 ${failed}`);
console.log('이어서 node scripts/build-products.ts 를 돌리면 화면 데이터에 반영된다.');
