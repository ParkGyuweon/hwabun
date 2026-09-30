import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import SiteHeader from './components/layout/SiteHeader';
import LiveLog from './components/devtools/LiveLog';
import { isPreviewMode } from './lib/devtools';
import Breadcrumb from './components/product/Breadcrumb';
import ProductDetailPage from './pages/ProductDetailPage';
import ProductListPage from './pages/ProductListPage';
import CartPage from './pages/CartPage';
import TermsPage from './pages/TermsPage';
import PrivacyPage from './pages/PrivacyPage';
import SiteFooter from './components/layout/SiteFooter';
import ActivityNotice from './components/legal/ActivityNotice';
import { LEGAL_QUERY, legalPageFromState, legalPageFromUrl } from './lib/legalRoute';
import type { LegalPage } from './lib/legalRoute';
import { setLoggerContext, startPageView, startSession, track } from './lib/logger';
import { setTraitProfile } from './lib/trait';
import { EVENT_CURRENCY, createOrderId, orderTotals, orderTotalsKrw, toOrderItems, unitMoneyProps } from './lib/checkout';
import {
  canCheckoutOnBackend,
  checkoutOnBackend,
  clearBackendCart,
  confirmBackendOrder,
  createBackendOrder,
  fetchBackendReviews,
  hasMemberSession,
} from './lib/shopApi';
import { requestLogin } from './lib/loginPrompt';
import {
  PAYMENT_FAILED_EVENT_ENABLED,
  PAYMENT_PROVIDER,
  clearPendingPayment,
  isPaymentEnabled,
  parsePaymentReturn,
  paymentIdFor,
  requestKakaoPay,
  savePendingPayment,
  takePendingPayment,
} from './lib/payment';
import type { PaymentMethod } from './lib/payment';
import type { PlacedOrder } from './lib/checkout';
import { DEFAULT_STOREFRONT, applyStorefront, storefrontEventProps } from './lib/storefront';
import { backendCatalogState, catalogSnapshot, ensureBackendDetail, resolveProduct } from './lib/productRegistry';
import EmptyState from './components/common/EmptyState';
import { useCatalog, useDraft } from './hooks/useCatalog';
import { useAuth } from './hooks/useAuth';
import { isBehaviorLinked } from './lib/auth';
import { loadMemberProfile, profileToPersona, subscribeMemberProfile } from './lib/memberProfile';
import { MEMBER_WITHDRAWN_EVENT } from './lib/memberWithdraw';
import { useAuthorCounts, useProductReviews, useReviewSkinTypes } from './lib/reviewStore';
import personasData from './mocks/personas.sample.json';
import type { PersonaProfile } from './types/persona';
import type { Review } from './types/review';
import type { CartItem } from './types/cart';
import './styles/product-detail.css';
import './styles/product-list.css';
import './styles/cart.css';
// 시각 레이어. 위 셋 다음에 와야 한다 — 같은 셀렉터를 덧씌운다
import './styles/apple.css';
// 소상공인이 고른 진열 레이아웃·색. 맨 마지막 — data-storefront / data-theme 로 분기한다
import './styles/storefront.css';
// 푸터·약관 화면·첫 방문 안내. 진열 테마와 겹치는 셀렉터가 없다
import './styles/legal.css';

// 상품은 등록 저장소(초안 + 등록 + 시드 + 세포라)가 준다. 렌더 안에서는 useCatalog() 를 쓴다
/**
 * 데이터 파트가 만든 PA 대역 100명을 그대로 쓴다.
 * 리뷰에서 파생시키던 예전 방식은 persona_id 가 author_id 라 페르소나 표와
 * 조인이 되지 않았다. scripts/build-personas.ts 가 이 파일을 만든다.
 */
const personas = personasData as unknown as PersonaProfile[];

/** 상세 페이지에서 유사·추천 자리에 올릴 개수 */
const SIMILAR_SIZE = 6;

/**
 * 주문이 어디서 시작됐나. 주문 경로는 하나지만 **끝난 뒤 장바구니를 비울지**가 다르다.
 *   `cart`     장바구니 확인 화면의 주문 버튼 → 장바구니를 비운다
 *   `buy_now`  상품 상세의 "바로 구매" → 담아 둔 장바구니는 그대로 둔다
 */
type OrderOrigin = 'cart' | 'buy_now';

/** 스크롤 복원을 기다려주는 최대 시간. 이미지 배치가 늦어도 이 안에는 자리를 잡는다 */
const RESTORE_TIMEOUT_MS = 1500;

/** 첫 진입 주소에 상품이 있으면 그 상세로 시작한다 */
function initialProductId(): string | null {
  const requested = new URLSearchParams(window.location.search).get('product');
  return requested && resolveProduct(requested, catalogSnapshot()) ? requested : null;
}

/**
 * 첫 진입 주소에 페르소나가 있으면 그 사람으로 시작한다.
 *
 * 페르소나를 화면 상태로만 들고 있으면 새 탭은 늘 첫 번째 사람으로 열린다. 그래서
 * 부하 생성기는 화면을 먼저 열고 드롭다운으로 사람을 바꾸는데, **바꾸기 전에 이미
 * 렌더된 화면의 이벤트가 첫 번째 사람 앞으로 기록된다.** 딥링크(`?product=`)로 상세에
 * 바로 들어가면 그 화면의 노출과 추천 스냅샷까지 남의 것이 된다.
 * (PA 100명 실행에서 49,749건 중 21,767건이 PA00001 로 쏠렸다 — 데이터 파트 실측)
 *
 * 전환을 앞당기는 것으로는 못 고친다. 뒤이은 이동이 선택을 되돌린다.
 * 그래서 상품과 똑같이 **주소로 정한다.** 목록에 없는 값은 무시하고 기본값으로 가는
 * 규칙도 `initialProductId` 와 같다.
 *
 * `actor=synthetic` 계열과 달리 개발 서버로 제한하지 않는다. 이 값이 하는 일은 화면의
 * 페르소나 드롭다운과 똑같아서, 주소로 고르든 눌러서 고르든 결과가 다르지 않다.
 * 로그의 출처(actor_type)를 바꾸는 값이 아니므로 위장에 쓰일 여지도 없다.
 */
function initialPersonaId(): string {
  return requestedPersonaId() ?? personas[0]?.persona_id ?? '';
}

/**
 * **주소로 명시한** 페르소나. 없으면 null.
 *
 * `initialPersonaId` 와 갈라 두는 이유는 둘이 답해야 하는 질문이 다르기 때문이다.
 *
 *   화면  "스위처에 누구를 띄울까"      → 아무도 안 골랐어도 하나는 띄워야 한다
 *   로그  "이 이벤트는 누구 것인가"     → 아무도 안 골랐으면 **주인이 없다**
 *
 * 예전에는 둘 다 `personas[0]`(PA00001)로 떨어졌다. 그래서 **로그인도 안 하고 페르소나도 안 고른
 * 실제 방문자의 이벤트가 전부 PA00001 앞으로 기록됐다** (AI 파트 배포본 확인 2026-09-16).
 * 대시보드에서는 있지도 않은 PA 한 명이 크게 잡히고, 그 사람의 진짜 로그와 섞여 둘 다 못 쓰게 된다.
 *
 * 없는 사실을 만드는 것보다 비우는 쪽이 낫다. 계약도 `persona_id` 를 `["string", "null"]` 로
 * 허용한다 (`event-schema.json`).
 *
 * 러너는 영향을 받지 않는다. `?persona=` 없이 화면을 먼저 열고 스위처로 바꾸는 순서라
 * 전환 **전** 이벤트를 이미 게이트로 버린다 (`simulator/agents/agent_runner.py`).
 * 그 이벤트가 PA00001 대신 null 로 찍힐 뿐 버려지는 것은 같다.
 */
