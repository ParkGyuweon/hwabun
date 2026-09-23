import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '../../hooks/useAuth';
import type { AccountRole } from '../../lib/auth';
import { fetchNotifications, fetchUnreadCount, markAllNotificationsRead, markNotificationRead } from '../../lib/shopApi';
import type { AppNotification } from '../../lib/shopApi';
import '../../styles/auth.css';

/**
 * 인앱 알림함 — 헤더의 종 아이콘, 안 읽은 수 배지, 최근 알림 20개 패널.
 *
 * 브라우저 푸시가 아니다. 정기 polling 도 하지 않는다 (백엔드 요청 2026-09-18). 서버를 보는 때는 셋뿐이다.
 *   1. 로그인 세션이 복원된 직후
 *   2. 탭이 다시 보이게 됐을 때 (visibilitychange → visible)
 *   3. 종을 눌러 패널을 열 때 — 이때는 안 읽은 수와 목록을 둘 다 받는다
 *
 * 회원과 판매자가 같은 UI 를 쓴다. 누가 어떤 알림을 받는지는 서버가 거른다 — 회원은 자기 의견의 확인·답변·반영,
 * 판매자는 새 의견. 알림을 누르면 `onOpen` 이 화면을 옮기고(회원은 상품 상세, 판매자는 피드백 화면) 읽음으로 남긴다.
 *
 * 로그인 전에는 아무것도 그리지 않는다. 받아 둔 목록·배지는 세션 id 에 묶어 두어, 재로그인하면 이전 사람 것이 안 보인다.
 *
 * `placement="above"` 는 대시보드 사이드바 발 부분용이다. 사이드바는 `overflow-y: auto` 에 `backdrop-filter` 까지 있어
 * 안에 둔 패널은 absolute 든 fixed 든 사이드바 폭(232px)에서 잘렸다 (2026-09-23 은솔님 제보). 그래서 패널을 body 로
 * 빼서(portal) 종 위치에 맞춰 화면 기준으로 띄운다 — 종 왼쪽 끝에 맞추고 위로 연다.
 */
