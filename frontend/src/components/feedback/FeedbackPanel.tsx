import { useMemo, useState } from 'react';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForProduct, submitFeedback } from '../../lib/feedbackStore';
import { categoryLabel } from '../../types/feedback';
import type { PersonaProfile } from '../../types/persona';
import type { Product } from '../../types/product';

interface FeedbackPanelProps {
  product: Product;
  persona: PersonaProfile | null;
}

const MAX_TEXT = 300;
const MIN_TEXT = 5;

/**
 * 상품 페이지의 "이 제품에 의견 남기기".
 *
 * 리뷰가 아니다. 평점이 없고, 사장님에게 가는 개선 요청이다. 분류는 소비자가 고르지 않는다 —
 * 계약(feedback-classification.md §1)이 텍스트 자동 분류로 확정했다. 미리 정한 선택지 안에서
 * 답하게 하지 않고 실제로 느낀 문제를 자유롭게 쓰게 하려는 것이다. 사장님은 분류기가 나눈
 * 결과로 받고, 반영하면 그 한 줄이 아래 `reply` 자리로 돌아온다 (루프 ④).
 *
 * 로그: 이벤트를 새로 만들지 않는다. 계약에 없는 이벤트를 보내면 격리된다. 백엔드 API 와
 * 함께 `feedback_submit` 을 계약에 올린 뒤 켠다. 원문은 어차피 로그에 싣지 않는다.
 */
export default function FeedbackPanel({ product, persona }: FeedbackPanelProps) {
  const all = useFeedback();
  const forProduct = useMemo(() => feedbackForProduct(all, product.product_id), [all, product.product_id]);
  const mine = useMemo(
    () => forProduct.filter((f) => f.user_id === (persona?.persona_id ?? null)),
    [forProduct, persona],
  );
  const reflectedCount = useMemo(() => forProduct.filter((f) => f.status === 'reflected').length, [forProduct]);

  const [text, setText] = useState('');
  const [sent, setSent] = useState(false);

  const canSubmit = text.trim().length >= MIN_TEXT;

  const submit = () => {
    if (!canSubmit) return;
    submitFeedback({
      product_id: product.product_id,
      brand_name: product.brand_name,
      user_id: persona?.persona_id ?? null,
      body: text,
    });
    setText('');
    setSent(true);
  };

  return (
    <div className="feedback" data-log-content="brand_story">
      <div className="feedback__head">
        <div>
          <p className="feedback__kicker">{product.brand_name} 사장님이 직접 읽습니다</p>
          <h3 className="feedback__title">이 제품에 의견 남기기</h3>
          <p className="feedback__lead">
            아쉬웠던 점이나 고쳐졌으면 하는 점을 <strong>자유롭게</strong> 적어 주세요. 향·용기·사용감 같은 분류는
            저희가 나눠서 사장님께 전달합니다.
            {reflectedCount > 0 ? ` 지금까지 ${reflectedCount}건이 제품에 반영됐습니다.` : ' 첫 의견을 남겨 보세요.'}
          </p>
        </div>
      </div>

      <textarea
        className="feedback__text"
        value={text}
        maxLength={MAX_TEXT}
        rows={3}
        placeholder="예) 거의 다 써갈 때쯤 펌프를 눌러도 잘 안 나와서 끝까지 쓰기가 어려웠어요"
        onChange={(e) => {
          setText(e.target.value);
          setSent(false);
        }}
      />

      <div className="feedback__actions">
        <span className="feedback__count">
          {text.trim().length}/{MAX_TEXT}
        </span>
        <button type="button" className="btn btn--primary" disabled={!canSubmit} onClick={submit}>
          사장님께 보내기
        </button>
      </div>
      {sent ? <p className="feedback__sent">보냈습니다. 반영되면 이 자리에서 알려 드립니다.</p> : null}

      {mine.length > 0 ? (
        <ul className="feedback__mine">
          {mine.map((f) => (
            <li key={f.feedback_id} className={`feedback__item feedback__item--${f.status}`}>
              <div className="feedback__item-head">
                <span className="feedback__item-aspects">
                  {f.category_id ? categoryLabel(f.category_id) : '분류 중'}
                </span>
                <span className="feedback__item-status">
                  {f.status === 'reflected' ? '반영됨' : f.status === 'read' ? '사장님이 읽음' : '전달됨'}
                </span>
              </div>
              <p className="feedback__item-text">{f.body}</p>
              {f.reply ? (
                <p className="feedback__item-reply">
                  <strong>{product.brand_name}</strong> {f.reply}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
