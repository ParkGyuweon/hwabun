import { EVENT_INTENT, SCHEMA_VERSION } from '../types/log';
import { sessionSnapshot } from './auth';
import { ingestForTrait } from './trait';
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
  /** synthetic 실행 정보. 실사용자 방문이면 null */
  synthetic: SyntheticContext | null;
  /**
   * 이 방문이 어떤 진열의 쇼핑몰에서 일어났는지 (src/lib/storefront.ts).
   *
   * 브랜드마다 진열이 다르기 때문에 필요하다. 같은 `product_click` 이라도 4열 그리드에서
   * 나온 것과 옆에 붙은 기획전 레일에서 나온 것은 다른 화면의 결과다. 안 실으면 브랜드
   * 50개 로그를 합쳤을 때 그 차이가 노이즈로 남고, 실으면 "어느 진열이 더 잘 팔리나" 가
   * group by 한 줄이 된다.
   *
   * 쇼핑몰만 채운다. 대시보드·플랫폼 화면은 로그를 남기지 않는다.
   */
  storefront: Record<string, string> | null;
}

/**
 * 부하 생성기가 이 화면을 직접 조작할 때 봉투에 실어야 하는 실행 정보.
 * actor_type='synthetic' 이면 셋 다 필수다 (contracts/event-schema.json).
 */
interface SyntheticContext {
  generatorType: string;
  simulationRunId: string;
  scenarioId: string;
}

type Listener = (event: LogEnvelope) => void;

const BATCH_SIZE = 20;
const FLUSH_INTERVAL_MS = 5000;

/**
 * 배치를 기다리지 않고 바로 보내는 이벤트 (계약 `recommendation-io-spec.md` §2-1).
 *
 * 수집 API 는 Kafka 로 보내면서 **Redis 사용자 벡터도 같이 갱신**한다. 그래서
 * 전환 이벤트가 배치 버퍼(최대 5초)에 묶여 있으면 담자마자 새로고침한 다음 추천에
 * 그 행동이 안 들어간다. 특히 `remove_from_cart` 는 부정 축이 늦게 반영돼서
 * **뺀 상품이 계속 추천에 뜨는** 것으로 보인다.
 *
 * 전환은 세션당 몇 건이라 즉시 보내도 트래픽에 영향이 없다. 스크롤·체류·노출은
 * 건수가 많고 서빙 상태를 바꾸지 않으므로 지금처럼 배치로 둔다.
 */
const IMMEDIATE_EVENTS: ReadonlySet<string> = new Set([
  'add_to_cart',
  'remove_from_cart',
  'quantity_change',
  'purchase',
  'wishlist_toggle',
]);
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
 * 로그인 상태면 수집 요청에 토큰을 얹는다 (백엔드 회신 2026-09-10).
 *
 * 백엔드가 JWT 의 `sub` 를 `account_id` 로 뽑아 Kafka 이벤트에 직접 넣는다.
 * 그래서 봉투에 `account_id` 를 우리가 채우지 않는다 — 두 곳에서 채우면
 * 어긋났을 때 어느 쪽이 맞는지 알 수 없다.
 *
 * 쇼핑몰을 보는 사람은 MEMBER 다. 판매자·관리자 화면은 대시보드라 이 로거를
 * 타지 않는다. 토큰이 없으면 헤더 없이 보낸다 — 비로그인 방문도 분석 대상이다.
 */
/**
 * 브랜드 담당자(SELLER)·운영자(ADMIN)가 이 브라우저에 로그인해 있으면 쇼핑몰 행동 로그를 **보내지 않는다**
 * (결정 2026-09-11). 그 사람은 고객이 아니다. 자기 상품을 점검하려고 상세를 열고 담아 보는 행동이 대시보드
 * 지표·추천·성향에 섞이면 안 된다.
 *
 * 단, 쇼핑몰에 회원(MEMBER)으로 로그인해 있으면 고객으로 보고 보낸다 (2026-09-27). 시연에서 같은 브라우저에
 * 대시보드를 로그인해 둔 채 회원으로 쇼핑하면 로그가 서버로 안 나가 실시간 화면이 멈췄다. 시크릿 창도 시크릿 창끼리
 * localStorage 를 공유해 피할 수 없었다. 비로그인으로 둘러보는 판매자·운영자는 지금처럼 막힌다.
 *
 * 로그인 여부는 이벤트가 만들어지는 순간마다 본다. 대시보드에서 로그아웃하면 다음 이벤트부터 다시 나간다.
 */
function isStaffSession(): boolean {
  try {
    if (sessionSnapshot('MEMBER') !== null) return false;
    return sessionSnapshot('SELLER') !== null || sessionSnapshot('ADMIN') !== null;
  } catch {
    return false;
  }
}

let staffNoticeShown = false;

function collectToken(): string | null {
  try {
    return sessionSnapshot('MEMBER')?.token ?? null;
  } catch {
    // 저장소를 못 읽어도 로그는 보내야 한다. 익명으로 나간다
    return null;
  }
}

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

/**
 * 계약이 정한 생성 방식(`contracts/event-schema.json`).
 * 여기 없는 값은 검증기가 거절하므로 받아주지 않는다.
 */
