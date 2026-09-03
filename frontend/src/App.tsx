import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import SiteHeader from './components/layout/SiteHeader';
import LogPanel from './components/devtools/LogPanel';
import Breadcrumb from './components/product/Breadcrumb';
import ProductDetailPage from './pages/ProductDetailPage';
import ProductListPage from './pages/ProductListPage';
import CartPage from './pages/CartPage';
import { setLoggerContext, startPageView, startSession, track } from './lib/logger';
import {
  DEFAULT_STOREFRONT,
  STOREFRONT_KEY,
  applyStorefront,
  loadStorefront,
  storefrontEventProps,
} from './lib/storefront';
import type { StorefrontPrefs } from './lib/storefront';
import productsData from './mocks/products.sample.json';
import reviewsData from './mocks/reviews.sample.json';
import personasData from './mocks/personas.sample.json';
import type { PersonaProfile } from './types/persona';
import type { Product } from './types/product';
import type { Review } from './types/review';
import type { CartItem } from './types/cart';
import './styles/product-detail.css';
import './styles/product-list.css';
import './styles/cart.css';
// 시각 레이어. 위 셋 다음에 와야 한다 — 같은 셀렉터를 덧씌운다
import './styles/apple.css';
// 소상공인이 고른 진열 레이아웃·색. 맨 마지막 — data-storefront / data-theme 로 분기한다
import './styles/storefront.css';

// JSON 목업은 리터럴 타입으로 추론되므로 unknown 을 거쳐 캐스팅한다.
const products = productsData as unknown as Product[];
const reviews = reviewsData as unknown as Review[];
/**
 * 데이터 파트가 만든 PA 대역 100명을 그대로 쓴다.
 * 리뷰에서 파생시키던 예전 방식은 persona_id 가 author_id 라 페르소나 표와
 * 조인이 되지 않았다. scripts/build-personas.ts 가 이 파일을 만든다.
 */
const personas = personasData as unknown as PersonaProfile[];

/** 상세 페이지에서 유사·추천 자리에 올릴 개수 */
const SIMILAR_SIZE = 6;

/** 스크롤 복원을 기다려주는 최대 시간. 이미지 배치가 늦어도 이 안에는 자리를 잡는다 */
const RESTORE_TIMEOUT_MS = 1500;

/**
 * 헤더 메뉴에 걸 카테고리.
 * 데이터에 실제로 있는 중분류만 쓴다. 상품 수가 많은 순서.
 */
const HEADER_CATEGORIES = (() => {
  const counts = new Map<string, number>();
  for (const p of products) {
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
  return requested && products.some((p) => p.product_id === requested) ? requested : null;
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
  const fallback = personas[0]?.persona_id ?? '';
  const requested = new URLSearchParams(window.location.search).get('persona');
  return requested && personas.some((p) => p.persona_id === requested) ? requested : fallback;
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
setLoggerContext({ personaId: initialPersonaId() });

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

  const persona = useMemo(
    () => personas.find((item) => item.persona_id === personaId) ?? null,
    [personaId],
  );

  const product = useMemo(
    () => (productId ? (products.find((item) => item.product_id === productId) ?? null) : null),
    [productId],
  );

  const productReviews = useMemo(
    () => (productId ? reviews.filter((review) => review.product_id === productId) : []),
    [productId],
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
    setLoggerContext({ environment: 'local' });
  }, []);

  /**
   * 소상공인이 대시보드에서 고른 쇼핑몰 진열 설정.
   * 같은 브라우저의 localStorage 로 건너온다. 대시보드 탭에서 바꾸면 storage 이벤트로
   * 이 탭도 새로고침 없이 따라온다 — 시연에서 두 탭을 나란히 놓고 보여줄 수 있다.
   */
  const [storefront, setStorefront] = useState<StorefrontPrefs>(
    () => loadStorefront() ?? DEFAULT_STOREFRONT,
  );

  useEffect(() => {
    applyStorefront(storefront);
    // 진열이 바뀌면 그 다음 이벤트부터 새 진열로 기록된다
    setLoggerContext({ storefront: storefrontEventProps(storefront) });
  }, [storefront]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STOREFRONT_KEY) setStorefront(loadStorefront() ?? DEFAULT_STOREFRONT);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

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
   * 페르소나가 바뀌면 새 방문으로 본다.
   * 세션의 첫 page_view 가 session_start 와 page_view_id 를 공유해야 해서
   * 지금 보고 있는 화면 정보를 함께 넘긴다. startSession 은 같은 페르소나면
   * 아무것도 하지 않으므로 productId 변경으로 다시 실행돼도 무해하다.
   */
  useEffect(() => {
    setLoggerContext({
      pageType: cartOpen ? 'cart' : productId ? 'product_detail' : 'product_list',
    });
    startSession(personaId || null, cartOpen ? null : productId);
  }, [personaId, productId, cartOpen]);

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
        onPersonaChange={setPersonaId}
        onHome={goHome}
        categories={HEADER_CATEGORIES}
        onCategorySelect={selectCategory}
        cartCount={cartItems.reduce((sum, item) => sum + item.quantity, 0)}
        onCart={openCart}
        brandName={storefront.brandName}
      />

      {cartOpen ? (
        <CartPage
          items={cartItems}
          onQuantityChange={changeCartQuantity}
          onRemove={removeFromCart}
          onSelectProduct={openProduct}
          onContinue={goHome}
        />
      ) : product ? (
        <>
          <Breadcrumb items={product.category} onHome={goHome} />
          <ProductDetailPage
            product={product}
            reviews={productReviews}
            allReviews={reviews}
            similar={similar}
            persona={persona}
            onSelectProduct={openProduct}
            onAddToCart={addToCart}
          />
        </>
      ) : (
        <ProductListPage
          products={products}
          reviews={reviews}
          persona={persona}
          onSelectProduct={openProduct}
          onAddToCart={addToCart}
          cartProductIds={cartProductIds}
          category={listCategory}
          onCategoryChange={setListCategory}
        />
      )}

      <LogPanel />
    </>
  );
}
