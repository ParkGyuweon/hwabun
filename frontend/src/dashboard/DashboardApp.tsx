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
import { MotifLine } from './components';
import { DEMO_BRAND } from '../mocks/products';
import { SCOPE_LABEL } from './lib/scope';
import type { ScopeKind } from './lib/scope';
import { useAuth } from '../hooks/useAuth';
import { logout } from '../lib/auth';
import { createBrand, fetchMyBrands, loadBrandId, saveBrandId } from '../lib/brands';
import type { BrandsState } from '../lib/brands';

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

/** 화면이 어느 데이터 스코프를 보나 (lib/scope.ts). 피드백·등록만 SSAFY Beauty, 나머지는 행동·리뷰 브랜드 */
const SCREEN_SCOPE: Record<ScreenKey, ScopeKind> = {
  overview: 'behavior',
  content: 'behavior',
  segments: 'behavior',
  ingredients: 'behavior',
  products: 'behavior',
  reviews: 'behavior',
  behavior: 'behavior',
  feedback: 'feedback',
  register: 'feedback',
};

const SCREENS: Array<{ key: ScreenKey; label: string; title: string; desc: string }> = [
  // 순서 = 브랜드가 결정하는 순서 (명세 §1). 범용 지표와 화면 문제는 뒤로
  { key: 'overview', label: '요약', title: '지금 손봐야 할 것', desc: '오늘 하나만 고친다면 이것입니다' },
  { key: 'content', label: '상세 콘텐츠', title: '무엇을 보고 사나', desc: '상세페이지의 어떤 글이 고객을 담게 만드나' },
  { key: 'segments', label: '고객군', title: '누가 사나', desc: '피부 타입과 피부 톤에 따라 누가 담는지' },
  { key: 'ingredients', label: '성분', title: '고객이 찾는 성분', desc: '많이 찾는데 내 상품에는 없는 성분' },
  { key: 'products', label: '상품', title: '상품마다 어디서 멈추나', desc: '상품별로 고객이 발길을 돌리는 지점' },
  { key: 'feedback', label: '고객 피드백', title: '고객이 고쳐 달라는 것', desc: '고객이 직접 고른 축과 그 안의 이유' },
  { key: 'reviews', label: '리뷰', title: '공개 리뷰', desc: '피부 타입에 따라 갈리는 평가와 자극 언급' },
  { key: 'behavior', label: '막히는 곳', title: '막히는 곳', desc: '고객이 화면에서 헤매는 자리 · 상품이 싫다는 뜻이 아닙니다' },
  { key: 'register', label: '상품 등록', title: '상품 등록', desc: '입력하면 고객 화면 그대로 미리보기' },
];

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
   * 서버가 없으면 'unavailable' · 화면은 모의 브랜드(DEMO_BRAND)로 남고 사이드바에 그 사실을 적는다.
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

  const active = SCREENS.find((s) => s.key === screen) ?? SCREENS[0];

  return (
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
            {brands.reason === 'server' ? '서버 미연결 · 모의 브랜드' : '로그인 만료 · 다시 로그인'}
          </p>
        ) : null}

        <MotifLine variant="divider" compact />

        <nav className="sidebar__nav" aria-label="대시보드 화면">
          {SCREENS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={s.key === screen ? 'is-active' : ''}
              onClick={() => setScreen(s.key)}
            >
              {s.label}
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
          <p>
            v0.2 · 이벤트 36종 기준
            <br />
            행동 지표는 수집 API 연결 전까지 모의 집계입니다. 리뷰·성분은 실측.
          </p>
        </div>
      </aside>

      <main className="main">
        <header className="main__head">
          <h1>{active.title}</h1>
          <p>{active.desc}</p>
          {/* 어느 브랜드 데이터인지 항상 적는다. 스코프가 둘이라 이게 없으면 숫자를 잘못 읽는다 */}
          <p className="main__scope" title={SCOPE_LABEL[SCREEN_SCOPE[active.key]].source}>
            <span className="main__scope-what">{SCOPE_LABEL[SCREEN_SCOPE[active.key]].what}</span>
            <strong>{SCOPE_LABEL[SCREEN_SCOPE[active.key]].brand}</strong>
            <span className="main__scope-src">{SCOPE_LABEL[SCREEN_SCOPE[active.key]].source}</span>
          </p>

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

        {screen === 'overview' ? <OverviewScreen days={days} onGo={(s) => setScreen(s as ScreenKey)} /> : null}
        {screen === 'products' ? <ProductsScreen /> : null}
        {screen === 'content' ? <ContentScreen /> : null}
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
  );
}
