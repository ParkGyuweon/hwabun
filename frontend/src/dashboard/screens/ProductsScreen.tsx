import { useMemo, useState } from 'react';
import { Kpi, Panel } from '../components';
import { STEP_KO, exitHint, fmt } from '../lib/metrics';
import type { ProductMetrics } from '../lib/metrics';
import { useBehavior } from '../lib/useBehavior';
import MyProducts from './MyProducts';

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
function repurchaseCell(r: { buyerCount: number; rate: number | null } | undefined): string {
  if (!r || r.rate === null) return '-';
  return `${fmt.pct(r.rate, 0)} (${r.buyerCount}명)`;
}

/** 이 수보다 적게 상세를 본 상품은 판단에서 빼고 흐리게 그린다 */
const MIN_DETAIL_VIEWS = 200;

export default function ProductsScreen({ brandId, brandName }: { brandId: string | null; brandName: string | null }) {
  const { productMetrics, repurchase, source } = useBehavior();
  const showRepurchase = source.purchase === 'real' && repurchase !== null;
  const [sort, setSort] = useState<SortKey>('interest');
  const eligible = productMetrics.filter((p) => p.detailViews >= MIN_DETAIL_VIEWS);
  const noDiag = source.diagnostics === 'none';

  const rows = useMemo(() => {
    const list = [...productMetrics];
    switch (sort) {
      case 'cartRate':
        return list.sort((a, b) => b.cartRate - a.cartRate);
      case 'remove':
        return list.sort((a, b) => b.removeRate - a.removeRate);
      case 'variant':
        // 값이 없는 상품은 뒤로. 모르는 것을 0 으로 세면 '왕복이 적은 상품' 으로 둔갑한다
        return list.sort((a, b) => (b.variantSwitches ?? -1) - (a.variantSwitches ?? -1));
      default:
        return list;
    }
  }, [sort, productMetrics]);

  // 병목 단계 분포: 내 라인에서 가장 많이 막히는 단계
  const bottleneckCount = eligible.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.bottleneck]: (acc[p.bottleneck] ?? 0) + 1 }), {});
  // 셀 상품이 없으면 "가장 많이 막히는 단계"도 없다. 'cart' 로 채우면 없는 병목이 생긴다 (2026-09-18)
  const topBottleneck = (Object.entries(bottleneckCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null) as ProductMetrics['bottleneck'] | null;
  // 이탈 지점을 모르는 상품은 세지 않는다. 임의의 기본값('product_hero')으로 채우면 없는 결론이 생긴다
  const exitCount = eligible.reduce<Record<string, number>>(
    (acc, p) => (p.exitContent ? { ...acc, [p.exitContent]: (acc[p.exitContent] ?? 0) + 1 } : acc),
    {},
  );
  const topExit = (Object.entries(exitCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null) as ProductMetrics['exitContent'];
  const friction = eligible.filter((p) => (p.variantSwitches ?? 0) >= 3).length;
  const highRemove = eligible.filter((p) => p.removeRate >= 0.3).length;

  const tooFew =
    productMetrics.length === 0
      ? source.products === 'none'
        ? '상품별 행동 기록을 아직 받지 못했습니다'
        : '이 기간에 상세를 본 상품이 없습니다'
      : `상세를 ${MIN_DETAIL_VIEWS}번 이상 본 상품이 아직 없어 판단하지 않습니다`;

  return (
    <div className="stack">
      {/* 등록 정보라 마트와 무관하다. 행동 로그가 없는 브랜드도 여기서는 자기 상품을 본다 */}
      <MyProducts brandId={brandId} brandName={brandName} />
      <div className="grid grid--kpi">
        <Kpi
          label="가장 많이 막히는 단계"
          value={topBottleneck ? STEP_KO[topBottleneck] : '-'}
          sub={
            topBottleneck
              ? `상품 ${bottleneckCount[topBottleneck] ?? 0}개가 여기서 막힙니다 · 상세를 ${MIN_DETAIL_VIEWS}번 이상 본 상품 ${eligible.length}개 중`
              : tooFew
          }
          source={source.products}
        />
        <Kpi
          label="고객이 가장 많이 나간 자리"
          value={topExit ? exitHint(topExit).ko : '-'}
          sub={
            topExit
              ? `상품 ${exitCount[topExit] ?? 0}개${exitHint(topExit).hint ? ` · ${exitHint(topExit).hint}` : ''}`
              : noDiag
                ? '어디서 나갔는지 계산이 아직 준비되지 않았습니다. 준비되면 자동으로 채워집니다'
                : eligible.length === 0
                  ? tooFew
                  : '나간 자리가 기록된 상품이 아직 없습니다'
          }
          source={source.diagnostics}
        />
        <Kpi
          label="옵션을 3번 넘게 오간 상품"
          value={noDiag ? '-' : `${friction}개`}
          sub={
            noDiag
              ? '옵션 고르기 기록 계산이 아직 준비되지 않았습니다'
              : '용량·색상을 골랐다 바꾸기를 반복한 상품. 고르기 어렵다는 신호입니다'
          }
          source={source.diagnostics}
        />
        <Kpi
          label="담았다가 뺀 고객이 30% 넘는 상품"
          value={`${highRemove}개`}
          sub={eligible.length === 0 ? tooFew : '장바구니에 넣고 다시 뺀 고객이 10명 중 3명이 넘는 상품. 배송비·묶음 조건을 점검해 보세요'}
          source={source.products}
        />
      </div>

      <Panel
        title="상품별 진단"
        source={source.products}
        aside={
          <span className="chips chips--inline">
            {(
              [
                ['interest', '관심 많은 순'],
                ['cartRate', '담기 비율 순'],
                ['remove', '담았다 뺀 비율 순'],
                ['variant', '옵션 많이 오간 순'],
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
                <th>막히는 단계</th>
                <th>나간 자리</th>
                <th>상세 본 뒤 담기</th>
                <th>성분·리뷰 확인</th>
                <th>옵션 오간 횟수</th>
                <th>빠른 보기 → 상세</th>
                <th>담았다 뺌</th>
                {showRepurchase ? <th>다시 산 고객</th> : null}
                <th>상세 본 방문</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={showRepurchase ? 10 : 9} className="note">
                    {source.products === 'none'
                      ? '상품별 행동 기록을 아직 받지 못했습니다. 고객이 내 상품을 보기 시작하면 상품마다 한 줄씩 채워집니다.'
                      : '이 기간에 고객이 상세를 본 내 상품이 없습니다.'}
                  </td>
                </tr>
              ) : null}
              {rows.map((p) => {
                const thin = p.detailViews < MIN_DETAIL_VIEWS;
                return (
                  <tr key={p.product.product_id} className={thin ? 'is-thin' : ''}>
                    <td className="is-name" title={p.product.product_name}>
                      {p.product.product_name}
                    </td>
                    <td>
                      <span className={`diag-step diag-step--${p.bottleneck}`}>{STEP_KO[p.bottleneck]}</span>
                    </td>
                    <td>
                      {p.exitContent ? exitHint(p.exitContent).ko : '-'}
                      {p.exitContent && exitHint(p.exitContent).hint ? <span className="diag-hint">{exitHint(p.exitContent).hint}</span> : null}
                    </td>
                    <td>
                      <b>{fmt.pct(p.cartRate)}</b>
                    </td>
                    <td>{fmt.pct(p.infoRate, 0)}</td>
                    {/* 모르는 값은 하이픈이다. 0 으로 적으면 "왕복이 없다" 로 읽힌다 */}
                    <td className={(p.variantSwitches ?? 0) >= 3 ? 'is-warn' : ''} title={p.variantSwitches === null ? '계산이 아직 준비되지 않았습니다' : '방문 한 번에 옵션을 바꾼 평균 횟수'}>
                      {p.variantSwitches === null ? '-' : `${p.variantSwitches.toFixed(1)}회`}
                    </td>
                    <td
                      className={p.quickLookToDetail !== null && p.quickLookToDetail < 0.4 ? 'is-warn' : ''}
                      title={p.quickLookToDetail === null ? '계산이 아직 준비되지 않았습니다' : '빠른 보기를 연 고객 중 상세까지 들어온 비율'}
                    >
                      {p.quickLookToDetail === null ? '-' : fmt.pct(p.quickLookToDetail, 0)}
                    </td>
                    <td className={p.removeRate >= 0.3 ? 'is-warn' : ''}>{fmt.pct(p.removeRate, 0)}</td>
                    {showRepurchase ? <td>{repurchaseCell(repurchase?.products.get(p.product.product_id))}</td> : null}
                    <td>{fmt.compact(p.detailViews)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="note">
          막히는 단계는 노출 → 클릭 → 상세 → 성분·리뷰 확인 → 담기 다섯 단계 중, 내 다른 상품들과 비교해 가장 뒤처진 하나입니다. 나간 자리
          옆의 짧은 말은 가능성이고 단정이 아닙니다. 흐린 행은 상세를 {MIN_DETAIL_VIEWS}번 미만 본 상품이라 아직 판단하기 이릅니다.
          {source.products === 'real' && noDiag
            ? ` 본 횟수·담기 비율·담았다 뺀 비율은 실제 기록이고, 나간 자리·옵션 오간 횟수·빠른 보기→상세 세 칸은 계산이 아직 준비되지 않아 '-'로 두었습니다. 준비되면 자동으로 채워집니다.`
            : ''}
        </p>
      </Panel>
    </div>
  );
}