const GENERATOR_TYPES = ['python_batch', 'agent_llm'];

/**
 * 진입 주소에서 synthetic 표시를 읽는다.
 *
 * LLM 에이전트는 로그를 직접 만들지 않고 실제 브라우저로 이 화면을 조작한다.
 * 표시가 없으면 로거가 실사용자와 구분할 수 없어 actor_type='user' 로 남기는데,
 * 그러면 Spark 가 user_id 를 NULL 로 파생하고 synthetic 필수 property 검증도
 * 건너뛰어서 **거절되지 않고 조용히 잘못된 데이터**가 된다.
 * 계약: docs/analytics/log-transport-contract.md §9
 *
 * **개발 서버에서만 인정한다.** 배포 화면에서도 받아주면 주소만 고쳐서
 * 아무나 로그 출처를 위장할 수 있다.
 *
 * 넷 중 하나라도 없거나 계약 밖의 값이면 통째로 무시하고 user 로 둔다.
 * 일부만 채운 봉투는 검증기에 걸려 어차피 격리되므로, 반쯤 표시된 상태로
 * 흘려보내는 것보다 실사용자로 남기고 러너가 보정하게 두는 편이 낫다.
 */
function syntheticContextFromUrl(): SyntheticContext | null {
  if (!import.meta.env.DEV) return null;
  if (typeof window === 'undefined') return null;

  const query = new URLSearchParams(window.location.search);
  if (query.get('actor') !== 'synthetic') return null;

  const generatorType = query.get('gen') ?? '';
  const simulationRunId = query.get('run') ?? '';
  const scenarioId = query.get('scenario') ?? '';
  if (!GENERATOR_TYPES.includes(generatorType)) return null;
  if (!simulationRunId || !scenarioId) return null;

  return { generatorType, simulationRunId, scenarioId };
}

/**
 * 모듈을 읽을 때 한 번 판정한다.
 *
 * 화면 effect 에서 정하면 그 전에 나가는 이벤트(첫 로드의 scroll_depth 등)가
 * user 로 남아 한 실행 안에서 actor_type 이 섞인다.
 */
const syntheticContext = syntheticContextFromUrl();

/**
 * 실행 환경. 봉투의 필수 필드다 (`raw-event-schema.md`).
 *
 * **하드코딩된 `'local'` 이었다.** 바꾸는 곳이 없어서 배포본 이벤트도 전부 `local` 로 나갔다
 * (AI 파트 배포본 확인 2026-09-16). 로컬 개발 로그와 시연 로그를 가를 방법이 없었다는 뜻이다.
 *
 * 빌드 모드로 정한다. 설정을 늘리지 않으면서 `npm run build` 로 나온 번들만 `production` 이 된다 —
 * dev 서버는 지금처럼 `local` 이다. 계약에 enum 이 없어(`event-schema.json`: minLength 1) 값은
 * 우리가 정하는데, 배포가 한 곳뿐이라 두 값이면 충분하다. 환경이 늘면 그때 환경변수로 뺀다.
 */
const environment = import.meta.env.PROD ? 'production' : 'local';

let context: LoggerContext = {
  personaId: null,
  pageType: 'product_detail',
  productId: null,
  actorType: syntheticContext ? 'synthetic' : 'user',
  environment,
  synthetic: syntheticContext,
  storefront: null,
};

/**
 * 세션 상태를 sessionStorage 에 둔다 (데이터 파트 요청 2026-09-22).
 *
 * 전에는 모듈 전역 변수여서 **페이지를 통째로 다시 로드하면** 새 session_id 가 발급됐다. 링크로 상세에 들어와
 * 새로고침한 사람은 세션이 둘로 갈리고, 앞 세션은 늦게 도착한 조각(recommendation_snapshot 1건)만 든 껍데기가 됐다
 * (규원님 실측: 사람당 세션 3.8개, product_view 가 0 인 세션 7/19).
 *
 * session_id 만 살리면 안 된다. `impressedProducts` 도 같이 살려야 같은 세션·같은 상품에 보강 노출
 * (implied_by_direct_view)이 두 번 나가지 않는다. sequence_no 도 이어 간다 — 같은 세션 안에서 번호가 되감기면
 * 정렬이 깨진다. 탭을 닫으면 sessionStorage 가 비므로 그때는 자연히 새 세션이다.
 */
const SESSION_STORE_KEY = 'hwabun.logger.session.v1';

interface StoredSession {
  session_id: string;
  /** startSession 에 넘어온 식별자(회원 id·페르소나 id·null). 같은 값이면 같은 세션을 이어 쓴다 */
  persona_key: string | null;
  sequence_no: number;
  impressed: string[];
  /** 이 세션에 상세를 본 상품. 새로고침 뒤에도 재조회(`revisit`)를 가르려면 같이 살려야 한다. 옛 저장본에는 없다 */
  viewed: string[];
}

