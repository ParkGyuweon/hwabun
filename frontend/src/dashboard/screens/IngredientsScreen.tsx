import { useMemo, useState } from 'react';
import { OriginBadge, Panel } from '../components';
import { MINOR_WEIGHT, catalogProducts, cautionPrevalence, fmt, ingredientStats, ingredientWeights } from '../lib/metrics';
import { useBrandProducts } from '../lib/useBrandProducts';
import { useBehavior } from '../lib/useBehavior';
import { labelKo } from '../../lib/formLabels';
import { josa } from '../../lib/format';

/** 성분 갭 표의 기본 행 수. 관심 상위 10종이면 "찾는데 없는 성분" 판단에 충분하다 */
const GAP_PREVIEW = 10;

const ko = (name: string) => {
  const k = labelKo(name);
  return k === name ? name : `${k}`;
};

/**
 * 성분. 결론(갭) → 갭 표(I1) → 내 상품 성분 띠(I2) → 주의 성분(I3) 순.
 * 관심(긁기·체류)은 마트(ingredient_weekly_interest)가 있으면 실측, 없으면 빈 표. 보유·위치가중은 전성분 실측.
 *
 * 마트의 관심 셋째 열은 체류 ms 가 아니라 "상품 귀속 점수" 다 (계약 E5). 열 제목과 단위가 그에 따라 바뀐다.
 */
