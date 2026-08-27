import { useEffect, useState } from 'react';
import { clearHistory, getHistory, subscribe } from '../../lib/logger';
import type { LogEnvelope } from '../../types/log';

/**
 * 개발·QA 전용 로그 패널.
 *
 * 트리거가 의도한 순간에만 한 번씩 발생하는지 눈으로 확인하려고 만든다.
 * 콘솔만으로는 중복 발생이나 누락을 놓치기 쉽다.
 */
export default function LogPanel() {
  const [events, setEvents] = useState<LogEnvelope[]>(() => [...getHistory()]);
  const [open, setOpen] = useState(false);

  useEffect(() => subscribe((event) => setEvents((prev) => [event, ...prev].slice(0, 200))), []);

  return (
    <aside className={`log-panel${open ? ' is-open' : ''}`}>
      <button type="button" className="log-panel__toggle" onClick={() => setOpen((prev) => !prev)}>
        로그 {events.length}건 {open ? '▾' : '▴'}
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
