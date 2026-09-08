import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import DashboardApp from './DashboardApp';
import AuthGate from '../components/auth/AuthGate';
import './dashboard.css';
import './dashboard-themes.css';
// 시각 레이어. 컴포넌트·테마 다음에 와야 한다
import './dashboard-apple.css';
// 가입 화면의 쇼핑몰 미리보기. 시각 레이어의 .onboard 규칙을 덮어야 해서 맨 마지막이다
import './storefront-preview.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    {/* 브랜드 담당자(SELLER) 로그인 — shop_backend /api/auth */}
    <AuthGate
      role="SELLER"
      product={{ mark: '/brand/hwabun-mark.png', name: 'HWABUN', tagline: '참여 브랜드 담당자 대시보드' }}
    >
      <DashboardApp />
    </AuthGate>
  </StrictMode>,
);
