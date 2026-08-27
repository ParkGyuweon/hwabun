/**
 * 세포라 이미지 CDN 유틸.
 *
 * 데이터셋에 이미지가 없어 세포라 CDN URL 을 그대로 담고 있다.
 * 원본은 장당 200~400KB 라서 썸네일까지 원본으로 받으면 갤러리 한 번에 수 MB 가 된다.
 * CDN 이 imwidth 쿼리로 리사이즈를 지원하므로 쓰이는 자리마다 폭을 지정한다.
 */

/** 갤러리 메인 뷰 */
export const IMAGE_WIDTH_MAIN = 1024;
/** 갤러리 썸네일 */
export const IMAGE_WIDTH_THUMB = 160;
/** 옵션 스와치, 추천 카드 */
export const IMAGE_WIDTH_SWATCH = 128;

const CDN_ORIGIN = 'https://www.sephora.com/productimages/sku/';
/** dev 서버가 대신 받아 디스크에 캐시해 주는 경로 (frontend/plugins/image-cache.ts) */
const LOCAL_PROXY = '/cdn/sku/';

export function sizedImage(url: string | null, width: number): string | null {
  if (!url) return null;

  // 로컬 정적 파일(placeholder 등)에는 붙이지 않는다
  if (!url.startsWith(CDN_ORIGIN)) return url;

  const sized = url.includes('imwidth=')
    ? url
    : `${url}${url.includes('?') ? '&' : '?'}imwidth=${width}`;

  /**
   * 개발 중에는 dev 서버 캐시를 거친다.
   * 세포라에서 직접 받으면 한 장에 수 초씩 걸리는데, 행동 로그를 재는 페이지라
   * 그 로딩 시간이 체류 시간으로 잡혀 실험 데이터가 오염된다.
   * 배포 빌드에는 그 미들웨어가 없으므로 원래 CDN 주소를 그대로 쓴다.
   */
  return import.meta.env.DEV ? sized.replace(CDN_ORIGIN, LOCAL_PROXY) : sized;
}
