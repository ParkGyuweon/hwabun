/**
 * 내 브랜드 — shop_backend `/api/brands` (SELLER 토큰 필요).
 *
 *   GET  /api/brands   → BrandResponse[]  (SELLER 는 자기 것만, ADMIN 은 전체)
 *   POST /api/brands   { name, description?, logoUrl? } → 201 BrandResponse
 *   BrandResponse = { id, sellerAccountId, name, description, logoUrl, status }
 *
 * 판매자 API(`/api/seller/dashboard`, `/api/seller/feedback`)는 전부 `brandId` 를 요구한다.
 * 그래서 로그인 직후 목록을 받아 하나를 고르고, 고른 id 를 같은 브라우저에 기억한다.
 * 서버가 없거나 401 이면 빈 목록으로 돌려주고 화면은 모의 브랜드(DEMO_BRAND)로 남는다.
 */
import { authFetch } from './auth';

export interface Brand {
  id: string;
  sellerAccountId: string;
  name: string;
  description: string | null;
  logoUrl: string | null;
  status: string;
}

export type BrandsState =
  | { kind: 'loading' }
  | { kind: 'ready'; brands: Brand[] }
  | { kind: 'unavailable'; reason: 'unauthorized' | 'server' };

const BRAND_KEY = 'bloom.brand.v1';

export function loadBrandId(): string | null {
  try {
    return window.localStorage.getItem(BRAND_KEY);
  } catch {
    return null;
  }
}

export function saveBrandId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(BRAND_KEY, id);
    else window.localStorage.removeItem(BRAND_KEY);
  } catch {
    /* 저장 불가 — 이번 탭에서만 유지 */
  }
}

export async function fetchMyBrands(): Promise<BrandsState> {
  let res: Response;
  try {
    res = await authFetch('SELLER', '/api/brands');
  } catch {
    return { kind: 'unavailable', reason: 'server' };
  }
  if (res.status === 401 || res.status === 403) return { kind: 'unavailable', reason: 'unauthorized' };
  if (!res.ok) return { kind: 'unavailable', reason: 'server' };
  try {
    const rows = (await res.json()) as Brand[];
    return { kind: 'ready', brands: Array.isArray(rows) ? rows : [] };
  } catch {
    return { kind: 'unavailable', reason: 'server' };
  }
}

export async function createBrand(name: string): Promise<Brand | null> {
  const res = await authFetch('SELLER', '/api/brands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  });
  if (!res.ok) return null;
  return (await res.json()) as Brand;
}
