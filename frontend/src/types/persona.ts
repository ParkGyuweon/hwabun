import type { SkinType } from './product';

/**
 * 가상 페르소나.
 *
 * 세포라 리뷰 작성자를 그대로 유저로 쓰는 대신, 리뷰에 붙은 피부 프로필만 뽑아서 만든다.
 * 실제 페르소나 생성은 데이터 담당 범위이고, 여기서는 프론트 QA 를 위해 샘플에서 파생시킨다.
 */
export interface PersonaProfile {
  persona_id: string;
  skin_type: SkinType;
  skin_tone: string;
  eye_color: string;
  hair_color: string;
  /** 이 페르소나가 샘플 안에서 리뷰를 남긴 상품 수 */
  reviewed_product_count: number;
}
