import { useSyncExternalStore } from 'react';
import { catalogSnapshot, draftProduct, registeredProducts, subscribeCatalog } from '../lib/productRegistry';
import type { RegisteredProduct } from '../lib/productRegistry';
import type { Product } from '../types/product';

/** 쇼핑몰 카탈로그. 브랜드가 대시보드에서 등록하거나 초안을 고치면 새로고침 없이 따라온다 */
export function useCatalog(): Product[] {
  return useSyncExternalStore(subscribeCatalog, catalogSnapshot, catalogSnapshot);
}

/** 이 브랜드가 등록한 상품만. 등록·수정·삭제에 따라온다 */
export function useRegistered(): RegisteredProduct[] {
  return useSyncExternalStore(subscribeCatalog, registeredProducts, registeredProducts);
}

/** 등록 폼의 초안. 미리보기 주소(`?product=DRAFT`)에서만 쓴다 */
export function useDraft(): Product | null {
  return useSyncExternalStore(subscribeCatalog, draftProduct, draftProduct);
}
