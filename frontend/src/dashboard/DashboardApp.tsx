import { useEffect, useState } from 'react';
import OverviewScreen from './screens/OverviewScreen';
import OrdersScreen from './screens/OrdersScreen';
import ProductsScreen from './screens/ProductsScreen';
import BehaviorScreen from './screens/BehaviorScreen';
import ContentScreen from './screens/ContentScreen';
import SegmentsScreen from './screens/SegmentsScreen';
import ReviewsScreen from './screens/ReviewsScreen';
import IngredientsScreen from './screens/IngredientsScreen';
import PriceScreen from './screens/PriceScreen';
import InflowScreen from './screens/InflowScreen';
import RegisterScreen from './screens/RegisterScreen';
import FeedbackScreen from './screens/FeedbackScreen';
import SettlementScreen from './screens/SettlementScreen';
import { MotifLine, OriginBadge } from './components';
import { DEMO_BRAND } from '../mocks/products';
import NotificationBell from '../components/notifications/NotificationBell';
import { SCOPE_LABEL } from './lib/scope';
import type { ScopeKind } from './lib/scope';
import { useAuth } from '../hooks/useAuth';
import { logout } from '../lib/auth';
import { createBrand, fetchMyBrands, loadBrandId, saveBrandId } from '../lib/brands';
import type { BrandsState } from '../lib/brands';
import { BehaviorGate, BehaviorProvider, useBehavior, useMartState } from './lib/useBehavior';
import { periodLabel } from './lib/metrics';

/**
 * 화면 하나. **이름을 바꾸지 않았다** — `insight.ts`·`prescription.ts` 가 "이 인사이트는 어느 화면으로
 * 가라" 를 이 키로 적어 두고 `onGo` 로 넘긴다. 메뉴를 묶으면서 키까지 갈면 그 연결이 전부 끊긴다.
 */
type ScreenKey =
  | 'overview'
  | 'products'
  | 'orders'
  | 'content'
  | 'segments'
  | 'behavior'
  | 'reviews'
  | 'ingredients'
  | 'price'
  | 'inflow'
  | 'register'
  | 'feedback'
  | 'settlement';

/**
 * 왼쪽 메뉴 한 칸. 화면 9개를 **브랜드가 묻는 질문 6개**로 묶는다.
 *
 * 예전 메뉴는 데이터 종류로 나뉘어 있었다 — 상세 콘텐츠·고객군·성분·상품·피드백·리뷰·막히는 곳.
 * 아홉 개가 한 줄로 늘어서 있으면 어디부터 봐야 할지가 안 보이고, 실제로는 같은 질문의 두 면인
 * 것들이 따로 떨어져 있었다. 상세페이지에서 **무엇을 읽나**(콘텐츠)와 **어디서 막히나**(마찰)는
 * 나란히 놓아야 뜻이 통하고, **공개 리뷰**와 **우리가 받은 피드백**은 둘 다 고객이 쓴 글이다.
 *
 * 묶되 화면은 합치지 않는다. 한 섹션 안에서 탭으로 가른다 — 한 화면에 전부 쏟으면 줄인 의미가 없다.
 */
type SectionKey = 'overview' | 'detail' | 'products' | 'orders' | 'customers' | 'voice' | 'market' | 'register';

interface ScreenDef {
  section: SectionKey;
  /** 섹션 안 탭 이름. 탭이 하나뿐인 섹션은 안 쓴다 */
  tab: string;
  title: string;
  desc: string;
  /** 어느 데이터 스코프를 보나 (lib/scope.ts). 피드백·등록만 SSAFY Beauty */
  scope: ScopeKind;
}

