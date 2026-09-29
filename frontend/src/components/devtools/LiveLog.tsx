import { useEffect, useState } from 'react';
import { getHistory, isSuppressed, subscribe } from '../../lib/logger';
import type { LogEnvelope } from '../../types/log';
import '../../styles/live-log.css';

/**
 * 우하단 실시간 행동 기록 (2026-09-29 새로 만듦. 옛 LogPanel 은 09-28 뺐다).
 *
 * 발표에서 "고객이 움직이는 순간 기록이 찍힌다" 를 보여 주는 자리라 **몇 초 전 · 이벤트 이름 두 가지만** 크게 적는다.
 * 이벤트 이름은 실제 로그에 찍히는 원래 이름(`product_click`) 그대로다. JSON·id·건수는 없다.
 * 시간은 "0.4초 전" 처럼 흐르는 값 — 방금 찍혔다는 느낌이 가장 강해서 팀이 골랐다 (2026-09-29 박규원·이은솔 님).
 *
 *   - 접으면 동그란 점 버튼 하나. 건수 배지는 없다 (유림님 2026-09-23 — 숫자가 계속 올라가면 정신없다)
 *   - 판매자·운영자 세션(서버로 안 보냄)이어도 이벤트는 여기까지 온다 → 점이 회색, "전송 안 함" 표시
 *   - 좁은 화면(480px 미만)은 접힌 채 시작한다
 */

const MAX_ROWS = 50;
/** "몇 초 전" 을 다시 그리는 간격. 0.1초 단위로 보이니 이보다 느리면 숫자가 뚝뚝 끊긴다 */
const TICK_MS = 100;

/** 10초 안은 0.1초 단위, 1분 안은 초, 그 뒤는 분 */
function ago(iso: string, now: number): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const sec = Math.max(0, (now - t) / 1000);
  if (sec < 10) return `${sec.toFixed(1)}초 전`;
  if (sec < 60) return `${Math.floor(sec)}초 전`;
  return `${Math.floor(sec / 60)}분 전`;
}

function startsOpen(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return !window.matchMedia('(max-width: 479px)').matches;
}

export default function LiveLog() {
  const [events, setEvents] = useState<LogEnvelope[]>(() => getHistory().slice(0, MAX_ROWS));
  const [open, setOpen] = useState(startsOpen);
  const [suppressed, setSuppressed] = useState(() => isSuppressed());
  const [now, setNow] = useState(() => Date.now());

  useEffect(
    () =>
      subscribe((event) => {
        setEvents((prev) => [event, ...prev].slice(0, MAX_ROWS));
        setSuppressed(isSuppressed());
      }),
    [],
  );

  // 펼쳐져 있을 때만 시계를 돌린다
  useEffect(() => {
    if (!open) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, [open]);

  if (!open) {
    return (
      <button
        type="button"
        className="live-log__fab"
        onClick={() => setOpen(true)}
        aria-expanded="false"
        aria-label={`실시간 행동 기록 펼치기${suppressed ? ' · 전송 안 함' : ''}`}
        title={suppressed ? '실시간 행동 기록 · 판매자 로그인 중이라 전송 안 함' : '실시간 행동 기록'}
      >
        <span className={`live-log__dot${suppressed ? ' is-muted' : ''}`} aria-hidden="true" />
      </button>
    );
  }

  return (
    <aside className="live-log" aria-label="실시간 행동 기록">
      <header className="live-log__head">
        <span className={`live-log__dot${suppressed ? ' is-muted' : ''}`} aria-hidden="true" />
        <span className="live-log__title">실시간 행동 기록</span>
        {suppressed ? <span className="live-log__hint">전송 안 함</span> : null}
        <button
          type="button"
          className="live-log__close"
          onClick={() => setOpen(false)}
          aria-expanded="true"
          aria-label="실시간 행동 기록 접기"
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
          {events.map((event) => (
            <li key={event.event_id} className="live-log__row">
              <time className="live-log__time" dateTime={event.occurred_at}>
                {ago(event.occurred_at, now)}
              </time>
              <span className="live-log__raw">{event.event_name}</span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
