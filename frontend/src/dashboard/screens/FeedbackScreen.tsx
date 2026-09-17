import { useMemo, useState, useEffect } from 'react';
import { fetchSellerFeedback } from '../../lib/shopApi';
import { loadBrandId } from '../../lib/brands';
import { OriginBadge, Panel } from '../components';
import { feedbackProducts as products } from '../lib/metrics';
import { FEEDBACK_BRAND } from '../lib/scope';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand, updateFeedback } from '../../lib/feedbackStore';
import { findAdTerms } from '../../lib/adTerms';
import { skinTypeLabel, humanizeAttribute } from '../../lib/format';
import {
  FEEDBACK_INPUT_AXES,
  FEEDBACK_VOCAB_VERSION,
  categoryDesc,
  categoryLabel,
  isUnclassified,
  labelsOf,
} from '../../types/feedback';
import type { Feedback } from '../../types/feedback';

type AxisFilter = string | 'all' | 'pending';

const PENDING = '__pending__';

/** 축 → 담당 (명세 F1). 축 하나가 한 팀으로 간다 */
const ROUTE: Record<string, { key: 'formula' | 'packaging' | 'pricing'; label: string }> = {
  efficacy: { key: 'formula', label: '처방' },
  texture: { key: 'formula', label: '처방' },
  scent: { key: 'formula', label: '처방' },
  packaging: { key: 'packaging', label: '포장' },
  value: { key: 'pricing', label: '가격·상품기획' },
};

/** 축 색. 누적 막대·표 막대에서만 쓴다. 회색 계열 + 브랜드·액센트 (§3-6) */
const AXIS_COLOR: Record<string, string> = {
  efficacy: 'var(--brand)',
  texture: '#8fb0a5',
  scent: 'var(--accent)',
  packaging: 'var(--support)',
  value: '#b9944f',
  other: 'var(--ink-faint)',
};

const STATUS_KO = { new: '새 의견', read: '읽음', reflected: '반영' } as const;

/**
 * 고객 피드백. 결론 한 줄 → 축 분포 → 카테고리 표 → 원문 순으로 내려간다.
 * 집계 grain 은 계약대로 (product_id, axis_id, category_id). 상품·축·카테고리는 전부 필터다.
 * 금지어가 걸린 행은 접어 두고 눌러야 본문을 보여준다. 집계에서는 빼지 않는다.
 */
