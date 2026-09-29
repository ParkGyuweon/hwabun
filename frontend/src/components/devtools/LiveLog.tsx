import { useEffect, useState } from 'react';
import { getHistory, isSuppressed, subscribe } from '../../lib/logger';
import type { EventName, LogEnvelope } from '../../types/log';
import '../../styles/live-log.css';

/**
 * 우하단 실시간 행동 기록 (2026-09-29 새로 만듦. 옛 LogPanel 은 09-28 뺐다).
 *
 * 발표에서 "고객이 움직이는 순간 기록이 찍힌다" 를 보여 주는 자리라 **시각과 행동 두 가지만** 크게 적는다.
 * JSON·id·건수는 없다. 시각은 벽시계 `HH:MM:SS` 에 **초만** 밝게 — "12초 전" 처럼 흐르는 값은
 * 매초 글자가 바뀌어 눈이 쫓기 바쁘고, 벽시계는 찍힌 순간 고정돼 방금 줄과 이전 줄의 간격이 그대로 읽힌다.
 *
 *   - 접으면 동그란 점 버튼 하나. 건수 배지는 없다 (유림님 2026-09-23 — 숫자가 계속 올라가면 정신없다)
 *   - 판매자·운영자 세션(서버로 안 보냄)이어도 이벤트는 여기까지 온다 → 점이 회색, "전송 안 함" 표시
 *   - 좁은 화면(480px 미만)은 접힌 채 시작한다
 */

const MAX_ROWS = 50;

const EVENT_LABEL: Record<EventName, string> = {
  login: '로그인',
  session_start: '방문 시작',
  page_view: '화면 열기',
  product_view: '상품 보기',
  product_impression: '상품 노출',
  navigation_click: '이동',
  product_click: '상품 클릭',
  section_view: '구역 보기',
  section_dwell: '머무름',
  accordion_toggle: '펼쳐 보기',
  recommendation_impression: '추천 노출',
  recommendation_click: '추천 클릭',
  banner_impression: '배너 노출',
  banner_click: '배너 클릭',
  wishlist_toggle: '찜',
  add_to_cart: '장바구니 담기',
  view_cart: '장바구니 열기',
  begin_checkout: '결제 시작',
  purchase: '구매',
  purchase_reason_select: '구매 이유',
  payment_failed: '결제 실패',
  exit_summary: '나가기',
  scroll_depth: '스크롤',
  impression_dwell: '노출 머무름',
  recommendation_snapshot: '추천 갱신',
  media_view: '사진 보기',
  quick_look: '미리보기',
  quick_look_close: '미리보기 닫기',
  remove_from_cart: '장바구니 빼기',
  variant_select: '옵션 선택',
  quantity_change: '수량 변경',
  review_filter_apply: '리뷰 거르기',
  review_expand: '리뷰 펼치기',
  ingredient_view_mode_change: '성분 보기 전환',
  sort_change: '정렬 변경',
  filter_change: '필터 변경',
  scroll_pause: '멈춰 읽기',
  scroll_backtrack: '다시 올려 보기',
  text_selection: '글 선택',
  text_copy: '글 복사',
  hover_dwell: '마우스 머무름',
  rage_click: '연타',
  dead_click: '헛클릭',
};

/** 체류가 있는 이벤트는 "머무름 4.2초", 스크롤은 "스크롤 40%" 처럼 숫자 하나만 붙인다 */
function detail(event: LogEnvelope): string | null {
  const props = event.properties;
  if (event.event_name === 'scroll_depth' && typeof props.depth_percent === 'number') {
    return `${Math.round(props.depth_percent)}%`;
  }
  if (typeof props.dwell_ms === 'number' && props.dwell_ms > 0) {
    return `${(props.dwell_ms / 1000).toFixed(1)}초`;
  }
  return null;
}

function clock(iso: string): { hm: string; ss: string } {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { hm: '--:--', ss: '--' };
  const pad = (n: number) => String(n).padStart(2, '0');
  return { hm: `${pad(d.getHours())}:${pad(d.getMinutes())}`, ss: pad(d.getSeconds()) };
}

function startsOpen(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return !window.matchMedia('(max-width: 479px)').matches;
}

export default function LiveLog() {
  const [events, setEvents] = useState<LogEnvelope[]>(() => getHistory().slice(0, MAX_ROWS));
  const [open, setOpen] = useState(startsOpen);
  const [suppressed, setSuppressed] = useState(() => isSuppressed());

  useEffect(
    () =>
      subscribe((event) => {
        setEvents((prev) => [event, ...prev].slice(0, MAX_ROWS));
        setSuppressed(isSuppressed());
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
        <ol className="live-log__list" aria-live="polite">
          {events.map((event) => {
            const t = clock(event.occurred_at);
            const extra = detail(event);
            return (
              <li key={event.event_id} className="live-log__row">
                <time className="live-log__time" dateTime={event.occurred_at}>
                  <span className="live-log__hm">{t.hm}:</span>
                  <span className="live-log__ss">{t.ss}</span>
                </time>
                <span className="live-log__event">
                  <span className="live-log__label">
                    {EVENT_LABEL[event.event_name] ?? event.event_name}
                    {extra ? <span className="live-log__extra"> {extra}</span> : null}
                  </span>
                  <span className="live-log__raw">{event.event_name}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
