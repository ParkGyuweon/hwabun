# Product Feature 후보표 및 Encoding 초안

> 버전 `0.1-draft` · 2026-08-27
> 대상: 상위 200개 Sephora 스킨케어 상품
> 소비처: `batch/jobs/product_feature_job.py` → MySQL → `backend/recommend/RankingService`
> 어휘집: [`product-feature-vocab.json`](./product-feature-vocab.json)

`category`, `highlights`, `price_usd`, `rating`, `loves_count` 5개 필드를 실측 분석하고 상품 벡터 Encoding 방식을 정의한 초안입니다. 모든 수치는 상위 200개 상품 전수 기준입니다.

---

## 0. 한눈에 보기

**콘텐츠 벡터 72차원 · 블록 가중치 합계 1.00**

| 순 | Feature | 담는 내용 | 원본 | 인코딩 | 차원 | 보유율 | 가중치 |
|---:|---|---|---|---|---:|---:|---:|
| 1 | `concern` | 피부 고민 9종 | `highlights` `Good for:` | 멀티핫 + IDF | 9 | 77.5% | **0.29** |
| 2 | `tertiary_category` | 세부 제품 종류 19종 | `tertiary_category` | 원핫 | 19 | 100% | 0.24 |
| 3 | `ingredient` | 핵심 성분 9종 | `highlights` 성분 태그 | 멀티핫 + IDF | 9 | 55.0% | 0.18 |
| 4 | `secondary_category` | 대분류 8종 | `secondary_category` | 원핫 | 8 | 100% | 0.15 |
| 5 | `clean` | 클린뷰티·성분 배제 16종 | `highlights` | 멀티핫 + IDF | 16 | 85.0% | 0.06 |
| 6 | `price_bin` | 가격대 5구간 | `price_usd` | 원핫 | 5 | 100% | 0.04 |
| 7 | `rating` | 평점 | `rating` | 스칼라 | 1 | 100% | 0.02 |
| 8 | `texture` | 제형·마감 5종 | `highlights` | 멀티핫 + IDF | 5 | 28.0% | 0.02 |

> **주의:** 위 가중치는 명목값입니다. 보유율을 곱한 **실효 비중**에서는 `tertiary_category`(28.9%)가 `concern`(27.1%)을 역전하고, 카테고리 두 블록 합계가 47.0%로 가장 큽니다. 측정 결과 상위 5 이웃의 **91.1%가 같은 세부 카테고리**로 쏠려 있어 가중치 조정이 권고됩니다. 상세는 4장 참조.

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
| `ingredient` | Hyaluronic Acid, Vitamin C, AHA/Glycolic Acid, Salicylic Acid, Niacinamide, SPF, Retinol, Lactic Acid, Collagen |
| `secondary_category` | Moisturizers, Treatments, Cleansers, Eye Care, Masks, Lip Balms & Treatments, Sunscreen, Self Tanners |
| `clean` | Clean at Sephora, Vegan, Without Parabens, Cruelty-Free, Clean + Planet Positive, Fragrance Free, Oil Free, Without Sulfates SLS & SLES, Without Silicones, Refill Available, Without Phthalates, Alcohol Free, Without Mineral Oil, Gluten Free, Hypoallergenic, Without Oxybenzone |
| `price_bin` | ~$20, $20-35, $35-50, $50-80, $80+ |
| `texture` | Hydrating, Plumping, Radiant Finish, Natural Finish, High Shine Finish |

### 인코딩 방식 2가지

| 방식 | 뜻 | 예시 |
|---|---|---|
| **원핫** (one-hot) | 여러 칸 중 **하나만** 1 | 한 상품은 클렌저이거나 수분크림. 둘 다일 수 없음 |
| **멀티핫 + IDF** (multi-hot) | **여러 칸이 동시에** 1. 흔한 값은 약하게 반영 | 비건이면서 파라벤 프리이면서 크루얼티프리일 수 있음 |

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

관련 설계는 `Research/recommendation_design.md` 6장·7-4절 참조.

---

## 1. Feature 후보표

