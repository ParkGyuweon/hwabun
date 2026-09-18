import { useState } from 'react';
import { submitReview } from '../../lib/shopApi';
import type { BackendOrderItem } from '../../lib/shopApi';

/** 별점은 1~5. 서버가 그 범위만 받는다 (`review.rating` CHECK) */
const RATINGS = [1, 2, 3, 4, 5];

/** 이보다 짧으면 "쓰다 만 것" 으로 본다. 한 줄이라도 있어야 사장님이 읽을 것이 생긴다 */
const MIN_BODY = 5;

/**
 * 산 상품에 리뷰 쓰기.
 *
 * 리뷰는 **결제한 사람만** 쓴다 — 서버가 `orderItemId` 가 이 회원의 결제 완료 주문인지 직접 확인하고
 * 아니면 403 이다 (`FeedbackController.purchasedOrderItem`). 화면이 막는 것이 아니라 서버가 막는다.
 *
 * 그동안 산 사람도 리뷰를 못 썼던 이유는 권한이 아니라 **주문 목록이 `orderItemId` 를 안 줬기** 때문이다.
 * 무엇을 리뷰할 수 있는지 화면이 알 방법이 없었다. 이제 주문마다 품목이 오고, 그 품목에 이 칸이 붙는다.
 */
export default function WriteReview({ item, onWritten }: { item: BackendOrderItem; onWritten: () => void }) {
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (item.reviewed) {
    return <span className="writereview__done">리뷰 작성 완료</span>;
  }

  if (!open) {
    return (
      <button type="button" className="writereview__open" onClick={() => setOpen(true)}>
        리뷰 쓰기
      </button>
    );
  }

  const send = async () => {
    if (body.trim().length < MIN_BODY || sending) return;
    setSending(true);
    setError(null);
    const r = await submitReview({
      orderItemId: item.orderItemId,
      rating,
      isRecommended: rating >= 4,
      title: null,
      body: body.trim(),
    });
    setSending(false);
    if (!r.ok) {
      /*
       * 403·409 는 화면 잘못이 아니라 서버가 아는 사실이다. 그대로 적는다 —
       * "다시 시도" 를 권하면 영영 안 되는 것을 계속 누르게 된다.
       */
      setError(
        r.status === 403
          ? '구매한 상품에만 리뷰를 쓸 수 있습니다.'
          : r.status === 409
            ? '이미 이 상품에 리뷰를 쓰셨습니다.'
            : `보내지 못했습니다. ${r.reason}`,
      );
      return;
    }
    setOpen(false);
    setBody('');
    onWritten();
  };

  return (
    <div className="writereview">
      <div className="writereview__stars" role="group" aria-label="별점">
        {RATINGS.map((n) => (
          <button
            key={n}
            type="button"
            className={n <= rating ? 'is-on' : ''}
            aria-label={`${n}점`}
            aria-pressed={n === rating}
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
        placeholder="써 보니 어떠셨나요? 같은 고민을 가진 분들에게 도움이 됩니다."
        onChange={(e) => setBody(e.target.value)}
      />

      {error ? <p className="writereview__error">{error}</p> : null}

      <div className="writereview__actions">
        <button type="button" className="writereview__cancel" onClick={() => setOpen(false)}>
          취소
        </button>
        <button
          type="button"
          className="writereview__send"
          disabled={body.trim().length < MIN_BODY || sending}
          onClick={() => void send()}
        >
          {sending ? '보내는 중' : '리뷰 남기기'}
        </button>
      </div>
    </div>
  );
}
