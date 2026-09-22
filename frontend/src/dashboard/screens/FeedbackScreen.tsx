import { useMemo, useState, useEffect } from 'react';
import { fetchSellerFeedback, respondToFeedback, startFeedbackClassification } from '../../lib/shopApi';
import { OriginBadge, Panel } from '../components';
import InsightCard from './InsightCard';
import { useBrandProducts } from '../lib/useBrandProducts';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForBrand, feedbackSource, updateFeedback } from '../../lib/feedbackStore';
import { findAdTerms } from '../../lib/adTerms';
import { skinTypeLabel, humanizeAttribute } from '../../lib/format';
import {
  FEEDBACK_INPUT_AXES,
  categoryDesc,
  categoryLabel,
  isUnclassified,
  labelsOf,
} from '../../types/feedback';
import { statusOfHandling } from '../../types/feedback';
import type { Feedback, FeedbackHandlingStatus, FeedbackResponseAction } from '../../types/feedback';

type AxisFilter = string | 'all' | 'pending';

const PENDING = '__pending__';

/** 분류 결과 재조회 간격·제한 시간. 끝나지 않아도 여기서 멈추고 지금 있는 것을 그대로 보여준다 */
const POLL_MS = 2500;
const WAIT_MS = 30_000;

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

/** 업체 처리 상태 문구 (백엔드 계약 2026-09-18). new=OPEN · read=ACKNOWLEDGED · reflected=IMPLEMENTED */
const STATUS_KO = { new: '아직 안 봤어요', read: '답변했어요', reflected: '반영했어요' } as const;

/** 분류기가 아직 종류를 정하지 못한 글에 붙이는 이름. 화면 곳곳에서 같은 말을 쓴다 */
const PENDING_LABEL = '종류 나누는 중';

/**
 * 고객 피드백. 결론 한 줄 → 축 분포 → 카테고리 표 → 원문 순으로 내려간다.
 * 집계 grain 은 계약대로 (product_id, axis_id, category_id). 상품·축·카테고리는 전부 필터다.
 * 금지어가 걸린 행은 접어 두고 눌러야 본문을 보여준다. 집계에서는 빼지 않는다.
 */
