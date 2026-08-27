# 배치 입력 데이터

| 파일 | 내용 |
|---|---|
| `products_200.json` | 상위 200개 상품 (`product_info` 27개 컬럼 + 병합·리뷰 통계) |
| `excluded_products.json` | 카테고리 사유로 제외된 상품 3개와 사유 |
| `affinity_lift.csv` | Attribute Affinity 테이블 4,000행 (200상품 × 21세그먼트) |

## products_200.json

- 200개 그룹이 실제로는 **262개 원본 `product_id`** 를 포함합니다 (사이즈 변형 병합)
- 리뷰 조인 시 `_merged.member_product_ids` 전체로 `IN` 조건을 걸어야 누락이 없습니다
- `_review_stats.segment_counts`는 정규화 후 값 기준 (`skin_tone` 5버킷, `eye_color` `gray` 병합)

## affinity_lift.csv

컬럼: `attribute`, `segment`, `group_id`, `rank`, `product_name`, `brand_name`, `n_reviews`, `share`, `base_share`, `lift`, `affinity`, `rating_affinity`, `z_score`

`affinity`가 추천 점수에 사용되는 값이고, `rating_affinity`는 폐기된 평점 기반 방식의 비교용입니다.

스키마와 계산 방식은 [`contracts/recommendation-io-spec.md`](../../../contracts/recommendation-io-spec.md) 3장 참조.

## 원본 데이터셋

Sephora 원본 CSV(약 520MB)는 커밋하지 않습니다. Kaggle "Sephora Products and Skincare Reviews" 데이터셋이며, 정제 기준은 개인 폴더의 `DATA_CLEANING.md`에 있습니다.
