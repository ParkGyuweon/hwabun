# 추천 입출력 데이터 구조

> 2026-08-27 (최종 갱신 2026-08-31) · 어휘집 버전 `0.4` (148차원)
> 관련: [`recommendation-design.md`](../docs/ai/recommendation-design.md) (계산 설계) · [`product-feature-spec.md`](product-feature-spec.md) (상품 벡터 명세) · [`product-feature-sample.md`](../docs/ai/product-feature-sample.md) (실제 계산 샘플)

추천 점수를 구성하는 4개 요소의 **입력 → 처리 → 출력 스키마 → 저장소 → 소비처**를 정의합니다.

```
score(u, i) = w1 x cos(v_u⁺, v_i)       <- Product Vector,  User Behavior Vector (긍정 축)
            − λ  x cos(v_u⁻, v_i)       <- User Behavior Vector (부정 축), λ = 0.15
            + w2 x attr_affinity(u, i)  <- Attribute Affinity
            + w3 x prior(i)             <- Product Prior
```

---

## 0. 전체 데이터 흐름

```
[Sephora 원본]                          [프론트 이벤트]
product_info.csv                        POST /api/events
reviews_*.csv                                │
     │                                       ▼
     │                              backend/collector -> Kafka
     ├──────────────┬──────────────┐          │
     ▼              ▼              ▼          ▼
 Product        Attribute      Product    streaming/
 Vector          Affinity       Prior     user_feature_job
 (batch)         (batch)       (batch)         │
     │              │              │            ▼
     ▼              ▼              ▼      User Behavior Vector
  MySQL          MySQL          MySQL         Redis
     └──────────────┴──────────────┴────────────┘
                          │
                          ▼
              backend/recommend/RankingService
                          │
                          ▼
                   GET /api/recommend
```

| 요소 | 갱신 주기 | 저장소 | 크기 |
|---|---|---|---|
| Product Vector | 일 1회 배치 | MySQL | 200행 × 148차원 = 116KB |
| Attribute Affinity | 일 1회 배치 | MySQL | 4,000행 = 약 500KB |
| Product Prior | 일 1회 배치 | MySQL | 200행 |
| User Behavior Vector | **이벤트마다 증분** | Redis | 10,000명 × 148차원 × 2축 = 11.6MB |

**앞의 3개는 사용자와 무관한 오프라인 산출물**이고, 마지막 하나만 실시간입니다.

---

## 1. Product Vector

상품의 콘텐츠를 148차원 벡터로 표현합니다. (어휘집 v0.4 — v0.3 의 93차원에 brand 블록 55차원 추가)

### 입력

| 소스 | 필드 |
|---|---|
| `batch/ingest/data/products_200.json` | `secondary_category`, `tertiary_category`, `highlights`, `price_usd`, `rating` |
| `contracts/product-feature-vocab.json` | 블록별 어휘·문서빈도·가중치 |

### 처리

```
1. highlights 를 concern / clean / texture 3개 블록으로 분류
2. ingredient 는 태그 + 전성분 문자열 파싱으로 값 생성 (위치 가중)
3. 블록별 인코딩 (원핫 또는 멀티핫 + IDF)
4. 블록별 L2 정규화 -> 블록 가중치 곱
5. 전체 이어붙인 후 L2 정규화
```

블록 구성과 가중치는 [`product-feature-spec.md`](product-feature-spec.md) 3장 참조.

### 출력 스키마

```sql
CREATE TABLE product_feature (
    product_id      VARCHAR(16)  NOT NULL,
    vocab_version   VARCHAR(16)  NOT NULL,
    vector          JSON         NOT NULL,   -- float[148], L2 정규화 완료
    prior_score     DECIMAL(6,5) NOT NULL,
    secondary_category VARCHAR(64) NOT NULL,
    tertiary_category  VARCHAR(64) NOT NULL,
    price_bin       VARCHAR(8)   NOT NULL,
    rating          DECIMAL(3,2),
    updated_at      DATETIME     NOT NULL,
    PRIMARY KEY (product_id, vocab_version),
    INDEX idx_category (tertiary_category)
);
```

