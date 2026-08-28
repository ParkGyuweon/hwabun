import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';

/**
 * 세포라 이미지 CDN 로컬 캐시.
 *
 * 상품 이미지를 세포라 CDN 에서 그대로 받아 쓰는데, 한 장에 수 초씩 걸린다.
 * 행동 로그를 재는 페이지에서 이건 그냥 느린 게 아니라 **데이터가 오염되는 문제**다.
 * 이미지가 늦게 뜨면 그동안 화면에 머문 시간이 전부 체류 시간으로 잡힌다.
 *
 * 그래서 dev 서버가 한 번만 원본을 받아 디스크에 저장하고, 그 다음부터는 로컬에서 준다.
 * 브라우저 캐시만으로는 부족하다. 캐시를 비우거나 다른 브라우저로 실험하면
 * 다시 처음부터 받아야 해서, 실험 조건이 사람마다 달라진다.
 *
 * 캐시 폴더는 커밋하지 않는다 (`.gitignore`). 없으면 요청이 올 때 알아서 채워지고,
 * 실험 전에 미리 다 받아두려면 `npm run warm-images` 를 쓴다.
 */

const UPSTREAM = 'https://www.sephora.com/productimages';

/** 이 경로로 온 요청만 가로챈다 */
export const CDN_PREFIX = '/cdn';

/**
 * 허용하는 하위 경로.
 * 대표 이미지는 SKU 기준, 갤러리 이미지는 상품 ID 기준으로 경로가 갈린다.
 * 임의 경로를 프록시하지 않도록 화이트리스트로 둔다.
 */
const ALLOWED_DIRS = new Set(['sku', 'product']);

const here = dirname(fileURLToPath(import.meta.url));
export const CACHE_DIR = join(here, '..', '.image-cache');

/** 경로 조작을 막는다. 세포라 이미지 파일명은 이 문자들만 쓴다 */
const SAFE_FILE = /^[A-Za-z0-9+._-]+\.(jpg|jpeg|png)$/;

/** 실험 중 다시 받아오는 일이 없도록 최대한 길게 잡는다 */
const ONE_YEAR = 60 * 60 * 24 * 365;

function cachePath(file: string, query: string): string {
  // 같은 파일이라도 폭이 다르면 다른 이미지라 따로 저장한다
  const suffix = query === '' ? 'orig' : createHash('sha1').update(query).digest('hex').slice(0, 12);
  return join(CACHE_DIR, `${file.replace(/[^A-Za-z0-9._-]/g, '_')}__${suffix}.jpg`);
}

/** `sku/s123-main-zoom.jpg` 를 디렉터리와 파일명으로 나눈다 */
export function splitCdnPath(path: string): { dir: string; file: string } | null {
  const slash = path.indexOf('/');
  if (slash <= 0) return null;

  const dir = path.slice(0, slash);
  const file = path.slice(slash + 1);
  if (!ALLOWED_DIRS.has(dir) || !SAFE_FILE.test(file)) return null;

  return { dir, file };
}

/**
 * 원본을 받아 디스크에 저장한다. 이미 있으면 그대로 쓴다.
 * @returns 저장된 파일 내용, 실패하면 null
 */
export async function fetchToCache(path: string, query: string): Promise<Buffer | null> {
  const target = cachePath(path, query);
  if (existsSync(target)) return readFileSync(target);

  const url = `${UPSTREAM}/${path}${query === '' ? '' : `?${query}`}`;

  try {
    const response = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    if (!response.ok) return null;

    const body = Buffer.from(await response.arrayBuffer());
    // 404 는 215 바이트짜리 안내 문서로 오므로 크기로 한 번 더 거른다
    if (body.byteLength < 1000) return null;

    mkdirSync(CACHE_DIR, { recursive: true });
    writeFileSync(target, body);
    return body;
  } catch {
    return null;
  }
}

export function imageCache(): Plugin {
  return {
    name: 'sephora-image-cache',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const raw = req.url ?? '';
        if (!raw.startsWith(`${CDN_PREFIX}/`)) return next();

        const [rawPath, query = ''] = raw.slice(`${CDN_PREFIX}/`.length).split('?');
        const parts = splitCdnPath(decodeURIComponent(rawPath));

        if (parts === null) {
          res.statusCode = 400;
          res.end('bad image path');
          return;
        }

        const body = await fetchToCache(`${parts.dir}/${parts.file}`, query);

        if (body === null) {
          res.statusCode = 404;
          res.end('not found');
          return;
        }

        res.setHeader('Content-Type', 'image/jpeg');
        res.setHeader('Cache-Control', `public, max-age=${ONE_YEAR}, immutable`);
        res.end(body);
      });
    },
  };
}
