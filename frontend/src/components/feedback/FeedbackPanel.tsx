import { useMemo, useState } from 'react';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForProduct, submitFeedback } from '../../lib/feedbackStore';
import { FEEDBACK_ASPECTS } from '../../types/feedback';
import type { FeedbackAspect } from '../../types/feedback';
import type { PersonaProfile } from '../../types/persona';
import type { Product } from '../../types/product';

interface FeedbackPanelProps {
  product: Product;
  persona: PersonaProfile | null;
}

const MAX_TEXT = 300;

/**
 * 상품 페이지의 "이 제품에 의견 남기기".
 *
 * 리뷰가 아니다. 평점이 없고, 대신 **어느 부분** 인지를 먼저 고른다. 사장님은 이 분류로
 * 나눠 받는다. 대기업에서는 내 의견이 수많은 것 중 하나지만 여기서는 사장이 읽고 바뀐 것을
 * 돌려준다 — 그 "돌려주는" 자리가 아래 `reply` 다 (루프 ④).
 *
 * 로그: 이벤트를 새로 만들지 않는다. 계약에 없는 이벤트를 보내면 격리된다. 백엔드 API 와
 * 함께 `feedback_submit` 을 계약에 올린 뒤 켠다. 원문은 어차피 로그에 싣지 않는다.
 */
export default function FeedbackPanel({ product, persona }: FeedbackPanelProps) {
  const all = useFeedback();
  const mine = useMemo(
    () => feedbackForProduct(all, product.product_id).filter((f) => f.persona_id === (persona?.persona_id ?? null)),
    [all, product.product_id, persona],
  );
  const reflectedCount = useMemo(
    () => feedbackForProduct(all, product.product_id).filter((f) => f.status === 'reflected').length,
    [all, product.product_id],
  );

  const [aspects, setAspects] = useState<FeedbackAspect[]>([]);
  const [text, setText] = useState('');
  const [sent, setSent] = useState(false);

  const toggle = (key: FeedbackAspect) =>
    setAspects((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const canSubmit = aspects.length > 0 && text.trim().length >= 5;

  const submit = () => {
    if (!canSubmit) return;
    submitFeedback({
      product_id: product.product_id,
      brand_name: product.brand_name,
      persona_id: persona?.persona_id ?? null,
      aspects,
      text,
    });
    setAspects([]);
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
            향·용기·제형·성분처럼 <strong>어느 부분</strong>인지 골라 주시면 그대로 사장님께 나눠서 갑니다.
            {reflectedCount > 0 ? ` 지금까지 ${reflectedCount}건이 제품에 반영됐습니다.` : ' 첫 의견을 남겨 보세요.'}
          </p>
        </div>
      </div>

      <div className="feedback__aspects" role="group" aria-label="의견 분류">
        {FEEDBACK_ASPECTS.map((a) => (
          <button
            key={a.key}
            type="button"
            className={`chip chip--select${aspects.includes(a.key) ? ' is-active' : ''}`}
            aria-pressed={aspects.includes(a.key)}
            title={a.hint}
            onClick={() => toggle(a.key)}
          >
            {a.label}
          </button>
        ))}
      </div>

      <textarea
        className="feedback__text"
        value={text}
        maxLength={MAX_TEXT}
        rows={3}
        placeholder={
          aspects.length
            ? FEEDBACK_ASPECTS.filter((a) => aspects.includes(a.key))
                .map((a) => a.hint)
                .filter(Boolean)
                .join(' · ')
            : '먼저 위에서 어느 부분인지 고르고, 무엇이 어땠는지 적어 주세요 (5자 이상)'
        }
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
                  {f.aspects.map((k) => FEEDBACK_ASPECTS.find((a) => a.key === k)?.label ?? k).join(' · ')}
                </span>
                <span className="feedback__item-status">
                  {f.status === 'reflected' ? '반영됨' : f.status === 'read' ? '사장님이 읽음' : '전달됨'}
                </span>
              </div>
              <p className="feedback__item-text">{f.text}</p>
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
