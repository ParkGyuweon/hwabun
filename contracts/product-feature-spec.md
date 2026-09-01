# Product Feature 후보표 및 Encoding 초안

> 버전 `0.4` · 2026-08-27 (최종 갱신 2026-08-31)
> 대상: 상위 200개 Sephora 스킨케어 상품
> 소비처: `batch/jobs/product_feature_job.py` → MySQL → `backend/recommend/RankingService`
> 어휘집: [`product-feature-vocab.json`](product-feature-vocab.json)

`category`, `highlights`, `price_usd`, `rating`, `loves_count` 5개 필드를 실측 분석하고 상품 벡터 Encoding 방식을 정의한 초안입니다. 모든 수치는 상위 200개 상품 전수 기준입니다.

---

## 0. 한눈에 보기

**콘텐츠 벡터 148차원 · 블록 가중치 합계 1.60**

| 순 | Feature | 담는 내용 | 원본 | 인코딩 | 차원 | 보유율 | 가중치 |
|---:|---|---|---|---|---:|---:|---:|
| 1 | `brand` | 브랜드 55종 | `brand_name` | 원핫 | **55** | 100% | **0.60** |
| 2 | `concern` | 피부 고민 9종 | `highlights` `Good for:` **+ 리뷰 추출** | 멀티핫 + IDF | 9 | 94.0% | **0.42** |
| 3 | `ingredient` | 핵심 성분 30종 | `highlights` 태그 + 전성분 파싱 | 멀티핫 + IDF + 위치가중 | 30 | 94.0% | 0.27 |
| 4 | `tertiary_category` | 세부 제품 종류 19종 | `tertiary_category` | 원핫 | 19 | 100% | 0.11 |
| 5 | `secondary_category` | 대분류 8종 | `secondary_category` | 원핫 | 8 | 100% | 0.06 |
| 6 | `clean` | 클린뷰티·성분 배제 16종 | `highlights` | 멀티핫 + IDF | 16 | 85.5% | 0.06 |
| 7 | `price_bin` | 가격대 5구간 | `price_usd` | 원핫 | 5 | 100% | 0.04 |
| 8 | `rating` | 평점 | `rating` | 스칼라 | 1 | 100% | 0.02 |
| 9 | `texture` | 제형·마감 5종 | `highlights` | 멀티핫 + IDF | 5 | 26.0% | 0.02 |

> **가중치 합계가 1.00 이 아닙니다.** `brand` 를 뒤에 추가하면서 1.60 이 됐습니다. 블록마다 L2 정규화 후 가중치를 곱하고 전체를 다시 L2 정규화하므로, 합계가 1 일 필요가 없습니다. 중요한 것은 **블록 간 비율**입니다.

### 왜 `brand` 가 0.60 인가

다음 구매에서 유지되는 속성 중 lift 가 압도적입니다. 리뷰 15만 연속쌍에서 측정했습니다.

| 속성 | 실제 유지율 | 무작위 | lift |
|---|---:|---:|---:|
| **`brand`** | **21.4%** | 3.5% | **6.08x** |
| `price_bin` | 28.9% | 22.2% | 1.30x |
| `clean` | 41.9% | 34.3% | 1.22x |
| `concern` | 31.3% | 27.9% | 1.12x |
| `ingredient` | 54.7% | 53.4% | 1.02x |

이 블록을 추가한 것만으로 Recall@10 이 **11.5% → 23.8%** 가 됐습니다 (+12.39%p, 95% CI [+11.55, +13.22], 대응 부트스트랩 2000회, 페르소나 9,900명).

**차원 순서에서 `brand` 는 맨 뒤입니다.** 앞에 끼워 넣으면 이미 저장된 사용자 벡터의 차원 의미가 통째로 밀려 전부 무효가 됩니다. 뒤에 붙이면 앞 93차원은 그대로입니다.

> **주의:** `brand` 를 뺀 나머지 가중치는 어휘집 `0.2` 확정값입니다. 카테고리 쏠림 측정에 따라 카테고리 두 블록을 실효 39% → 22.4%로 하향하고 그만큼을 `concern`·`ingredient`로 이관했습니다. 근거는 [`cbf-technical-review.md`](../docs/ai/cbf-technical-review.md) 4장 참조.

### 블록별 한계 기여 (ablation)

lift 는 **단독 예측력**이라 가중치의 근거로 쓰면 안 됩니다. 블록을 하나씩 빼서 전체 대비 손해를 재면 순서가 달라집니다.

| 뺀 블록 | 가중치 | Recall@10 | 전체 대비 | 95% CI |
|---|---:|---:|---:|---|
| **`brand`** | 0.60 | 11.8% | **−12.00%p** | [−12.78, −11.19] |
| **`ingredient`** | 0.27 | 23.2% | **−0.70%p** | [−0.98, −0.40] |
| `concern` | 0.42 | 23.4% | −0.48%p | [−0.97, +0.02] |
| `clean` / `texture` / `rating` / `price_bin` | 0.02~0.06 | 23.8% | ±0.01%p 이하 | 0 포함 |
| `secondary_category` / `tertiary_category` | 0.06 / 0.11 | 23.9% | +0.05%p | 0 포함 |

