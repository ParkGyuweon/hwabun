import { useState } from 'react';
import { MAX_REASONS, PURCHASE_REASONS } from '../../lib/checkout';

/**
 * 구매 직후 이유 설문.
 *
 * 행동 로그는 "무엇을 얼마나 봤나" 는 답하지만 **왜 샀나** 는 답하지 못한다.
 * 성분을 오래 봤다는 것과 성분 때문에 샀다는 것은 다르고, 전자로 후자를 추론하면
 * 추천이 그쪽으로 쏠린다. 그래서 한 번만, 클릭으로만 묻는다.
 *
 * 두 개까지만 고르게 한다. 다 고르면 아무 말도 안 하는 것과 같다.
 * 건너뛰기도 이벤트로 남긴다 — 안 답한 것도 정보이고, 응답률을 모르면 답변 분포를
 * 전체 구매자의 것으로 읽는 실수를 한다.
 */
export default function PurchaseSurvey({
  onSubmit,
  onSkip,
}: {
  onSubmit: (reasons: string[]) => void;
  onSkip: () => void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  /** 보내고 나면 같은 주문에 두 번 답할 수 없다. 설문은 주문당 한 번이다 */
  const [sent, setSent] = useState(false);

  const toggle = (key: string) => {
    setPicked((prev) => {
      if (prev.includes(key)) return prev.filter((k) => k !== key);
      // 가득 찼으면 가장 먼저 고른 것을 밀어낸다. 눌러도 아무 일 없으면 dead_click 이 된다
      return prev.length >= MAX_REASONS ? [...prev.slice(1), key] : [...prev, key];
    });
  };

  if (sent) {
    return (
      <section className="survey survey--done" data-log-section="purchase_survey">
        <p>답변 고맙습니다. 추천을 다듬는 데 쓰겠습니다.</p>
      </section>
    );
  }

  return (
    <section className="survey" data-log-section="purchase_survey">
      <header className="survey__head">
        <h2>어떤 점이 마음에 들어 구매하셨나요?</h2>
        <p>최대 {MAX_REASONS}개까지 고를 수 있어요. 답변은 추천을 다듬는 데만 씁니다.</p>
      </header>

      <div className="survey__chips" role="group" aria-label="구매 이유">
        {PURCHASE_REASONS.map((reason) => {
          const on = picked.includes(reason.key);
          return (
            <button
              key={reason.key}
              type="button"
              className={`survey__chip${on ? ' is-on' : ''}`}
              onClick={() => toggle(reason.key)}
              aria-pressed={on}
              data-log-action="purchase_reason_toggle"
            >
              {reason.label}
            </button>
          );
        })}
      </div>

      <div className="survey__actions">
        <button
          type="button"
          className="survey__skip"
          onClick={() => {
            setSent(true);
            onSkip();
          }}
        >
          건너뛰기
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={picked.length === 0}
          onClick={() => {
            setSent(true);
            onSubmit(picked);
          }}
          data-log-action="purchase_reason_submit"
        >
          보내기
        </button>
      </div>
    </section>
  );
}
