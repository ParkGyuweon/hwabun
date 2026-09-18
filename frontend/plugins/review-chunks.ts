import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';
import { deriveSkinTypesFromReviews } from '../src/lib/skinTypes.ts';

/**
 * 리뷰를 상품별 JSON 조각으로 나눠 준다 — `/reviews/{product_id}.json`.
 *
 * 예전에는 쇼핑몰 번들이 `reviews.sample.json`(2,000건)과 한국어 번역본 `contracts/localization/reviews-ko.json`
 * (20,000건 · 9MB, 모듈로 감싸면 44MB)을 통째로 import 했다. 상세 한 번 열 때 46MB 가 내려온 원인이 상세 API 가
 * 아니라 이 두 파일이었다 (2026-09-14 실측). 상세 페이지는 그 상품의 리뷰 10건만 쓴다.
 *
 * 그래서 dev 서버·빌드가 두 파일을 한 번 읽어 **상품별로 합쳐 번역까지 끼운 조각**을 만들고, 화면은 연 상품 것만
 * 받는다 (`src/lib/reviewStore.ts`). 원본 파일은 그대로 두고(대시보드 지표가 영문 원본을 정규식으로 읽는다) 커밋할
 * 산출물도 없다 — dev 는 요청 때 메모리에서, build 는 `dist/reviews/` 로 낸다.
 *
 *   /reviews/{product_id}.json   그 상품의 리뷰 (번역 반영, 없으면 `[]`)
 *   /reviews/_authors.json       작성자별 리뷰 수 (2건 이상만). "이 리뷰어의 다른 리뷰 n개" 표시용
 *   /reviews/_skin_types.json    상품별 리뷰어 피부 타입 (lib/skinTypes 규칙). 목록 페이지의 페르소나 매칭 근거
 *   /reviews/_counts.json        상품별 리뷰 건수. 카드가 적는 숫자와 상세가 그리는 리뷰 수를 같게 한다
 */

interface RawReview {
  review_id: string;
  product_id: string;
  author_id: string;
  review_title: string | null;
  review_text: string | null;
  skin_type: 'combination' | 'dry' | 'normal' | 'oily' | null;
  [k: string]: unknown;
}
interface ReviewKo {
  review_title: string | null;
  review_text: string;
}

const here = dirname(fileURLToPath(import.meta.url));
const SAMPLE = join(here, '..', 'src', 'mocks', 'reviews.sample.json');
const KO = join(here, '..', '..', 'contracts', 'localization', 'reviews-ko.json');

export const REVIEWS_PREFIX = '/reviews/';
export const AUTHORS_FILE = '_authors';
export const SKIN_TYPES_FILE = '_skin_types';
export const COUNTS_FILE = '_counts';

const SAFE_ID = /^[A-Za-z0-9_-]+$/;

interface Built {
  byProduct: Map<string, string>;
  authors: string;
  skinTypes: string;
  /** 상품별 리뷰 건수. 카드·요약이 "전체 몇 건" 대신 **실제 가진 건수**를 적는다 */
  counts: string;
}

let built: Built | null = null;

const isReviewKo = (v: unknown): v is ReviewKo =>
  typeof v === 'object' && v !== null && 'review_text' in (v as Record<string, unknown>);

/** 두 파일을 읽어 상품별 조각을 만든다. 파일이 바뀌면 dev 서버를 다시 띄운다 (번역본은 생성 파일이라 자주 안 바뀐다) */
function build(): Built {
  if (built) return built;
  const rows = JSON.parse(readFileSync(SAMPLE, 'utf8')) as RawReview[];
  const ko = JSON.parse(readFileSync(KO, 'utf8')) as Record<string, unknown>;

  const groups = new Map<string, RawReview[]>();
  const authorCounts = new Map<string, number>();
  for (const r of rows) {
    const t = ko[r.review_id];
    // src/lib/localize.ts 의 옛 localizeReview 와 같은 규칙: 번역이 있으면 제목은 번역값 그대로, 본문은 비어 있지 않을 때만
    const row: RawReview = isReviewKo(t) ? { ...r, review_title: t.review_title, review_text: t.review_text || r.review_text } : r;
    const list = groups.get(r.product_id);
    if (list) list.push(row);
    else groups.set(r.product_id, [row]);
    authorCounts.set(r.author_id, (authorCounts.get(r.author_id) ?? 0) + 1);
  }

  const byProduct = new Map<string, string>();
  for (const [id, list] of groups) byProduct.set(id, JSON.stringify(list));
  const authors = JSON.stringify(Object.fromEntries([...authorCounts].filter(([, n]) => n > 1)));
  const skinTypes = JSON.stringify(
    Object.fromEntries([...groups].map(([id, list]) => [id, deriveSkinTypesFromReviews(list).types]).filter(([, t]) => (t as string[]).length > 0)),
  );
  const counts = JSON.stringify(Object.fromEntries([...groups].map(([id, list]) => [id, list.length])));
  built = { byProduct, authors, skinTypes, counts };
  return built;
}

function lookup(name: string): string | null {
  if (name === AUTHORS_FILE) return build().authors;
  if (name === SKIN_TYPES_FILE) return build().skinTypes;
  if (name === COUNTS_FILE) return build().counts;
  if (!SAFE_ID.test(name)) return null;
  return build().byProduct.get(name) ?? '[]';
}

export function reviewChunks(): Plugin {
  return {
    name: 'hwabun-review-chunks',

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        if (!url.startsWith(REVIEWS_PREFIX) || !url.includes('.json')) return next();
        const name = url.slice(REVIEWS_PREFIX.length).split('?')[0].replace(/\.json$/, '');
        const body = lookup(name);
        if (body === null) return next();
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.setHeader('Cache-Control', 'no-cache');
        res.end(body);
      });
    },

    generateBundle() {
      const { byProduct, authors } = build();
      for (const [id, source] of byProduct) {
        this.emitFile({ type: 'asset', fileName: `reviews/${id}.json`, source });
      }
      this.emitFile({ type: 'asset', fileName: `reviews/${AUTHORS_FILE}.json`, source: authors });
      this.emitFile({ type: 'asset', fileName: `reviews/${SKIN_TYPES_FILE}.json`, source: build().skinTypes });
      this.emitFile({ type: 'asset', fileName: `reviews/${COUNTS_FILE}.json`, source: build().counts });
    },
  };
}
