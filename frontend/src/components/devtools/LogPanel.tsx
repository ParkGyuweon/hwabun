import { useEffect, useState } from 'react';
import { clearHistory, getHistory, isSuppressed, subscribe } from '../../lib/logger';
import type { LogEnvelope } from '../../types/log';

/**
 * 개발·QA·시연용 로그 창 (우하단). 쇼핑몰에 늘 뜬다 (2026-09-23, 전에는 `?dev=1` 일 때만).
 *
 * 트리거가 의도한 순간에만 한 번씩 발생하는지 눈으로 확인하려고 만들었고, 발표에서는 "고객이 움직일 때마다
 * 로그가 우르르 찍힌다" 를 보여 주는 자리다 (유림님 2026-09-22). 그래서
 *   - 켜지면 **펼친 채로** 시작한다 (전에는 접혀 있어 "로그 0건" 한 줄만 보였다)
 *   - 새 줄은 위에 꽂히며 잠깐 빛난다
 *   - 대시보드에 로그인한 브라우저(판매자 세션)라 서버로 안 나가는 상태면 그 사실을 머리에 적는다.
 *     이벤트는 여전히 여기까지는 온다 (logger.ts isSuppressed)
 *   - 접으면 막대가 아니라 **동그란 버튼 하나**만 남는다. 건수는 그 위 작은 배지 (유림님 2026-09-23 — 접어도 화면을 가렸다)
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
    <aside className={`log-panel${open ? ' is-open' : ' is-collapsed'}`}>
      {open ? (
        <button type="button" className="log-panel__toggle" onClick={() => setOpen(false)} aria-expanded="true">
          <span className="log-panel__live" aria-hidden="true" />
          고객 행동 로그 {events.length}건
          {suppressed ? <span className="log-panel__muted">판매자 로그인 중 · 화면에만 표시</span> : null}
          <span className="log-panel__caret">▾</span>
        </button>
      ) : (
        <button
          type="button"
          className="log-panel__toggle log-panel__toggle--round"
          onClick={() => setOpen(true)}
          aria-expanded="false"
          aria-label={`고객 행동 로그 ${events.length}건 펼치기${suppressed ? ' · 판매자 로그인 중이라 화면에만 표시' : ''}`}
          title={suppressed ? '고객 행동 로그 · 판매자 로그인 중이라 서버로 안 보냄' : '고객 행동 로그 펼치기'}
        >
          <span className="log-panel__live" aria-hidden="true" />
          {/* 판매자 로그인 중(서버로 안 나감)이면 배지를 회색으로 */}
          <span className={`log-panel__count${suppressed ? ' is-muted' : ''}`} aria-hidden="true">
            {events.length > 99 ? '99+' : events.length}
          </span>
        </button>
      )}

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
