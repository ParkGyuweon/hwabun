import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '../../hooks/useAuth';
import { useBackdropClose } from '../../hooks/useBackdropClose';
import AuthForm from './AuthForm';
import MyPage from '../account/MyPage';
import '../../styles/auth.css';

/**
 * 쇼핑몰 헤더의 계정 자리. 로그인 전엔 "로그인" 버튼, 후엔 이름(누르면 내 정보)과 로그아웃은 내 정보 안에.
 *
 * 페르소나 스위처는 그대로 둔다 — 페르소나는 행동 로그의 주체(시뮬레이션 신원)이고,
 * 여기 계정은 백엔드 주문·리뷰·피드백의 주체다. 둘은 역할이 다르다.
 * 단, 로그인한 회원이 피부 정보를 채우면 그 값이 스위처 페르소나 대신 화면(리뷰 필터·피부 칩)에 쓰인다 (App.tsx).
 */
export default function AccountMenu() {
  const session = useAuth('MEMBER');
  const [open, setOpen] = useState(false);
  const [mypage, setMypage] = useState(false);

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
        <button type="button" className="account__btn account__btn--me" onClick={() => setMypage(true)} title={session.email}>
          <span className="account__name">{session.name}</span>
          <span className="account__me">내 정보</span>
        </button>
        {mypage ? <MyPage session={session} onClose={() => setMypage(false)} /> : null}
      </div>
    );
  }

  // 드래그로 글자를 긁다 배경에서 손을 떼도 닫히지 않게 — 배경에서 눌렀다 뗀 클릭만 닫는다
  const backdrop = useBackdropClose(() => setOpen(false));

  return (
    <>
      <button type="button" className="account__btn account__btn--login" onClick={() => setOpen(true)}>
        로그인
      </button>
      {/* body 로 포털 — 헤더의 backdrop-filter 가 fixed 기준을 헤더로 바꿔 카드가 잘린다 (MyPage 주석) */}
      {open ? createPortal(
        <div className="auth-modal" role="presentation" {...backdrop}>
          <div className="auth-modal__card" role="dialog" aria-modal="true" aria-label="로그인">
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
        </div>,
        document.body,
      ) : null}
    </>
  );
}