| # | Feature | 담는 내용 | 원본 | 인코딩 | 차원 | 보유율 | 가중치 |
|---:|---|---|---|---|---:|---:|---:|
| 1 | `concern` | 피부 고민 9종 | `highlights` `Good for:` | 멀티핫 + IDF | 9 | 77.5% | **0.29** |
| 2 | `tertiary_category` | 세부 제품 종류 19종 | `tertiary_category` | 원핫 | 19 | 100% | 0.24 |
| 3 | `ingredient` | 핵심 성분 9종 | `highlights` 성분 태그 | 멀티핫 + IDF | 9 | 55.0% | 0.18 |
| 4 | `secondary_category` | 대분류 8종 | `secondary_category` | 원핫 | 8 | 100% | 0.15 |
| 5 | `clean` | 클린뷰티·성분 배제 16종 | `highlights` | 멀티핫 + IDF | 16 | 85.0% | 0.06 |
| 6 | `price_bin` | 가격대 5구간 | `price_usd` | 원핫 | 5 | 100% | 0.04 |
| 7 | `rating` | 평점 | `rating` | 스칼라 | 1 | 100% | 0.02 |
| 8 | `texture` | 제형·마감 5종 | `highlights` | 멀티핫 + IDF | 5 | 28.0% | 0.02 |

**콘텐츠 벡터 총 72차원**

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

중복이 있는 만큼 secondary 가중치를 tertiary보다 낮게(0.13 vs 0.20) 둡니다.

> **주의:** `tertiary_category`는 12개 상품에서 원본이 비어 있어 `secondary_category` 값으로 채운 결과입니다. 상세 기준은 `Research/DATA_CLEANING.md` 5-2 참조.

### 2-2. highlights

**보유 상품 181/200 (90.5%) · 고유 태그 62종 · 상품당 평균 4.9개**

62종을 성격별로 6개 블록으로 분리했습니다. 하나의 멀티핫으로 묶지 않는 이유는 **블록마다 추천 근거로서의 무게가 다르기** 때문입니다. "지성 피부에 좋다"와 "비건이다"를 같은 가중치로 둘 수 없습니다.

#### concern — 9종 / 보유 155개 (77.5%) / 가중치 0.25

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

상세 설계는 `Research/recommendation_design.md` 6장·7-4절, 테이블은 `Research/artifacts/affinity_lift.csv` 참조.

#### ingredient — 9종 / 보유 110개 (55.0%) / 가중치 0.15

| 값 | 개수 | | 값 | 개수 |
|---|---:|---|---|---:|
| Hyaluronic Acid | 46 | | SPF | 10 |
| Vitamin C | 19 | | Retinol | 10 |
| AHA/Glycolic Acid | 16 | | Lactic Acid | 7 |
| Salicylic Acid | 16 | | Collagen | 3 |
| Niacinamide | 12 | | | |

**`ingredients` 원본 컬럼의 TF-IDF는 이번 초안에서 제외합니다.** 원본이 성분 배열이 아니라 전 성분을 쉼표로 이어붙인 1,000자 내외 통짜 문자열이라, 분리·정규화 품질이 결과를 좌우하고 차원이 수천 개로 증가합니다. `highlights`의 성분 태그 9종만으로 **주요 활성 성분은 이미 커버**됩니다.

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
[ingredient 9] [clean 16] [texture 5] [price_bin 5] [rating 1]

총 72차원
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
| `concern` | 0.29 | 사용자가 해결하려는 문제와 직결 |
| `tertiary_category` | 0.24 | 가장 정밀한 제품 종류 |
| `ingredient` | 0.18 | 효능 근거. 성분 기반 설명 가능 |
| `secondary_category` | 0.15 | 계층 상위. tertiary와 중복 있어 낮춤 |
| `clean` | 0.06 | 보유율 높으나 변별력 낮음 |
| `price_bin` | 0.04 | 보조 신호 |
| `rating` | 0.02 | 변동계수 0.057, 최소 유지 |
| `texture` | 0.02 | 보유율 28%, 마케팅 문구 성격 |

`skin_fit` 제외로 확보된 0.15는 위 8개 블록에 비례 재분배했습니다.

> 이 가중치는 **초안**입니다. 최종 값은 프론트 담당자가 1차 조정 후 확정합니다.

### 3-4. 결측 처리

| 상황 | 처리 |
|---|---|
| `highlights` 전체 없음 (19개 상품) | `concern`·`ingredient`·`clean`·`texture` 4개 블록이 0 |
| 블록 하나만 없음 | 해당 블록만 0. 나머지 블록 가중치는 재분배하지 않음 |
| `rating` 결측 | 전체 평균으로 대체 (상위 200개에는 없음) |

