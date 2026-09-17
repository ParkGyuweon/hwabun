import { Fragment, useEffect, useMemo, useState } from 'react';
import { BarList, Kpi, Panel } from '../components';
import { fmt } from '../lib/metrics';
import { fetchSellerOrders } from '../../lib/shopApi';
import type { SellerOrder } from '../../lib/shopApi';
import { rangeOf } from '../lib/martApi';

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
export default function OrdersScreen({ brandId, days }: { brandId: string | null; days: number }) {
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
    return { revenue, units, count: list.length, average: list.length === 0 ? 0 : Math.round(revenue / list.length) };
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

  /** 상품별 판매. 행동 화면의 "관심도" 와 다르다 — 이건 실제 결제다 */
  const byProduct = useMemo(() => {
    const acc = new Map<string, { name: string; quantity: number; amount: number; orders: Set<string> }>();
    for (const o of orders ?? []) {
      for (const item of o.items) {
        const cur = acc.get(item.product_id) ?? { name: item.product_name, quantity: 0, amount: 0, orders: new Set<string>() };
        cur.quantity += item.quantity;
        cur.amount += item.line_amount;
        cur.orders.add(o.order_id);
        acc.set(item.product_id, cur);
      }
    }
    return [...acc.entries()]
      .map(([id, v]) => ({ id, name: v.name, quantity: v.quantity, amount: v.amount, orders: v.orders.size }))
      .sort((a, b) => b.amount - a.amount);
  }, [orders]);

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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