export default function FeedbackScreen() {
  const all = useFeedback();
  /**
   * 백엔드 피드백(GET /api/seller/feedback)을 로컬 저장본과 합친다.
   * 브랜드 id 는 대시보드 로그인 때 저장된 값. 없거나 백엔드가 없으면 로컬만 보인다.
   */
  const [remote, setRemote] = useState<Feedback[]>([]);
  useEffect(() => {
    const brandId = loadBrandId();
    if (!brandId) return;
    let alive = true;
    void fetchSellerFeedback(brandId, FEEDBACK_BRAND).then((rows) => {
      if (alive && rows) setRemote(rows);
    });
    return () => {
      alive = false;
    };
  }, []);
  const mine = useMemo(() => {
    const local = feedbackForBrand(all, FEEDBACK_BRAND);
    const seen = new Set(local.map((f) => f.feedback_id));
    return [...remote.filter((f) => !seen.has(f.feedback_id)), ...local];
  }, [all, remote]);

  const [axis, setAxis] = useState<AxisFilter>('all');
  const [category, setCategory] = useState<string | null>(null);
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
      const k = f.axis_id ?? PENDING;
      c.set(k, (c.get(k) ?? 0) + 1);
    }
    return c;
  }, [scoped]);

  const byAxis = useMemo(
    () =>
      scoped.filter((f) =>
        axis === 'all' ? true : axis === 'pending' ? isUnclassified(f) : f.axis_id === axis,
      ),
    [scoped, axis],
  );

  /**
   * 카테고리 표. **언급 수** 많은 순 (계약 0.2.0 §4). 한 건이 labels 를 둘 가지면 두 칸에 각 1씩 —
   * 카테고리별 합이 피드백 수를 넘을 수 있다. 분류 대기는 맨 아래
   */
  const categories = useMemo(() => {
    const m = new Map<string, Feedback[]>();
    for (const f of byAxis) {
      const labels = labelsOf(f);
      if (labels.length === 0) {
        m.set(PENDING, [...(m.get(PENDING) ?? []), f]);
        continue;
      }
      for (const l of labels) m.set(l.category_id, [...(m.get(l.category_id) ?? []), f]);
    }
    return [...m.entries()]
      .map(([id, list]) => ({
        id,
        list,
        axisId: list[0]?.axis_id ?? 'other',
        products: new Set(list.map((f) => f.product_id)).size,
        fresh: list.filter((f) => f.status === 'new').length,
      }))
      .sort((a, b) => (a.id === PENDING ? 1 : b.id === PENDING ? -1 : b.list.length - a.list.length));
  }, [byAxis]);

  const rows = useMemo(
    () =>
      category
        ? byAxis.filter((f) => (category === PENDING ? isUnclassified(f) : labelsOf(f).some((l) => l.category_id === category)))
        : byAxis,
    [byAxis, category],
  );

  const total = mine.length;
  const fresh = mine.filter((f) => f.status === 'new').length;
  const reflected = mine.filter((f) => f.status === 'reflected').length;
  const maxCategory = Math.max(1, ...categories.filter((c) => c.id !== PENDING).map((c) => c.list.length));

  /** 결론 한 줄 (명세 F2). LLM 없이 상위 2개 카테고리로 만든다 */
  const verdict = useMemo(() => {
    const top = [...mine.reduce((m, f) => {
      for (const l of labelsOf(f)) m.set(l.category_id, (m.get(l.category_id) ?? 0) + 1);
      return m;
    }, new Map<string, number>()).entries()].sort((a, b) => b[1] - a[1]);
    if (top.length === 0) return null;
    const [first, second] = top;
    const has = (f: Feedback, id: string) => labelsOf(f).some((l) => l.category_id === id);
    const firstProducts = new Set(mine.filter((f) => has(f, first[0])).map((f) => f.product_id)).size;
    const routes = [...new Set(top.slice(0, 2).map(([id]) => mine.find((f) => has(f, id))?.axis_id ?? ''))]
      .map((a) => ROUTE[a])
      .filter(Boolean);
    return {
      headline: second
        ? `${categoryLabel(first[0])} 언급 ${first[1]} · ${categoryLabel(second[0])} 언급 ${second[1]}`
        : `${categoryLabel(first[0])} 언급 ${first[1]}`,
      reason:
        first[1] >= 5 && firstProducts >= 2
          ? `${categoryLabel(first[0])}: 상품 ${firstProducts}개에서 반복. 한 상품 문제가 아닙니다.`
          : `${categoryLabel(first[0])}: 상품 ${firstProducts}개.`,
      routes,
    };
  }, [mine]);

  const productName = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;
  const reflect = (f: Feedback) => {
    const reply = (draft[f.feedback_id] ?? '').trim();
    updateFeedback(f.feedback_id, { status: 'reflected', reply: reply || null });
  };
  const pickAxis = (next: AxisFilter) => {
    setAxis(next);
    setCategory(null);
  };

  const axisLabelOf = (id: AxisFilter) =>
    id === 'all' ? '전체' : id === 'pending' ? '분류 대기' : (FEEDBACK_INPUT_AXES.find((a) => a.id === id)?.label ?? id);

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
          {total}건 · 새 의견 {fresh} · 반영 {reflected} · 어휘 {FEEDBACK_VOCAB_VERSION}
        </p>
      </div>

      {verdict ? (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            가장 많이 고쳐 달라는 것 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">{verdict.headline}</h2>
          <p className="verdict__reason">{verdict.reason}</p>
          <div className="fbx-verdict__routes">
            {verdict.routes.map((r) => (
              <span key={r.key} className={`fbx-route fbx-route--${r.key}`}>
                담당 · {r.label}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <Panel title="축별 건수" source="real" aside={`${scoped.length}건`}>
        <div className="fbx-axes">
          <div className="fbx-stack" aria-hidden="true">
            {FEEDBACK_INPUT_AXES.map((a) => {
              const n = axisCounts.get(a.id) ?? 0;
              if (n === 0) return null;
              return (
                <span
                  key={a.id}
                  className={`fbx-stack__seg${axis !== 'all' && axis !== a.id ? ' is-dim' : ''}`}
                  style={{ width: `${(n / Math.max(1, scoped.length)) * 100}%`, ['--seg' as string]: AXIS_COLOR[a.id] }}
                  title={`${a.label} ${n}`}
                />
              );
            })}
          </div>
          <ul className="fbx-axis-list">
            <li>
              <button type="button" className={`fbx-axis${axis === 'all' ? ' is-active' : ''}`} onClick={() => pickAxis('all')}>
                전체 <span className="fbx-axis__n">{scoped.length}</span>
              </button>
            </li>
            {FEEDBACK_INPUT_AXES.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  className={`fbx-axis${axis === a.id ? ' is-active' : ''}`}
                  style={{ ['--seg' as string]: AXIS_COLOR[a.id] }}
                  title={a.desc}
                  onClick={() => pickAxis(a.id)}
                >
                  <span className="fbx-axis__swatch" aria-hidden="true" />
                  {a.label} <span className="fbx-axis__n">{axisCounts.get(a.id) ?? 0}</span>
                </button>
              </li>
            ))}
            {(axisCounts.get(PENDING) ?? 0) > 0 ? (
              <li>
                <button
                  type="button"
                  className={`fbx-axis fbx-axis--pending${axis === 'pending' ? ' is-active' : ''}`}
                  onClick={() => pickAxis('pending')}
                >
                  분류 대기 <span className="fbx-axis__n">{axisCounts.get(PENDING)}</span>
                </button>
              </li>
            ) : null}
          </ul>
        </div>
      </Panel>

      <Panel title={`${axisLabelOf(axis)} · 카테고리`} source="real" aside="행을 누르면 원문만 추립니다">
        {categories.length === 0 ? (
          <p className="fbx-empty">아직 없습니다. 쇼핑몰 상품 페이지에서 들어온 글이 여기 쌓입니다.</p>
        ) : (
          <div className="table-wrap">
            <table className="fbx-table">
              <thead>
                <tr>
                  <th>카테고리</th>
                  <th>담당</th>
                  <th className="is-num" title="한 글에 불만이 둘이면 두 칸에 각 1. 합이 글 수를 넘을 수 있습니다">언급</th>
                  <th style={{ width: '22%' }} aria-label="비중" />
                  <th className="is-num">상품</th>
                  <th className="is-num">새 의견</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((c) => {
                  const pending = c.id === PENDING;
                  const route = ROUTE[c.axisId];
                  return (
                    <tr
                      key={c.id}
                      className={category === c.id ? 'is-active' : ''}
                      onClick={() => setCategory(category === c.id ? null : c.id)}
                    >
                      <td>
                        <span className="fbx-table__name">{pending ? '분류 대기' : categoryLabel(c.id)}</span>
                        {!pending ? (
                          <span className="fbx-table__desc">
                            {c.id === 'other' ? '이 축 얘기지만 목록에 없는 불만' : categoryDesc(c.id)}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        {route ? <span className={`fbx-route fbx-route--${route.key}`}>{route.label}</span> : null}
                      </td>
                      <td className="is-num">
                        <b>{c.list.length}</b>
                      </td>
                      <td>
                        {!pending ? (
                          <span className="fbx-table__track">
                            <span
                              className="fbx-table__bar"
                              style={{ width: `${(c.list.length / maxCategory) * 100}%`, ['--seg' as string]: AXIS_COLOR[c.axisId] }}
                            />
                          </span>
                        ) : null}
                      </td>
                      <td className="is-num">{c.products}</td>
                      <td className="is-num">{c.fresh > 0 ? <span className="fbx-table__new">{c.fresh}</span> : '–'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {axis === 'other' ? <p className="note">기타에 같은 문제가 여러 상품에서 반복되면 어휘에 항목을 추가합니다.</p> : null}
      </Panel>

      {rows.length > 0 ? (
        <Panel title="원문" source="real" fold aside={`${rows.length}건`}>
          <div className="fbx-inbox__head">
            <h3>{category ? (category === PENDING ? '분류 대기' : categoryLabel(category)) : axisLabelOf(axis)}</h3>
            <small>반영했으면 한 줄 남기세요. 고객 화면에 그대로 갑니다.</small>
            {category ? (
              <button type="button" className="fbx-inbox__reset" onClick={() => setCategory(null)}>
                카테고리 해제
              </button>
            ) : null}
          </div>
          <ul className="fbx-inbox">
            {rows.map((f) => {
              const hidden = f.hidden_by_default && !revealed[f.feedback_id];
              const text = draft[f.feedback_id] ?? '';
              const hits = findAdTerms(text);
              return (
                <li key={f.feedback_id} className={`fbx-card is-${f.status}`}>
                  <div className="fbx-card__meta">
                    <span className="fbx-card__product">{productName(f.product_id)}</span>
                    {labelsOf(f).map((l) => (
                      <span key={l.category_id} className="fbx-card__cat">{categoryLabel(l.category_id)}</span>
                    ))}
                    {f.profile ? (
                      <span title="작성자 피부">
                        {skinTypeLabel(f.profile.skin_type)} · {humanizeAttribute(f.profile.skin_tone)}
                      </span>
                    ) : null}
                    <span className="fbx-card__when">{f.created_at.slice(0, 10)}</span>
                    <span className={`fbx-status fbx-status--${f.status}`}>{STATUS_KO[f.status]}</span>
                  </div>

                  {hidden ? (
                    <button
                      type="button"
                      className="fbx-card__hidden"
                      onClick={() => setRevealed({ ...revealed, [f.feedback_id]: true })}
                    >
                      금지어 포함 · 눌러서 보기
                    </button>
                  ) : (
                    <p className="fbx-card__body">{f.body}</p>
                  )}

                  {f.status === 'reflected' ? (
                    <blockquote className="fbx-card__reply">
                      <span>{f.reply ?? '답글 없이 반영'}</span>
                      <small>{FEEDBACK_BRAND} · {f.replied_at?.slice(0, 10)}</small>
                    </blockquote>
                  ) : (
                    <div className="fbx-card__actions">
                      {f.status === 'new' ? (
                        <button type="button" className="fbx-btn" onClick={() => updateFeedback(f.feedback_id, { status: 'read' })}>
                          읽음
                        </button>
                      ) : (
                        <span />
                      )}
                      <div className={`fbx-reply${hits.length ? ' has-warning' : ''}`}>
                        <input
                          placeholder="어떻게 반영했는지 한 줄"
                          value={text}
                          aria-label="반영 답글"
                          onChange={(e) => setDraft({ ...draft, [f.feedback_id]: e.target.value })}
                        />
                        {hits.length ? (
                          <p className="fbx-reply__warn">
                            {hits.map((h) => (
                              <span key={h.term}>
                                <b>{h.term}</b> {h.level === 'forbidden' ? '금지' : h.why}
                                {' · '}
                              </span>
                            ))}
                            화장품법 제13조
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className="fbx-btn fbx-btn--primary"
                        disabled={hits.some((h) => h.level === 'forbidden')}
                        onClick={() => reflect(f)}
                      >
                        반영했어요
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
