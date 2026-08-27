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

const CDN_HOST = 'www.sephora.com';

export function sizedImage(url: string | null, width: number): string | null {
  if (!url) return null;

  // 로컬 정적 파일(placeholder 등)에는 붙이지 않는다
  if (!url.includes(CDN_HOST)) return url;
  if (url.includes('imwidth=')) return url;

  return `${url}${url.includes('?') ? '&' : '?'}imwidth=${width}`;
}
