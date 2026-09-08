import { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { logout } from '../../lib/auth';
import AuthForm from './AuthForm';
import '../../styles/auth.css';

/**
 * 쇼핑몰 헤더의 계정 자리. 로그인 전엔 "로그인" 버튼, 후엔 이름과 로그아웃.
 *
 * 페르소나 스위처는 그대로 둔다 — 페르소나는 행동 로그의 주체(시뮬레이션 신원)이고,
 * 여기 계정은 백엔드 주문·리뷰·피드백의 주체다. 둘은 역할이 다르다.
 */
export default function AccountMenu() {
  const session = useAuth('MEMBER');
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (session) {
    return (
      <div className="account">
        <span className="account__name" title={session.email}>
          {session.name}
        </span>
        <button type="button" className="account__btn" onClick={() => logout('MEMBER')}>
          로그아웃
        </button>
      </div>
    );
  }

  return (
    <>
      <button type="button" className="account__btn account__btn--login" onClick={() => setOpen(true)}>
        로그인
      </button>
      {open ? (
        <div className="auth-modal" role="presentation" onClick={() => setOpen(false)}>
          <div
            className="auth-modal__card"
            role="dialog"
            aria-modal="true"
            aria-label="로그인"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="auth-modal__close" aria-label="닫기" onClick={() => setOpen(false)}>
              ×
            </button>
            <AuthForm role="MEMBER" onSuccess={() => setOpen(false)} />
            {/* 브랜드 담당자는 다른 진입점(dashboard.html, SELLER 세션). 같은 모달에 모드를 섞지 않는다 */}
            <p className="auth__hint auth__hint--alt">
              브랜드 담당자이신가요?{' '}
              <a className="auth__link" href="/dashboard.html">
                대시보드 로그인
              </a>
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
