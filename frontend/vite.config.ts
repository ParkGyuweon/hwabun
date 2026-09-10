import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import { imageCache } from './plugins/image-cache.ts'

// https://vite.dev/config/
export default defineConfig({
  // 상품 이미지를 세포라 CDN 에서 매번 받으면 한 장에 수 초씩 걸린다.
  // 행동 로그를 재는 페이지라 로딩 시간이 체류 시간으로 잡혀서, dev 서버가 캐시해 준다.
  plugins: [react(), imageCache()],

  build: {
    rollupOptions: {
      /*
       * 세 진입점을 나눈다. 서로 어디에서도 링크되지 않는다.
       *
       *   shop       BLOOM  — 테스트 쇼핑몰. 가상 소비자와 실사용자가 들어온다
       *   dashboard  HWABUN — 참여 브랜드(소상공인) 담당자의 분석 화면
       *   platform   HWABUN Platform — 운영자(우리 팀)가 참여 브랜드 전체를 보는 화면
       *
       * 실제 접근 제어(로그인·권한)는 백엔드 범위다.
       */
      input: {
        shop: fileURLToPath(new URL('./index.html', import.meta.url)),
        dashboard: fileURLToPath(new URL('./dashboard.html', import.meta.url)),
        platform: fileURLToPath(new URL('./platform.html', import.meta.url)),
      },
    },
  },

  server: {
    // 다른 세션이 5173 을 쓰고 있을 때 PORT 로 비켜 띄울 수 있게 한다
    port: Number(process.env.PORT) || undefined,
    proxy: {
      /*
       * 백엔드가 둘이다. 구체적인 경로를 먼저 적어야 '/api' 가 삼키지 않는다.
       *
       *   shop_backend (8090)  로그인·브랜드·상품·주문·리뷰·피드백·대시보드   feat/shop-backend
       *   collector    (8080)  행동 로그 수집 /api/events                     backend/
       */
      ...Object.fromEntries(
        ['/api/auth', '/api/brands', '/api/products', '/api/cart', '/api/orders', '/api/reviews', '/api/feedback', '/api/seller', '/api/settlements', '/api/admin'].map(
          (path) => [path, { target: process.env.SHOP_BACKEND_URL || 'http://localhost:8090', changeOrigin: true }],
        ),
      ),
      // 로그 수집 서버. 안 떠 있으면 프론트는 재시도만 한다
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
