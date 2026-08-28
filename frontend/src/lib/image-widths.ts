/**
 * 이미지 요청 폭.
 *
 * `scripts/warm-images.ts` 도 같은 값을 써야 캐시가 화면이 실제로 요청하는
 * 주소와 맞는다. 어긋나면 워밍은 성공했다고 나오는데 화면은 캐시를 못 맞고
 * 세포라에서 직접 받아서 느려진다. 그래서 상수를 여기 한 군데 둔다.
 *
 * 이 파일은 `import.meta.env` 같은 Vite 전용 값을 쓰지 않는다.
 * warm-images 가 node 로 그대로 import 하기 때문이다.
 *
 * 값은 실제 표시 크기를 재서 정했다 (viewport 1280 / dpr 1 기준).
 * CDN 은 `imwidth` 로 리사이즈해 주고, 폭에 따라 용량이 크게 달라진다.
 * 같은 파일 기준: 128px 7KB · 160px 15KB · 384px 45KB · 768px 178KB · 1024px 532KB.
 * 768 을 넘기면 사실상 원본이 와서 장당 500KB 가 넘는다.
 */

/** 갤러리 메인 뷰. 표시 560px */
export const IMAGE_WIDTH_MAIN = 768;
/** 갤러리 썸네일. 표시 71px */
export const IMAGE_WIDTH_THUMB = 160;
/** 옵션 스와치. 표시 62px */
export const IMAGE_WIDTH_SWATCH = 128;
/** 추천 상품 카드. 표시 181px */
export const IMAGE_WIDTH_CARD = 384;
