import { Fragment, useEffect, useMemo, useState } from 'react';
import { BarList, Kpi, Panel } from '../components';
import { fmt } from '../lib/metrics';
import { fetchSellerOrders } from '../../lib/shopApi';
import type { SellerOrder } from '../../lib/shopApi';
import { rangeOf } from '../lib/martApi';
import { useBrandProducts } from '../lib/useBrandProducts';
import { categoryKo } from '../../lib/localize';

/**
 * 주문 (`docs/dashboard/seller-console-gaps.md` §5).
 *
 * 대시보드의 다른 화면은 전부 **행동 마트**를 읽는다. 이 화면만 `shop_backend` 원장을 읽는다 — 그래서
 * DW 적재가 끝나기 전에도 여기만은 실측으로 찬다. 결제가 끝난 주문이 곧 판매이고, 그것은 마트를 거치지
 * 않아도 이미 서버에 있다.
 *
 * 상단 칸·일별 매출·상품별 판매는 전부 **주문 목록 하나를 접어서** 만든다. 집계 엔드포인트를 따로 두면
 * 표의 합과 칸의 숫자가 갈릴 수 있어서다. 한 배열에서 나오면 갈릴 수가 없다.
 *
 * 값이 없으면 0 과 "-" 다. 모의로 채우지 않는다.
 */