function requestedPersonaId(): string | null {
  const requested = new URLSearchParams(window.location.search).get('persona');
  return requested && personas.some((p) => p.persona_id === requested) ? requested : null;
}

/**
 * 로거에 먼저 꽂아 둔다.
 *
 * 자식 컴포넌트의 effect 는 부모(App)의 effect 보다 먼저 돈다. 그래서 `startSession` 이
 * 돌기 전에 진입 화면의 `recommendation_snapshot` 과 `scroll_depth` 두 건이 이미 나간다.
 * 그때 persona 가 비어 있으면 **딥링크로 들어온 방문의 첫 노출이 주인 없는 로그**가 된다.
 * 추천 스냅샷은 그 사람 기준으로 계산해 놓고 누구 것인지는 안 적히는 셈이라 더 나쁘다.
 *
 * 모듈을 읽을 때 한 번 정한다 — 로거가 synthetic 표시를 정하는 방식과 같다.
 */
setLoggerContext({ personaId: requestedPersonaId() });

/**
 * 라우터는 아직 붙이지 않았다.
 *
 * 화면이 목록과 상세 둘뿐이라 상태 전환으로 충분하다.
 * 다만 **뒤로가기는 그 자체가 행동 신호**이므로 History API 는 쓴다.
 * 목록으로 돌아간 것이 브라우저 뒤로가기인지 화면 안의 링크인지 구분해서 남긴다.
 */