`vocab_version`을 PK에 포함해 어휘집 변경 시 구버전과 공존시킵니다. 롤백과 A/B 테스트에 필요합니다.

### 주의

**`product_id`는 사이즈 변형이 병합된 대표 ID입니다.** 리뷰를 조인할 때는 `products_200.json`의 `_merged.member_product_ids` 전체로 `IN` 조건을 걸어야 누락이 없습니다. 200개 그룹이 실제로는 262개 원본 `product_id`를 포함합니다.

### 소비처

- `backend/recommend/RankingService` — 코사인 유사도 계산
- `batch/jobs/build_user_vectors.py` — **User Behavior Vector 생성의 재료.** 이벤트의 `product_id`를 벡터로 변환하려면 이 테이블이 필요합니다. 스트리밍으로 옮길 때는 잡 기동 시 브로드캐스트로 적재해야 합니다

---

## 2. User Behavior Vector

사용자가 상호작용한 **상품 벡터들의 가중 평균**입니다. 사용자 속성은 들어가지 않습니다.

### 입력

| 소스 | 내용 |
|---|---|
| Kafka `events` 토픽 | `persona_id`, `product_id`, `event_type`, `event_time`, `session_id` |
| MySQL `product_feature` | 상품 벡터 (브로드캐스트) |

### 처리

사용자 벡터는 **두 개**입니다. 긍정 축 `v_u⁺` 와 부정 축 `v_u⁻` 입니다.

```
v_u⁺ = sum(w_k x decay(t_k) x v_i_k) / sum(w_k x decay(t_k))    전환한 상품만
v_u⁻ = sum(w_k x decay(t_k) x v_i_k) / sum(w_k x decay(t_k))    미전환 접촉 상품 + UI 좌절
```

**행동 가중치 — 단일 출처는 `frontend/src/types/log.ts` 입니다**

> 이 문서에 값을 복사해 두지 않습니다. 복사본은 반드시 갈라집니다.
> `batch/jobs/behavior_weights.py` 가 `log.ts` 를 **직접 파싱**해 `EVENT_WEIGHT` ·
> `SECTION_DWELL_WEIGHT` · `scrollDepthWeight()` · `EVENT_INTENT` 를 읽습니다.
> 프론트가 값을 고치면 배치·시뮬레이터가 자동으로 따라갑니다.

| 원천 (`log.ts`) | 내용 |
|---|---|
| `EVENT_WEIGHT` | 이벤트 33종의 가중치 (`add_to_cart` 4.0 ~ `rage_click` −2.0) |
| `SECTION_DWELL_WEIGHT` | 섹션 11종의 체류 가중치 (`ingredients`·`reviews` 1.5 ~ `list_controls` 0.3) |
| `scrollDepthWeight()` | 도달률 → 가중치 (25% 0.2 / 50% 0.5 / 75% 1.0 / 100% 1.5) |
| `EVENT_INTENT` | 이벤트 → intent 8종 (`session` `exposure` `interest` `comparison` `validation` `hesitation` `conversion` `friction`) |

값을 확인하려면 아래를 실행합니다.

```bash
python batch/jobs/behavior_weights.py
```

`event_weight = 0` 인 이벤트(`product_impression`, `recommendation_impression`, `impression_dwell`, `recommendation_snapshot`, `scroll_depth`, `session_start`, `exit_summary`, `quick_look_close`)는 두 축 어디에도 누적되지 않습니다. `scroll_depth` 가 0인 이유는 도달률별 가중치를 `scrollDepthWeight()` 로 따로 계산하기 때문입니다(규칙 2).

**리뷰 작성 이벤트는 없습니다.** 프론트에 `review_submit` 이 존재하지 않으며, 시뮬레이터도 생성하지 않습니다. 페르소나의 리뷰 이력은 이벤트가 아니라 **시드 상태**(`session_id = "seed"`)로 들어가고, 추천 단계에서는 "이미 산 상품" 으로 후보에서 제외됩니다(§5).

**시간 감쇠**: `decay(t) = exp(−Δt / τ)`, τ = 30일

### 집계 규칙 (canonical)

