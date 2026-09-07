/**
 * 배너 문구 틀. 축과 값(라벨)만 바뀌고 나머지는 같다.
 *
 * "광고" 라는 말을 쓰지 않는다. 배너는 유료 광고가 아니라 추천 결과를 강조해 보여 주는
 * 영역이다 (기획 §15-10). 문구가 광고처럼 읽히면 추천 신뢰도가 떨어진다.
 */
import { bannerValueLabel } from '../../lib/vocabLabels';
import type { BannerType } from '../../types/log';

export interface BannerCopy {
  /** 작은 글씨. 왜 이 자리에 있는지 */
  kicker: string;
  /** 큰 글씨 */
  headline: string;
}

export function bannerCopy(type: BannerType, value: string | null): BannerCopy {
  const label = bannerValueLabel(type, value);
  switch (type) {
    case 'concern':
      return { kicker: '피부 고민', headline: `${label}이 고민이라면` };
    case 'ingredient':
      return { kicker: '성분으로 고르기', headline: `${label}이 들어간` };
    case 'clean':
      return { kicker: '성분 표방', headline: `${label} 제품 중에서` };
    case 'price_bin':
      return { kicker: '가격대', headline: `${label}에서 고르면` };
    case 'category':
      return { kicker: '카테고리', headline: `${label} 중에서` };
    case 'segment':
      return { kicker: '같은 피부의 선택', headline: `${label} 사용자가 반응한` };
    case 'new_brand':
      return { kicker: '새로 입점', headline: '새로 들어온 브랜드' };
    default:
      return { kicker: '추천', headline: '지금 주목할 상품' };
  }
}
