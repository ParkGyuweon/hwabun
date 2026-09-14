/**
 * 신규 상품 판정 — 계약 recommendation-io-spec §5 처리 6-1 (2026-09-11 결정, Jira 247-b).
 *
 * 신규 = **등록 후 14일 이내인 등록 상품**. 추천 서버(`NEW_BRAND_DAYS`, 기본 14)와 같은 값이다.
 * 등록 시각을 모르면(백엔드 요약이 아직 `createdAt` 을 안 내려줌 — 요청서 9-11) 신규로 본다.
 * 원천 카탈로그 200개는 등록 시각이 없고 `rank` 가 있어 신규가 아니다.
 *
 * 시연용 SSAFY Beauty 8개는 2026-09-09 등록이라 09-23 부터 신규에서 빠진다. 추천 서버의
 * `NEW_BRAND_ALWAYS_PREFIX` 와 짝을 맞추려면 `NEW_ALWAYS_PREFIX` 를 같은 값으로 둔다.
 */
export const NEW_BRAND_DAYS = 14;

/** 기간과 무관하게 신규로 두는 product_id 접두. 추천 서버 `NEW_BRAND_ALWAYS_PREFIX` 와 같은 값 (팀 합의 뒤) */
export const NEW_ALWAYS_PREFIX: string = (import.meta.env.VITE_NEW_BRAND_ALWAYS_PREFIX as string | undefined) ?? '';

/** 등록 시각이 지금부터 `NEW_BRAND_DAYS` 안이면 true. 시각이 없거나 못 읽으면 `unknown` 을 돌려준다 */
export function isWithinNewWindow(createdAt: string | null | undefined, unknown = true, now: number = Date.now()): boolean {
  if (!createdAt) return unknown;
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return unknown;
  return now - t < NEW_BRAND_DAYS * 24 * 60 * 60 * 1000;
}

/** 신규 종료 시각 (ISO). 등록 시각을 모르면 null. 추천 서버 `GET /api/products/{id}` 의 `new_until` 과 같은 뜻 */
export function newUntil(createdAt: string | null | undefined): string | null {
  if (!createdAt) return null;
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return null;
  return new Date(t + NEW_BRAND_DAYS * 24 * 60 * 60 * 1000).toISOString();
}

/** 등록 상품의 `new` 배지: 14일 규칙 또는 시연 예외 접두 */
export function isNewRegistered(productId: string, createdAt: string | null | undefined): boolean {
  if (NEW_ALWAYS_PREFIX && productId.startsWith(NEW_ALWAYS_PREFIX)) return true;
  return isWithinNewWindow(createdAt);
}