export default function IngredientsScreen({
  brandId,
  brandName,
  productId,
  onProductChange,
}: {
  brandId: string | null;
  brandName: string | null;
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const { ingredientGap, ingredientInterestKind, source } = useBehavior();
  /**
   * 성분은 **내가 등록한 상품의 전성분**이다.
   *
   * 전에는 번들 카탈로그를 `BEHAVIOR_BRAND`(Drunk Elephant)로 걸러 쓰고, 고른 상품이 없으면 그 목록의
   * 첫 상품으로 물러났다. 어느 브랜드로 로그인하든 남의 상품 전성분이 "실측" 배지를 달고 떴다는 뜻이다.
   * 사장님은 그것을 내 상품 성분으로 읽고 처방을 판단한다.
   *
   * 물러날 곳을 두지 않는다. 내 상품이 없으면 없다고 적는다.
   */
  const { products: mine, failed } = useBrandProducts(brandId, brandName);
  // 고른 것이 없으면 **내 상품 중** 첫 번째. 다른 브랜드로는 넘어가지 않는다
  const product = mine ? (mine.find((p) => p.product_id === productId) ?? mine[0] ?? null) : null;
  const stats = useMemo(() => (product ? ingredientStats(product) : null), [product]);
  const weights = useMemo(() => (product ? ingredientWeights(product) : new Map<string, number>()), [product]);

  const gaps = ingredientGap.filter((r) => r.gap);
  const top10 = ingredientGap.filter((r) => r.rank <= 10);
  const noInterest = ingredientGap.length === 0;
  /*
   * 표는 갭 행이 위로 정렬돼 있어 답이 첫 열 줄 안에 있다. 30종을 다 펼쳐 두면 화면이 표 하나로
   * 덮이고 정작 봐야 할 갭 행이 스크롤에 묻힌다. 기본은 10행, 나머지는 눌러서 편다.
   */
  const [showAllGap, setShowAllGap] = useState(false);
  const shownGap = showAllGap ? ingredientGap : ingredientGap.slice(0, GAP_PREVIEW);
  const ownedTop = top10.filter((r) => r.owned.length > 0).length;

  const band = [...weights.entries()]
    .map(([name, weight]) => ({ name, weight, tagged: weight === 1 }))
    .sort((a, b) => b.weight - a.weight);
  const minorTagged = band.filter((b) => !b.tagged && b.weight <= MINOR_WEIGHT);

  const thirdCol = ingredientInterestKind === 'score' ? '상품에서 본 점수' : '머문 시간';
  const third = (v: number) => (ingredientInterestKind === 'score' ? fmt.int(Math.round(v)) : `${(v / 1000).toFixed(1)}초`);

  /**
   * 내 상품이 없으면 성분 화면은 그릴 것이 없다. 번들 카탈로그로 대신 채우지 않는다 —
   * 남의 상품 성분을 내 것으로 읽게 만드는 것이 이 화면의 원래 문제였다.
   */
  if (mine === null || !product || !stats) {
    const why = failed ? '상품 목록을 읽지 못했습니다' : mine === null ? '상품 목록을 받는 중입니다' : '등록한 상품이 없습니다';
    return (
      <div className="stack">
        <Panel title="내 상품 성분 띠" origin="mine" source="real">
          <p className="fbx-empty">{why}</p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="stack">
      {/* 관심 순위는 플랫폼 전체 값(E5 에 brand 축 없음). 보유 판정만 내 전성분이다 → 전체 종합(핑크) */}
      <section className="verdict verdict--shared">
        <p className="verdict__eyebrow">
          고객이 찾는데 내 상품에 없는 성분 <OriginBadge kind="shared" />
        </p>
        <h2 className="verdict__headline">
          {noInterest
            ? '고객이 찾은 성분 기록이 아직 없습니다'
            : gaps.length === 0
              ? '고객 관심 상위 10 성분을 모두 갖고 있습니다'
              : gaps
                  .slice(0, 3)
                  .map((g) => ko(g.name))
                  .join(' · ')}
        </h2>
        <p className="verdict__reason">
          {noInterest
            ? '기록이 쌓이면 여기에 나옵니다'
            : `상위 10 중 있음 ${ownedTop} · 없음 ${Math.max(0, Math.min(10, top10.length) - ownedTop)}${
                gaps.length > 3 ? ` · 그 외 ${gaps.length - 3}종` : ''
              }`}
        </p>
        {gaps.length > 0 ? (
          <p className="verdict__action" title="상세페이지에는 대신 쓴 성분이 무엇인지 설명해 주세요">
            {josa(ko(gaps[0].name), '이/가')} 든 상품을 검토해 보세요
          </p>
        ) : null}
        <p className="verdict__sample">
          {source.ingredients === 'real' ? '찾는 순위는 쇼핑몰 전체 고객 기준 · 있고 없고는 내 상품 전성분 기준' : '찾는 순위는 아직 기록 없음 · 있고 없고는 내 상품 전성분 기준'}
        </p>
      </section>

      <Panel
        title="고객이 찾는 성분과 내 상품 성분 맞춰 보기"
        origin="shared"
        source={source.ingredients}
        aside={noInterest ? undefined : `고객이 많이 찾는 순서 ${ingredientGap.length}종 · 내 상품에 없는 성분이 위`}
      >
        <div className="table-wrap">
          <table className="fbx-table gap-table">
            <thead>
              <tr>
                <th className="is-num">순위</th>
                <th>성분</th>
                <th className="is-num" title="고객이 성분 이름을 마우스로 긁거나 복사한 횟수 (쇼핑몰 전체)">
                  긁은 횟수
                </th>
                <th
                  className="is-num"
                  title={
                    ingredientInterestKind === 'score'
                      ? '그 성분이 든 상품을 본 행동을 성분마다 나눠 매긴 점수 (쇼핑몰 전체)'
                      : '그 성분 부분에 머문 시간 (쇼핑몰 전체)'
                  }
                >
                  {thirdCol}
                </th>
                <th title="내 상품 전성분 기준">내 상품</th>
                <th style={{ width: '18%' }}>함량 위치</th>
              </tr>
            </thead>
            <tbody>
              {shownGap.length === 0 ? (
                <tr>
                  <td colSpan={6} className="fbx-empty">
                    아직 기록이 없습니다
                  </td>
                </tr>
              ) : null}
              {shownGap.map((r) => (
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
                      <span className="gap-flag gap-flag--gap" title="고객 관심 상위 10인데 내 상품에는 없습니다">
                        찾는데 없음
                      </span>
                    ) : r.owned.length === 0 ? (
                      <span className="gap-flag">없음</span>
                    ) : (
                      <span title={r.owned.map((o) => o.product.product_name).join(', ')}>
                        {r.owned.length}개
                        {r.minor ? (
                          <span className="gap-flag gap-flag--minor" title="전성분 뒤쪽에만 있어 함량이 적을 가능성">
                            미량
                          </span>
                        ) : null}
                      </span>
                    )}
                  </td>
                  <td>
                    {r.owned.length > 0 ? (
                      <span className="fbx-table__track" title="막대가 길수록 전성분 앞쪽에 있습니다 (함량이 많을수록 앞에 적습니다)">
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
        {/*
          갭이 위로 정렬돼 있어 답은 첫 열 줄 안에 있다. 30행을 다 펼쳐 두면 화면이 표 하나로 덮이고,
          정작 봐야 할 갭 행이 스크롤에 묻힌다. 나머지는 접되 몇 개가 더 있는지는 버튼에 적는다.
        */}
        {ingredientGap.length > GAP_PREVIEW ? (
          <button type="button" className="more-btn" onClick={() => setShowAllGap((v) => !v)}>
            {showAllGap
              ? '상위 10종만 보기'
              : `나머지 ${ingredientGap.length - GAP_PREVIEW}종 더 보기`}
          </button>
        ) : null}
      </Panel>

      <div className="grid grid--2">
        <Panel title="내 상품 성분 띠" origin="mine" source="real" fold aside={<span title="막대가 길수록 전성분 앞쪽에 있어 함량이 많은 편">길수록 함량 많은 편</span>}>
          <div className="scope scope--inline">
            <label className="scope__field">
              <span className="scope__label">상품</span>
              <select value={product.product_id} onChange={(e) => onProductChange(e.target.value)} aria-label="성분을 볼 상품 고르기">
                {mine.map((p) => (
                  <option key={p.product_id} value={p.product_id}>
                    {p.product_name}
                  </option>
                ))}
              </select>
            </label>
            <p className="scope__meta">
              전성분 {fmt.int(stats.totalCount)}개 · 자주 찾는 성분 {band.length}개
            </p>
          </div>
          {band.length === 0 ? (
            <p className="fbx-empty">자주 찾는 성분이 없습니다</p>
          ) : (
            <ul className="band">
              {band.map((b) => (
                <li key={b.name} className={`band__row${!b.tagged && b.weight <= MINOR_WEIGHT ? ' is-minor' : ''}`}>
                  <span className="band__name">
                    {ko(b.name)}
                    {b.tagged ? (
                      <span className="gap-flag" title="상품 등록 때 대표 성분으로 내세운 성분">
                        대표
                      </span>
                    ) : null}
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
                  {/* 0.73 같은 숫자는 사장님이 읽을 값이 아니다. 전성분에서 어디쯤 있는지로 풀어 쓴다 */}
                  <span className="band__w" title="전성분에서 앞에 적힐수록 많이 든 편입니다">
                    {b.tagged ? '' : b.weight > 0.66 ? '앞쪽' : b.weight > MINOR_WEIGHT ? '중간' : '뒤쪽 · 적은 양'}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {minorTagged.length > 0 ? (
            <p className="note" title="광고 문구에 내세우면 근거 자료를 요구받을 수 있습니다">
              미량 추정 {minorTagged.map((mt) => ko(mt.name)).join(' · ')} · 광고 문구 주의
            </p>
          ) : null}
        </Panel>

        <Panel
          title="확인이 필요한 성분"
          origin="shared"
          source="real"
          fold
          aside={<span title={`${product.product_name} · 위해 판정이 아니라 민감한 피부 고객이 자주 확인하는 성분입니다`}>전체 {catalogProducts.length}개 상품과 비교</span>}
        >
          <table className="fbx-table">
            <thead>
              <tr>
                <th>성분</th>
                <th>이 상품</th>
                <th className="is-num" title="쇼핑몰 전체 상품 중 이 성분이 든 상품 수와 비율">
                  든 상품 수
                </th>
              </tr>
            </thead>
            <tbody>
              {cautionPrevalence.map((c) => {
                const hit = stats.cautions.find((x) => x.label === c.label)?.hit ?? false;
                return (
                  <tr key={c.label}>
                    <td>{c.label}</td>
                    <td>
                      {hit ? (
                        <span className="gap-flag gap-flag--minor">들어 있음</span>
                      ) : (
                        <span className="gap-flag" title="이 상품 전성분에는 없습니다">
                          없음
                        </span>
                      )}
                    </td>
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
