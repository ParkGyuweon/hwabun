/**
 * 상품별 리뷰 조각 · 연 상품 것만 받는다.
 *
 * 리뷰 2,000건과 번역본 20,000건을 번들에 통째로 넣던 것을 상품별 JSON 으로 나눴다 (`plugins/review-chunks.ts`).
 * 상세 페이지가 열릴 때 `/reviews/{product_id}.json` 하나(10건 안팎)만 받고, 같은 상품은 다시 받지 않는다.
 * "이 리뷰어의 다른 리뷰 n개" 는 작성자별 건수 파일 하나로 대신한다 — 전체 리뷰를 들고 있을 이유가 그것뿐이었다.
 *
 * 백엔드 상품(`source: 'backend'`)의 리뷰는 여기가 아니라 `shopApi.fetchBackendReviews` 다.
 */
import { useEffect, useState } from 'react';
import type { Review } from '../types/review';
import type { SkinType } from '../types/product';

const BASE = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/reviews/`;

const cache = new Map<string, Review[]>();
const inflight = new Map<string, Promise<Review[]>>();

async function getJson<T>(name: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${encodeURIComponent(name)}.json`, { headers: { Accept: 'application/json' } });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

/** 상품 하나의 리뷰. 실패하면 빈 배열이고 다음 요청 때 다시 시도한다 */
export function loadProductReviews(productId: string): Promise<Review[]> {
  const hit = cache.get(productId);
  if (hit) return Promise.resolve(hit);
  const pending = inflight.get(productId);
  if (pending) return pending;
  const p = getJson<Review[] | null>(productId, null).then((rows) => {
    inflight.delete(productId);
    if (!Array.isArray(rows)) return [];
    cache.set(productId, rows);
    return rows;
  });
  inflight.set(productId, p);
  return p;
}

let authorCounts: Map<string, number> | null = null;
let authorPending: Promise<Map<string, number>> | null = null;

/** 작성자별 리뷰 수 (2건 이상만 들어 있다). 한 번만 받는다 */
export function loadAuthorCounts(): Promise<Map<string, number>> {
  if (authorCounts) return Promise.resolve(authorCounts);
  if (authorPending) return authorPending;
  authorPending = getJson<Record<string, number>>('_authors', {}).then((obj) => {
    authorCounts = new Map(Object.entries(obj));
    authorPending = null;
    return authorCounts;
  });
  return authorPending;
}

const EMPTY: Review[] = [];
const EMPTY_COUNTS = new Map<string, number>();

/** 상품이 바뀌면 그 상품 리뷰를 받는다. 캐시에 있으면 첫 렌더부터 있다 */
export function useProductReviews(productId: string | null): { reviews: Review[]; loading: boolean } {
  const cached = productId ? cache.get(productId) : undefined;
  const [state, setState] = useState<{ id: string | null; rows: Review[] } | null>(null);

  useEffect(() => {
    if (!productId || cache.has(productId)) return;
    let alive = true;
    void loadProductReviews(productId).then((rows) => {
      if (alive) setState({ id: productId, rows });
    });
    return () => {
      alive = false;
    };
  }, [productId]);

  if (!productId) return { reviews: EMPTY, loading: false };
  if (cached) return { reviews: cached, loading: false };
  if (state && state.id === productId) return { reviews: state.rows, loading: false };
  return { reviews: EMPTY, loading: true };
}

let skinTypes: Map<string, SkinType[]> | null = null;
let skinPending: Promise<Map<string, SkinType[]>> | null = null;

/** 상품별 리뷰어 피부 타입 (표기할 만큼 비중이 있는 것만, lib/skinTypes 규칙). 목록 페이지가 한 번 받는다 */
export function loadReviewSkinTypes(): Promise<Map<string, SkinType[]>> {
  if (skinTypes) return Promise.resolve(skinTypes);
  if (skinPending) return skinPending;
  skinPending = getJson<Record<string, SkinType[]>>('_skin_types', {}).then((obj) => {
    skinTypes = new Map(Object.entries(obj));
    skinPending = null;
    return skinTypes;
  });
  return skinPending;
}

const EMPTY_SKIN = new Map<string, SkinType[]>();

export function useReviewSkinTypes(): Map<string, SkinType[]> {
  const [map, setMap] = useState<Map<string, SkinType[]>>(skinTypes ?? EMPTY_SKIN);
  useEffect(() => {
    if (skinTypes) return;
    let alive = true;
    void loadReviewSkinTypes().then((m) => {
      if (alive) setMap(m);
    });
    return () => {
      alive = false;
    };
  }, []);
  return map;
}

export function useAuthorCounts(): Map<string, number> {
  const [counts, setCounts] = useState<Map<string, number>>(authorCounts ?? EMPTY_COUNTS);
  useEffect(() => {
    if (authorCounts) return;
    let alive = true;
    void loadAuthorCounts().then((m) => {
      if (alive) setCounts(m);
    });
    return () => {
      alive = false;
    };
  }, []);
  return counts;
}
