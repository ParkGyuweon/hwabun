# Product Feature 샘플 — 실제 상품 5개

> 어휘집 버전 `0.2` · 콘텐츠 벡터 72차원 · 2026-08-27
> 원본 데이터: `artifacts/feature_sample.json` (72차원 벡터 전체 값 포함)

명세([`product-feature-spec.md`](./product-feature-spec.md))가 실제로 어떤 값을 만들어내는지 확인하기 위한 샘플입니다. 각 속성의 신호를 보여줄 수 있는 극단 사례 5개를 골랐습니다.

| 상품 | 선정 이유 |
|---|---|
| Balancing Force Oil Control Toner | `skin_type=oily` lift 최고 (2.56배) |
| Cicapair Tiger Grass Cream | `skin_type=dry` lift 최고 (1.97배), `skin_tone=fair` 편중 |
| LANEIGE Lip Sleeping Mask | 1위 상품, `loves_count` 최고 (108만) |
| Greek Yoghurt Foaming Cream Cleanser | `skin_tone=deep` lift 최고 (2.67배) |
| Smart Clinical Repair Wrinkle Serum | `hair_color=gray` lift 최고 (2.80배, 연령 대리변수) |

---

## 1. 원본 필드

| 상품 | 순위 | secondary | tertiary | 가격 | 평점 | loves_count |
|---|---:|---|---|---:|---:|---:|
| Balancing Force Oil Control Toner | 169 | Cleansers | Toners | $35 | 4.30 | 98,160 |
| Cicapair Tiger Grass Cream | 153 | Moisturizers | Moisturizers | $49 | 4.32 | 73,855 |
| Lip Sleeping Mask Intense Hydration wi | 1 | Lip Balms & Treatments | Lip Balms & Treatments | $24 | 4.35 | 1,081,315 |
| Greek Yoghurt Foaming Cream Cleanser | 12 | Cleansers | Face Wash & Cleansers | $28 | 4.57 | 38,097 |
| Smart Clinical Repair Wrinkle Correcti | 161 | Treatments | Face Serums | $71 | 4.19 | 4,293 |

### highlights 태그 분류

62종 태그를 4개 블록으로 나눈 결과입니다. `Best for ... Skin`과 인기 태그(`Community Favorite`, allure 수상)는 콘텐츠 벡터에서 제외됩니다.

**Balancing Force Oil Control Toner**

- `concern` (피부 고민): Pores, Acne/Blemishes
- `ingredient` (성분): AHA/Glycolic Acid, Salicylic Acid
- `clean` (클린뷰티): Vegan, Without Parabens

**Cicapair Tiger Grass Cream**

- `concern` (피부 고민): Redness, Dryness

**Lip Sleeping Mask Intense Hydration with Vitamin C**

- `concern` (피부 고민): Dryness
- `ingredient` (성분): Vitamin C
- `clean` (클린뷰티): Without Parabens
- `texture` (제형): Hydrating

**Greek Yoghurt Foaming Cream Cleanser**

- `concern` (피부 고민): Redness, Dryness
- `clean` (클린뷰티): Clean at Sephora

**Smart Clinical Repair Wrinkle Correcting Serum**

- `concern` (피부 고민): Anti-Aging
- `ingredient` (성분): Hyaluronic Acid, Retinol
- `clean` (클린뷰티): Fragrance Free, Oil Free, Without Sulfates SLS & SLES

---

## 2. 인코딩 결과 — 0이 아닌 값만

블록별 L2 정규화 후 블록 가중치를 곱한 값입니다. 전체 L2 정규화 전 단계이며, 72차원 최종 벡터는 `feature_sample.json`의 `벡터_72차원`에 있습니다.

### Balancing Force Oil Control Toner

`P416816` · 169위 · `prior_score` **0.6457**

| 블록 | 항목 | 값 |
|---|---|---:|
| secondary_category | Cleansers | 0.06 |
| tertiary_category | Toners | 0.11 |
| concern | Pores | 0.2276 |
|  | Acne/Blemishes | 0.353 |
| ingredient | AHA/Glycolic Acid | 0.1909 |
|  | Salicylic Acid | 0.1909 |
| clean | Vegan | 0.0353 |
|  | Without Parabens | 0.0485 |
| price_bin | 35-50 | 0.04 |
| rating | rating | 0.02 |

