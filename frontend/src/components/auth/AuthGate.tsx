import type { ReactNode } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { devSession } from '../../lib/auth';
import type { AccountRole } from '../../lib/auth';
import AuthForm from './AuthForm';
import '../../styles/auth.css';

interface AuthGateProps {
  role: AccountRole;
  /** 게이트 화면의 로고·이름 */
  product: { mark: string; name: string; tagline: string };
  children: ReactNode;
}

/** 개발자 모드 버튼을 보일까. 로컬 개발 서버이거나 주소에 ?dev=1 이 있을 때만 */
function showDevButton(): boolean {
  if (import.meta.env.DEV) return true;
  try {
    return new URLSearchParams(window.location.search).get('dev') === '1';
  } catch {
    return false;
  }
}

/**
 * 역할 로그인이 없으면 전체 화면을 로그인으로 바꾼다. 대시보드(SELLER)·플랫폼(ADMIN)용.
 * 쇼핑몰은 로그인 없이도 둘러볼 수 있어야 하므로 게이트를 쓰지 않고 헤더 메뉴(AccountMenu)만 둔다.
 */
export default function AuthGate({ role, product, children }: AuthGateProps) {
  const session = useAuth(role);
  if (session) return <>{children}</>;

  return (
    <div className="auth-gate">
      <div className="auth-gate__card">
        <div className="auth-gate__brand">
          <img src={product.mark} alt="" width="40" height="40" />
          <div>
            <strong>{product.name}</strong>
            <span>{product.tagline}</span>
          </div>
        </div>
        <AuthForm role={role} onSuccess={() => undefined} />
        {role === 'ADMIN' ? (
          <p className="auth-gate__note">운영자 계정은 가입 화면이 없습니다. 팀에서 발급한 계정으로 들어오세요.</p>
        ) : null}
        {/*
          개발자 모드 — 로컬 개발(import.meta.env.DEV)이거나 주소에 ?dev=1 을 붙였을 때만 보인다 (2026-09-29).
          배포 화면에 그대로 두면 심사위원이 눌러 모의 데이터 화면을 실제 화면으로 볼 수 있다.
          모의 세션이라 서버는 부르지 않고 화면은 모의 데이터다.
        */}
        {showDevButton() ? (
          <button type="button" className="auth-gate__dev" onClick={() => devSession(role)}>
            개발자 모드 · 백엔드 없이 모의 데이터로 보기
          </button>
        ) : null}
      </div>
    </div>
  );
}
