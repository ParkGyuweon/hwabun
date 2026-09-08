import { useState } from 'react';
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
import { useAuth } from '../hooks/useAuth';
import { logout } from '../lib/auth';

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

const SCREENS: Array<{ key: ScreenKey; label: string; title: string; desc: string }> = [
  { key: 'overview', label: 'Overview', title: 'Overview', desc: '전체 성과와 핵심 KPI' },
  { key: 'register', label: '상품 등록', title: '상품 등록', desc: '입력하면 고객이 보는 상세 페이지 그대로 미리 보입니다' },
  { key: 'products', label: '상품 분석', title: '상품 분석', desc: '상품별 관심도와 전환 성과' },
  {
    key: 'content',
    label: '정보 관심도',
    title: '정보 관심도',
    desc: '무엇을 보여줘야 사는가 — 콘텐츠 단위 주목도',
  },
  {
    key: 'segments',
    label: '고객군',
    title: '고객군 분석',
    desc: '피부 타입 × 톤별 전환과 콘텐츠 선호',
  },
  {
    key: 'behavior',
    label: '행동 분석',
    title: '사용자 행동 분석',
    desc: '의도 퍼널·이탈 구간·마찰 신호',
  },
  { key: 'reviews', label: '리뷰 분석', title: '리뷰 분석', desc: '소비자 평가와 자극·트러블' },
  { key: 'feedback', label: '고객 피드백', title: '고객 피드백', desc: '고객이 쓴 글을 효능·사용감·향·용기·용량 5축으로 나눠 받고 반영 처리' },
  {
    key: 'ingredients',
    label: '성분 분석',
    title: '성분 분석',
    desc: '성분 구성과 성분 정보 관심',
  },
];

/**
 * HWABUN — 참여 브랜드(소상공인) 담당자용 대시보드 v0.2.
 *
 * 쇼핑몰과 진입점이 분리되어 있다 (/dashboard.html — 쇼핑몰 어디에서도 링크하지 않는다).
 * 실제 접근 제어(계정·권한)는 백엔드 범위이고, 여기서는 화면과 지표 정의를 확정한다.
 *
 * 화면은 사이드바 하나로 고정이고 색도 HWABUN 이다 — 브랜드마다 다른 것은 대시보드가 아니라
 * **고객이 보는 쇼핑몰**이다. 가입할 때 쇼핑몰의 진열 레이아웃과 색을 고르고(Onboarding),
 * 그 값은 같은 브라우저의 쇼핑몰(index.html)에 바로 반영된다. 사이드바 "쇼핑몰 설정" 으로 다시 고칠 수 있다.
 */
export default function DashboardApp() {
  /** main.tsx 의 AuthGate 를 지나 왔으므로 null 이 아니다. 만료되면 게이트가 다시 로그인으로 바꾼다 */
  const seller = useAuth('SELLER');
  const [storefront, setStorefront] = useState<StorefrontPrefs | null>(() => loadStorefront());
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
            <span>{storefront.brandName || DEMO_BRAND}</span>
          </div>
        </div>

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

        {/* 내 쇼핑몰 — 고객이 보는 화면. 진열 설정과 바로가기 */}
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
