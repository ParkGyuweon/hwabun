import { useMemo, useState } from 'react';
import { Kpi, Panel } from '../components';
import { EXIT_HINT, STEP_KO, fmt } from '../lib/metrics';
import type { ProductMetrics } from '../lib/metrics';
import { useBehavior } from '../lib/useBehavior';

type SortKey = 'interest' | 'cartRate' | 'remove' | 'variant';

/**
 * 상품 (명세 §2-5). 상품마다 "어디서 막히나 · 어디서 나가나 · 왜일 가능성" 을 한 줄로.
 *
 * 병목은 노출→클릭→상세→정보확인→담기 중 브랜드 중앙값 대비 가장 낮은 단계 하나만 지목한다.
 * 이탈 지점은 exit_summary 최빈값이고 힌트는 단정이 아니라 가능성이다 (규칙 R-1c·e·h).
 * P7(미량 성분 경고)은 넣지 않았다. 계약상 태그(highlights)에 성분이 없어 "내세운 성분" 을 정할 수 없다.
 *
 * 마트가 붙으면 수량·전환·제거율은 product_daily_kpi·funnel_daily_kpi 실측이고, 진단 3열(이탈 지점·옵션 왕복·
 * 퀵룩→상세)은 별도 마트(계약 §6-3)가 와야 실측이다. 배지가 둘로 갈릴 수 있다.
 */
export default function ProductsScreen() {
  const { productMetrics, source } = useBehavior();
  const [sort, setSort] = useState<SortKey>('interest');
  const eligible = productMetrics.filter((p) => p.detailViews >= 200);

  const rows = useMemo(() => {
    const list = [...productMetrics];
    const cartRate = (p: ProductMetrics) => (p.detailViews === 0 ? 0 : p.addToCart / p.detailViews);
    switch (sort) {
      case 'cartRate':
        return list.sort((a, b) => cartRate(b) - cartRate(a));
      case 'remove':
        return list.sort((a, b) => b.removeRate - a.removeRate);
      case 'variant':
        return list.sort((a, b) => b.variantSwitches - a.variantSwitches);
      default:
        return list;
    }
  }, [sort, productMetrics]);

  // 병목 단계 분포: 내 라인에서 가장 많이 막히는 단계
  const bottleneckCount = eligible.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.bottleneck]: (acc[p.bottleneck] ?? 0) + 1 }), {});
  const topBottleneck = (Object.entries(bottleneckCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'cart') as ProductMetrics['bottleneck'];
  const exitCount = eligible.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.exitContent]: (acc[p.exitContent] ?? 0) + 1 }), {});
  const topExit = (Object.entries(exitCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'product_hero') as ProductMetrics['exitContent'];
  const friction = eligible.filter((p) => p.variantSwitches >= 3).length;
  const highRemove = eligible.filter((p) => p.removeRate >= 0.3).length;

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label="가장 많이 막히는 단계"
          value={STEP_KO[topBottleneck]}
          sub={`상품 ${bottleneckCount[topBottleneck] ?? 0}개 (상세 200건 이상 ${eligible.length}개 중)`}
          source={source.products}
        />
        <Kpi label="가장 흔한 이탈 지점" value={EXIT_HINT[topExit].ko} sub={`${exitCount[topExit] ?? 0}개 상품 · ${EXIT_HINT[topExit].hint}`} source={source.diagnostics} />
        <Kpi label="옵션 왕복 3회 이상" value={`${friction}개`} sub="용량·색상 사이를 오가는 상품. 막힌 기록" source={source.diagnostics} />
        <Kpi label="담기 후 제거 30% 이상" value={`${highRemove}개`} sub="배송비·묶음 조건 점검 대상" source={source.products} />
      </div>

      <Panel
        title="상품별 진단"
        source={source.products}
        aside={
          <span className="chips chips--inline">
            {(
              [
                ['interest', '관심도'],
                ['cartRate', '전환율'],
                ['remove', '제거율'],
                ['variant', '옵션 왕복'],
              ] as Array<[SortKey, string]>
            ).map(([k, label]) => (
              <button key={k} type="button" className={`chip${sort === k ? ' chip--hit' : ''}`} onClick={() => setSort(k)}>
                {label}
              </button>
            ))}
          </span>
        }
      >
        <div className="table-wrap">
          <table className="data data--diag">
            <thead>
              <tr>
                <th className="is-name">상품</th>
                <th>병목 단계</th>
                <th>이탈 지점</th>
                <th>상세 → 담기</th>
                <th>정보 확인</th>
                <th>옵션 왕복</th>
                <th>퀵룩 → 상세</th>
                <th>담기 후 제거</th>
                <th>표본</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const thin = p.detailViews < 200;
                return (
                  <tr key={p.product.product_id} className={thin ? 'is-thin' : ''}>
                    <td className="is-name" title={p.product.product_name}>
                      {p.product.product_name}
                    </td>
                    <td>
                      <span className={`diag-step diag-step--${p.bottleneck}`}>{STEP_KO[p.bottleneck]}</span>
                    </td>
                    <td>
                      {EXIT_HINT[p.exitContent].ko}
                      <span className="diag-hint">{EXIT_HINT[p.exitContent].hint}</span>
                    </td>
                    <td>
                      <b>{fmt.pct(p.detailViews === 0 ? 0 : p.addToCart / p.detailViews)}</b>
                    </td>
                    <td>{fmt.pct(p.infoRate, 0)}</td>
                    <td className={p.variantSwitches >= 3 ? 'is-warn' : ''}>{p.variantSwitches.toFixed(1)}회</td>
                    <td className={p.quickLookToDetail < 0.4 ? 'is-warn' : ''}>{fmt.pct(p.quickLookToDetail, 0)}</td>
                    <td className={p.removeRate >= 0.3 ? 'is-warn' : ''}>{fmt.pct(p.removeRate, 0)}</td>
                    <td>{fmt.compact(p.detailViews)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="note">
          병목 = 다섯 단계 중 브랜드 중앙값 대비 가장 낮은 하나. 이탈 지점의 힌트는 가능성이고 단정이 아닙니다. 흐린 행은 상세 조회 200건 미만.
          {source.products === 'real' && source.diagnostics === 'mock'
            ? ' 수량·전환·제거율은 마트 실측이고, 이탈 지점·옵션 왕복·퀵룩→상세 세 열은 아직 모의입니다 (product_exit_daily 요청 중).'
            : ''}
        </p>
      </Panel>
    </div>
  );
}