function loadStoredSession(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORE_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<StoredSession>;
    if (typeof v.session_id !== 'string' || typeof v.sequence_no !== 'number') return null;
    return {
      session_id: v.session_id,
      persona_key: typeof v.persona_key === 'string' ? v.persona_key : null,
      sequence_no: v.sequence_no,
      impressed: Array.isArray(v.impressed) ? v.impressed.filter((x): x is string => typeof x === 'string') : [],
      viewed: Array.isArray(v.viewed) ? v.viewed.filter((x): x is string => typeof x === 'string') : [],
    };
  } catch {
    return null;
  }
}

/** 새로고침 전 세션. 있으면 startSession 이 같은 식별자일 때 이어 쓴다. 한 번 쓰고 비운다 */
let restoredSession: StoredSession | null = loadStoredSession();

let sessionId = restoredSession?.session_id ?? createId();
let pageViewId = createId();
let sequenceNo = restoredSession?.sequence_no ?? 0;

function persistSession(personaKey: string | null): void {
  try {
    const v: StoredSession = { session_id: sessionId, persona_key: personaKey, sequence_no: sequenceNo, impressed: [...impressedProducts], viewed: [...viewedProducts] };
    window.sessionStorage.setItem(SESSION_STORE_KEY, JSON.stringify(v));
  } catch {
    /* 저장 못 해도 이번 페이지 안에서는 그대로 동작한다 */
  }
}

const queue: LogEnvelope[] = [];
const history: LogEnvelope[] = [];
const listeners = new Set<Listener>();

let flushTimer: number | undefined;

/**
 * 한 번만 발생해야 하는 이벤트의 중복 방지 키 저장소.
 * 스크롤을 위아래로 반복해도 section_view 가 다시 찍히지 않게 한다.
 */
const firedOnceKeys = new Set<string>();

/**
 * 계약이 `string|null` 로 선언한 property. **이 셋만** null 을 실어 보낸다.
 * (`contracts/event-properties-schema.md` §4)
 *
 * 나머지는 전부 `string` 이라 null 을 실으면 "값을 안 줬다" 가 아니라 **타입 위반**이다.
 * 검증기가 `_matches_type(None, "string")` 을 False 로 보고 격리한다.
 * 선택 property 는 값이 없으면 키 자체를 빼는 것이 계약이 말하는 "미제공" 이다.
 *
 * 화면 코드는 이걸 신경 쓰지 않아도 된다. 구역 판정(regionOfNode)은 못 찾으면 null 을
 * 돌려주고 호출부는 그걸 그대로 펼쳐 넣는데, 어디서 무엇이 null 이 될지 호출부마다
 * 따지게 하면 언젠가 빠뜨린다. 나가는 길목인 여기서 한 번에 거른다.
 */
const NULLABLE_PROPERTIES: Record<string, ReadonlySet<string>> = {
  hover_dwell: new Set(['action']),
  rage_click: new Set(['action']),
  dead_click: new Set(['target_tag']),
  // §3.13: banner_type=new_brand 면 banner_value 는 **JSON null 이 필수**다. 키를 빼면 수집기가 거절한다
  banner_impression: new Set(['banner_value']),
  banner_click: new Set(['banner_value']),
};

/** 계약이 허용하지 않는 null 을 걷어낸다. 봉투를 만들기 직전에 한 번 */
function dropDisallowedNulls(
  eventName: EventName,
  properties: Record<string, unknown>,
): Record<string, unknown> {
  const allowed = NULLABLE_PROPERTIES[eventName];
  const cleaned: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(properties)) {
    if (value === null && !allowed?.has(key)) continue;
    cleaned[key] = value;
  }

  return cleaned;
}

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
/**
 * 노출로 인정하는 판정 임계값 (계약 §3.12-1). `IntersectionObserver` threshold 와 같은 값을 그대로 싣는다.
 * 합성 노출도 같은 값을 싣는다 — 측정값이 아니라 기준이라서다. useImpression 이 이 값을 쓴다.
 */
export const IMPRESSION_VISIBLE_RATIO = 0.5;

/**
 * 이 **세션에서** 노출이 한 번이라도 남은 상품.
 *
 * `firedOnceKeys` 는 page_view 마다 비우므로 "세션 안에 노출이 있었나" 를 볼 수 없다. 그 판정이 따로 필요하다 —
 * 목록을 거치지 않고 링크·북마크로 상세에 바로 들어오면 노출이 하나도 없는데 상세 조회만 남아서,
 * 마트의 `detail_entry_rate` 가 1 을 넘는다 (데이터 파트 실측 2026-09-21: 노출 4 세션 · 상세 6 세션 = 1.5).
 */
const impressedProducts = new Set<string>(restoredSession?.impressed ?? []);

/**
 * 이 세션에 `product_view` 를 남긴 상품. 같은 상품 상세로 화면 안에서 다시 돌아오면 `in_app` 대신 `revisit` 을 단다
 * (계약 §3.4, 데이터 파트 요청 2026-09-23).
 *
 * 상세에서 담기 → 장바구니 열기 → 닫기면 상세가 다시 열리며 `product_view` 가 한 번 더 나간다. `in_app` 이면 새 진입과
 * 구분이 안 돼 마트의 `detail_entry_rate` 가 노출 1 · 조회 3 = 300% 가 됐다. 실사용자 세션 5건 중 1건꼴이다.
 * 뒤로가기(`history_back`)·새로고침(`reload`)과 같은 재조회라 마트가 같은 방식으로 `product_view_count` 에서 뺀다.
 */