export default function App() {
  // effect 로 늦게 세팅하면 목록을 한 번 그린 뒤 상세로 바뀌어서
  // page_view 가 목록·상세 두 번 찍힌다. 처음부터 올바른 값으로 시작한다.
  const [productId, setProductId] = useState<string | null>(initialProductId);

  const [personaId, setPersonaId] = useState(initialPersonaId);
  /**
   * 이 페르소나를 **누가 골랐나.** 주소(`?persona=`)나 스위처로 고른 것만 참이다.
   * 거짓이면 화면은 기본 페르소나로 그리되 로그에는 신원을 싣지 않는다 (`requestedPersonaId` 주석).
   */
  const [personaChosen, setPersonaChosen] = useState(() => requestedPersonaId() !== null);
  // 브랜드가 대시보드에서 등록·수정하면 새로고침 없이 따라온다 (lib/productRegistry)
  const products = useCatalog();
  const draft = useDraft();
  /**
   * 주소의 상품이 나중에 카탈로그에 들어오면 그때 연다.
   * 등록 폼의 미리보기(iframe)가 초안(`?product=DRAFT`)보다 먼저 로드되는 경우다.
   * 반대로 초안이 지워지면(폼을 떠남) 목록으로 돌아간다.
   */
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('product');
    if (!requested) return;
    const exists = resolveProduct(requested, products, draft) !== null;
    if (exists && productId === null) setProductId(requested);
    if (!exists && productId === requested) setProductId(null);
  }, [products, draft, productId]);
  // 헤더 메뉴와 목록 탭이 같은 값을 바꾸므로 여기서 소유한다
  const [listCategory, setListCategory] = useState('all');
  /** 장바구니 화면이 열려 있는지. 상품 상태와 별개로 겹쳐 둔다 */
  const [cartOpen, setCartOpen] = useState(false);
  /**
   * 약관 화면(`?terms=1` · `?privacy=1`). 장바구니처럼 **아래 화면 위에 겹쳐 둔다** —
   * 상품·장바구니 상태는 그대로 두고, 뒤로가기로 닫으면 보던 화면으로 돌아간다.
   * 아래 상태를 건드리지 않으므로 약관을 여닫는 것만으로 page_view 가 새로 찍히지 않는다
   * (page_type 계약에 약관 화면 값이 없다 — types/log PageType).
   */
  const [legalPage, setLegalPage] = useState<LegalPage | null>(() => legalPageFromUrl());
  /**
   * 장바구니. 서버가 없어 메모리에만 산다.
   * 이 화면의 목적은 view_cart / remove_from_cart 신호다 (조사 7-2).
   */
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  /**
   * 회원 탈퇴가 끝나면 장바구니를 비운다 (lib/memberWithdraw). 로그아웃은 장바구니를 그대로 두지만,
   * 탈퇴한 사람이 담은 것을 다음 손님이 이어받게 두지 않는다.
   */
  useEffect(() => {
    const onWithdrawn = () => setCartItems([]);
    window.addEventListener(MEMBER_WITHDRAWN_EVENT, onWithdrawn);
    return () => window.removeEventListener(MEMBER_WITHDRAWN_EVENT, onWithdrawn);
  }, []);
  /** 다음 page_view 가 어떻게 발생했는지. 뒤로가기와 화면 안 이동을 구분한다 */
  const navigationSourceRef = useRef('in_app');

  /**
   * 완료된 테스트 주문. 완료 화면과 설문이 이 값으로 뜬다.
   *
   * 결제 연동은 없다. 여기서 만드는 것은 전환 신호뿐이다 — 담기까지만 있는 로그로는
   * "담고 안 산 사람" 과 "산 사람" 이 같은 무게로 세어진다.
   */
  const [order, setOrder] = useState<PlacedOrder | null>(null);
  /** 결제창까지 갔다가 실패·취소한 이유. 장바구니는 그대로 두고 다시 시도할 수 있게 한다 */
  const [paymentError, setPaymentError] = useState<string | null>(null);
  /** 결제창이 떠 있거나 서버 확인 중. 버튼 연타 방지 */
  const [paying, setPaying] = useState(false);
  /**
   * 주문 잠금. `paying` 은 다음 렌더에야 바뀌어서, 빠른 두 번 클릭이 둘 다 통과해 서버 장바구니에 같은 상품이
   * 두 번 담기고 수량·금액이 두 배로 주문됐다. ref 는 바로 바뀌므로 두 번째 클릭을 그 자리에서 막는다.
   */
  const orderLockRef = useRef(false);
  /**
   * 결제는 끝났는데 확인만 실패한 주문. 다시 누르면 결제창을 또 열지 않고 **확인부터** 다시 한다 —
   * 같은 결제 번호로 결제창을 다시 열면 결제사가 거절하고, 새 번호로 열면 두 번 결제된다.
   * `clientOrderId` · `sig` 는 같은 품목으로 다시 누를 때 같은 주문 번호를 쓰기 위해 둔다.
   */
  const unconfirmedPaymentRef = useRef<{ orderId: string; paymentId: string; clientOrderId?: string; sig: string } | null>(null);
  /** 백엔드 상품의 리뷰. 상품이 바뀔 때 받아 온다. 목 상품이면 빈 배열이고 샘플 리뷰를 쓴다 */
  const [backendReviews, setBackendReviews] = useState<Review[]>([]);
  /**
   * 주문 확인 단계에서 만든 주문 번호. `begin_checkout` 과 `purchase` 가 **같은 값**을
   * 실어야 "확인까지 갔다가 안 한 사람" 을 셀 수 있다.
   * ref 인 이유는 이 값이 화면을 바꾸지 않기 때문이다.
   */
  const pendingOrderIdRef = useRef<string | null>(null);
  /** 그 번호를 만들 때의 장바구니 내용. 내용이 바뀌었는데 같은 번호(=멱등키)로 주문하면 서버가 409 를 준다 */
  const pendingOrderSigRef = useRef<string>('');

  /**
   * 화면별로 마지막 스크롤 위치를 기억한다.
   *
   * 브라우저는 문서 이동일 때 이걸 알아서 해주지만, 이 앱은 주소만 바꾸고
   * 같은 문서를 다시 그리는 구조라 아무도 안 해준다.
   * 그대로 두면 목록 중간에서 상품을 열었을 때 그 상품도 중간부터 보인다.
   */
  const scrollPositionsRef = useRef(new Map<string, number>());
  /** 이번 화면 전환이 뒤로가기인지. 맞으면 맨 위가 아니라 이전 위치로 되돌린다 */
  const restoreScrollRef = useRef(false);
  /** 복원을 기다리는 도중 사용자가 직접 스크롤했는지. 그러면 복원을 포기한다 */
  const userScrolledRef = useRef(false);

  /** 목록·상세·장바구니를 구분하는 키. 스크롤 위치 저장에 쓴다 */
  const viewKey = legalPage ? `legal:${legalPage}` : cartOpen ? 'cart' : (productId ?? 'list');

  /**
   * 화면이 쓰는 페르소나. 둘 중 하나다.
   *   로그인 회원이 피부 정보를 채웠으면 → 그 프로필 (persona_id = accountId, 09-09 합의)
   *   아니면                              → 스위처가 고른 시뮬레이션 페르소나
   * 리뷰 필터 "내 피부 타입만" · "내 피부 타입 일치" 칩 · 추천 목의 피부 매칭이 전부 이 값을 본다.
   * 로그의 persona_id 도 로그인 중에는 회원 id 다 — 추천 요청과 행동 로그가 같은 식별자를 써야 추천 서버의
   * 세션 상태(좋아요 → 목록 반영)가 이어진다 (계약 recommendation-io-spec §5 · AI 파트 요청 2026-09-14 §1).
   */
  const member = useAuth('MEMBER');
  const getMemberProfile = useCallback(() => loadMemberProfile(member?.id), [member?.id]);
  const memberProfile = useSyncExternalStore(subscribeMemberProfile, getMemberProfile, getMemberProfile);
  const persona = useMemo(() => {
    const mine = member ? profileToPersona(member.id, memberProfile) : null;
    return mine ?? personas.find((item) => item.persona_id === personaId) ?? null;
  }, [personaId, member, memberProfile]);

  // 피부 타입을 아는 사용자는 concern 축에 고정 가점 (lib/trait.ts)
  useEffect(() => {
    setTraitProfile({ hasSkinProfile: persona !== null });
  }, [persona]);

  const product = useMemo(
    () => resolveProduct(productId, products, draft),
    [productId, products, draft],
  );

  // 샘플 리뷰는 상품별 조각으로 연 상품 것만 받는다 (lib/reviewStore). 백엔드 상품이면 안 받는다
  const { reviews: productReviews } = useProductReviews(product && product.source !== 'backend' ? product.product_id : null);
  const authorReviewCounts = useAuthorCounts();
  const reviewSkinTypes = useReviewSkinTypes();

  // 백엔드에만 있는 상품은 상세를 열 때 그 한 건만 받는다. 목록은 요약으로 그린다 (N+1 제거, 2026-09-14)
  useEffect(() => {
    ensureBackendDetail(productId);
  }, [productId, products]);

  /**
   * 백엔드에 있는 상품이면 **source 와 상관없이** 실제 리뷰를 받는다 (2026-09-21).
   *
   * 전에는 `source === 'backend'` 일 때만 불렀다. 그런데 프론트가 정적으로 아는 208개(SSAFY Beauty 8 + 세포라 200)는
   * `mergeWithLocal` 이 정적 사본의 `source`(seed_catalog)를 유지해서, 그 상품에 고객이 실제로 쓴 리뷰는
   * 서버에 저장되고도 화면에 한 번도 뜨지 않았다 (배포본 SB000007: API 1건 · 화면 0건, 유림님 제보).
   * "백엔드에 있는가" 는 `backend_brand_id` 가 말해 준다 (productRegistry 주석). 정적 세포라 리뷰는 그대로 두고 앞에 붙인다.
   */
  const inBackend = Boolean(product && (product.source === 'backend' || product.backend_brand_id));
  /** 상세에서 리뷰를 쓰면 올려서 백엔드 리뷰를 다시 받는다 */
  const [reviewNonce, setReviewNonce] = useState(0);
  useEffect(() => {
    if (!product || !inBackend) {
      setBackendReviews([]);
      return;
    }
    let alive = true;
    void fetchBackendReviews(product.product_id).then((rows) => {
      if (alive) setBackendReviews(rows);
    });
    return () => {
      alive = false;
    };
    // 상세가 늦게 도착하면 product 객체만 바뀌고 id 는 같다 — 그때 리뷰를 다시 부르지 않는다.
    // 백엔드 목록이 늦게 와서 inBackend 가 false → true 로 바뀌면 그때 한 번 부른다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product?.product_id, inBackend, reviewNonce]);

  /** 화면에 그리는 리뷰. 고객이 실제로 쓴 것(최신순)을 앞에, 정적 세포라 표본을 뒤에 */
  const shownReviews = useMemo(
    () => (product?.source === 'backend' ? backendReviews : backendReviews.length > 0 ? [...backendReviews, ...productReviews] : productReviews),
    [product?.source, backendReviews, productReviews],
  );

  /**
   * 장바구니에 담긴 상품. 추천 자리에서 뺀다.
   * 이미 담은 상품을 다시 추천하는 것은 자리 낭비이고, 아는 상품이라
   * 클릭률이 높게 나와 추천 CTR 지표도 왜곡한다. 빼면 다음 순위가 올라와 채워진다.
   */
  const cartProductIds = useMemo(
    () => new Set(cartItems.map((item) => item.product_id)),
    [cartItems],
  );

  /**
   * 유사 상품.
   * 같은 중분류에서 뽑는다. 대분류는 200개가 전부 Skincare 라 구분이 안 된다.
   */
  const similar = useMemo(() => {
    if (!product) return [];
    const key = product.category[1];
    return products
      .filter(
        (item) =>
          item.product_id !== product.product_id &&
          item.category[1] === key &&
          !cartProductIds.has(item.product_id),
      )
      .slice(0, SIMILAR_SIZE);
  }, [product, cartProductIds]);

  const openProduct = useCallback((nextId: string) => {
    window.history.pushState({ productId: nextId, cart: false }, '', `?product=${nextId}`);
    setLegalPage(null);
    setCartOpen(false);
    setProductId(nextId);
  }, []);

  const goHome = useCallback(() => {
    /*
     * 홈으로 가는 것은 상품 클릭이 아니다.
     * product_click 으로 남기면 product_id 가 null 인 클릭이 섞여서 상품별
     * 클릭 수와 노출 대비 클릭률이 어긋난다. 화면 이동으로 분리한다.
     */
    track('navigation_click', { target: 'home', entry_source: 'breadcrumb' });
    window.history.pushState({ productId: null, cart: false }, '', '/');
    setLegalPage(null);
    setCartOpen(false);
    setProductId(null);
  }, []);

  /**
   * 장바구니 열기. GA4 표준 퍼널의 view_cart 를 여기서 남긴다.
   * effect 에서 남기면 StrictMode 가 두 번 실행한다. 명시적 행동 지점에서만 찍는다.
   */
  const cartSummary = useCallback(
    () => ({
      item_count: cartItems.reduce((sum, item) => sum + item.quantity, 0),
      distinct_products: cartItems.length,
      // 원화 정가 합 + currency (계약 §4.5 view_cart 필수 · 2026-09-16)
      cart_value: orderTotalsKrw(cartItems).total,
      currency: EVENT_CURRENCY,
    }),
    [cartItems],
  );

  /**
   * 장바구니 요약은 뒤로가기로 들어올 때도 실어야 한다.
   * 열기 버튼에만 실으면 같은 view_cart 인데 진입 경로에 따라 필드가 있다 없다
   * 하게 되고, 분석하는 쪽이 장바구니 규모를 셀 수 없다.
   */
  const cartSummaryRef = useRef(cartSummary);
  cartSummaryRef.current = cartSummary;
  /** popstate 에서 "이미 장바구니를 보고 있었나" 를 읽는다. 약관을 닫고 장바구니로 돌아올 때 view_cart 를 두 번 세지 않게 */
  const cartOpenRef = useRef(cartOpen);
  cartOpenRef.current = cartOpen;

  const openCart = useCallback(() => {
    track('view_cart', cartSummary());
    window.history.pushState({ productId, cart: true }, '', '?cart=1');
    setLegalPage(null);
    setCartOpen(true);
  }, [cartSummary, productId]);

  /**
   * 약관 화면 열기. 아래 화면(상품·장바구니)은 history.state 에 그대로 실어 둔다 —
   * 뒤로가기의 popstate 가 그 값으로 보던 화면을 되살린다.
   * 이동 이벤트는 남기지 않는다. 약관 보기는 쇼핑 행동이 아니고, 새 target 값은 계약에 없다.
   */
  const openLegal = useCallback(
    (page: LegalPage) => {
      if (legalPage === page) return;
      window.history.pushState({ productId, cart: cartOpen, legal: page }, '', LEGAL_QUERY[page]);
      setLegalPage(page);
    },
    [productId, cartOpen, legalPage],
  );

  /** 같은 상품·옵션이면 수량을 합친다 */
  const addToCart = useCallback((item: CartItem) => {
    setCartItems((prev) => {
      const at = prev.findIndex(
        (p) => p.product_id === item.product_id && p.sku_id === item.sku_id,
      );
      if (at === -1) return [...prev, item];
      const next = [...prev];
      next[at] = { ...next[at], quantity: Math.min(99, next[at].quantity + item.quantity) };
      return next;
    });
  }, []);

  const changeCartQuantity = useCallback((item: CartItem, quantity: number) => {
    track('quantity_change', {
      product_id: item.product_id,
      quantity,
      entry_source: 'cart',
    });
    setCartItems((prev) =>
      prev.map((p) =>
        p.product_id === item.product_id && p.sku_id === item.sku_id ? { ...p, quantity } : p,
      ),
    );
  }, []);

  /** 조사 7-2: 담았다 뺀 것은 상품을 특정하는 가장 명확한 부정 신호다 */
  const removeFromCart = useCallback(
    (item: CartItem) => {
      // track 을 setState 업데이터 안에서 부르면 StrictMode 가 업데이터를
      // 두 번 실행할 때 이벤트도 두 번 나간다. 반드시 밖에서 계산한다
      const next = cartItems.filter(
        (p) => !(p.product_id === item.product_id && p.sku_id === item.sku_id),
      );
      track('remove_from_cart', {
        product_id: item.product_id,
        sku_id: item.sku_id,
        quantity: item.quantity,
        ...unitMoneyProps(item),
        cart_size_after: next.length,
      });
      setCartItems(next);
    },
    [cartItems],
  );

  /* ---------- 테스트 주문 ---------- */

  /**
   * 주문 확인 단계 진입.
   *
   * 주문 번호를 **여기서 한 번** 만든다. 확인 화면에서 되돌아갔다가 다시 들어와도
   * 같은 번호를 쓴다 — 그래야 한 번의 주문 시도가 한 건으로 남는다.
   */
  const beginCheckout = useCallback(() => {
    if (cartItems.length === 0) return;
    /*
     * 장바구니 내용(상품·옵션·수량)이 그대로면 같은 번호, 바뀌었으면 새 번호. 이 번호가 서버 `idempotencyKey` 라서
     * 내용이 다른데 같은 키로 보내면 409 "idempotency key reused" 가 온다 (계약 대조 2026-09-17 #3).
     */
    const sig = JSON.stringify(toOrderItems(cartItems));
    const unconfirmed = unconfirmedPaymentRef.current;
    const orderId = pendingOrderIdRef.current !== null && pendingOrderSigRef.current === sig
      ? pendingOrderIdRef.current
      // 결제 확인만 남은 같은 주문이 있으면 그 번호를 이어 쓴다 (모바일 복귀 뒤에는 위 ref 가 비어 있다)
      : unconfirmed?.clientOrderId && unconfirmed.sig === sig ? unconfirmed.clientOrderId : createOrderId();
    pendingOrderIdRef.current = orderId;
    pendingOrderSigRef.current = sig;

    const { total, paid } = orderTotalsKrw(cartItems);
    track('begin_checkout', {
      /*
       * 계약상 필수는 items[] 뿐이지만 order_id 를 같이 싣는다 — "확인까지 갔다가 안 산 사람" 을 세기 위해서다.
       * 다만 이 값은 **프론트 번호**다. purchase.order_id 는 서버가 발급한 번호라 둘이 다르다 (서버는 이 값을
       * idempotencyKey 로만 받는다). 그래서 둘 다 `client_order_id` 에 프론트 번호를 같이 실어 조인 키를 하나 둔다.
       */
      order_id: orderId,
      client_order_id: orderId,
      items: toOrderItems(cartItems),
      // 원화 정가 합. 할인 적용 합은 paid_value 로 덧붙인다 (계약 §4.5 · 2026-09-16)
      cart_value: total,
      paid_value: paid,
      currency: EVENT_CURRENCY,
    });
  }, [cartItems]);

  /** 확인 화면에서 되돌아감. 이벤트는 남기지 않는다 — 이탈은 begin_checkout 대비로 센다 */
  const cancelCheckout = useCallback(() => {}, []);

  /**
   * 주문 확정. **purchase 이벤트는 결제(또는 PAID 표시)가 끝난 뒤에만** 남긴다.
   * `order_id` 는 서버 주문 번호(백엔드 원장과 대조용)이고, begin_checkout 과의 조인은 `client_order_id`(프론트 번호)로 한다.
   * 결제 정보(payment_method · pg_provider · payment_id · paid_at)는 properties 에 덧붙인다. 계약 §6 필드 추가는 데이터 파트가
   * 넣기로 했고(2026-09-14), properties 는 열린 객체라 먼저 실어도 거절되지 않는다.
   */
  const finishOrder = useCallback(
    (placed: PlacedOrder, origin: OrderOrigin = 'cart') => {
      track('purchase', {
        order_id: placed.orderId,
        ...(placed.clientOrderId ? { client_order_id: placed.clientOrderId } : {}),
        items: placed.items,
        // 원화. order_value 는 정가 합(items[].unit_price × quantity), paid_value 는 실결제액 — 서버 주문이면 totalAmount 그대로
        order_value: placed.items.reduce((sum, it) => sum + it.unit_price * it.quantity, 0),
        paid_value: placed.paidKrw,
        currency: EVENT_CURRENCY,
        order_channel: placed.mode,
        payment_method: placed.payment_method ?? 'test',
        pg_provider: placed.payment_method === 'kakaopay' ? PAYMENT_PROVIDER : null,
        payment_id: placed.payment_id ?? null,
        paid_at: placed.paid_at ?? null,
      });
      setPaymentError(null);
      setOrder(placed);
      /*
       * 장바구니는 **장바구니 주문일 때만** 비운다. "바로 구매" 는 담아 둔 것과 무관한 주문이라,
       * 여기서 비우면 사용자가 모아 둔 장바구니가 산 적 없는 채로 사라진다.
       * 같은 이유로 확인 단계의 주문 번호(`pendingOrderIdRef`)도 건드리지 않는다.
       */
      if (origin === 'cart') {
        setCartItems([]);
        // 다음 주문은 새 번호를 받는다
        pendingOrderIdRef.current = null;
      } else {
        /*
         * 완료 화면과 구매 이유 설문은 장바구니 화면 안에 산다. 바로 구매는 상품 상세에서 시작하므로
         * 여기서 그 화면을 열어 주지 않으면 **주문이 끝났는지 알 수 없다** — 버튼만 잠깐 눌리고 만다.
         *
         * `view_cart` 는 남기지 않는다. 장바구니를 본 적이 없기 때문이다. 이걸 흘리면 GA4 퍼널의
         * 장바구니 단계가 실제보다 커지고, "담기 → 장바구니 → 주문" 이탈률이 흐려진다.
         */
        window.history.pushState({ productId: null, cart: true }, '', '?cart=1');
        setLegalPage(null);
        setCartOpen(true);
      }
    },
    [],
  );

  /** 결제 실패·취소. 장바구니는 그대로 두고 화면에 이유를 적고 `payment_failed` 를 남긴다 */
  const failPayment = useCallback((orderId: string, code: string, message: string, method: PaymentMethod, clientOrderId?: string) => {
    setPaymentError(message);
    if (PAYMENT_FAILED_EVENT_ENABLED) {
      track('payment_failed', {
        order_id: orderId,
        // begin_checkout(프론트 번호)과 이어 세기 위한 키. 서버 주문을 만들기 전에 실패하면 order_id 자체가 프론트 번호다
        ...(clientOrderId && clientOrderId !== orderId ? { client_order_id: clientOrderId } : {}),
        reason_code: code,
        payment_method: method,
      });
    }
  }, []);

  /**
   * 주문 한 건을 끝까지 보낸다. 장바구니 주문과 "바로 구매" 가 **같은 함수**를 탄다.
   *
   * 둘의 차이는 두 가지뿐이라 인자로 받는다.
   *   `source`  주문할 품목. 장바구니 주문은 장바구니 전부, 바로 구매는 그 상품 하나
   *   `origin`  끝난 뒤 장바구니를 비울지 (`cart` 만 비운다 — 바로 구매는 담아 둔 걸 건드리지 않는다)
   *
   * 경로를 두 벌로 나누지 않은 이유는, 결제·확인·실패 처리가 전부 같아야 하기 때문이다. 한쪽만
   * 고치면 "장바구니로는 되는데 바로 구매는 안 되는" 종류의 버그가 난다.
   */
  const sendOrder = useCallback(async (source: CartItem[], origin: OrderOrigin, localOrderId: string) => {
    // 잠금(orderLockRef)은 부르는 쪽(submitOrder · buyNow)이 이미 잡았다. 여기서 바로 부르지 않는다
    if (source.length === 0) return;
    const items = toOrderItems(source);
    const { count, total, paid } = orderTotals(source);
    const paidKrwLocal = orderTotalsKrw(source).paid;
    setPaymentError(null);

    /**
     * 장바구니가 전부 백엔드 상품이고 고객 로그인이 있으면 서버 주문이다. 결제 키가 있으면 카카오페이(포트원) 결제창 →
     * 서버 confirm, 없으면 예전처럼 /pay 로 PAID 표시. 그래야 피드백 API 의 "구매 이력" 조건이 성립한다.
     * 백엔드 주문으로 만들 수 없는 상품이나 비로그인 상태에서는 로컬 테스트 주문으로 우회하지 않고 실패를 표시한다.
     */
    if (canCheckoutOnBackend(source)) {
      /*
       * 서버 장바구니는 주문 직전에만 채워지는 임시 자리인데, `POST /api/orders` 는 요청 본문이 아니라 거기 든 것을
       * **전부** 주문한다 (CommerceController). 그래서 **어느 경로든** 주문 직전에 서버 카트를 비우고 이번 품목만 담는다.
       * 전에는 바로 구매만 비웠는데, 장바구니 주문도 앞선 시도가 실패해 남은 항목(품절 409 뒤의 잔여물, 결제 실패 뒤
       * 다시 담은 중복)이 다음 주문에 섞여 화면 합계와 다른 금액이 결제될 수 있었다 (계약 대조 2026-09-17 #2·#3).
       *
       * **못 비웠으면 주문하지 않는다** (백엔드 리뷰 2026-09-17). 비우기가 실패한 채로 진행하면 남아
       * 있던 상품까지 같이 결제된다. 조용히 덮지 않고 멈춘 이유를 화면에 띄운다.
       */
      {
        const cleared = await clearBackendCart();
        if (!cleared.ok) {
          failPayment(
            localOrderId,
            `cart_clear_${cleared.status}`,
            '주문을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.',
            isPaymentEnabled() ? 'kakaopay' : 'test',
            localOrderId,
          );
          return;
        }
      }
      if (isPaymentEnabled()) {
        setPaying(true);
        try {
          const created = await createBackendOrder(source, localOrderId);
          if (!created.ok) {
            failPayment(localOrderId, `order_${created.status}`, `주문을 만들지 못했습니다. ${created.reason}`, 'kakaopay', localOrderId);
            return;
          }
          /*
           * 같은 주문 번호로 다시 누르면 서버는 **이미 있는 주문**을 돌려준다. 앞선 시도에서 결제가 끝났으면
           * 결제창을 다시 열지 않는다 — 결제사가 같은 결제 번호를 거절해 "결제 실패" 로 보이기 때문이다.
           */
          const completePaid = (paymentId: string, paidAt: string | null) => {
            unconfirmedPaymentRef.current = null;
            finishOrder({
              orderId: created.orderId,
              clientOrderId: localOrderId,
              items,
              count,
              total,
              paid,
              mode: 'backend',
              note: null,
              payment_method: 'kakaopay',
              payment_id: paymentId,
              paid_at: paidAt ?? new Date().toISOString(),
              paidKrw: created.totalAmountKrw ?? paidKrwLocal,
            }, origin);
          };
          if (created.status === 'PAID') {
            completePaid(paymentIdFor(created.orderId), created.paidAt);
            return;
          }
          const unconfirmed = unconfirmedPaymentRef.current;
          if (unconfirmed && unconfirmed.orderId === created.orderId) {
            const again = await confirmBackendOrder(created.orderId, unconfirmed.paymentId);
            if (again.ok) {
              completePaid(unconfirmed.paymentId, again.paidAt);
              return;
            }
            // 409 는 "아직 결제되지 않음" 이다 — 그때만 아래에서 결제창을 연다. 나머지는 잠시 뒤 다시 확인하게 둔다
            if (again.status !== 409) {
              failPayment(created.orderId, `confirm_${again.status}`, '결제 확인이 아직 끝나지 않았습니다. 잠시 뒤 다시 눌러 주세요. 다시 눌러도 두 번 결제되지 않습니다.', 'kakaopay', localOrderId);
              return;
            }
            unconfirmedPaymentRef.current = null;
          }
          if (created.totalAmountKrw === null) {
            failPayment(created.orderId, 'no_total_amount', '결제 금액을 확인하지 못해 결제창을 열 수 없습니다. 잠시 후 다시 시도해 주세요.', 'kakaopay', localOrderId);
            return;
          }
          // 모바일은 결제창으로 페이지가 떠났다 돌아온다. 돌아와서 confirm 을 부르려면 여기 두어야 한다
          savePendingPayment({ orderId: created.orderId, clientOrderId: localOrderId, items, count, total, paid, totalAmountKrw: created.totalAmountKrw, origin });
          // 결제 정본은 서버 totalAmount(원화 정수). 화면 합계와 1원 차이가 나도 이벤트는 실제 결제액을 따른다
          const paidKrw = created.totalAmountKrw;
          const pay = await requestKakaoPay({
            orderId: created.orderId,
            totalAmountKrw: created.totalAmountKrw,
            orderName: `BLOOM 주문 ${count}건`,
            // 포트원 SDK 가 email 형식을 검증한다 — 개발용 세션(dev-…@local)처럼 형식이 아니면 빼고 보낸다
            customer: member
              ? { fullName: member.name, ...(/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(member.email) ? { email: member.email } : {}) }
              : undefined,
          });
          if (!pay.ok) {
            clearPendingPayment();
            failPayment(created.orderId, pay.code, pay.message, 'kakaopay', localOrderId);
            return;
          }
          const confirmed = await confirmBackendOrder(created.orderId, pay.paymentId);
          clearPendingPayment();
          if (!confirmed.ok) {
            unconfirmedPaymentRef.current = { orderId: created.orderId, paymentId: pay.paymentId, clientOrderId: localOrderId, sig: JSON.stringify(items) };
            failPayment(created.orderId, `confirm_${confirmed.status}`, '결제 확인을 마치지 못했습니다. 잠시 뒤 다시 눌러 주세요. 다시 눌러도 두 번 결제되지 않습니다.', 'kakaopay', localOrderId);
            return;
          }
          unconfirmedPaymentRef.current = null;
          finishOrder({
            orderId: created.orderId,
            clientOrderId: localOrderId,
            items,
            count,
            total,
            paid,
            mode: 'backend',
            note: null,
            payment_method: 'kakaopay',
            payment_id: pay.paymentId,
            paid_at: confirmed.paidAt ?? new Date().toISOString(),
            paidKrw,
          }, origin);
        } finally {
          setPaying(false);
        }
        return;
      }

      const r = await checkoutOnBackend(source, localOrderId);
      if (r.ok) {
        finishOrder({ orderId: r.orderId, clientOrderId: localOrderId, items, count, total, paid, mode: 'backend', note: null, payment_method: 'test', paidKrw: paidKrwLocal }, origin);
        return;
      }
      failPayment(localOrderId, `order_${r.status}`, `주문을 완료하지 못했습니다. ${r.reason}`, 'test', localOrderId);
      return;
    }

    /*
     * 서버 주문을 탈 수 없으면 **로컬 테스트 주문으로 우회하지 않고** 이유를 띄운다
     * (백엔드 요청 2026-09-15 §5 · 이 브랜치의 결정을 그대로 따른다).
     * 바로 구매도 같은 길이라 여기서 갈리지 않는다 — 막힌 이유는 origin 과 무관하다.
     */
    const message = source.some((i) => !i.variant_id)
      ? '지금 주문할 수 없는 상품이 장바구니에 있습니다.'
      : '결제하려면 로그인이 필요합니다.';
    failPayment(localOrderId, 'backend_checkout_required', message, 'test', localOrderId);
  }, [member, finishOrder, failPayment]);

  /**
   * 주문 버튼의 입구. **await 전에** 잠그고 `paying` 을 켠다 — 서버 장바구니를 비우고 다시 채운 뒤 주문하는
   * 흐름이라, 두 번째 클릭이 그 사이에 끼면 같은 상품이 두 번 담겨 두 배로 결제된다. 끝나면 무조건 푼다.
   */
  const submitOrder = useCallback(async (source: CartItem[], origin: OrderOrigin, localOrderId: string) => {
    if (source.length === 0 || orderLockRef.current) return;
    orderLockRef.current = true;
    setPaying(true);
    try {
      await sendOrder(source, origin, localOrderId);
    } finally {
      orderLockRef.current = false;
      setPaying(false);
    }
  }, [sendOrder]);

  /** 장바구니 확인 화면의 주문 버튼. 주문 번호는 `beginCheckout` 이 만든 것을 그대로 쓴다 */
  const placeOrder = useCallback(
    () => submitOrder(cartItems, 'cart', pendingOrderIdRef.current ?? createOrderId()),
    [submitOrder, cartItems],
  );

  /**
   * 상품 상세의 "바로 구매". 장바구니를 거치지 않고 **이 상품 하나만** 주문한다.
   *
   * 로그인이 없으면 여기서 멈추고 로그인 모달을 띄운다. 백엔드가 비회원 주문을 받지 않기 때문이다 —
   * `/api/cart/items` · `/api/orders` · `/pay` · `/confirm` 전부 `requireMember` 가 걸려 있다
   * (`CommerceController`). 담아 두고 마지막에 막히는 것보다 여기서 말하는 게 낫다.
   *
   * 주문 번호는 매번 새로 만든다. `pendingOrderIdRef` 는 장바구니 확인 단계의 번호라 공유하면
   * "확인까지 갔다가 안 산 사람" 집계가 섞인다.
   */
  const buyNow = useCallback(
    async (item: CartItem, addToCartProps: Record<string, unknown>) => {
      // 잠금 확인은 맨 앞에서, 잠그는 건 로그인 확인 뒤에 — 모달만 열고 끝나는 클릭이 잠금을 쥐고 있으면 안 된다
      if (orderLockRef.current) return;
      if (!hasMemberSession()) {
        /*
         * 여기서는 이벤트를 남기지 않는다. 새 이름(`buy_now_blocked` 같은)은 계약
         * (`event-schema.json` · 수집기 INTENTS)에 등록되기 전에는 `unregistered_event` 로 거절된다.
         */
        requestLogin('바로 구매하려면 로그인이 필요합니다. 로그인하면 이어서 주문할 수 있습니다.');
        return;
      }
      // 여기서부터 첫 await 까지는 동기라 두 번째 클릭이 끼어들 틈이 없다. 잠금은 await 바로 앞에서 잡는다
      // 결제 확인만 남은 같은 상품이면 그 주문 번호를 이어 쓴다 — 새 번호면 새 주문이 생겨 두 번 결제된다
      const unconfirmed = unconfirmedPaymentRef.current;
      const orderId = unconfirmed?.clientOrderId && unconfirmed.sig === JSON.stringify(toOrderItems([item]))
        ? unconfirmed.clientOrderId
        : createOrderId();
      const { total, paid } = orderTotalsKrw([item]);
      /*
       * 바로 구매도 퍼널을 전부 밟는다 — add_to_cart → begin_checkout → purchase.
       * 단계를 비우면 그 단계를 분모로 쓰는 비율이 1.0 을 넘는다 (ProductSummary.buyNow 주석).
       *
       * `add_to_cart` 는 **로그인 확인을 통과한 여기서** 남긴다. 위에서 모달만 열고 끝난 클릭은 담기도
       * 결제도 아니므로 아무 이벤트도 남기지 않는다 (리뷰 !286). 속성 모양은 담기 버튼과 같다 (ProductSummary).
       */
      track('add_to_cart', addToCartProps);
      track('begin_checkout', {
        order_id: orderId,
        client_order_id: orderId,
        items: toOrderItems([item]),
        cart_value: total,
        paid_value: paid,
        currency: EVENT_CURRENCY,
        entry_source: 'buy_now',
      });
      orderLockRef.current = true;
      setPaying(true);
      try {
        await sendOrder([item], 'buy_now', orderId);
      } finally {
        orderLockRef.current = false;
        setPaying(false);
      }
    },
    [sendOrder],
  );

  /**
   * 모바일 결제창(REDIRECTION)에서 돌아온 경우 — `/?order=…&pay=return`. 결제창을 열기 전에 둔 주문을 꺼내
   * confirm 을 부르고 완료 화면으로 간다. PC 위젯 경로는 여기 오지 않는다.
   */
  useEffect(() => {
    const ret = parsePaymentReturn();
    if (!ret) return;
    const pending = takePendingPayment(ret.orderId);
    window.history.replaceState({ productId: null, cart: true }, '', '?cart=1');
    setCartOpen(true);
    if (ret.code || !ret.paymentId) {
      failPayment(ret.orderId, ret.code ?? 'no_payment_id', ret.message ?? '결제가 완료되지 않았습니다.', 'kakaopay', pending?.clientOrderId);
      return;
    }
    if (!pending) {
      setPaymentError('결제는 됐지만 이 탭의 주문 정보를 찾지 못했습니다. 주문 내역에서 확인해 주세요.');
      return;
    }
    const paymentId = ret.paymentId;
    void confirmBackendOrder(pending.orderId, paymentId).then((confirmed) => {
      if (!confirmed.ok) {
        unconfirmedPaymentRef.current = { orderId: pending.orderId, paymentId, clientOrderId: pending.clientOrderId, sig: JSON.stringify(pending.items) };
        failPayment(pending.orderId, `confirm_${confirmed.status}`, '결제 확인을 마치지 못했습니다. 잠시 뒤 다시 눌러 주세요. 다시 눌러도 두 번 결제되지 않습니다.', 'kakaopay', pending.clientOrderId);
        return;
      }
      finishOrder({
        orderId: pending.orderId,
        clientOrderId: pending.clientOrderId,
        items: pending.items,
        count: pending.count,
        total: pending.total,
        paid: pending.paid,
        mode: 'backend',
        note: null,
        payment_method: 'kakaopay',
        payment_id: paymentId,
        paid_at: confirmed.paidAt ?? new Date().toISOString(),
        paidKrw: pending.totalAmountKrw,
        // 예전에 저장된 값에는 origin 이 없다 — 그때는 원래대로 장바구니 주문으로 본다
      }, pending.origin ?? 'cart');
    });
    // 첫 진입 한 번만. finishOrder/failPayment 는 안정적이다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitPurchaseReasons = useCallback(
    (reasons: string[]) => {
      if (!order) return;
      track('purchase_reason_select', {
        order_id: order.orderId,
        reasons,
        // 첫 번째로 고른 것을 주된 이유로 본다
        primary_reason: reasons[0],
        skipped: false,
      });
    },
    [order],
  );

  /**
   * 건너뛰기도 남긴다.
   * 응답률을 모르면 답변 분포를 전체 구매자의 것으로 읽는 실수를 한다.
   */
  const skipPurchaseReasons = useCallback(() => {
    if (!order) return;
    track('purchase_reason_select', { order_id: order.orderId, reasons: [], skipped: true });
  }, [order]);

  /**
   * 브라우저 뒤로/앞으로.
   *
   * 처음에는 이걸 scroll_backtrack 으로 남겼는데 잘못이었다.
   * 그 이벤트는 가중 -1.0 의 좌절 신호인데, 목록으로 돌아가는 것은
   * 정상적인 탐색이다. 정상 행동에 감점을 주면 추천이 틀어진다.
   *
   * 이동 자체는 page_view 가 이미 남기므로, 어떻게 왔는지만 속성으로 구분한다.
   */
  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const next = (event.state?.productId as string | null | undefined) ?? null;
      const nextCart = Boolean(event.state?.cart);
      const nextLegal = legalPageFromState(event.state?.legal);
      setLegalPage(nextLegal);
      // 약관을 열고 닫는 것은 아래 화면이 바뀌지 않는다. 아래 화면이 그대로면 page_view·view_cart 를 다시 남기지 않는다
      navigationSourceRef.current = 'history_back';
      // 뒤로 온 화면은 보던 자리에서 이어봐야 한다
      restoreScrollRef.current = true;
      if (nextCart && !nextLegal && !cartOpenRef.current) {
        track('view_cart', {
          ...cartSummaryRef.current(),
          navigation_source: 'history_back',
        });
      }
      setCartOpen(nextCart);
      setProductId(next);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  /**
   * actor_type 은 로거가 진입 주소를 보고 스스로 정한다 (syntheticContextFromUrl).
   * 여기서 'user' 로 덮으면 부하 생성기의 방문까지 실사용자로 남는다.
   */
  useEffect(() => {
    /*
     * 등록 폼 미리보기(iframe)에서 나온 로그는 소비자 행동이 아니다. environment 로 구분한다.
     *
     * **미리보기가 아닐 때는 건드리지 않는다.** 예전에는 여기서 `'local'` 로 덮어써서, 로거가
     * 빌드 모드로 정한 값(`production`)이 마운트 직후 지워졌다 — 배포본 이벤트가 전부 `local` 로
     * 나간 원인이다 (AI 파트 배포본 확인 2026-09-16). 기본값은 로거가 안다 (`lib/logger.ts`).
     */
    if (new URLSearchParams(window.location.search).get('preview') === '1') {
      setLoggerContext({ environment: 'preview' });
    }
  }, []);

  /**
   * 쇼핑몰 진열. **하나로 고정이다.**
   *
   * 올리브영·세포라처럼 소비자가 보는 몰이 하나이고, 브랜드는 거기에 상품을 등록하고
   * 대시보드만 받는다. 브랜드가 진열을 고르던 화면은 없앴다. 진열 값은 로그에 계속 실어
   * 두는데, 나중에 플랫폼이 진열을 바꿀 때 그 전후를 비교하려면 이벤트에 남아 있어야 한다.
   */
  const storefront = DEFAULT_STOREFRONT;

  useEffect(() => {
    applyStorefront(storefront);
    setLoggerContext({ storefront: storefrontEventProps(storefront) });
  }, [storefront]);

  /**
   * 스크롤 복원을 브라우저에서 가져온다.
   *
   * 기본값('auto')이면 뒤로가기 때 브라우저가 복원을 시도하는데,
   * 그 시점에는 아직 새 화면이 그려지기 전이라 문서가 짧아서 엉뚱한 곳에 멈춘다.
   * 우리가 직접 하는 편이 정확하다.
   *
   * 첫 진입 상태도 여기서 심는다. `?product=` 로 바로 들어온 뒤 뒤로가기를 눌렀을 때
   * state 가 비어 있으면 목록으로 못 돌아간다.
   */
  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = 'manual';
    window.history.replaceState({ productId: initialProductId(), legal: legalPageFromUrl() }, '', window.location.href);

    return () => {
      window.history.scrollRestoration = previous;
    };
  }, []);

  /**
   * 스크롤할 때마다 현재 화면의 위치를 기록해 둔다.
   *
   * 화면을 떠날 때 한 번만 읽으면 될 것 같지만 안 된다.
   * React 는 useLayoutEffect 의 정리 함수를 DOM 을 이미 바꾼 뒤에 실행해서,
   * 그 시점의 `window.scrollY` 는 새 화면 높이에 맞춰 잘려 있다.
   * 긴 상세에서 짧은 목록으로 갈 때 2500 이 1499 로 줄어든 채 저장됐다.
   */
  useEffect(() => {
    const positions = scrollPositionsRef.current;
    const key = viewKey;

    const remember = () => positions.set(key, window.scrollY);
    remember();

    window.addEventListener('scroll', remember, { passive: true });
    return () => window.removeEventListener('scroll', remember);
  }, [viewKey]);

  /**
   * 새 화면은 맨 위에서, 뒤로 온 화면은 보던 자리에서 시작한다.
   * 그리기 전에 옮겨야 중간 위치가 한 프레임 비쳤다 사라지는 일이 없다.
   */
  useLayoutEffect(() => {
    if (!restoreScrollRef.current) {
      window.scrollTo(0, 0);
      return;
    }
    restoreScrollRef.current = false;

    const target = scrollPositionsRef.current.get(viewKey) ?? 0;
    window.scrollTo(0, target);
    if (target === 0) return;

    /**
     * 한 번으로는 모자란다.
     *
     * 이 시점의 문서는 아직 이미지 자리가 잡히기 전이라 실제보다 짧다.
     * 브라우저는 문서 끝을 넘는 스크롤을 잘라내므로 원하는 위치보다 위에 멈춘다.
     * 문서가 그 위치를 담을 만큼 길어질 때까지 계속 시도한다.
     */
    const deadline = Date.now() + RESTORE_TIMEOUT_MS;
    let raf = 0;

    const canReach = () =>
      document.documentElement.scrollHeight - window.innerHeight >= target - 1;

    const retry = () => {
      // 기다리는 동안 사용자가 직접 스크롤했으면 그쪽을 존중한다
      if (userScrolledRef.current) return;

      if (canReach()) {
        window.scrollTo(0, target);
        return;
      }
      // 문서가 아직 짧으면 일단 갈 수 있는 데까지 가 두고 계속 늘어나길 기다린다
      window.scrollTo(0, target);
      if (Date.now() < deadline) raf = requestAnimationFrame(retry);
    };

    userScrolledRef.current = false;
    const onUserScroll = (event: Event) => {
      // 우리가 부른 scrollTo 가 아니라 사용자가 굴린 것만 잡는다
      if (event.isTrusted) userScrolledRef.current = true;
    };
    window.addEventListener('wheel', onUserScroll, { passive: true });
    window.addEventListener('touchmove', onUserScroll, { passive: true });
    window.addEventListener('keydown', onUserScroll);

    raf = requestAnimationFrame(retry);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('wheel', onUserScroll);
      window.removeEventListener('touchmove', onUserScroll);
      window.removeEventListener('keydown', onUserScroll);
    };
  }, [viewKey]);

  /** 탭 제목. 히스토리 목록에도 이 값이 남는다 */
  useEffect(() => {
    document.title = legalPage
      ? `${legalPage === 'terms' ? '이용약관' : '개인정보처리방침'} | BLOOM`
      : product
        ? `${product.product_name} - ${product.brand_name} | BLOOM`
        : 'BLOOM';
  }, [product, legalPage]);

  /**
   * 식별자가 바뀌면 새 방문으로 본다.
   * 로그인 회원이면 회원 id, 아니면 스위처 페르소나 id — 추천 요청(`persona.persona_id`)과 같은 값이어야
   * `wishlist_toggle` 이 추천 서버의 그 사람 상태에 쌓인다. 로그인·로그아웃이 곧 세션 경계다 (`login` 이벤트 시점).
   * 세션의 첫 page_view 가 session_start 와 page_view_id 를 공유해야 해서
   * 지금 보고 있는 화면 정보를 함께 넘긴다. startSession 은 같은 식별자면
   * 아무것도 하지 않으므로 productId 변경으로 다시 실행돼도 무해하다.
   */
  // 로그인 회원이 최우선. 아니면 **고른** 페르소나. 둘 다 없으면 주인 없는 방문이라 null 이다.
  // 가입 때 기록 연결에 동의하지 않은 회원은 회원 id 를 싣지 않는다 (logger 도 토큰을 빼고 보낸다)
  const linkedMemberId = member && isBehaviorLinked(member) ? member.id : null;
  const logIdentity = linkedMemberId ?? (personaChosen ? personaId || null : null);
  useEffect(() => {
    setLoggerContext({
      pageType: cartOpen ? 'cart' : productId ? 'product_detail' : 'product_list',
    });
    startSession(logIdentity, cartOpen ? null : productId);
  }, [logIdentity, productId, cartOpen]);

  // 목록과 상세는 다른 page_type 이다. 화면이 바뀔 때마다 새 페이지 조회로 남긴다
  useEffect(() => {
    setLoggerContext({
      pageType: cartOpen ? 'cart' : productId ? 'product_detail' : 'product_list',
    });
    // 장바구니는 특정 상품의 화면이 아니다
    startPageView(cartOpen ? null : productId, navigationSourceRef.current);
    navigationSourceRef.current = 'in_app';
  }, [productId, cartOpen]);

  /*
   * 등록 폼 미리보기(`?preview=1`, 대시보드 iframe)는 **상세 페이지 본문만** 그린다. 헤더·프로모 띠·페르소나 스위처·
   * 로그인·로그 창은 쇼핑몰의 껍데기지 상품이 아니다 — 사장님이 보려는 건 "내 상품이 어떻게 보이나" 지 사이트 전체가
   * 아니다 (2026-09-18). 담기·구매도 미리보기에서는 아무 일도 하지 않는다.
   */
  const preview = isPreviewMode();
  /*
   * 주소의 `?product=` 가 카탈로그에 끝내 없으면(오타·내린 상품) 조용히 목록으로 떨구지 않고 "없는 상품" 을 알린다.
   * 백엔드 목록이 아직 오는 중이면 판정을 미룬다 — 백엔드에만 있는 상품은 목록이 온 뒤에 열린다 (위 effect).
   * 미리보기는 초안이 늦게 오거나 지워지는 게 정상이라 제외한다.
   */
  const requestedProductId = new URLSearchParams(window.location.search).get('product');
  const catalogState = backendCatalogState();
  const productMissing =
    !preview &&
    !cartOpen &&
    productId === null &&
    requestedProductId !== null &&
    catalogState !== 'idle' &&
    catalogState !== 'loading' &&
    // 목록이 막 와서 effect 가 곧 열어 줄 상품이면 "없음" 을 한 프레임도 비추지 않는다
    resolveProduct(requestedProductId, products, draft) === null;
  return (
    <>
      {preview ? null : (
      <SiteHeader
        personas={personas}
        persona={persona}
        onPersonaChange={(id: string) => {
          setPersonaId(id);
          setPersonaChosen(true);
        }}
        onHome={goHome}
        onOpenProduct={openProduct}
        cartCount={cartItems.reduce((sum, item) => sum + item.quantity, 0)}
        onCart={openCart}
      />
      )}

      {legalPage === 'terms' && !preview ? (
        <TermsPage />
      ) : legalPage === 'privacy' && !preview ? (
        <PrivacyPage />
      ) : cartOpen ? (
        <CartPage
          items={cartItems}
          onQuantityChange={changeCartQuantity}
          onRemove={removeFromCart}
          onSelectProduct={openProduct}
          onContinue={() => {
            setOrder(null);
            goHome();
          }}
          onBeginCheckout={beginCheckout}
          onCancelCheckout={cancelCheckout}
          onPlaceOrder={placeOrder}
          order={order}
          paymentEnabled={isPaymentEnabled() && canCheckoutOnBackend(cartItems)}
          paymentError={paymentError}
          paying={paying}
          onSurveySubmit={submitPurchaseReasons}
          onSurveySkip={skipPurchaseReasons}
        />
      ) : product ? (
        <>
          {preview ? null : <Breadcrumb items={product.category} onHome={goHome} />}
          <ProductDetailPage
            product={product}
            reviews={shownReviews}
            authorReviewCounts={authorReviewCounts}
            similar={similar}
            persona={persona}
            onSelectProduct={openProduct}
            onAddToCart={preview ? () => undefined : addToCart}
            onBuyNow={preview ? () => undefined : buyNow}
            buying={paying}
            onReviewWritten={() => setReviewNonce((n) => n + 1)}
          />
        </>
      ) : productMissing ? (
        <main className="page cart">
          <div className="cart__empty">
            <EmptyState message="상품을 찾을 수 없습니다. 판매가 끝났거나 주소가 바뀌었을 수 있습니다." />
            <button type="button" className="cart__continue" onClick={goHome}>
              상품 목록으로 가기
            </button>
          </div>
        </main>
      ) : (
        <ProductListPage
          products={products}
          reviewSkinTypes={reviewSkinTypes}
          persona={persona}
          memberId={member?.id ?? null}
          memberProfile={memberProfile}
          onSelectProduct={openProduct}
          onAddToCart={addToCart}
          cartProductIds={cartProductIds}
          category={listCategory}
          onCategoryChange={setListCategory}
        />
      )}

      {preview ? null : <SiteFooter onOpenLegal={openLegal} />}
      {preview ? null : <ActivityNotice onOpenPrivacy={() => openLegal('privacy')} />}
      {/* 우하단 실시간 행동 기록 · 늘 켜짐 (2026-09-29 새로 만듦). 상품 등록 미리보기에는 없다 */}
      {/* 로그인한 고객에게만 보인다 (2026-09-30) */}
      {!preview && member ? <LiveLog /> : null}
    </>
  );
}
