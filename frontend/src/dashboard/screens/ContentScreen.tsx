import { useMemo } from 'react';
import { Actions, BarList, Kpi, OriginBadge, Panel, Scatter } from '../components';
import { fmt } from '../lib/metrics';
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
  const best = [...rows].sort((a, b) => b.conversionLift - a.conversionLift)[0];

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
    if (rx?.origin === 'llm') tags.push('AI 문장');
    if (rx?.needsEvidence.length) tags.push(`실증자료 필요: ${rx.needsEvidence.join('·')}`);
    return {
      verb: r.verb,
      what: r.ko,
      why:
        r.verb === 'up'
          ? `본 사람이 평균보다 ${r.conversionLift.toFixed(1)}배 더 담았는데, 상세페이지를 연 사람 중 ${fmt.pct(r.viewRate)}만 여기까지 내려왔습니다.`
          : `${(r.avgDwellMs / 1000).toFixed(0)}초나 읽는데 본 사람이 평균보다 덜 담았습니다. 읽고도 마음이 안 움직인 글입니다.`,
      num: `${r.conversionLift.toFixed(1)}배`,
      unit: '본 사람의 담기율',
      how: rx?.rx?.how,
      basis: rx?.rx?.basis,
      verify: rx?.rx?.verify,
      tags: tags.length ? tags : undefined,
    };
  });

  const topScrape = scrapedIngredients[0];
  const expand = validationBehaviors.find((v) => v.event === 'ingredient_view_mode_change') ?? validationBehaviors[0];

  return (
    <div className="stack">
      <section className="verdict verdict--mine">
        <p className="verdict__eyebrow">
          이 화면이 말하는 것 <OriginBadge kind="mine" />
        </p>
        <h2 className="verdict__headline">
          {firstUp ? `${firstUp.ko}를 위로 올리고, ` : ''}
          {firstFix ? `${firstFix.ko}을 손보세요` : '지금 순서를 그대로 두세요'}
        </h2>
        <ul className="verdict__reasons">
          <li>
            상세페이지 안에서 읽는 글 {rows.length}종을 <b>본 사람이 더 담았는지</b>로 줄 세운 결과입니다.
          </li>
          {best ? (
            <li>
              가장 잘 먹히는 것은 {best.ko}입니다. 본 사람이 평균보다 {best.conversionLift.toFixed(1)}배 더 담았습니다.
            </li>
          ) : null}
        </ul>
      </section>

      <Panel title="지금 할 일" source={source.contentLift} aside="본 사람의 담기율이 기준">
        <Actions items={actions} />
        <p className="note">
          담기율 1.0배는 내 브랜드 전체 평균과 같다는 뜻입니다. 1.0배 미만은 손볼 것, 1.5배 이상인데 절반도 못 본 것은 위로
          올릴 것으로 골랐습니다. 지시 문장은 이 화면 숫자만으로 쓰지 않고, 고객군·성분·막히는 곳 화면에서 모은 근거까지
          모아 만듭니다. 근거는 각 줄을 펼치면 나옵니다.
          {llmCount > 0 ? ` 처방 문장 ${llmCount}건은 AI 서버가 썼고, ${ruleCount}건은 규칙 표입니다.` : ' 처방 문장은 규칙 표입니다. AI 서버가 연결되면 그 문장으로 바뀝니다.'}
        </p>
      </Panel>

      <div className="grid grid--kpi">
        <Kpi
          label="가장 잘 먹히는 콘텐츠"
          value={best?.ko ?? '-'}
          sub={best ? `본 사람이 평균보다 ${best.conversionLift.toFixed(1)}배 더 담았습니다` : ''}
          source={source.contentLift}
        />
        <Kpi
          label="손봐야 할 콘텐츠"
          value={firstFix ? firstFix.ko : '없음'}
          sub={firstFix ? '오래 읽는데 담기는 평균보다 적습니다' : '평균보다 낮은 콘텐츠가 없습니다'}
          source={source.contentLift}
        />
        <Kpi
          label="고객이 가장 많이 드래그한 성분"
          value={topScrape ? labelKo(topScrape.name) : '-'}
          sub={topScrape ? `${fmt.int(topScrape.count)}회 · 관심이 가장 큰 성분` : ''}
          source={source.scraped}
        />
        <Kpi
          label="전성분을 펼쳐 본 방문"
          value={expand ? fmt.pct(expand.doneRate) : '-'}
          sub="상세페이지를 연 방문 중"
          source={source.behaviors}
        />
      </div>

      <Panel title="콘텐츠 10종 전부" source={source.content} fold aside="내 브랜드 상품의 상세페이지 안만">
        <p className="panel__lead">
          목록·장바구니 요소는 상세페이지에서 살지 말지 정하는 것과 무관해 빼고, <b>상세페이지 안에서 읽는 글 10종</b>만
          셌습니다.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>콘텐츠</th>
              <th>몇 명이 봤나</th>
              <th>얼마나 오래 읽나</th>
              <th>본 사람의 담기율</th>
              <th>할 일</th>
            </tr>
          </thead>
          <tbody>
            {[...rows]
              .sort((a, b) => ORDER[a.verb] - ORDER[b.verb] || b.conversionLift - a.conversionLift)
              .map((c) => (
                <tr key={c.kind} className={c.sampleSize < 500 ? 'is-thin' : ''}>
                  <td>
                    {c.ko} <span className="table__code">{c.kind}</span>
                  </td>
                  <td>{fmt.pct(c.viewRate)}</td>
                  <td>{(c.avgDwellMs / 1000).toFixed(0)}초</td>
                  <td>
                    <strong>{c.conversionLift.toFixed(1)}배</strong>
                  </td>
                  <td>
                    <span className={`pill pill--${c.verb}`}>{VERB_PILL[c.verb]}</span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <p className="note">
          흐린 행은 본 방문이 500건 미만이라 아직 판단하기에 표본이 얇습니다. 작은 회색 글씨는 데이터 파트와 맞춘 이벤트
          이름이라 그대로 두었습니다.
          {source.content === 'real' && source.contentLift === 'none'
            ? ' 열람·체류·표본은 마트 실측이고, 담기율 배수만 아직 모의입니다 (content_conversion_daily 요청 중).'
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
            오른쪽 아래(오래 읽는데 안 담는다)가 손볼 곳, 왼쪽 위(짧게 읽는데 담게 만든다)가 위로 올릴 곳입니다. 원 크기는
            표본 수입니다.
          </p>
        </details>

        <details className="defn">
          <summary>숫자의 정의와 콘텐츠 선정 기준</summary>
          <dl className="defn__list">
            <dt>무엇을 셌나</dt>
            <dd>
              상세페이지 콘텐츠 <b>10종</b>. 계약 <code>content_kind</code> 21종 중 상품 상세 안에서 읽는 것만 골랐습니다.
              넣은 것은 성분 목록·성분 특징·임상 결과·사용자 리뷰·평점 분포·제품 소개·추가 설명·사용법·브랜드 소개·상품
              이미지입니다. 제외한 것은 목록·장바구니·내비게이션 요소(<code>product_card</code>·<code>cart_item</code>·
              <code>navigation</code> 등)입니다.
            </dd>
            <dt>몇 명이 봤나</dt>
            <dd>그 콘텐츠가 화면에 한 번이라도 보인 세션 ÷ 상세페이지를 연 세션.</dd>
            <dt>얼마나 오래 읽나</dt>
            <dd>
              그 콘텐츠의 체류 시간 합계 ÷ 상세 조회 세션 수. <code>section_dwell</code> 이벤트를 <code>content_kind</code>{' '}
              별로 합산합니다. 한 화면에 블록이 3개 이상 겹쳐 보인 체류(<code>co_visible_blocks &gt; 2</code>)는 어느
              콘텐츠를 향한 것인지 단정할 수 없어 뺍니다.
            </dd>
            <dt>본 사람의 담기율</dt>
            <dd>
              그 콘텐츠를 본 세션의 담기율 ÷ 내 브랜드 전체 담기율. 1.0배면 평균과 같고, 1.6배면 그 콘텐츠를 본 사람이
              평균보다 1.6배 더 담았다는 뜻입니다. <b>같이 움직인다는 뜻이고, 이것 때문이라는 뜻은 아닙니다</b> · 살 마음이
              큰 사람이 성분을 더 볼 수도 있습니다.
            </dd>
            <dt>표본</dt>
            <dd>그 콘텐츠가 한 번이라도 보인 세션 수. 500 미만은 흐리게, 50 미만은 그리지 않습니다.</dd>
            <dt>지금 상태</dt>
            <dd>
              체류·표본은 계약에 정의가 있고(<code>content_daily_kpi</code>), 담기율 배수는{' '}
              <code>contracts/dashboard-mart-api-spec.md</code> §6-2 로 데이터 파트에 요청한 마트에서 옵니다. 마트 응답이
              오면 배지가 "실측" 으로 바뀝니다.
            </dd>
          </dl>
        </details>
      </Panel>

      <div className="grid grid--2">
        <Panel title="고객이 드래그한 성분 TOP 10" source={source.scraped} fold aside="원문 미저장 · 성분 사전 표준명만 (vocab 0.4)">
          <BarList
            items={scrapedIngredients.map((i) => ({
              label: labelKo(i.name),
              value: i.count,
              hint: i.copyCount === null ? undefined : `복사 ${i.copyCount}`,
            }))}
          />
          <p className="note">
            드래그 횟수는 관심의 크기입니다. 설명이 어려운지는 이 성분 구간의 되돌아 읽기·이탈·담기율을 함께 봐야 알 수
            있고, 그 집계는 데이터 마트가 만들면 여기에 붙습니다.
          </p>
        </Panel>

        <Panel title="이 행동을 한 사람은 더 담나" source={source.behaviors} fold aside="한 방문 vs 안 한 방문">
          <table className="table">
            <thead>
              <tr>
                <th>행동</th>
                <th>한 방문</th>
                <th>했을 때 담기율</th>
                <th>안 했을 때</th>
              </tr>
            </thead>
            <tbody>
              {validationBehaviors.map((v) => (
                <tr key={v.event}>
                  <td>
                    {v.ko} <span className="table__code">{v.event}</span>
                  </td>
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
