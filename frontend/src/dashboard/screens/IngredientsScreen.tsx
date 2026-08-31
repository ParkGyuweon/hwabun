import { BarList, Kpi, Panel } from '../components';
import { cautionPrevalence, fmt, ingredientStats, productMetrics, products } from '../lib/metrics';

/** 성분 구성과 성분 정보에 대한 사용자 관심 */
export default function IngredientsScreen({
  productId,
  onProductChange,
}: {
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const product = products.find((p) => p.product_id === productId) ?? products[0];
  const stats = ingredientStats(product);
  const behavior = productMetrics.find((m) => m.product.product_id === product.product_id);

  return (
    <div className="stack">
      <Panel title="상품 선택" aside="성분 정보는 데이터셋 실측">
        <select
          value={product.product_id}
          onChange={(e) => onProductChange(e.target.value)}
          aria-label="상품 선택"
        >
          {products.map((p) => (
            <option key={p.product_id} value={p.product_id}>
              {p.brand_name} — {p.product_name}
            </option>
          ))}
        </select>
      </Panel>

      <div className="grid grid--kpi">
        <Kpi label="전체 성분 수" value={fmt.int(stats.totalCount)} source="real" />
        <Kpi
          label="확인 필요 성분"
          value={`${stats.cautionCount}종`}
          sub="민감성 피부 체크 항목"
          source="real"
        />
        <Kpi
          label="성분 열람률"
          value={behavior ? fmt.pct(behavior.ingredientViewRate, 0) : '—'}
          sub="상세 조회 대비"
          source="mock"
        />
        <Kpi
          label="성분 텍스트 드래그"
          value={behavior ? fmt.int(Math.round(behavior.detailViews * 0.06)) : '—'}
          sub="text_selection · 검색해 본 성분"
          source="mock"
        />
      </div>

      <div className="grid grid--2">
        <Panel
          title={`확인 필요 성분 · ${product.product_name}`}
          source="real"
          aside="위해성 판정이 아니라 민감성 피부의 일반적 확인 항목"
        >
          <div className="chips">
            {stats.cautions.map((c) => (
              <span key={c.label} className={`chip${c.hit ? ' chip--hit' : ''}`}>
                {c.hit ? '● ' : '○ '}
                {c.label}
              </span>
            ))}
          </div>
          <p className="note">
            ● 포함 / ○ 미검출. 전성분 문자열 패턴 매칭 결과라 표기 변형은 놓칠 수 있다.
          </p>
        </Panel>

        <Panel title="확인 필요 성분 유형별 포함 상품 수" source="real" aside="전체 200개 기준">
          <BarList
            items={cautionPrevalence.map((c) => ({
              label: c.label,
              value: c.count,
              hint: fmt.pct(c.count / products.length, 0),
            }))}
          />
        </Panel>
      </div>

      <Panel title="상품별 성분 관심도 TOP 10" source="mock" aside="성분 열람률 × 상세 조회">
        <BarList
          items={[...productMetrics]
            .sort(
              (a, b) => b.ingredientViewRate * b.detailViews - a.ingredientViewRate * a.detailViews,
            )
            .slice(0, 10)
            .map((m) => ({
              label: `${m.product.brand_name} — ${m.product.product_name}`,
              value: Math.round(m.ingredientViewRate * m.detailViews),
              hint: fmt.pct(m.ingredientViewRate, 0),
            }))}
          format={fmt.compact}
        />
        <p className="note">
          "성분을 오래 봤는데 전환이 낮은 상품"은 성분 설명이 불안을 해소하지 못한다는
          신호다. 콘텐츠 체류(content_kind=ingredient_list) × 전환 교차는 수집 연결 후 붙는다.
        </p>
      </Panel>
    </div>
  );
}