export default function FeedbackScreen({ brandId, brandName }: { brandId: string | null; brandName: string | null }) {
  const all = useFeedback();
  // 상품 목록은 로그인한 브랜드가 등록한 것. 전에는 번들 카탈로그의 SSAFY Beauty 8종으로 고정돼 있었다
  const { products: mine0 } = useBrandProducts(brandId, brandName);
  const products = useMemo(() => mine0 ?? [], [mine0]);
  /**
   * 백엔드 피드백(GET /api/seller/feedback)을 로컬 저장본과 합친다.
   * 브랜드 id 는 대시보드 로그인 때 저장된 값. 없거나 백엔드가 없으면 로컬만 보인다.
   */
  const [remote, setRemote] = useState<Feedback[]>([]);
  /** 마지막 읽기가 실패했는지. 빈 화면에 "없다" 대신 "못 읽었다" 를 적기 위해 기억한다 */
  const [remoteFailed, setRemoteFailed] = useState(false);
  /** 분류를 걸어 놓고 결과를 기다리는 중. 제한 시간 안에 안 끝나면 지금 있는 데이터를 그대로 둔다 */
  const [classifying, setClassifying] = useState(false);
  useEffect(() => {
    if (!brandId || !brandName) return;
    let alive = true;
    let timer: number | undefined;

    const pull = async (): Promise<boolean> => {
      const rows = await fetchSellerFeedback(brandId, brandName);
      if (!alive) return false;
      if (!rows) {
        setRemoteFailed(true);
        return false;
      }
      setRemoteFailed(false);
      setRemote(rows);
      // 백엔드 행이 하나도 PENDING 이 아니면 끝난 것. 행이 없어도 기다릴 이유가 없다
      return !rows.some((f) => f.classification_status === 'PENDING');
    };

    void (async () => {
      // 202(방금 걸었다)든 409(이미 돈다)든 정상이다. 엔드포인트가 없으면 그냥 한 번 읽고 끝낸다
      const start = await startFeedbackClassification(brandId);
      if (!alive) return;
      if (start === 'unavailable') {
        await pull();
        return;
      }
      setClassifying(true);
      const deadline = Date.now() + WAIT_MS;
      const step = async () => {
        if (!alive) return;
        const done = await pull();
        if (!alive) return;
        if (done || Date.now() >= deadline) {
          setClassifying(false);
          return;
        }
        timer = window.setTimeout(step, POLL_MS);
      };
      await step();
    })();

    return () => {
      alive = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [brandId, brandName]);
  const mine = useMemo(() => {
    // 번들 시드(SSAFY Beauty 30건)는 로그인한 브랜드가 그 이름일 때만 섞인다. 다른 브랜드에는 남의 피드백이다
    const local = brandName ? feedbackForBrand(all, brandName) : [];
    const seen = new Set(local.map((f) => f.feedback_id));
    return [...remote.filter((f) => !seen.has(f.feedback_id)), ...local];
  }, [all, remote, brandName]);

  /** 배지. 백엔드 행이나 이 사이트에서 쓴 글이 있으면 실측, 전부 번들 샘플이면 시드 */
  const source = useMemo(() => feedbackSource(mine), [mine]);

  const [axis, setAxis] = useState<AxisFilter>('all');
  const [category, setCategory] = useState<string | null>(null);
  const [productId, setProductId] = useState<string>('all');

  /**
   * 상품별 묶음 (1차 상품 → 2차 카테고리). 사장님은 "어느 제품이 문제냐" 부터 묻는다.
   * 축·카테고리 필터와 무관하게 브랜드 전체(`mine`)로 만든다 — 상품 목록 자체가 필터라서.
   * 카테고리 칩은 언급 수 많은 순, 한 글에 라벨이 둘이면 두 칩에 각 1
   */
  const byProduct = useMemo(() => {
    const m = new Map<string, Feedback[]>();
    for (const f of mine) m.set(f.product_id, [...(m.get(f.product_id) ?? []), f]);
    return [...m.entries()]
      .map(([id, list]) => {
        const cats = new Map<string, number>();
        let pending = 0;
        for (const f of list) {
          const labels = labelsOf(f);
          if (labels.length === 0) pending += 1;
          for (const l of labels) cats.set(l.category_id, (cats.get(l.category_id) ?? 0) + 1);
        }
        return {
          id,
          list,
          fresh: list.filter((f) => f.status === 'new').length,
          cats: [...cats.entries()].sort((a, b) => b[1] - a[1]),
          pending,
        };
      })
      .sort((a, b) => b.list.length - a.list.length);
  }, [mine]);
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
    const firstProductIds = [...new Set(mine.filter((f) => has(f, first[0])).map((f) => f.product_id))];
    const firstProducts = firstProductIds.length;
    // 상품 이름을 문장에 넣는다. "상품 5개" 만으로는 사장님이 어느 제품인지 모른다
    const named = (ids: string[]) => {
      const name = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;
      return ids.length <= 2 ? ids.map(name).join(' · ') : `${name(ids[0])} 외 ${ids.length - 1}개`;
    };
    const routes = [...new Set(top.slice(0, 2).map(([id]) => mine.find((f) => has(f, id))?.axis_id ?? ''))]
      .map((a) => ROUTE[a])
      .filter(Boolean);
    return {
      headline: second
        ? `${categoryLabel(first[0])} ${first[1]}건 · ${categoryLabel(second[0])} ${second[1]}건`
        : `${categoryLabel(first[0])} ${first[1]}건`,
      reason:
        first[1] >= 5 && firstProducts >= 2
          ? `${categoryLabel(first[0])} · ${named(firstProductIds)}에서 되풀이`
          : `${categoryLabel(first[0])} · ${named(firstProductIds)}`,
      routes,
    };
  }, [mine, products]);

  const productName = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;
  /** 요청 중인 피드백. 버튼을 잠가 중복 클릭을 막는다 */
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<Record<string, string>>({});

  /**
   * 판매자 처리 — 확인 · 답변 · 반영. 백엔드 행은 서버(POST /responses)가 정본이고 201 응답으로 그 행을 바로 갱신한다.
   * 로컬 시드 행(서버에 없는 시연 데이터)만 예전처럼 브라우저 저장본을 고친다.
   */
  const respond = async (f: Feedback, action: FeedbackResponseAction) => {
    const body = (draft[f.feedback_id] ?? '').trim();
    if (action === 'REPLIED' && !body) return;
    if (f.source !== 'backend') {
      if (action === 'ACKNOWLEDGED') updateFeedback(f.feedback_id, { status: 'read' });
      else if (action === 'IMPLEMENTED') updateFeedback(f.feedback_id, { status: 'reflected', reply: body || null });
      else updateFeedback(f.feedback_id, { status: 'read', reply: body });
      if (action !== 'ACKNOWLEDGED') setDraft({ ...draft, [f.feedback_id]: '' });
      return;
    }
    setBusy((b) => ({ ...b, [f.feedback_id]: true }));
    setActionError((e) => ({ ...e, [f.feedback_id]: '' }));
    const result = await respondToFeedback(f.feedback_id, action, action === 'REPLIED' ? body : undefined);
    setBusy((b) => ({ ...b, [f.feedback_id]: false }));
    if (!result) {
      setActionError((e) => ({ ...e, [f.feedback_id]: '처리하지 못했습니다. 다시 눌러 주세요' }));
      return;
    }
    setRemote((rows) =>
      rows.map((r) =>
        r.feedback_id === result.feedbackId
          ? {
              ...r,
              handling_status: result.handlingStatus as FeedbackHandlingStatus,
              status: statusOfHandling(result.handlingStatus),
              replied_at: result.lastRespondedAt,
              latest_response: { action: result.response.action as FeedbackResponseAction, body: result.response.body, created_at: result.response.createdAt },
              reply: result.response.action === 'REPLIED' ? (result.response.body ?? null) : r.reply,
            }
          : r,
      ),
    );
    if (action === 'REPLIED') setDraft({ ...draft, [f.feedback_id]: '' });
  };
  const pickAxis = (next: AxisFilter) => {
    setAxis(next);
    setCategory(null);
  };

  const axisLabelOf = (id: AxisFilter) =>
    id === 'all' ? '전체' : id === 'pending' ? PENDING_LABEL : (FEEDBACK_INPUT_AXES.find((a) => a.id === id)?.label ?? id);

  /** 빈 목록에 적는 말. 못 읽었으면 그렇다고, 아니면 어디서 들어오는지 */
  const emptyText =
    remoteFailed && mine.length === 0
      ? '불러오지 못했습니다. 다시 열어 주세요'
      : '아직 들어온 의견이 없습니다';

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
          고객 의견 {total}건 · 아직 안 본 것 {fresh}건 · 반영한 것 {reflected}건
          {classifying ? ' · 종류 나누는 중' : ''}
        </p>
      </div>

      {/* AI 요약. 원문 목록보다 위 — 사장님은 결론부터 본다. 상품 필터를 그대로 따른다 */}
      <InsightCard brandId={brandId} productId={productId === 'all' ? null : productId} />

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

      <Panel title="상품별 의견" source={source} aside="눌러서 좁혀 보기">
        {byProduct.length === 0 ? (
          <p className="fbx-empty">{emptyText}</p>
        ) : (
          <ul className="fbx-products">
            {byProduct.map((p) => {
              const active = productId === p.id;
              return (
                <li key={p.id} className={`fbx-product${active ? ' is-active' : ''}`}>
                  <button
                    type="button"
                    className="fbx-product__head"
                    aria-pressed={active}
                    onClick={() => {
                      setProductId(active ? 'all' : p.id);
                      setCategory(null);
                    }}
                  >
                    <span className="fbx-product__name">{productName(p.id)}</span>
                    <span className="fbx-product__n">
                      <b>{p.list.length}</b>건
                      {p.fresh > 0 ? <span className="fbx-table__new">안 본 글 {p.fresh}</span> : null}
                    </span>
                  </button>
                  <div className="fbx-product__cats">
                    {p.cats.map(([id, n]) => {
                      const on = active && category === id;
                      const route = ROUTE[p.list.find((f) => labelsOf(f).some((l) => l.category_id === id))?.axis_id ?? ''];
                      return (
                        <button
                          key={id}
                          type="button"
                          className={`fbx-cat${on ? ' is-active' : ''}`}
                          title={route ? `담당 · ${route.label}` : undefined}
                          onClick={() => {
                            setProductId(p.id);
                            setAxis('all');
                            setCategory(on ? null : id);
                          }}
                        >
                          {categoryLabel(id)} <span className="fbx-cat__n">{n}</span>
                        </button>
                      );
                    })}
                    {p.pending > 0 ? (
                      <button
                        type="button"
                        className={`fbx-cat fbx-cat--pending${active && category === PENDING ? ' is-active' : ''}`}
                        onClick={() => {
                          setProductId(p.id);
                          setAxis('all');
                          setCategory(active && category === PENDING ? null : PENDING);
                        }}
                      >
                        {PENDING_LABEL} <span className="fbx-cat__n">{p.pending}</span>
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel title="불만 종류별 건수" source={source} fold aside={`의견 ${scoped.length}건`}>
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
                  {PENDING_LABEL} <span className="fbx-axis__n">{axisCounts.get(PENDING)}</span>
                </button>
              </li>
            ) : null}
          </ul>
        </div>
      </Panel>

      <Panel title={`${axisLabelOf(axis)} · 세부 불만`} source={source} fold aside="줄을 누르면 원문 보기">
        {categories.length === 0 ? (
          <p className="fbx-empty">{emptyText}</p>
        ) : (
          <div className="table-wrap">
            <table className="fbx-table">
              <thead>
                <tr>
                  <th>불만 종류</th>
                  <th>담당</th>
                  <th className="is-num" title="한 글에 불만이 둘이면 둘 다 셉니다">언급 수</th>
                  <th style={{ width: '22%' }} aria-label="비중" />
                  <th className="is-num">상품 수</th>
                  <th className="is-num">안 본 글</th>
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
                        <span className="fbx-table__name">{pending ? PENDING_LABEL : categoryLabel(c.id)}</span>
                        {!pending ? (
                          <span className="fbx-table__desc">
                            {c.id === 'other' ? '그 밖의 불만' : categoryDesc(c.id)}
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
                      <td className="is-num">{c.fresh > 0 ? <span className="fbx-table__new">{c.fresh}</span> : '0'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {rows.length > 0 ? (
        <Panel title="의견 원문" source={source} fold aside={`의견 ${rows.length}건`}>
          <div className="fbx-inbox__head">
            <h3>
              {productId !== 'all' ? `${productName(productId)} · ` : ''}
              {category ? (category === PENDING ? PENDING_LABEL : categoryLabel(category)) : axisLabelOf(axis)}
            </h3>
            <small>답변은 고객 화면에 그대로 보입니다</small>
            {category ? (
              <button type="button" className="fbx-inbox__reset" onClick={() => setCategory(null)}>
                모든 불만 종류 보기
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
                    {/*
                      산 사람의 말인지. 의견은 사지 않아도 보낼 수 있고, 두 말은 무게가 다르다 —
                      산 사람의 "향이 강하다" 와 안 산 사람의 "향이 강할 것 같다" 는 다른 이야기다.
                      옛 서버 응답·로컬 저장본은 이 값이 없어서(undefined) 아무것도 적지 않는다.
                    */}
                    {f.purchased === true ? (
                      <span className="fbx-card__buyer" title="이 상품을 결제한 고객">구매자</span>
                    ) : f.purchased === false ? (
                      <span className="fbx-card__buyer fbx-card__buyer--no" title="이 상품을 결제하지 않은 고객">미구매</span>
                    ) : null}
                    {labelsOf(f).map((l) => (
                      <span key={l.category_id} className="fbx-card__cat">{categoryLabel(l.category_id)}</span>
                    ))}
                    {f.profile ? (
                      <span title="피부 타입 · 피부 톤">
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
                      부적절할 수 있는 표현 · 눌러서 보기
                    </button>
                  ) : (
                    <p className="fbx-card__body">{f.body}</p>
                  )}

                  {/* 남긴 답변은 상태와 무관하게 보인다 — 확인만 하고 답변한 것도, 반영한 것도 */}
                  {f.reply ? (
                    <blockquote className="fbx-card__reply">
                      <span>{f.reply}</span>
                      <small>{brandName ?? ''} · {(f.latest_response?.created_at ?? f.replied_at ?? '').slice(0, 10)}</small>
                    </blockquote>
                  ) : f.status === 'reflected' ? (
                    <blockquote className="fbx-card__reply">
                      <span>답글 없이 반영했습니다</span>
                      <small>{brandName ?? ''} · {f.replied_at?.slice(0, 10)}</small>
                    </blockquote>
                  ) : null}
                  {/* "확인했어요" 버튼은 뺐다 (2026-09-22 유림님). 할 일은 답변 남기기와 반영했어요 둘이면 된다 */}
                  {f.status !== 'reflected' ? (
                    <div className="fbx-card__actions">
                      <div className={`fbx-reply${hits.length ? ' has-warning' : ''}`}>
                        <input
                          placeholder="고객에게 보일 답변 한 줄"
                          value={text}
                          aria-label="답변"
                          disabled={busy[f.feedback_id]}
                          onChange={(e) => setDraft({ ...draft, [f.feedback_id]: e.target.value })}
                        />
                        {hits.length ? (
                          <p className="fbx-reply__warn">
                            {hits.map((h) => (
                              <span key={h.term}>
                                <b>{h.term}</b> {h.level === 'forbidden' ? '쓸 수 없는 표현' : h.why}
                                {' · '}
                              </span>
                            ))}
                            화장품법 표시·광고 제한에 걸릴 수 있는 표현
                          </p>
                        ) : null}
                        {actionError[f.feedback_id] ? <p className="fbx-reply__warn">{actionError[f.feedback_id]}</p> : null}
                      </div>
                      <button
                        type="button"
                        className="fbx-btn"
                        disabled={busy[f.feedback_id] || !text.trim() || hits.some((h) => h.level === 'forbidden')}
                        onClick={() => void respond(f, 'REPLIED')}
                      >
                        답변 남기기
                      </button>
                      <button
                        type="button"
                        className="fbx-btn fbx-btn--primary"
                        disabled={busy[f.feedback_id] || hits.some((h) => h.level === 'forbidden')}
                        onClick={() => void respond(f, 'IMPLEMENTED')}
                      >
                        반영했어요
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
