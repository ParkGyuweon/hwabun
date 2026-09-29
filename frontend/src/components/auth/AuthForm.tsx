import { useState } from 'react';
import type { FormEvent } from 'react';
import { AuthError, ROLE_LABEL, login, register } from '../../lib/auth';
import type { AccountRole, AccountSession } from '../../lib/auth';
import {
  EMPTY_PROFILE,
  PROFILE_FIELDS,
  PROFILE_FIELD_KO,
  PROFILE_OPTIONS,
  PROFILE_RECOMMENDED,
  profileToApi,
  saveMemberProfile,
} from '../../lib/memberProfile';
import type { MemberProfile, ProfileField } from '../../lib/memberProfile';
import { track } from '../../lib/logger';

type Mode = 'login' | 'register';

/** 가입 동의 항목. 필수 둘이 켜져야 가입 버튼이 눌린다 */
type ConsentKey = 'terms' | 'privacy' | 'skinInfo' | 'behaviorLink';

const CONSENTS: { key: ConsentKey; required: boolean; label: string; view?: string; hint?: string }[] = [
  { key: 'terms', required: true, label: '이용약관 동의', view: '?terms=1' },
  { key: 'privacy', required: true, label: '개인정보 수집·이용 동의', view: '?privacy=1' },
  { key: 'skinInfo', required: false, label: '피부 정보 수집·이용 동의 (맞춤 추천용)', view: '?privacy=1' },
  { key: 'behaviorLink', required: false, label: '둘러본 기록을 내 계정과 연결해 추천에 쓰기', view: '?privacy=1', hint: '끄면 찜·장바구니·구매가 추천에 반영되지 않아 맞춤 추천이 약해져요.' },
];

const NO_CONSENT: Record<ConsentKey, boolean> = { terms: false, privacy: false, skinInfo: false, behaviorLink: false };

