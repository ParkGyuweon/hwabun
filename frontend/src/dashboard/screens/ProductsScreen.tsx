import { BarList, Panel } from '../components';
import { fmt, productMetrics } from '../lib/metrics';

const TABLE_SIZE = 30;

/** 상품별 관심 → 전환 성과. 표가 중심이고 그림은 보조다 */
export default function ProductsScreen() {
  const rows = productMetrics.slice(0, TABLE_SIZE);

  return (
    <div className="stack">
      <Panel title="구매 전환율 TOP 10" source="mock" aside="상세 조회 대비 장바구니">
        <BarList
          items={[...productMetrics]
            .filter((m) => m.detailViews >= 200)
            .sort((a, b) => b.addToCart / b.detailViews - a.addToCart / a.detailViews)
            .slice(0, 10)
            .map((m) => ({
              label: `${m.product.brand_name} — ${m.product.product_name}`,
              value: (m.addToCart / m.detailViews) * 100,
              hint: `표본 ${fmt.compact(m.detailViews)}`,
            }))}
          format={(v) => `${v.toFixed(1)}%`}
        />
        <p className="note">상세 조회 200건 미만 상품은 제외했다. 표본이 작으면 비율이 요동친다.</p>
      </Panel>

      <Panel
        title={`상품별 성과 · 관심도순 상위 ${TABLE_SIZE}`}
        source="mock"
        aside={`전체 ${productMetrics.length}개 상품`}
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>상품</th>
                <th>노출</th>
                <th>클릭</th>
                <th>클릭률</th>
                <th>상세 조회</th>
                <th>퀵룩</th>
                <th>성분 열람률</th>
                <th>리뷰 열람률</th>
                <th>담기</th>
                <th>전환율</th>
                <th>재고(제거)</th>
                <th>관심도</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.product.product_id}>
                  <td title={m.product.product_name}>
                    {m.product.brand_name} — {m.product.product_name}
                  </td>
                  <td>{fmt.compact(m.impressions)}</td>
                  <td>{fmt.compact(m.clicks)}</td>
                  <td>{fmt.pct(m.clicks / m.impressions)}</td>
                  <td>{fmt.compact(m.detailViews)}</td>
                  <td>{fmt.int(m.quickLooks)}</td>
                  <td>{fmt.pct(m.ingredientViewRate, 0)}</td>
                  <td>{fmt.pct(m.reviewViewRate, 0)}</td>
                  <td>{fmt.int(m.addToCart)}</td>
                  <td>{fmt.pct(m.addToCart / m.detailViews)}</td>
                  <td>{fmt.int(m.removedFromCart)}</td>
                  <td>
                    <strong>{fmt.int(m.interestScore)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          퀵룩은 상세로 가지 않고 요약 창만 연 횟수다. 재고(제거)는 담았다 뺀
          횟수로, 상품을 특정하는 가장 명확한 부정 신호다.
        </p>
      </Panel>
    </div>
  );
}
