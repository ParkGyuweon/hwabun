import { useCallback, useEffect, useRef, useState } from 'react';
import { Panel } from '../components';
import { fmt } from '../lib/metrics';
import { fetchRefreshJob, fetchSellerInsight, requestInsightRefresh } from '../lib/insightApi';
import type { InsightRead } from '../lib/insightApi';
import type { SellerInsight } from '../../types/insight';

/**
 * "AI 가 정리한 고객 목소리" 카드 (고객의 말 화면 맨 위).
 *
 * 사장님은 원문 수백 줄을 읽지 않는다. 그 대신 **무엇이 가장 많이 나왔고, 안 산 사람은 왜 안 샀고, 지금 뭘 하면
 * 되는지** 세 가지만 본다. 근거 원문은 접어 둔다 — 감추는 게 아니라 결론부터 읽게 하려는 것.
 *
 * 요약은 서버가 06:00 에 하루 한 번 만든다. 그 뒤 쌓인 글이 있으면 `newSince` 가 0 보다 크고, 사장님이 "즉시 반영"
 * 을 누르면 그 시점까지의 글로 다시 만든다. 프론트는 버튼·조회·기다리는 표시만 한다.
 *
 * 서버가 아직 없으면(`unavailable`) 그 사실을 적고 버튼을 잠근다. 규칙 표로 대신 쓰지 않는다 — 원문 없이 만든
 * 요약은 없는 사실이 된다.
 */
export default function InsightCard({ brandId, productId }: { brandId: string | null; productId: string | null }) {
  const [read, setRead] = useState<InsightRead | { kind: 'loading' }>({ kind: 'loading' });
  const [phase, setPhase] = useState<'idle' | 'requesting' | 'polling'>('idle');
  const [notice, setNotice] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const lockTimer = useRef<number | null>(null);
  const pollTimer = useRef<number | null>(null);

  const load = useCallback(async () => {
    if (!brandId) return;
    const r = await fetchSellerInsight(brandId, productId);
    setRead(r);
  }, [brandId, productId]);

  useEffect(() => {
    if (!brandId) return;
    let alive = true;
    setRead({ kind: 'loading' });
    void fetchSellerInsight(brandId, productId).then((r) => {
      if (alive) setRead(r);
    });
    return () => {
      alive = false;
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
      if (lockTimer.current !== null) window.clearTimeout(lockTimer.current);
    };
  }, [brandId, productId]);

  /** 202 를 받으면 2초마다 묻는다. 60초를 넘기면 포기하고 마지막 완성본을 다시 읽는다 */
  const poll = useCallback(
    (jobId: string, startedAt: number) => {
      const tick = async () => {
        const r = await fetchRefreshJob(jobId);
        if (r.state === 'done') {
          setPhase('idle');
          if (r.insight) setRead({ kind: 'ready', insight: r.insight });
          else await load();
          setNotice('새 의견까지 읽어 다시 정리했습니다.');
          return;
        }
        if (r.state === 'failed' || Date.now() - startedAt > 60_000) {
          setPhase('idle');
          setNotice('다시 정리하지 못했습니다. 잠시 뒤 눌러 주세요.');
          await load();
          return;
        }
        pollTimer.current = window.setTimeout(tick, 2000);
      };
      pollTimer.current = window.setTimeout(tick, 2000);
    },
    [load],
  );

  const refresh = async () => {
    if (!brandId || phase !== 'idle') return;
    setPhase('requesting');
    setNotice(null);
    const r = await requestInsightRefresh(brandId, productId);
    if (r.kind === 'done') {
      setRead({ kind: 'ready', insight: r.insight });
      setPhase('idle');
      setNotice('새 의견까지 읽어 다시 정리했습니다.');
    } else if (r.kind === 'accepted') {
      setPhase('polling');
      poll(r.jobId, Date.now());
    } else if (r.kind === 'rejected') {
      setPhase('idle');
      if (r.retryAfterSec) {
        setLocked(true);
        if (lockTimer.current !== null) window.clearTimeout(lockTimer.current);
        lockTimer.current = window.setTimeout(() => setLocked(false), r.retryAfterSec * 1000);
      }
      setNotice(
        r.reason === 'nothing_new'
          ? '새 의견이 없어 그대로 둡니다.'
          : `방금 정리했습니다. ${r.retryAfterSec ? `${Math.ceil(r.retryAfterSec / 60)}분 뒤` : '잠시 뒤'} 다시 누를 수 있습니다.`,
      );
    } else {
      setPhase('idle');
      setNotice('AI 정리에 연결하지 못했습니다.');
    }
  };

  const unavailable = read.kind === 'unavailable';
  const insight = read.kind === 'ready' ? read.insight : null;

  const aside = (
    <div className="ai__aside">
      <span className="ai__stamp">{stampOf(read)}</span>
      <button
        type="button"
        className="fbx-btn fbx-btn--primary"
        onClick={refresh}
        disabled={!brandId || unavailable || phase !== 'idle' || locked}
        aria-busy={phase !== 'idle'}
        title={unavailable ? 'AI 정리가 연결되면 누를 수 있습니다' : '쌓인 리뷰·피드백을 읽어 다시 정리합니다. 매일 아침 6시에는 자동으로 정리됩니다'}
      >
        {phase === 'idle' ? '지금 다시 정리' : '다시 읽는 중'}
      </button>
    </div>
  );

  return (
    <Panel title="AI가 정리한 고객 목소리" source={insight ? 'real' : 'none'} origin="mine" aside={aside}>
      {notice ? <p className="note ai__notice" role="status">{notice}</p> : null}
      {phase !== 'idle' ? (
        <p className="ai__progress" aria-live="polite">
          <span className="ai__dot" aria-hidden="true" />
          다시 읽고 있습니다. 몇 초 걸립니다.
        </p>
      ) : null}

      {read.kind === 'loading' ? <p className="note">받는 중입니다.</p> : null}

      {unavailable ? <p className="note">AI 정리가 아직 연결되지 않았습니다. 아래 원문을 읽어 주세요.</p> : null}

      {read.kind === 'empty' ? <p className="note">아직 정리한 내용이 없습니다. 위 버튼으로 지금 만들 수 있습니다.</p> : null}

      {insight ? <InsightBody insight={insight} /> : null}
    </Panel>
  );
}

