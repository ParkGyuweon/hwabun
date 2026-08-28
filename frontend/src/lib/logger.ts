import { EVENT_INTENT, SCHEMA_VERSION } from '../types/log';
import type { ActorType, EventName, LogEnvelope, PageType } from '../types/log';

/**
 * 프론트 전역 로거.
 *
 * 화면 코드는 track() 하나만 호출한다.
 * 지금은 콘솔과 인메모리 버퍼에만 쌓고, 수집 API가 확정되면 flush() 내부만 교체하면 된다.
 *
 * 컴포넌트가 각자 API 를 호출하면 공통 필드 누락과 중복 전송을 막기 어려워서
 * 발생 지점과 전송 지점을 분리해 둔다.
 */

interface LoggerContext {
  personaId: string | null;
  pageType: PageType;
  productId: string | null;
  actorType: ActorType;
  environment: string;
}

type Listener = (event: LogEnvelope) => void;

const BATCH_SIZE = 20;
const FLUSH_INTERVAL_MS = 5000;
/** 개발용 패널에서 되돌아볼 최근 이벤트 보관 개수 */
const HISTORY_LIMIT = 200;

function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

let context: LoggerContext = {
  personaId: null,
  pageType: 'product_detail',
  productId: null,
  actorType: 'user',
  environment: 'local',
};

let sessionId = createId();
let pageViewId = createId();
let sequenceNo = 0;

const queue: LogEnvelope[] = [];
const history: LogEnvelope[] = [];
const listeners = new Set<Listener>();

let flushTimer: number | undefined;

/**
 * 한 번만 발생해야 하는 이벤트의 중복 방지 키 저장소.
 * 스크롤을 위아래로 반복해도 section_view 가 다시 찍히지 않게 한다.
 */
const firedOnceKeys = new Set<string>();

export function setLoggerContext(patch: Partial<LoggerContext>): void {
  context = { ...context, ...patch };
}

/**
 * 이미 시작한 세션·페이지 조회의 키.
 *
 * StrictMode 는 개발 중 effect 를 두 번 실행한다. 그래서 호출하는 쪽에 가드가 없으면
 * `session_start` 와 `page_view` 가 각각 두 번 찍힌다. 단순히 로그가 지저분해지는
 * 문제가 아니다. `startPageView` 가 `firedOnceKeys` 를 비우기 때문에, 두 번째 호출이
 * 1회성 이벤트의 중복 방지 기록까지 지워서 `scroll_depth` 같은 것도 다시 찍힌다.
 *
 * 컴포넌트마다 가드를 두는 대신 여기서 막는다. 호출을 몇 번 하든
 * **상태가 실제로 바뀔 때만** 이벤트가 나가는 것을 로거가 보장한다.
 */
const NOT_STARTED = Symbol('not-started');
let startedSessionKey: string | null | typeof NOT_STARTED = NOT_STARTED;
let startedPageViewKey: string | null | typeof NOT_STARTED = NOT_STARTED;

/** 페르소나가 바뀌면 새 방문으로 취급한다 */
export function startSession(personaId: string | null): void {
  if (startedSessionKey === personaId) return;
  startedSessionKey = personaId;

  sessionId = createId();
  sequenceNo = 0;
  firedOnceKeys.clear();
  setLoggerContext({ personaId });
  track('session_start', { entry_page: context.pageType });
}

/**
 * 페이지(또는 상품)가 바뀔 때마다 호출한다.
 *
 * `navigationSource` 로 **어떻게 이 화면에 왔는지**를 남긴다.
 * 브라우저 뒤로가기로 온 것과 화면 안 링크로 온 것은 다른 신호다.
 * 다만 뒤로가기 자체는 좌절이 아니라 정상적인 탐색이므로 감점하지 않는다.
 */
export function startPageView(productId: string | null, navigationSource = 'in_app'): void {
  if (startedPageViewKey === productId) return;
  startedPageViewKey = productId;

  pageViewId = createId();
  firedOnceKeys.clear();
  setLoggerContext({ productId });
  track('page_view', { product_id: productId, navigation_source: navigationSource });
}

export function track(eventName: EventName, properties: Record<string, unknown> = {}): void {
  sequenceNo += 1;

  const event: LogEnvelope = {
    schema_version: SCHEMA_VERSION,
    event_id: createId(),
    event_name: eventName,
    // 분석하는 쪽이 이벤트 이름마다 의미를 다시 정하지 않도록 발생 시점에 실어 보낸다
    intent: EVENT_INTENT[eventName],
    occurred_at: new Date().toISOString(),

    persona_id: context.personaId,
    session_id: sessionId,
    page_view_id: pageViewId,
    sequence_no: sequenceNo,

    page_type: context.pageType,
    product_id: context.productId,
    actor_type: context.actorType,
    environment: context.environment,

    properties,
  };

  queue.push(event);

  history.unshift(event);
  if (history.length > HISTORY_LIMIT) {
    history.length = HISTORY_LIMIT;
  }

  for (const listener of listeners) {
    listener(event);
  }

  // 수집 API 연결 전까지의 임시 싱크
  console.info(`[log] ${eventName}`, event);

  if (queue.length >= BATCH_SIZE) {
    flush();
  } else {
    scheduleFlush();
  }
}

/**
 * 같은 키로는 한 번만 발생시킨다.
 * section_view, scroll_depth 처럼 페이지 방문당 1회여야 하는 이벤트에 사용한다.
 */
export function trackOnce(
  key: string,
  eventName: EventName,
  properties: Record<string, unknown> = {},
): boolean {
  if (firedOnceKeys.has(key)) {
    return false;
  }
  firedOnceKeys.add(key);
  track(eventName, properties);
  return true;
}

function scheduleFlush(): void {
  if (flushTimer !== undefined) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = undefined;
    flush();
  }, FLUSH_INTERVAL_MS);
}

/**
 * 배치 전송 지점.
 *
 * 수집 API 가 확정되면 이 함수 안에서 POST /events/batch 를 호출하면 된다.
 * 게임/화면 응답이 로그 저장을 기다리지 않도록 반드시 비동기로 유지한다.
 */
export function flush(useBeacon = false): void {
  if (queue.length === 0) return;

  const batch = queue.splice(0, queue.length);

  if (flushTimer !== undefined) {
    window.clearTimeout(flushTimer);
    flushTimer = undefined;
  }

  // TODO: 수집 API 확정 후 교체
  // const body = JSON.stringify({ events: batch });
  // if (useBeacon) navigator.sendBeacon('/api/events/batch', body);
  // else fetch('/api/events/batch', { method: 'POST', body, keepalive: true });
  console.debug(`[log] flush ${batch.length}건${useBeacon ? ' (beacon)' : ''}`, batch);
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getHistory(): LogEnvelope[] {
  return history;
}

export function clearHistory(): void {
  history.length = 0;
}