/* 눈 아이콘. 아이콘 라이브러리를 넣지 않으려고 인라인 SVG 로 둔다 */
function EyeIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M1.5 10S4.6 4.5 10 4.5 18.5 10 18.5 10 15.4 15.5 10 15.5 1.5 10 1.5 10Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <circle cx="10" cy="10" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M1.5 10S4.6 4.5 10 4.5c1.2 0 2.3.3 3.2.7M18.5 10s-1.4 2.5-4 4.1c-1.3.8-2.8 1.4-4.5 1.4-1.1 0-2.1-.2-3-.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path d="M3 3l14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

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
  /** 비밀번호를 눈으로 확인하는 토글. 오타를 입력 단계에서 잡는다 */
  const [showPassword, setShowPassword] = useState(false);
  /**
   * 고객 가입에서 받는 피부 프로필 4개. 페르소나 표와 같은 값 체계라 페르소나를 회원으로
   * 옮길 때도 그대로 들어간다. 전부 "선택 안 함"(null) 가능 — 억지로 채우게 하지 않는다 (AI 요청 §1.2).
   */
  const [profile, setProfile] = useState<MemberProfile>(EMPTY_PROFILE);
  /** 고객 가입 동의. 피부 정보 동의가 꺼져 있으면 피부 입력을 숨기고 값도 보내지 않는다 */
  const [consent, setConsent] = useState<Record<ConsentKey, boolean>>(NO_CONSENT);
  const needsConsent = mode === 'register' && role === 'MEMBER';
  const allConsented = CONSENTS.every((c) => consent[c.key]);
  const requiredConsented = consent.terms && consent.privacy;

  const nameLabel = role === 'MEMBER' ? '닉네임' : '담당자 이름';
  const valid =
    /\S+@\S+\.\S+/.test(email.trim()) &&
    password.length >= 8 &&
    (mode === 'login' || name.trim().length > 0) &&
    (!needsConsent || requiredConsented);
  /** 동의하지 않았으면 서버에도 이 브라우저에도 피부 정보를 남기지 않는다 */
  const sentProfile = consent.skinInfo ? profile : EMPTY_PROFILE;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === 'login' || role === 'ADMIN'
          ? await login(role, email, password)
          : await register(
              role,
              email,
              password,
              name,
              role === 'MEMBER'
                ? {
                    ...(consent.skinInfo ? profileToApi(profile) : {}),
                    agreeTerms: consent.terms,
                    agreePrivacy: consent.privacy,
                    agreeSkinInfo: consent.skinInfo,
                    agreeBehaviorLink: consent.behaviorLink,
                  }
                : {},
            );
      // 백엔드 프로필 API 가 열리기 전까지 이 브라우저가 프로필을 든다. 리뷰 필터·"내 피부 타입" 칩이 바로 켜진다
      if (mode === 'register' && role === 'MEMBER') saveMemberProfile(session.id, sentProfile);
      /**
       * `login` 이벤트 (계약 event-properties-schema.md :78 · intent session · properties 없음). "익명 → 계정 전환 시점" 이라
       * 가입 직후도 같은 시점이다. 고객(MEMBER)만 — 판매자·운영자는 로거가 어차피 막는다. 수집기가 JWT 로 account_id 를
       * 붙이므로 봉투에는 아무것도 더 싣지 않는다.
       */
      if (role === 'MEMBER') track('login');
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
        <div className="auth__password">
          <input
            type={showPassword ? 'text' : 'password'}
            name="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="8자 이상"
            minLength={8}
            required
          />
          {/*
            토글은 `button` 이고 label 안에 있다. label 을 누르면 입력으로 포커스가
            가야 하므로 이 버튼만 클릭을 삼킨다(onMouseDown preventDefault) — 안 그러면
            누를 때 포커스가 튀어 커서 위치가 사라진다.
          */}
          <button
            type="button"
            className="auth__peek"
            aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
            aria-pressed={showPassword}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => setShowPassword((v) => !v)}
          >
            {showPassword ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
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

      {needsConsent ? (
        <fieldset className="auth__consent">
          <legend className="auth__sr">약관 동의</legend>
          <label className="auth__consent-all">
            <input
              type="checkbox"
              checked={allConsented}
              onChange={(e) => {
                const on = e.target.checked;
                setConsent({ terms: on, privacy: on, skinInfo: on, behaviorLink: on });
              }}
            />
            <span>전체 동의</span>
          </label>
          <ul className="auth__consent-list">
            {CONSENTS.map((c) => (
              <li key={c.key} className="auth__consent-item">
                <label>
                  <input
                    type="checkbox"
                    name={`agree-${c.key}`}
                    checked={consent[c.key]}
                    onChange={(e) => setConsent((prev) => ({ ...prev, [c.key]: e.target.checked }))}
                  />
                  <span>
                    <em className={c.required ? 'auth__consent-tag is-required' : 'auth__consent-tag'}>
                      {c.required ? '필수' : '선택'}
                    </em>
                    {c.label}
                    {c.hint ? <small className="auth__consent-hint">{c.hint}</small> : null}
                  </span>
                </label>
                {c.view ? (
                  // 새 탭으로 연다 — 같은 탭에서 열면 쓰던 가입 양식이 사라진다
                  <a className="auth__consent-view" href={c.view} target="_blank" rel="noopener noreferrer">
                    보기
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
          {!requiredConsented ? (
            <p className="auth__consent-note">필수 항목에 동의하시면 가입할 수 있어요.</p>
          ) : null}
        </fieldset>
      ) : null}

      {needsConsent && consent.skinInfo ? (
        <fieldset className="auth__profile">
          <legend>
            피부 정보 <span className="auth__optional">선택</span>
          </legend>
          <p className="auth__profile-lead">
            피부 타입과 톤을 알려 주시면 비슷한 피부 사용자의 반응을 추천에 반영합니다. 나중에 내 정보에서 바꿀 수 있습니다.
          </p>
          <div className="auth__profile-grid">
            {PROFILE_FIELDS.map((field: ProfileField) => (
              <label key={field} className="auth__field">
                <span>
                  {PROFILE_FIELD_KO[field]}
                  {PROFILE_RECOMMENDED.includes(field) ? <em className="auth__recommended">권장</em> : null}
                </span>
                <select
                  name={field}
                  value={profile[field] ?? ''}
                  onChange={(e) => setProfile((p) => ({ ...p, [field]: e.target.value === '' ? null : e.target.value }))}
                >
                  <option value="">선택 안 함</option>
                  {PROFILE_OPTIONS[field].map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.ko}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      {error ? (
        <p className={`auth__error auth__error--${error.kind}`} role="alert">
          {error.message}
          {/*
            백엔드는 역할별로 계정을 따로 조회하고 401 하나만 돌려준다. 그래서 브랜드
            담당자 계정으로 고객 로그인을 시도해도 "비밀번호가 틀렸다" 로만 보인다.
            실제로 그렇게 막힌 적이 있어서 갈 곳을 같이 알려준다.
          */}
          {role === 'MEMBER' && error.kind === 'credentials' ? (
            <span className="auth__error-hint">
              브랜드 담당자 계정은 여기서 로그인되지 않습니다. 아래 대시보드 로그인을 써 주세요.
            </span>
          ) : null}
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
