import { useEffect, useMemo, useState } from 'react';
import { Panel } from '../components';
import { fmt } from '../lib/metrics';
import { useBrandProducts } from '../lib/useBrandProducts';
import { toKrw } from '../../lib/localize';
import { fetchSellerOrders } from '../../lib/shopApi';
import type { SellerOrder } from '../../lib/shopApi';

/** 로컬(Asia/Seoul) 기준 YYYY-MM-DD. 결제 시각은 ISO 라 UTC 로 자르면 자정 근처 주문이 어제로 간다 */
function localDay(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

interface Sold {
  today: number;
  month: number;
  total: number;
  amount: number;
}

/**
 * 내가 등록한 상품 — 썸네일과 함께 쭉 훑는 목록. **뭐가 얼마나 팔렸는지**를 같이 적는다.
 *
 * 위 진단 표와 목적이 다르다. 진단 표는 **행동 데이터가 있는 브랜드**의 상품을 병목·이탈 축으로 줄세운다.
 * 시연 브랜드처럼 행동 로그가 아직 없는 브랜드는 그 표에 한 줄도 안 나오고, 그래서 사장님이
 * "내가 올린 것들" 을 대시보드 안에서 볼 자리가 없었다.
 *
 * 판매량은 쇼핑몰 원장(GET /api/seller/orders)의 결제 완료 주문에서 센다 — 오늘 · 이번 달 · 누적.
 * 많이 팔린 순으로 줄을 세우고 1위에 표시를 단다 (2026-09-18 요청). 한 개도 안 팔렸으면 순위가 없다.
 *
 * **못 읽으면 못 읽었다고 적는다.** 번들 파일로 대신 채우지 않는다 — 사장님이 그 목록을 "내가 올린 것" 으로
 * 읽기 때문이다. 없으면 없다고, 못 읽으면 못 읽었다고 적는 편이 언제나 낫다.
 */
export default function MyProducts({ brandId, brandName }: { brandId: string | null; brandName: string | null }) {
  const { products: list, failed } = useBrandProducts(brandId, brandName);

  // 주문은 누적으로 센다. 시작일을 넉넉히 잡는다 — 서버가 from/to 를 요구한다
  // 브랜드별로 받은 결과를 기억한다. 브랜드가 바뀌면 자연히 null(받는 중)이 된다 — effect 안에서 초기화하지 않는다
  const [loaded, setLoaded] = useState<{ brand: string; rows: SellerOrder[] | null } | null>(null);
  const orders = loaded !== null && loaded.brand === brandId ? loaded.rows : null;
  const ordersFailed = loaded !== null && loaded.brand === brandId && loaded.rows === null;
  useEffect(() => {
    if (!brandId) return;
    let alive = true;
    void fetchSellerOrders(brandId, { from: '2020-01-01', to: localDay(new Date().toISOString()) }).then((rows) => {
      if (alive) setLoaded({ brand: brandId, rows });
    });
    return () => {
      alive = false;
    };
  }, [brandId]);

  const sold = useMemo(() => {
    const today = localDay(new Date().toISOString());
    const month = today.slice(0, 7);
    const acc = new Map<string, Sold>();
    for (const o of orders ?? []) {
      const day = localDay(o.ordered_at);
      for (const item of o.items) {
        const cur = acc.get(item.product_id) ?? { today: 0, month: 0, total: 0, amount: 0 };
        cur.total += item.quantity;
        cur.amount += item.line_amount;
        if (day === today) cur.today += item.quantity;
        if (day.slice(0, 7) === month) cur.month += item.quantity;
        acc.set(item.product_id, cur);
      }
    }
    return acc;
  }, [orders]);

  const totals = useMemo(() => {
    let today = 0;
    let month = 0;
    let total = 0;
    for (const s of sold.values()) {
      today += s.today;
      month += s.month;
      total += s.total;
    }
    return { today, month, total };
  }, [sold]);

  /** 많이 팔린 순. 같은 수면 등록 순서 그대로 */
  const ranked = useMemo(() => {
    if (!list) return [];
    return [...list].sort((a, b) => (sold.get(b.product_id)?.total ?? 0) - (sold.get(a.product_id)?.total ?? 0));
  }, [list, sold]);
  const bestId = ranked.length > 0 && (sold.get(ranked[0].product_id)?.total ?? 0) > 0 ? ranked[0].product_id : null;

  if (failed) {
    return (
      <Panel title="내가 등록한 상품" source="real">
        <p className="note">상품 목록을 읽지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>
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
        <p className="note">아직 등록한 상품이 없습니다. 왼쪽 메뉴 "상품 등록" 에서 첫 상품을 올리면 여기에 보입니다.</p>
      </Panel>
    );
  }

  const salesAside = ordersFailed
    ? '판매량은 읽지 못했습니다. 잠시 뒤 다시 열어 주세요'
    : orders === null
      ? '판매량 받는 중'
      : `오늘 ${fmt.int(totals.today)}개 · 이번 달 ${fmt.int(totals.month)}개 · 지금까지 ${fmt.int(totals.total)}개 팔림`;

  return (
    <Panel title="내가 등록한 상품" source="real" aside={`${list.length}개 · ${salesAside}`}>
      <ul className="myproducts">
        {ranked.map((p) => {
          const image = p.image_url ?? p.images[0] ?? null;
          const price = toKrw(p.price_usd);
          const s = sold.get(p.product_id) ?? { today: 0, month: 0, total: 0, amount: 0 };
          return (
            <li key={p.product_id} className={`myproducts__item${p.product_id === bestId ? ' is-best' : ''}`}>
              {image ? (
                <img className="myproducts__thumb" src={image} alt="" loading="lazy" width="64" height="64" />
              ) : (
                /* 이미지를 안 올린 상품도 줄을 비우지 않는다. 빈 칸이면 목록이 어긋나 읽기 어렵다 */
                <span className="myproducts__thumb myproducts__thumb--empty" aria-hidden="true" />
              )}
              <div className="myproducts__body">
                <p className="myproducts__name">
                  {p.product_name}
                  {p.product_id === bestId ? <span className="myproducts__tag">가장 많이 팔림</span> : null}
                </p>
                <p className="myproducts__meta">
                  {p.product_id}
                  {p.variants.length > 0 ? ` · 옵션 ${p.variants.length}개` : ''}
                  {(p.badges ?? []).includes('new') ? ' · 신상품' : ''}
                </p>
                {orders !== null ? (
                  <p className="myproducts__sales">
                    오늘 <b>{fmt.int(s.today)}</b>개 · 이번 달 <b>{fmt.int(s.month)}</b>개 · 지금까지 <b>{fmt.int(s.total)}</b>개
                    {s.total > 0 ? ` · 매출 ${fmt.int(s.amount)}원` : ' · 아직 팔린 적 없음'}
                  </p>
                ) : null}
              </div>
              <p className="myproducts__price">{price > 0 ? `${fmt.int(price)}원` : '가격 미입력'}</p>
            </li>
          );
        })}
      </ul>
      {orders !== null ? <p className="note">판매량은 결제가 끝난 주문 기준입니다. 많이 팔린 순으로 보여 줍니다.</p> : null}
    </Panel>
  );
}
