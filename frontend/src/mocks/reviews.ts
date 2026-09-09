/**
 * 쇼핑몰이 읽는 리뷰 · 제목·본문만 한국어로 바꿔 끼운 것.
 *
 * 대시보드는 이 파일을 쓰지 않고 `reviews.sample.json` 원본을 읽는다. 자극·트러블·요인
 * 언급 지표가 영문 정규식이라서다 (dashboard/lib/metrics.ts). 한 데이터를 두 화면이
 * 다른 언어로 읽는 것이 어색해 보이지만, 지표가 조용히 0 이 되는 것보다 낫다.
 */
import reviewsData from './reviews.sample.json';
import { localizeReview } from '../lib/localize';
import type { Review } from '../types/review';

export const reviews: Review[] = (reviewsData as unknown as Review[]).map(localizeReview);
