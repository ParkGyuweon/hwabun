import { useMemo, useState } from 'react';
import { Panel } from '../components';
import { products } from '../lib/metrics';
import { DEMO_BRAND } from '../../mocks/products';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand, updateFeedback } from '../../lib/feedbackStore';
import { FEEDBACK_AXES, FEEDBACK_VOCAB_VERSION, categoryDesc, categoryLabel, isUnclassified } from '../../types/feedback';
import type { Feedback } from '../../types/feedback';
import { labelKo } from '../../lib/formLabels';

type AxisFilter = string | 'all' | 'pending';

const UNCLASSIFIED = '__pending__';

/**
 * 고객 피드백 인박스 — 축 → 카테고리 → 원문 순서로 내려간다.
 *
 * 집계 grain 은 계약대로 (product_id, axis_id, category_id) 이고 상품별 보기는 필터다.
 * 같은 "펌프 막힘" 을 상품마다 따로 세면 문제가 상품 수만큼 갈라져서 사장님이 무엇을
 * 먼저 고칠지 못 본다. 그래서 첫 화면은 카테고리별 건수이고, 원문은 그 아래 펼쳐진다.
 *
 * 금지어가 걸린 행(hidden_by_default)은 접어 두고 눌러야 본문을 보여준다. 집계에서는 빼지
 * 않는다 — 욕이 섞여도 "펌프 막힘" 은 사장님이 봐야 할 내용이다 (계약 §1·§4).
 */
