import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DemoBanner from './components/DemoBanner'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* 발표용 상단 띠 · ?demo=shopper 일 때만 */}
    <DemoBanner />
    <App />
  </StrictMode>,
)
