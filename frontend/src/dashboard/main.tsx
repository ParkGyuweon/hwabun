import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import DashboardApp from './DashboardApp';
import AuthGate from '../components/auth/AuthGate';
import DemoBanner from '../components/DemoBanner';
import ErrorBoundary from '../components/ErrorBoundary';
// 글꼴 정본 (--font-sans). dashboard.css 의 --font 가 이 값을 받으므로 먼저 와야 한다
import '../styles/pretendard.css';
import './dashboard.css';
import './dashboard-themes.css';
// 시각 레이어. 컴포넌트·테마 다음에 와야 한다
import './dashboard-apple.css';
// 가입 화면의 쇼핑몰 미리보기. 시각 레이어의 .onboard 규칙을 덮어야 해서 맨 마지막이다
import './storefront-preview.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    {/* 발표용 상단 띠 · 늘 켜짐 */}
    <DemoBanner role="seller" />
    {/* 브랜드 담당자(SELLER) 로그인 · shop_backend /api/auth */}
    <ErrorBoundary>
      <AuthGate
        role="SELLER"
        product={{ mark: '/brand/hwabun-mark.png', name: 'HWABUN', tagline: '브랜드 사장님을 위한 판매 현황판' }}
      >
        <DashboardApp />
      </AuthGate>
    </ErrorBoundary>
  </StrictMode>,
);