`lift` 상위권(`price_bin`, `clean`, 카테고리)은 **브랜드가 정해지면 따라오는 속성**이라, 브랜드를 넣은 뒤에는 새로 보태는 것이 없습니다. 반대로 `ingredient` 는 lift 가 꼴찌인데 한계 기여는 두 번째입니다.

### 제외한 것

| Feature | 이유 |
|---|---|
| **`skin_fit`** | **콘텐츠 벡터가 아니라 속성 친화도 테이블(`attr_affinity`)로 이관.** 2-2절 참조 |
| `primary_category` | 200개 전부 `Skincare` — 정보량 0 |
| `loves_count` | 상품 속성이 아니라 인기도. 추천 점수의 prior 항으로 분리 |
| popularity 태그 | `Community Favorite`, allure 수상. 인기 신호이지 제품 속성 아님 |

### 각 블록의 어휘

| 블록 | 값 |
|---|---|
| `concern` | Dullness/Uneven Texture, Dryness, Anti-Aging, Pores, Loss of firmness, Dark Circles, Acne/Blemishes, Redness, Dark spots |
| `tertiary_category` | Moisturizers, Face Serums, Face Wash & Cleansers, Eye Creams & Treatments, Face Masks, Lip Balms & Treatments, Face Sunscreen, Toners, Face Oils, Exfoliators, Facial Peels, Makeup Removers, Mists & Essences, BB & CC Creams, Blemish & Acne Treatments, For Face, Night Creams, Face Wipes, Eye Masks |
| `ingredient` | Hyaluronic Acid, Silicone, Vitamin C, Squalane, Probiotic/Ferment, Green Tea, Peptides, Aloe, Lactic Acid, Licorice, Shea Butter, Panthenol(B5), Niacinamide, Jojoba, AHA/Glycolic Acid, Salicylic Acid, Ceramide, Rosehip/Rose, Caffeine, Urea, Adenosine, Allantoin, Retinol, Zinc, Alcohol Denat, SPF, Centella(Cica), Willow Bark, Collagen, Mineral Oil/Petrolatum |
| `secondary_category` | Moisturizers, Treatments, Cleansers, Eye Care, Masks, Lip Balms & Treatments, Sunscreen, Self Tanners |
| `clean` | Clean at Sephora, Vegan, Without Parabens, Cruelty-Free, Clean + Planet Positive, Fragrance Free, Oil Free, Without Sulfates SLS & SLES, Without Silicones, Refill Available, Without Phthalates, Alcohol Free, Without Mineral Oil, Gluten Free, Hypoallergenic, Without Oxybenzone |
| `price_bin` | ~$20, $20-35, $35-50, $50-80, $80+ |
| `texture` | Hydrating, Plumping, Radiant Finish, Natural Finish, High Shine Finish |

### 인코딩 방식

| 방식 | 뜻 | 예시 |
|---|---|---|
| **원핫** (one-hot) | 여러 칸 중 **하나만** 1 | 한 상품은 클렌저이거나 수분크림. 둘 다일 수 없음 |
| **멀티핫 + IDF** (multi-hot) | **여러 칸이 동시에** 1. 흔한 값은 약하게 반영 | 비건이면서 파라벤 프리이면서 크루얼티프리일 수 있음 |
| **+ 위치 가중** | `ingredient` 전용. 전성분 앞쪽일수록 큰 값 | 히알루론산이 2번째면 0.9, 40번째면 0.2 |

**IDF가 필요한 이유**

멀티핫에서 흔한 태그는 상품을 구분하지 못합니다. `Clean at Sephora`는 200개 중 80개(40%)가 갖고 있어 유사도 판단에 도움이 안 되고, `Collagen`은 3개뿐이라 둘 다 가졌다면 실제로 비슷한 제품일 가능성이 높습니다.

```
idf(t) = log(N / (1 + df(t)))        N = 200
```

| 태그 | 보유 상품 | idf 값 |
|---|---:|---:|
| Clean at Sephora | 80 | 0.90 |
| Vegan | 62 | 1.16 |
| Niacinamide | 12 | 2.73 |
| Collagen | 3 | **3.91** |

같은 `1`이어도 `Collagen`이 `Clean at Sephora`보다 **4.3배 무겁게** 계산됩니다.

### `skin_fit`은 콘텐츠 벡터에서 제외되었습니다

피부 타입 적합도는 **추천 점수의 속성 항(`attr_affinity`) 테이블**이 담당합니다. 콘텐츠 벡터에서 제외한 이유는 2-2절에 있습니다. 요약하면:

- 같은 정보가 콘텐츠 벡터와 속성 친화도 테이블에 **중복** 존재했습니다
- 콘텐츠 벡터는 상품당 1개로 고정되므로 **사용자별 분기가 불가능**합니다. 복합성 사용자에게 이 항을 끄는 처리를 할 수 없습니다
- 테이블은 사용자 속성으로 조회하므로 분기가 가능합니다

관련 설계는 [`recommendation-design.md`](../docs/ai/recommendation-design.md) 6장·7-4절 참조.

---

## 1. Feature 후보표