export default function FeedbackScreen() {
  const all = useFeedback();
  const mine = useMemo(() => feedbackForBrand(all, DEMO_BRAND), [all]);

  const [axis, setAxis] = useState<AxisFilter>('all');
  const [productId, setProductId] = useState<string>('all');
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  const scoped = useMemo(
    () => mine.filter((f) => productId === 'all' || f.product_id === productId),
    [mine, productId],
  );

  const axisCounts = useMemo(() => {
    const c = new Map<string, number>();
    for (const f of scoped) {
      const k = f.axis_id ?? UNCLASSIFIED;
      c.set(k, (c.get(k) ?? 0) + 1);
    }
    return c;
  }, [scoped]);

  const rows = useMemo(
    () =>
      scoped.filter((f) =>
        axis === 'all' ? true : axis === 'pending' ? isUnclassified(f) : f.axis_id === axis,
      ),
    [scoped, axis],
  );

  /** (category_id) → 행들. 계약 grain 의 category 축. 건수 많은 순 */
  const groups = useMemo(() => {
    const m = new Map<string, Feedback[]>();
    for (const f of rows) {
      const k = f.category_id ?? UNCLASSIFIED;
      const list = m.get(k) ?? [];
      list.push(f);
      m.set(k, list);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [rows]);

  const newCount = mine.filter((f) => f.status === 'new').length;
  const reflectedCount = mine.filter((f) => f.status === 'reflected').length;
  const pendingCount = mine.filter(isUnclassified).length;
  const productName = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;

  const reflect = (f: Feedback) => {
    const reply = (draft[f.feedback_id] ?? '').trim();
    updateFeedback(f.feedback_id, { status: 'reflected', reply: reply || null });
  };

  const axisTitle =
    axis === 'all' ? '전체' : axis === 'pending' ? '분류 대기' : FEEDBACK_AXES.find((a) => a.id === axis)?.label ?? axis;

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
          {pendingCount > 0 ? ` · 분류 대기 ${pendingCount}건` : ''}
        </p>
        <p className="scope__note">
          리뷰가 아니라 고쳐 달라는 의견입니다. 고객이 쓴 글을 AI가 어휘 {FEEDBACK_VOCAB_VERSION} 기준 5축 20종으로 나눴습니다.
          같은 문제는 상품이 달라도 한 칸에 모입니다. 반영했으면 한 줄 남겨 주세요. 그 한 줄이 고객 화면에 그대로 갑니다.
        </p>
      </div>

      <Panel title="무엇을 고쳐 달라고 하나 — 축별 건수" source="real">
        <div className="chips">
          <button type="button" className={`chip${axis === 'all' ? ' chip--hit' : ''}`} onClick={() => setAxis('all')}>
            전체 {scoped.length}
          </button>
          {FEEDBACK_AXES.map((a) => (
            <button
              key={a.id}
              type="button"
              className={`chip${axis === a.id ? ' chip--hit' : ''}`}
              title={a.desc}
              onClick={() => setAxis(a.id)}
            >
              {a.label} {axisCounts.get(a.id) ?? 0}
            </button>
          ))}
          {(axisCounts.get(UNCLASSIFIED) ?? 0) > 0 ? (
            <button
              type="button"
              className={`chip chip--pending${axis === 'pending' ? ' chip--hit' : ''}`}
              title="쇼핑몰에서 방금 들어온 글. 분류기가 돌면 축·카테고리가 붙습니다"
              onClick={() => setAxis('pending')}
            >
              분류 대기 {axisCounts.get(UNCLASSIFIED)}
            </button>
          ) : null}
        </div>
        {axis === 'other' ? (
          <p className="note">
            기타에 쌓인 글은 어휘에 없는 문제입니다. 여러 상품에 걸쳐 반복되면 어휘에 항목을 추가합니다 (계약 §6). 분류기가 스스로 이름을 짓지는 않습니다.
          </p>
        ) : null}
      </Panel>

      <Panel title={`${axisTitle} — 카테고리별`} source="real" aside={`${rows.length}건`}>
        {rows.length === 0 ? (
          <p className="feedback-inbox__empty">
            아직 없습니다. 쇼핑몰 상품 페이지의 "의견 남기기" 에서 들어온 글이 분류돼 여기 쌓입니다.
          </p>
        ) : (
          <div className="fb-groups">
            {groups.map(([categoryId, list]) => {
              const pending = categoryId === UNCLASSIFIED;
              const productCount = new Set(list.map((f) => f.product_id)).size;
              return (
                <section key={categoryId} className={`fb-group${pending ? ' fb-group--pending' : ''}`}>
                  <header className="fb-group__head">
                    <h3 className="fb-group__title">{pending ? '분류 대기' : categoryLabel(categoryId)}</h3>
                    <span className="fb-group__count">{list.length}건</span>
                    {productCount > 1 ? <span className="fb-group__products">상품 {productCount}개에서</span> : null}
                    {!pending ? <span className="fb-group__desc">{categoryDesc(categoryId)}</span> : null}
                  </header>
                  <ul className="feedback-inbox">
                    {list.map((f) => {
                      const hidden = f.hidden_by_default && !revealed[f.feedback_id];
                      return (
                        <li key={f.feedback_id} className={`feedback-inbox__item is-${f.status}`}>
                          <div className="feedback-inbox__meta">
                            <span className="feedback-inbox__product">{productName(f.product_id)}</span>
                            {f.profile ? (
                              <span className="feedback-inbox__profile" title="작성자 피부 (계약: 비익명)">
                                {labelKo(f.profile.skin_type)} · {labelKo(f.profile.skin_tone)}
                              </span>
                            ) : null}
                            <span className="feedback-inbox__when">{f.created_at.slice(0, 10)}</span>
                            <span className={`feedback-inbox__status feedback-inbox__status--${f.status}`}>
                              {f.status === 'reflected' ? '반영' : f.status === 'read' ? '읽음' : '새 의견'}
                            </span>
                          </div>
                          {hidden ? (
                            <button
                              type="button"
                              className="feedback-inbox__hidden"
                              onClick={() => setRevealed({ ...revealed, [f.feedback_id]: true })}
                            >
                              금지어 포함 · 눌러서 보기
                            </button>
                          ) : (
                            <p className="feedback-inbox__text">{f.body}</p>
                          )}
                          {f.status === 'reflected' ? (
                            <p className="feedback-inbox__reply">
                              답글: {f.reply ?? '(없음)'} · {f.replied_at?.slice(0, 10)}
                            </p>
                          ) : (
                            <div className="feedback-inbox__actions">
                              {f.status === 'new' ? (
                                <button
                                  type="button"
                                  className="chip"
                                  onClick={() => updateFeedback(f.feedback_id, { status: 'read' })}
                                >
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
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