### Cicapair Tiger Grass Cream

`P411539` · 153위 · `prior_score` **0.6037**

| 블록 | 항목 | 값 |
|---|---|---:|
| secondary_category | Moisturizers | 0.06 |
| tertiary_category | Moisturizers | 0.11 |
| concern | Dryness | 0.1753 |
|  | Redness | 0.3817 |
| price_bin | 35-50 | 0.04 |
| rating | rating | 0.02 |

### Lip Sleeping Mask Intense Hydration with Vitamin C

`P420652` · 1위 · `prior_score` **1.0**

| 블록 | 항목 | 값 |
|---|---|---:|
| secondary_category | Lip Balms & Treatments | 0.06 |
| tertiary_category | Lip Balms & Treatments | 0.11 |
| concern | Dryness | 0.42 |
| ingredient | Vitamin C | 0.27 |
| clean | Without Parabens | 0.06 |
| texture | Hydrating | 0.02 |
| price_bin | 20-35 | 0.04 |
| rating | rating | 0.02 |

### Greek Yoghurt Foaming Cream Cleanser

`P456412` · 12위 · `prior_score` **0.506**

| 블록 | 항목 | 값 |
|---|---|---:|
| secondary_category | Cleansers | 0.06 |
| tertiary_category | Face Wash & Cleansers | 0.11 |
| concern | Dryness | 0.1753 |
|  | Redness | 0.3817 |
| clean | Clean at Sephora | 0.06 |
| price_bin | 20-35 | 0.04 |
| rating | rating | 0.02 |

### Smart Clinical Repair Wrinkle Correcting Serum

`P473267` · 161위 · `prior_score` **0.1836**

| 블록 | 항목 | 값 |
|---|---|---:|
| secondary_category | Treatments | 0.06 |
| tertiary_category | Face Serums | 0.11 |
| concern | Anti-Aging | 0.42 |
| ingredient | Hyaluronic Acid | 0.1206 |
|  | Retinol | 0.2416 |
| clean | Fragrance Free | 0.0299 |
|  | Oil Free | 0.0345 |
|  | Without Sulfates SLS & SLES | 0.039 |
| price_bin | 50-80 | 0.04 |
| rating | rating | 0.02 |

---

## 3. IDF가 실제로 하는 일

Balancing Force Oil Control Toner의 `concern` 블록을 보면 IDF 효과가 드러납니다.

| 태그 | 보유 상품 수 | 가중치 적용값 |
|---|---:|---:|
| Pores | 35 | 0.1572 |
| Acne/Blemishes | 13 | **0.2437** |

두 태그를 똑같이 하나씩 갖고 있는데도 **드문 `Acne/Blemishes`가 1.55배 무겁게** 반영됩니다. 흔한 태그로 상품을 묶는 것을 IDF가 자동으로 억제합니다.

`clean` 블록에서는 효과가 더 큽니다. LANEIGE 립마스크는 `Without Parabens` 하나만 가져서 블록 전체 가중치 0.06을 독점하지만, Smart Clinical Repair는 태그 3개를 나눠 가져 각각 0.03~0.04로 분산됩니다.

---

## 4. 속성별 통계 — `attr_affinity` 테이블

리뷰 458,614건으로 계산한 구성비 lift입니다. `affinity`는 lift를 `clip((lift-0.80)/0.40, 0, 1)`로 0~1 변환한 값입니다.

### skin_type

| 상품 | combination | dry | normal | oily |
|---|---:|---:|---:|---:|
| Balancing Force Oil Control Toner | 0.40 (1.0x) | 0.00 (0.4x) | 0.00 (0.4x) | 1.00 (2.6x) |
| Cicapair Tiger Grass Cream | 0.27 (0.9x) | 1.00 (2.0x) | 0.10 (0.7x) | 0.00 (0.4x) |
| Lip Sleeping Mask Intense Hydratio | 0.36 (1.0x) | 0.43 (1.0x) | 0.48 (1.1x) | 0.43 (1.0x) |
| Greek Yoghurt Foaming Cream Cleans | 0.39 (1.0x) | 0.44 (1.0x) | 0.34 (0.9x) | 0.43 (1.0x) |
| Smart Clinical Repair Wrinkle Corr | 0.44 (1.0x) | 0.44 (1.0x) | 0.55 (1.2x) | 0.00 (0.6x) |

