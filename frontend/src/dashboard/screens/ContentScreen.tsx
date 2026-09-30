import { useMemo } from 'react';
import { Actions, BarList, Kpi, OriginBadge, Panel, Scatter } from '../components';
import { fmt } from '../lib/metrics';
import { josa } from '../../lib/format';
import { useBehavior } from '../lib/useBehavior';
import { usePrescriptions } from '../lib/prescriptionApi';
import { labelKo } from '../../lib/formLabels';
import type { ActionItem } from '../components';

/**
 * ③ 정보 관심도 · 이 대시보드의 존재 이유.
 *
 * 일반 웹 분석은 "상세 이탈률이 높다" 에서 멈춘다. 이 화면은 그 다음을 말한다 ·
 * **무엇을 보여줘야 사는가.** 콘텐츠 단위 체류(`section_dwell` + `content_kind`)를
 * 수집하는 우리만 만들 수 있는 화면이다.
 *
 * 화면 순서를 뒤집었다. 예전에는 산점도를 먼저 보여주고 사장님이 사분면을 스스로
 * 읽게 했다. 그 읽기를 화면이 대신한다 · 맨 위는 **할 일 목록**, 그 다음이 표,
 * 두 축을 겹친 그림은 근거를 확인하고 싶을 때 펼치는 부록이다.
 */

type Verb = ActionItem['verb'];

/**
 * 콘텐츠 하나를 할 일 하나로 바꾼다.
 *
 * 사장님이 물어야 할 질문은 두 개뿐이다 · **본 사람이 더 담았나**, **몇 명이 봤나.**
 *   · 더 담지 않았다(1.0배 미만)         → 손보세요. 읽었는데 설득이 안 된 글이다
 *   · 더 담았는데 절반도 못 봤다(1.5배↑) → 위로 올리세요. 안 보여서 못 먹히고 있다
 *   · 그 밖에                            → 그대로 두세요
 *
 * 1.0배는 내 브랜드 전체 담기율과 같다는 뜻이다. 정의는 아래 접힌 설명에 있다.
 */
function verbOf(kind: string, lift: number, viewRate: number, sampleSize: number): Verb {
  // 고객이 만든 값에는 동사를 붙이지 않는다. "평점 분포를 손보세요" 는 리뷰 조작 권유로 읽힌다 (2026-09-22 데이터 파트)
  if (CUSTOMER_MADE.has(kind)) return 'keep';
  // 읽은 사람이 거의 없으면 "읽었는데 설득이 안 됐다" 고 말할 수 없다. 표를 흐리게 그리는 기준과 같은 수
  if (sampleSize < THIN_VIEWS) return 'keep';
  if (lift < 1) return 'fix';
  if (lift >= 1.5 && viewRate < 0.5) return 'up';
  return 'keep';
}

/**
 * 사장님이 고칠 수 없는 글. 리뷰 원문과 평점 분포는 고객이 쓴 값이라 "손보기·올리기" 대상이 아니다.
 * 표에는 "고객이 만든 값" 으로 적고, 할 일 목록과 맨 위 결론에서는 뺀다. 순위·담기 배수 관찰은 그대로 보인다.
 */
const CUSTOMER_MADE = new Set(['user_review', 'review_stats']);

const VERB_PILL: Record<Verb, string> = { up: '위로 올리기', fix: '손보기', keep: '그대로' };
const ORDER: Record<Verb, number> = { up: 0, fix: 1, keep: 2 };

/** 이 수보다 적게 본 글은 흐리게 그리고 할 일도 내지 않는다. 아직 판단하기 이르다는 표시 */
const THIN_VIEWS = 500;

