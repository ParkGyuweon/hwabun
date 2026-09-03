# Product Feature 샘플 — 실제 상품 6개

> 어휘집 `0.5` · 콘텐츠 벡터 148차원
> 원본 데이터: [`batch/ingest/data/feature_sample.json`](../../batch/ingest/data/feature_sample.json) (벡터 전체 값 포함)
> **이 문서는 생성물입니다.** 고칠 일이 있으면 `batch/ingest/build_feature_sample.py` 를 고치고 다시 실행하세요.

명세([`product-feature-spec.md`](../../contracts/product-feature-spec.md))가 실제로 어떤 값을 만들어내는지 확인하기 위한 샘플입니다. 각 속성의 신호를 보여줄 극단 사례와, `brand` 블록을 확인하기 위한 같은 브랜드 형제 하나를 골랐습니다.

| 상품 | 브랜드 | 순위 | 선정 이유 |
|---|---|---:|---|
| Balancing Force Oil Control Toner | OLEHENRIKSEN | 168 | skin_type=oily lift 최고 |
| Cicapair Tiger Grass Cream | Dr. Jart+ | 152 | skin_type=dry lift 최고 |
| Lip Sleeping Mask Intense Hydration with Vitamin C | LANEIGE | 1 | 1위 상품 - loves_count 최고 |
| Greek Yoghurt Foaming Cream Cleanser | KORRES | 12 | skin_tone=deep lift 최고 |
| Smart Clinical Repair Wrinkle Correcting Serum | CLINIQUE | 160 | hair_color=gray lift 최고 |
| Glow2OH Dark Spot Toner | OLEHENRIKSEN | 28 | OLEHENRIKSEN 형제 - brand 블록 확인용 |

---

## 1. 원본 필드

| 상품 | secondary | tertiary | 가격 | 평점 | loves_count | prior |
|---|---|---|---:|---:|---:|---:|
| Balancing Force Oil Control Toner | Cleansers | Toners | $35 | 4.30 | 98,160 | 0.646 |
| Cicapair Tiger Grass Cream | Moisturizers | Moisturizers | $49 | 4.32 | 73,855 | 0.604 |
| Lip Sleeping Mask Intense Hydration wi | Lip Balms & Treatments | Lip Balms & Treatments | $24 | 4.35 | 1,081,315 | 1.000 |
| Greek Yoghurt Foaming Cream Cleanser | Cleansers | Face Wash & Cleansers | $28 | 4.57 | 38,097 | 0.506 |
| Smart Clinical Repair Wrinkle Correcti | Treatments | Face Serums | $71 | 4.19 | 4,293 | 0.184 |
| Glow2OH Dark Spot Toner | Cleansers | Toners | $35 | 4.19 | 182,201 | 0.737 |

`prior` 는 `loves_count` 를 log1p 후 min-max 로 편 값입니다. 개인화 정보가 없는 구간의 안전장치입니다.

## 2. 블록 구성

| 블록 | 차원 | 블록 가중치 |
|---|---:|---:|
| `secondary_category` | 8 | 0.06 |
| `tertiary_category` | 19 | 0.11 |
| `concern` | 9 | 0.42 |
| `ingredient` | 30 | 0.27 |
| `clean` | 16 | 0.06 |
| `texture` | 5 | 0.02 |
| `price_bin` | 5 | 0.04 |
| `brand` | 55 | 0.6 |
| `rating` (스칼라) | 1 | 0.02 |

합계 148차원. **`brand` 가 55차원 · 가중치 0.60 으로 가장 큽니다.** 다음 구매에서 유지되는 속성 중 lift 가 압도적이기 때문입니다(6.08배).

## 3. 인코딩 따라가기 — Balancing Force Oil Control Toner

블록별로 L2 정규화한 뒤 블록 가중치를 곱한 값입니다. 전체 L2 정규화 전 단계이며, 최종 벡터는 산출물의 `벡터` 에 있습니다.

| 블록 | 가중치 | 비영값 |
|---|---:|---|
| `secondary_category` | 0.06 | `Cleansers` 0.06 |
| `tertiary_category` | 0.11 | `Toners` 0.11 |
| `concern` | 0.42 | `Pores` 0.173, `Acne/Blemishes` 0.3692, `Redness` 0.1009 |
| `ingredient` | 0.27 | `Green Tea` 0.0364, `Lactic Acid` 0.1143, `AHA/Glycolic Acid` 0.171, `Salicylic Acid` 0.171 |
| `clean` | 0.06 | `Vegan` 0.035, `Without Parabens` 0.0487 |
| `texture` | 0.02 | (없음) |
| `price_bin` | 0.04 | `35-50` 0.04 |
| `rating` | 0.02 | `rating` 0.02 |
| `brand` | 0.6 | `OLEHENRIKSEN` 0.6 |

성분은 하이라이트 태그와 전성분 문자열에서 뽑아 위치 가중을 줍니다 (전성분 25개 파싱): `AHA/Glycolic Acid` 1.0, `Salicylic Acid` 1.0, `Lactic Acid` 0.8, `Green Tea` 0.28.

## 4. 샘플 간 코사인 — `brand` 블록이 하는 일

| | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| **0** Balancing Force Oil Control To (OLEHENRIKSEN) | 1.000 | 0.061 | 0.005 | 0.165 | 0.001 | 0.687 |
| **1** Cicapair Tiger Grass Cream (Dr. Jart+) | 0.061 | 1.000 | 0.183 | 0.266 | 0.011 | 0.003 |
| **2** Lip Sleeping Mask Intense Hydr (LANEIGE) | 0.005 | 0.183 | 1.000 | 0.102 | 0.022 | 0.004 |
| **3** Greek Yoghurt Foaming Cream Cl (KORRES) | 0.165 | 0.266 | 0.102 | 1.000 | 0.002 | 0.066 |
| **4** Smart Clinical Repair Wrinkle  (CLINIQUE) | 0.001 | 0.011 | 0.022 | 0.002 | 1.000 | 0.051 |
| **5** Glow2OH Dark Spot Toner (OLEHENRIKSEN) | 0.687 | 0.003 | 0.004 | 0.066 | 0.051 | 1.000 |

**OLEHENRIKSEN 형제 두 개(0·5)가 0.687** 입니다. 같은 상품 0 와 다른 브랜드들의 코사인은 0.001~0.165 입니다.

브랜드가 같으면 55차원 원핫이 정확히 겹치고 그 축의 가중치가 0.60 이라, 카테고리나 성분이 달라도 코사인이 크게 올라갑니다. 브랜드 재구매를 잡아내는 힘이 여기서 나오고, 새 브랜드 추천이 어려운 이유도 같습니다 — 원핫이라 시드와 직교하면 그 축의 기여가 0 입니다.

## 5. 행동이 0건인 사용자의 순위

상호작용 상품이 0개인 구간의 가중치입니다 (`w1=0.0` · `w2=0.3` · `w3=0.7`, `batch/jobs/recommender.py` 의 `SCHEDULE`). 코사인 항이 없으므로 **속성 친화도와 인기도만으로** 순위가 정해집니다.

**지성 / light 톤** (`skin_type=oily`, `skin_tone=light`, `hair_color=brown`, `eye_color=brown`)

| 순위 | 상품 | attr_affinity | prior | score |
|---:|---|---:|---:|---:|
| 1 | Lip Sleeping Mask Intense Hydration wi | 0.388 | 1.000 | **0.8165** |
| 2 | Glow2OH Dark Spot Toner | 0.491 | 0.737 | **0.6632** |
| 3 | Balancing Force Oil Control Toner | 0.664 | 0.646 | **0.6511** |
| 4 | Cicapair Tiger Grass Cream | 0.197 | 0.604 | **0.4817** |
| 5 | Greek Yoghurt Foaming Cream Cleanser | 0.255 | 0.506 | **0.4307** |
| 6 | Smart Clinical Repair Wrinkle Correcti | 0.242 | 0.184 | **0.2012** |

**건성 / fair 톤** (`skin_type=dry`, `skin_tone=fair`, `hair_color=blonde`, `eye_color=blue`)

| 순위 | 상품 | attr_affinity | prior | score |
|---:|---|---:|---:|---:|
| 1 | Lip Sleeping Mask Intense Hydration wi | 0.438 | 1.000 | **0.8314** |
| 2 | Cicapair Tiger Grass Cream | 0.797 | 0.604 | **0.6616** |
| 3 | Glow2OH Dark Spot Toner | 0.157 | 0.737 | **0.5631** |
| 4 | Greek Yoghurt Foaming Cream Cleanser | 0.449 | 0.506 | **0.4888** |
| 5 | Balancing Force Oil Control Toner | 0.122 | 0.646 | **0.4885** |
| 6 | Smart Clinical Repair Wrinkle Correcti | 0.471 | 0.184 | **0.2699** |

**복합성 / deep 톤** (`skin_type=combination`, `skin_tone=deep`, `hair_color=black`, `eye_color=brown`)

| 순위 | 상품 | attr_affinity | prior | score |
|---:|---|---:|---:|---:|
| 1 | Lip Sleeping Mask Intense Hydration wi | 0.478 | 1.000 | **0.8436** |
| 2 | Glow2OH Dark Spot Toner | 0.937 | 0.737 | **0.7971** |
| 3 | Balancing Force Oil Control Toner | 0.588 | 0.646 | **0.6285** |
| 4 | Greek Yoghurt Foaming Cream Cleanser | 0.870 | 0.506 | **0.6152** |
| 5 | Cicapair Tiger Grass Cream | 0.054 | 0.604 | **0.4387** |
| 6 | Smart Clinical Repair Wrinkle Correcti | 0.100 | 0.184 | **0.1585** |

복합성 사용자는 `skin_type` 항을 쓰지 않고 그 몫을 `skin_tone` 으로 넘깁니다 (0.00 / 0.80 / 0.10 / 0.10). 200개 상품 전부 lift 0.85~1.19 로 판별력이 없기 때문입니다. 나머지는 0.40 / 0.40 / 0.10 / 0.10 입니다.

## 6. 재생성

```bash
python batch/ingest/build_feature_sample.py
```

산출물과 이 문서가 함께 갱신됩니다. 어휘집이나 가중치 스케줄을 바꾸면 반드시 다시 실행하세요.