**`highlights`가 없는 19개 상품(9.5%)은 4개 블록이 0입니다.** 측정 결과 이 상품들은 추천 후보에서 밀리는 대신 **같은 카테고리 상품과 과도하게 유사해지는** 방향으로 작용합니다 (4-5 참조). 속성 항(`attr_affinity`)은 리뷰 기반이라 영향받지 않습니다.

### 3-5. 어휘집 파일

인코딩에 필요한 어휘·문서빈도·가중치는 [`product-feature-vocab.json`](./product-feature-vocab.json)에 정의되어 있습니다. `batch/jobs/product_feature_job.py`가 이 파일을 읽어 인코딩합니다.

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

## 4. 가중치 검증 — 이웃 쏠림 측정

블록 가중치가 실제 추천 결과에 어떤 영향을 주는지 인코더를 구현해 측정했습니다. (`Research/encode_products.py`)

### 4-1. 보유율이 100%가 아닌 블록의 실제 영향

**결론: 구조적으로 문제 없습니다.** 블록별 L2 정규화 → 가중치 → 전체 L2 정규화 순서이므로, 비어 있는 블록의 몫은 소실되지 않고 **남은 블록에 자동 재분배**됩니다. `concern`이 없는 상품은 카테고리·성분·가격 성분이 그만큼 커지고, 벡터 길이는 여전히 1입니다.

다만 **기대 기여도**(`가중치 × 보유율`)로 보면 명목 가중치와 순위가 달라집니다.

| 블록 | 가중치 | 보유율 | 기대 기여 | 실효 비중 |
|---|---:|---:|---:|---:|
| `tertiary_category` | 0.24 | 100% | 0.240 | **28.9%** |
| `concern` | 0.29 | 77.5% | 0.225 | 27.1% |
| `secondary_category` | 0.15 | 100% | 0.150 | 18.1% |
| `ingredient` | 0.18 | 55.0% | 0.099 | 11.9% |
| `clean` | 0.06 | 85.0% | 0.051 | 6.1% |
| `price_bin` | 0.04 | 100% | 0.040 | 4.8% |
| `rating` | 0.02 | 100% | 0.020 | 2.4% |
| `texture` | 0.02 | 26.0% | 0.005 | 0.6% |
| **합계** | 1.00 | | 0.830 | 100% |

명목상 1위인 `concern`이 실효 비중에서는 `tertiary_category`에 역전됩니다. **카테고리 두 블록 합계가 47.0%** 로 가장 큽니다.

### 4-2. 상위 5 이웃의 카테고리 쏠림

각 상품의 코사인 유사도 상위 5개가 같은 카테고리인지 측정했습니다.

| 시나리오 | 같은 `tertiary` | 같은 `secondary` | 이웃 5개의 카테고리 종류 |
|---|---:|---:|---:|
| 카테고리 상향 | 93.5% | 99.2% | 1.16개 |
| **현재안** | **91.1%** | **97.2%** | **1.28개** |
| 중간안 A | 71.7% | 79.9% | 2.03개 |
| 중간안 B | 58.1% | 66.6% | 2.50개 |
| 카테고리 최소 | 44.9% | 53.9% | 2.89개 |

**현재안에서 이미 이웃의 91.1%가 같은 세부 카테고리입니다.** 이웃 5개의 카테고리 종류가 1.28개이므로 사실상 "같은 카테고리 상품 목록"에 가깝습니다.

```
LANEIGE 립 슬리핑 마스크의 이웃 4개
  0.900  Brazilian Kiss Cupuaçu Lip Butter  (Lip Balms & Treatments)
  0.896  The Kissu Lip Mask                 (Lip Balms & Treatments)
  0.896  Lip Butter Balm                    (Lip Balms & Treatments)
  0.896  Lip Glowy Balm                     (Lip Balms & Treatments)
```

### 4-3. 카테고리 가중치를 올려서는 안 되는 이유

보유율 100%라는 이유로 카테고리 가중치를 올리면 같은 카테고리 비율이 **93.5%** 가 되어, 추천이 **카테고리 필터로 퇴화**합니다. 클렌저를 보던 사용자에게 클렌저만 5개 제시하는 것은 추천의 가치가 없습니다.