| # | Feature | 담는 내용 | 원본 | 인코딩 | 차원 | 보유율 | 가중치 |
|---:|---|---|---|---|---:|---:|---:|
| 1 | `concern` | 피부 고민 9종 | `highlights` `Good for:` | 멀티핫 + IDF | 9 | 77.5% | **0.42** |
| 2 | `tertiary_category` | 세부 제품 종류 19종 | `tertiary_category` | 원핫 | 19 | 100% | 0.11 |
| 3 | `ingredient` | 핵심 성분 **30종** | `highlights` 태그 + **전성분 파싱** | 멀티핫 + IDF + 위치가중 | **30** | **98.0%** | 0.27 |
| 4 | `secondary_category` | 대분류 8종 | `secondary_category` | 원핫 | 8 | 100% | 0.06 |
| 5 | `clean` | 클린뷰티·성분 배제 16종 | `highlights` | 멀티핫 + IDF | 16 | 85.5% | 0.06 |
| 6 | `price_bin` | 가격대 5구간 | `price_usd` | 원핫 | 5 | 100% | 0.04 |
| 7 | `rating` | 평점 | `rating` | 스칼라 | 1 | 100% | 0.02 |
| 8 | `texture` | 제형·마감 5종 | `highlights` | 멀티핫 + IDF | 5 | 26.0% | 0.02 |
| 9 | `brand` | 브랜드 55종 | `brand_name` | 원핫 | 55 | 100% | **0.60** |

**콘텐츠 벡터 총 148차원**

---

## 2. 필드별 분석 근거

### 2-1. category

| 레벨 | 고유값 | 결측 | 판정 |
|---|---:|---:|---|
| `primary_category` | **1종** | 0 | **제외** |
| `secondary_category` | 8종 | 0 | 채택 |
| `tertiary_category` | 19종 | 0 | 채택 |

`primary_category`는 200개 전부 `Skincare`입니다. 모든 상품이 같은 값이면 유사도에 아무 기여를 하지 못하고 차원만 낭비합니다.

**`secondary_category` 분포 (8종)**

| 값 | 개수 | 비율 |
|---|---:|---:|
| Moisturizers | 62 | 31.0% |
| Treatments | 49 | 24.5% |
| Cleansers | 36 | 18.0% |
| Eye Care | 18 | 9.0% |
| Masks | 14 | 7.0% |
| Lip Balms & Treatments | 10 | 5.0% |
| Sunscreen | 9 | 4.5% |
| Self Tanners | 2 | 1.0% |

**`tertiary_category` 분포 (19종)**

| 값 | 개수 | | 값 | 개수 |
|---|---:|---|---|---:|
| Moisturizers | 48 | | Exfoliators | 6 |
| Face Serums | 42 | | Facial Peels | 5 |
| Face Wash & Cleansers | 18 | | Makeup Removers | 3 |
| Eye Creams & Treatments | 17 | | Mists & Essences | 3 |
| Face Masks | 14 | | BB & CC Creams | 2 |
| Lip Balms & Treatments | 10 | | Blemish & Acne Treatments | 2 |
| Face Sunscreen | 9 | | For Face | 2 |
| Toners | 8 | | Night Creams | 2 |
| Face Oils | 7 | | Face Wipes / Eye Masks | 각 1 |

**두 레벨을 모두 쓰는 이유**

계층 정보를 유지하기 위해서입니다. `Face Serums`와 `Toners`는 tertiary가 다르지만 둘 다 `Treatments`에 속합니다. secondary를 함께 인코딩하면 **같은 대분류 안의 다른 소분류 상품끼리 부분 유사도**가 생깁니다. tertiary만 쓰면 두 상품의 카테고리 유사도가 0이 됩니다.

중복이 있는 만큼 secondary 가중치를 tertiary보다 낮게(0.06 vs 0.11) 둡니다.

> **주의:** `tertiary_category`는 12개 상품에서 원본이 비어 있어 `secondary_category` 값으로 채운 결과입니다. 상세 기준은 `Research/DATA_CLEANING.md`(개인 폴더) 5-2 참조.

### 2-2. highlights

**보유 상품 181/200 (90.5%) · 고유 태그 62종 · 상품당 평균 4.9개**

62종을 성격별로 6개 블록으로 분리했습니다. 하나의 멀티핫으로 묶지 않는 이유는 **블록마다 추천 근거로서의 무게가 다르기** 때문입니다. "지성 피부에 좋다"와 "비건이다"를 같은 가중치로 둘 수 없습니다.

#### concern — 9종 / 보유 155개 (77.5%) / 가중치 0.42

`"Good for: X"` → `X` 추출.

| 값 | 개수 | 비율 |
|---|---:|---:|
| Dullness/Uneven Texture | 68 | 34.0% |
| Dryness | 56 | 28.0% |
| Anti-Aging | 49 | 24.5% |
| Pores | 35 | 17.5% |
| Loss of firmness | 28 | 14.0% |
| Dark Circles | 17 | 8.5% |
| Acne/Blemishes | 13 | 6.5% |
| Redness | 12 | 6.0% |
| Dark spots | 10 | 5.0% |

