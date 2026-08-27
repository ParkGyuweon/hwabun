import type { SkinType } from './product';

/**
 * 리뷰 타입.
 *
 * 사용자 속성 4개(skin_type/skin_tone/eye_color/hair_color)가 모두 채워진
 * 리뷰만 전달되므로 해당 필드에는 null이 없다.
 */
export interface Review {
  /** 유니크 키. (author_id, product_id) 조합은 중복될 수 있으므로 반드시 이걸 쓸 것 */
  review_id: string;
  product_id: string;
  author_id: string;
  rating: number;
  is_recommended: boolean | null;
  /** 약 31% 가 null */
  review_title: string | null;
  review_text: string | null;
  /** "2021-04-29" */
  submission_time: string;
  skin_type: SkinType;
  skin_tone: string;
  eye_color: string;
  hair_color: string;
}
