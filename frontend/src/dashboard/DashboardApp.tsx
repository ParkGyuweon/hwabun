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
import Onboarding from './Onboarding';
import { MotifLine } from './components';
import { DEFAULT_STOREFRONT, describeStorefront, loadStorefront, saveStorefront } from '../lib/storefront';
import type { StorefrontPrefs } from '../lib/storefront';
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
  // 순서 = 브랜드가 결정하는 순서 (명세 §1). 범용 지표·마찰은 뒤로
  { key: 'overview', label: '개요', title: '개요', desc: '지금 손봐야 할 것 하나' },
  { key: 'content', label: '정보 관심도', title: '정보 관심도', desc: '무엇을 보고 사나 · 콘텐츠 단위 주목도와 전환 기여' },
  { key: 'segments', label: '고객군', title: '고객군', desc: '누가 사나 · 피부 타입 × 톤' },
  { key: 'ingredients', label: '성분', title: '성분', desc: '고객이 찾는 성분과 내 라인의 갭' },
  { key: 'products', label: '상품', title: '상품', desc: '상품별 병목과 이탈 지점' },
  { key: 'feedback', label: '고객 피드백', title: '고객 피드백', desc: '고객이 고쳐 달라는 것 · 5축' },
  { key: 'reviews', label: '리뷰', title: '리뷰', desc: '공개 평가 · 피부 타입별 갈림과 자극 언급' },
  { key: 'behavior', label: '행동·마찰', title: '행동·마찰', desc: '화면이 막는 곳 · 상품 선호와 분리해서 본다' },
  { key: 'register', label: '상품 등록', title: '상품 등록', desc: '입력하면 고객 화면 그대로 미리보기' },
];

/**
 * HWABUN · 참여 브랜드(소상공인) 담당자용 대시보드 v0.2.
 *
 * 쇼핑몰과 진입점이 분리되어 있다 (/dashboard.html · 쇼핑몰 어디에서도 링크하지 않는다).
 * 실제 접근 제어(계정·권한)는 백엔드 범위이고, 여기서는 화면과 지표 정의를 확정한다.
 *
 * 화면은 사이드바 하나로 고정이고 색도 HWABUN 이다. 브랜드마다 다른 것은 대시보드가 아니라
 * **고객이 보는 쇼핑몰**이다. 가입할 때 쇼핑몰의 진열 레이아웃과 색을 고르고(Onboarding),
 * 그 값은 같은 브라우저의 쇼핑몰(index.html)에 바로 반영된다. 사이드바 "쇼핑몰 설정" 으로 다시 고칠 수 있다.
 */
export default function DashboardApp() {
  /** main.tsx 의 AuthGate 를 지나 왔으므로 null 이 아니다. 만료되면 게이트가 다시 로그인으로 바꾼다 */
  const seller = useAuth('SELLER');
  const [storefront, setStorefront] = useState<StorefrontPrefs | null>(() => loadStorefront());
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
  const [editing, setEditing] = useState(false);
  const [screen, setScreen] = useState<ScreenKey>('overview');
  const [days, setDays] = useState(14);
  /** 리뷰·성분 화면이 공유하는 상품 선택 */
  const [productId, setProductId] = useState<string | null>(null);

  const commit = (next: StorefrontPrefs) => {
    saveStorefront(next);
    setStorefront(next);
    setEditing(false);
  };

  if (storefront === null || editing) {
    return (
      <Onboarding
        initial={storefront ?? DEFAULT_STOREFRONT}
        onDone={commit}
        onCancel={storefront === null ? undefined : () => setEditing(false)}
      />
    );
  }

  const active = SCREENS.find((s) => s.key === screen) ?? SCREENS[0];
  const storefrontSummary = describeStorefront(storefront);

  return (
    <div className="console">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <img src="/brand/hwabun-mark.png" alt="" width="34" height="34" />
          <div>
            <strong>HWABUN</strong>
            <span>{brand?.name || storefront.brandName || DEMO_BRAND}</span>
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
              const created = await createBrand(storefront.brandName || DEMO_BRAND);
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

        {/* 내 쇼핑몰 · 고객이 보는 화면. 진열 설정과 바로가기 */}
        <div className="sidebar__shop">
          <p className="sidebar__shop-label">내 쇼핑몰</p>
          <p className="sidebar__shop-state">
            {storefrontSummary}
          </p>
          <div className="sidebar__shop-actions">
            <button type="button" className="sidebar__settings" onClick={() => setEditing(true)}>
              쇼핑몰 설정
            </button>
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

        {screen === 'overview' ? <OverviewScreen days={days} /> : null}
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
