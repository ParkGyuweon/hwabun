import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import { imageCache } from './plugins/image-cache.ts'
import { reviewChunks } from './plugins/review-chunks.ts'

// https://vite.dev/config/
export default defineConfig({
  // 상품 이미지를 세포라 CDN 에서 매번 받으면 한 장에 수 초씩 걸린다.
  // 행동 로그를 재는 페이지라 로딩 시간이 체류 시간으로 잡혀서, dev 서버가 캐시해 준다.
  // 리뷰는 상품별 JSON 조각으로 나눠 상세를 연 상품 것만 받는다 (plugins/review-chunks.ts)
  plugins: [react(), imageCache(), reviewChunks()],

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
       * 백엔드가 셋이다. 구체적인 경로를 먼저 적어야 '/api' 가 삼키지 않는다.
       *
       *   recommend    (8300)  추천·처방 문장·카탈로그 동기화                 batch/serving/
       *   shop_backend (8090)  로그인·브랜드·상품·주문·리뷰·피드백·대시보드   shop_backend/
       *   collector    (8080)  행동 로그 수집 /api/events                     backend/
       */
      ...Object.fromEntries(
        ['/api/recommend', '/api/prescription', '/api/catalog'].map((path) => [
          path,
          // 127.0.0.1: Windows 에서 localhost 는 ::1 을 먼저 시도해 요청마다 2초를 먹는다 (AI 회신 2026-09-11)
          { target: process.env.RECOMMEND_URL || 'http://127.0.0.1:8300', changeOrigin: true },
        ]),
      ),
      ...Object.fromEntries(
        ['/api/auth', '/api/brands', '/api/products', '/api/cart', '/api/orders', '/api/reviews', '/api/feedback', '/api/seller', '/api/settlements', '/api/admin'].map(
          (path) => [path, { target: process.env.SHOP_BACKEND_URL || 'http://localhost:8090', changeOrigin: true }],
        ),
      ),
      // 로그 수집 서버. 안 떠 있으면 프론트는 재시도만 한다
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        /*
         * 수집기는 Origin 을 ALLOWED_ORIGINS(기본 localhost:3000·5173)와 대조해 아니면 403 "Invalid CORS request" 를 낸다.
         * 이 프록시는 같은 출처라 CORS 가 성립하지 않는데 브라우저의 Origin 이 그대로 전달돼, dev 서버가 5173 이 아닌
         * 포트(autoPort)에 뜨면 모든 이벤트가 403 으로 버려진다 (2026-09-11 리허설에서 실측). 프록시에서 Origin 을 뗀다.
         * 배포에서는 nginx 가 같은 역할을 하거나 ALLOWED_ORIGINS 에 실제 도메인이 있어야 한다.
         */
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.removeHeader('origin');
          });
        },
      },
    },
  },
})