`persona-schema.md` §12.1 · §12.3 과 `processed-schema.md` 는 이 절을 참조합니다. 산식을 중복 정의하지 않습니다.
구현은 `batch/jobs/user_vector.py` 입니다.

| # | 규칙 | 이유 |
|---|---|---|
| 1 | `product_id` 가 없는 이벤트는 버린다 | 목록 그리드 체류는 특정 상품에 귀속되지 않는다 |
| 2 | `scroll_depth` 는 상품별 **최대 도달 1건**만 가중한다 | 누적하면 끝까지 내려간 것이 `cart.add` 보다 무거워진다 |
| 3 | `section_dwell` / `section_view` 는 **상품 × 섹션당 1건**만 센다 | 스크롤을 오르내릴 때마다 쌓여 `cart.add` 를 압도한다 |
| 4 | `reason=checkpoint` 인 체류는 버린다 | 화면에 떠 있었다는 뜻이지 봤다는 뜻이 아니다 |
| 5 | **전환한 상품만 `v_u⁺`. 전환하지 않은 접촉 상품은 양의 가중치까지 통째로 `v_u⁻`** | "보긴 봤다" 는 좋아한다는 뜻이 아니다 |
| 6 | **UI 좌절**(`intent=friction`)은 전환 여부와 무관하게 항상 `v_u⁻` | `rage_click`, `dead_click` |
| 7 | **미전환 상품의 부정 강도는 관여도에 반비례한다** | 아래 참조 |

### 규칙 7 — 부정 강도는 관여도에 반비례한다

```
neg(i) = NEG_W0 / (1 + engagement(i) / NEG_TAU)      NEG_W0 = 1.0, NEG_TAU = 4.0
```

`engagement(i)` 는 그 상품에 쌓인 관여 점수입니다 — 양의 가중치 합에 **망설임·비교 이벤트의 절대값**을 더한 값입니다.

| 상황 | 관여도 | 부정 강도 |
|---|---:|---:|
| 즉시 이탈 (클릭만 하고 나감) | 1.0 | **0.80** |
| 얕게 보고 이탈 | 3.0 | 0.57 |
| 정독 후 이탈 | 5.0 | 0.44 |
| 담았다 뺌 | 13.0 | **0.24** |

**오래 본 상품은 그 사용자의 취향과 방향이 가깝습니다.** 그것을 강하게 감점하면 자기 취향을 스스로 깎아내리게 됩니다. 반대로 열자마자 나간 상품은 취향과 멀다는 뜻이므로 감점을 세게 줍니다.

이전 구현은 반대였습니다. 관여 점수를 그대로 부정 가중치로 써서 **담았다 뺀 상품이 그냥 지나친 상품보다 3.16배 무겁게** 감점됐습니다(평균 13.89 vs 4.39). 구매 직전까지 간 상품을 가장 싫어하는 것으로 계산한 셈입니다.

**감점 이벤트를 두 갈래로 가릅니다. 분류는 `log.ts` 의 `EVENT_INTENT` 를 그대로 따릅니다.**

| intent | 이벤트 | 처리 |
|---|---|---|
| `friction` | `rage_click`, `dead_click` | UI 좌절. 관여의 반대이므로 **절대값 그대로 감점** |
| `hesitation` | `remove_from_cart` | 재고(再考). **관여도에 더한다** → 부정이 약해짐 |
| `comparison` | `scroll_backtrack` | 되돌아 읽기. **관여도에 더한다** |

프론트가 이미 `remove_from_cart` 를 *"좌절이 아니라 망설임 축"* 으로 분류해 두었는데(`log.ts:204`), 집계가 그 구분을 쓰지 않고 있었습니다.

> 정확도 영향은 없습니다(`NEG_TAU` 를 1~무한대로 훑어도 전부 CI 가 0 을 걸침). **설계 논리로 정한 값이며, 실로그가 쌓이면 재측정 대상입니다.**

**전환(conversion)의 정의**

