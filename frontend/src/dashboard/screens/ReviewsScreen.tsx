import { useEffect, useMemo, useState } from 'react';
import { BarList, Kpi, OriginBadge, Panel } from '../components';
import { SKIN_TYPE_KO, fmt, reviewStats, reviewsBySkinType } from '../lib/metrics';
import { fetchSellerReviews } from '../lib/sellerReviewsApi';
import type { SellerReview, SellerReviewsRead } from '../lib/sellerReviewsApi';
import { useBrandProducts } from '../lib/useBrandProducts';

/** 원문 목록을 한 번에 펼치는 건수. 그 뒤는 "더 보기" */
const RECENT_LIMIT = 30;

/** 별 다섯 개. 반올림한 점수만큼 채운다 */
function stars(rating: number): string {
  const n = Math.max(0, Math.min(5, Math.round(rating)));
  return '★'.repeat(n) + '☆'.repeat(5 - n);
}

/**
 * 고객이 남긴 공개 리뷰. 전부 로그인한 브랜드 상품의 실제 리뷰(판매자 리뷰 API) 실측이다.
 *
 * 사장님이 이 화면에서 답을 얻어야 하는 질문은 세 가지다 — **누가 뭐라고 썼나(원문), 어느 상품 얘기인가, 몇 점인가.**
 * 그래서 원문 목록을 KPI 바로 아래에 두고, 상품별 요약 표에서 상품을 누르면 그 상품 리뷰만 본다.
 * 2026-09-18 전에는 집계만 있고 원문·상품별 보기가 없어서 "리뷰가 1건" 이라는 숫자만 보였다.
 *
 * 내 상품이 없거나 리뷰가 없거나 API 를 못 읽으면 그렇다고 적는다 — 남의 브랜드 리뷰나 표본으로 채우지 않는다.
 */
