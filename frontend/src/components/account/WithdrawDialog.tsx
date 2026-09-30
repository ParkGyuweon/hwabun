import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { useBackdropClose } from '../../hooks/useBackdropClose';
import { withdrawMember } from '../../lib/memberWithdraw';

/**
 * 회원 탈퇴 확인 창. 마이페이지 위에 한 겹 더 띄운다.
 *
 * 비밀번호와 "확인했어요" 체크가 둘 다 있어야 누를 수 있다. 되돌릴 수 없는 일이라 한 번 더 멈추게 한다.
 * 탈퇴 요청 중에는 Esc·배경·취소로 닫히지 않는다 — 닫힌 뒤에 탈퇴가 끝나면 무엇이 일어났는지 알 수 없다.
 */
export default function WithdrawDialog({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  busyRef.current = busy;
  const titleId = useId();
  const descId = useId();

  const cancel = () => {
    if (!busyRef.current) onCancel();
  };
  const backdrop = useBackdropClose(cancel);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Esc 로 닫기 · Tab 을 창 안에 가두기
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (!busyRef.current) onCancel();
        return;
      }
      if (e.key !== 'Tab' || !cardRef.current) return;
      const items = Array.from(
        cardRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)'),
      );
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  const canSubmit = password.length > 0 && agreed && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const result = await withdrawMember(password);
    if (result.ok) {
      onDone();
      return;
    }
    setBusy(false);
    setError(result.reason);
    if (result.kind === 'password') {
      setPassword('');
      inputRef.current?.focus();
    }
  };

  return createPortal(
    <div className="auth-modal auth-modal--stacked" role="presentation" {...backdrop}>
      <div
        ref={cardRef}
        className="auth-modal__card withdraw"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        aria-busy={busy}
      >
        <button type="button" className="auth-modal__close" aria-label="닫기" onClick={cancel} disabled={busy}>
          ×
        </button>

        <form className="auth" onSubmit={(e) => void submit(e)} noValidate>
          <div className="auth__head">
            <h2 id={titleId} className="auth__title">
              회원 탈퇴
            </h2>
            <p className="auth__lead">탈퇴하기 전에 한 번만 확인해 주세요.</p>
          </div>

          <ul id={descId} className="withdraw__list">
            <li>이메일·닉네임·피부 정보는 바로 지워져요.</li>
            <li>
              주문 내역과 작성한 리뷰는 ‘탈퇴한 회원’으로 남아요. 거래 기록은 법에 따라 5년 동안 보관해요.
            </li>
            <li>같은 이메일로 언제든 다시 가입할 수 있어요.</li>
          </ul>

          <label className="auth__field">
            <span>비밀번호</span>
            <input
              ref={inputRef}
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (error) setError(null);
              }}
              placeholder="지금 쓰는 비밀번호"
              disabled={busy}
              required
            />
          </label>

          <label className="withdraw__check">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} disabled={busy} />
            <span>위 내용을 확인했어요</span>
          </label>

          {error ? (
            <p className="auth__error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="withdraw__actions">
            <button type="button" className="withdraw__cancel" onClick={cancel} disabled={busy}>
              취소
            </button>
            <button type="submit" className="withdraw__submit" disabled={!canSubmit}>
              {busy ? '탈퇴하는 중…' : '탈퇴하기'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