export default function NotificationBell({
  role,
  onOpen,
  placement = 'below',
}: {
  role: AccountRole;
  /** 알림을 눌렀을 때. 화면 이동은 호출부가 정한다 */
  onOpen: (n: AppNotification) => void;
  /** below: 종 아래 오른쪽 맞춤(헤더). above: 종 위로, body 에 띄워 부모의 잘림을 피한다(사이드바) */
  placement?: 'below' | 'above';
}) {
  const session = useAuth(role);
  const sessionKey = session?.id ?? null;

  const [state, setState] = useState<{ key: string | null; unread: number; items: AppNotification[] | null; open: boolean; failed: boolean }>({
    key: null,
    unread: 0,
    items: null,
    open: false,
    failed: false,
  });
  // 세션이 바뀌었으면 화면은 빈 상태로 읽는다. 상태 초기화를 effect 에서 하지 않는다 — 렌더 중에 파생한다
  const mine = state.key === sessionKey ? state : { key: sessionKey, unread: 0, items: null, open: false, failed: false };
  const patch = (p: Partial<typeof mine>) => setState((cur) => ({ ...(cur.key === sessionKey ? cur : { key: sessionKey, unread: 0, items: null, open: false, failed: false }), ...p, key: sessionKey }));
  const rootRef = useRef<HTMLDivElement | null>(null);
  const bellRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [floatStyle, setFloatStyle] = useState<CSSProperties | null>(null);

  // above: 열려 있는 동안 종 위치를 따라간다. 사이드바가 스크롤되거나 창 크기가 바뀌면 다시 잰다
  useLayoutEffect(() => {
    if (placement !== 'above' || !mine.open) return;
    const place = () => {
      const r = bellRef.current?.getBoundingClientRect();
      if (!r) return;
      const gap = 8;
      const edge = 16;
      setFloatStyle({
        position: 'fixed',
        top: 'auto',
        right: 'auto',
        left: r.left,
        bottom: window.innerHeight - r.top + gap,
        width: Math.max(240, Math.min(360, window.innerWidth - r.left - edge)),
        maxHeight: Math.max(160, r.top - gap - edge),
      });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [placement, mine.open]);

  const refreshCount = useCallback(async () => {
    const n = await fetchUnreadCount(role);
    if (n !== null) setState((cur) => (cur.key === sessionKey ? { ...cur, unread: n } : { key: sessionKey, unread: n, items: null, open: false, failed: false }));
  }, [role, sessionKey]);

  // 1. 세션 복원 직후
  useEffect(() => {
    if (!sessionKey) return;
    void refreshCount();
  }, [sessionKey, refreshCount]);

  // 2. 탭이 다시 보일 때
  useEffect(() => {
    if (!sessionKey) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refreshCount();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [sessionKey, refreshCount]);

  // 바깥을 누르거나 Esc 면 닫는다
  useEffect(() => {
    if (!mine.open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      patch({ open: false });
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') patch({ open: false });
    };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
    // patch 는 sessionKey 만 잡는 얇은 함수라 의존성에서 뺀다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mine.open, sessionKey]);

  // 3. 종을 눌러 열 때 — 안 읽은 수와 목록을 둘 다
  const toggle = async () => {
    if (mine.open) {
      patch({ open: false });
      return;
    }
    patch({ open: true, failed: false });
    const [list] = await Promise.all([fetchNotifications(role, 20), refreshCount()]);
    if (list === null) patch({ failed: true });
    else patch({ items: list });
  };

  const openOne = async (n: AppNotification) => {
    patch({ open: false });
    onOpen(n);
    if (n.readAt === null) {
      // 화면부터 옮기고 읽음은 뒤에. 읽음 처리가 실패해도 이동은 된 것이다
      const at = await markNotificationRead(role, n.notificationId);
      setState((cur) =>
        cur.key === sessionKey
          ? {
              ...cur,
              unread: Math.max(0, cur.unread - 1),
              items: cur.items ? cur.items.map((x) => (x.notificationId === n.notificationId ? { ...x, readAt: at ?? new Date().toISOString() } : x)) : cur.items,
            }
          : cur,
      );
    }
  };

  const readAll = async () => {
    const ok = await markAllNotificationsRead(role);
    if (ok === null) return;
    const now = new Date().toISOString();
    setState((cur) =>
      cur.key === sessionKey
        ? { ...cur, unread: 0, items: cur.items ? cur.items.map((x) => (x.readAt === null ? { ...x, readAt: now } : x)) : cur.items }
        : cur,
    );
  };

  if (!session) return null;

  const { unread, open, items, failed } = mine;
  const panel = (
    <div
      ref={panelRef}
      className={`notif__panel${placement === 'above' ? ' notif__panel--float' : ''}`}
      style={placement === 'above' ? (floatStyle ?? undefined) : undefined}
      role="dialog"
      aria-label="알림"
    >
      <div className="notif__head">
        <strong>알림</strong>
        {items && items.some((x) => x.readAt === null) ? (
          <button type="button" className="notif__readall" onClick={() => void readAll()}>
            모두 읽음
          </button>
        ) : null}
      </div>
      {failed ? (
        <p className="notif__empty">알림을 읽지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>
      ) : items === null ? (
        <p className="notif__empty">알림을 받는 중입니다.</p>
      ) : items.length === 0 ? (
        <p className="notif__empty">아직 알림이 없습니다.</p>
      ) : (
        <ul className="notif__list">
          {items.map((n) => (
            <li key={n.notificationId}>
              <button
                type="button"
                className={`notif__item${n.readAt === null ? ' is-unread' : ''}`}
                onClick={() => void openOne(n)}
              >
                <span className="notif__title">{n.title}</span>
                <span className="notif__body">{n.body}</span>
                <span className="notif__when">{formatWhen(n.createdAt)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <div className="notif" ref={rootRef}>
      <button
        ref={bellRef}
        type="button"
        className={`notif__bell${unread > 0 ? ' has-unread' : ''}`}
        aria-label={unread > 0 ? `알림 ${unread}개 안 읽음` : '알림'}
        aria-expanded={open}
        onClick={() => void toggle()}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 22a2.2 2.2 0 0 0 2.2-2.2H9.8A2.2 2.2 0 0 0 12 22Zm6-6V11a6 6 0 0 0-4.5-5.8V4.5a1.5 1.5 0 0 0-3 0v.7A6 6 0 0 0 6 11v5l-2 2v1h16v-1l-2-2Z"
            fill="currentColor"
          />
        </svg>
        {unread > 0 ? <span className="notif__badge">{unread > 99 ? '99+' : unread}</span> : null}
      </button>

      {open ? (placement === 'above' ? (floatStyle ? createPortal(panel, document.body) : null) : panel) : null}
    </div>
  );
}

/** "9/18 17:10". 연도는 안 적는다 — 알림함은 최근 것만 있다 */
function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
