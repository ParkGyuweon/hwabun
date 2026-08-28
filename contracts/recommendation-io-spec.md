# 추천 입출력 데이터 구조

> 2026-08-27 · 어휘집 버전 `0.1-draft`
> 관련: [`recommendation-design.md`](../docs/ai/recommendation-design.md) (계산 설계) · [`product-feature-spec.md`](product-feature-spec.md) (상품 벡터 명세) · [`product-feature-sample.md`](../docs/ai/product-feature-sample.md) (실제 계산 샘플)

추천 점수를 구성하는 4개 요소의 **입력 → 처리 → 출력 스키마 → 저장소 → 소비처**를 정의합니다.

```
score(u, i) = w1 x cos(v_u, v_i)        <- Product Vector,  User Behavior Vector
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
| Product Vector | 일 1회 배치 | MySQL | 200행 × 93차원 = 73KB |
| Attribute Affinity | 일 1회 배치 | MySQL | 4,000행 = 약 500KB |
| Product Prior | 일 1회 배치 | MySQL | 200행 |
| User Behavior Vector | **이벤트마다 증분** | Redis | 10,000명 × 93차원 = 3.6MB |

**앞의 3개는 사용자와 무관한 오프라인 산출물**이고, 마지막 하나만 실시간입니다.

---

## 1. Product Vector

상품의 콘텐츠를 93차원 벡터로 표현합니다.

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
    vector          JSON         NOT NULL,   -- float[93], L2 정규화 완료
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
- `streaming/transforms/feature_calc.py` — **User Behavior Vector 생성의 재료.** 이벤트의 `product_id`를 벡터로 변환하려면 이 테이블이 필요하므로 스트리밍 잡 기동 시 브로드캐스트로 적재해야 합니다

---

## 2. User Behavior Vector

사용자가 상호작용한 **상품 벡터들의 가중 평균**입니다. 사용자 속성은 들어가지 않습니다.

### 입력

| 소스 | 내용 |
|---|---|
| Kafka `events` 토픽 | `persona_id`, `product_id`, `event_type`, `event_time`, `session_id` |
| MySQL `product_feature` | 상품 벡터 (브로드캐스트) |

### 처리

```
v_u = sum(w_k x decay(t_k) x v_i_k) / sum(w_k x decay(t_k))
```

**행동 가중치**

| `event_type` | 가중치 | 비고 |
|---|---:|---|
| `product.impression` | 0 | 목록 노출은 증거가 아님 |
| `product.click` | 1.0 | 상세 진입 |
| `scroll.depth` 25% | 0.5 | |
| `scroll.depth` 50% | 1.5 | |
| `scroll.depth` 75% | 2.0 | 실질 관심 신호 |
| `scroll.depth` 100% | 2.5 | |
| `cart.add` | 4.0 | |
| `review.submit` | **(rating − 3) × 2** | 범위 −4 ~ +4 |

`review.submit`의 중심 3은 **고정**입니다. `rating`을 그대로 쓰면 1점 준 상품도 취향으로 학습됩니다.

**시간 감쇠**: `decay(t) = exp(−Δt / τ)`, τ = 30일

### 출력 스키마 (Redis)

전체 재계산 없이 O(93)로 증분 갱신하기 위해 **누적합과 누적가중치만** 보관합니다.

```
KEY   user:vec:{persona_id}
TYPE  Hash
FIELD u_sum      : float[93]  가중 누적합 (JSON 또는 바이너리)
      w_sum      : float      가중치 누적합
      n_products : int        상호작용한 고유 상품 수 (가중치 스케줄 판정용)
      seen       : Set        이미 상호작용한 product_id (추천 제외용)
      updated_at : timestamp
TTL   없음 (시뮬레이션 종료까지 유지)
```

```python
# 이벤트 1건당 O(93)
u_sum += w * decay * v_item
w_sum += w * decay
n_products = |seen|
user_vector = u_sum / w_sum          # 조회 시 계산
```

`n_products`를 별도로 두는 이유는 가중치 스케줄이 **이벤트 수가 아니라 고유 상품 수**를 기준으로 하기 때문입니다. 스크롤 4단계 때문에 상품 하나만 정독해도 이벤트가 5건 발생합니다.

### 소비처

`RankingService` — `cos(v_u, v_i)` 계산 및 `seen` 제외

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

**4,000행** = 200상품 × 21세그먼트(`skin_type` 4 + `skin_tone` 5 + `hair_color` 6 + `eye_color` 5). 원본은 `batch/ingest/data/affinity_lift.csv`.

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
1. Redis에서 (u_sum, w_sum, n_products, seen) 조회
2. n_products로 가중치 스케줄 결정
3. user_vector = u_sum / w_sum        (n_products = 0이면 생략)
4. scores = w1 x (V @ user_vector) + w2 x attr_affinity + w3 x prior
5. seen 제외
6. MMR 다양성 보정 (λ = 0.7)
7. 상위 size개 반환
```

**가중치 스케줄**

| 상호작용 고유 상품 수 | w1 (코사인) | w2 (속성) | w3 (인기도) |
|---|---:|---:|---:|
| 0개 | 0.00 | 0.80 | 0.20 |
| 1~2개 | 0.35 | 0.55 | 0.10 |
| 3~5개 | 0.60 | 0.35 | 0.05 |
| 6개 이상 | 0.80 | 0.20 | 0.00 |

### 응답

```json
{
  "persona_id": "PC00001",
  "n_products_seen": 3,
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

상품 200개 × 93차원 기준, numpy 싱글 코어:

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
| MMR λ | 0.7은 초기값 |
| 시간 감쇠 τ | 30일. 생성 로그의 시간 범위에 따라 조정 |
| `w1` 항 검증 | 행동 로그 생성 후 가능 |
