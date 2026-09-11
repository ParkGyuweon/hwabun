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
  /**
   * `hero=new_brand` 로 뽑힌 히어로는 `items` 밖 상품이라 서버가 이름·점수·근거를 같이 준다
   * (AI 회신 2026-09-10). `top` 히어로(items[0])에는 없다.
   */
  product_name?: string;
  brand_name?: string;
  score?: number;
  reason?: string;
  product_source?: string;
  /** 신규 브랜드 몫으로 뽑혔다는 표시. 전용 칸 `reserved` 와 같은 뜻 */
  reserved?: boolean;
}

/** 히어로 정책. 요청 `hero=` 와 응답 `hero_policy` 가 같은 값 집합을 쓴다 */
export type HeroPolicy = 'top' | 'new_brand';

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
  /**
   * 이 응답 한 번을 가리키는 귀속 키. **응답마다 새로 발급된다.**
   *
   * 프론트가 지어내면 안 되는 값이다 (`recommendation-io-spec.md` §5, 추천 서버
   * `recommend_server.py` 주석: "FE 는 recommendation_click · product_view 에
   * recommendation_id / list_id / position / algorithm 을 그대로 싣는다").
   * 전에는 화면이 `rec-promo-{persona_id}` 를 만들어 썼는데, 그러면 같은 사람의
   * 모든 요청이 한 값으로 묶여 노출-클릭 귀속이 세션 단위로 뭉개진다.
   *
   * 서버가 붙으면 이 필드에 서버 값이 그대로 들어온다.
   */
  recommendation_id: string;
  /** 메인 목록(`items`) 의 목록 식별자. 서버는 `"main"` 을 준다 */
  list_id: string;
  /** 히어로·배너 줄의 목록 식별자. 서버는 `"banner_row"` 를 준다 */
  banner_list_id: string;
  items: RecommendItem[];
  hero: RecommendHero | null;
  banners: RecommendBanner[];
  /**
   * 실제로 적용된 히어로 정책. `hero=new_brand` 를 요청했어도 신규 상품이 없으면 `top` 으로 온다.
   * `banner_daily` 에서 `policy_version` 과 함께 자르는 키 (AI 회신 2026-09-10)
   */
  hero_policy?: HeroPolicy;
}

export interface RecommendRequest {
  user_id: string;
  k: number;
  banner_slots: number;
  reserved: number;
  /** 세션 성향이 고른 축 순서. 없으면 서버 기본값(concern, segment) */
  axes?: BannerType[];
  /** 히어로 정책. 기본 `top` (예전 호출은 아무것도 안 바뀐다) */
  hero?: HeroPolicy;
}