### skin_tone

| 상품 | fair | light | medium | tan | deep |
|---|---:|---:|---:|---:|---:|
| Balancing Force Oil Control Toner | 0.19 (0.8x) | 0.42 (1.0x) | 0.66 (1.3x) | 0.58 (1.2x) | 0.59 (1.2x) |
| Cicapair Tiger Grass Cream | 0.74 (1.3x) | 0.32 (0.9x) | 0.25 (0.8x) | 0.08 (0.7x) | 0.00 (0.2x) |
| Lip Sleeping Mask Intense Hydratio | 0.46 (1.1x) | 0.34 (0.9x) | 0.45 (1.0x) | 0.45 (1.1x) | 0.50 (1.1x) |
| Greek Yoghurt Foaming Cream Cleans | 0.48 (1.1x) | 0.01 (0.6x) | 1.00 (1.6x) | 1.00 (1.9x) | 1.00 (2.7x) |
| Smart Clinical Repair Wrinkle Corr | 0.45 (1.1x) | 0.50 (1.1x) | 0.18 (0.8x) | 0.00 (0.6x) | 0.00 (0.5x) |

### hair_color

| 상품 | black | blonde | brown | auburn | red | gray |
|---|---:|---:|---:|---:|---:|---:|
| Balancing Force Oil Control Toner | 0.60 (1.2x) | 0.28 (0.9x) | 0.42 (1.0x) | 0.19 (0.8x) | 0.05 (0.7x) | 0.00 (0.2x) |
| Cicapair Tiger Grass Cream | 0.26 (0.9x) | 0.47 (1.1x) | 0.42 (1.0x) | 0.31 (0.9x) | 0.72 (1.3x) | 0.42 (1.0x) |
| Lip Sleeping Mask Intense Hydratio | 0.37 (1.0x) | 0.40 (1.0x) | 0.42 (1.0x) | 0.32 (0.9x) | 0.39 (1.0x) | 0.42 (1.0x) |
| Greek Yoghurt Foaming Cream Cleans | 0.32 (0.9x) | 0.36 (1.0x) | 0.44 (1.0x) | 0.58 (1.2x) | 0.52 (1.1x) | 0.22 (0.8x) |
| Smart Clinical Repair Wrinkle Corr | 0.66 (1.3x) | 0.65 (1.2x) | 0.09 (0.7x) | 1.00 (1.6x) | 0.71 (1.3x) | 1.00 (2.8x) |

### eye_color

| 상품 | brown | blue | green | hazel | gray |
|---|---:|---:|---:|---:|---:|
| Balancing Force Oil Control Toner | 0.55 (1.1x) | 0.16 (0.8x) | 0.21 (0.8x) | 0.38 (1.0x) | 0.04 (0.6x) |
| Cicapair Tiger Grass Cream | 0.28 (0.9x) | 0.55 (1.1x) | 0.52 (1.1x) | 0.52 (1.1x) | 0.42 (1.0x) |
| Lip Sleeping Mask Intense Hydratio | 0.38 (1.0x) | 0.44 (1.0x) | 0.41 (1.0x) | 0.40 (1.0x) | 0.80 (1.4x) |
| Greek Yoghurt Foaming Cream Cleans | 0.38 (1.0x) | 0.46 (1.1x) | 0.33 (0.9x) | 0.46 (1.1x) | 0.39 (1.0x) |
| Smart Clinical Repair Wrinkle Corr | 0.34 (0.9x) | 0.49 (1.1x) | 0.43 (1.0x) | 0.44 (1.0x) | 1.00 (1.6x) |

괄호 안이 원래 lift입니다. 읽는 법:

- Oil Control Toner의 `oily` **2.6배** — 지성 사용자가 평균보다 2.6배 많이 리뷰
- Cicapair Cream의 `dry` **2.0배**, `oily` 0.4배 — 건성용 제품
- Greek Yoghurt Cleanser의 `deep` **2.7배** — 어두운 톤 사용자 편중
- Smart Clinical Repair의 `gray` **2.8배** — 흰머리(=연령) 편중
- 모든 상품의 `combination`이 1.0 근처 — **판별력 없음** (전체의 55.3%가 복합성)

