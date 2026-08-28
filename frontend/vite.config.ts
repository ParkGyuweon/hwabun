import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { imageCache } from './plugins/image-cache.ts'

// https://vite.dev/config/
export default defineConfig({
  // 상품 이미지를 세포라 CDN 에서 매번 받으면 한 장에 수 초씩 걸린다.
  // 행동 로그를 재는 페이지라 로딩 시간이 체류 시간으로 잡혀서, dev 서버가 캐시해 준다.
  plugins: [react(), imageCache()],
})