**가장 높은 가중치를 부여합니다.** 사용자가 실제로 해결하려는 문제와 직결되고, 추천 근거 문구("건조함 개선에 좋은 제품")로 그대로 쓰입니다.

#### skin_fit — **콘텐츠 벡터에서 제외** (속성 친화도 테이블로 이관)

##### 원래 계획과 문제

`highlights`의 `"Best for Dry, Combo, Normal Skin"` 태그로 만들 계획이었으나 **68개 상품(34%)에만 존재**했습니다. 리뷰의 `skin_type` 구성비(lift)로 역산해 보유율 100%를 확보했고, 태그가 있는 68개로 검증했을 때 `dry`(격차 +36%)·`oily`(+38%)에서 태그와 일치했습니다.

미태그 132개에 적용한 결과도 타당했습니다.

| `oily` 적합 상위 | `dry` 적합 상위 |
|---|---|
| Niacinamide 10% + Zinc 1% Oil Control Serum | Cicapair Tiger Grass Color Correcting |
| Salicylic Acid Acne Healing Dots | Hyaluronic Acid 2% + B5 Hydrating Serum |
| AHA 30% + BHA 2% Exfoliating Peeling Solution | The True Cream Moisturizing Bomb |

##### 그런데 콘텐츠 벡터에 두면 안 됩니다

**세 가지 이유로 콘텐츠 벡터에서 제외하고 추천 점수의 속성 항(`attr_affinity`) 테이블로 이관합니다.**

**(1) 정보 중복**
`attr_affinity` 테이블의 `상품 × skin_type` 축과 **같은 값**입니다. 같은 리뷰 데이터를 같은 lift 방식으로 계산했습니다. 두 곳에 두면 이중 계산됩니다.

**(2) 콘텐츠 벡터는 사용자별 분기가 불가능**
콘텐츠 벡터는 상품당 하나로 고정되어 배치에서 미리 생성됩니다. 누가 조회하든 같은 값입니다. 반면 **복합성 사용자에게 이 항을 끄는 처리**가 필요한데(아래 참조), 벡터 안에 박혀 있으면 불가능합니다. 테이블은 사용자 속성으로 조회하므로 분기가 됩니다.

**(3) 사용자 벡터의 의미가 꼬임**
사용자 벡터는 본인이 조회한 상품 벡터들의 가중 평균입니다. `skin_fit`이 포함되면 "이 사용자가 본 상품들의 피부타입 적합도 평균"이라는 값이 생기는데, 이는 사용자 본인의 `skin_type`과 다른 값이라 해석이 어렵습니다.

##### 복합성 문제 — 이관의 결정적 이유

리뷰 458,614건으로 측정한 `skin_type` 세그먼트별 판별력입니다.

| 세그먼트 | 사용자 비중 | lift 표준편차 | lift 범위 |
|---|---:|---:|---|
| `oily` | 12.3% | 0.289 | 0.30 ~ 2.56 |
| `dry` | 19.2% | 0.237 | 0.38 ~ 1.97 |
| `normal` | 13.2% | 0.158 | 0.43 ~ 1.55 |
| **`combination`** | **55.3%** | **0.053** | 0.85 ~ 1.19 |

**복합성은 200개 상품 전부가 0.85~1.19에 갇혀 사실상 상수입니다.** 복합성은 T존 지성 + U존 건성이라 지성용 제품도 건성용 제품도 구매하기 때문입니다. 개념 자체의 특성이며 데이터 결함이 아닙니다.

전체의 55.3%가 복합성이므로 방치하면 사용자 절반에게 이 항이 무력해집니다. **해결은 `skin_type` 가중치를 0으로 두고 `skin_tone`으로 이관하는 것**이며, 이는 테이블에서만 가능합니다.

| 사용자 `skin_type` | `skin_type` | `skin_tone` | `hair_color` | `eye_color` |
|---|---:|---:|---:|---:|
| `dry` / `oily` / `normal` (44.7%) | 0.40 | 0.40 | 0.10 | 0.10 |
| **`combination` (55.3%)** | **0.00** | **0.80** | 0.10 | 0.10 |

복합성 리뷰 253,456건만으로 재계산해도 `skin_tone` lift 표준편차가 0.269(전체 0.262)로 유지됩니다. 복합성/비복합성을 겹치지 않게 나눈 독립 검정에서 톤별 상관이 +0.69~+0.82로, **피부색 신호는 피부 타입과 대체로 독립적**입니다.

##### 감수하는 것

"둘 다 지성용 제품"이라는 콘텐츠 유사도는 사라집니다. 다만 지성용 제품끼리는 `concern`(Pores, Acne/Blemishes)과 `ingredient`(Salicylic Acid, Niacinamide)가 이미 겹치므로 대부분 보존됩니다.

##### 주의 — 이것은 "효능"이 아니라 "구매 성향"

리뷰 구성비는 **누가 이 제품을 샀는가**를 나타냅니다. 지성용으로 마케팅된 제품에 지성 사용자가 몰리는 선택 효과가 포함됩니다. 추천 근거로는 자연스럽지만 **"이 제품이 지성 피부에 효과가 있다"는 의학적 주장으로 사용해서는 안 됩니다.**

