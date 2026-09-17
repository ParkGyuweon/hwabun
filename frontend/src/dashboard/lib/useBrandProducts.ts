import { useEffect, useMemo, useState } from 'react';
import { listBackendProducts } from '../../lib/shopApi';
import type { Product } from '../../types/product';

export interface BrandProducts {
  /** 아직 받는 중이면 null. 실패해도 null 이고 `failed` 로 가른다 */
  products: Product[] | null;
  failed: boolean;
}

/**
 * 내 브랜드가 등록한 상품.
 *
 * 등록 상품 목록과 주문 화면이 같은 것을 본다 — 주문 화면은 "판매된 적 없는 상품" 을 고르려고 전체 목록이
 * 필요하고, 그 판정이 두 화면에서 갈리면 안 된다. 그래서 고르는 규칙을 여기 한 곳에 둔다.
 *
 * `backend_brand_id` 가 정본이고, 비어 있으면(등록 직후 동기화 시차) 브랜드 이름으로 맞춘다.
 * **못 읽으면 못 읽었다고 한다.** 번들 파일로 대신 채우지 않는다.
 */
export function useBrandProducts(brandId: string | null, brandName: string | null): BrandProducts {
  const [rows, setRows] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    void listBackendProducts().then((all) => {
      if (!alive) return;
      if (all === null) setFailed(true);
      else setRows(all);
    });
    return () => {
      alive = false;
    };
  }, []);

  const products = useMemo(() => {
    if (rows === null) return null;
    return rows.filter((p) => (brandId && p.backend_brand_id === brandId) || (brandName && p.brand_name === brandName));
  }, [rows, brandId, brandName]);

  return { products, failed };
}