const viewedProducts = new Set<string>(restoredSession?.viewed ?? []);

/**
 * 직전 `product_view` 이후에 `product_click` 이 있었던 상품. 이런 상품은 이미 본 상품이어도 **새 진입**(`in_app`)이다
 * (데이터 파트 요청 2026-09-23 오후).
 *
 * 처음엔 "이 세션에 본 적 있으면 전부 revisit" 이었는데, 목록으로 돌아가 같은 카드를 다시 누른 것까지 묶였다. 그건 카드를
 * 다시 봤으니 노출도 같이 늘어나는 새 진입이다 (실측: 재조회 후보 109건 중 105건이 바로 앞에 product_click).
 * 추천 카드도 `recommendation_click` 과 함께 `product_click` 을 내므로 이것 하나로 가른다. 상세를 열면 비운다.
 * 새로고침은 `reload` 로 따로 가르므로 저장하지 않는다.
 */
const clickedSinceView = new Set<string>();

/** 노출을 남긴 쪽이 알려 준다 (useImpression). 세션이 바뀌면 비워진다. 새로고침에는 남는다 */
export function markProductImpressed(productId: string | null | undefined): void {
  if (!productId || impressedProducts.has(productId)) return;
  impressedProducts.add(productId);
  if (startedSessionKey !== NOT_STARTED) persistSession(startedSessionKey);
}

export function hasProductImpression(productId: string): boolean {
  return impressedProducts.has(productId);
}