| 이벤트 | 처리 |
|---|---|
| `cart.add` (`add_to_cart`), `quantity_change` | `converted` 에 추가 |
| `wishlist_toggle` (`action != "remove"`) | `converted` 에 추가 |
| `wishlist_toggle` (`action == "remove"`), `remove_from_cart` | `converted` 에서 제거 → 해당 상품은 `v_u⁻` 로 넘어간다 |

> **`intent` 와 `converted` 는 다른 축입니다.** `log.ts` 의 `EVENT_INTENT` 는 GA4 퍼널 단계 라벨이고, `converted` 는 특정 상품에 대한 선호 판정입니다.
> `view_cart` 는 `intent = conversion` 이지만 `converted` 에 넣지 않습니다. 장바구니 **화면**을 열었다는 뜻이라 특정 상품의 증거가 아니며, 프론트도 `product_id` 없이 발행하므로 규칙 1에서 걸러집니다. 장바구니에 담긴 상품은 이미 `add_to_cart` 로 `converted` 에 들어가 있습니다.

**부호와 축을 혼동하지 않도록 2단계로 나눕니다.** `final_weight` 의 부호는 1단계에서만 쓰고, 어느 축으로 갈지는 2단계에서 **상품 단위**로 정합니다.

```python
# 1단계 — 이벤트를 상품별로 누적 (부호 그대로, 규칙 2·3·4 적용 후)
if final_weight > 0: product_pos[pid] += final_weight
if final_weight < 0: product_neg[pid] += abs(final_weight)   # 규칙 6

# 2단계 — 조회 시점에 상품 단위로 축을 가른다 (규칙 5)
for pid, w in product_pos.items():
    if pid in converted:
        positive_u_sum += w * v_pid;  positive_w_sum += w
    else:
        negative_u_sum += w * v_pid;  negative_w_sum += w

for pid, w in product_neg.items():
    negative_u_sum += w * v_pid;  negative_w_sum += w
```

분모는 두 축 모두 절대값 누적이라 0 또는 음수가 되지 않습니다. `positive_w_sum = 0` 이면 `v_u⁺` 를 만들지 않고 속성·인기도 중심 스케줄을 씁니다.
감점은 벡터 누적 단계가 아니라 **최종 점수에서 한 번만** 적용합니다 (§5).

**측정 근거** — 페르소나 9,900명 시뮬레이션 로그, 부트스트랩 300회. 오프라인 평가 모드 기준입니다.

| 집계 규칙 | Recall@10 | 95% CI | 롱테일 |
|---|---:|---|---:|
| 리뷰 시드만으로 만든 벡터 (기준선) | 12.8% | | 19.9% |
| `final_weight > 0` 을 전부 `v_u⁺` 로 (초안) | 5.9% | [5.1, 6.8] | 6.1% |
| + 규칙 3 (체류 1건) | 8.3% | [7.3, 9.3] | 10.8% |
| **+ 규칙 5 (미전환은 `v_u⁻`)** | **12.6%** | [11.4, 13.7] | **19.6%** |

규칙 5 가 없으면 **로그로 만든 벡터가 리뷰 시드만 쓴 벡터보다 나쁩니다.** 눌러보기만 한 상품이 취향 벡터의 대부분을 차지하기 때문입니다.

### 출력 스키마 (Redis)

전체 재계산 없이 O(148)로 증분 갱신하기 위해 **누적합과 누적가중치만** 보관합니다.

```
KEY   user:vec:{persona_id}
TYPE  Hash
FIELD positive_u_sum : float[148]  긍정 축 가중 누적합 (JSON 또는 바이너리)
      positive_w_sum : float       긍정 축 가중치 누적합
      negative_u_sum : float[148]  부정 축 가중 누적합
      negative_w_sum : float       부정 축 가중치 누적합
      converted      : Set         전환한 product_id — 하드 제외 + v_u⁺ 판정
      viewed         : Set         접촉한 모든 product_id (converted 포함)
      n_products     : int         |viewed| (가중치 스케줄 판정용)
      updated_at     : timestamp
TTL   없음 (시뮬레이션 종료까지 유지)
```

**`seen` 을 두 집합으로 나눕니다.** 하드 제외와 소프트 강등은 다른 처리라 단일 집합으로 표현되지 않습니다. 기존 문서의 `seen` 은 `viewed` 에 해당하고, **추천 후보에서 실제로 빼는 것은 `converted` 뿐**입니다.

