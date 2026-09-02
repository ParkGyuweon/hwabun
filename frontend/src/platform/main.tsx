import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import PlatformApp from './PlatformApp';
import '../dashboard/dashboard.css';
import '../dashboard/dashboard-themes.css';
import './platform.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <PlatformApp />
  </StrictMode>,
);