export function startSession(personaId: string | null, productId: string | null = null): void {
  if (startedSessionKey === personaId) return;
  const firstCall = startedSessionKey === NOT_STARTED;
  startedSessionKey = personaId;

  /*
   * 새로고침 뒤 첫 호출이고 저장된 세션의 식별자가 같으면 **그 세션을 이어 쓴다.** session_start 를 다시 내지 않고
   * (세션은 하나다) 화면 조회만 남긴다. navigation_source 는 `reload` (계약 §3.4, 2026-09-22 추가) — 마트가 뒤로가기 재조회처럼 product_view_count 에서 빼려면 direct 와 갈라야 한다.
   * 노출 기록도 살아 있으니 이미 본 상품에는 보강 노출이 다시 나가지 않는다.
   */
  const resume = firstCall && restoredSession !== null && restoredSession.persona_key === personaId;
  restoredSession = null;
  if (resume) {
    firedOnceKeys.clear();
    pendingEntry = null;
    setLoggerContext({ personaId, productId });
    pageViewId = createId();
    startedPageViewKey = productId;
    track('page_view', { product_id: productId, navigation_source: 'reload' });
    trackProductView(productId, 'reload');
    persistSession(personaId);
    return;
  }

  sessionId = createId();
  sequenceNo = 0;
  firedOnceKeys.clear();
  impressedProducts.clear();
  viewedProducts.clear();
  clickedSinceView.clear();
  pendingEntry = null;
  setLoggerContext({ personaId, productId });

  // 첫 page_view 몫의 id 를 세션 시작 전에 발급해 둘이 공유한다
  pageViewId = createId();
  startedPageViewKey = productId;

  track('session_start', { entry_page: context.pageType });
  track('page_view', { product_id: productId, navigation_source: 'session_start' });
  trackProductView(productId, 'session_start');
  persistSession(personaId);
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
function trackProductView(
  productId: string | null,
  navigationSource: string,
  entry: ProductViewEntry | null = null,
): void {
  if (productId === null) return;
  /**
   * **상세를 봤으면 그 상품을 본 것이다.** 이 세션에 그 상품의 노출이 하나도 없으면 여기서 하나 보강한다
   * (데이터 파트 요청 2026-09-21).
   *
   * 목록에서 누르고 들어온 경우는 `confirmImpressionByClick` 이 이미 남겼고, 화면에 오래 머문 카드는 관찰 경로가
   * 남겼다. 남는 것은 **목록을 아예 안 거친 진입** — 링크·북마크·새 탭으로 상세가 첫 화면인 경우다. 그때는 누른 것이
   * 없어 기존 보강 두 갈래(implied_by_click · implied_by_quick_look)가 동작하지 않아, 노출 없이 상세 조회만 남았다.
   * 합성 트래픽은 늘 목록을 거쳐서 이 경로가 지금까지 안 보였다.
   */
  if (!impressedProducts.has(productId)) {
    impressedProducts.add(productId);
    track('product_impression', {
      product_id: productId,
      // 목록을 거치지 않았으므로 자리가 없다. 목록 이름과 순번 자리에 "목록 없음" 을 적는다
      list_id: 'direct',
      position: 0,
      hold_ms: 0,
      visible_ratio: IMPRESSION_VISIBLE_RATIO,
      impression_origin: 'implied_by_direct_view',
    });
  }
  // 로그를 안 내는 판매자·운영자 세션에는 기록하지 않는다. 로그아웃 뒤 첫 조회가 재조회로 찍히면 안 된다
  if (!isStaffSession()) viewedProducts.add(productId);
  clickedSinceView.delete(productId);
  track('product_view', {
    product_id: productId,
    navigation_source: navigationSource,
    ...(entry && entry.product_id === productId
      ? { recommendation_id: entry.recommendation_id, list_id: entry.list_id, position: entry.position }
      : {}),
  });
}

/**
 * 추천 카드를 눌러 들어온 상세의 `product_view` 에 실을 식별자 (Jira 210).
 *
 * 계약(event-properties §4.2)은 `product_view` 에 `recommendation_id`·`list_id`·`position` 을
 * 선택 필드로 허용한다. 값은 그 카드의 `recommendation_click` 과 같다. 이게 있어야 교차 브랜드
 * 유입의 "추천 경유" 가 세션 순서를 추정하지 않고 product_view 한 행으로 닫힌다.
 * 생성기(`gen_behavior_logs.py visit_detail(rec_meta=)`)가 같은 모양으로 채운다.
 *
 * 카드 클릭 → `onSelect` → App 의 setProductId → effect → `startPageView` 순서라 클릭 시점과
 * product_view 시점이 갈라진다. 그래서 클릭한 쪽이 여기 예약해 두고 `startPageView` 가 한 번 쓴다.
 * 예약한 상품과 실제로 열린 상품이 다르면(중간에 장바구니를 열었다 등) 버린다 — 잘못 붙는 것보다
 * 안 붙는 게 낫다. 직접 진입·목록 클릭은 키 자체를 보내지 않는다 (생성기와 같음).
 */
export interface ProductViewEntry {
  product_id: string;
  recommendation_id: string;
  list_id: string;
  position: number;
}
let pendingEntry: ProductViewEntry | null = null;

export function setNextProductViewEntry(entry: ProductViewEntry | null): void {
  pendingEntry = entry;
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
  const entry = pendingEntry;
  pendingEntry = null;
  // 화면 안 이동인데 이 세션에 이미 본 상품이고, 그 뒤로 카드를 다시 누르지 않았으면 재조회다.
  // page_view 와 product_view 에 같은 값을 단다 (계약 §3.4)
  const source =
    navigationSource === 'in_app' && productId !== null && viewedProducts.has(productId) && !clickedSinceView.has(productId)
      ? 'revisit'
      : navigationSource;
  track('page_view', { product_id: productId, navigation_source: source });
  trackProductView(productId, source, entry);
}

/**
 * 판매자·운영자 세션이라 지금 로그를 **보내지 않는** 상태인가. 서버로는 한 건도 안 나간다.
 * 이벤트는 여전히 만들어져 우하단 실시간 행동 기록(components/devtools/LiveLog)에는 흐른다 —
 * 대시보드에 로그인해 둔 같은 브라우저로 시연해도 찍혀야 한다. 그때 창은 점을 회색으로, "전송 안 함" 을 적는다.
 */
export function isSuppressed(): boolean {
  return isStaffSession();
}

export function track(eventName: EventName, properties: Record<string, unknown> = {}): void {
  // 판매자·운영자의 행동은 고객 행동이 아니다. 만들어서 화면 로그 창에는 보여 주되 **쌓지도 보내지도 않는다**
  const suppressed = isStaffSession();
  if (suppressed) {
    if (!staffNoticeShown) {
      staffNoticeShown = true;
      console.info('[log] 판매자·운영자 세션이라 행동 로그를 보내지 않습니다 (로그아웃하면 다시 보냅니다)');
    }
  } else {
    staffNoticeShown = false;
  }
  sequenceNo += 1;
  // 번호가 오른 뒤 바로 저장한다. 새로고침 뒤에도 같은 세션의 번호가 이어진다
  if (startedSessionKey !== NOT_STARTED) persistSession(startedSessionKey);

  /**
   * top-level `product_id` 는 **이벤트 대상 상품**이다 (데이터 계약).
   *
   * 페이지 컨텍스트 상품과 대상이 다를 수 있다. A 상세에서 추천 B 를 클릭하면
   * 대상은 B 이고, A 는 properties.context_product_id 로 따로 남긴다.
   * 호출부가 properties 에 product_id 를 실으면 그것이 대상이고,
   * 안 실으면(섹션 체류·스크롤 등 화면 자체 이벤트) 보고 있는 상품이 곧 대상이다.
   */
  // `product_id: undefined` 로 온 것은 "대상 없음" 이 아니라 "안 실은 것" 으로 본다 — 스프레드로 빈 값이 섞여도 컨텍스트 상품이 남는다
  const hasTarget =
    Object.prototype.hasOwnProperty.call(properties, 'product_id') && properties.product_id !== undefined;
  let targetProductId = hasTarget ? ((properties.product_id as string | null) ?? null) : context.productId;
  /**
   * 상세 화면의 이벤트는 수집기가 top-level product_id 를 요구한다 (event-properties-schema §24-25 ·
   * EventContractValidator PRODUCT_DETAIL_SCOPED_EVENTS). 대상이 비면 보고 있는 상품으로 채운다 —
   * 상세에서 대상 없는 이벤트는 정의상 없다 (AI 파트 보고 2026-09-14 §2: scroll_depth·scroll_pause 거절).
   */
  if (targetProductId === null && context.pageType === 'product_detail' && context.productId !== null) {
    targetProductId = context.productId;
  }

  const { product_id: _lifted, ...restProperties } = properties;
  const finalProperties: Record<string, unknown> = hasTarget ? restProperties : { ...properties };
  if (hasTarget && context.productId !== null && context.productId !== targetProductId) {
    finalProperties.context_product_id = context.productId;
  }

  /**
   * synthetic 실행 정보는 어느 이벤트에나 실린다. 셋 다 없으면 검증기가 거절한다.
   *
   * 호출부가 같은 키를 이미 실었으면 덮지 않는다. 덮으면 화면이 제대로 붙였는지
   * 확인할 방법이 없어진다 (log-transport-contract.md §9-3 과 같은 규칙).
   */
  if (context.synthetic !== null) {
    const { generatorType, simulationRunId, scenarioId } = context.synthetic;
    finalProperties.generator_type ??= generatorType;
    finalProperties.simulation_run_id ??= simulationRunId;
    finalProperties.scenario_id ??= scenarioId;
  }

  /**
   * 진열 정보도 어느 이벤트에나 실린다.
   *
   * **이벤트 정의는 하나도 바뀌지 않는다.** `properties` 는 계약상 열린 객체라
   * (contracts/event-schema.json — `"properties": {"type": "object"}`) 키를 더해도
   * 검증기·수집 서버·기존 소비자가 그대로 통과한다. 읽지 않는 쪽은 없는 것처럼 동작한다.
   */
  if (context.storefront !== null) {
    for (const [key, value] of Object.entries(context.storefront)) {
      finalProperties[key] ??= value;
    }
  }

  const event: LogEnvelope = {
    schema_version: SCHEMA_VERSION,
    event_id: createId(),
    event_name: eventName,
    // 분석하는 쪽이 이벤트 이름마다 의미를 다시 정하지 않도록 발생 시점에 실어 보낸다
    intent: EVENT_INTENT[eventName],
    occurred_at: new Date().toISOString(),

    // 소유 식별자(tenant·brand)는 봉투에 싣지 않는다. 처리 단계가 product_id 로 파생한다
    persona_id: context.personaId,
    session_id: sessionId,
    page_view_id: pageViewId,
    sequence_no: sequenceNo,

    page_type: context.pageType,
    product_id: targetProductId,
    actor_type: context.actorType,
    environment: context.environment,

    properties: dropDisallowedNulls(eventName, finalProperties),
  };

  history.unshift(event);
  if (history.length > HISTORY_LIMIT) {
    history.length = HISTORY_LIMIT;
  }

  for (const listener of listeners) {
    listener(event);
  }

  /*
   * 브라우저 개발자 도구 콘솔에도 찍는다. 배포 빌드에서도 켠다 — 전에는 개발 서버에서만 찍혀서 배포 사이트의
   * 콘솔에는 아무것도 안 떠 "로그가 안 찍힌다" 로 보였다 (2026-09-23 유림님). 서버로 안 나가는 줄은 표시한다
   */
  console.info(`[log] ${eventName}${suppressed ? ' (판매자 로그인 중 · 서버로 안 보냄)' : ''}`, event);

  // 판매자·운영자 세션: 화면 로그 창까지만. 성향 누적·전송 큐에는 넣지 않는다
  if (suppressed) return;

  // 카드를 눌렀다 — 곧 열릴 상세는 이미 본 상품이어도 새 진입이다 (위 clickedSinceView)
  if (eventName === 'product_click' && targetProductId) clickedSinceView.add(targetProductId);

  // 세션 성향은 이벤트가 나가는 바로 이 자리에서 같이 누적한다 (lib/trait.ts). 지연 0
  ingestForTrait(eventName, event.properties);

  queue.push(event);

  // 전환은 배치를 기다리지 않는다 (§2-1). 백오프 중이면 그대로 예약으로 떨어진다 —
  // 수집 서버가 죽어 있을 때 전환마다 요청을 쏘면 폭주 방지가 무너진다
  const immediate = IMMEDIATE_EVENTS.has(eventName);
  if ((immediate || queue.length >= BATCH_SIZE) && Date.now() >= backoffUntil) {
    flush();
  } else {
    scheduleFlush();
  }
}

/**
 * 같은 키로는 한 번만 발생시킨다.
 * section_view, scroll_depth 처럼 페이지 방문당 1회여야 하는 이벤트에 사용한다.
 */
/** `trackOnce` 로 이미 남긴 키인가. 노출 훅이 "클릭이 먼저 노출을 확정했나" 를 볼 때 쓴다 */
export function hasTrackedOnce(key: string): boolean {
  return firedOnceKeys.has(key);
}

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

function scheduleFlush(delayMs = FLUSH_INTERVAL_MS): void {
  if (flushTimer !== undefined) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = undefined;
    flush();
  }, delayMs);
}