`converted ⊆ viewed` 입니다. `cart.add` 는 가중치 4.0 이라 `viewed` 에도 들어갑니다. 두 집합은 배타적이지 않습니다.

| 집합 | 등록 조건 | 추천에서의 처리 |
|---|---|---|
| `converted` | 위 "전환의 정의" 표에 해당하는 이벤트 발생 | **후보에서 완전히 제외** |
| `viewed` | `event_weight != 0` 인 이벤트가 1건이라도 발생 (감점 이벤트·`scroll_depth` 포함) | 후보에 남기되 **상한 2개** (§5) |
| (미등록) | `product.impression` 등 `event_weight = 0` 노출 | 두 집합 어디에도 넣지 않는다 |

소프트 강등이 실제로 적용되는 대상은 `converted` 를 먼저 제외한 뒤 남는 **`viewed \ converted`** 입니다. 상한 계산은 이 차집합에 대해 셉니다.

감점 이벤트만 발생한 상품도 `viewed` 에 들어갑니다. `rage_click` 이 찍혔다는 것은 그 상품을 봤다는 뜻이므로 노출 이력으로는 유효합니다.

### 리뷰 극성의 처리

페르소나의 리뷰 이력을 쓰는 오프라인 평가에서는 **별점 1~2점 상품을 `v_u⁻` 로 넘깁니다.** 시드(긍정 축)에 섞으면 취향 벡터가 비선호 방향으로 끌려갑니다.

| 처리 | Recall@10 |
|---|---:|
| 극성 무관 — 전부 시드에 (옛 동작) | 23.61% |
| 0 처리 — 어디에도 안 넣음 | 23.84% |
| **음수축 λ=0.15 (채택)** | **23.85%** |

0 처리와 음수축의 차이는 없습니다(+0.01%p, CI [−0.08, +0.10]). 부정 상품을 가진 페르소나가 1,270명(12.8%)뿐이라 그렇습니다. **실로그에서 어떤 영향을 줄지 모르므로 축을 살려 둡니다.**

> ⚠️ **"부정" 이라는 말의 대상이 두 가지입니다.** 리뷰의 부정은 **별점 1~2점**, 행동 로그의 `v_u⁻` 는 **조회했으나 전환하지 않은 상품** 입니다. 문서에서 언급할 때 어느 쪽인지 명시해야 합니다.

노출(`impression`)을 넣지 않는 이유는 사용자 의지가 아니기 때문입니다. 넣으면 스크롤 한 번에 후보가 통째로 사라집니다.

```python
# 이벤트 1건당 O(148)
#  축 결정은 조회 시점의 상품 단위 분기를 따른다 (위 2단계 의사코드)
u_sum += w * decay * v_item
w_sum += w * decay
n_products = |viewed|                               # converted ⊆ viewed
positive_vector = positive_u_sum / positive_w_sum   # positive_w_sum > 0
negative_vector = negative_u_sum / negative_w_sum   # negative_w_sum > 0
```

`n_products`를 별도로 두는 이유는 가중치 스케줄이 **이벤트 수가 아니라 고유 상품 수**를 기준으로 하기 때문입니다. 스크롤 4단계 때문에 상품 하나만 정독해도 이벤트가 5건 발생합니다.

### 소비처

`RankingService` — `cos(v_u⁺, v_i)` · `cos(v_u⁻, v_i)` 계산, `converted` 제외, `viewed` 상한 적용

---

## 3. Attribute Affinity

**사용자 속성 ↔ 상품**을 잇는 조회 테이블입니다. 콘텐츠 벡터가 아니라 별도 테이블인 이유는, 콘텐츠 벡터가 상품당 1개로 고정되어 **사용자별 분기가 불가능**하기 때문입니다.

### 입력

| 소스 | 내용 |
|---|---|
| `reviews_*.csv` | 458,180건 (상위 200개 상품, 속성 4개 전부 채워진 건) |
| 정규화 규칙 | `skin_tone` 5버킷, `hair_color` `brunette`→`brown`, `eye_color` `Grey`→`gray` |

