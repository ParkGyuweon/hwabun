import { useMemo, useState } from 'react';
import { Panel } from '../components';
import { products } from '../lib/metrics';
import { DEMO_BRAND } from '../../mocks/products';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand, updateFeedback } from '../../lib/feedbackStore';
import { FEEDBACK_ASPECTS } from '../../types/feedback';
import type { Feedback, FeedbackAspect } from '../../types/feedback';

type AspectFilter = FeedbackAspect | 'all';

/**
 * 고객 피드백 인박스 — 분류별로 나눠서 받는다.
 *
 * 사장님 입장에서 향·용기는 포장 담당, 성분·제형은 처방 담당이라 같은 목록에 섞이면
 * 일이 안 된다. 그래서 분류 탭이 첫 화면이다. 읽음 → 반영 처리를 하면 소비자 화면에
 * "반영됐습니다" 와 답글이 돌아간다 (루프 ④).
 */
export default function FeedbackScreen() {
  const all = useFeedback();
  const mine = useMemo(() => feedbackForBrand(all, DEMO_BRAND), [all]);

  const [aspect, setAspect] = useState<AspectFilter>('all');
  const [productId, setProductId] = useState<string>('all');
  const [draft, setDraft] = useState<Record<string, string>>({});

  const counts = useMemo(() => {
    const c = new Map<FeedbackAspect, number>();
    for (const f of mine) for (const a of f.aspects) c.set(a, (c.get(a) ?? 0) + 1);
    return c;
  }, [mine]);

  const rows = useMemo(
    () =>
      mine.filter(
        (f) => (aspect === 'all' || f.aspects.includes(aspect)) && (productId === 'all' || f.product_id === productId),
      ),
    [mine, aspect, productId],
  );

  const newCount = mine.filter((f) => f.status === 'new').length;
  const reflectedCount = mine.filter((f) => f.status === 'reflected').length;
  const productName = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;

  const reflect = (f: Feedback) => {
    const reply = (draft[f.feedback_id] ?? '').trim();
    updateFeedback(f.feedback_id, { status: 'reflected', reply: reply || null });
  };

  return (
    <div className="stack">
      <div className="scope">
        <label className="scope__field">
          <span className="scope__label">상품</span>
          <select value={productId} onChange={(e) => setProductId(e.target.value)} aria-label="상품 선택">
            <option value="all">전체 상품</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.product_name}
              </option>
            ))}
          </select>
        </label>
        <p className="scope__meta">
          전체 {mine.length}건 · 새 의견 {newCount}건 · 반영 {reflectedCount}건
        </p>
        <p className="scope__note">
          리뷰가 아니라 의견입니다. 분류별로 나눠서 보고, 반영했으면 한 줄 남겨 주세요. 그 한 줄이 고객 화면에 그대로 갑니다.
        </p>
      </div>

      <Panel title="분류별로 받은 의견" source="real">
        <div className="chips">
          <button
            type="button"
            className={`chip${aspect === 'all' ? ' chip--hit' : ''}`}
            onClick={() => setAspect('all')}
          >
            전체 {mine.length}
          </button>
          {FEEDBACK_ASPECTS.map((a) => (
            <button
              key={a.key}
              type="button"
              className={`chip${aspect === a.key ? ' chip--hit' : ''}`}
              onClick={() => setAspect(a.key)}
            >
              {a.label} {counts.get(a.key) ?? 0}
            </button>
          ))}
        </div>
      </Panel>

      <Panel
        title={aspect === 'all' ? '받은 의견' : `${FEEDBACK_ASPECTS.find((a) => a.key === aspect)?.label} 의견`}
        source="real"
        aside={`${rows.length}건`}
      >
        {rows.length === 0 ? (
          <p className="feedback-inbox__empty">
            아직 없습니다. 쇼핑몰 상품 페이지의 "의견 남기기" 에서 들어온 의견이 여기 분류별로 쌓입니다.
          </p>
        ) : (
          <ul className="feedback-inbox">
            {rows.map((f) => (
              <li key={f.feedback_id} className={`feedback-inbox__item is-${f.status}`}>
                <div className="feedback-inbox__meta">
                  <span className="feedback-inbox__product">{productName(f.product_id)}</span>
                  <span className="feedback-inbox__aspects">
                    {f.aspects.map((k) => FEEDBACK_ASPECTS.find((a) => a.key === k)?.label ?? k).join(' · ')}
                  </span>
                  <span className="feedback-inbox__when">{f.created_at.slice(0, 10)}</span>
                  <span className={`feedback-inbox__status feedback-inbox__status--${f.status}`}>
                    {f.status === 'reflected' ? '반영' : f.status === 'read' ? '읽음' : '새 의견'}
                  </span>
                </div>
                <p className="feedback-inbox__text">{f.text}</p>
                {f.status === 'reflected' ? (
                  <p className="feedback-inbox__reply">
                    답글: {f.reply ?? '(없음)'} · {f.replied_at?.slice(0, 10)}
                  </p>
                ) : (
                  <div className="feedback-inbox__actions">
                    {f.status === 'new' ? (
                      <button type="button" className="chip" onClick={() => updateFeedback(f.feedback_id, { status: 'read' })}>
                        읽음
                      </button>
                    ) : null}
                    <input
                      className="feedback-inbox__reply-input"
                      placeholder="어떻게 반영했는지 한 줄 (고객에게 보입니다)"
                      value={draft[f.feedback_id] ?? ''}
                      onChange={(e) => setDraft({ ...draft, [f.feedback_id]: e.target.value })}
                    />
                    <button type="button" className="chip chip--hit" onClick={() => reflect(f)}>
                      반영했어요
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
