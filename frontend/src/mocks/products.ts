/**
 * 쇼핑몰이 읽는 상품 목록 — 두 출처를 합친다.
 *
 * - `products.sample.json`  세포라 200개. `scripts/build-products.ts` 가 만드는 **생성 파일**이라
 *                            손으로 고치지 않는다. 리뷰 84만 건과 페르소나가 여기에 묶여 있어
 *                            추천 검증의 기준 카탈로그다.
 * - `products.ssafy-beauty.json`  시연용 가상 브랜드 SSAFY Beauty 8종. 손으로 쓴 파일이다.
 *                            "브랜드가 직접 등록한 상품" 을 보여 주는 자리라 리뷰가 없고
 *                            (`rating: null`, `review_count: 0`) 이미지도 플레이스홀더다.
 *                            전성분은 공개 INCI 표기를 옮겨 적었고 상품명·설명은 자체 작성.
 *
 * 시드가 앞에 온다 — `rank` 가 없어 인기순 정렬에서는 뒤로 가지만, 배열 순서를 쓰는
 * 곳(대시보드 기본 목록)에서는 우리 브랜드가 먼저 보인다.
 * 결정 근거: docs/dashboard/korean-brand-seed-plan.md (2026-09-07).
 */
import sampleData from './products.sample.json';
import seedData from './products.ssafy-beauty.json';
import { localizeProduct } from '../lib/localize';
import { applyDiscount } from '../lib/discount';
import type { Product } from '../types/product';

/** 시연용 브랜드. 브랜드 대시보드의 "내 브랜드" 기본값이다 */
export const DEMO_BRAND = 'SSAFY Beauty';

export const seedProducts = (seedData as unknown as Product[]).map(applyDiscount);
/**
 * 세포라 200개는 표시 필드(상품명·용량·설명·한국어 전성분)만 한국어로 바꿔 끼운다.
 * 분석이 읽는 값은 그대로다 (lib/localize.ts 원칙). 시드 8종은 처음부터 한국어라 대상이 아니다.
 */
export const sampleProducts = (sampleData as unknown as Product[]).map(localizeProduct).map(applyDiscount);

export const products: Product[] = [...seedProducts, ...sampleProducts];