### 처리 — 평점 평균이 아니라 구성비 lift

```
share_shrunk = (관측수 + K x 기준비율) / (셀 표본수 + K),   K = 50
lift         = share_shrunk / 기준비율
affinity     = clip((lift - CLIP_LO) / (CLIP_HI - CLIP_LO), 0, 1)

CLIP_LO = 0.60,  CLIP_HI = 1.60
```

클리핑 구간은 lift 분포의 p5~p95(0.636~1.364)를 담도록 잡았습니다. 초기값 `[0.80, 1.20]`은 범위가 좁아 **4,000셀 중 23.5%가 0 또는 1로 포화**되어 상위권 서열이 사라졌습니다. `[0.60, 1.60]`으로 넓혀 포화율을 **6.4%**로 낮췄습니다.

| 구간 | 총 포화율 |
|---|---:|
| `[0.80, 1.20]` (초기값) | 23.5% |
| **`[0.60, 1.60]` (채택)** | **6.4%** |
| `[0.50, 2.00]` | 3.2% |

더 넓히면 포화는 줄지만 값이 0.5 근처로 몰려 상품 간 격차가 작아집니다. p99가 1.907이므로 상위 1%만 상단에서 잘립니다.

평점 평균을 쓰지 않는 이유는 리뷰의 **63.4%가 5점**이라 판별력이 노이즈 수준(η² < 0.004)이기 때문입니다. 근거는 [`recommendation-design.md`](../docs/ai/recommendation-design.md) 6-1절 참조.

### 출력 스키마

```sql
CREATE TABLE attribute_affinity (
    product_id   VARCHAR(16)  NOT NULL,   -- 병합 대표 ID
    attribute    VARCHAR(16)  NOT NULL,   -- skin_type | skin_tone | hair_color | eye_color
    segment      VARCHAR(24)  NOT NULL,   -- oily | deep | gray ...
    affinity     DECIMAL(6,5) NOT NULL,   -- 0~1
    lift         DECIMAL(8,4) NOT NULL,   -- 원본 lift (디버깅·설명 문구용)
    n_reviews    INT          NOT NULL,   -- 셀 표본 수
    z_score      DECIMAL(8,2) NOT NULL,   -- 유의성
    updated_at   DATETIME     NOT NULL,
    PRIMARY KEY (product_id, attribute, segment)
);
```

**4,000행** = 200상품 × 20세그먼트(`skin_type` 4 + `skin_tone` 5 + `hair_color` 6 + `eye_color` 5). 원본은 `batch/ingest/data/affinity_lift.csv`.

구현은 `batch/jobs/persona_feature.py` 입니다. `AffinityTable(index)` 를 만들면 `Recommender(affinity=...)` 에 그대로 넘길 수 있습니다.

`lift`와 `n_reviews`를 함께 저장하는 이유는 **추천 근거 문구**에 쓰기 때문입니다 — "지성 피부 사용자 1,240명이 평균보다 2.6배 많이 선택한 제품".

### 조회 시 가중치 — 사용자 `skin_type`에 따라 분기

| 사용자 `skin_type` | `skin_type` | `skin_tone` | `hair_color` | `eye_color` |
|---|---:|---:|---:|---:|
| `dry` / `oily` / `normal` (44.7%) | 0.40 | 0.40 | 0.10 | 0.10 |
| **`combination` (55.3%)** | **0.00** | **0.80** | 0.10 | 0.10 |

```
attr_affinity(u, i) = w_type x A[i][skin_type][u.skin_type]
                    + w_tone x A[i][skin_tone][u.skin_tone]
                    + 0.10   x A[i][hair_color][u.hair_color]
                    + 0.10   x A[i][eye_color][u.eye_color]
```

복합성 사용자는 `skin_type` 항을 사용하지 않습니다. 200개 상품 전부 lift 0.85~1.19(표준편차 0.053)로 판별력이 없기 때문입니다. 해당 몫은 `skin_tone`으로 이관합니다.

**셀이 없는 경우 기본값 0.5** (중립)을 사용합니다.