상세 설계는 [`recommendation-design.md`](../docs/ai/recommendation-design.md) 6장·7-4절, 테이블은 `batch/ingest/data/affinity_lift.csv` 참조.

#### ingredient — 30종 / 보유 196개 (98.0%) / 가중치 0.27

| 값 | 개수 | | 값 | 개수 |
|---|---:|---|---|---:|
| Hyaluronic Acid | 46 | | SPF | 10 |
| Vitamin C | 19 | | Retinol | 10 |
| AHA/Glycolic Acid | 16 | | Lactic Acid | 7 |
| Salicylic Acid | 16 | | Collagen | 3 |
| Niacinamide | 12 | | | |

**`highlights` 태그만 쓰면 보유율이 55%뿐이어서, 전성분 문자열까지 파싱합니다.**

`highlights`는 세포라 마케팅 태그라 상품마다 있고 없습니다. 반면 `ingredients`(전성분)는 200/200 채워져 있고, 그 안에 성분명이 실제로 들어 있습니다.

```
highlights:  []
ingredients: ["Water, Glycerin, Sodium Hyaluronate, Niacinamide, ..."]
```

동의어 패턴으로 매칭합니다 (`Hyaluronic Acid` ← `hyaluronic acid` / `sodium hyaluronate` / `hyaluronate`). 태그가 붙은 성분의 **91.5%** 를 전성분에서 재발견했고, 태그에 없던 **159건**을 새로 찾았습니다.

**어휘 30종은 데이터로 선별했습니다.** 상위 200개 중 **5~120개 상품 보유** 구간만 채택했습니다. `Vitamin E`는 127개(63.5%)가 보유해 변별력이 없어 제외했고, `Bakuchiol`·`Mandelic Acid`는 각 2개뿐이라 제외했습니다.

**위치 가중이 필수입니다.** 전성분은 함량 순 나열이므로 뒤쪽 성분은 미량입니다.

```
태그로 표시됨        -> 1.0    (브랜드가 핵심이라고 표시)
전성분에서만 발견     -> max(1 - 등장위치/전체성분수, 0.10)
```

Cicapair Tiger Grass Cream(전성분 62개)의 실제 값입니다.

| 성분 | 값 | 해석 |
|---|---:|---|
| Shea Butter | 0.871 | 앞쪽 = 주요 성분 |
| Niacinamide | 0.855 | 앞쪽 |
| Centella (Cica) | 0.661 | 중간. 제품명의 핵심 성분 |
| Adenosine | 0.355 | 뒤쪽 = 미량 |
| Panthenol (B5) | 0.226 | 뒤쪽 = 미량 |

이 처리가 없으면 히알루론산 세럼과 히알루론산이 0.01% 들어간 클렌저가 같은 값을 받습니다.

#### clean — 16종 / 보유 170개 (85.0%) / 가중치 0.05

| 값 | 개수 | | 값 | 개수 |
|---|---:|---|---|---:|
| Clean at Sephora | 80 | | Without Silicones | 12 |
| Vegan | 62 | | Refill Available | 8 |
| Without Parabens | 40 | | Without Phthalates | 7 |
| Cruelty-Free | 40 | | Alcohol Free | 7 |
| Clean + Planet Positive | 27 | | Without Mineral Oil | 5 |
| Fragrance Free | 25 | | Gluten Free | 5 |
| Oil Free | 18 | | Hypoallergenic | 4 |
| Without Sulfates SLS & SLES | 13 | | Without Oxybenzone | 3 |

보유율은 높지만 **변별력이 낮습니다.** `Clean at Sephora`는 40%, `Vegan`은 31%가 갖고 있어 상품을 구분하지 못합니다. IDF 가중으로 흔한 태그를 자동 감쇠시키고, 블록 가중치도 0.05로 낮춥니다.

#### texture — 5종 / 보유 56개 (28.0%) / 가중치 0.02

`Hydrating`(44), `Plumping`(9), `Radiant Finish`(6), `Natural Finish`(4), `High Shine Finish`(3)

빈도 3 미만 태그 10종은 어휘에서 제외했습니다 — `Medium Coverage`, `Customizable`, `Fresh Scent`, `Cream Formula`, `Matte Finish`, `Full Coverage`, `UV Protection`, `Recyclable Packaging`, `Warm &Spicy Scent`, `Black Owned at Sephora`. 1~2개 상품에만 붙은 태그는 어떤 상품과도 유사도를 만들지 못하면서 차원만 늘립니다.

#### popularity — 7종 / 보유 47개 (23.5%) / **콘텐츠 벡터 제외**

`Community Favorite`(34), `allure 2019~2022 Best of Beauty Award Winner`(6/6/4/1/1/1)

**제품의 속성이 아니라 인기 신호입니다.** 콘텐츠 벡터에 넣으면 "인기 있는 것끼리 유사하다"는 의미 없는 축이 생깁니다. 추천 점수의 인기도 항(prior)으로 옮깁니다.

### 2-3. price_usd

```
결측 0 / 범위 $3 ~ $380
p10 $16.90  p25 $33.00  p50 $45.50  p75 $65.25  p90 $89.10
mean $52.44  std $38.52  왜도 3.92
```

