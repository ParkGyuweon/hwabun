/**
 * 세포라 상품 주소표를 만든다.
 *
 * 출력  scripts/data/sephora-product-urls.json   { "P123456": "https://..." }
 *
 * 왜 필요한가.
 * 아카이브에서 상품 하나를 찾을 때 주소를 모르면 `sephora.com/product/*` 전체
 * 색인을 정규식으로 훑게 하는 수밖에 없다. 그 쿼리는 **서버가 60초에서 잘라
 * 504 를 준다** — 클라이언트 타임아웃을 아무리 늘려도 소용없다.
 * 실측으로 와일드카드 60초 타임아웃, 정확한 주소 3.4초였다.
 *
 * 같은 상품이 어떤 때는 찾아지고 어떤 때는 안 찾아지던 것이 이 때문이다.
 * 색인에서 일찍 걸리면 성공하고 늦게 걸리면 잘린다. 재시도해도 똑같이 비싼
 * 쿼리를 다시 던지는 거라 잘 낫지 않는다.
 *
 * 세포라 사이트맵이 아카이브에 남아 있어서, 거기서 주소를 한 번에 받아 둔다.
 * 상품 주소는 끝이 항상 상품 ID(-P123456)라 ID 로 색인할 수 있다.
 *
 * 주의: 사이트맵 스냅샷은 대부분 오류 페이지(1KB 안팎)다. 실제 내용이 담긴
 * 것만 골라야 해서 응답 크기가 큰 스냅샷을 먼저 시도한다.
 *
 *   node scripts/build-product-urls.mjs
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(here, 'data');
const OUT = join(OUT_DIR, 'sephora-product-urls.json');

/** 지역별로 상품 구성이 조금씩 달라서 합치면 커버리지가 올라간다 */
const SITEMAPS = [
  'products-sitemap.xml',
  'products-sitemap_en-CA.xml',
  'products-sitemap_fr-CA.xml',
];

/** 이보다 작으면 사이트맵이 아니라 오류 페이지다 */
const MIN_USEFUL_BYTES = 100_000;

const UA = 'Mozilla/5.0';

async function get(url, timeout = 180_000) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const res = await fetch(url, { headers: { 'User-Agent': UA }, signal: controller.signal });
    clearTimeout(timer);
    return res.ok ? await res.text() : null;
  } catch {
    return null;
  }
}

/** 응답이 큰 스냅샷부터 시도한다. 작은 것은 오류 페이지다 */
async function snapshotsFor(name) {
  const cdx =
    'https://web.archive.org/cdx/search/cdx' +
    `?url=sephora.com/sitemaps/${name}&fl=timestamp,statuscode,length&limit=40`;

  const body = await get(cdx, 90_000);
  if (!body) return [];

  return body
    .split('\n')
    .map((line) => line.trim().split(/\s+/))
    .filter(([ts, status, length]) => /^\d{14}$/.test(ts ?? '') && status === '200' && Number(length) > 5_000)
    .sort((a, b) => Number(b[2]) - Number(a[2]))
    .map(([ts]) => ts);
}

const map = {};
try {
  Object.assign(map, JSON.parse(readFileSync(OUT, 'utf8')));
  console.log(`기존 주소 ${Object.keys(map).length}개를 불러왔다`);
} catch {
  /* 처음 만드는 중 */
}

for (const name of SITEMAPS) {
  const timestamps = await snapshotsFor(name);
  if (timestamps.length === 0) {
    console.log(`${name}  쓸 만한 스냅샷 없음`);
    continue;
  }

  let added = 0;
  for (const ts of timestamps.slice(0, 3)) {
    const xml = await get(
      `https://web.archive.org/web/${ts}id_/https://www.sephora.com/sitemaps/${name}`,
    );
    if (!xml || xml.length < MIN_USEFUL_BYTES) continue;

    for (const match of xml.matchAll(/<loc>([^<]*)<\/loc>/g)) {
      const url = match[1].split('?')[0].replace(/^http:/, 'https:');
      const id = url.match(/-(P\d+)$/);
      if (id && !map[id[1]]) {
        map[id[1]] = url;
        added += 1;
      }
    }
    break; // 내용이 있는 스냅샷 하나면 충분하다
  }
  console.log(`${name}  +${added}개`);
}

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(OUT, `${JSON.stringify(map)}\n`);

console.log(`\n상품 주소 ${Object.keys(map).length}개 → scripts/data/sephora-product-urls.json`);

// 우리 카탈로그가 얼마나 덮이는지 같이 보여준다
try {
  const catalog = JSON.parse(
    readFileSync(join(here, '..', '..', 'batch', 'ingest', 'data', 'products_200.json'), 'utf8'),
  );
  const hit = catalog.filter((p) => map[p.product_id]).length;
  console.log(`카탈로그 ${catalog.length}개 중 ${hit}개의 주소를 안다`);
} catch {
  /* 카탈로그가 없으면 넘어간다 */
}