### 소비처

`RankingService` — 딕셔너리 조회 1회. 4,000행 전량을 메모리에 적재합니다.

---

## 4. Product Prior

개인화 정보가 부족한 초기 구간의 안전장치입니다.

### 입력

`products_200.json`의 `loves_count` (범위 1,237 ~ 1,081,315)

### 처리 — log 정규화 필수

```
prior(i) = (log1p(loves_count) - log_min) / (log_max - log_min)
```

선형 정규화 시 **200개 중 109개가 0.1 미만**으로 붙어버립니다. log 적용 시 1개뿐입니다.

### 왜 `rating`을 쓰지 않는가

상위 200개의 `rating`은 3.31~4.83에 몰려 변동계수가 0.057입니다. 그리고 `loves_count`와의 상관이 **−0.062**로 무관합니다. 인기와 만족도는 별개이므로 평점을 인기도 대용으로 쓸 수 없습니다.

### 출력

`product_feature.prior_score` 컬럼에 함께 저장합니다 (별도 테이블 불필요).

### 소비처

`RankingService` — `w3` 항. 상호작용 상품 6개 이상이면 `w3 = 0`으로 빠집니다.

---

## 5. 최종 추천 API

### 요청

```
GET /api/recommend?persona_id={id}&size=10
```

### 처리

```
1. Redis에서 (positive_*, negative_*, n_products, converted, viewed) 조회
2. n_products로 가중치 스케줄 결정
3. v_u⁺ = positive_u_sum / positive_w_sum   (positive_w_sum = 0이면 생략)
   v_u⁻ = negative_u_sum / negative_w_sum   (negative_w_sum = 0이면 생략)
4. scores = w1 x (V @ v_u⁺) − λ x (V @ v_u⁻) + w2 x attr_affinity + w3 x prior
5. 노출 정책 적용 (아래)
6. MMR 다양성 보정 (λ_mmr = 0.8, 후보 풀 상위 30개 — λ_mmr 은 점수 쪽 계수라 클수록 약하게 걸리고 1.0 이면 끈 것과 같음)
7. 상위 size개 반환
```

`λ = 0.15` 입니다. **시뮬레이션 로그 기준 잠정값**이며 실제 로그가 쌓이면 재측정합니다.
§4의 MMR 계수와 이름이 겹치므로 문서에서는 감점 계수를 `λ`, 다양성 계수를 `λ_mmr` 로 구분합니다.

**노출 정책**

| 상품 | 오프라인 평가 | 서빙 |
|---|---|---|
| 리뷰 쓴 상품 (이미 구매) | 제외 | 제외 |
| `converted` (장바구니·위시리스트) | 제외 | 제외 |
| `viewed` (조회만) | **제외** | **상한 2개까지 포함** |

서빙에서 조회 상품을 전부 빼지 않는 이유는 재고려 리마인드가 유효한 추천이기 때문입니다. 상한을 0~6으로 재봤을 때 **2개에서 포화**했고 비용은 −0.6%p 였습니다.

> ⚠️ **오프라인 평가에서는 `viewed` 까지 전부 제외합니다.** 시드가 결과에 섞이면 자기 자신을 맞히는 셈이라 적중률이 부풀려집니다(leakage). **서빙 수치와 평가 수치를 직접 비교하지 마십시오.** 이 문서의 모든 Recall 수치는 평가 모드 값입니다.

**가중치 스케줄**

| 상호작용 고유 상품 수 | w1 (코사인) | w2 (속성) | w3 (인기도) |
|---|---:|---:|---:|
| 0개 | 0.00 | 0.30 | 0.70 |
| 1~5개 | 0.70 | 0.25 | 0.05 |
| 6개 이상 | 0.80 | 0.18 | 0.02 |

**행동이 쌓일수록 속성의 몫을 콘텐츠로 넘깁니다.** 이전 표의 "6개 이상 = 0.40 / 0.55 / 0.05"는 방향이 뒤집혀 있었고(미확정으로 표시돼 있었음), 그 구간에서 Recall@10 이 17.6% 였습니다. 같은 조건에서 속성 항을 빼면 21.5% 로 올라갈 만큼 손해가 컸습니다.