export default function ContentScreen({ brandName }: { brandName: string }) {
  const m = useBehavior();
  const { contentAttention, scrapedIngredients, validationBehaviors, source } = m;
  const rows = useMemo(
    () => contentAttention.map((c) => ({ ...c, verb: verbOf(c.kind, c.conversionLift, c.viewRate, c.sampleSize) })),
    [contentAttention],
  );

  // 할 일은 올릴 것부터. 그 안에서는 담기 배수가 큰 순서, 손볼 것은 오래 읽힌 순서
  const todo = useMemo(
    () =>
      rows
        .filter((r) => r.verb !== 'keep')
        .sort(
          (a, b) =>
            ORDER[a.verb] - ORDER[b.verb] ||
            (a.verb === 'up' ? b.conversionLift - a.conversionLift : b.avgDwellMs - a.avgDwellMs),
        ),
    [rows],
  );

  const firstUp = todo.find((r) => r.verb === 'up');
  const firstFix = todo.find((r) => r.verb === 'fix');
  // 0 끼리는 순위가 없다. 담기 배수가 0 인 콘텐츠를 "가장 잘 먹히는 것"으로 세우지 않는다 (2026-09-18)
  const best = [...rows].filter((r) => r.conversionLift > 0).sort((a, b) => b.conversionLift - a.conversionLift)[0];
  const noData = rows.length === 0;
  // 담기율 배수가 아직 안 와서 전부 1.0 인 상태. 이때는 "그대로 두세요" 가 아니라 "아직 판단 전" 이다
  const liftPending = source.contentLift === 'none';

  // 처방(무엇을 어떻게)은 이 화면 숫자만으로 못 쓴다. 다른 화면의 근거까지 모아 만든다.
  // 먼저 규칙 표(lib/prescription.ts)로 그리고, AI 서버(POST /api/prescription)가 답하면 그 문장으로 바꾼다.
  const targets = useMemo(() => todo.map((r) => ({ row: r, verb: r.verb as 'up' | 'fix' })), [todo]);
  const brand = useMemo(() => ({ name: brandName, productCount: m.productMetrics.length }), [brandName, m.productMetrics.length]);
  const rxs = usePrescriptions(m, targets, brand);
  const llmCount = Object.values(rxs).filter((r) => r.origin === 'llm').length;
  const ruleCount = Object.values(rxs).filter((r) => r.origin === 'rule').length;

  const actions: ActionItem[] = todo.map((r) => {
    const rx = rxs[r.kind];
    const tags: string[] = [];
    if (rx?.origin === 'llm') tags.push('AI가 쓴 문장');
    if (rx?.needsEvidence.length) tags.push(`근거 필요: ${rx.needsEvidence.join('·')}`);
    return {
      verb: r.verb,
      what: r.ko,
      why:
        r.verb === 'up'
          ? `본 방문은 평균의 ${r.conversionLift.toFixed(1)}배 담았는데, 본 비율은 ${fmt.pct(r.viewRate)}뿐`
          : `${(r.avgDwellMs / 1000).toFixed(0)}초나 읽는데 담기는 평균 아래`,
      num: `${r.conversionLift.toFixed(1)}배`,
      unit: '본 방문 담기 배수 (평균이 1.0배)',
      how: rx?.rx?.how,
      basis: rx?.rx?.basis,
      verify: rx?.rx?.verify,
      tags: tags.length ? tags : undefined,
    };
  });

  // 드래그 0회인 성분을 "가장 많이 드래그한 성분"으로 적지 않는다. 기록이 없으면 없다고 적는다
  const topScrape = scrapedIngredients.find((x) => x.score > 0);
  // 복사가 한 번도 없으면 열 자체를 안 둔다. 0 만 늘어선 열은 읽을 게 없다
  const anyCopy = rows.some((c) => c.copyCount > 0);
  const expand = validationBehaviors.find((v) => v.event === 'ingredient_view_mode_change') ?? validationBehaviors[0];

  const headline = noData
    ? '아직 상세페이지 글을 읽은 기록이 없습니다'
    : liftPending
      ? '담기 비율 계산이 준비되면 할 일이 나옵니다'
      : `${firstUp ? `${josa(firstUp.ko, '을/를')} 위로 올려 보고, ` : ''}${firstFix ? `${josa(firstFix.ko, '을/를')} 손봐 보세요` : '지금 순서를 그대로 두세요'}`;

  return (
    <div className="stack">
      <section className="verdict verdict--mine">
        <p className="verdict__eyebrow">
          결론 <OriginBadge kind="mine" />
        </p>
        <h2 className="verdict__headline">{headline}</h2>
        <ul className="verdict__reasons">
          {noData ? (
            <li>기록이 쌓이면 여기에 나옵니다</li>
          ) : (
            <li>
              글 {rows.length}종을 <b>본 방문 담기 배수</b> 순으로 세운 결과
            </li>
          )}
          {!noData && liftPending ? <li>본 방문 담기 배수는 계산 준비 중</li> : null}
          {best && !liftPending ? (
            <li>
              본 방문이 가장 많이 담은 글: {best.ko} · {best.conversionLift.toFixed(1)}배
            </li>
          ) : null}
        </ul>
      </section>

      <Panel
        title="지금 할 일"
        source={source.contentLift}
        aside={
          <span
            title={`본 방문이 평균보다 덜 담은 글은 손봐 보고, 1.5배 넘게 담았는데 절반도 안 본 글은 위로 올려 보라고 알려 드려요. 바꾼 뒤 담기가 실제로 오르는지 꼭 확인해 보세요 (AI가 쓴 안내 ${llmCount}건 · 기본 안내 ${ruleCount}건)`}
          >
            본 방문 담기 배수 기준
          </span>
        }
      >
        {actions.length > 0 ? (
          <Actions items={actions} />
        ) : (
          <p className="note">
            {noData ? '아직 할 일이 없습니다' : liftPending ? '본 방문 담기 배수 계산 준비 중입니다' : '지금 순서를 그대로 두세요'}
          </p>
        )}
      </Panel>

      <div className="grid grid--kpi">
        <Kpi
          label="본 방문이 가장 많이 담은 글"
          value={best && !liftPending ? best.ko : '-'}
          sub={best && !liftPending ? `평균의 ${best.conversionLift.toFixed(1)}배 담기` : noData ? '아직 기록 없음' : '계산 준비 중'}
          source={source.contentLift}
        />
        <Kpi
          label="손봐야 할 글"
          value={firstFix ? firstFix.ko : '없음'}
          sub={firstFix ? '오래 읽는데 담기는 평균 아래' : noData ? '아직 기록 없음' : liftPending ? '계산 준비 중' : '담기 낮은 글 없음'}
          source={source.contentLift}
        />
        <Kpi
          label="고객이 가장 많이 찾아본 성분"
          value={topScrape ? labelKo(topScrape.name) : '-'}
          sub={topScrape ? `이름을 긁거나 복사한 성분 1위 · 관련 행동 ${fmt.int(topScrape.events)}번` : '아직 기록 없음'}
          source={source.scraped}
        />
        <Kpi
          label="전성분을 펼쳐 본 방문"
          value={expand ? fmt.pct(expand.doneRate) : '-'}
          sub={expand ? '상세를 연 방문 중' : '아직 기록 없음'}
          source={source.behaviors}
        />
      </div>

      <Panel
        title="상세페이지 글 10종 전부"
        source={source.content}
        fold
        aside={<span title={`${fmt.int(THIN_VIEWS)}건 미만 본 글은 흐리게 표시`}>상세페이지 안의 글만</span>}
      >
        <table className="table">
          <thead>
            <tr>
              <th>글</th>
              <th title="상세페이지를 연 방문 중 그 글까지 본 비율이에요">본 비율</th>
              <th title="상세페이지를 한 번 열 때 그 글을 평균 얼마나 읽었는지예요">읽은 시간</th>
              <th title="그 글을 본 방문 중 장바구니에 담은 비율">본 고객 담기</th>
              <th title="그 글을 본 방문이 내 브랜드 평균보다 몇 배 더 담았는지예요. 같이 움직였다는 뜻이지 그 글 때문이라는 뜻은 아니에요">본 방문 담기 배수</th>
              {anyCopy ? <th title="그 글에서 글자를 복사한 횟수">복사</th> : null}
              <th>할 일</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={anyCopy ? 7 : 6} className="note">
                  아직 기록이 없습니다
                </td>
              </tr>
            ) : null}
            {[...rows]
              .sort((a, b) => ORDER[a.verb] - ORDER[b.verb] || b.conversionLift - a.conversionLift)
              .map((c) => (
                <tr key={c.kind} className={c.sampleSize < THIN_VIEWS ? 'is-thin' : ''}>
                  <td>{c.ko}</td>
                  <td>{fmt.pct(c.viewRate)}</td>
                  <td>{(c.avgDwellMs / 1000).toFixed(0)}초</td>
                  <td>{c.viewedCartRate === null ? '-' : fmt.pct(c.viewedCartRate)}</td>
                  <td>
                    <strong>{liftPending ? '-' : `${c.conversionLift.toFixed(1)}배`}</strong>
                  </td>
                  {anyCopy ? <td>{c.copyCount > 0 ? `${fmt.int(c.copyCount)}번` : '-'}</td> : null}
                  <td>
                    <span className={`pill pill--${c.verb}`} title={CUSTOMER_MADE.has(c.kind) ? '고객이 쓴 리뷰·평점이라 사장님이 고치는 대상이 아닙니다' : undefined}>
                      {liftPending ? '판단 전' : CUSTOMER_MADE.has(c.kind) ? '고객이 만든 값' : c.sampleSize < THIN_VIEWS ? '판단 전' : VERB_PILL[c.verb]}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <details className="fold">
          <summary>읽은 시간과 본 방문 담기 배수를 한 그림으로</summary>
          <Scatter
            points={rows.map((c) => ({
              label: c.ko,
              x: c.avgDwellMs / 1000,
              y: c.conversionLift,
              n: c.sampleSize,
            }))}
          />
          <p className="note">오른쪽 아래가 손볼 곳, 왼쪽 위가 올릴 곳</p>
        </details>

        <details className="defn">
          <summary>숫자의 정의</summary>
          <dl className="defn__list">
            <dt>무엇을 셌나</dt>
            <dd>상세페이지 안에서 읽는 글 10종. 목록 카드·장바구니·메뉴는 제외.</dd>
            <dt>본 비율</dt>
            <dd>상세페이지를 연 방문 중 그 글까지 본 비율.</dd>
            <dt>읽은 시간</dt>
            <dd>상세페이지를 한 번 열 때 그 글을 평균 얼마나 읽었는지. 글 3개 이상이 한 화면에 겹친 시간은 뺐습니다.</dd>
            <dt>본 고객 담기</dt>
            <dd>그 글을 본 방문 중 장바구니에 담은 비율.</dd>
            <dt>본 방문 담기 배수</dt>
            <dd>그 글을 본 방문이 내 브랜드 평균보다 몇 배 더 담았는지. 1.0배가 평균입니다. 같이 움직인다는 뜻이고 원인이라는 뜻은 아닙니다.</dd>
            <dt>기록 수</dt>
            <dd>그 글이 보인 방문 수. {fmt.int(THIN_VIEWS)}건 미만은 흐리게, 50건 미만은 그림에서 제외.</dd>
          </dl>
        </details>
      </Panel>

      <div className="grid grid--2">
        <Panel title="고객이 가장 많이 찾아본 성분 10가지" source={source.scraped} fold aside={<span title="긁은 글 원문은 저장하지 않습니다">이름을 긁거나 복사할수록 점수가 올라갑니다</span>}>
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: labelKo(i.name),
              value: i.score,
              hint: `행동 ${fmt.int(i.events)}번`,
            }))}
            format={(v) => `${fmt.int(v)}점`}
          />
        </Panel>

        {/*
          열 이름을 문장으로 풀었다 (2026-09-22 은솔님: "한 방문·안 한 방문" 이 직관적으로 안 읽힌다).
          "했을 때 담기 / 안 했을 때" 는 무엇의 비율인지가 빠져 있었다. 세 열 모두 "누구의 무엇" 을 적고,
          표 아래에 첫 줄을 문장으로 한 번 읽어 준다.
        */}
        <Panel
          title="이 행동을 한 고객이 더 담았나"
          source={source.behaviors}
          fold
          aside={<span title="같이 움직인다는 뜻이고, 이것 때문이라는 뜻은 아닙니다">행동한 고객과 안 한 고객의 담기 비율을 나란히</span>}
        >
          <table className="table">
            <thead>
              <tr>
                <th>행동</th>
                <th title="상세를 연 고객 중 이 행동을 한 고객의 비율">이 행동을 한 고객</th>
                <th title="이 행동을 한 고객 중 장바구니에 담은 비율">한 고객 중 담은 비율</th>
                <th title="이 행동을 안 한 고객 중 장바구니에 담은 비율">안 한 고객 중 담은 비율</th>
              </tr>
            </thead>
            <tbody>
              {validationBehaviors.length === 0 ? (
                <tr>
                  <td colSpan={4} className="note">
                    아직 기록이 없습니다
                  </td>
                </tr>
              ) : null}
              {validationBehaviors.map((v) => (
                <tr key={v.event}>
                  <td>{v.ko}</td>
                  <td>{fmt.pct(v.doneRate)}</td>
                  <td>
                    <strong>{fmt.pct(v.cartRateWith)}</strong>
                  </td>
                  <td>{fmt.pct(v.cartRateWithout)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {validationBehaviors[0] ? (
            <p className="note">
              읽는 법: 상세를 본 고객 중 {fmt.pct(validationBehaviors[0].doneRate)}가 &lsquo;{validationBehaviors[0].ko}&rsquo;를 했고, 그 고객은{' '}
              {fmt.pct(validationBehaviors[0].cartRateWith)}가 담았습니다. 안 한 고객은 {fmt.pct(validationBehaviors[0].cartRateWithout)}가 담았습니다.
            </p>
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
