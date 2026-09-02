import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import DashboardApp from './DashboardApp';
import './dashboard.css';
import './dashboard-themes.css';
// 시각 레이어. 컴포넌트·테마 다음에 와야 한다
import './dashboard-apple.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <DashboardApp />
  </StrictMode>,
);
