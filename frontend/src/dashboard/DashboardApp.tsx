import { useEffect, useState } from 'react';
import OverviewScreen from './screens/OverviewScreen';
import ProductsScreen from './screens/ProductsScreen';
import BehaviorScreen from './screens/BehaviorScreen';
import ContentScreen from './screens/ContentScreen';
import SegmentsScreen from './screens/SegmentsScreen';
import ReviewsScreen from './screens/ReviewsScreen';
import IngredientsScreen from './screens/IngredientsScreen';
import RegisterScreen from './screens/RegisterScreen';
import FeedbackScreen from './screens/FeedbackScreen';
import { MotifLine, OriginBadge } from './components';
import { DEMO_BRAND } from '../mocks/products';
import { SCOPE_LABEL } from './lib/scope';
import type { ScopeKind } from './lib/scope';
import { useAuth } from '../hooks/useAuth';
import { logout } from '../lib/auth';
import { createBrand, fetchMyBrands, loadBrandId, saveBrandId } from '../lib/brands';
import type { BrandsState } from '../lib/brands';
import { BehaviorProvider, useBehavior, useMartState } from './lib/useBehavior';

/**
 * 화면 하나. **이름을 바꾸지 않았다** — `insight.ts`·`prescription.ts` 가 "이 인사이트는 어느 화면으로
 * 가라" 를 이 키로 적어 두고 `onGo` 로 넘긴다. 메뉴를 묶으면서 키까지 갈면 그 연결이 전부 끊긴다.
 */
