import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import type { AccountSession } from '../../lib/auth';
import { logout } from '../../lib/auth';
import {
  PROFILE_FIELDS,
  PROFILE_FIELD_KO,
  PROFILE_OPTIONS,
  PROFILE_RECOMMENDED,
  isEmptyProfile,
  loadMemberProfile,
  saveMemberProfile,
  subscribeMemberProfile,
} from '../../lib/memberProfile';
import type { MemberProfile, ProfileField } from '../../lib/memberProfile';
import { loadOrders, subscribeOrders } from '../../lib/orderHistory';
import { formatPrice } from '../../lib/format';

/**
 * 마이페이지 · 쇼핑몰의 기본 요소 중 빠져 있던 것 (2026-09-11).
 *
 * 세 덩이만 둔다. 내 정보(이메일·닉네임) · 피부 정보(가입 때 받은 4개, 여기서 고침) · 주문 내역.
 * 피부 정보는 "가입에서 건너뛸 수 있게 하되 나중에 채우고 바꿀 수 있어야 한다" (AI 요청 §1.2) 의 그 자리다.
 *
 * 백엔드에 프로필 조회·수정 API 와 주문 목록 API 가 없다 (`docs/shop-backend-requests.md` 8번). 그래서 지금은
 * 둘 다 이 브라우저 저장본이고, 화면에 그렇게 적는다. API 가 열리면 저장·조회 함수 본문만 바뀐다.
 *
 * 비밀번호 변경·회원 탈퇴는 백엔드 API 가 없어 넣지 않았다. 빈 버튼을 두는 것보다 없는 것이 낫다.
 *
 * 모달은 `document.body` 로 포털한다. 헤더(`.site-header`)에 `backdrop-filter` 가 있어 그 안의 `position: fixed` 는
 * 화면이 아니라 헤더 상자를 기준으로 잡힌다 — 헤더 높이 안에서 가운데 정렬돼 카드 윗부분이 잘렸다 (팀원 제보 09-14).
 */
export default function MyPage({ session, onClose }: { session: AccountSession; onClose: () => void }) {
  const getProfile = useCallback(() => loadMemberProfile(session.id), [session.id]);
  const saved = useSyncExternalStore(subscribeMemberProfile, getProfile, getProfile);
  /**
   * 편집 중인 값. 저장본(`saved`)이 바뀌면(저장 직후 · 다른 탭) 편집본을 버리고 저장본으로 돌아간다.
   * effect 로 동기화하지 않고 "어느 저장본에서 시작한 편집인가" 를 함께 들어 렌더 중에 판단한다.
   */
  const [edit, setEdit] = useState<{ from: MemberProfile; value: MemberProfile } | null>(null);
  const draft: MemberProfile = edit && edit.from === saved ? edit.value : saved;
  const setDraft = (update: (p: MemberProfile) => MemberProfile) => setEdit({ from: saved, value: update(draft) });
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const getOrders = useCallback(() => loadOrders(session.id), [session.id]);
  const orders = useSyncExternalStore(subscribeOrders, getOrders, getOrders);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dirty = PROFILE_FIELDS.some((f) => draft[f] !== saved[f]);

  const save = () => {
    saveMemberProfile(session.id, draft);
    setSavedAt(Date.now());
  };

  return createPortal(
    <div className="auth-modal" role="presentation" onClick={onClose}>
      <div className="auth-modal__card mypage" role="dialog" aria-modal="true" aria-label="내 정보" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="auth-modal__close" aria-label="닫기" onClick={onClose}>
          ×
        </button>

        <header className="mypage__head">
          <p className="auth__eyebrow">내 정보</p>
          <h2 className="auth__title">{session.name}</h2>
          <p className="mypage__email">{session.email}</p>
        </header>

        <section className="mypage__section">
          <h3>피부 정보</h3>
          <p className="mypage__lead">
            비슷한 피부 사용자의 반응을 추천에 반영하는 데 씁니다. 리뷰 필터의 "내 피부 타입만 보기" 와 상세페이지의 피부 타입 표시도
            이 값을 씁니다.
          </p>
          <div className="auth__profile-grid">
            {PROFILE_FIELDS.map((field: ProfileField) => (
              <label key={field} className="auth__field">
                <span>
                  {PROFILE_FIELD_KO[field]}
                  {PROFILE_RECOMMENDED.includes(field) ? <em className="auth__recommended">권장</em> : null}
                </span>
                <select
                  value={draft[field] ?? ''}
                  onChange={(e) => {
                    setSavedAt(null);
                    setDraft((p) => ({ ...p, [field]: e.target.value === '' ? null : e.target.value }));
                  }}
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
          <div className="mypage__actions">
            <button type="button" className="auth__submit mypage__save" disabled={!dirty} onClick={save}>
              {dirty ? '피부 정보 저장' : isEmptyProfile(saved) ? '아직 입력한 정보가 없습니다' : '저장됨'}
            </button>
            {savedAt ? <span className="mypage__saved">저장했습니다</span> : null}
          </div>
          <p className="mypage__note">이 브라우저에 저장됩니다. 서버 프로필 저장은 백엔드 API 가 열리면 이어집니다.</p>
        </section>

        <section className="mypage__section">
          <h3>주문 내역</h3>
          {orders.length === 0 ? (
            <p className="mypage__empty">이 브라우저에서 한 주문이 없습니다.</p>
          ) : (
            <ul className="mypage__orders">
              {orders.map((o) => (
                <li key={o.orderId} className="mypage__order">
                  <div className="mypage__order-head">
                    <span className="mypage__order-id">주문 {o.orderId.slice(0, 8)}</span>
                    <span className="mypage__order-when">{formatWhen(o.placed_at)}</span>
                  </div>
                  <div className="mypage__order-body">
                    <span>상품 {o.count}개</span>
                    <strong>{formatPrice(o.paid)}</strong>
                    <span className={`mypage__order-mode mypage__order-mode--${o.mode}`}>
                      {o.payment_method === 'kakaopay' ? '카카오페이 테스트 결제' : o.mode === 'backend' ? '서버 주문' : '테스트 주문'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mypage__note">서버 주문 목록 API 가 아직 없어 이 브라우저에서 한 주문만 보입니다.</p>
        </section>

        <footer className="mypage__foot">
          <button
            type="button"
            className="account__btn"
            onClick={() => {
              logout('MEMBER');
              onClose();
            }}
          >
            로그아웃
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
