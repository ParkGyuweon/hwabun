import { useEffect, useState } from 'react';
import { fetchBackendOrders, submitReview } from '../../lib/shopApi';
import type { BackendOrderItem } from '../../lib/shopApi';
import { useAuth } from '../../hooks/useAuth';

const RATINGS = [1, 2, 3, 4, 5];
/** 이보다 짧으면 "쓰다 만 것" 으로 본다 (WriteReview 와 같은 기준) */
const MIN_BODY = 5;

type Eligibility =
  | { kind: 'loading' }
  /** 로그인 안 함 */
  | { kind: 'guest' }
  /** 로그인은 했지만 이 상품을 산 적이 없다 */
  | { kind: 'not_buyer' }
  /** 산 품목은 있는데 전부 리뷰를 이미 썼다 */
  | { kind: 'done' }
  | { kind: 'ok'; item: BackendOrderItem };

/**
 * 상품 상세의 리뷰 쓰기 칸 (2026-09-22 유림님).
 *
 * **누구에게나 보인다.** 다만 이 상품을 결제한 회원에게만 살아 있고, 그 밖에는 회색으로 잠긴 채
 * "구매자만 리뷰를 작성할 수 있습니다" 를 적는다. 칸을 아예 숨기면 "리뷰는 어디서 쓰지" 가 되고, 살려 두고
 * 서버 403 에 맡기면 다 쓴 글이 거절된다. 잠긴 칸이 그 둘 사이의 답이다.
 *
 * 구매 여부는 내 주문 목록(GET /api/orders)에서 이 상품 품목을 찾아 판단한다. 리뷰는 품목(orderItemId) 단위라
 * 아직 리뷰를 안 쓴 품목 하나를 고른다. 최종 판정은 여전히 서버가 한다 (FeedbackController.purchasedOrderItem).
 */
export default function ProductReviewBox({ productId, onWritten }: { productId: string; onWritten: () => void }) {
  const member = useAuth('MEMBER');
  const [elig, setElig] = useState<Eligibility>({ kind: 'loading' });
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [written, setWritten] = useState(false);

  useEffect(() => {
    setWritten(false);
    setError(null);
    if (!member) {
      setElig({ kind: 'guest' });
      return;
    }
    let alive = true;
    setElig({ kind: 'loading' });
    void fetchBackendOrders().then((r) => {
      if (!alive) return;
      if (!r.ok) {
        setElig({ kind: 'not_buyer' });
        return;
      }
      const items = r.orders
        .filter((o) => o.paidAt !== null || o.status === 'PAID')
        .flatMap((o) => o.items)
        .filter((it) => it.productId === productId);
      if (items.length === 0) {
        setElig({ kind: 'not_buyer' });
        return;
      }
      const open = items.find((it) => !it.reviewed);
      setElig(open ? { kind: 'ok', item: open } : { kind: 'done' });
    });
    return () => {
      alive = false;
    };
  }, [member?.id, productId]);

  const enabled = elig.kind === 'ok' && !written;

  const send = async () => {
    if (elig.kind !== 'ok' || body.trim().length < MIN_BODY || sending) return;
    setSending(true);
    setError(null);
    const r = await submitReview({
      orderItemId: elig.item.orderItemId,
      rating,
      isRecommended: rating >= 4,
      title: null,
      body: body.trim(),
    });
    setSending(false);
    if (!r.ok) {
      setError(
        r.status === 403
          ? '구매한 상품에만 리뷰를 쓸 수 있습니다.'
          : r.status === 409
            ? '이미 이 상품에 리뷰를 쓰셨습니다.'
            : `보내지 못했습니다. ${r.reason}`,
      );
      return;
    }
    setBody('');
    setWritten(true);
    onWritten();
  };

  const note =
    written || elig.kind === 'done'
      ? '리뷰를 남겨 주셔서 고맙습니다.'
      : elig.kind === 'guest'
        ? '구매자만 리뷰를 작성할 수 있습니다. 로그인 후 구매한 상품에 남겨 주세요.'
        : elig.kind === 'not_buyer'
          ? '구매자만 리뷰를 작성할 수 있습니다.'
          : elig.kind === 'loading'
            ? '구매 내역을 확인하는 중입니다.'
            : null;

  return (
    <div className={`reviewbox writereview${enabled ? '' : ' is-locked'}`} aria-disabled={!enabled}>
      <p className="reviewbox__title">리뷰 쓰기</p>
      <div className="writereview__stars" role="group" aria-label="별점">
        {RATINGS.map((n) => (
          <button
            key={n}
            type="button"
            className={n <= rating ? 'is-on' : ''}
            aria-label={`${n}점`}
            aria-pressed={n === rating}
            disabled={!enabled}
            onClick={() => setRating(n)}
          >
            ★
          </button>
        ))}
        <span className="writereview__rating">{rating}점</span>
      </div>

      <textarea
        className="writereview__body"
        value={body}
        maxLength={1000}
        rows={3}
        disabled={!enabled}
        placeholder={enabled ? '써 보니 어떠셨나요? 같은 고민을 가진 분들에게 도움이 됩니다.' : '구매한 분만 쓸 수 있는 칸입니다.'}
        onChange={(e) => setBody(e.target.value)}
      />

      {error ? <p className="writereview__error">{error}</p> : null}

      <div className="reviewbox__foot">
        {note ? <p className="reviewbox__note">{note}</p> : <span />}
        <button
          type="button"
          className="writereview__send"
          disabled={!enabled || body.trim().length < MIN_BODY || sending}
          onClick={() => void send()}
        >
          {sending ? '보내는 중' : '리뷰 작성'}
        </button>
      </div>
    </div>
  );
}
