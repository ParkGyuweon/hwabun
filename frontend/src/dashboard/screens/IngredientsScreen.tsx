import { useMemo } from 'react';
import { Panel } from '../components';
import { MINOR_WEIGHT, catalogProducts, cautionPrevalence, fmt, ingredientStats, ingredientWeights, products } from '../lib/metrics';
import { useBehavior } from '../lib/useBehavior';
import { labelKo } from '../../lib/formLabels';

const ko = (name: string) => {
  const k = labelKo(name);
  return k === name ? name : `${k}`;
};

/**
 * 성분. 결론(갭) → 갭 표(I1) → 내 상품 성분 띠(I2) → 주의 성분(I3) 순.
 * 관심(긁기·체류)은 마트(ingredient_weekly_interest)가 있으면 실측, 없으면 모의. 보유·위치가중은 전성분 실측.
 *
 * 마트의 관심 셋째 열은 체류 ms 가 아니라 "상품 귀속 점수" 다 (계약 E5). 열 제목과 단위가 그에 따라 바뀐다.
 */
export default function IngredientsScreen({
  productId,
  onProductChange,
}: {
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const { ingredientGap, ingredientInterestKind, source } = useBehavior();
  const product = products.find((p) => p.product_id === productId) ?? products[0];
  const stats = ingredientStats(product);
  const weights = useMemo(() => ingredientWeights(product), [product]);

  const gaps = ingredientGap.filter((r) => r.gap);
  const top10 = ingredientGap.filter((r) => r.rank <= 10);
  const ownedTop = top10.filter((r) => r.owned.length > 0).length;

  const band = [...weights.entries()]
    .map(([name, weight]) => ({ name, weight, tagged: weight === 1 }))
    .sort((a, b) => b.weight - a.weight);
  const minorTagged = band.filter((b) => !b.tagged && b.weight <= MINOR_WEIGHT);

  const thirdCol = ingredientInterestKind === 'score' ? '상품 귀속' : '체류';
  const third = (v: number) => (ingredientInterestKind === 'score' ? fmt.int(Math.round(v)) : `${(v / 1000).toFixed(1)}초`);

  return (
    <div className="stack">
      <section className="verdict">
        <p className="verdict__eyebrow">찾는데 없는 성분</p>
        <h2 className="verdict__headline">
          {gaps.length === 0
            ? '관심 상위 10 성분을 모두 갖고 있습니다'
            : gaps
                .slice(0, 3)
                .map((g) => ko(g.name))
                .join(' · ')}
        </h2>
        <p className="verdict__reason">
          관심 상위 10 중 보유 {ownedTop} · 미보유 {Math.max(0, Math.min(10, top10.length) - ownedTop)}
          {gaps.length > 3 ? ` · 그 외 ${gaps.length - 3}종` : ''}
        </p>
        {gaps.length > 0 ? (
          <p className="verdict__action">제품·처방: {ko(gaps[0].name)} 라인 검토 · 상세페이지: 대체 성분 설명</p>
        ) : null}
        <p className="verdict__sample">{source.ingredients === 'real' ? '관심은 마트 실측 (플랫폼 전체) · 보유는 전성분 실측' : '관심은 모의 · 보유는 전성분 실측'}</p>
      </section>

      <Panel title="성분 갭 표" source={source.ingredients} aside={`관심 순 ${ingredientGap.length}종 · 갭 행 위`}>
        <div className="table-wrap">
          <table className="fbx-table gap-table">
            <thead>
              <tr>
                <th className="is-num">관심</th>
                <th>성분</th>
                <th className="is-num">긁기</th>
                <th className="is-num">{thirdCol}</th>
                <th>내 라인</th>
                <th style={{ width: '18%' }}>함량 위치</th>
              </tr>
            </thead>
            <tbody>
              {ingredientGap.map((r) => (
                <tr key={r.name} className={r.gap ? 'is-gap' : r.minor ? 'is-minor' : ''}>
                  <td className="is-num">{r.rank}</td>
                  <td>
                    <span className="fbx-table__name">{ko(r.name)}</span>
                    {ko(r.name) !== r.name ? <span className="fbx-table__desc">{r.name}</span> : null}
                  </td>
                  <td className="is-num">{fmt.int(r.scrapeCount)}</td>
                  <td className="is-num">{third(r.dwellMs)}</td>
                  <td>
                    {r.gap ? (
                      <span className="gap-flag gap-flag--gap">갭</span>
                    ) : r.owned.length === 0 ? (
                      <span className="gap-flag">없음</span>
                    ) : (
                      <span title={r.owned.map((o) => o.product.product_name).join(', ')}>
                        {r.owned.length}개{r.minor ? <span className="gap-flag gap-flag--minor">미량</span> : null}
                      </span>
                    )}
                  </td>
                  <td>
                    {r.owned.length > 0 ? (
                      <span className="fbx-table__track">
                        <span
                          className="fbx-table__bar"
                          style={{
                            width: `${r.maxWeight * 100}%`,
                            ['--seg' as string]: r.minor ? 'var(--accent)' : 'var(--brand)',
                          }}
                        />
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {ingredientInterestKind === 'score' ? (
          <p className="note">
            긁기 = 고객이 성분 이름을 직접 드래그·복사한 점수(direct_match_score). 상품 귀속 = 그 성분이 든 상품에서 한
            행동을 성분으로 나눈 점수. 둘 다 플랫폼 전체 기준이고, 내 라인 보유만 내 상품에서 셉니다.
          </p>
        ) : null}
      </Panel>

      <div className="grid grid--2">
        <Panel title="내 상품 성분 띠" source="real" aside="앞쪽일수록 함량 높음">
          <div className="scope scope--inline">
            <label className="scope__field">
              <span className="scope__label">상품</span>
              <select value={product.product_id} onChange={(e) => onProductChange(e.target.value)} aria-label="상품 선택">
                {products.map((p) => (
                  <option key={p.product_id} value={p.product_id}>
                    {p.product_name}
                  </option>
                ))}
              </select>
            </label>
            <p className="scope__meta">전성분 {fmt.int(stats.totalCount)} · 핵심 성분 {band.length}</p>
          </div>
          {band.length === 0 ? (
            <p className="fbx-empty">핵심 성분 30종 중 검출된 것이 없습니다.</p>
          ) : (
            <ul className="band">
              {band.map((b) => (
                <li key={b.name} className={`band__row${!b.tagged && b.weight <= MINOR_WEIGHT ? ' is-minor' : ''}`}>
                  <span className="band__name">
                    {ko(b.name)}
                    {b.tagged ? <span className="gap-flag">태그</span> : null}
                  </span>
                  <span className="fbx-table__track">
                    <span
                      className="fbx-table__bar"
                      style={{
                        width: `${b.weight * 100}%`,
                        ['--seg' as string]: !b.tagged && b.weight <= MINOR_WEIGHT ? 'var(--accent)' : 'var(--brand)',
                      }}
                    />
                  </span>
                  <span className="band__w">{b.weight.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
          {minorTagged.length > 0 ? (
            <p className="note">미량: {minorTagged.map((mt) => ko(mt.name)).join(' · ')} · 강조 문구에 쓰면 실증 부담</p>
          ) : null}
        </Panel>

        <Panel title="주의 성분" source="real" aside={`${product.product_name} · 플랫폼 ${catalogProducts.length}개 대비`}>
          <table className="fbx-table">
            <thead>
              <tr>
                <th>성분</th>
                <th>이 상품</th>
                <th className="is-num">포함 상품</th>
              </tr>
            </thead>
            <tbody>
              {cautionPrevalence.map((c) => {
                const hit = stats.cautions.find((x) => x.label === c.label)?.hit ?? false;
                return (
                  <tr key={c.label}>
                    <td>{c.label}</td>
                    <td>{hit ? <span className="gap-flag gap-flag--minor">포함</span> : <span className="gap-flag">–</span>}</td>
                    <td className="is-num">
                      {c.count} <small>({fmt.pct(c.count / catalogProducts.length, 0)})</small>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
