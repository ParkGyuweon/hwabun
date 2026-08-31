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
       * 쇼핑몰과 관리자 대시보드를 별도 진입점으로 나눈다.
       * 대시보드는 쇼핑몰 어디에서도 링크되지 않는다 — 브랜드 담당자 전용이고,
       * 실제 접근 제어(로그인)는 백엔드 범위다.
       */
      input: {
        shop: fileURLToPath(new URL('./index.html', import.meta.url)),
        dashboard: fileURLToPath(new URL('./dashboard.html', import.meta.url)),
      },
    },
  },

  server: {
    // 다른 세션이 5173 을 쓰고 있을 때 PORT 로 비켜 띄울 수 있게 한다
    port: Number(process.env.PORT) || undefined,
    proxy: {
      // 로그 수집 서버(Spring, 기본 8080)로 넘긴다. 안 떠 있으면 프론트는 재시도만 한다
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
