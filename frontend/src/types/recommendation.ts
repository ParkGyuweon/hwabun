/**
 * 추천 API 응답. 계약 `contracts/recommendation-io-spec.md` §5 · §5-1 (2026-09-07, 제안).
 *
 * 한 화면의 17칸(히어로 1 + 배너 6 + 메인 10)이 **한 응답**에서 나온다.
 * 나눠서 두 번 부르면 같은 상품이 히어로와 배너에 겹치거나 중복 제거를 프론트가 떠안는다.
 * `items` 와 `banners` 의 product_id 는 서로 겹치지 않고, `hero` 만 `items[0]` 과 같을 수 있다.
 */
import type { BannerType } from './log';

export interface RecommendItem {
  product_id: string;
  score: number;
  rank: number;
}

export interface RecommendHero {
  product_id: string;
  banner_type: BannerType;
  /** 어휘집 원문. `new_brand` 는 null */
  banner_value: string | null;
}

export interface RecommendBanner {
  /** 배너 영역에서 몇 번째 칸인가 (1부터) */
  slot: number;
  banner_type: BannerType;
  banner_value: string | null;
  product_id: string;
  score: number;
  /** 신규·저노출 브랜드 전용 칸 */
  reserved?: boolean;
}

export interface RecommendResponse {
  user_id: string;
  generated_at: string;
  /** 배치·모델 판. 프론트 목은 `mock-fe-*` */
  model_version: string;
  items: RecommendItem[];
  hero: RecommendHero | null;
  banners: RecommendBanner[];
}

export interface RecommendRequest {
  user_id: string;
  k: number;
  banner_slots: number;
  reserved: number;
  /** 세션 성향이 고른 축 순서. 없으면 서버 기본값(concern, segment) */
  axes?: BannerType[];
}
