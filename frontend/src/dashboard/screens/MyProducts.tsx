import { useEffect, useMemo, useState } from 'react';
import { Panel } from '../components';
import { fmt } from '../lib/metrics';
import { listBackendProducts } from '../../lib/shopApi';
import { toKrw } from '../../lib/localize';
import type { Product } from '../../types/product';

/**
 * 내가 등록한 상품 — 썸네일과 함께 쭉 훑는 목록.
 *
 * 위 진단 표와 목적이 다르다. 진단 표는 **행동 데이터가 있는 브랜드**의 상품을 병목·이탈 축으로 줄세운다.
 * 시연 브랜드처럼 행동 로그가 아직 없는 브랜드는 그 표에 한 줄도 안 나오고, 그래서 사장님이
 * "내가 올린 것들" 을 대시보드 안에서 볼 자리가 없었다.
 *
 * 여기 숫자는 전부 등록 정보다 — 가격·옵션 수. 행동 지표가 아니라서 마트가 비어 있어도 값이 나온다.
 *
 * **못 읽으면 못 읽었다고 적는다.** 번들 파일로 대신 채우지 않는다 — 사장님이 그 목록을 "내가 올린 것" 으로
 * 읽기 때문이다. 없으면 없다고, 못 읽으면 못 읽었다고 적는 편이 언제나 낫다.
 */
export default function MyProducts({ brandId, brandName }: { brandId: string | null; brandName: string | null }) {
  const [rows, setRows] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    void listBackendProducts().then((all) => {
      if (!alive) return;
      if (all === null) {
        setFailed(true);
        return;
      }
      setRows(all);
    });
    return () => {
      alive = false;
    };
  }, []);

  /**
   * 내 상품 고르기. 백엔드가 준 `backend_brand_id` 가 정본이고, 그게 비어 있으면 브랜드 이름으로 맞춘다
   * (등록 직후 동기화 시차). 둘 다 안 맞으면 내 상품이 아니다.
   */
  const list = useMemo(() => {
    if (rows === null) return null;
    return rows.filter((p) => (brandId && p.backend_brand_id === brandId) || (brandName && p.brand_name === brandName));
  }, [rows, brandId, brandName]);

  if (failed) {
    return (
      <Panel title="내가 등록한 상품" source="real" aside="-">
        <p className="note">쇼핑몰 서버를 읽지 못했습니다. 잠시 뒤 새로고침해 주세요.</p>
      </Panel>
    );
  }

  if (list === null) {
    return (
      <Panel title="내가 등록한 상품" source="real" aside="불러오는 중">
        <p className="note">상품 목록을 받는 중입니다.</p>
      </Panel>
    );
  }

  if (list.length === 0) {
    return (
      <Panel title="내가 등록한 상품" source="real" aside="0개">
        <p className="note">아직 등록한 상품이 없습니다. 왼쪽 "상품 등록" 에서 첫 상품을 올리면 여기에 보입니다.</p>
      </Panel>
    );
  }

  return (
    <Panel title="내가 등록한 상품" source="real" aside={`${list.length}개 · 쇼핑몰에 올라간 그대로`}>
      <ul className="myproducts">
        {list.map((p) => {
          const image = p.image_url ?? p.images[0] ?? null;
          const price = toKrw(p.price_usd);
          return (
            <li key={p.product_id} className="myproducts__item">
              {image ? (
                <img className="myproducts__thumb" src={image} alt="" loading="lazy" width="64" height="64" />
              ) : (
                /* 이미지를 안 올린 상품도 줄을 비우지 않는다. 빈 칸이면 목록이 어긋나 읽기 어렵다 */
                <span className="myproducts__thumb myproducts__thumb--empty" aria-hidden="true" />
              )}
              <div className="myproducts__body">
                <p className="myproducts__name">{p.product_name}</p>
                <p className="myproducts__meta">
                  {p.product_id}
                  {p.variants.length > 0 ? ` · 옵션 ${p.variants.length}개` : ''}
                  {(p.badges ?? []).includes('new') ? ' · 신상품' : ''}
                </p>
              </div>
              <p className="myproducts__price">{price > 0 ? `${fmt.int(price)}원` : '가격 미입력'}</p>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
