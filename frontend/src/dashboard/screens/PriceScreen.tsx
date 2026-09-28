import { useEffect, useMemo, useState } from 'react';
import { Kpi, Panel } from '../components';
import { fetchPricePosition } from '../lib/martApi';
import type { PricePositionPayload, PricePositionRow } from '../lib/martApi';
import { categoryKo } from '../../lib/localize';

/**
 * 시장 · 가격 (GET /api/seller/dashboard/price-position, 2026-09-28).
 *
 * 내 상품 가격을 같은 카테고리 상품들의 중간 가격과 나란히 둔다. 쇼핑몰 상품 목록에서 바로 세는 값이라
 * 기간이 없고, 브랜드는 로그인 토큰의 브랜드다. 같은 카테고리 상품이 3개 미만이면 서버가 전체 중간 가격으로
 * 대신 비교해 주고(`global_fallback`), 화면은 그 줄을 흐리게 그려 "참고만" 으로 읽히게 한다.
 */

/** ±10% 안이면 "비슷함". 그 밖이면 비싼 편·싼 편 */
const NEAR_PCT = 10;

const won = (n: number | null) => (n === null ? '-' : `${Math.round(n).toLocaleString('ko-KR')}원`);
const diffText = (pct: number) => (Math.abs(pct) < 0.5 ? '같음' : `${pct > 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)}%`);

export default function PriceScreen({ brandId }: { brandId: string | null }) {
  // undefined = 받는 중, null = 못 받음
  const [data, setData] = useState<PricePositionPayload | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    setData(undefined);
    void fetchPricePosition().then((d) => {
      if (alive) setData(d);
    });
    return () => {
      alive = false;
    };
  }, [brandId]);

  const rows = useMemo(
    () =>
      [...(data?.products ?? [])].sort(
        (a, b) => Math.abs(b.price_difference_pct ?? -1) - Math.abs(a.price_difference_pct ?? -1),
      ),
    [data],
  );
  const compared = rows.filter((r): r is PricePositionRow & { price_difference_pct: number } => r.price_difference_pct !== null);
  // 칸의 결론은 같은 카테고리와 비교한 상품만으로 낸다. 전체 상품 기준 비교는 카테고리가 달라 표에만 흐리게 둔다
  const judged = compared.filter((r) => r.is_sample_sufficient);
  const pricey = judged.filter((r) => r.price_difference_pct > NEAR_PCT);
  const cheap = judged.filter((r) => r.price_difference_pct < -NEAR_PCT);
  const widest = judged[0] ?? null;
  const source = data ? 'real' : 'none';
  const empty = data === undefined ? '불러오는 중' : data === null ? '불러오지 못했습니다' : '가격이 등록된 상품이 없습니다';

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label="카테고리보다 비싼 편"
          value={judged.length ? `${pricey.length}개` : '-'}
          sub={judged.length ? `중간 가격보다 ${NEAR_PCT}% 넘게 비쌈` : compared.length ? '같은 카테고리 상품이 아직 적음' : empty}
          source={source}
          origin="shared"
        />
        <Kpi
          label="카테고리보다 싼 편"
          value={judged.length ? `${cheap.length}개` : '-'}
          sub={judged.length ? `중간 가격보다 ${NEAR_PCT}% 넘게 쌈` : compared.length ? '같은 카테고리 상품이 아직 적음' : empty}
          source={source}
          origin="shared"
        />
        <Kpi
          label="가격 차이가 가장 큰 상품"
          value={widest ? widest.product_name : '-'}
          sub={widest ? `${categoryKo(widest.secondary_category ?? '')} 중간 가격보다 ${diffText(widest.price_difference_pct)}` : compared.length ? '같은 카테고리 상품이 아직 적음' : empty}
          source={source}
          origin="shared"
        />
      </div>

      <Panel title="내 가격과 카테고리 중간 가격" source={source} origin="shared" aside="쇼핑몰에 올라온 전체 상품과 비교">
        <div className="table-wrap">
          <table className="table table--price">
            <thead>
              <tr>
                <th>상품</th>
                <th>카테고리</th>
                <th>내 가격</th>
                <th title="같은 카테고리 상품을 가격순으로 세웠을 때 가운데 가격">중간 가격</th>
                <th title="(내 가격 − 중간 가격) ÷ 중간 가격">차이</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="note">
                    {empty}
                  </td>
                </tr>
              ) : null}
              {rows.map((r) => {
                const thin = !r.is_sample_sufficient;
                const pct = r.price_difference_pct;
                return (
                  <tr
                    key={r.product_id}
                    className={thin ? 'is-thin' : ''}
                    title={thin ? `같은 카테고리 상품이 ${r.category_product_count}개뿐이라 전체 상품의 중간 가격과 비교했습니다` : undefined}
                  >
                    <td>{r.product_name}</td>
                    <td>{r.secondary_category ? categoryKo(r.secondary_category) : '-'}</td>
                    <td>{won(r.price_krw)}</td>
                    <td>
                      {won(r.reference_median_krw)}
                      <span className="diag-hint">{thin ? '전체 상품 기준' : `${r.category_product_count}개 기준`}</span>
                    </td>
                    <td className={pct !== null && pct > NEAR_PCT ? 'is-warn' : ''}>
                      <strong>{pct === null ? '-' : diffText(pct)}</strong>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="note">비싸다고 나쁜 것은 아닙니다. 상세페이지가 그 차이를 설명하는지 함께 보세요.</p>
      </Panel>
    </div>
  );
}