/**
 * 한 번에 보내는 건수. 평소에는 서버 상한(MAX_BATCH_SIZE)이고,
 * 413(본문 과대)을 받으면 반으로 줄여서 다시 보낸다. 같은 크기로 재시도하면
 * 계속 같은 이유로 거절당해 자력 복구가 안 된다. 성공하면 조금씩 되돌린다.
 */
let sendBatchSize = MAX_BATCH_SIZE;

/**
 * 이 시각 전에는 즉시 전송을 걸지 않는다.
 *
 * 전송이 실패해 배치가 큐로 돌아오면 큐는 계속 BATCH_SIZE 를 넘는 상태가 된다.
 * 그때 track() 이 "쌓였으니 바로 보내자" 를 반복하면, 죽어 있는 수집 서버에
 * 새 이벤트가 생길 때마다 요청을 쏘는 폭주가 된다 (실측: 13초에 19회).
 * 실패 후에는 예약된 재시도 시각까지 기다린다.
 */
let backoffUntil = 0;

/**
 * 이 응답이면 다시 보내볼 가치가 있다 (수집 서버와 합의한 기준).
 *   429  수집 스레드 포화 — Retry-After 를 존중한다
 *   502 / 503 / 504  게이트웨이·Kafka 장애 — 지나가는 문제다
 * 400 계열(400/403/404/422)은 요청 자체가 잘못된 것이라 몇 번을 보내도
 * 똑같이 거절당한다. 재시도하면 같은 배치가 5초마다 영원히 돈다.
 */