export default function OrdersScreen({
  brandId,
  brandName,
  days,
}: {
  brandId: string | null;
  brandName: string | null;
  days: number;
}) {
  // 등록 상품 전체. "판매된 적 없는 상품" 을 고르려면 판 것만으로는 알 수 없다
  const { products: myProducts } = useBrandProducts(brandId, brandName);
  const [orders, setOrders] = useState<SellerOrder[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const range = useMemo(() => rangeOf(days), [days]);

  useEffect(() => {
    if (!brandId) return;
    let alive = true;
    setOrders(null);
    setFailed(false);
    void fetchSellerOrders(brandId, range).then((rows) => {
      if (!alive) return;
      if (rows === null) setFailed(true);
      else setOrders(rows);
    });
    return () => {
      alive = false;
    };
  }, [brandId, range]);

  const totals = useMemo(() => {
    const list = orders ?? [];
    const revenue = list.reduce((s, o) => s + o.brand_amount, 0);
    const units = list.reduce((s, o) => s + o.item_count, 0);
    /*
     * 구매 고객 수는 주문 수와 다르다. 한 사람이 세 번 사면 주문 3 · 고객 1 이다.
     * 주문 수만 보면 같은 고객의 반복 구매가 가려져서 "고객이 늘었다" 로 잘못 읽힌다.
     */
    const buyers = new Set(list.map((o) => o.buyer_id)).size;
    return {
      revenue,
      units,
      buyers,
      count: list.length,
      average: list.length === 0 ? 0 : Math.round(revenue / list.length),
    };
  }, [orders]);

  /** 일별 매출. 결제일로 접는다 — 주문이 없는 날은 줄을 만들지 않는다 (0 원을 그리면 "안 팔린 날" 이 된다) */
  const daily = useMemo(() => {
    const byDay = new Map<string, number>();
    for (const o of orders ?? []) {
      const day = (o.ordered_at ?? '').slice(0, 10);
      if (!day) continue;
      byDay.set(day, (byDay.get(day) ?? 0) + o.brand_amount);
    }
    return [...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [orders]);

  /** 상품별 판매. 행동 화면의 "관심도" 와 다르다 — 이건 실제 결제다. 마지막으로 팔린 날도 같이 센다 */
  const byProduct = useMemo(() => {
    const acc = new Map<string, { name: string; quantity: number; amount: number; orders: Set<string>; last: string }>();
    for (const o of orders ?? []) {
      const day = (o.ordered_at ?? '').slice(0, 10);
      for (const item of o.items) {
        const cur =
          acc.get(item.product_id) ?? { name: item.product_name, quantity: 0, amount: 0, orders: new Set<string>(), last: '' };
        cur.quantity += item.quantity;
        cur.amount += item.line_amount;
        cur.orders.add(o.order_id);
        if (day > cur.last) cur.last = day;
        acc.set(item.product_id, cur);
      }
    }
    return [...acc.entries()]
      .map(([id, v]) => ({ id, name: v.name, quantity: v.quantity, amount: v.amount, orders: v.orders.size, last: v.last }))
      .sort((a, b) => b.amount - a.amount);
  }, [orders]);

  /**
   * 카테고리별 판매. 어느 갈래가 실제로 팔리는지 — 관심도가 아니라 결제다.
   * 카테고리는 상품 목록이 싣고 온다 (`category = [대분류, 중분류, 소분류]`). 중분류를 쓴다.
   */
  const byCategory = useMemo(() => {
    const categoryOf = new Map((myProducts ?? []).map((p) => [p.product_id, p.category[1] ?? p.category[0] ?? '']));
    const acc = new Map<string, { quantity: number; amount: number }>();
    for (const o of orders ?? []) {
      for (const item of o.items) {
        const key = categoryOf.get(item.product_id) || '기타';
        const cur = acc.get(key) ?? { quantity: 0, amount: 0 };
        cur.quantity += item.quantity;
        cur.amount += item.line_amount;
        acc.set(key, cur);
      }
    }
    return [...acc.entries()]
      .map(([key, v]) => ({ key, ko: key === '기타' ? '기타' : categoryKo(key), ...v }))
      .sort((a, b) => b.amount - a.amount);
  }, [orders, myProducts]);

  /** 이 기간에 한 개도 안 팔린 등록 상품. 상품 정리·기획 후보다 */
  const unsold = useMemo(() => {
    if (myProducts === null || orders === null) return null;
    const sold = new Set(byProduct.map((p) => p.id));
    return myProducts.filter((p) => !sold.has(p.product_id));
  }, [myProducts, orders, byProduct]);

  const won = (v: number) => `${fmt.int(v)}원`;

  if (!brandId) {
    return <Panel title="주문" source="real" aside="-"><p className="note">브랜드를 먼저 고르세요.</p></Panel>;
  }
  if (failed) {
    return (
      <Panel title="주문" source="real" aside="-">
        <p className="note">주문을 읽지 못했습니다. 잠시 뒤 새로고침해 주세요.</p>
      </Panel>
    );
  }
  if (orders === null) {
    return <Panel title="주문" source="real" aside="불러오는 중"><p className="note">주문을 받는 중입니다.</p></Panel>;
  }

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi label="기간 매출" value={won(totals.revenue)} sub={`결제 완료 · 최근 ${days}일`} source="real" />
        <Kpi label="주문 수" value={`${fmt.int(totals.count)}건`} sub="내 브랜드 상품이 포함된 주문" source="real" />
        <Kpi
          label="구매 고객 수"
          value={`${fmt.int(totals.buyers)}명`}
          sub={totals.buyers === 0 ? '구매한 고객이 없습니다' : `한 사람이 평균 ${(totals.count / totals.buyers).toFixed(1)}번 삽니다`}
          source="real"
        />
        <Kpi label="판매 수량" value={`${fmt.int(totals.units)}개`} sub="주문 수와 다르다 — 한 주문에 여러 개" source="real" />
        <Kpi
          label="평균 주문 금액"
          value={totals.count === 0 ? '-' : won(totals.average)}
          sub={totals.count === 0 ? '주문이 없습니다' : '내 브랜드 줄의 합 기준'}
          source="real"
        />
      </div>

      <Panel title={`일별 매출 · 최근 ${days}일`} source="real" aside={daily.length === 0 ? '-' : `${daily.length}일`}>
        {daily.length === 0 ? (
          <p className="note">이 기간에 결제된 주문이 없습니다.</p>
        ) : (
          <BarList items={daily.map(([day, amount]) => ({ label: day.slice(5).replace('-', '/'), value: amount }))} format={won} />
        )}
      </Panel>

      <Panel title="카테고리별 판매" source="real" aside={byCategory.length === 0 ? '-' : `${byCategory.length}개 갈래`}>
        {byCategory.length === 0 ? (
          <p className="note">판매된 상품이 없습니다.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>카테고리</th>
                <th>수량</th>
                <th>매출</th>
              </tr>
            </thead>
            <tbody>
              {byCategory.map((c) => (
                <tr key={c.key}>
                  <td>{c.ko}</td>
                  <td>{fmt.int(c.quantity)}</td>
                  <td>{won(c.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="주문" source="real" aside={orders.length === 0 ? '-' : `${orders.length}건 · 줄을 누르면 품목`}>
        {orders.length === 0 ? (
          <p className="note">이 기간에 들어온 주문이 없습니다.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>결제 시각</th>
                <th>주문번호</th>
                <th>구매자</th>
                <th>품목</th>
                <th>수량</th>
                <th>금액</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <Fragment key={o.order_id}>
                  <tr
                    className="is-clickable"
                    onClick={() => setOpen((cur) => (cur === o.order_id ? null : o.order_id))}
                  >
                    <td>{(o.ordered_at ?? '-').slice(0, 16).replace('T', ' ')}</td>
                    <td>
                      <span className="table__code">{o.order_id}</span>
                    </td>
                    <td>{o.buyer_nickname || o.buyer_id}</td>
                    <td>
                      {o.items[0]?.product_name ?? '-'}
                      {o.items.length > 1 ? ` 외 ${o.items.length - 1}` : ''}
                    </td>
                    <td>{fmt.int(o.item_count)}</td>
                    <td>{won(o.brand_amount)}</td>
                  </tr>
                  {open === o.order_id
                    ? o.items.map((item) => (
                        <tr key={`${o.order_id}-${item.product_id}-${item.variant_label ?? ''}`} className="table__sub">
                          <td />
                          <td colSpan={3}>
                            {item.product_name}
                            {item.variant_label ? <span className="table__code">{item.variant_label}</span> : null}
                          </td>
                          <td>{fmt.int(item.quantity)}</td>
                          <td>{won(item.line_amount)}</td>
                        </tr>
                      ))
                    : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="상품별 판매" source="real" aside={byProduct.length === 0 ? '-' : `${byProduct.length}개 상품`}>
        {byProduct.length === 0 ? (
          <p className="note">판매된 상품이 없습니다.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>상품</th>
                <th>수량</th>
                <th>주문 수</th>
                <th>매출</th>
                <th>마지막 판매</th>
              </tr>
            </thead>
            <tbody>
              {byProduct.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.name}
                    <span className="table__code">{p.id}</span>
                  </td>
                  <td>{fmt.int(p.quantity)}</td>
                  <td>{fmt.int(p.orders)}</td>
                  <td>{won(p.amount)}</td>
                  <td>{p.last || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title={`최근 ${days}일 동안 안 팔린 상품`}
        source="real"
        aside={unsold === null ? '불러오는 중' : unsold.length === 0 ? '없음' : `${unsold.length}개`}
      >
        {unsold === null ? (
          <p className="note">상품 목록을 받는 중입니다.</p>
        ) : unsold.length === 0 ? (
          <p className="note">등록한 상품이 모두 한 번 이상 팔렸습니다.</p>
        ) : (
          <>
            <ul className="myproducts">
              {unsold.map((p) => (
                <li key={p.product_id} className="myproducts__item">
                  {p.image_url ?? p.images[0] ? (
                    <img className="myproducts__thumb" src={(p.image_url ?? p.images[0]) as string} alt="" loading="lazy" width="64" height="64" />
                  ) : (
                    <span className="myproducts__thumb myproducts__thumb--empty" aria-hidden="true" />
                  )}
                  <div className="myproducts__body">
                    <p className="myproducts__name">{p.product_name}</p>
                    <p className="myproducts__meta">{p.product_id}</p>
                  </div>
                  <p className="myproducts__price">-</p>
                </li>
              ))}
            </ul>
            <p className="note">
              이 기간에 결제가 한 건도 없었다는 뜻입니다. 안 팔린 이유는 여기서 알 수 없습니다 — 노출이 없었는지, 보고
              안 샀는지는 상품 화면에서 봅니다.
            </p>
          </>
        )}
      </Panel>
    </div>
  );
}