**왜도 3.92로 심하게 우편향**입니다. 최고가 $380이 평균을 끌어올려 스칼라로 쓰면 소수 고가 상품이 유사도를 지배합니다.

**5구간 one-hot을 채택합니다.**

| 구간 | 개수 | 비율 |
|---|---:|---:|
| ~$20 | 27 | 13.5% |
| $20-35 | 29 | 14.5% |
| $35-50 | 58 | 29.0% |
| $50-80 | 54 | 27.0% |
| $80+ | 32 | 16.0% |

구간 경계는 실제 분위수(p25 $33, p50 $45.5, p75 $65)를 참고해 **읽기 쉬운 값**으로 조정했습니다. 분포가 13~29%로 고르게 나뉩니다.

가격 민감도는 사용자마다 다르므로 가중치는 0.03으로 낮게 둡니다. 성분이 같아도 가격대가 다르면 다른 상품이라는 정도의 신호입니다.

### 2-4. rating — 채택하되 최소 가중치

```
범위 3.31 ~ 4.83  평균 4.285  표준편차 0.246
변동계수(std/mean) 0.0574
```

**변별력이 매우 낮습니다.** 상위 200개는 이미 인기 상품이라 평점이 4점대에 몰려 있습니다. 변동계수 0.057은 사실상 모든 상품이 같은 값을 갖는다는 뜻입니다.

`product_info.rating`과 리뷰에서 재계산한 평균 평점의 **상관계수가 0.991**이므로 둘 중 하나만 쓰면 됩니다. 원본 컬럼을 사용합니다.

가중치 0.02로 유지하되, **성능 검증 후 제외를 검토**합니다.

### 2-5. loves_count — prior 전용

```
범위 1,237 ~ 1,081,315  중앙값 101,276  왜도 2.78
log1p 적용 후 왜도 -0.82
```

**콘텐츠 벡터에 넣지 않습니다.** 인기도는 상품의 속성이 아니라 시장 반응입니다. 벡터에 넣으면 "인기 있는 것끼리 유사하다"는 축이 생깁니다. 추천 점수의 인기도 항으로 분리합니다.

**log 정규화가 필수입니다.**

| 상품 | loves_count | 선형 정규화 | log 정규화 |
|---|---:|---:|---:|
| LANEIGE 립 슬리핑 마스크 | 1,081,315 | 1.000 | 1.000 |
| The Ordinary 나이아신아마이드 | 763,168 | 0.705 | 0.949 |
| Clinique Smart Clinical Repair | 3,109 | 0.002 | 0.136 |

**선형 정규화 시 200개 중 109개가 0.1 미만**으로 붙어버립니다. log 적용 시 1개뿐입니다.

```
prior(i) = (log1p(loves_count) - log_min) / (log_max - log_min)
```

**상관계수 검증**

| 쌍 | 상관계수 | 해석 |
|---|---:|---|
| loves_count ↔ 고유 리뷰어 수 | 0.691 | 적절히 연동 |
| loves_count ↔ rating | **−0.062** | 무관 — 인기와 만족도는 별개 |
| reviews ↔ 고유 리뷰어 수 | 0.910 | 거의 중복 |

`rating`을 인기도로 쓸 수 없다는 근거입니다. `reviews`는 고유 리뷰어 수와 0.910으로 거의 중복이라 별도 Feature로 쓰지 않습니다.

---

## 3. Encoding 방식

### 3-1. 블록 구조

```
[secondary_category  8] [tertiary_category 19] [concern 9]
[ingredient 30] [clean 16] [texture 5] [price_bin 5] [rating 1]
[brand 55]

총 148차원

brand 는 **맨 뒤**다. 앞에 끼워 넣으면 이미 저장된 사용자 벡터의
차원 의미가 전부 밀려 무효가 된다. 뒤에 붙이면 앞 93차원은 그대로다.
```

### 3-2. IDF 가중

멀티핫 블록(`concern`, `ingredient`, `clean`, `texture`)에 적용합니다.

```
idf(t) = log(N / (1 + df(t)))        N = 200
value(t) = 1.0 * idf(t)              태그 보유 시
```

`Clean at Sephora`(df=80)는 `idf = log(200/81) = 0.90`, `Collagen`(df=3)은 `idf = log(200/4) = 3.91`로 **드문 태그가 4배 이상 강하게** 반영됩니다.

### 3-3. 블록별 L2 정규화 후 가중 결합

**블록마다 차원 수가 달라 그대로 이어붙이면 큰 블록이 유사도를 지배합니다.** `clean`이 16차원, `rating`이 1차원인데 동등하게 취급되면 클린뷰티 태그가 결과를 좌우합니다.

```python
v = []
for block in blocks:
    b = encode(block)                  # one-hot / multi-hot(+IDF)
    if norm(b) > 0:
        b = b / norm(b)                # 블록 내 L2 정규화
    v.append(b * block.weight)         # 블록 가중치
vector = concat(v)
vector = vector / norm(vector)         # 전체 L2 정규화
```

**블록 가중치 합계 = 1.00**

