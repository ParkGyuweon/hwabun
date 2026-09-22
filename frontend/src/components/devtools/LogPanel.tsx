import { useEffect, useState } from 'react';
import { clearHistory, getHistory, isSuppressed, subscribe } from '../../lib/logger';
import type { LogEnvelope } from '../../types/log';

/**
 * 개발·QA·시연용 로그 창 (우하단). `?dev=1` 로 켠다 (lib/devtools).
 *
 * 트리거가 의도한 순간에만 한 번씩 발생하는지 눈으로 확인하려고 만들었고, 발표에서는 "고객이 움직일 때마다
 * 로그가 우르르 찍힌다" 를 보여 주는 자리다 (유림님 2026-09-22). 그래서
 *   - 켜지면 **펼친 채로** 시작한다 (전에는 접혀 있어 "로그 0건" 한 줄만 보였다)
 *   - 새 줄은 위에 꽂히며 잠깐 빛난다
 *   - 대시보드에 로그인한 브라우저(판매자 세션)라 서버로 안 나가는 상태면 그 사실을 머리에 적는다.
 *     이벤트는 여전히 여기까지는 온다 (logger.ts isSuppressed)
 */
export default function LogPanel() {
  const [events, setEvents] = useState<LogEnvelope[]>(() => [...getHistory()]);
  const [open, setOpen] = useState(true);
  const [suppressed, setSuppressed] = useState(() => isSuppressed());

  useEffect(
    () =>
      subscribe((event) => {
        setEvents((prev) => [event, ...prev].slice(0, 200));
        setSuppressed(isSuppressed());
      }),
    [],
  );

  return (
    <aside className={`log-panel${open ? ' is-open' : ''}`}>
      <button type="button" className="log-panel__toggle" onClick={() => setOpen((prev) => !prev)}>
        <span className="log-panel__live" aria-hidden="true" />
        고객 행동 로그 {events.length}건
        {suppressed ? <span className="log-panel__muted">판매자 로그인 중 · 화면에만 표시</span> : null}
        <span className="log-panel__caret">{open ? '▾' : '▴'}</span>
      </button>

      {open ? (
        <div className="log-panel__body">
          <div className="log-panel__actions">
            <button
              type="button"
              className="link-button"
              onClick={() => {
                clearHistory();
                setEvents([]);
              }}
            >
              비우기
            </button>
          </div>

          <ol className="log-panel__list">
            {events.length === 0 ? <li className="log-panel__empty">아직 기록이 없습니다. 화면을 움직여 보세요.</li> : null}
            {events.map((event) => (
              <li key={event.event_id}>
                <span className="log-panel__seq">#{event.sequence_no}</span>
                <span className="log-panel__name">{event.event_name}</span>
                <span className="log-panel__props">
                  {Object.entries(event.properties)
                    .map(([key, value]) => `${key}=${String(value)}`)
                    .join(' · ') || '—'}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </aside>
  );
}
