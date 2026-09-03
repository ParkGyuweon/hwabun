import { BarList, Kpi, Panel } from '../components';
import { fmt, products, reviewStats, troubleRanking } from '../lib/metrics';

/** 소비자 평가와 자극·트러블. 이 화면은 전부 리뷰 2,000건 실측이다 */
export default function ReviewsScreen({
  productId,
  onProductChange,
}: {
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const stats = reviewStats(productId);
  const scopeLabel = productId
    ? (products.find((p) => p.product_id === productId)?.product_name ?? productId)
    : '전체 상품';

  return (
    <div className="stack">
      <div className="scope">
        <label className="scope__field">
          <span className="scope__label">분석 범위</span>
          <select
            value={productId ?? 'all'}
            onChange={(e) => onProductChange(e.target.value === 'all' ? null : e.target.value)}
            aria-label="상품 선택"
          >
            <option value="all">전체 상품</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.product_name} — {p.brand_name}
              </option>
            ))}
          </select>
        </label>
        <p className="scope__meta">
          리뷰 {fmt.int(stats.sampleSize)}건 · 본문 있는 리뷰 {fmt.int(stats.withText)}건
        </p>
        <p className="scope__note">
          상품당 리뷰가 10건이라 개별 상품 수치는 표본이 작다. 비율만 보지 말고 건수를 함께 볼 것.
        </p>
      </div>

      <div className="grid grid--kpi">
        <Kpi label="평균 평점" value={stats.avgRating.toFixed(2)} source="real" />
        <Kpi
          label="추천 비율"
          value={fmt.pct(stats.recommendRate)}
          sub="is_recommended 기준"
          source="real"
        />
        <Kpi
          label="자극 언급"
          value={fmt.pct(stats.irritationRate)}
          sub="따가움·화끈거림·가려움 등"
          source="real"
        />
        <Kpi
          label="트러블 언급"
          value={fmt.pct(stats.troubleRate)}
          sub="브레이크아웃·붉어짐 등"
          source="real"
        />
      </div>

      <div className="grid grid--2">
        <Panel title={`평점 분포 · ${scopeLabel}`} source="real">
          <BarList
            items={stats.ratingDist
              .map((count, i) => ({ label: `${i + 1}점`, value: count }))
              .reverse()}
          />
        </Panel>

        <Panel title="주요 평가 요소" source="real" aside="본문 키워드 매칭">
          <BarList
            items={stats.factors.map((f) => ({
              label: f.label,
              value: f.count,
              hint: fmt.pct(f.share, 0),
            }))}
          />
          <p className="note">
            영문 리뷰 원문에서 표현 패턴을 센 값이다. 형태소 분석이 아니라 근사치이며,
            정식 평가 요소 추출은 리뷰 분석 파이프라인(범위: 데이터)에서 온다.
          </p>
        </Panel>
      </div>

      <Panel title="자극·트러블 언급 상위 상품" source="real" aside="언급 비율 합 기준">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>상품</th>
                <th>자극 언급</th>
                <th>트러블 언급</th>
                <th>표본(본문)</th>
              </tr>
            </thead>
            <tbody>
              {troubleRanking.slice(0, 10).map((row) => (
                <tr key={row.product.product_id}>
                  <td>
                    {row.product.brand_name} — {row.product.product_name}
                  </td>
                  <td>{fmt.pct(row.irritationRate, 0)}</td>
                  <td>{fmt.pct(row.troubleRate, 0)}</td>
                  <td>{row.sampleSize}건</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          "트러블 리뷰 확인 후 이탈률" 같은 행동 교차 지표는 수집 연결 후 이 자리에 붙는다
          (리뷰 열람 content_kind=user_review × exit_summary 조합).
        </p>
      </Panel>
    </div>
  );
}