| 블록 | 가중치 | 근거 |
|---|---:|---|
| `concern` | 0.42 | 사용자가 해결하려는 문제와 직결 |
| `tertiary_category` | 0.11 | 가장 정밀한 제품 종류. 카테고리 쏠림 방지를 위해 하향 |
| `ingredient` | 0.27 | 효능 근거. 전성분 파싱으로 보유율 98% |
| `secondary_category` | 0.06 | 계층 상위. tertiary와 중복 있어 낮춤 |
| `clean` | 0.06 | 보유율 높으나 변별력 낮음 |
| `price_bin` | 0.04 | 보조 신호 |
| `rating` | 0.02 | 변동계수 0.057, 최소 유지 |
| `texture` | 0.02 | 보유율 28%, 마케팅 문구 성격 |

`skin_fit` 제외로 확보된 0.15를 8개 블록에 비례 재분배한 뒤, 카테고리 쏠림 측정에 따라 카테고리 두 블록을 하향하고 그만큼을 `concern`·`ingredient`로 이관했습니다 (어휘집 `0.2`).

> 이 가중치는 **초안**입니다. 최종 값은 프론트 담당자가 1차 조정 후 확정합니다.

### 3-4. 결측 처리

| 상황 | 처리 |
|---|---|
| `highlights` 전체 없음 (19개 상품) | `concern`·`clean`·`texture` 3개 블록이 0. `ingredient`는 전성분 파싱으로 채워짐 |
| 블록 하나만 없음 | 해당 블록만 0. 나머지 블록 가중치는 재분배하지 않음 |
| `rating` 결측 | 전체 평균으로 대체 (상위 200개에는 없음) |

**`highlights`가 없는 19개 상품(9.5%)은 4개 블록이 0입니다.** 측정 결과 이 상품들은 추천 후보에서 밀리는 대신 **같은 카테고리 상품과 과도하게 유사해지는** 방향으로 작용합니다 (4-5 참조). 속성 항(`attr_affinity`)은 리뷰 기반이라 영향받지 않습니다.

### 3-5. 어휘집 파일

인코딩에 필요한 어휘·문서빈도·가중치는 [`product-feature-vocab.json`](product-feature-vocab.json)에 정의되어 있습니다. `batch/jobs/product_feature_job.py`가 이 파일을 읽어 인코딩합니다.

```json
{
  "version": "0.1-draft",
  "n_products": 200,
  "min_tag_freq": 3,
  "idf_formula": "log(N / (1 + df))",
  "blocks": [
    { "name": "concern", "encoding": "multi_hot_idf", "block_weight": 0.25,
      "dim": 9, "vocab": [...], "doc_freq": { "Dryness": 56, ... } }
  ],
  "scalars": [...],
  "prior_only": [...],
  "price_bin_edges": [0, 20, 35, 50, 80],
  "total_content_dim": 76
}
```

**어휘집이 바뀌면 벡터 차원이 바뀝니다.** 학습·서빙 양쪽에서 동일한 버전을 써야 하므로 `version` 필드로 관리합니다.

---

## 4. 가중치 검증

블록 가중치가 실제 추천 결과에 어떤 영향을 주는지는 [`cbf-technical-review.md`](../docs/ai/cbf-technical-review.md) 4장에서 페르소나 1,000명으로 측정했습니다. 그 결과에 따라 카테고리 두 블록을 하향하고 어휘집을 `0.2`로 확정했습니다. 여기서는 요약만 둡니다.

### 4-1. 보유율이 100%가 아닌 블록의 영향

**구조적으로 문제 없습니다.** 블록별 L2 정규화 → 가중치 → 전체 L2 정규화 순서이므로, 비어 있는 블록의 몫은 소실되지 않고 **남은 블록에 자동 재분배**됩니다. 벡터 길이는 항상 1입니다.

다만 **기대 기여도**(`가중치 × 보유율`)는 명목 가중치와 다릅니다.

| 블록 | 가중치 | 보유율 | 기대 기여 | 실효 비중 |
|---|---:|---:|---:|---:|
| `concern` | 0.42 | 77.5% | 0.326 | **42.8%** |
| `ingredient` | 0.27 | 98.0% | 0.265 | 27.8% |
| `tertiary_category` | 0.11 | 100.0% | 0.110 | 14.5% |
| `secondary_category` | 0.06 | 100.0% | 0.060 | 7.9% |
| `clean` | 0.06 | 85.0% | 0.051 | 6.7% |
| `price_bin` | 0.04 | 100.0% | 0.040 | 5.3% |
| `rating` | 0.02 | 100.0% | 0.020 | 2.6% |
| `texture` | 0.02 | 26.0% | 0.005 | 0.7% |
| **합계** | 1.00 | | 0.760 | 100% |

카테고리 두 블록의 실효 비중은 **22.4%** 입니다. (명목 17%)

### 4-2. 조정 근거 요약

| 지표 | 조정 전 | 조정 후 |
|---|---:|---:|
| 상위 5개 추천의 카테고리 종류 | 1.90개 | **3.13개** |
| 상위 5개 평균 코사인 (관련성) | 0.614 | **0.632** |
| `concern` 겹침률 | 77.6% | **86.7%** |

다양성을 올렸는데 관련성도 함께 올라갔습니다. 카테고리 원핫이 유사도를 독점하고 있었기 때문입니다.

