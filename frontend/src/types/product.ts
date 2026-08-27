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
  /** 대표 이미지. 세포라 CDN 에서 sku_id 기준으로 수집했다 */
  image_url: string | null;
  /** 세포라 SKU 번호. 이미지 URL 조립 키 */
  sku_id: string | null;
  /** 대표 이미지 외 추가 갤러리 이미지 */
  images: string[];
  /** 색상/향/용량 등 구매 옵션 */
  variants: ProductVariant[];
  /** 원본 상세 설명. 데이터셋에 없어 세포라에서 별도 수집했다 */
  description: ProductDescription | null;
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

/** 구매 옵션 하나. 세포라는 옵션마다 SKU 와 이미지가 따로 있다 */
export interface ProductVariant {
  sku_id: string;
  /** 옵션 표기명. 색상명, 향, 용량 등이 그대로 들어온다 */
  label: string;
  image_url: string;
}

/**
 * 세포라 About the Product 원문.
 *
 * 영문 원문을 그대로 담는다. 없는 항목은 null 이며 화면에서 해당 블록을 숨긴다.
 */
export interface ProductDescription {
  what_it_is: string | null;
  skin_type: string | null;
  concerns_text: string | null;
  highlighted_ingredients: string[];
  ingredient_callouts: string | null;
  what_else: string | null;
  clinical_results: string | null;
  suggested_usage: string | null;
  brand_story: string | null;
}