const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);

/** 버린 배치를 상태 코드마다 한 번만 알린다. 매번 찍으면 콘솔이 묻힌다 */
const dropWarned = new Set<number>();

/**
 * 지금 나가고 있는 전송들. `settled()` 가 이것을 기다린다.
 *
 * 수집 API 는 Kafka 로 보내며 추천 서버의 사용자 상태도 같이 바꾼다. 그래서 "좋아요 → 뒤로 가기" 직후의
 * 추천 요청이 좋아요 전송보다 먼저 서버에 닿으면 옛 목록을 받는다 (AI 파트 요청 2026-09-14 저녁 §2).
 * 화면 응답은 이것을 기다리지 않는다 — 추천 재요청처럼 "서버 상태를 읽는" 쪽만 기다린다.
 */
const inFlight = new Set<Promise<void>>();

/** 전송 완료를 기다리는 상한. 수집 서버가 느려도 목록이 이만큼 이상 목(mock)에 머물면 안 된다 */
const SETTLE_TIMEOUT_MS = 1500;

/**
 * 큐를 비우고, 나가고 있는 전송이 모두 끝날 때까지 기다린다 (상한 `SETTLE_TIMEOUT_MS`).
 *
 * 백오프 중(수집 서버 장애)이면 큐는 그대로 두고 즉시 끝난다 — 죽은 서버를 기다리느라 화면을 세우지 않는다.
 * 실패·거절도 "끝남" 으로 친다. 결과가 어떻든 그 뒤의 추천 요청은 나가야 한다.
 */
export function settled(): Promise<void> {
  flush();
  if (inFlight.size === 0) return Promise.resolve();
  const all = Promise.allSettled([...inFlight]).then(() => undefined);
  const cap = new Promise<void>((resolve) => window.setTimeout(resolve, SETTLE_TIMEOUT_MS));
  return Promise.race([all, cap]);
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
   * 백오프 중이면 예약 시각까지 미룬다.
   * 다른 경로로 걸린 타이머가 먼저 발화해 Retry-After 를 무시하는 일을 막는다.
   * 이탈 시점(useBeacon)만은 예외다 — 마지막 기회라 기다릴 수 없다.
   */
  const waitMs = backoffUntil - Date.now();
  if (!useBeacon && waitMs > 0) {
    scheduleFlush(waitMs);
    return;
  }

  /**
   * 한 번에 보내는 건수를 서버 상한에 맞춘다.
   *
   * 큐 전체를 통째로 보내면, 수집 서버가 잠깐 죽었다 살아났을 때
   * 그 사이 쌓인 배치가 상한을 넘어 계속 거절당한다.
   * 거절 → 재시도 → 다시 거절 로 자력 복구가 안 된다.
   */
  const batch = queue.splice(0, Math.min(queue.length, sendBatchSize));

  if (flushTimer !== undefined) {
    window.clearTimeout(flushTimer);
    flushTimer = undefined;
  }

  // 상한에 걸려 남은 것이 있으면 이어서 보낸다
  if (queue.length > 0) scheduleFlush();

  const body = JSON.stringify({ schema_version: SCHEMA_VERSION, events: batch });

  const token = collectToken();

  /**
   * sendBeacon 은 Authorization 헤더를 붙일 수 없다. 로그인 상태에서 beacon 으로
   * 보내면 토큰 없이 나가 백엔드가 account_id 를 못 뽑는다 — 그 사람의 마지막
   * 화면(이탈 직전)이 통째로 익명이 된다. 그래서 토큰이 있으면 이탈 시점에도
   * fetch keepalive 를 쓴다. keepalive 는 언로드를 건너뛰고 나가며, 비어 있는
   * 익명 경로는 지금까지처럼 beacon 이 더 확실하므로 그대로 둔다.
   */
  if (useBeacon && !token) {
    /**
     * 이탈 시점에는 일반 요청이 취소될 수 있어 sendBeacon 을 쓴다.
     * 반환값 false 는 브라우저 전송 큐에 넣지도 못했다는 뜻이므로 배치를
     * 버리지 않고 되돌린다 — 페이지가 살아 있으면 다음 주기에 다시 나간다.
     * true 여도 서버 도착이 보장되지는 않지만, 그건 알 방법이 없고
     * 서버가 event_id 로 멱등 처리하므로 유실보다 중복이 낫다.
     */
    const accepted = navigator.sendBeacon(
      COLLECT_ENDPOINT,
      new Blob([body], { type: 'application/json' }),
    );
    if (!accepted) requeue(batch, 'sendBeacon 큐 거절');
    return;
  }

  post(body, batch, token);
}