카테고리를 넘나드는 추천을 만드는 블록이 `concern`입니다. "건조함 개선"으로 묶이면 세럼·크림·마스크가 함께 후보에 오릅니다. 이 블록을 낮추면 그 능력이 사라집니다.

### 4-4. 권고안 — 중간안 A

```
tertiary_category 0.19   secondary_category 0.11
concern 0.33   ingredient 0.21
(clean 0.06 / price_bin 0.04 / rating 0.02 / texture 0.02 유지)
```

같은 카테고리 비율 71.7%, 이웃 카테고리 종류 2.03개. 화장품 추천에 필요한 카테고리 일관성은 유지하면서 교차 추천 여지를 확보합니다.

> **어휘집(`product-feature-vocab.json`)의 현재 값은 "현재안"입니다.** 중간안 A로의 변경은 가중치 결정 권한이 있는 담당자 확정 후 반영합니다. (미해결 과제 6번)

### 4-5. `highlights` 결측 상품은 밀리지 않고 뭉칩니다

| 그룹 | 최고 유사도 평균 |
|---|---:|
| `highlights` 결측 19개 | **0.922** |
| `highlights` 보유 181개 | 0.864 |

블록이 적을수록 남은 카테고리 블록에 집중되어, **같은 카테고리 상품과 과도하게 유사**해집니다. 추천 후보에서 밀리는 것이 아니라 카테고리 내부로 뭉치는 방향으로 작용합니다.

---

## 5. MySQL 테이블 초안

```sql
CREATE TABLE product_feature (
    product_id      VARCHAR(16)  NOT NULL,
    vocab_version   VARCHAR(16)  NOT NULL,
    vector          JSON         NOT NULL,   -- float[72]
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

200개 × 72차원 float32 = **58KB**입니다. `RankingService`가 기동 시 전량 메모리에 적재해도 무방합니다.

---

## 6. 미해결 과제

1. **`highlights` 결측 19개 (9.5%)** — `concern`·`ingredient`·`clean` 블록이 비어 카테고리·가격·`skin_fit`만으로 벡터가 구성됩니다. 그 결과 같은 카테고리 상품과 유사도가 과도하게 높아집니다(최고 유사도 평균 0.922 vs 0.864). `ingredients` 원본 문자열에서 `Hyaluronic Acid`, `Niacinamide` 등 키워드를 매칭해 `ingredient` 블록을 보완하는 방안이 있습니다. 미적용.

2. **`attr_affinity`의 `hair_color` / `eye_color`** — lift 기준 판별력이 4개 속성 중 최하위(유의 셀 16.1% / 19.8%)이고, `hair_color`의 유일한 신호는 `gray`가 안티에이징 제품에 몰리는 것으로 **연령 대리변수**로 보입니다. 가중치 0.10씩 유지할지 제외할지 결정 필요.

3. **`rating` 유지 여부** — 변동계수 0.057. 성능 검증 후 제외를 검토합니다.

4. **`secondary` / `tertiary` 중복** — 두 레벨을 모두 인코딩하는 것이 계층 정보 유지에 유리하나, 27차원 중 상당 부분이 중복입니다. tertiary 단독 대비 성능 비교 필요.

5. **`ingredients` TF-IDF 미적용** — 통짜 문자열 분리·정규화가 선행되어야 합니다. V2 과제.

6. **블록 가중치 미확정** — 어휘집의 현재 값은 "현재안"이며, 측정 결과 같은 카테고리 이웃 비율이 91.1%로 과도합니다. **중간안 A(71.7%)로의 변경을 권고**하나, 가중치 결정 권한이 있는 담당자 확정을 대기합니다. 근거는 4장 참조.

---

## 7. 참고

| 문서 | 내용 |
|---|---|
| `Research/DATA_CLEANING.md` | 상품 200개 선정·병합·결측 보완 기준 |
| `Research/PERSONA_SAMPLING.md` | 페르소나 10,000명 층화추출 기준 |
| `Research/recommendation_design.md` | 추천 점수 설계 (이 벡터의 소비처) |

**재현**

```
cd Research
python analyze_product_features.py    # 필드별 분석 수치 출력
python build_feature_vocab.py         # 어휘집 JSON 생성
python encode_products.py             # 인코딩 + 가중치 시나리오별 이웃 쏠림 측정
```
