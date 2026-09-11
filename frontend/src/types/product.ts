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
  /**
   * 할인가 (표시 전용). 이벤트·추천은 정가 `price_usd` 를 본다 (결정 2026-09-10, lib/discount.ts).
   * 단일 출처는 mocks/discounts.json. 백엔드 카탈로그가 붙으면 옵션 salePriceKrw 에서 온다.
   */
  sale_price_usd?: number | null;
  /** 0~1. 배지의 % 는 여기서 계산하지 않고 discountPercent() 로 낸다 */
  discount_rate?: number;
  /** "입점 기념" 처럼 할인 이유 한 마디 */
  discount_label?: string;
  /** 자유 텍스트. 파싱하지 말고 그대로 표시 */
  size: string | null;
  rating: number | null;
  review_count: number | null;
  /** 데이터셋의 인기 순위. 목록 기본 정렬에 쓴다 */
  rank?: number;
  /** 세포라 좋아요 수. 인기도 정렬 보조 */
  loves_count?: number | null;
  /**
   * 화면 배지. 원본 플래그를 그대로 옮긴 값이다.
   * 할인율은 여기 없다. 가격 옆에 PriceTag 가 `sale_price_usd` 로 그린다.
   */
  badges?: ProductBadge[];
  /**
   * 등록 시각 (ISO-8601). 등록 상품만 있고 원천 200개는 없다. 신규 배지·추천 신규 판정의
   * 기준(등록 후 14일, `lib/newBrandRule.ts`). 백엔드 요약 `createdAt` 이 오면 여기로 (요청서 9-11)
   */
  created_at?: string | null;
  highlights: string[];
  /** 원소 1개에 전 성분이 쉼표로 이어붙은 통짜 문자열인 경우가 대부분 */
  ingredients: string[];
  /**
   * 한국어 전성분 (표시 전용). 분석·매칭은 위 영문 `ingredients` 를 읽는다.
   * 번역이 없는 상품(시드·브랜드 등록)은 비어 있고, 화면은 `ingredients` 로 대신한다.
   */
  ingredients_ko?: string[];
  /** 파생 필드. 빈 배열인 상품이 절반 가까이 된다 */
  suitable_skin_types: SkinType[];
  skincare_concerns: string[];
  /**
   * 어디서 온 상품인가. 백엔드(shop_backend)에서 온 상품만 장바구니·주문·피드백 API 를 탈 수 있다.
   * 세포라 200개·SSAFY Beauty 시드는 백엔드 DB 에 없어서 목 경로다. 비어 있으면 목이다.
   */
  source?: 'backend' | 'brand_registered';
  /** 백엔드 브랜드 id. 판매자 피드백·대시보드 조회에 쓴다 */
  backend_brand_id?: string;
}

export type SkinType = 'combination' | 'dry' | 'normal' | 'oily';

/** 원본 플래그에서 그대로 옮긴 배지 종류 */
export type ProductBadge = 'new' | 'limited' | 'exclusive' | 'online_only';

/** 구매 옵션 하나. 세포라는 옵션마다 SKU 와 이미지가 따로 있다 */
export interface ProductVariant {
  sku_id: string;
  /** 옵션 표기명. 색상명, 향, 용량 등이 그대로 들어온다 */
  label: string;
  /** 이 옵션을 골랐을 때 갤러리에 뜨는 상품 사진 */
  image_url: string;
  /**
   * 옵션 버튼에 들어가는 작은 스와치. 세포라는 상품 사진과 별도로 62px 짜리를 준다.
   * 이걸 갤러리에 쓰면 확대돼서 뭉개지므로 자리를 나눠 둔다. 없으면 image_url 로 대신한다.
   */
  swatch_url: string | null;
  /** 백엔드 옵션 id. 장바구니 API(POST /api/cart/items) 는 이 값으로 담는다. 목 상품은 없다 */
  variant_id?: string;
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