const SCREENS: Record<ScreenKey, ScreenDef> = {
  overview: {
    section: 'overview', tab: '요약', scope: 'behavior',
    title: '요약', desc: '지금 상황과 첫 번째 할 일',
  },
  content: {
    section: 'detail', tab: '설명 글', scope: 'behavior',
    title: '상세페이지 설명 글', desc: '어떤 글을 읽은 고객이 담는지',
  },
  behavior: {
    section: 'detail', tab: '막히는 자리', scope: 'behavior',
    title: '고객이 막히는 자리', desc: '눌러도 반응 없는 곳, 되돌아 읽는 곳',
  },
  products: {
    section: 'products', tab: '상품', scope: 'behavior',
    title: '상품별 진단', desc: '상품마다 고객이 멈추는 단계',
  },
  orders: {
    section: 'orders', tab: '주문', scope: 'feedback',
    title: '주문', desc: '결제 완료된 주문',
  },
  settlement: {
    section: 'orders', tab: '정산', scope: 'feedback',
    title: '정산', desc: '월별 정산 · 수수료 0%',
  },
  segments: {
    section: 'customers', tab: '고객군', scope: 'behavior',
    title: '고객군', desc: '피부 타입·톤별로 누가 담는지',
  },
  reviews: {
    section: 'voice', tab: '공개 리뷰', scope: 'behavior',
    title: '공개 리뷰', desc: '피부 타입별 평가',
  },
  feedback: {
    section: 'voice', tab: '받은 피드백', scope: 'feedback',
    title: '받은 피드백', desc: '고객이 고쳐 달라고 한 것',
  },
  ingredients: {
    section: 'market', tab: '성분', scope: 'behavior',
    title: '성분', desc: '고객이 찾는데 내 상품엔 없는 성분',
  },
  price: {
    section: 'market', tab: '가격', scope: 'behavior',
    title: '가격', desc: '내 가격과 같은 카테고리 중간 가격',
  },
  inflow: {
    section: 'market', tab: '넘어온 방문', scope: 'behavior',
    title: '다른 브랜드에서 넘어온 방문', desc: '다른 브랜드를 보다가 내 상품으로 온 방문 수',
  },
  register: {
    section: 'register', tab: '상품 등록', scope: 'feedback',
    title: '상품 등록', desc: '고객 화면 미리보기',
  },
};

/**
 * 메뉴 순서 = 브랜드가 결정을 내리는 순서 (명세 §1).
 *
 * `시장` 만 성격이 다르다. 나머지 다섯은 **내 로그**를 보는 자리이고, 시장은 **여러 브랜드가 모여야
 * 나오는 자리**다 (components.tsx `OriginBadge`). 그래서 맨 아래 따로 떼어 두고 이름도 "성분" 이
 * 아니라 "시장" 으로 둔다 — 앞으로 코호트 비교가 붙는 자리이기도 하다.
 *
 * `상품 등록` 은 분석이 아니라 작업이라 메뉴에서 한 번 더 갈라 놓는다.
 */
const SECTIONS: Array<{ key: SectionKey; label: string; screens: ScreenKey[] }> = [
  { key: 'overview', label: '요약', screens: ['overview'] },
  { key: 'detail', label: '상세페이지', screens: ['content', 'behavior'] },
  { key: 'products', label: '상품', screens: ['products'] },
  // 주문은 행동 마트가 아니라 쇼핑몰 원장을 읽는다. DW 적재와 무관하게 값이 찬다
  { key: 'orders', label: '주문', screens: ['orders', 'settlement'] },
  { key: 'customers', label: '고객', screens: ['segments'] },
  { key: 'voice', label: '고객의 말', screens: ['reviews', 'feedback'] },
  { key: 'market', label: '시장', screens: ['ingredients', 'price', 'inflow'] },
];

/** 분석 메뉴와 성격이 달라 아래 따로 둔다 */
const WORK_SECTIONS: Array<{ key: SectionKey; label: string; screens: ScreenKey[] }> = [
  { key: 'register', label: '상품 등록', screens: ['register'] },
];

const ALL_SECTIONS = [...SECTIONS, ...WORK_SECTIONS];

/**
 * HWABUN · 참여 브랜드(소상공인) 담당자용 대시보드 v0.2.
 *
 * 쇼핑몰과 진입점이 분리되어 있다 (/dashboard.html · 쇼핑몰 어디에서도 링크하지 않는다).
 * 실제 접근 제어(계정·권한)는 백엔드 범위이고, 여기서는 화면과 지표 정의를 확정한다.
 *
 * 화면은 사이드바 하나로 고정이고 색도 HWABUN 이다.
 *
 * **쇼핑몰은 공통이다.** 올리브영·세포라처럼 소비자가 보는 몰이 하나이고, 브랜드는 거기에 상품을
 * 등록하고 이 대시보드만 받는다. 그래서 브랜드가 진열 레이아웃·색을 고르는 화면(구 Onboarding)은
 * 없앴다. 브랜드마다 다른 것은 진열이 아니라 **상품과 지표**다.
 */
