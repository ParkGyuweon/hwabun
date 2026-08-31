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
/** 개발용 패널에서 되돌아볼 최근 이벤트 보관 개수. 전송량과는 무관하다 */
const HISTORY_LIMIT = 200;

/**
 * 수집 API.
 *
 * 백엔드가 프론트 계약에 맞추기로 해서 이 형태가 기준이다.
 * 자세한 값은 docs/analytics/log-transport-contract.md 참고.
 */
const COLLECT_ENDPOINT = '/api/events';

/**
 * 한 요청에 담는 최대 건수. 수집 서버가 100건으로 막고 있어 거기에 맞춘다.
 * BATCH_SIZE 는 "이만큼 쌓이면 보낸다" 는 기준이고, 이 값은 넘지 말아야 할 상한이다.
 */
const MAX_BATCH_SIZE = 100;

/**
 * 재시도 큐 상한.
 * 수집 서버가 죽어 있어도 브라우저 메모리를 계속 먹지 않도록 막는다.
 * 방문당 100~160건이라 넉넉잡아 몇 분치다.
 */
const QUEUE_LIMIT = 1000;

/** 전송 실패 경고를 매번 찍으면 콘솔이 묻힌다. 한 번만 알린다 */
let retryWarned = false;

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

/**
 * 페르소나가 바뀌면 새 방문으로 취급한다.
 *
 * `session_start` 는 **세션의 첫 page_view 와 같은 page_view_id** 를 공유한다
 * (데이터 계약). 그래서 여기서 첫 page_view_id 를 미리 발급하고,
 * 같은 id 로 첫 page_view 까지 바로 남긴다. 조인 없이 세션의 시작 화면을 알 수 있다.
 *
 * 이전에는 session_start 가 직전 화면의 page_view_id 를 들고 나갔고,
 * 페르소나 교체 시 새 세션의 첫 page_view 가 아예 없었다.
 */
export function startSession(personaId: string | null, productId: string | null = null): void {
  if (startedSessionKey === personaId) return;
  startedSessionKey = personaId;

  sessionId = createId();
  sequenceNo = 0;
  firedOnceKeys.clear();
  setLoggerContext({ personaId, productId });

  // 첫 page_view 몫의 id 를 세션 시작 전에 발급해 둘이 공유한다
  pageViewId = createId();
  startedPageViewKey = productId;

  track('session_start', { entry_page: context.pageType });
  track('page_view', { product_id: productId, navigation_source: 'session_start' });
  trackProductView(productId, 'session_start');
}

/**
 * 상품 상세를 열었을 때 `product_view` 를 남긴다 (데이터 계약).
 *
 * page_view 는 화면 이동과 체류를 표현하고, product_view 는 **상품 단위 조회 수**와
 * Funnel 의 기준이다. page_view 만 쓰면 상품 조회 집계가 화면 구조에 종속돼서,
 * 상세를 모달이나 탭 같은 다른 형태로 바꾸면 과거 수치와 이어지지 않는다.
 *
 * 상세로 들어오는 경로가 세션 시작과 화면 이동 두 갈래라 함수로 묶어 둔다.
 * 한쪽에만 넣으면 상품 URL 로 바로 들어온 방문이 통째로 빠진다.
 * 같은 page_view_id 를 쓰므로 page_view 와 이어 붙일 수 있다.
 */
function trackProductView(productId: string | null, navigationSource: string): void {
  if (productId === null) return;
  track('product_view', { product_id: productId, navigation_source: navigationSource });
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
  trackProductView(productId, navigationSource);
}

