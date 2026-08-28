/**
 * 상품 이미지를 미리 전부 받아 디스크 캐시에 채운다.
 *
 * 실험 전에 한 번 돌려두면 그 뒤로는 이미지가 즉시 뜬다.
 * 안 돌려도 화면을 열 때 알아서 채워지지만, 첫 방문자만 느린 화면을 보게 되고
 * 그 사람의 체류 시간 로그가 다른 사람과 달라진다.
 *
 *   npm run warm-images
 */
import { readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CACHE_DIR, fetchToCache } from '../plugins/image-cache.ts';
// 화면과 같은 폭을 받아야 캐시가 실제 요청 주소와 맞는다
import {
  IMAGE_WIDTH_CARD,
  IMAGE_WIDTH_MAIN,
  IMAGE_WIDTH_SWATCH,
  IMAGE_WIDTH_THUMB,
} from '../src/lib/image-widths.ts';

const CDN_ORIGIN = 'https://www.sephora.com/productimages/sku/';

const here = dirname(fileURLToPath(import.meta.url));
const products = JSON.parse(
  readFileSync(join(here, '..', 'src', 'mocks', 'products.sample.json'), 'utf8'),
) as Array<{
  image_url: string | null;
  images: string[];
  variants: Array<{ image_url: string; swatch_url: string | null }>;
}>;

/** 화면에서 실제로 쓰이는 (파일, 폭) 조합만 모은다 */
const wanted = new Set<string>();

function want(url: string | null, ...widths: number[]) {
  if (!url || !url.startsWith(CDN_ORIGIN)) return;
  const file = url.slice(CDN_ORIGIN.length);
  for (const width of widths) wanted.add(`${file}|imwidth=${width}`);
}

for (const product of products) {
  // 대표 이미지는 갤러리 메인·썸네일에 쓰이고, 추천 카드에도 실린다
  want(product.image_url, IMAGE_WIDTH_MAIN, IMAGE_WIDTH_THUMB, IMAGE_WIDTH_CARD);

  for (const image of product.images) want(image, IMAGE_WIDTH_MAIN, IMAGE_WIDTH_THUMB);

  for (const variant of product.variants) {
    // 옵션을 고르면 그 이미지가 갤러리 메인 자리로 올라온다
    want(variant.image_url, IMAGE_WIDTH_MAIN, IMAGE_WIDTH_THUMB);
    want(variant.swatch_url, IMAGE_WIDTH_SWATCH);
  }
}

const jobs = [...wanted];
console.log(`이미지 ${jobs.length}장 받는 중... (${CACHE_DIR})`);

let done = 0;
let failed = 0;

/** 한 번에 너무 많이 열면 CDN 이 끊는다 */
const CONCURRENCY = 6;

async function worker() {
  for (;;) {
    const job = jobs.shift();
    if (job === undefined) return;

    const [file, query] = job.split('|');
    const body = await fetchToCache(file, query);

    if (body === null) {
      failed += 1;
      console.warn(`  실패 ${file}?${query}`);
    } else {
      done += 1;
      if (done % 25 === 0) console.log(`  ${done}장`);
    }
  }
}

await Promise.all(Array.from({ length: CONCURRENCY }, worker));

let bytes = 0;
try {
  const { readdirSync } = await import('node:fs');
  for (const name of readdirSync(CACHE_DIR)) bytes += statSync(join(CACHE_DIR, name)).size;
} catch {
  // 캐시 폴더가 없으면 크기 보고를 건너뛴다
}

console.log(`\n완료: ${done}장 · 실패 ${failed}장 · 캐시 ${(bytes / 1024 / 1024).toFixed(1)}MB`);
