import { BarList, Kpi, OriginBadge, Panel } from '../components';
import { SKIN_TYPE_KO, fmt, products, reviewStats, reviewsBySkinType, troubleRanking } from '../lib/metrics';

/** 소비자 평가와 자극·트러블. 이 화면은 전부 리뷰 2,000건 실측이다 */
export default function ReviewsScreen({
  productId,
  onProductChange,
}: {
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const stats = reviewStats(productId);
  const bySkin = reviewsBySkinType(productId).filter((r) => r.n >= 5);
  // 결론은 리뷰 20건 이상인 타입끼리만 비교한다. 5건짜리 평점 차이는 우연이다
  const solid = bySkin.filter((r) => r.n >= 20);
  const hi = solid.length > 1 ? solid.reduce((a, b) => (a.avgRating >= b.avgRating ? a : b)) : null;
  const lo = solid.length > 1 ? solid.reduce((a, b) => (a.avgRating <= b.avgRating ? a : b)) : null;
  const split = hi && lo ? hi.avgRating - lo.avgRating : 0;
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
                {p.product_name}
              </option>
            ))}
          </select>
        </label>
        <p className="scope__meta">
          리뷰 {fmt.int(stats.sampleSize)}건 · 본문 있는 리뷰 {fmt.int(stats.withText)}건
        </p>
        <p className="scope__note">상품당 리뷰 10건. 건수를 함께 볼 것.</p>
      </div>

      {hi && lo && split >= 0.5 ? (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            피부 타입별로 평가가 갈립니다 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">
            {SKIN_TYPE_KO[hi.type]} {hi.avgRating.toFixed(1)}점 · {SKIN_TYPE_KO[lo.type]} {lo.avgRating.toFixed(1)}점
          </h2>
          <ul className="verdict__reasons">
            <li>
              {SKIN_TYPE_KO[hi.type]} n={hi.n}, {SKIN_TYPE_KO[lo.type]} n={lo.n}. 차 {split.toFixed(1)}점
            </li>
            {lo.irritationRate > hi.irritationRate + 0.05 ? (
              <li>
                {SKIN_TYPE_KO[lo.type]} 리뷰어의 자극 언급 {fmt.pct(lo.irritationRate, 0)} vs {SKIN_TYPE_KO[hi.type]} {fmt.pct(hi.irritationRate, 0)}
              </li>
            ) : null}
          </ul>
          <p className="verdict__action">
            <span className="verdict__unit">타깃·문구</span>
            타깃 문구와 리뷰 노출 순서를 {SKIN_TYPE_KO[hi.type]} 기준으로 두고, {SKIN_TYPE_KO[lo.type]} 고객에게는 사용 주의 안내를 붙이세요
          </p>
          <p className="verdict__sample">리뷰 {fmt.int(stats.sampleSize)}건 실측</p>
        </section>
      ) : null}

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
          <p className="note">영문 표현 패턴 근사치</p>
        </Panel>
      </div>

      <Panel title="피부 타입별 평점 · 자극 언급" source="real" aside="n<5 제외 · n<20 흐림 · 결론은 n≥20 만">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>리뷰어 피부 타입</th>
                <th>평점</th>
                <th>자극 언급</th>
                <th>리뷰 수</th>
              </tr>
            </thead>
            <tbody>
              {bySkin.map((r) => (
                <tr key={r.type} className={r.n < 20 ? 'is-thin' : ''}>
                  <td>{SKIN_TYPE_KO[r.type]}</td>
                  <td>
                    <b>{r.avgRating.toFixed(2)}</b>
                  </td>
                  <td>{fmt.pct(r.irritationRate, 0)}</td>
                  <td>{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="자극·트러블 언급 상위 상품" source="real" fold aside="언급 비율 합 기준">
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
                  <td className="is-name" title={row.product.product_name}>
                    {row.product.product_name}
                  </td>
                  <td>{fmt.pct(row.irritationRate, 0)}</td>
                  <td>{fmt.pct(row.troubleRate, 0)}</td>
                  <td>{row.sampleSize}건</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