export function track(eventName: EventName, properties: Record<string, unknown> = {}): void {
  sequenceNo += 1;

  /**
   * top-level `product_id` 는 **이벤트 대상 상품**이다 (데이터 계약).
   *
   * 페이지 컨텍스트 상품과 대상이 다를 수 있다. A 상세에서 추천 B 를 클릭하면
   * 대상은 B 이고, A 는 properties.context_product_id 로 따로 남긴다.
   * 호출부가 properties 에 product_id 를 실으면 그것이 대상이고,
   * 안 실으면(섹션 체류·스크롤 등 화면 자체 이벤트) 보고 있는 상품이 곧 대상이다.
   */
  const hasTarget = Object.prototype.hasOwnProperty.call(properties, 'product_id');
  const targetProductId = hasTarget
    ? ((properties.product_id as string | null | undefined) ?? null)
    : context.productId;

  const { product_id: _lifted, ...restProperties } = properties;
  const finalProperties: Record<string, unknown> = hasTarget ? restProperties : { ...properties };
  if (hasTarget && context.productId !== null && context.productId !== targetProductId) {
    finalProperties.context_product_id = context.productId;
  }

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
    product_id: targetProductId,
    actor_type: context.actorType,
    environment: context.environment,

    properties: finalProperties,
  };

  queue.push(event);

  history.unshift(event);
  if (history.length > HISTORY_LIMIT) {
    history.length = HISTORY_LIMIT;
  }

  for (const listener of listeners) {
    listener(event);
  }

  // 개발 중 확인용. 화면에서는 LogPanel 이 같은 내용을 보여준다
  if (import.meta.env.DEV) console.info(`[log] ${eventName}`, event);

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
 * 화면 응답이 로그 저장을 기다리지 않도록 반드시 비동기로 유지한다.
 * 실패해도 화면에는 아무 영향이 없어야 한다. 로그는 부가 기능이다.
 */
export function flush(useBeacon = false): void {
  if (queue.length === 0) return;

  /**
   * 한 번에 보내는 건수를 서버 상한에 맞춘다.
   *
   * 큐 전체를 통째로 보내면, 수집 서버가 잠깐 죽었다 살아났을 때
   * 그 사이 쌓인 배치가 상한을 넘어 계속 거절당한다.
   * 거절 → 재시도 → 다시 거절 로 자력 복구가 안 된다.
   */
  const batch = queue.splice(0, Math.min(queue.length, MAX_BATCH_SIZE));

  if (flushTimer !== undefined) {
    window.clearTimeout(flushTimer);
    flushTimer = undefined;
  }

  // 상한에 걸려 남은 것이 있으면 이어서 보낸다
  if (queue.length > 0) scheduleFlush();

  const body = JSON.stringify({ schema_version: SCHEMA_VERSION, events: batch });

  if (useBeacon) {
    /**
     * 이탈 시점에는 일반 요청이 취소될 수 있어 sendBeacon 을 쓴다.
     * 대신 성공 여부를 알 수 없어서 재시도도 못 한다.
     * 서버가 event_id 로 멱등 처리하기로 했으므로 유실보다 중복이 낫다.
     */
    navigator.sendBeacon(COLLECT_ENDPOINT, new Blob([body], { type: 'application/json' }));
    return;
  }

  fetch(COLLECT_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  })
    .then((response) => {
      if (!response.ok) requeue(batch, `HTTP ${response.status}`);
    })
    .catch((error: unknown) => {
      requeue(batch, error instanceof Error ? error.message : '네트워크 오류');
    });
}

/**
 * 실패한 배치를 큐 앞에 되돌린다.
 *
 * 서버가 `event_id` 기준으로 중복을 걸러주기로 해서 재시도가 안전하다.
 * 다만 수집 서버가 계속 죽어 있으면 큐가 무한히 커지므로 상한을 둔다.
 * 오래된 것부터 버린다. 최근 행동이 분석에 더 쓸모가 있다.
 */
function requeue(batch: LogEnvelope[], reason: string): void {
  if (!retryWarned) {
    retryWarned = true;
    console.warn(`[log] 전송 실패, 재시도 큐에 넣음 (${reason})`);
  }

  queue.unshift(...batch);
  if (queue.length > QUEUE_LIMIT) {
    const dropped = queue.length - QUEUE_LIMIT;
    queue.splice(0, dropped);
    console.warn(`[log] 큐가 넘쳐 오래된 ${dropped}건을 버렸다`);
  }

  scheduleFlush();
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
