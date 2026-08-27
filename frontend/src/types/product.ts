/**
 * 상품 타입.
 *
 * 데이터 담당자 전달 스키마 기준 (docs/data/README.md).
 * 배열 필드는 원본이 null이면 [] 로 내려오므로 null 체크가 필요 없다.
 */
export interface Product {
  product_id: string;
  product_name: string;
  brand_name: string;
  /** 계층 순서. 길이 2~3 가변이므로 인덱스로 접근하지 말 것 */
  category: string[];
  /** 데이터셋에 이미지가 없어 현재는 항상 null */
  image_url: string | null;
  price_usd: number;
  /** 자유 텍스트. 파싱하지 말고 그대로 표시 */
  size: string | null;
  rating: number | null;
  review_count: number | null;
  highlights: string[];
  /** 원소 1개에 전 성분이 쉼표로 이어붙은 통짜 문자열인 경우가 대부분 */
  ingredients: string[];
  /** 파생 필드. 빈 배열인 상품이 절반 가까이 된다 */
  suitable_skin_types: SkinType[];
  skincare_concerns: string[];
}

export type SkinType = 'combination' | 'dry' | 'normal' | 'oily';