9,900명 leave-last-out 재측정 결과입니다 (부트스트랩 300회, 짝비교).

| 조건 | 전체 | 롱테일 | 현행 대비 |
|---|---:|---:|---|
| **현행 (이 표, test 1,971명)** | **23.39%** | 31.29% | 기준 |
| 이전 스케줄 | 22.43% | 30.91% | −0.96%p CI [−1.50, −0.36] |
| 속성 항 제거(w2=0) | 22.58% | 30.91% | −0.81%p CI [−1.52, −0.02] |

**고친 것은 6개 이상 구간 하나입니다.** 1~5개 구간(0.70 / 0.25 / 0.05)은 측정으로 뒷받침된 값이라 그대로 둡니다 — 함께 손대면 시드 1~2개 구간이 26.24% → 25.38% 로 손해를 봅니다.

속성 항은 정확도를 올리는 장치가 아니라 **롱테일 보험**입니다 — 빼면 전체보다 롱테일이 더 크게 떨어집니다(30.86% → 29.48%). 속성 항의 몫을 인기도로 옮기는 안은 −2.24%p 로 명확히 나빠 채택하지 않았습니다. 측정 스크립트는 `batch/jobs/eval_persona_feature.py`, 배경은 `docs/ai/persona-feature-port.md` §7.

### 응답

```json
{
  "persona_id": "PC00001",
  "n_products": 3,
  "weights": { "cosine": 0.60, "attr": 0.35, "prior": 0.05 },
  "items": [
    {
      "product_id": "P420652",
      "product_name": "Lip Sleeping Mask Intense Hydration with Vitamin C",
      "score": 0.7231,
      "breakdown": {
        "cosine": 0.6120,
        "attr_affinity": 0.4710,
        "prior": 1.0000
      },
      "reason": {
        "attribute": "지성 피부 사용자가 평균보다 2.6배 많이 선택",
        "content": "회원님이 본 클렌저와 성분 구성이 유사"
      }
    }
  ]
}
```

`breakdown`을 응답에 포함하는 이유는 **추천 근거를 항별로 분해해 설명**할 수 있기 때문입니다. 잠재 요인 CF로는 불가능한 부분이며 CBF를 선택한 이유입니다.

### 성능 실측

상품 200개 × 148차원 기준, numpy 싱글 코어:

| 항목 | 값 |
|---|---:|
| 추천 1건 (점수 계산 + 상위 10개 추출) | **6.8 μs** |
| 싱글 코어 처리량 | 146,000 RPS |
| 사용자 10,000명 전원 일괄 재계산 | 3.8 ms |

FAISS·벡터DB·ANN 인덱스는 사용하지 않습니다. 200개 규모에서는 numpy 행렬곱 한 줄이 더 빠릅니다.

---

## 6. 검증 시 주의

**생성한 페르소나 로그로 가중치를 학습·튜닝하지 마세요.** 로그를 이 규칙으로 만들 것이므로, 그 로그로 평가하면 심어둔 규칙을 되찾을 뿐입니다.

- 가중치: 룰로 고정
- 검증: **실제 리뷰 데이터 holdout**으로 수행

---

## 7. 미확정 항목

| 항목 | 상태 |
|---|---|
| 콘텐츠 벡터 블록 가중치 | 측정 결과 같은 카테고리 이웃 91.1%로 과도. 중간안 A 권고, 담당자 확정 대기 |
| `hair_color` / `eye_color` 존치 | 판별력 최하위. `hair_color`는 연령 대리변수로 의심 |
| MMR λ_mmr | **0.8 확정** (2026-09-01). valid 에서 정확도는 어느 λ 에서도 유의차 없음 → **다양성 기준으로 채택**. 목록당 고유 브랜드 3.7 → 4.2개, 한 브랜드 최대 점유 61.3% → 59.0%. 근거는 `docs/ai/recommendation-design.md` 8절 |
| 시간 감쇠 τ | 30일. 생성 로그의 시간 범위에 따라 조정 |
| `w1` 항 검증 | 행동 로그 생성 후 가능 |
