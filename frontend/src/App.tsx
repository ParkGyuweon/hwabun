import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import SiteHeader from './components/layout/SiteHeader';
import LogPanel from './components/devtools/LogPanel';
import { isDevtoolsOn } from './lib/devtools';
import Breadcrumb from './components/product/Breadcrumb';
import ProductDetailPage from './pages/ProductDetailPage';
import ProductListPage from './pages/ProductListPage';
import CartPage from './pages/CartPage';
import { setLoggerContext, startPageView, startSession, track } from './lib/logger';
import { setTraitProfile } from './lib/trait';
import { createOrderId, orderTotals, toOrderItems } from './lib/checkout';
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
  requestKakaoPay,
  savePendingPayment,
  takePendingPayment,
} from './lib/payment';
import type { PaymentMethod } from './lib/payment';
import type { PlacedOrder } from './lib/checkout';
import { DEFAULT_STOREFRONT, applyStorefront, storefrontEventProps } from './lib/storefront';
import { catalogSnapshot, ensureBackendDetail, resolveProduct } from './lib/productRegistry';
import { useCatalog, useDraft } from './hooks/useCatalog';
import { useAuth } from './hooks/useAuth';
import { loadMemberProfile, profileToPersona, subscribeMemberProfile } from './lib/memberProfile';
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

/**
 * 헤더 메뉴에 걸 카테고리.
 * 데이터에 실제로 있는 중분류만 쓴다. 상품 수가 많은 순서.
 */
