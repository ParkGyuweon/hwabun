/**
 * 리뷰어 피부 타입 분포 → 상품 피부 타입 표기. 의존성이 없는 순수 계산이라 따로 둔다 —
 * 화면(`lib/format.ts` 가 다시 내보낸다)과 dev 서버·빌드 플러그인(`plugins/review-chunks.ts`)이 같은 규칙을 쓴다.
 */
import type { SkinType } from '../types/product.ts';

/** 이 함수가 읽는 것은 리뷰의 피부 타입뿐이다 */
export interface HasSkinType {
  skin_type: SkinType | null | undefined;
}

/** 리뷰에서 파생한 피부 타입 분포 */
export interface DerivedSkinTypes {
  /** 표기할 만큼 비중이 있는 타입. 비중 큰 순서 */
  types: SkinType[];
  /** 타입별 비중 (0~1) */
  shares: Map<SkinType, number>;
  /** 근거가 된 리뷰 수. 화면에 같이 보여준다 */
  sampleSize: number;
}

/** 이 비중을 넘는 타입만 표기한다. 한두 명 때문에 칩이 붙는 것을 막는다 */
export const SKIN_TYPE_MIN_SHARE = 0.2;

/**
 * 상품 정보에 피부 타입 표기가 없을 때 리뷰로 채운다.
 *
 * 데이터셋 상품 200개 중 132개(66%)에 `suitable_skin_types` 가 비어 있다.
 * 대신 리뷰마다 작성자의 피부 타입이 붙어 있어서, 그 분포로 대신할 수 있다.
 *
 * **브랜드가 표기한 값이 아니라 리뷰어 분포다.** 성격이 다르므로
 * `suitable_skin_types` 를 덮어쓰지 않고 따로 계산해서 화면에서 구분해 보여준다.
 * (`suitable_skin_types` 는 데이터 담당자가 내려주는 원본 필드다)
 */
export function deriveSkinTypesFromReviews(reviews: HasSkinType[]): DerivedSkinTypes {
  const counts = new Map<SkinType, number>();

  for (const review of reviews) {
    if (!review.skin_type) continue;
    counts.set(review.skin_type, (counts.get(review.skin_type) ?? 0) + 1);
  }

  const sampleSize = [...counts.values()].reduce((sum, n) => sum + n, 0);
  const shares = new Map<SkinType, number>();
  if (sampleSize === 0) return { types: [], shares, sampleSize: 0 };

  for (const [type, n] of counts) shares.set(type, n / sampleSize);

  const types = [...shares.entries()]
    .filter(([, share]) => share >= SKIN_TYPE_MIN_SHARE)
    .sort((a, b) => b[1] - a[1])
    .map(([type]) => type);

  return { types, shares, sampleSize };
}
