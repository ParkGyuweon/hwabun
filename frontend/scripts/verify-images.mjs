/**
 * 수집해 둔 이미지 주소가 아직 살아 있는지 확인하고, 죽은 것을 걷어낸다.
 *
 * 출력  src/mocks/products.collected.json 의 images / image_url
 *
 * 왜 필요한가.
 * 아카이브 스냅샷에서 뽑은 주소는 2018~2021년 페이지의 것이다. 그중에는
 * 지금 CDN 에 없는 것이 섞인다. 그대로 두면 상세페이지 갤러리에 깨진 칸이
 * 생기고, 썸네일을 눌러도 아무 일이 없다. 이건 단순히 보기 나쁜 게 아니라
 * **행동 로그가 오염되는 문제**다 — 이미지가 안 뜨면 그 자리에 머문 시간이
 * 그대로 체류 시간으로 잡힌다.
 *
 * 주의: CDN 이 User-Agent 없는 요청을 403 으로 막는다. UA 를 안 붙이면
 * 살아 있는 이미지도 죽은 것으로 판정한다. 403 이 오면 판정하지 않고 멈춘다.
 *
 * 본문은 받지 않는다(HEAD). 갤러리 한 장이 수백 KB 라 GET 으로 훑으면
 * 1,500장에서 수백 MB 를 받게 된다.
 *
 *   node scripts/verify-images.mjs             전체 확인. 죽은 것 제거
 *   node scripts/verify-images.mjs --dry-run   확인만. 파일은 안 고친다
 *   node scripts/verify-images.mjs --only P473322,P500633
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const COLLECTED = join(here, '..', 'src', 'mocks', 'products.collected.json');

const UA = 'Mozilla/5.0';
const PAUSE_MS = 90;

const args = process.argv.slice(2);
const argOf = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};
const only = argOf('--only')?.split(',').map((s) => s.trim().toUpperCase()) ?? null;
const dryRun = args.includes('--dry-run');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const collected = JSON.parse(readFileSync(COLLECTED, 'utf8'));

async function alive(url) {
  try {
    const res = await fetch(url, { method: 'HEAD', headers: { 'User-Agent': UA } });
    if (res.status === 403) throw new Error('403');
    return res.status === 200;
  } catch (error) {
    if (String(error.message) === '403') throw error;
    return false;
  }
}

const ids = Object.keys(collected).filter((id) => (only ? only.includes(id) : true));
let checked = 0;
let dropped = 0;
let touched = 0;

for (const id of ids) {
  const entry = collected[id];
  const urls = [...(entry.images ?? [])];
  if (entry.image_url) urls.push(entry.image_url);
  if (urls.length === 0) continue;

  const dead = [];
  try {
    for (const url of urls) {
      checked += 1;
      if (!(await alive(url))) dead.push(url);
      await sleep(PAUSE_MS);
    }
  } catch {
    console.log(`${id}  중단 — CDN 이 403 을 준다. UA 차단 정책을 확인해야 한다`);
    break;
  }

  if (dead.length === 0) continue;

  const deadSet = new Set(dead);
  entry.images = (entry.images ?? []).filter((u) => !deadSet.has(u));
  if (entry.image_url && deadSet.has(entry.image_url)) entry.image_url = null;

  dropped += dead.length;
  touched += 1;
  console.log(`${id}  죽은 주소 ${dead.length}개 제거 (남은 갤러리 ${entry.images.length}장)`);

  if (!dryRun) writeFileSync(COLLECTED, `${JSON.stringify(collected, null, 2)}\n`, 'utf8');
}

console.log(`\n확인 ${checked}장 · 제거 ${dropped}장 · 손댄 상품 ${touched}개`);
if (dryRun) console.log('--dry-run 이라 파일에 쓰지 않았다');
