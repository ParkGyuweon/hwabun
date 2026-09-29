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
import { fetchBackendOrders } from '../../lib/shopApi';
import { saveMemberProfileServer, useSyncMemberProfile } from '../../lib/memberProfileApi';
import WriteReview from '../review/WriteReview';
import { useBackdropClose } from '../../hooks/useBackdropClose';
import type { BackendOrder } from '../../lib/shopApi';

/**
 * 마이페이지 · 쇼핑몰의 기본 요소 중 빠져 있던 것 (2026-09-11).
 *
 * 세 덩이만 둔다. 내 정보(이메일·닉네임) · 피부 정보(가입 때 받은 4개, 여기서 고침) · 주문 내역.
 * 피부 정보는 "가입에서 건너뛸 수 있게 하되 나중에 채우고 바꿀 수 있어야 한다" (AI 요청 §1.2) 의 그 자리다.
 *
 * 피부 정보는 **서버가 정본**이다 (2026-09-21, `/api/members/me/profile`). 열 때 서버 값을 받아 브라우저 사본에 비추고,
 * 저장은 서버에 먼저 쓴 뒤 사본을 맞춘다. 서버가 없을 때만 사본에 저장하고 그렇다고 적는다.
 * 주문 내역은 백엔드의 결제 완료 주문만 조회한다.
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
  /** 저장 결과. 서버에 썼는지, 이 브라우저에만 남았는지 사장님이 알아야 한다 */
  const [saveState, setSaveState] = useState<{ at: number; where: 'server' | 'local'; reason?: string } | null>(null);
  const [saving, setSaving] = useState(false);
  // 열 때 서버 프로필을 받아 사본에 비춘다. 가입 때 보낸 값이 여기서 처음 보인다
  useSyncMemberProfile(session.id);

  const [orders, setOrders] = useState<BackendOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [ordersError, setOrdersError] = useState<string | null>(null);

  /** 리뷰를 쓰면 그 품목의 `reviewed` 가 바뀌므로 목록을 다시 받는다 */
  const [ordersNonce, setOrdersNonce] = useState(0);
  /** 주문 목록 페이지. 5건씩 — 다 펼치면 로그아웃이 화면 밖으로 밀려난다 (2026-09-18) */
  const [page, setPage] = useState(1);
  const reloadOrders = useCallback(() => setOrdersNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    void fetchBackendOrders().then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setOrders(result.orders);
        setPage(1);
        setOrdersError(null);
      } else {
        setOrders([]);
        setOrdersError(result.reason);
      }
      setOrdersLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [session.id, ordersNonce]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dirty = PROFILE_FIELDS.some((f) => draft[f] !== saved[f]);
  // 주문 번호 같은 글자를 긁어 복사하다 창이 닫히지 않게 (useBackdropClose)
  const backdrop = useBackdropClose(onClose);

  const save = async () => {
    setSaving(true);
    const result = await saveMemberProfileServer(draft);
    if (result.ok) {
      saveMemberProfile(session.id, result.profile);
      setSaveState({ at: Date.now(), where: 'server' });
    } else {
      // 서버가 없으면 이 브라우저에만. 다음에 서버가 살아나면 useSyncMemberProfile 이 올린다
      saveMemberProfile(session.id, draft);
      setSaveState({ at: Date.now(), where: 'local', reason: result.reason });
    }
    setSaving(false);
  };

  return createPortal(
    <div className="auth-modal" role="presentation" {...backdrop}>
      <div className="auth-modal__card mypage" role="dialog" aria-modal="true" aria-label="내 정보">
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
                    setSaveState(null);
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
            <button type="button" className="auth__submit mypage__save" disabled={!dirty || saving} onClick={() => void save()}>
              {saving ? '저장 중' : dirty ? '피부 정보 저장' : isEmptyProfile(saved) ? '아직 입력한 정보가 없습니다' : '저장됨'}
            </button>
            {saveState ? (
              <span className="mypage__saved">
                {saveState.where === 'server' ? '저장했습니다' : '서버에 연결되지 않아 이 브라우저에만 저장했습니다'}
              </span>
            ) : null}
          </div>
          <p className="mypage__note">
            내 계정에 저장되어 어느 기기에서 로그인해도 같이 보입니다. 저장하면 피부 정보 수집·이용에 동의한 것으로 봐요.
          </p>
        </section>

        <section className="mypage__section">
          <h3>주문 내역</h3>
          {ordersLoading ? (
            <p className="mypage__empty">주문 내역을 불러오는 중입니다.</p>
          ) : ordersError ? (
            <p className="mypage__empty">주문 내역을 불러오지 못했습니다. {ordersError}</p>
          ) : orders.length === 0 ? (
            <p className="mypage__empty">결제 완료된 주문이 없습니다.</p>
          ) : (
            <ul className="mypage__orders">
              {orders.slice((page - 1) * ORDERS_PER_PAGE, page * ORDERS_PER_PAGE).map((o) => (
                <li key={o.orderId} className="mypage__order">
                  <div className="mypage__order-head">
                    <span className="mypage__order-id">주문 {o.orderId.slice(0, 8)}</span>
                    <span className="mypage__order-when">{formatWhen(o.paidAt ?? o.createdAt)}</span>
                  </div>
                  <div className="mypage__order-body">
                    <span>상품 {o.itemCount}개</span>
                    <strong>{Math.round(o.paidAmount ?? o.totalAmount).toLocaleString('ko-KR')}원</strong>
                    <span className="mypage__order-mode mypage__order-mode--backend">
                      {o.paymentProvider === 'PORTONE_TEST' ? '카카오페이 테스트 결제' : '서버 테스트 결제'}
                    </span>
                  </div>

                  {/*
                    품목마다 리뷰 칸. 리뷰는 산 사람만 쓸 수 있고 그 판정은 서버가 한다 —
                    여기서는 "무엇을 리뷰할 수 있는지" 를 보여 줄 뿐이다.
                  */}
                  {o.items.length > 0 ? (
                    <ul className="mypage__order-items">
                      {o.items.map((item) => (
                        <li key={item.orderItemId} className="mypage__order-item">
                          <div className="mypage__order-item-name">
                            {item.productName}
                            {item.variantLabel ? <span className="mypage__order-item-variant">{item.variantLabel}</span> : null}
                            <span className="mypage__order-item-qty">{item.quantity}개</span>
                          </div>
                          <WriteReview item={item} onWritten={reloadOrders} />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {orders.length > ORDERS_PER_PAGE ? (
            <nav className="mypage__pager" aria-label="주문 페이지">
              <button
                type="button"
                className="mypage__pager-btn"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="이전"
              >
                ‹
              </button>
              {pageNumbers(page, Math.ceil(orders.length / ORDERS_PER_PAGE)).map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`mypage__pager-btn${n === page ? ' is-current' : ''}`}
                  aria-current={n === page ? 'page' : undefined}
                  onClick={() => setPage(n)}
                >
                  {n}
                </button>
              ))}
              <button
                type="button"
                className="mypage__pager-btn"
                disabled={page >= Math.ceil(orders.length / ORDERS_PER_PAGE)}
                onClick={() => setPage((p) => Math.min(Math.ceil(orders.length / ORDERS_PER_PAGE), p + 1))}
                aria-label="다음"
              >
                ›
              </button>
            </nav>
          ) : null}
          <p className="mypage__note">
            백엔드에서 확인된 결제 완료 주문만 표시됩니다.
            {orders.length > ORDERS_PER_PAGE
              ? ` 전체 ${orders.length}건 중 ${(page - 1) * ORDERS_PER_PAGE + 1}–${Math.min(orders.length, page * ORDERS_PER_PAGE)}건.`
              : ''}
          </p>
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

/** 한 페이지에 보이는 주문 수 */
const ORDERS_PER_PAGE = 5;

/** 현재 페이지를 가운데 둔 번호 다섯 개. 페이지가 다섯 미만이면 있는 만큼 */
function pageNumbers(current: number, total: number): number[] {
  const span = Math.min(5, total);
  const start = Math.max(1, Math.min(current - Math.floor(span / 2), total - span + 1));
  return Array.from({ length: span }, (_, i) => start + i);
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
