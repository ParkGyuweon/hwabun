import { useMemo, useState } from 'react';
import { submitFeedbackBackend } from '../../lib/shopApi';
import { useAuth } from '../../hooks/useAuth';
import { useFeedback } from '../../hooks/useFeedback';
import { feedbackForProduct, submitFeedback } from '../../lib/feedbackStore';
import { FEEDBACK_INPUT_AXES, axisLabel, categoryLabel, labelsOf } from '../../types/feedback';
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
 * 리뷰가 아니다. 평점이 없고, 사장님에게 가는 개선 요청이다.
 *
 * 계약 0.2.0 (feedback-classification.md): **축은 고객이 토글로 고르고** `axis_id` 로 보낸다.
 * 분류기는 그 축 안의 카테고리만 여러 개(최대 3) 붙이고 축을 다시 판단하지 않는다.
 * 한 고객이 상품 하나에 축마다 한 건씩 여러 건을 보낼 수 있으므로, 왼쪽에서 축을 고르고
 * 오른쪽 칸에 그 축 얘기만 쓴다. 축을 바꾸면 칸은 그 축의 초안으로 바뀌고 저장은 새 건이다.
 * 사장님이 반영하면 그 한 줄이 아래 `reply` 자리로 돌아온다 (루프 ④).
 *
 * 로그: 이벤트를 새로 만들지 않는다. 계약에 없는 이벤트를 보내면 격리된다. 백엔드 API 와
 * 함께 `feedback_submit` 을 계약에 올린 뒤 켠다. 원문은 어차피 로그에 싣지 않는다.
 */