### 4-3. 부작용 — 구분되지 않는 상품 31개

`concern`과 `ingredient` 가중치가 47% → 69%로 올라간 대가로, **두 블록이 모두 빈 상품 31개(15.5%)** 는 서로 벡터가 거의 같아졌습니다. 코사인 0.99 이상인 쌍이 19쌍 존재합니다.

```
1.0000  The True Cream Aqua Bomb  |  The True Cream Moisturizing Bomb
1.0000  The True Cream Aqua Bomb  |  Greek Yoghurt Nourishing Gel-Cream
```

`ingredients` 원본 문자열에서 성분 키워드를 매칭해 `ingredient` 블록을 채우는 방안이 권고되어 있습니다. 상세는 [`cbf-technical-review.md`](../docs/ai/cbf-technical-review.md) 5장 참조.

### 4-4. `highlights` 결측 상품은 밀리지 않고 뭉칩니다

블록이 적을수록 남은 블록에 집중되어, **같은 카테고리 상품과 과도하게 유사**해집니다. 추천 후보에서 밀리는 것이 아니라 카테고리 내부로 뭉치는 방향으로 작용합니다.


## 5. MySQL 테이블 초안

```sql
CREATE TABLE product_feature (
    product_id      VARCHAR(16)  NOT NULL,
    vocab_version   VARCHAR(16)  NOT NULL,
    vector          JSON         NOT NULL,   -- float[148]
    prior_score     DECIMAL(6,5) NOT NULL,   -- log 정규화 loves_count
    secondary_category VARCHAR(64) NOT NULL, -- 필터·디버깅용 원본 보존
    tertiary_category  VARCHAR(64) NOT NULL,
    price_bin       VARCHAR(8)   NOT NULL,
    rating          DECIMAL(3,2),
    updated_at      DATETIME     NOT NULL,
    PRIMARY KEY (product_id, vocab_version),
    INDEX idx_category (tertiary_category)
);
```

`vocab_version`을 PK에 포함해 어휘집 변경 시 **구버전 벡터와 공존**할 수 있게 합니다. 롤백과 A/B 테스트에 필요합니다.

200개 × 148차원 float32 = **116KB**입니다. `RankingService`가 기동 시 전량 메모리에 적재해도 무방합니다.

---

## 6. 미해결 과제

1. ~~**`highlights` 결측 19개 (9.5%)**~~ — **해결됨.** 두 가지를 적용했습니다.
   - `ingredient` 는 전성분 문자열 파싱으로 보완 (어휘 30종, 위치 기반 감쇠). 보유율 98.0% → 94.0%\*
   - `concern` 은 리뷰 54만건에서 뽑은 상위 2축을 **더합니다**(대체 아님). 보유율 78.0% → 94.0%. 다만 평가 프로토콜을 리뷰 극성 반영으로 고친 뒤에는 +0.39%p (CI [−0.18, +0.97]) 로 **유의하지 않음**

   \* 보유율 수치가 내려간 것은 카탈로그가 바뀌어서이지 기능이 약해진 것이 아닙니다.
   생성 방법은 `batch/jobs/concern_from_reviews.py` 참조.

2. **`attr_affinity`의 `hair_color` / `eye_color`** — lift 기준 판별력이 4개 속성 중 최하위(유의 셀 16.0% / 19.4%)이고, `hair_color`의 유일한 신호는 `gray`가 안티에이징 제품에 몰리는 것으로 **연령 대리변수**로 보입니다. **가중치 0.10 유지로 확정.** 기여가 작아 위험이 제한적이고, 사용자 속성 4개를 모두 반영하는 것이 설계 전제입니다. 로그 축적 후 실제 지표로 재평가합니다.

3. **`rating` 유지 여부** — 변동계수 0.057. 성능 검증 후 제외를 검토합니다.

4. **`secondary` / `tertiary` 중복** — 두 레벨을 모두 인코딩하는 것이 계층 정보 유지에 유리하나, 27차원 중 상당 부분이 중복입니다. tertiary 단독 대비 성능 비교 필요.

5. **`ingredients` TF-IDF 미적용** — 통짜 문자열 분리·정규화가 선행되어야 합니다. V2 과제.

6. **~~블록 가중치 미확정~~** → 어휘집 `0.2`에서 확정. 카테고리 실효 39% → 22.4%, 상위 5개 추천의 카테고리 종류 1.90 → 3.13개. 근거는 [`cbf-technical-review.md`](../docs/ai/cbf-technical-review.md) 4장

---

## 7. 참고

| 문서 | 내용 |
|---|---|
| `Research/DATA_CLEANING.md` | 상품 200개 선정·병합·결측 보완 기준 |
| `Research/PERSONA_SAMPLING.md` | 페르소나 10,000명 층화추출 기준 |
| [`recommendation-design.md`](../docs/ai/recommendation-design.md) | 추천 점수 설계 (이 벡터의 소비처) |

**재현**

```
cd Research
python analyze_product_features.py    # 필드별 분석 수치 출력
python build_feature_vocab.py         # 어휘집 JSON 생성
python encode_products.py             # 인코딩 + 가중치 시나리오별 이웃 쏠림 측정
```