type ScreenKey =
  | 'overview'
  | 'products'
  | 'content'
  | 'segments'
  | 'behavior'
  | 'reviews'
  | 'ingredients'
  | 'register'
  | 'feedback';

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
type SectionKey = 'overview' | 'detail' | 'products' | 'customers' | 'voice' | 'market' | 'register';

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
    title: '지금 손봐야 할 것', desc: '오늘 하나만 고친다면 이것입니다',
  },
  content: {
    section: 'detail', tab: '무엇을 보고 사나', scope: 'behavior',
    title: '무엇을 보고 사나', desc: '상세페이지의 어떤 글이 고객을 담게 만드나',
  },
  behavior: {
    section: 'detail', tab: '어디서 막히나', scope: 'behavior',
    title: '막히는 곳', desc: '고객이 화면에서 헤매는 자리 · 상품이 싫다는 뜻이 아닙니다',
  },
  products: {
    section: 'products', tab: '상품', scope: 'behavior',
    title: '상품마다 어디서 멈추나', desc: '상품별로 고객이 발길을 돌리는 지점',
  },
  segments: {
    section: 'customers', tab: '고객군', scope: 'behavior',
    title: '누가 사나', desc: '피부 타입과 피부 톤에 따라 누가 담는지',
  },
  reviews: {
    section: 'voice', tab: '공개 리뷰', scope: 'behavior',
    title: '공개 리뷰', desc: '피부 타입에 따라 갈리는 평가와 자극 언급',
  },
  feedback: {
    section: 'voice', tab: '받은 피드백', scope: 'feedback',
    title: '고객이 고쳐 달라는 것', desc: '고객이 직접 고른 축과 그 안의 이유',
  },
  ingredients: {
    section: 'market', tab: '성분', scope: 'behavior',
    title: '고객이 찾는 성분', desc: '많이 찾는데 내 상품에는 없는 성분',
  },
  register: {
    section: 'register', tab: '상품 등록', scope: 'feedback',
    title: '상품 등록', desc: '입력하면 고객 화면 그대로 미리보기',
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
  { key: 'customers', label: '고객', screens: ['segments'] },
  { key: 'voice', label: '고객의 말', screens: ['reviews', 'feedback'] },
  { key: 'market', label: '시장', screens: ['ingredients'] },
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
            <span>{brand?.name || DEMO_BRAND}</span>
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
            서버에 브랜드 등록
          </button>
        ) : null}
        {brands.kind === 'unavailable' ? (
          <p className="sidebar__brand-note">
            {brands.reason === 'server' ? '서버 미연결 · 브랜드를 못 읽었습니다' : '로그인 만료 · 다시 로그인'}
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
          <p className="sidebar__shop-state">HWABUN 통합 쇼핑몰 · 내 상품이 함께 진열됩니다</p>
          <div className="sidebar__shop-actions">
            <a className="sidebar__settings" href="/" target="_blank" rel="noopener">
              쇼핑몰 보기 ↗
            </a>
          </div>
        </div>

        <div className="sidebar__foot">
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
          <p className="sidebar__legend" aria-label="결론 색 범례">
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
          <ScopeNote scope={active.scope} brandName={brand?.name ?? null} />

          <div className="main__controls">
            {screen === 'overview' ? (
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                aria-label="기간"
              >
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

        {screen === 'overview' ? <OverviewScreen days={days} onGo={(s) => setScreen(s as ScreenKey)} /> : null}
        {screen === 'products' ? <ProductsScreen /> : null}
        {screen === 'content' ? <ContentScreen brandName={brand?.name || SCOPE_LABEL.behavior.brand} /> : null}
        {screen === 'segments' ? <SegmentsScreen /> : null}
        {screen === 'behavior' ? <BehaviorScreen /> : null}
        {screen === 'reviews' ? (
          <ReviewsScreen productId={productId} onProductChange={setProductId} />
        ) : null}
        {screen === 'ingredients' ? (
          <IngredientsScreen productId={productId} onProductChange={setProductId} />
        ) : null}
        {screen === 'register' ? <RegisterScreen /> : null}
        {screen === 'feedback' ? <FeedbackScreen /> : null}
      </main>
    </div>
    </BehaviorProvider>
  );
}

/**
 * 헤더의 "어느 브랜드 데이터인가" 한 줄.
 *
 * 행동·리뷰 스코프는 마트가 붙기 전까지 세포라 카탈로그의 고정 브랜드(`BEHAVIOR_BRAND`) 모의값이라
 * 그 이름을 적는 것이 정직하다. 마트 행이 실제로 쓰이면(`anyReal`) 숫자의 주인은 **로그인한 브랜드**로
 * 바뀌므로 그 이름으로 갈아끼운다. 이 줄을 고정으로 두면 브랜드 1254 로 로그인해 놓고 헤더는
 * Drunk Elephant 를 가리키게 된다 (09-15 확인. 시드가 브랜드별 판매자 계정을 넣으면서 실제로 갈릴 수 있게 됐다).
 *
 * 피드백·등록 스코프는 마트와 무관한 로컬 분류본이라 언제나 고정 라벨이다.
 */
function ScopeNote({ scope, brandName }: { scope: ScopeKind; brandName: string | null }) {
  const { anyReal } = useBehavior();
  const label = SCOPE_LABEL[scope];
  const live = scope === 'behavior' && anyReal && brandName !== null;
  const brand = live && brandName ? brandName : label.brand;
  const source = live ? '행동 마트 실측 · 로그인한 브랜드' : label.source;
  return (
    <p className="main__scope" title={source}>
      <span className="main__scope-what">{label.what}</span>
      <strong>{brand}</strong>
      <span className="main__scope-src">{source}</span>
    </p>
  );
}

/** 사이드바 하단. 행동 지표가 어디서 왔는지 한 줄 (계약 §7) */
function MartNote() {
  const state = useMartState();
  const { anyReal, martProcessedAt } = useBehavior();
  let line: string;
  if (state === 'loading') line = '마트 지표를 받는 중';
  else if (anyReal) line = `마트 연결됨${martProcessedAt ? ` · 갱신 ${martProcessedAt.slice(0, 16).replace('T', ' ')}` : ''} · 배지가 화면별 출처`;
  else if (state === 'ready') line = '마트는 답했지만 이 브랜드·기간에 행이 없습니다 · 행동 지표는 0';
  else line = '마트에 닿지 못했습니다 · 행동 지표는 0. 리뷰·성분은 실측.';
  return (
    <p>
      <span className="sidebar__mart">
        v0.3 · 이벤트 36종 기준
      </span>
      <br />
      {line}
    </p>
  );
}
