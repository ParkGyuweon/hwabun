# 배치 입력 데이터

| 파일 | 내용 |
|---|---|
| `products_200.json` | 상위 200개 상품 (`product_info` 27개 컬럼 + 병합·리뷰 통계) |
| `affinity_lift.csv` | Attribute Affinity 테이블 4,000행 (200상품 × 20세그먼트) |

---

## products_200.json

- 200개 그룹이 실제로는 **262개 원본 `product_id`** 를 포함합니다 (사이즈 변형 병합)
- 리뷰 조인 시 `_merged.member_product_ids` 전체로 `IN` 조건을 걸어야 누락이 없습니다
- `_review_stats.segment_counts`는 정규화 후 값 기준 (`skin_tone` 5버킷, `hair_color` `brunette`→`brown`, `eye_color` `Grey`→`gray`)

### 선정 기준

고유 리뷰어 수 상위 200개. 리뷰 수가 아니라 **고유 `author_id` 수** 기준입니다(한 사람이 같은 상품에 리뷰를 여러 번 단 경우가 있음).

| | 값 |
|---|---|
| 포함 리뷰 | 458,180건 |
| 리뷰어 수 범위 | 949 ~ 14,519명 |
| `primary_category` | Skincare 200/200 |

### 제외된 상품 4개

카테고리 또는 품목 성격이 스킨케어 단품이 아니어서 제외했습니다. 제외 후 201위까지 승격되었습니다.

| `product_id` | 상품 | 리뷰어 | 제외 사유 |
|---|---|---:|---|
| `P460512` | Tatcha Mini Liquid Silk Canvas | 1,774 | `secondary_category = Mini Size`. 실체는 **메이크업 프라이머** (정가 상품 카테고리 `Face > Face Primer`) |
| `P173726` | Shiseido Facial Cotton | 1,388 | **화장솜.** 전성분이 `"100% Cotton"`인 도구. 카테고리가 `Makeup Removers`로 잡혀 카테고리 필터를 통과 |
| `P456211` | goop GOOPGLOW Morning Skin Superpowder | 1,088 | `secondary_category = Wellness`. **먹는 뷰티 보충제** |
| `P470041` | Lancôme UV Expert Aquagel Duo | 1,007 | `secondary_category = Value & Gift Sets`. **2개 세트 상품**으로 벡터가 두 제품의 혼합이 됨 |

**제외 규칙** (`build_products_json.py`)

```python
EXCLUDE_SECONDARY = {"Mini Size", "Wellness", "Value & Gift Sets"}
EXCLUDE_PRODUCT_IDS = {"P173726": "화장솜. 전성분이 100% Cotton인 도구"}
```

> **주의:** 전성분 파싱 결과가 0개라고 자동 제외하면 안 됩니다. 84·86위는 단일 오일 제품(로즈힙 오일, 마룰라 오일)으로 정당한 스킨케어입니다. 개별 확인이 필요합니다.

---

## affinity_lift.csv

상품 × 사용자 속성 세그먼트별 친화도 표입니다. **4,000행** = 200상품 × 20세그먼트(`skin_type` 4 + `skin_tone` 5 + `hair_color` 6 + `eye_color` 5).

### 컬럼

| 컬럼 | 뜻 |
|---|---|
| `attribute` | `skin_type` / `skin_tone` / `hair_color` / `eye_color` |
| `segment` | 그 속성의 값 (`oily`, `deep`, `gray` …) |
| `group_id` | 상품 ID (병합 대표) |
| `rank`, `product_name`, `brand_name` | 상품 정보 (가독성용) |
| `n_reviews` | 이 상품 × 이 세그먼트의 리뷰 수 |
| `share` | 이 상품 리뷰 중 해당 세그먼트 비중 |
| `base_share` | 전체 리뷰 중 해당 세그먼트 비중 (기준선) |
| `lift` | `share / base_share`. 몇 배 많은가 |
| **`affinity`** | lift를 0~1로 변환. **추천 계산에 실제로 쓰이는 값** |
| `z_score` | 통계적 유의성. 절대값 3 이상이면 우연이 아님 |
| `rating_affinity` | **폐기된** 평점 기반 값. 비교용으로만 보존 |

### 계산식

```
share_shrunk = (관측수 + K × 기준비율) / (셀 표본수 + K),   K = 50
lift         = share_shrunk / 기준비율
affinity     = clip((lift - 0.60) / 1.00, 0, 1)
```

### 읽는 예시

```
Balancing Force Oil Control Toner, skin_type

segment      n_reviews  share   base_share  lift  affinity  z_score
oily              346   32.5%     12.3%     2.56    1.000    20.01
combination       591   55.5%     55.3%     1.00    0.405     0.18
dry                71    6.7%     19.2%     0.38    0.000   -10.35
```

지성 사용자가 평균보다 **2.56배** 많이 리뷰했으므로 지성용 제품입니다. 건성은 0.38배로 잘 쓰지 않습니다.

### 왜 평점이 아니라 구성비인가

리뷰의 **63.4%가 5점**이라 평점 기반 친화도는 판별력이 없었습니다(η² < 0.004). 같은 상품의 `rating_affinity`를 보면 4개 세그먼트가 0.831~0.881로 거의 같습니다. 구성비로 바꾸자 상품 내 편차가 10배 커졌습니다.

상세 근거는 [`contracts/cbf-technical-review.md`](../../../contracts/cbf-technical-review.md), 스키마는 [`contracts/recommendation-io-spec.md`](../../../contracts/recommendation-io-spec.md) 3장 참조.

---

## 원본 데이터셋

Sephora 원본 CSV(약 520MB)는 커밋하지 않습니다. Kaggle "Sephora Products and Skincare Reviews" 데이터셋이며, 정제 기준은 개인 폴더의 `DATA_CLEANING.md`에 있습니다.

## 재생성

```
cd <Research 폴더>
python build_products_json.py    # products_200.json
python build_affinity_lift.py    # affinity_lift.csv
```
