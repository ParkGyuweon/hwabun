import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import PlatformApp from './PlatformApp';
import '../dashboard/dashboard.css';
import '../dashboard/dashboard-themes.css';
import './platform.css';
// 시각 레이어. 맨 마지막
import '../dashboard/dashboard-apple.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <PlatformApp />
  </StrictMode>,
);
