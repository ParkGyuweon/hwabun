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
    if (rx?.needsEvidence.length) tags.push(`근거 자료가 필요한 표현: ${rx.needsEvidence.join('·')}`);
    return {
      verb: r.verb,
      what: r.ko,
      why:
        r.verb === 'up'
          ? `이 글을 본 사람은 평균보다 ${r.conversionLift.toFixed(1)}배 더 담았는데, 상세페이지를 연 사람 중 ${fmt.pct(r.viewRate)}만 여기까지 내려왔습니다.`
          : `${(r.avgDwellMs / 1000).toFixed(0)}초나 읽는데, 본 사람이 평균보다 덜 담았습니다. 읽고도 마음이 안 움직인 글입니다.`,
      num: `${r.conversionLift.toFixed(1)}배`,
      unit: '이 글을 본 사람의 담기 비율 (평균 = 1.0배)',
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
          이 화면이 말하는 것 <OriginBadge kind="mine" />
        </p>
        <h2 className="verdict__headline">{headline}</h2>
        <ul className="verdict__reasons">
          {noData ? (
            <li>고객이 내 상품 상세페이지를 열고 글을 읽기 시작하면, 어떤 글이 담기에 도움이 되는지 여기서 알려 드립니다.</li>
          ) : (
            <li>
              상세페이지 안에서 읽는 글 {rows.length}종을 <b>본 사람이 더 담았는지</b>로 줄 세운 결과입니다.
            </li>
          )}
          {!noData && liftPending ? (
            <li>지금은 몇 명이 봤는지·얼마나 오래 읽었는지만 있고, 본 사람이 더 담았는지는 계산이 준비되는 대로 채워집니다.</li>
          ) : null}
          {best && !liftPending ? (
            <li>
              가장 잘 먹히는 글은 {best.ko}입니다. 본 사람이 평균보다 {best.conversionLift.toFixed(1)}배 더 담았습니다.
            </li>
          ) : null}
        </ul>
      </section>

      <Panel title="지금 할 일" source={source.contentLift} aside="글을 본 사람이 더 담았는지가 기준">
        {actions.length > 0 ? (
          <Actions items={actions} />
        ) : (
          <p className="note">
            {noData
              ? '아직 할 일이 없습니다. 고객이 상세페이지 글을 읽은 기록이 쌓이면 여기에 "위로 올리세요" · "손보세요" 목록이 생깁니다.'
              : liftPending
                ? '몇 명이 봤는지는 알지만, 본 사람이 더 담았는지 계산이 아직 준비되지 않아 할 일을 고르지 않았습니다. 준비되면 자동으로 채워집니다.'
                : '손볼 글도, 위로 올릴 글도 없습니다. 지금 순서를 그대로 두셔도 됩니다.'}
          </p>
        )}
        <p className="note">
          1.0배는 그 글을 본 사람의 담기 비율이 내 브랜드 전체 평균과 같다는 뜻입니다. 1.0배가 안 되면 손볼 글, 1.5배 이상인데 절반도 못
          본 글은 위로 올릴 글로 골랐습니다. 지시 문장은 이 화면 숫자만으로 쓰지 않고, 고객군·성분·막히는 곳 화면에서 모은 근거까지
          모아 만듭니다. 근거는 각 줄을 펼치면 나옵니다.
          {llmCount > 0
            ? ` 지시 문장 ${llmCount}건은 AI가 썼고, ${ruleCount}건은 미리 정해 둔 규칙으로 만들었습니다.`
            : ' 지시 문장은 미리 정해 둔 규칙으로 만들었습니다. AI가 연결되면 그 문장으로 바뀝니다.'}
        </p>
      </Panel>

      <div className="grid grid--kpi">
        <Kpi
          label="가장 잘 먹히는 글"
          value={best && !liftPending ? best.ko : '-'}
          sub={
            best && !liftPending
              ? `본 사람이 평균보다 ${best.conversionLift.toFixed(1)}배 더 담았습니다`
              : noData
                ? '상세페이지 글을 읽은 기록이 아직 없습니다'
                : '본 사람이 더 담았는지 계산이 아직 준비되지 않았습니다'
          }
          source={source.contentLift}
        />
        <Kpi
          label="손봐야 할 글"
          value={firstFix ? firstFix.ko : '없음'}
          sub={
            firstFix
              ? '오래 읽는데 담기는 평균보다 적습니다'
              : noData
                ? '상세페이지 글을 읽은 기록이 아직 없습니다'
                : liftPending
                  ? '담기 비율 계산이 준비되면 고릅니다'
                  : '평균보다 담기가 낮은 글이 없습니다'
          }
          source={source.contentLift}
        />
        <Kpi
          label="고객이 가장 많이 드래그한 성분"
          value={topScrape ? labelKo(topScrape.name) : '-'}
          sub={topScrape ? `${fmt.int(topScrape.count)}회 · 관심이 가장 큰 성분` : '고객이 성분 이름을 드래그한 기록이 아직 없습니다'}
          source={source.scraped}
        />
        <Kpi
          label="전성분을 펼쳐 본 방문"
          value={expand ? fmt.pct(expand.doneRate) : '-'}
          sub={expand ? '상세페이지를 연 방문 중' : '전성분을 펼친 기록이 아직 없습니다'}
          source={source.behaviors}
        />
      </div>

      <Panel title="상세페이지 글 10종 전부" source={source.content} fold aside="내 브랜드 상품의 상세페이지 안만">
        <p className="panel__lead">
          목록 카드·장바구니·메뉴처럼 상세페이지 밖의 것은 빼고, <b>상세페이지 안에서 읽는 글 10종</b>만 셌습니다.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>글</th>
              <th>몇 명이 봤나</th>
              <th>얼마나 오래 읽나</th>
              <th>본 사람의 담기 비율</th>
              <th>할 일</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="note">
                  아직 기록이 없습니다. 고객이 내 상품 상세페이지를 열어 글을 읽으면 여기에 한 줄씩 채워집니다.
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
        <p className="note">
          흐린 행은 그 글을 본 방문이 {fmt.int(THIN_VIEWS)}건이 안 돼 아직 판단하기 이릅니다.
          {source.content === 'real' && liftPending
            ? ' 몇 명이 봤는지와 얼마나 오래 읽었는지는 실제 기록이고, 본 사람의 담기 비율은 계산이 아직 준비되지 않아 비워 두었습니다. 준비되면 자동으로 채워집니다.'
            : ''}
        </p>

        <details className="fold">
          <summary>두 축을 한 장에 겹쳐 보기 · 오래 읽는 것과 담게 만드는 것은 다릅니다</summary>
          <Scatter
            points={rows.map((c) => ({
              label: c.ko,
              x: c.avgDwellMs / 1000,
              y: c.conversionLift,
              n: c.sampleSize,
            }))}
          />
          <p className="note">
            오른쪽 아래(오래 읽는데 안 담는다)가 손볼 곳, 왼쪽 위(짧게 읽는데 담게 만든다)가 위로 올릴 곳입니다. 원이 클수록 그 글을
            본 방문이 많습니다.
          </p>
        </details>

        <details className="defn">
          <summary>숫자의 정의와 글 고른 기준</summary>
          <dl className="defn__list">
            <dt>무엇을 셌나</dt>
            <dd>
              상세페이지 안에서 읽는 글 <b>10종</b>입니다. 성분 목록·성분 특징·임상 결과·사용자 리뷰·평점 분포·제품 소개·추가
              설명·사용법·브랜드 소개·상품 이미지를 넣었고, 목록 카드·장바구니·메뉴처럼 상세페이지 밖의 것은 뺐습니다.
            </dd>
            <dt>몇 명이 봤나</dt>
            <dd>그 글이 화면에 한 번이라도 보인 방문 ÷ 상세페이지를 연 방문.</dd>
            <dt>얼마나 오래 읽나</dt>
            <dd>
              그 글에 머문 시간을 모두 더해 상세페이지를 연 방문 수로 나눈 값입니다. 한 화면에 글이 3개 이상 겹쳐 보인 시간은 어느 글을
              읽은 것인지 알 수 없어 빼고 셉니다.
            </dd>
            <dt>본 사람의 담기 비율</dt>
            <dd>
              그 글을 본 방문의 담기 비율 ÷ 내 브랜드 전체 담기 비율. 1.0배면 평균과 같고, 1.6배면 그 글을 본 사람이 평균보다 1.6배 더
              담았다는 뜻입니다. <b>같이 움직인다는 뜻이고, 이것 때문이라는 뜻은 아닙니다</b> · 살 마음이 큰 사람이 성분을 더 볼 수도
              있습니다.
            </dd>
            <dt>기록 수</dt>
            <dd>그 글이 한 번이라도 보인 방문 수입니다. {fmt.int(THIN_VIEWS)}건이 안 되면 흐리게, 50건이 안 되면 그림에서 뺍니다.</dd>
            <dt>지금 상태</dt>
            <dd>
              몇 명이 봤는지·얼마나 오래 읽었는지는 지금 실제 기록으로 셉니다. 본 사람의 담기 비율은 계산이 준비되는 대로 채워지고,
              그때 이 표의 표시도 함께 바뀝니다.
            </dd>
          </dl>
        </details>
      </Panel>

      <div className="grid grid--2">
        <Panel title="고객이 드래그한 성분 TOP 10" source={source.scraped} fold aside="긁은 글 원문은 저장하지 않고 성분 이름만 셉니다">
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: labelKo(i.name),
              value: i.count,
              hint: i.copyCount === null ? undefined : `복사 ${i.copyCount}회`,
            }))}
          />
          <p className="note">
            드래그 횟수는 관심의 크기입니다. 설명이 어려운지는 그 성분 부분에서 위로 되돌아가 다시 읽었는지·그냥 나갔는지·담았는지를
            함께 봐야 알 수 있고, 그 계산이 준비되면 여기에 붙습니다.
          </p>
        </Panel>

        <Panel title="이 행동을 한 사람은 더 담나" source={source.behaviors} fold aside="한 방문과 안 한 방문 비교">
          <table className="table">
            <thead>
              <tr>
                <th>행동</th>
                <th>한 방문</th>
                <th>했을 때 담기 비율</th>
                <th>안 했을 때</th>
              </tr>
            </thead>
            <tbody>
              {validationBehaviors.length === 0 ? (
                <tr>
                  <td colSpan={4} className="note">
                    아직 기록이 없습니다. 고객이 전성분을 펼치거나 리뷰를 걸러 보기 시작하면 여기에 채워집니다.
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
          <p className="note">같이 움직인다는 뜻이고, 이것 때문이라는 뜻은 아닙니다.</p>
        </Panel>
      </div>
    </div>
  );
}