function stampOf(read: InsightRead | { kind: 'loading' }): string {
  if (read.kind !== 'ready') return read.kind === 'unavailable' ? '연결 전' : read.kind === 'empty' ? '아직 없음' : '';
  const i = read.insight;
  const at = i.generatedAt.slice(0, 16).replace('T', ' ');
  const how = i.source === 'manual' ? '직접 요청' : '아침 6시 자동';
  const fresh = i.newSince > 0 ? ` · 이후 새 의견 ${fmt.int(i.newSince)}건` : '';
  return `마지막 정리 ${at} (${how})${fresh}`;
}

function InsightBody({ insight }: { insight: SellerInsight }) {
  const { summary, evidence, inputCount } = insight;
  const empty = summary.topComplaints.length === 0 && summary.preBuyDropReasons.length === 0 && summary.actions.length === 0;
  if (empty) {
    return <p className="note">읽은 글 {fmt.int(inputCount.feedback + inputCount.review)}건 · 공통 의견이 아직 없습니다</p>;
  }
  return (
    <div className="ai">
      <div className="ai__cols">
        <section className="ai__col">
          <h3 className="ai__h">가장 많이 나온 불만</h3>
          {summary.topComplaints.length === 0 ? (
            <p className="note">여러 고객이 함께 말한 불만이 없습니다</p>
          ) : (
            <ol className="ai__list">
              {summary.topComplaints.map((c) => (
                <li key={c.text}>
                  <span className="ai__text">{c.text}</span>
                  <span className="ai__count">{fmt.int(c.count)}건</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="ai__col">
          <h3 className="ai__h">안 산 사람이 남긴 이유</h3>
          {summary.preBuyDropReasons.length === 0 ? (
            <p className="note">사지 않은 사람의 의견이 아직 없습니다</p>
          ) : (
            <ol className="ai__list">
              {summary.preBuyDropReasons.map((c) => (
                <li key={c.text}>
                  <span className="ai__text">{c.text}</span>
                  <span className="ai__count">{fmt.int(c.count)}건</span>
                </li>
              ))}
            </ol>
          )}
          <p className="ai__sub" title="읽은 글 100개 중 가격을 말한 글의 수">
            가격 언급 {summary.priceMentionRate === null ? '아직 없음' : `${Math.round(summary.priceMentionRate * 100)}%`}
          </p>
        </section>

        <section className="ai__col ai__col--act">
          <h3 className="ai__h">지금 할 일</h3>
          {summary.actions.length === 0 ? (
            <p className="note">지금 바로 할 일은 없습니다</p>
          ) : (
            <ol className="ai__acts">
              {summary.actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <details className="act__more">
        <summary>
          읽은 글 · 피드백 {fmt.int(inputCount.feedback)} · 리뷰 {fmt.int(inputCount.review)}
          {evidence.length > 0 ? ` · 근거 ${evidence.length}줄` : ''}
        </summary>
        {evidence.length === 0 ? (
          <p className="note">따로 뽑은 근거 문장이 없습니다</p>
        ) : (
          <ul className="act__basis">
            {evidence.map((e) => (
              <li key={`${e.type}-${e.id}`}>
                <span className="act__from">{e.type === 'review' ? '리뷰' : '피드백'}</span>
                {e.quote}
              </li>
            ))}
          </ul>
        )}
        <p className="ai__sub-note" title="효능이나 원인을 단정하지 않습니다. 글에 나온 말을 세어 모은 것입니다">
          결정은 원문을 한 번 더 보고 내리세요
        </p>
      </details>
    </div>
  );
}