export default function FeedbackPanel({ product, persona }: FeedbackPanelProps) {
  const all = useFeedback();
  /** 로그인했으면 계정 id 가 작성자다. 백엔드 피드백 API 의 주체와 같게 둔다. 아니면 페르소나 */
  const account = useAuth('MEMBER');
  const userId = account?.id ?? persona?.persona_id ?? null;
  const forProduct = useMemo(() => feedbackForProduct(all, product.product_id), [all, product.product_id]);
  const mine = useMemo(
    () => forProduct.filter((f) => f.user_id === userId),
    [forProduct, userId],
  );
  const reflectedCount = useMemo(() => forProduct.filter((f) => f.status === 'reflected').length, [forProduct]);
  /** 내가 이 상품에 이미 보낸 축. 토글에 점으로 표시 */
  const sentAxes = useMemo(() => new Set(mine.map((f) => f.axis_id).filter(Boolean)), [mine]);

  const [axisId, setAxisId] = useState<string>(FEEDBACK_INPUT_AXES[0].id);
  /** 축마다 초안을 따로 둔다. 축을 바꿔도 쓰던 글이 사라지지 않는다 */
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sentAxis, setSentAxis] = useState<string | null>(null);

  const axis = FEEDBACK_INPUT_AXES.find((a) => a.id === axisId) ?? FEEDBACK_INPUT_AXES[0];
  const text = drafts[axisId] ?? '';
  const canSubmit = text.trim().length >= MIN_TEXT;

  const [sendError, setSendError] = useState<string | null>(null);
  const submit = async () => {
    if (!canSubmit) return;
    setSendError(null);
    /*
     * 백엔드에 있는 상품이면 서버로 보낸다. 서버가 이 고객의 결제 완료 주문을 확인하고, 없으면 403 이 정상이다.
     *
     * 판정은 `backend_brand_id` 로 한다. `source` 로 보면 안 된다 — 프론트가 이미 아는 상품(번들 카탈로그에
     * 있는 것)은 백엔드 값을 얹어도 `source` 를 `seed_catalog` 로 **일부러 남긴다**(productRegistry
     * `mergeWithLocal`: 그래야 세포라 리뷰 2,000건이 안 사라진다). 그래서 SSAFY Beauty 8종처럼 번들에도 있고
     * 백엔드에도 있는 상품은 `source !== 'backend'` 라 의견이 서버로 안 가고 이 브라우저에만 쌓였다.
     * 대시보드 "백엔드 피드백 0" 이 그 결과다. `mergeWithLocal` 주석이 이미 같은 말을 하고 있다 —
     * "이 상품이 백엔드에 있는가" 는 `backend_brand_id` 로 안다.
     */
    if (product.backend_brand_id) {
      const r = await submitFeedbackBackend({ productId: product.product_id, axisId, body: text.trim() });
      if (!r.ok) {
        setSendError(
          r.status === 403
            ? '구매한 상품에만 의견을 남길 수 있습니다. 주문·결제 뒤에 다시 시도해 주세요.'
            : `보내지 못했습니다. ${r.reason}`,
        );
        return;
      }
    } else {
      submitFeedback({
        product_id: product.product_id,
        brand_name: product.brand_name,
        user_id: userId,
        axis_id: axisId,
        body: text,
      });
    }
    setDrafts((d) => ({ ...d, [axisId]: '' }));
    setSentAxis(axisId);
  };

  return (
    <div className="feedback" data-log-content="brand_story">
      <div className="feedback__head">
        <div>
          <p className="feedback__kicker">{product.brand_name} 사장님이 직접 읽습니다</p>
          <h3 className="feedback__title">이 제품에 의견 남기기</h3>
          <p className="feedback__lead">
            왼쪽에서 주제를 고르고 오른쪽 칸에 <strong>자유롭게</strong> 적어 주세요. 주제마다 따로 보낼 수 있습니다.
            {reflectedCount > 0 ? ` 지금까지 ${reflectedCount}건이 제품에 반영됐습니다.` : ' 첫 의견을 남겨 보세요.'}
          </p>
        </div>
      </div>

      <div className="feedback__compose">
        <div className="feedback__axes" role="tablist" aria-label="피드백 주제">
          <p className="feedback__axes-label">피드백 주제</p>
          {FEEDBACK_INPUT_AXES.map((a) => {
            const active = a.id === axisId;
            const hasDraft = (drafts[a.id] ?? '').trim().length > 0;
            return (
              <button
                key={a.id}
                type="button"
                role="tab"
                aria-selected={active}
                aria-label={a.label}
                className={`feedback__axis${active ? ' is-active' : ''}`}
                title={a.desc}
                onClick={() => {
                  setAxisId(a.id);
                  setSentAxis(null);
                }}
              >
                <span>{a.label}</span>
                {active ? (
                  <span className="feedback__axis-dot" aria-hidden="true" />
                ) : hasDraft ? (
                  <span className="feedback__axis-mark" aria-label="작성 중">
                    …
                  </span>
                ) : sentAxes.has(a.id) ? (
                  <span className="feedback__axis-mark feedback__axis-mark--sent" aria-label="보냄">
                    ✓
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="feedback__editor">
          <label className="feedback__editor-label" htmlFor="feedback-body">
            {axis.label}에 대한 의견
          </label>
          <textarea
            id="feedback-body"
            className="feedback__text"
            value={text}
            maxLength={MAX_TEXT}
            rows={5}
            placeholder={`예) ${axis.desc}`}
            onChange={(e) => {
              const v = e.target.value;
              setDrafts((d) => ({ ...d, [axisId]: v }));
              setSentAxis(null);
            }}
          />
          <div className="feedback__actions">
            <span className="feedback__count">
              {sentAxis === axisId ? (
                <span className="feedback__sent">보냈습니다. 반영되면 이 자리에서 알려 드립니다.</span>
              ) : (
                `${text.trim().length}/${MAX_TEXT}`
              )}
            </span>
            {sendError ? <p className="feedback__error" role="alert">{sendError}</p> : null}
            <button type="button" className="btn btn--primary feedback__submit" disabled={!canSubmit} onClick={submit}>
              사장님께 보내기
            </button>
          </div>
        </div>
      </div>

      {mine.length > 0 ? (
        <ul className="feedback__mine">
          {mine.map((f) => (
            <li key={f.feedback_id} className={`feedback__item feedback__item--${f.status}`}>
              <div className="feedback__item-head">
                <span className="feedback__item-aspects">
                  <strong>{f.axis_id ? axisLabel(f.axis_id) : '주제 없음'}</strong>
                  {' · '}
                  {labelsOf(f).length > 0 ? labelsOf(f).map((l) => categoryLabel(l.category_id)).join(' · ') : '분류 중'}
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
