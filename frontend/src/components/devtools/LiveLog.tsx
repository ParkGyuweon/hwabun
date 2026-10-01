import { useEffect, useState } from 'react';
import { getHistory, subscribe } from '../../lib/logger';
import type { LogEnvelope } from '../../types/log';
import '../../styles/live-log.css';

/**
 * 우하단 실시간 로그 기록 (2026-09-29 새로 만듦. 옛 LogPanel 은 09-28 뺐다).
 *
 * 발표에서 "고객이 움직이는 순간 기록이 찍힌다" 를 보여 주는 자리라 **시각 · 이벤트 이름 두 가지만** 크게 적는다.
 * 이벤트 이름은 실제 로그에 찍히는 원래 이름(`product_click`) 그대로다. JSON·id·건수는 없다.
 *
 *   - 시각은 로그 콘솔처럼 `09:21:15.482` (밀리초까지). 수집 서버로 가는 occurred_at 과 같은 값이다
 *     (2026-09-30 유림님. 09-29 에는 "0.4초 전" 이었다)
 *   - 화면에는 최근 5줄만 보인다 — 카드가 작아야 상품·결제 버튼을 가리지 않는다. 50개는 기억해 둔다
 *   - 로그인한 고객에게만 그린다 (App.tsx). "전송 안 함" 같은 상태 표시는 두지 않는다 (2026-09-30)
 *   - 접으면 동그란 점 버튼 하나. 건수 배지는 없다 (유림님 2026-09-23 — 숫자가 계속 올라가면 정신없다)
 *   - 좁은 화면(480px 미만)은 접힌 채 시작한다
 */

const MAX_ROWS = 50;
/** 한 번에 보이는 줄 수 */
const VISIBLE_ROWS = 5;

/** 로그 콘솔처럼 시:분:초.밀리초 (브라우저 시간대) */
function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

function startsOpen(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return !window.matchMedia('(max-width: 479px)').matches;
}

export default function LiveLog() {
  const [events, setEvents] = useState<LogEnvelope[]>(() => getHistory().slice(0, MAX_ROWS));
  const [open, setOpen] = useState(startsOpen);

  useEffect(
    () =>
      subscribe((event) => {
        setEvents((prev) => [event, ...prev].slice(0, MAX_ROWS));
      }),
    [],
  );

  if (!open) {
    return (
      <button
        type="button"
        className="live-log__fab"
        onClick={() => setOpen(true)}
        aria-expanded="false"
        aria-label="실시간 로그 기록 펼치기"
        title="실시간 로그 기록"
      >
        <span className="live-log__dot" aria-hidden="true" />
      </button>
    );
  }

  return (
    <aside className="live-log" aria-label="실시간 로그 기록">
      <header className="live-log__head">
        <span className="live-log__dot" aria-hidden="true" />
        <span className="live-log__title">실시간 로그 기록</span>
        <button
          type="button"
          className="live-log__close"
          onClick={() => setOpen(false)}
          aria-expanded="true"
          aria-label="실시간 로그 기록 접기"
        >
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </header>

      {events.length === 0 ? (
        <p className="live-log__empty">화면을 움직이면 여기에 찍힙니다</p>
      ) : (
        <ol className="live-log__list">
          {events.slice(0, VISIBLE_ROWS).map((event) => (
            <li key={event.event_id} className="live-log__row">
              <time className="live-log__time" dateTime={event.occurred_at}>
                {clock(event.occurred_at)}
              </time>
              <span className="live-log__raw">{event.event_name}</span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