const HEADER_CATEGORIES = (() => {
  const counts = new Map<string, number>();
  // 헤더 메뉴는 시작 시점 카탈로그로 정한다. 등록 상품은 기존 중분류 안에 들어오므로 메뉴가 바뀌지 않는다
  for (const p of catalogSnapshot()) {
    const key = p.category[1];
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([name]) => name);
})();

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
   * 장바구니. 서버가 없어 메모리에만 산다.
   * 이 화면의 목적은 view_cart / remove_from_cart 신호다 (조사 7-2).
   */
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
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
  /** 백엔드 상품의 리뷰. 상품이 바뀔 때 받아 온다. 목 상품이면 빈 배열이고 샘플 리뷰를 쓴다 */
  const [backendReviews, setBackendReviews] = useState<Review[]>([]);
  /**
   * 주문 확인 단계에서 만든 주문 번호. `begin_checkout` 과 `purchase` 가 **같은 값**을
   * 실어야 "확인까지 갔다가 안 한 사람" 을 셀 수 있다.
   * ref 인 이유는 이 값이 화면을 바꾸지 않기 때문이다.
   */
  const pendingOrderIdRef = useRef<string | null>(null);

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
  const viewKey = cartOpen ? 'cart' : (productId ?? 'list');

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

  useEffect(() => {
    if (!product || product.source !== 'backend') {
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
    // 상세가 늦게 도착하면 product 객체만 바뀌고 id 는 같다 — 그때 리뷰를 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product?.product_id, product?.source]);

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
    setCartOpen(false);
    setProductId(null);
  }, []);

  /** 헤더 메뉴로 카테고리를 고르면 목록으로 돌아가 그 카테고리를 펼친다 */
  const selectCategory = useCallback((category: string) => {
    track('filter_change', { filter_kind: 'category', filter_value: category, from: 'header' });
    setListCategory(category);
    window.history.pushState({ productId: null, cart: false }, '', '/');
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
      cart_value: cartItems.reduce((sum, item) => sum + item.price_usd * item.quantity, 0),
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

  const openCart = useCallback(() => {
    track('view_cart', cartSummary());
    window.history.pushState({ productId, cart: true }, '', '?cart=1');
    setCartOpen(true);
  }, [cartSummary, productId]);

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
        price_usd: item.price_usd,
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
    const orderId = pendingOrderIdRef.current ?? createOrderId();
    pendingOrderIdRef.current = orderId;

    const { total, paid } = orderTotals(cartItems);
    track('begin_checkout', {
      // 계약상 필수는 items[] 뿐이지만 order_id 를 같이 싣는다.
      // 이게 없으면 "확인까지 갔다가 안 산 사람" 을 purchase 와 이어 셀 수 없다
      order_id: orderId,
      items: toOrderItems(cartItems),
      cart_value: Number(total.toFixed(2)),
      // 할인 적용 합계. cart_value(정가)의 뜻은 그대로 두고 덧붙인다
      paid_value: Number(paid.toFixed(2)),
      currency: 'USD',
    });
  }, [cartItems]);

  /** 확인 화면에서 되돌아감. 이벤트는 남기지 않는다 — 이탈은 begin_checkout 대비로 센다 */
  const cancelCheckout = useCallback(() => {}, []);

  /**
   * 주문 확정. **purchase 이벤트는 결제(또는 PAID 표시)가 끝난 뒤에만** 남긴다 — begin_checkout 과 같은 order_id.
   * 결제 정보(payment_method · pg_provider · payment_id · paid_at)는 properties 에 덧붙인다. 계약 §6 필드 추가는 데이터 파트가
   * 넣기로 했고(2026-09-14), properties 는 열린 객체라 먼저 실어도 거절되지 않는다.
   */
  const finishOrder = useCallback(
    (placed: PlacedOrder, origin: OrderOrigin = 'cart') => {
      track('purchase', {
        order_id: placed.orderId,
        items: placed.items,
        order_value: Number(placed.total.toFixed(2)),
        paid_value: Number(placed.paid.toFixed(2)),
        currency: 'USD',
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
        setCartOpen(true);
      }
    },
    [],
  );

  /** 결제 실패·취소. 장바구니는 그대로 두고 화면에 이유를 적고 `payment_failed` 를 남긴다 */
  const failPayment = useCallback((orderId: string, code: string, message: string, method: PaymentMethod) => {
    setPaymentError(message);
    if (PAYMENT_FAILED_EVENT_ENABLED) {
      track('payment_failed', { order_id: orderId, reason_code: code, payment_method: method });
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
  const submitOrder = useCallback(async (source: CartItem[], origin: OrderOrigin, localOrderId: string) => {
    if (source.length === 0 || paying) return;
    const items = toOrderItems(source);
    const { count, total, paid } = orderTotals(source);
    setPaymentError(null);

    /**
     * 장바구니가 전부 백엔드 상품이고 고객 로그인이 있으면 서버 주문이다. 결제 키가 있으면 카카오페이(포트원) 결제창 →
     * 서버 confirm, 없으면 예전처럼 /pay 로 PAID 표시. 그래야 피드백 API 의 "구매 이력" 조건이 성립한다.
     * 백엔드 주문으로 만들 수 없는 상품이나 비로그인 상태에서는 로컬 테스트 주문으로 우회하지 않고 실패를 표시한다.
     */
    if (canCheckoutOnBackend(source)) {
      /*
       * 서버 장바구니는 주문 직전에만 채워지는 임시 자리인데, `POST /api/orders` 는 거기 든 것을 **전부**
       * 주문한다. 담기까지 갔다가 실패한 시도가 남아 있으면 "이 상품만" 이 아니게 된다 (shopApi 주석).
       *
       * **못 비웠으면 주문하지 않는다** (백엔드 리뷰 2026-09-17). 비우기가 실패한 채로 진행하면 남아
       * 있던 상품까지 같이 결제된다 — "이 상품만" 이라고 적힌 버튼이 다른 것도 사는 셈이다.
       * 조용히 덮지 않고 멈춘 이유를 화면에 띄운다. 사용자는 장바구니를 직접 비우고 다시 누르면 된다.
       */
      if (origin === 'buy_now') {
        const cleared = await clearBackendCart();
        if (!cleared.ok) {
          failPayment(
            localOrderId,
            `cart_clear_${cleared.status}`,
            `장바구니를 정리하지 못해 바로 구매를 멈췄습니다. ${cleared.reason} 장바구니에서 주문해 주세요.`,
            isPaymentEnabled() ? 'kakaopay' : 'test',
          );
          return;
        }
      }
      if (isPaymentEnabled()) {
        setPaying(true);
        try {
          const created = await createBackendOrder(source, localOrderId);
          if (!created.ok) {
            failPayment(localOrderId, `order_${created.status}`, `주문을 만들지 못했습니다. ${created.reason}`, 'kakaopay');
            return;
          }
          if (created.totalAmountKrw === null) {
            failPayment(created.orderId, 'no_total_amount', '주문 응답에 결제 금액(totalAmount)이 없어 결제창을 열 수 없습니다.', 'kakaopay');
            return;
          }
          // 모바일은 결제창으로 페이지가 떠났다 돌아온다. 돌아와서 confirm 을 부르려면 여기 두어야 한다
          savePendingPayment({ orderId: created.orderId, items, count, total, paid, totalAmountKrw: created.totalAmountKrw });
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
            failPayment(created.orderId, pay.code, pay.message, 'kakaopay');
            return;
          }
          const confirmed = await confirmBackendOrder(created.orderId, pay.paymentId);
          clearPendingPayment();
          if (!confirmed.ok) {
            failPayment(created.orderId, `confirm_${confirmed.status}`, `결제는 됐지만 서버 확인에 실패했습니다. ${confirmed.reason}`, 'kakaopay');
            return;
          }
          finishOrder({
            orderId: created.orderId,
            items,
            count,
            total,
            paid,
            mode: 'backend',
            note: null,
            payment_method: 'kakaopay',
            payment_id: pay.paymentId,
            paid_at: confirmed.paidAt ?? new Date().toISOString(),
          }, origin);
        } finally {
          setPaying(false);
        }
        return;
      }

      const r = await checkoutOnBackend(source, localOrderId);
      if (r.ok) {
        finishOrder({ orderId: r.orderId, items, count, total, paid, mode: 'backend', note: null, payment_method: 'test' }, origin);
        return;
      }
      failPayment(localOrderId, `order_${r.status}`, `주문을 완료하지 못했습니다. ${r.reason}`, 'test');
      return;
    }

    /*
     * 서버 주문을 탈 수 없으면 **로컬 테스트 주문으로 우회하지 않고** 이유를 띄운다
     * (백엔드 요청 2026-09-15 §5 · 이 브랜치의 결정을 그대로 따른다).
     * 바로 구매도 같은 길이라 여기서 갈리지 않는다 — 막힌 이유는 origin 과 무관하다.
     */
    const message = source.some((i) => !i.variant_id)
      ? '백엔드에 등록되지 않은 상품은 결제할 수 없습니다.'
      : '결제하려면 고객 로그인이 필요합니다.';
    failPayment(localOrderId, 'backend_checkout_required', message, 'test');
  }, [paying, member, finishOrder, failPayment]);

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
      if (paying) return;
      if (!hasMemberSession()) {
        /*
         * 여기서는 이벤트를 남기지 않는다. 새 이름(`buy_now_blocked` 같은)은 계약
         * (`event-schema.json` · 수집기 INTENTS)에 등록되기 전에는 `unregistered_event` 로 거절된다.
         */
        requestLogin('바로 구매는 고객 로그인이 필요합니다. 로그인하면 이어서 주문할 수 있습니다.');
        return;
      }
      const orderId = createOrderId();
      const { total, paid } = orderTotals([item]);
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
        items: toOrderItems([item]),
        cart_value: Number(total.toFixed(2)),
        paid_value: Number(paid.toFixed(2)),
        currency: 'USD',
        entry_source: 'buy_now',
      });
      await submitOrder([item], 'buy_now', orderId);
    },
    [paying, submitOrder],
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
      failPayment(ret.orderId, ret.code ?? 'no_payment_id', ret.message ?? '결제가 완료되지 않았습니다.', 'kakaopay');
      return;
    }
    if (!pending) {
      setPaymentError('결제는 됐지만 이 탭의 주문 정보를 찾지 못했습니다. 주문 내역에서 확인해 주세요.');
      return;
    }
    const paymentId = ret.paymentId;
    void confirmBackendOrder(pending.orderId, paymentId).then((confirmed) => {
      if (!confirmed.ok) {
        failPayment(pending.orderId, `confirm_${confirmed.status}`, `결제는 됐지만 서버 확인에 실패했습니다. ${confirmed.reason}`, 'kakaopay');
        return;
      }
      finishOrder({
        orderId: pending.orderId,
        items: pending.items,
        count: pending.count,
        total: pending.total,
        paid: pending.paid,
        mode: 'backend',
        note: null,
        payment_method: 'kakaopay',
        payment_id: paymentId,
        paid_at: confirmed.paidAt ?? new Date().toISOString(),
      });
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
      navigationSourceRef.current = 'history_back';
      // 뒤로 온 화면은 보던 자리에서 이어봐야 한다
      restoreScrollRef.current = true;
      if (nextCart) {
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
    window.history.replaceState({ productId: initialProductId() }, '', window.location.href);

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
    document.title = product
      ? `${product.product_name} - ${product.brand_name} | BLOOM`
      : 'BLOOM';
  }, [product]);

  /**
   * 식별자가 바뀌면 새 방문으로 본다.
   * 로그인 회원이면 회원 id, 아니면 스위처 페르소나 id — 추천 요청(`persona.persona_id`)과 같은 값이어야
   * `wishlist_toggle` 이 추천 서버의 그 사람 상태에 쌓인다. 로그인·로그아웃이 곧 세션 경계다 (`login` 이벤트 시점).
   * 세션의 첫 page_view 가 session_start 와 page_view_id 를 공유해야 해서
   * 지금 보고 있는 화면 정보를 함께 넘긴다. startSession 은 같은 식별자면
   * 아무것도 하지 않으므로 productId 변경으로 다시 실행돼도 무해하다.
   */
  // 로그인 회원이 최우선. 아니면 **고른** 페르소나. 둘 다 없으면 주인 없는 방문이라 null 이다
  const logIdentity = member?.id ?? (personaChosen ? personaId || null : null);
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

  return (
    <>
      <SiteHeader
        personas={personas}
        persona={persona}
        onPersonaChange={(id: string) => {
          setPersonaId(id);
          setPersonaChosen(true);
        }}
        onHome={goHome}
        categories={HEADER_CATEGORIES}
        onCategorySelect={selectCategory}
        cartCount={cartItems.reduce((sum, item) => sum + item.quantity, 0)}
        onCart={openCart}
      />

      {cartOpen ? (
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
          <Breadcrumb items={product.category} onHome={goHome} />
          <ProductDetailPage
            product={product}
            reviews={product?.source === 'backend' ? backendReviews : productReviews}
            authorReviewCounts={authorReviewCounts}
            similar={similar}
            persona={persona}
            onSelectProduct={openProduct}
            onAddToCart={addToCart}
            onBuyNow={buyNow}
            buying={paying}
          />
        </>
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

      {isDevtoolsOn() ? <LogPanel /> : null}
    </>
  );
}