export default function ReviewsScreen({
  brandId,
  brandName,
  productId,
  onProductChange,
}: {
  brandId: string | null;
  brandName: string | null;
  productId: string | null;
  onProductChange: (id: string | null) => void;
}) {
  const { products: mine, failed } = useBrandProducts(brandId, brandName);
  const products = useMemo(() => mine ?? [], [mine]);
  // 로그인한 브랜드의 리뷰를 이 화면이 열릴 때 받는다. 받기 전이면 null. 브랜드가 바뀌면 다시 받는다
  const [loaded, setLoaded] = useState<{ brand: string; read: SellerReviewsRead } | null>(null);
  const read = loaded !== null && loaded.brand === brandId ? loaded.read : null;
  const reviews = read?.kind === 'ready' ? read.rows : null;
  useEffect(() => {
    let alive = true;
    if (brandId === null) return;
    void fetchSellerReviews(brandId).then((r) => {
      if (alive) setLoaded({ brand: brandId, read: r });
    });
    return () => {
      alive = false;
    };
  }, [brandId]);
  const [expanded, setExpanded] = useState(false);

  const rows = useMemo(() => reviews ?? [], [reviews]);
  const nameOf = useMemo(() => new Map(products.map((p) => [p.product_id, p.product_name])), [products]);
  const countOf = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.product_id, (m.get(r.product_id) ?? 0) + 1);
    return m;
  }, [rows]);
  const stats = useMemo(() => reviewStats(rows, productId, products), [rows, productId, products]);
  // 리뷰가 한 건이라도 있는 타입은 전부 보여준다. 건수 칸이 옆에 있으니 몇 건짜리 평점인지 사장님이 직접 본다. 20건 미만은 흐리게
  const bySkin = useMemo(() => reviewsBySkinType(rows, productId, products).filter((r) => r.n >= 1), [rows, productId, products]);
  // 백엔드가 피부 타입을 하나도 모르면 표를 그릴 근거가 없다. 빈 표 대신 왜 비었는지 적는다
  const hasSkinType = rows.some((r) => r.skin_type !== null);

  /** 이 범위의 원문. 최신순. 고른 상품이 있으면 그 상품만, 없으면 내 상품 전체 */
  const scoped = useMemo(() => {
    const list = rows.filter((r) => (productId ? r.product_id === productId : nameOf.has(r.product_id)));
    return [...list].sort((a, b) => (b.submission_date ?? '').localeCompare(a.submission_date ?? ''));
  }, [rows, productId, nameOf]);

  /** 상품별 요약. 리뷰가 있는 상품만, 많은 순 */
  const byProduct = useMemo(
    () =>
      products
        .map((p) => ({ product: p, stats: reviewStats(rows, p.product_id, products) }))
        .filter((x) => x.stats.sampleSize > 0)
        .sort((a, b) => b.stats.sampleSize - a.stats.sampleSize),
    [rows, products],
  );

  // 결론은 리뷰 20건 이상인 타입끼리만 비교한다. 5건짜리 평점 차이는 우연이다
  const solid = bySkin.filter((r) => r.n >= 20);
  const hi = solid.length > 1 ? solid.reduce((a, b) => (a.avgRating >= b.avgRating ? a : b)) : null;
  const lo = solid.length > 1 ? solid.reduce((a, b) => (a.avgRating <= b.avgRating ? a : b)) : null;
  const split = hi && lo ? hi.avgRating - lo.avgRating : 0;
  const scopeLabel = productId ? (nameOf.get(productId) ?? productId) : '전체 상품';
  const total = rows.filter((r) => nameOf.has(r.product_id)).length;

  /**
   * 내 상품이 없으면 셀 리뷰가 없다. 번들 표본의 다른 브랜드로 대신 채우지 않는다 —
   * 남의 리뷰 평점을 내 것으로 읽게 만드는 것이 이 화면의 원래 문제였다.
   */
  if (brandId === null || mine === null || mine.length === 0 || reviews === null) {
    const why =
      brandId === null
        ? '판매자로 로그인하면 내 상품에 달린 리뷰가 여기 보입니다.'
        : failed
          ? '상품 목록을 읽지 못했습니다. 잠시 뒤 다시 열어 주세요.'
          : mine === null
            ? '상품 목록을 받는 중입니다.'
            : read === null
              ? '리뷰를 받는 중입니다.'
              : read.kind === 'unavailable'
                ? '리뷰를 읽지 못했습니다. 잠시 뒤 다시 열어 주세요.'
                : '등록한 상품이 없습니다. 상품을 등록하고 고객이 리뷰를 남기면 여기 모입니다.';
    return (
      <div className="stack">
        <Panel title="공개 리뷰" source="real">
          <p className="note">{why}</p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="scope">
        <label className="scope__field">
          <span className="scope__label">상품</span>
          <select
            value={productId ?? 'all'}
            onChange={(e) => onProductChange(e.target.value === 'all' ? null : e.target.value)}
            aria-label="상품 선택"
          >
            <option value="all">전체 상품 · 리뷰 {fmt.int(total)}건</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.product_name} · {countOf.get(p.product_id) ?? 0}건
              </option>
            ))}
          </select>
        </label>
        <p className="scope__meta">
          리뷰 {fmt.int(stats.sampleSize)}건 · 그중 글을 쓴 리뷰 {fmt.int(stats.withText)}건
        </p>
        <p className="scope__note">
          {stats.sampleSize === 0 ? '이 상품에는 리뷰가 아직 없습니다.' : '내 상품에 달린 리뷰만 셉니다. 건수가 적으면 비율은 참고만 하세요.'}
        </p>
      </div>

      <div className="grid grid--kpi">
        <Kpi
          label="평균 평점"
          value={stats.sampleSize === 0 ? '-' : stats.avgRating.toFixed(2)}
          sub={stats.sampleSize === 0 ? '아직 리뷰가 없어 낼 수 없습니다' : `리뷰 ${fmt.int(stats.sampleSize)}건의 평균 (5점 만점)`}
          source="real"
        />
        <Kpi
          label="추천 비율"
          value={stats.sampleSize === 0 ? '-' : fmt.pct(stats.recommendRate)}
          sub={stats.sampleSize === 0 ? '아직 리뷰가 없어 낼 수 없습니다' : '"추천해요" 에 표시한 리뷰의 비율'}
          source="real"
        />
        <Kpi
          label="자극 언급"
          value={stats.withText === 0 ? '-' : fmt.pct(stats.irritationRate)}
          sub={stats.withText === 0 ? '글을 쓴 리뷰가 없어 낼 수 없습니다' : '따가움·화끈거림·가려움 같은 말이 든 리뷰의 비율'}
          source="real"
        />
        <Kpi
          label="트러블 언급"
          value={stats.withText === 0 ? '-' : fmt.pct(stats.troubleRate)}
          sub={stats.withText === 0 ? '글을 쓴 리뷰가 없어 낼 수 없습니다' : '뾰루지·붉어짐 같은 말이 든 리뷰의 비율'}
          source="real"
        />
      </div>

      <Panel
        title={`리뷰 원문 · ${scopeLabel}`}
        source={scoped.length ? 'real' : 'none'}
        aside={scoped.length === 0 ? '0건' : `최신순 · ${fmt.int(scoped.length)}건`}
      >
        {scoped.length === 0 ? (
          <p className="note">
            {productId
              ? '이 상품에 달린 리뷰가 아직 없습니다. 고객이 리뷰를 남기면 여기 보입니다.'
              : '내 상품에 달린 리뷰가 아직 없습니다. 고객이 리뷰를 남기면 여기 보입니다.'}
          </p>
        ) : (
          <>
            <ul className="reviews">
              {(expanded ? scoped : scoped.slice(0, RECENT_LIMIT)).map((r: SellerReview) => {
                const name = nameOf.get(r.product_id) ?? r.product_name ?? r.product_id;
                return (
                  <li key={r.review_id} className="reviews__item">
                    <div className="reviews__head">
                      <span className="reviews__stars" aria-label={`${r.rating}점`}>
                        {stars(r.rating)}
                      </span>
                      <b className="reviews__rating">{r.rating.toFixed(1)}</b>
                      {productId ? (
                        <span className="reviews__product">{name}</span>
                      ) : (
                        <button
                          type="button"
                          className="reviews__product reviews__product--link"
                          onClick={() => onProductChange(r.product_id)}
                          title="이 상품 리뷰만 보기"
                        >
                          {name}
                        </button>
                      )}
                      {r.is_recommended === true ? <span className="reviews__tag">추천</span> : null}
                      {r.is_recommended === false ? <span className="reviews__tag reviews__tag--no">비추천</span> : null}
                      {r.skin_type ? <span className="reviews__tag">{SKIN_TYPE_KO[r.skin_type] ?? r.skin_type}</span> : null}
                      {r.is_purchaser ? <span className="reviews__tag" title="이 상품을 결제한 고객이 쓴 리뷰입니다">구매 고객</span> : null}
                      <span className="reviews__when">{r.submission_date ?? ''}</span>
                    </div>
                    {r.review_title ? <p className="reviews__title">{r.review_title}</p> : null}
                    <p className="reviews__body">{r.review_text?.trim() ? r.review_text : '(본문 없이 별점만 남겼습니다)'}</p>
                  </li>
                );
              })}
            </ul>
            {scoped.length > RECENT_LIMIT && !expanded ? (
              <button type="button" className="more-btn" onClick={() => setExpanded(true)}>
                나머지 {fmt.int(scoped.length - RECENT_LIMIT)}건 더 보기
              </button>
            ) : null}
          </>
        )}
      </Panel>

      <Panel title="상품별 리뷰 요약" source="real" aside="리뷰 많은 순 · 상품을 누르면 그 상품 리뷰만 봅니다">
        {byProduct.length === 0 ? (
          <p className="note">아직 리뷰가 달린 상품이 없습니다. 고객이 리뷰를 남기면 상품별로 여기 정리됩니다.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th className="is-name">상품</th>
                  <th>리뷰 수</th>
                  <th>평균 평점</th>
                  <th>추천 비율</th>
                  <th>자극 언급</th>
                  <th>트러블 언급</th>
                </tr>
              </thead>
              <tbody>
                {byProduct.map(({ product: p, stats: st }) => (
                  <tr key={p.product_id} className={p.product_id === productId ? 'is-hit' : ''}>
                    <td className="is-name" title={p.product_name}>
                      <button
                        type="button"
                        className="table__link"
                        onClick={() => onProductChange(p.product_id === productId ? null : p.product_id)}
                      >
                        {p.product_name}
                      </button>
                    </td>
                    <td>{fmt.int(st.sampleSize)}건</td>
                    <td>
                      <b>{st.avgRating.toFixed(2)}</b>
                    </td>
                    <td>{fmt.pct(st.recommendRate, 0)}</td>
                    <td>{st.withText === 0 ? '글 없음' : fmt.pct(st.irritationRate, 0)}</td>
                    <td>{st.withText === 0 ? '글 없음' : fmt.pct(st.troubleRate, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">
          자극·트러블 언급은 리뷰 글에 그런 낱말이 있는지만 봅니다. 지금은 영어로 쓴 리뷰에서만 찾고, 한국어 리뷰는 아직 세지
          않습니다. "글 없음" 은 별점만 남기고 글은 안 쓴 리뷰뿐이라는 뜻입니다.
        </p>
      </Panel>

      {hi && lo && split >= 0.5 ? (
        <section className="verdict verdict--mine">
          <p className="verdict__eyebrow">
            피부 타입별로 평가가 갈립니다 <OriginBadge kind="mine" />
          </p>
          <h2 className="verdict__headline">
            {SKIN_TYPE_KO[hi.type]} {hi.avgRating.toFixed(1)}점 · {SKIN_TYPE_KO[lo.type]} {lo.avgRating.toFixed(1)}점
          </h2>
          <ul className="verdict__reasons">
            <li>
              {SKIN_TYPE_KO[hi.type]} 고객 리뷰 {hi.n}건, {SKIN_TYPE_KO[lo.type]} 고객 리뷰 {lo.n}건. 평점 차이 {split.toFixed(1)}점
            </li>
            {lo.irritationRate > hi.irritationRate + 0.05 ? (
              <li>
                {SKIN_TYPE_KO[lo.type]} 고객 리뷰 중 자극을 말한 비율 {fmt.pct(lo.irritationRate, 0)} · {SKIN_TYPE_KO[hi.type]} 고객은{' '}
                {fmt.pct(hi.irritationRate, 0)}
              </li>
            ) : null}
          </ul>
          <p className="verdict__action">
            <span className="verdict__unit">홍보 문구</span>
            홍보 문구와 리뷰 정렬을 {SKIN_TYPE_KO[hi.type]} 고객 기준으로 두고, {SKIN_TYPE_KO[lo.type]} 고객에게는 사용 주의 안내를
            붙이세요
          </p>
          <p className="verdict__sample">리뷰 {fmt.int(stats.sampleSize)}건을 보고 낸 결론입니다</p>
        </section>
      ) : null}

      <div className="grid grid--2">
        <Panel title={`평점 분포 · ${scopeLabel}`} source="real">
          {stats.sampleSize === 0 ? (
            <p className="note">아직 리뷰가 없어 별점 분포를 그릴 수 없습니다.</p>
          ) : (
            <BarList items={stats.ratingDist.map((count, i) => ({ label: `${i + 1}점`, value: count })).reverse()} />
          )}
        </Panel>

        <Panel title="리뷰에 자주 나오는 이야기" source="real" aside="리뷰 글에 그 낱말이 있는지만 봅니다">
          {stats.withText === 0 || stats.factors.every((f) => f.count === 0) ? (
            <p className="note">
              리뷰 글에서 보습감·향·발림성 같은 표현을 찾지 못했습니다. 지금은 영어로 쓴 리뷰에서만 찾고, 한국어 리뷰는 아직 세지
              않습니다.
            </p>
          ) : (
            <BarList
              items={stats.factors.map((f) => ({
                label: f.label,
                value: f.count,
                hint: fmt.pct(f.share, 0),
              }))}
            />
          )}
        </Panel>
      </div>

      <Panel
        title="피부 타입별 평점 · 자극 언급"
        source={hasSkinType ? 'real' : 'none'}
        aside={hasSkinType ? '리뷰 20건 미만인 타입은 흐리게 · 참고만' : '기록 없음'}
      >
        {!hasSkinType ? (
          <p className="note">
            리뷰를 남긴 고객 중 피부 타입을 알려 준 사람이 아직 없어 표를 만들 수 없습니다. 고객이 회원 정보에 피부 타입을
            넣고 리뷰를 남기면 채워집니다.
          </p>
        ) : bySkin.length === 0 ? (
          <p className="note">이 상품 리뷰에는 피부 타입이 기록된 것이 아직 없습니다.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>고객 피부 타입</th>
                  <th>평균 평점</th>
                  <th>자극 언급</th>
                  <th>리뷰 수</th>
                </tr>
              </thead>
              <tbody>
                {bySkin.map((r) => (
                  <tr key={r.type} className={r.n < 20 ? 'is-thin' : ''}>
                    <td>{SKIN_TYPE_KO[r.type]}</td>
                    <td>
                      <b>{r.avgRating.toFixed(2)}</b>
                    </td>
                    <td>{fmt.pct(r.irritationRate, 0)}</td>
                    <td>{r.n}건</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {hasSkinType && bySkin.length > 0 ? (
          <p className="note">타입별로 평가가 갈린다는 결론은 두 타입 모두 리뷰 20건 이상일 때만 위에 띄웁니다.</p>
        ) : null}
      </Panel>
    </div>
  );
}