export default function DashboardApp() {
  /** main.tsx 의 AuthGate 를 지나 왔으므로 null 이 아니다. 만료되면 게이트가 다시 로그인으로 바꾼다 */
  const seller = useAuth('SELLER');
  /**
   * 내 브랜드. 판매자 API 는 전부 brandId 를 요구하므로 로그인 직후 받아 하나를 고른다.
   * 서버가 없으면 'unavailable' · 화면은 시연 브랜드 이름(DEMO_BRAND)만 띄우고 사이드바에 그 사실을 적는다.
   */
  const [brands, setBrands] = useState<BrandsState>({ kind: 'loading' });
  const [brandId, setBrandId] = useState<string | null>(() => loadBrandId());

  useEffect(() => {
    let alive = true;
    fetchMyBrands().then((state) => {
      if (!alive) return;
      setBrands(state);
      if (state.kind === 'ready') {
        const keep = state.brands.some((b) => b.id === brandId);
        const next = keep ? brandId : (state.brands[0]?.id ?? null);
        setBrandId(next);
        saveBrandId(next);
      }
    });
    return () => {
      alive = false;
    };
    // seller 가 바뀌면(재로그인) 다시 받는다. brandId 는 안에서 맞추므로 의존성에 넣지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seller?.id]);

  const brand = brands.kind === 'ready' ? (brands.brands.find((b) => b.id === brandId) ?? null) : null;
  const [screen, setScreen] = useState<ScreenKey>('overview');
  const [days, setDays] = useState(14);
  /** 리뷰·성분 화면이 공유하는 상품 선택 */
  const [productId, setProductId] = useState<string | null>(null);

  const active = SCREENS[screen];
  /** 지금 열린 섹션. 화면 키 하나만 상태로 두고 섹션은 거기서 끌어낸다 — 둘을 따로 두면 어긋난다 */
  const activeSection = ALL_SECTIONS.find((sec) => sec.key === active.section) ?? ALL_SECTIONS[0];

  return (
    /*
     * 행동 지표는 여기서 한 번 받는다 (마트 API 6개 병렬 · contracts/dashboard-mart-api-spec.md).
     * 서버 브랜드가 없으면 부르지 않고 값은 전부 0 이다. 화면은 useBehavior() 로 같은 모양을 읽는다.
     */
    <BehaviorProvider brandId={brand?.id ?? null} brandName={brand?.name ?? null} days={days}>
    <div className="console">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <img src="/brand/hwabun-mark.png" alt="" width="34" height="34" />
          <div>
            <strong>HWABUN</strong>
            <span>{brand?.name || (brands.kind === 'loading' ? '브랜드 확인 중' : DEMO_BRAND)}</span>
          </div>
        </div>

        {/* 서버 브랜드. 둘 이상이면 고르고, 없으면 만들고, 서버가 없으면 모의값이라고 적는다 */}
        {brands.kind === 'ready' && brands.brands.length > 1 ? (
          <select
            className="sidebar__brand-select"
            value={brandId ?? ''}
            aria-label="브랜드 선택"
            onChange={(e) => {
              setBrandId(e.target.value);
              saveBrandId(e.target.value);
            }}
          >
            {brands.brands.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        ) : null}
        {brands.kind === 'ready' && brands.brands.length === 0 ? (
          <button
            type="button"
            className="sidebar__settings sidebar__brand-create"
            onClick={async () => {
              const created = await createBrand(DEMO_BRAND);
              if (created) {
                setBrands({ kind: 'ready', brands: [created] });
                setBrandId(created.id);
                saveBrandId(created.id);
              }
            }}
          >
            내 브랜드 만들기
          </button>
        ) : null}
        {brands.kind === 'unavailable' ? (
          <p className="sidebar__brand-note">
            {brands.reason === 'server' ? '브랜드를 못 불러왔습니다' : '다시 로그인해 주세요'}
          </p>
        ) : null}

        <MotifLine variant="divider" compact />

        <nav className="sidebar__nav" aria-label="대시보드 화면">
          {SECTIONS.map((sec) => (
            <button
              key={sec.key}
              type="button"
              className={sec.key === active.section ? 'is-active' : ''}
              /* 섹션을 누르면 그 안 첫 화면으로 간다. 이미 그 섹션이면 탭 선택을 유지한다 */
              onClick={() => setScreen((cur) => (SCREENS[cur].section === sec.key ? cur : sec.screens[0]))}
            >
              {sec.label}
            </button>
          ))}

          {/* 분석이 아니라 작업. 선 하나로 갈라 둔다 */}
          <span className="sidebar__nav-gap" aria-hidden="true" />
          {WORK_SECTIONS.map((sec) => (
            <button
              key={sec.key}
              type="button"
              className={sec.key === active.section ? 'is-active' : ''}
              onClick={() => setScreen(sec.screens[0])}
            >
              {sec.label}
            </button>
          ))}
        </nav>

        {/* 공통 쇼핑몰 바로가기. 진열은 브랜드가 고르지 않는다 — 몰이 하나다 */}
        <div className="sidebar__shop">
          <p className="sidebar__shop-label">고객이 보는 곳</p>
          <p className="sidebar__shop-state">HWABUN 통합 쇼핑몰</p>
          <div className="sidebar__shop-actions">
            <a className="sidebar__settings" href="/" target="_blank" rel="noopener">
              쇼핑몰 보기 ↗
            </a>
          </div>
        </div>

        <div className="sidebar__foot">
          {/* 인앱 알림함. 판매자는 새 의견 알림을 받는다 — 누르면 고객의 말 화면으로 */}
          <NotificationBell role="SELLER" placement="above" onOpen={() => setScreen('feedback')} />
          {seller ? (
            <div className="sidebar__account">
              <span className="sidebar__account-name" title={seller.email}>
                {seller.name}
              </span>
              <button type="button" className="sidebar__settings" onClick={() => logout('SELLER')}>
                로그아웃
              </button>
            </div>
          ) : null}
          <MartNote />
          {/* 결론 색 범례. 연두 = 내 브랜드 데이터만, 핑크 = 플랫폼 전체(다른 브랜드 포함) 종합 (components DataOrigin) */}
          <p className="sidebar__legend" aria-label="숫자 출처 색 안내">
            <OriginBadge kind="mine" />
            <OriginBadge kind="shared" />
          </p>
        </div>
      </aside>

      <main className="main">
        <header className="main__head">
          <h1>{active.title}</h1>
          <p>{active.desc}</p>
          {/* 어느 브랜드 데이터인지 항상 적는다. 스코프가 둘이라 이게 없으면 숫자를 잘못 읽는다 */}
          {/*
            행동 숫자를 쓰는 화면은 요약에서 고른 기간을 그대로 따른다. 기간 고르기가 없는 화면이라도 몇 일치인지는 적는다 —
            안 적으면 사장님은 전체 기간으로 읽는다 (2026-09-29)
          */}
          <ScopeNote scope={active.scope} brandName={brand?.name ?? null} period={PERIOD_LABEL_SCREENS.has(screen) ? periodLabel(days) : null} />

          <div className="main__controls">
            {screen === 'overview' || screen === 'inflow' ? (
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                aria-label="기간"
              >
                <option value={1}>오늘</option>
                <option value={7}>최근 7일</option>
                <option value={14}>최근 14일</option>
                <option value={30}>최근 30일</option>
              </select>
            ) : null}
          </div>
        </header>

        {/*
          섹션 안의 탭. 화면이 하나뿐인 섹션에는 안 그린다 — 선택지가 하나인 탭은 공간만 먹는다.
          왼쪽 메뉴가 "무엇을 묻나", 이 탭이 "그 질문의 어느 면인가" 다.
        */}
        {activeSection.screens.length > 1 ? (
          <div className="tabs" role="tablist" aria-label={`${activeSection.label} 화면`}>
            {activeSection.screens.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={key === screen}
                className={key === screen ? 'is-active' : ''}
                onClick={() => setScreen(key)}
              >
                {SCREENS[key].tab}
              </button>
            ))}
          </div>
        ) : null}

        {/* 요약은 주문·매출 카드를 먼저 그리고 행동 기록 부분만 화면 안에서 가린다 (2026-09-30) */}
        {screen === 'overview' ? <OverviewScreen days={days} brandName={brand?.name ?? null} onGo={(s) => setScreen(s as ScreenKey)} /> : null}
        {screen === 'products' ? <BehaviorGate><ProductsScreen brandId={brand?.id ?? null} brandName={brand?.name ?? null} /></BehaviorGate> : null}
        {screen === 'orders' ? <OrdersScreen brandId={brand?.id ?? null} brandName={brand?.name ?? null} /> : null}
        {screen === 'content' ? <BehaviorGate><ContentScreen brandName={brand?.name ?? ''} /></BehaviorGate> : null}
        {screen === 'segments' ? <BehaviorGate><SegmentsScreen /></BehaviorGate> : null}
        {screen === 'behavior' ? <BehaviorGate><BehaviorScreen /></BehaviorGate> : null}
        {screen === 'reviews' ? (
          <ReviewsScreen brandId={brand?.id ?? null} brandName={brand?.name ?? null} productId={productId} onProductChange={setProductId} />
        ) : null}
        {screen === 'ingredients' ? (
          <BehaviorGate>
            <IngredientsScreen brandId={brand?.id ?? null} brandName={brand?.name ?? null} productId={productId} onProductChange={setProductId} />
          </BehaviorGate>
        ) : null}
        {screen === 'price' ? <PriceScreen brandId={brand?.id ?? null} /> : null}
        {screen === 'inflow' ? <InflowScreen brandId={brand?.id ?? null} days={days} /> : null}
        {screen === 'register' ? <RegisterScreen /> : null}
        {screen === 'feedback' ? <FeedbackScreen brandId={brand?.id ?? null} brandName={brand?.name ?? null} /> : null}
        {screen === 'settlement' ? <SettlementScreen brandId={brand?.id ?? null} /> : null}
      </main>
    </div>
    </BehaviorProvider>
  );
}

/**
 * 헤더의 "어느 브랜드 데이터인가" 한 줄.
 *
 * **언제나 로그인한 브랜드 이름을 적는다.** 행동 지표는 마트를 로그인한 brandId 로 조회하고, 원장(주문·정산
 * ·리뷰)과 성분도 내 브랜드 것이라 숫자의 주인은 늘 로그인한 브랜드다. 이름을 아직 못 받았으면 비워 둔다 —
 * 남의 브랜드 이름을 적느니 비는 편이 낫다.
 *
 * 전에는 행동 스코프가 마트 실측(`anyReal`) 전까지 고정 브랜드(Drunk Elephant)를 적었다. 브랜드 1254 로
 * 로그인해 놓고 헤더가 Drunk Elephant 를 가리켰다 (09-15 확인). 2026-09-18 에 그 고정 브랜드를 없앴다.
 * `anyReal` 은 이제 이름이 아니라 **출처 문구**만 가른다 (마트 실측인지, 아직 못 받았는지).
 *
 * 피드백·등록 스코프는 마트와 무관한 로컬 분류본이라 언제나 고정 라벨이다.
 */
/** 기간 고르기는 없지만 요약의 기간(days)을 따르는 화면. 헤더에 "최근 N일" 을 적는다 */
const PERIOD_LABEL_SCREENS = new Set<ScreenKey>(['content', 'behavior', 'products', 'segments', 'ingredients']);

function ScopeNote({ scope, brandName, period }: { scope: ScopeKind; brandName: string | null; period?: string | null }) {
  const { anyReal } = useBehavior();
  const label = SCOPE_LABEL[scope];
  const live = scope === 'behavior' && anyReal;
  // 대시보드가 적는 브랜드는 언제나 로그인한 브랜드다. 못 받았으면 남의 이름을 적느니 비워 둔다 (피드백 스코프도 2026-09-18 부터)
  const brand = brandName ?? (label.brand || '브랜드 확인 중');
  const source = live ? '내 쇼핑몰 실제 기록' : label.source;
  // 출처("내 쇼핑몰 실제 기록" 등)는 화면에 적지 않는다 — 발표 화면에서 거슬린다 (2026-10-01 유림님). 마우스를 올리면 title 로 보인다
  return (
    <p className="main__scope" title={source}>
      <span className="main__scope-what">{label.what}</span>
      <strong>{brand}</strong>
      {period ? <span className="main__scope-period">{period}</span> : null}
    </p>
  );
}

/** 사이드바 하단. 행동 지표가 어디서 왔는지 한 줄 (계약 §7) */
function MartNote() {
  const state = useMartState();
  const { anyReal } = useBehavior();
  let line: string;
  if (state === 'idle') line = '브랜드를 고르면 불러옵니다';
  else if (state === 'loading') line = '행동 기록을 불러오는 중';
  // 배치 시각("9월 28일 03:56까지 반영")은 늦어도 맞아도 사장님 눈에 거슬려서 적지 않는다 (유림님)
  else if (anyReal) line = '행동 기록을 불러왔습니다';
  else if (state === 'ready') line = '이 기간 행동 기록이 없습니다';
  else line = '행동 기록을 못 불러왔습니다';
  return (
    <p>
      <span className="sidebar__mart">
        고객 행동 기록
      </span>
      <br />
      {line}
    </p>
  );
}