/**
 * 실제 전송 한 번.
 *
 * `token` 을 실었는데 401 이 오면 **헤더 없이 한 번만 다시 보낸다.**
 * 비로그인 로그도 수집하기로 했으므로(데이터 파트 합의 2026-09-10) 401 은
 * "이 토큰이 만료·손상됐다" 는 뜻이지 "이 로그가 필요 없다" 는 뜻이 아니다.
 * 토큰이 15분이라 조금만 긴 세션이면 반드시 만료되는데, 그때 배치를 통째로
 * 버리면 그 사람의 로그가 그 시점부터 끊긴다. 익명으로라도 남기는 편이 낫다.
 *
 * 재시도는 한 번뿐이다(`retriedAnonymously`). 헤더 없이 보낸 요청이 또 401 이면
 * 그건 토큰 문제가 아니라 서버가 익명을 막고 있다는 뜻이라, 다시 보내도 같다.
 */
function post(body: string, batch: LogEnvelope[], token: string | null, retriedAnonymously = false): void {
  const request = fetch(COLLECT_ENDPOINT, {
    method: 'POST',
    headers: token
      ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
      : { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  })
    .then((response) => {
      if (response.status === 401 && token && !retriedAnonymously) {
        post(body, batch, null, true);
        return;
      }

      if (response.ok) {
        // 413 으로 줄었던 배치 크기를 천천히 되돌린다
        if (sendBatchSize < MAX_BATCH_SIZE) {
          sendBatchSize = Math.min(MAX_BATCH_SIZE, sendBatchSize + 10);
        }
        return;
      }

      if (response.status === 413) {
        // 같은 크기로 다시 보내면 같은 이유로 거절당한다. 반으로 쪼갠다
        sendBatchSize = Math.max(1, Math.floor(sendBatchSize / 2));
        requeue(batch, `HTTP 413 — 배치를 ${sendBatchSize}건으로 축소`);
        return;
      }

      if (RETRYABLE_STATUS.has(response.status)) {
        /**
         * 429 의 Retry-After(초)를 존중한다.
         * 서버가 "이만큼 쉬라" 고 말해줬는데 5초마다 두드리면 포화를 키운다.
         */
        const retryAfter = Number(response.headers.get('Retry-After'));
        const delayMs =
          response.status === 429 && Number.isFinite(retryAfter) && retryAfter > 0
            ? retryAfter * 1000
            : undefined;
        requeue(batch, `HTTP ${response.status}`, delayMs);
        return;
      }

      /**
       * 400 / 403 / 404 / 422 등 — 요청 자체가 잘못됐다. 버린다.
       * 재시도해도 결과가 같아서, 되돌리면 같은 배치가 영원히 돈다.
       */
      if (!dropWarned.has(response.status)) {
        dropWarned.add(response.status);
        console.error(`[log] HTTP ${response.status} — 재시도하지 않고 ${batch.length}건을 버림`);
      }
    })
    .catch((error: unknown) => {
      // 네트워크 오류·타임아웃은 지나가는 문제라 다시 보낸다
      requeue(batch, error instanceof Error ? error.message : '네트워크 오류');
    });

  inFlight.add(request);
  void request.finally(() => inFlight.delete(request));
}

/**
 * 실패한 배치를 큐 앞에 되돌린다.
 *
 * 서버가 `event_id` 기준으로 중복을 걸러주기로 해서 재시도가 안전하다.
 * 다만 수집 서버가 계속 죽어 있으면 큐가 무한히 커지므로 상한을 둔다.
 * 오래된 것부터 버린다. 최근 행동이 분석에 더 쓸모가 있다.
 */
function requeue(batch: LogEnvelope[], reason: string, delayMs?: number): void {
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

  // 서버가 Retry-After 로 지정한 시간이 있으면 그때까지 기다린다.
  // 그때까지는 새 이벤트가 와도 즉시 전송을 걸지 않는다
  backoffUntil = Date.now() + (delayMs ?? FLUSH_INTERVAL_MS);

  /**
   * 이미 걸려 있는 타이머가 더 이르면 걷어낸다.
   * flush 가 배치를 쪼개며 미리 걸어둔 5초 타이머가 남아 있으면, 예약이
   * 그쪽에 막혀 Retry-After 가 무시된다 (실측: 9초 지시에 5초 재시도).
   */
  if (delayMs !== undefined && flushTimer !== undefined) {
    window.clearTimeout(flushTimer);
    flushTimer = undefined;
  }
  scheduleFlush(delayMs);
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
