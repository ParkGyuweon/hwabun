import { useState } from 'react';
import type { FormEvent } from 'react';
import { AuthError, ROLE_LABEL, login, register } from '../../lib/auth';
import type { AccountRole, AccountSession } from '../../lib/auth';

type Mode = 'login' | 'register';

interface AuthFormProps {
  role: AccountRole;
  onSuccess: (session: AccountSession) => void;
  /** 처음 열 때 어느 탭인지 */
  initialMode?: Mode;
  /** 폼 위에 붙는 제목. 없으면 역할 이름 */
  title?: string;
  lead?: string;
}

/**
 * 로그인 / 가입 폼. 쇼핑몰(MEMBER)·대시보드(SELLER)·플랫폼(ADMIN)이 같이 쓴다.
 *
 * 백엔드 `IdentityController` 계약: 비밀번호 8자 이상, MEMBER 는 닉네임·SELLER 는 담당자 이름.
 * ADMIN 은 가입 API 가 없어 로그인 탭만 보인다.
 * 서버 오류는 `AuthError.kind` 로 나눠 보여준다 — 자격 증명 실패와 서버 미기동을 섞지 않는다.
 */
export default function AuthForm({ role, onSuccess, initialMode = 'login', title, lead }: AuthFormProps) {
  const canRegister = role !== 'ADMIN';
  const [mode, setMode] = useState<Mode>(canRegister ? initialMode : 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AuthError | null>(null);

  const nameLabel = role === 'MEMBER' ? '닉네임' : '담당자 이름';
  const valid =
    /\S+@\S+\.\S+/.test(email.trim()) && password.length >= 8 && (mode === 'login' || name.trim().length > 0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === 'login' || role === 'ADMIN'
          ? await login(role, email, password)
          : await register(role, email, password, name);
      onSuccess(session);
    } catch (err) {
      setError(err instanceof AuthError ? err : new AuthError('알 수 없는 오류가 났습니다.', 'unknown'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="auth" onSubmit={submit} noValidate>
      <div className="auth__head">
        <p className="auth__eyebrow">{ROLE_LABEL[role]}</p>
        <h2 className="auth__title">{title ?? (mode === 'login' ? '로그인' : '가입하기')}</h2>
        {lead ? <p className="auth__lead">{lead}</p> : null}
      </div>

      {canRegister ? (
        <div className="auth__tabs" role="tablist" aria-label="로그인 또는 가입">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            className={mode === 'login' ? 'is-active' : ''}
            onClick={() => {
              setMode('login');
              setError(null);
            }}
          >
            로그인
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register'}
            className={mode === 'register' ? 'is-active' : ''}
            onClick={() => {
              setMode('register');
              setError(null);
            }}
          >
            가입
          </button>
        </div>
      ) : null}

      <label className="auth__field">
        <span>이메일</span>
        <input
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
        />
      </label>

      <label className="auth__field">
        <span>비밀번호</span>
        <input
          type="password"
          name="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="8자 이상"
          minLength={8}
          required
        />
      </label>

      {mode === 'register' && canRegister ? (
        <label className="auth__field">
          <span>{nameLabel}</span>
          <input
            type="text"
            name="name"
            autoComplete={role === 'MEMBER' ? 'nickname' : 'name'}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={role === 'MEMBER' ? '리뷰에 보이는 이름' : '브랜드 담당자 이름'}
            required
          />
        </label>
      ) : null}

      {error ? (
        <p className={`auth__error auth__error--${error.kind}`} role="alert">
          {error.message}
        </p>
      ) : null}

      <button type="submit" className="auth__submit" disabled={!valid || busy}>
        {busy ? '확인 중…' : mode === 'login' ? '로그인' : '가입하고 시작하기'}
      </button>

      {mode === 'login' && canRegister ? (
        <p className="auth__hint">
          처음이신가요?{' '}
          <button type="button" className="auth__link" onClick={() => setMode('register')}>
            가입하기
          </button>
        </p>
      ) : null}
    </form>
  );
}