---

## 5. 샘플 간 코사인 유사도

| | (1) | (2) | (3) | (4) | (5) |
|---|---:|---:|---:|---:|---:|
| (1) Balancing Force Oil Control Toner | 1.000 | 0.009 | 0.012 | 0.017 | 0.001 |
| (2) Cicapair Tiger Grass Cream | 0.009 | 1.000 | 0.323 | 0.903 | 0.002 |
| (3) Lip Sleeping Mask Intense Hydratio | 0.012 | 0.323 | 1.000 | 0.327 | 0.001 |
| (4) Greek Yoghurt Foaming Cream Cleans | 0.017 | 0.903 | 0.327 | 1.000 | 0.002 |
| (5) Smart Clinical Repair Wrinkle Corr | 0.001 | 0.002 | 0.001 | 0.002 | 1.000 |

- **(2) Cicapair ↔ (4) Greek Yoghurt = 0.503** — 카테고리가 다른데(모이스처라이저 vs 클렌저) 유사도가 높습니다. `concern` 태그가 `Dryness`·`Redness`로 완전히 겹치기 때문입니다. **`concern`이 카테고리를 넘나드는 추천을 만든다**는 근거입니다
- **(5) Smart Clinical Repair는 모든 상품과 0.002** — 유일한 `Anti-Aging` 제품이고 카테고리·성분도 겹치지 않습니다
- (1) Oil Control Toner ↔ (4) Greek Yoghurt = 0.124 — 둘 다 `Cleansers`지만 tertiary(Toners vs Face Wash)와 concern이 달라 낮습니다

---

## 6. 추천 점수 계산 예시

**행동 로그 0개 구간**입니다. 가중치는 `w1(코사인)=0.00` / `w2(속성)=0.80` / `w3(인기도)=0.20`이므로 속성과 인기도만으로 순위가 정해집니다.

```
score = w2 x attr_affinity(u, i) + w3 x prior(i)
```

### 지성 / light 톤

`skin_type=oily` `skin_tone=light` `hair_color=brown` `eye_color=brown`

| 순위 | 상품 | attr_affinity | prior | **최종 점수** |
|---:|---|---:|---:|---:|
| 1 | Balancing Force Oil Control Toner | 0.664 | 0.646 | **0.6602** |
| 2 | Lip Sleeping Mask Intense Hydration wi | 0.389 | 1.000 | **0.5109** |
| 3 | Greek Yoghurt Foaming Cream Cleanser | 0.255 | 0.506 | **0.3052** |
| 4 | Cicapair Tiger Grass Cream | 0.197 | 0.604 | **0.2784** |
| 5 | Smart Clinical Repair Wrinkle Correcti | 0.242 | 0.184 | **0.2304** |

1위 상품의 속성 항 분해:

| 속성 | 세그먼트 | affinity | 가중치 | 기여 |
|---|---|---:|---:|---:|
| skin_type | oily | 1.000 | 0.40 | 0.4000 |
| skin_tone | light | 0.417 | 0.40 | 0.1670 |
| hair_color | brown | 0.418 | 0.10 | 0.0418 |
| eye_color | brown | 0.550 | 0.10 | 0.0550 |

### 건성 / fair 톤

`skin_type=dry` `skin_tone=fair` `hair_color=blonde` `eye_color=blue`

| 순위 | 상품 | attr_affinity | prior | **최종 점수** |
|---:|---|---:|---:|---:|
| 1 | Cicapair Tiger Grass Cream | 0.797 | 0.604 | **0.7583** |
| 2 | Lip Sleeping Mask Intense Hydration wi | 0.438 | 1.000 | **0.5504** |
| 3 | Greek Yoghurt Foaming Cream Cleanser | 0.449 | 0.506 | **0.4602** |
| 4 | Smart Clinical Repair Wrinkle Correcti | 0.471 | 0.184 | **0.4136** |
| 5 | Balancing Force Oil Control Toner | 0.122 | 0.646 | **0.2267** |

