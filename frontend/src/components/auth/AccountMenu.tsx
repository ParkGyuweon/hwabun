import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '../../hooks/useAuth';
import { useSyncMemberProfile } from '../../lib/memberProfileApi';
import { clearLoginPrompt, useLoginPrompt } from '../../lib/loginPrompt';
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
  // 로그인하면 서버 피부 프로필을 받아 브라우저 사본에 비춘다. 추천·리뷰 필터가 그 사본을 읽는다
  useSyncMemberProfile(session?.id);
  const [open, setOpen] = useState(false);
  const [mypage, setMypage] = useState(false);

  /*
   * 화면 다른 곳(상품 상세의 "바로 구매")에서 로그인을 요청하면 여기서 연다.
   * 로그인 폼을 두 벌 만들지 않기 위해서다 — 가입·에러 문구가 조용히 갈라진다 (lib/loginPrompt).
   */
  const promptReason = useLoginPrompt();
  const modalOpen = open || (promptReason !== null && session === null);

  const close = () => {
    setOpen(false);
    clearLoginPrompt();
  };

  useEffect(() => {
    if (!modalOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [modalOpen]);

  // 로그인이 되면 요청 사유는 역할을 다했다. 남겨 두면 로그아웃할 때 모달이 혼자 열린다
  useEffect(() => {
    if (session) clearLoginPrompt();
  }, [session]);

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

  return (
    <>
      <button type="button" className="account__btn account__btn--login" onClick={() => setOpen(true)}>
        로그인
      </button>
      {/* body 로 포털 — 헤더의 backdrop-filter 가 fixed 기준을 헤더로 바꿔 카드가 잘린다 (MyPage 주석) */}
      {modalOpen ? createPortal(
        <div className="auth-modal" role="presentation" onClick={close}>
          <div
            className="auth-modal__card"
            role="dialog"
            aria-modal="true"
            aria-label="로그인"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="auth-modal__close" aria-label="닫기" onClick={close}>
              ×
            </button>
            {/* 왜 갑자기 로그인 창이 떴는지 적는다. 모르면 그냥 닫아 버린다 */}
            {promptReason ? (
              <p className="auth-modal__reason" role="status">
                {promptReason}
              </p>
            ) : null}
            <AuthForm role="MEMBER" onSuccess={close} />
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
