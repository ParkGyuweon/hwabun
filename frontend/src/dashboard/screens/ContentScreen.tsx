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
function verbOf(lift: number, viewRate: number): Verb {
  if (lift < 1) return 'fix';
  if (lift >= 1.5 && viewRate < 0.5) return 'up';
  return 'keep';
}

const VERB_PILL: Record<Verb, string> = { up: '위로 올리기', fix: '손보기', keep: '그대로' };
const ORDER: Record<Verb, number> = { up: 0, fix: 1, keep: 2 };

/** 이 수보다 적게 본 글은 흐리게 그린다. 아직 판단하기 이르다는 표시 */
const THIN_VIEWS = 500;

export default function ContentScreen({ brandName }: { brandName: string }) {
  const m = useBehavior();
  const { contentAttention, scrapedIngredients, validationBehaviors, source } = m;
  const rows = useMemo(() => contentAttention.map((c) => ({ ...c, verb: verbOf(c.conversionLift, c.viewRate) })), [contentAttention]);

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
          ? `평균의 ${r.conversionLift.toFixed(1)}배 담는데, 본 사람은 ${fmt.pct(r.viewRate)}뿐`
          : `${(r.avgDwellMs / 1000).toFixed(0)}초나 읽는데 담기는 평균 아래`,
      num: `${r.conversionLift.toFixed(1)}배`,
      unit: '담기 효과 (평균이 1.0배)',
      how: rx?.rx?.how,
      basis: rx?.rx?.basis,
      verify: rx?.rx?.verify,
      tags: tags.length ? tags : undefined,
    };
  });

  // 드래그 0회인 성분을 "가장 많이 드래그한 성분"으로 적지 않는다. 기록이 없으면 없다고 적는다
  const topScrape = scrapedIngredients.find((x) => x.count > 0);
  const expand = validationBehaviors.find((v) => v.event === 'ingredient_view_mode_change') ?? validationBehaviors[0];

  const headline = noData
    ? '아직 상세페이지 글을 읽은 기록이 없습니다'
    : liftPending
      ? '담기 비율 계산이 준비되면 할 일이 나옵니다'
      : `${firstUp ? `${josa(firstUp.ko, '을/를')} 위로 올리고, ` : ''}${firstFix ? `${josa(firstFix.ko, '을/를')} 손보세요` : '지금 순서를 그대로 두세요'}`;

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
              글 {rows.length}종을 <b>담기 효과</b> 순으로 세운 결과
            </li>
          )}
          {!noData && liftPending ? <li>담기 효과는 계산 준비 중</li> : null}
          {best && !liftPending ? (
            <li>
              가장 잘 먹히는 글: {best.ko} · {best.conversionLift.toFixed(1)}배
            </li>
          ) : null}
        </ul>
      </section>

      <Panel
        title="지금 할 일"
        source={source.contentLift}
        aside={
          <span
            title={`1.0배 = 내 브랜드 평균 담기율 · 1.0배 미만은 손보기, 1.5배 이상인데 절반도 못 봤으면 위로 올리기 · 지시 문장: AI ${llmCount}건 · 규칙 ${ruleCount}건`}
          >
            담기 효과 기준
          </span>
        }
      >
        {actions.length > 0 ? (
          <Actions items={actions} />
        ) : (
          <p className="note">
            {noData ? '아직 할 일이 없습니다' : liftPending ? '담기 효과 계산 준비 중입니다' : '지금 순서를 그대로 두세요'}
          </p>
        )}
      </Panel>

      <div className="grid grid--kpi">
        <Kpi
          label="가장 잘 먹히는 글"
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
          sub={topScrape ? `이름을 긁거나 복사한 횟수 ${fmt.int(topScrape.count)}번` : '아직 기록 없음'}
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
              <th title="그 글이 화면에 보인 방문 ÷ 상세를 연 방문">본 비율</th>
              <th title="그 글에 머문 시간 ÷ 상세를 연 방문">읽은 시간</th>
              <th title="그 글을 본 방문의 담기율 ÷ 내 브랜드 전체 담기율">담기 효과</th>
              <th>할 일</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="note">
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
                  <td>
                    <strong>{liftPending ? '-' : `${c.conversionLift.toFixed(1)}배`}</strong>
                  </td>
                  <td>
                    <span className={`pill pill--${c.verb}`}>{liftPending ? '판단 전' : VERB_PILL[c.verb]}</span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <details className="fold">
          <summary>읽은 시간과 담기 효과를 한 그림으로</summary>
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
            <dd>그 글이 화면에 보인 방문 ÷ 상세를 연 방문.</dd>
            <dt>읽은 시간</dt>
            <dd>그 글에 머문 시간 ÷ 상세를 연 방문. 글 3개 이상 겹친 시간은 제외.</dd>
            <dt>담기 효과</dt>
            <dd>그 글을 본 방문의 담기율 ÷ 내 브랜드 전체 담기율. 1.0배가 평균입니다. 같이 움직인다는 뜻이고 원인이라는 뜻은 아닙니다.</dd>
            <dt>기록 수</dt>
            <dd>그 글이 보인 방문 수. {fmt.int(THIN_VIEWS)}건 미만은 흐리게, 50건 미만은 그림에서 제외.</dd>
          </dl>
        </details>
      </Panel>

      <div className="grid grid--2">
        <Panel title="고객이 가장 많이 찾아본 성분 10가지" source={source.scraped} fold aside={<span title="긁은 글 원문은 저장하지 않습니다">성분 이름을 마우스로 긁거나 복사한 횟수</span>}>
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: labelKo(i.name),
              value: i.count,
              hint: i.copyCount === null ? undefined : `복사 ${i.copyCount}회`,
            }))}
          />
        </Panel>

        <Panel
          title="이 행동을 한 사람은 더 담나"
          source={source.behaviors}
          fold
          aside={<span title="같이 움직인다는 뜻이고, 이것 때문이라는 뜻은 아닙니다">한 방문과 안 한 방문 비교</span>}
        >
          <table className="table">
            <thead>
              <tr>
                <th>행동</th>
                <th title="상세를 연 방문 중 이 행동을 한 비율">한 방문</th>
                <th title="이 행동을 한 방문의 담기 비율">했을 때 담기</th>
                <th title="이 행동을 안 한 방문의 담기 비율">안 했을 때</th>
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
        </Panel>
      </div>
    </div>
  );
}