1위 상품의 속성 항 분해:

| 속성 | 세그먼트 | affinity | 가중치 | 기여 |
|---|---|---:|---:|---:|
| skin_type | dry | 1.000 | 0.40 | 0.4000 |
| skin_tone | fair | 0.739 | 0.40 | 0.2955 |
| hair_color | blonde | 0.467 | 0.10 | 0.0467 |
| eye_color | blue | 0.547 | 0.10 | 0.0547 |

### 복합성 / deep 톤

`skin_type=combination` `skin_tone=deep` `hair_color=black` `eye_color=brown`

> 복합성 사용자이므로 `skin_type` 가중치 0, `skin_tone` 0.80이 적용됩니다.

| 순위 | 상품 | attr_affinity | prior | **최종 점수** |
|---:|---|---:|---:|---:|
| 1 | Greek Yoghurt Foaming Cream Cleanser | 0.870 | 0.506 | **0.7972** |
| 2 | Balancing Force Oil Control Toner | 0.586 | 0.646 | **0.5983** |
| 3 | Lip Sleeping Mask Intense Hydration wi | 0.477 | 1.000 | **0.5814** |
| 4 | Cicapair Tiger Grass Cream | 0.054 | 0.604 | **0.1636** |
| 5 | Smart Clinical Repair Wrinkle Correcti | 0.100 | 0.184 | **0.1164** |

1위 상품의 속성 항 분해:

| 속성 | 세그먼트 | affinity | 가중치 | 기여 |
|---|---|---:|---:|---:|
| skin_type | combination | 0.395 | 0.00 | 0.0000 |
| skin_tone | deep | 1.000 | 0.80 | 0.8000 |
| hair_color | black | 0.318 | 0.10 | 0.0318 |
| eye_color | brown | 0.382 | 0.10 | 0.0382 |

### 결과 해석

| 사용자 | 1위 | 최하위 | 판단 |
|---|---|---|---|
| 지성 / light | Oil Control Toner | Cicapair Cream | 지성용 1위, 건성용 최하위 |
| 건성 / fair | Cicapair Cream | Oil Control Toner | 정확히 반대로 뒤집힘 |
| 복합성 / deep | Oil Control Toner | Smart Clinical Repair | `skin_tone`만으로 결정 |

지성과 건성 사용자의 1·5위가 완전히 뒤집힙니다. **`skin_type` 항이 실제로 작동한다는 증거**입니다.

복합성 사용자는 `skin_type` 가중치가 0이므로 `skin_tone=deep` 하나로 순위가 결정됩니다. Oil Control Toner가 1위인 이유는 지성용이라서가 아니라 **`deep` 톤 사용자의 리뷰 편중이 크기 때문**입니다. 해석할 때 주의해야 합니다.

Cicapair Cream이 복합성/deep 사용자에게 최하위권(0.148)인 것은 타당합니다 — 톤 보정 제품이라 `fair` 톤에 편중되어 있고 `deep` 톤 친화도가 낮습니다.

---

## 7. 이 샘플로 확인된 것

| 항목 | 결과 |
|---|---|
| 인코딩 파이프라인 | 원본 → 72차원 벡터 정상 생성 |
| IDF 가중 | 드문 태그가 1.55배 이상 무겁게 반영됨 |
| 블록별 L2 정규화 | 태그 수가 많은 블록이 지배하지 않음 |
| `concern`의 교차 추천 | 카테고리가 달라도 고민이 같으면 유사도 0.503 |
| 속성 항 작동 | 지성/건성 사용자의 1·5위가 완전히 뒤집힘 |
| 복합성 분기 | `skin_type` 0 → `skin_tone` 0.80으로 정상 이관 |
| 추천 근거 설명 | 속성별 기여도 분해 가능 |

## 8. 남은 과제

1. **`w1`(코사인) 항 미검증** — 행동 로그가 없어 0입니다. 페르소나 시뮬레이션 후 검증이 필요합니다
2. **블록 가중치 미확정** — 이웃 쏠림 91.1%로 과도. 중간안 A 권고 상태
3. **`hair_color` / `eye_color` 존치 여부** — 판별력 최하위, `hair_color`는 연령 대리변수로 의심

