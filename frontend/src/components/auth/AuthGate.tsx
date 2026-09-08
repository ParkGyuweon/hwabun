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
        {import.meta.env.DEV ? (
          <button type="button" className="auth-gate__dev" onClick={() => devSession(role)}>
            백엔드 없이 보기 (개발용 · 모의 세션)
          </button>
        ) : null}
      </div>
    </div>
  );
}
