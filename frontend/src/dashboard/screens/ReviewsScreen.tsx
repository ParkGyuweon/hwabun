import { useEffect, useMemo, useState } from 'react';
import { BarList, Kpi, Panel } from '../components';
import { fmt } from '../lib/metrics';
import { useBrandProducts } from '../lib/useBrandProducts';
import { fetchBackendReviews } from '../../lib/shopApi';
import type { Review } from '../../types/review';

/**
 * 자극·트러블 언급. 실제 리뷰는 한국어라 한글 표현을 앞세우고, 영문 시드 표현도 남겨 둔다.
 * "본문 키워드 매칭" 근사치다 — 문장 뜻을 읽는 것이 아니라 낱말이 있나만 본다. 화면에 그렇게 적는다.
 */
const IRRITATION_PATTERN = /자극|따가|따끔|화끈|가려|쓰라|민감|irritat|sting|burn|tingl|itch|sensitiv/i;
const TROUBLE_PATTERN = /트러블|뾰루지|여드름|좁쌀|붉|홍조|올라오|뒤집|break\s?out|acne|pimple|rash|redness|bumps/i;

/** 최근 원문 목록에 보여줄 개수. 더 보려면 상품을 좁힌다 */
const RECENT_LIMIT = 30;

/**
 * 공개 리뷰 — **로그인한 브랜드의 실제 리뷰**만 본다 (2026-09-18).
 *
 * 전에는 번들의 세포라 리뷰 2,000건을 `BEHAVIOR_BRAND`(Drunk Elephant)로 걸러 보여줬다. 어느 브랜드로 들어와도
 * 같은 표가 나왔고, 사장님은 남의 상품이 왜 내 대시보드에 있는지 알 수 없었다. 시드는 걷어냈다.
 *
 * 판매자용 리뷰 API(`GET /api/seller/reviews`)는 아직 없다. 그래서 **내 상품마다 공개 리뷰 API**
 * (`GET /api/products/{id}/reviews`)를 불러 모은다. 상품 수만큼 부르지만 브랜드 하나가 가진 상품은 열 개 안팎이다.
 * 판매자 API 가 생기면 그 한 번으로 바꾼다 — 화면 모양은 그대로다.
 *
 * 리뷰어 피부 타입은 백엔드가 주지 않는다. 그래서 피부 타입별 표는 없다. 서버가 주면 그때 붙인다.
 * 값이 없으면 "리뷰가 아직 없습니다" 다. 모의로 채우지 않는다.
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
  const { products, failed: productsFailed } = useBrandProducts(brandId, brandName);
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [expanded, setExpanded] = useState(false);

  // 상품 목록이 오면 상품마다 리뷰를 받는다. 상품 목록이 바뀌면(등록 직후) 다시 받는다
  const productKey = useMemo(() => (products ?? []).map((p) => p.product_id).join(','), [products]);
  useEffect(() => {
    if (products === null) return;
    let alive = true;
    setReviews(null);
    void Promise.all(products.map((p) => fetchBackendReviews(p.product_id))).then((lists) => {
      if (!alive) return;
      const all = lists.flat().sort((a, b) => b.submission_time.localeCompare(a.submission_time));
      setReviews(all);
    });
    return () => {
      alive = false;
    };
    // 상품 id 목록이 같으면 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productKey]);

  const nameOf = useMemo(() => new Map((products ?? []).map((p) => [p.product_id, p.product_name])), [products]);

  // 화면에 없는 상품이 선택돼 있으면(브랜드 전환) 전체로 돌린다
  useEffect(() => {
    if (productId && products && !products.some((p) => p.product_id === productId)) onProductChange(null);
  }, [productId, products, onProductChange]);

  const scoped = useMemo(
    () => (reviews ?? []).filter((r) => productId === null || r.product_id === productId),
    [reviews, productId],
  );

  const stats = useMemo(() => {
    const n = scoped.length;
    const texts = scoped.filter((r) => (r.review_text ?? '').trim().length > 0);
    const recommended = scoped.filter((r) => r.is_recommended !== null);
    const dist = [0, 0, 0, 0, 0];
    for (const r of scoped) if (r.rating >= 1 && r.rating <= 5) dist[Math.round(r.rating) - 1] += 1;
    return {
      n,
      withText: texts.length,
      avgRating: n === 0 ? 0 : scoped.reduce((s, r) => s + r.rating, 0) / n,
      recommendRate: recommended.length === 0 ? null : recommended.filter((r) => r.is_recommended).length / recommended.length,
      irritationRate: texts.length === 0 ? null : texts.filter((r) => IRRITATION_PATTERN.test(r.review_text as string)).length / texts.length,
      troubleRate: texts.length === 0 ? null : texts.filter((r) => TROUBLE_PATTERN.test(r.review_text as string)).length / texts.length,
      ratingDist: dist,
    };
  }, [scoped]);

  /** 상품별 표. 브랜드 전체(reviews)로 만든다 — 상품 선택은 위 칸들의 필터일 뿐이다 */
  const byProduct = useMemo(() => {
    const acc = new Map<string, Review[]>();
    for (const r of reviews ?? []) acc.set(r.product_id, [...(acc.get(r.product_id) ?? []), r]);
    return [...acc.entries()]
      .map(([id, list]) => {
        const texts = list.filter((r) => (r.review_text ?? '').trim().length > 0);
        const irritation = texts.length === 0 ? 0 : texts.filter((r) => IRRITATION_PATTERN.test(r.review_text as string)).length / texts.length;
        const trouble = texts.length === 0 ? 0 : texts.filter((r) => TROUBLE_PATTERN.test(r.review_text as string)).length / texts.length;
        return {
          id,
          name: nameOf.get(id) ?? id,
          n: list.length,
          avg: list.reduce((s, r) => s + r.rating, 0) / list.length,
          irritation,
          trouble,
          texts: texts.length,
        };
      })
      .sort((a, b) => b.irritation + b.trouble - (a.irritation + a.trouble) || b.n - a.n);
  }, [reviews, nameOf]);

  const pct = (v: number | null) => (v === null ? '-' : fmt.pct(v, 0));
  const scopeLabel = productId ? (nameOf.get(productId) ?? productId) : '전체 상품';

  if (!brandId) {
    return <Panel title="공개 리뷰" source="real" aside="-"><p className="note">브랜드를 먼저 고르세요.</p></Panel>;
  }
  if (productsFailed) {
    return (
      <Panel title="공개 리뷰" source="real" aside="-">
        <p className="note">상품 목록을 읽지 못해 리뷰를 모을 수 없습니다. 잠시 뒤 새로고침해 주세요.</p>
      </Panel>
    );
  }
  if (products === null || reviews === null) {
    return <Panel title="공개 리뷰" source="real" aside="불러오는 중"><p className="note">내 상품의 리뷰를 모으는 중입니다.</p></Panel>;
  }

  return (
    <div className="stack">
      <div className="scope">
        <label className="scope__field">
          <span className="scope__label">분석 범위</span>
          <select
            value={productId ?? 'all'}
            onChange={(e) => onProductChange(e.target.value === 'all' ? null : e.target.value)}
            aria-label="상품 선택"
          >
            <option value="all">전체 상품</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.product_name}
              </option>
            ))}
          </select>
        </label>
        <p className="scope__meta">
          리뷰 {fmt.int(stats.n)}건 · 본문 있는 리뷰 {fmt.int(stats.withText)}건 · 내 상품 {fmt.int(products.length)}개
        </p>
        <p className="scope__note">쇼핑몰에서 결제한 회원이 쓴 리뷰만 있습니다. 건수를 함께 볼 것.</p>
      </div>

      {reviews.length === 0 ? (
        <Panel title="공개 리뷰" source="none" aside="0건">
          <p className="note">
            리뷰가 아직 없습니다. 결제한 회원이 내 정보 → 주문 내역에서 리뷰를 남기면 여기에 그대로 쌓입니다.
          </p>
        </Panel>
      ) : null}

      <div className="grid grid--kpi">
        <Kpi label="평균 평점" value={stats.n === 0 ? '-' : stats.avgRating.toFixed(2)} sub={`${scopeLabel} · ${fmt.int(stats.n)}건`} source={stats.n ? 'real' : 'none'} />
        <Kpi label="추천 비율" value={pct(stats.recommendRate)} sub="별 4점 이상을 추천으로 봅니다" source={stats.n ? 'real' : 'none'} />
        <Kpi label="자극 언급" value={pct(stats.irritationRate)} sub="따가움·화끈거림·가려움 등 · 본문 기준" source={stats.withText ? 'real' : 'none'} />
        <Kpi label="트러블 언급" value={pct(stats.troubleRate)} sub="뾰루지·붉어짐 등 · 본문 기준" source={stats.withText ? 'real' : 'none'} />
      </div>

      <div className="grid grid--2">
        <Panel title={`평점 분포 · ${scopeLabel}`} source={stats.n ? 'real' : 'none'}>
          {stats.n === 0 ? (
            <p className="note">리뷰가 없습니다.</p>
          ) : (
            <BarList items={stats.ratingDist.map((count, i) => ({ label: `${i + 1}점`, value: count })).reverse()} />
          )}
        </Panel>

        <Panel title="상품별 리뷰" source={byProduct.length ? 'real' : 'none'} aside="자극·트러블 언급 많은 순">
          {byProduct.length === 0 ? (
            <p className="note">리뷰가 달린 상품이 없습니다.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>상품</th>
                    <th>평점</th>
                    <th>자극</th>
                    <th>트러블</th>
                    <th>리뷰</th>
                  </tr>
                </thead>
                <tbody>
                  {byProduct.map((row) => (
                    <tr key={row.id} className={row.texts < 5 ? 'is-thin' : ''}>
                      <td className="is-name" title={row.name}>
                        {row.name}
                      </td>
                      <td>
                        <b>{row.avg.toFixed(2)}</b>
                      </td>
                      <td>{fmt.pct(row.irritation, 0)}</td>
                      <td>{fmt.pct(row.trouble, 0)}</td>
                      <td>{row.n}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="note">본문 5건 미만인 상품은 흐리게. 언급 비율은 낱말 매칭 근사치입니다.</p>
        </Panel>
      </div>

      <Panel
        title={`최근 리뷰 원문 · ${scopeLabel}`}
        source={scoped.length ? 'real' : 'none'}
        aside={scoped.length === 0 ? '-' : `${fmt.int(scoped.length)}건`}
      >
        {scoped.length === 0 ? (
          <p className="note">이 범위에 리뷰가 없습니다.</p>
        ) : (
          <>
            <ul className="reviews">
              {(expanded ? scoped : scoped.slice(0, RECENT_LIMIT)).map((r) => (
                <li key={r.review_id} className="reviews__item">
                  <div className="reviews__head">
                    <span className="reviews__stars" aria-label={`${r.rating}점`}>
                      {'★'.repeat(Math.max(0, Math.min(5, Math.round(r.rating))))}
                    </span>
                    <span className="reviews__product">{nameOf.get(r.product_id) ?? r.product_id}</span>
                    <span className="reviews__when">{r.submission_time}</span>
                  </div>
                  {r.review_title ? <p className="reviews__title">{r.review_title}</p> : null}
                  <p className="reviews__body">{r.review_text || '(본문 없음)'}</p>
                </li>
              ))}
            </ul>
            {scoped.length > RECENT_LIMIT && !expanded ? (
              <button type="button" className="more-btn" onClick={() => setExpanded(true)}>
                나머지 {fmt.int(scoped.length - RECENT_LIMIT)}건 더 보기
              </button>
            ) : null}
          </>
        )}
      </Panel>

      <p className="note">
        리뷰어 피부 타입별 비교는 서버가 작성자 피부 속성을 주면 붙습니다. 지금은 원문과 별점만 있습니다.
      </p>
    </div>
  );
}
