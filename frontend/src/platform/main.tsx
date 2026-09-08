import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import PlatformApp from './PlatformApp';
import AuthGate from '../components/auth/AuthGate';
import '../dashboard/dashboard.css';
import '../dashboard/dashboard-themes.css';
import './platform.css';
// 시각 레이어. 맨 마지막
import '../dashboard/dashboard-apple.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    {/* 운영자(ADMIN) 로그인 — 가입 API 없음, 발급 계정만 */}
    <AuthGate
      role="ADMIN"
      product={{ mark: '/brand/hwabun-mark.png', name: 'HWABUN Platform', tagline: '운영자 화면 · 참여 브랜드 전체' }}
    >
      <PlatformApp />
    </AuthGate>
  </StrictMode>,
);
