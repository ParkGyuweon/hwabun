# 추천 입출력 데이터 구조

> 2026-08-27 (최종 갱신 2026-08-31) · 어휘집 버전 `0.4` (148차원)
> 관련: [`recommendation-design.md`](../docs/ai/recommendation-design.md) (계산 설계) · [`product-feature-spec.md`](product-feature-spec.md) (상품 벡터 명세) · [`product-feature-sample.md`](../docs/ai/product-feature-sample.md) (실제 계산 샘플)

> ## 2026-09-07 — 점수 결합이 바뀌었습니다. 먼저 읽을 것
>
> 두 가지가 같은 날 채택됐습니다.
>
> **① CF 가점** (§4-1) — "이 상품을 좋게 본 사람이 저것도 좋게 봤다" 를 더합니다.
> **② 학습 결합 (LTR)** (§4-2) — 손으로 정한 선형 합을 **모델 추론으로 대체**합니다.
>
> | 축 | CBF 단독 | CBF + CF | **현행 (LTR)** |
> |---|---:|---:|---:|
> | 오프라인 Recall@10 | 23.39% | 38.15 / 39.25% | **43.30 / 42.60%** |
> | 리뷰 순차 재생 | 22.63% | — | **43.30 / 42.60%** |
> | 동적 Start / Ever HR@10 (holdout_a) | 23.39 / 28.97% | 37.4 / 40.55% | **43.65 / 49.60%** (b: 42.60 / 48.45%) |
> | 최다 브랜드 칸 수 (09-07 측정) | 5.92칸 | 4.43칸 | **2.62칸** |
> | 10칸 전부 한 브랜드 (09-07 측정) | 9.8% | 3.6% | **0.1%** |
>
> **두 값은 `holdout_a / holdout_b` 입니다.** `test` 는 소진돼 대표 지표에 쓰지
> 않습니다 (`evaluation-framework.md` 부록 Q). CBF 단독 열만 옛 `test` 값입니다.
>
> **대표 지표는 `Recall@10 = 43.30%` (holdout_a 2,000명)** 이고, 확인 집합
> `holdout_b` 에서 42.60% 입니다. 선형 대비 **+5.10%p [+3.25, +6.55]** ·
> **+3.30%p [+1.52, +5.00]** 로 두 집합 다 CI 가 0 을 제외합니다.
> (2026-09-10 갱신 — highlights 성분 태그를 벡터에서 뺀 뒤 값. 09-07 의 43.95 / 43.20% 는
> 계약 §3.1 과 어긋난 인코더의 값이었다. `evaluation-framework.md` 부록 V)
>
> **바뀌는 것은 §5 처리의 4단계 하나입니다.** Redis 스키마·실시간 증분 갱신
> (§2-1)·노출 정책·MMR·배너(§5-1)는 그대로입니다. 다만 §2 에 **`positive` 집합이
> 하나 추가**됐습니다 — 학습 결합의 시드입니다.
>
> **잃는 것은 `breakdown` 항별 분해**입니다. 블록 가중치·상품 인코딩·배너 축은
> 그대로 남습니다.
>
> **이 문서 안의 다른 수치 중 날짜가 2026-09-07 보다 앞선 것은 CBF 기준입니다.**
> 그때 값으로 남겨 두었습니다 — 돌리지 않은 수치를 손으로 고치면 그것이 다음
> 사고가 됩니다. 근거는 `evaluation-framework.md` 부록 S · T.

추천 점수를 구성하는 요소의 **입력 → 처리 → 출력 스키마 → 저장소 → 소비처**를 정의합니다.

```
score(u, i) = model.predict_proba(피처 19개)      <- Learning to Rank (§4-2)
```

**결합을 사람이 정하지 않고 학습합니다** (2026-09-07 채택). 아래 항들은 없어지지
않고 **모델의 피처로 들어갑니다.**

```
피처 19개 = cos(v_u⁺, v_i)         <- Product Vector, User Behavior Vector
            attr_affinity(u, i)     <- Attribute Affinity (§3)
            prior(i)                <- Product Prior (§4)
            cf, cf_rank, supporters <- Item Co-occurrence (§4-1)
            same_brand, price_prox, n_seed, pop_rank
            블록별 코사인 9개        <- 어휘집 ORDER 순서
```

> **선형 결합은 폴백으로 남습니다.** 모델 산출물이 없으면 아래 식으로 돕니다.
> 구현할 때 이 한 단계만 갈아 끼울 수 있는 모양으로 두십시오.
>
> ```
> score(u, i) = w1 x cos(v_u⁺, v_i) − λ x cos(v_u⁻, v_i)   λ = 0.15
>             + w2 x attr_affinity(u, i) + w3 x prior(i)
>             + w_b x brand_unknown(u, i)                   w_b = 0.60
>             + β  x cf_bonus(u, i)                         β = 1.0 (§4-1)
> ```

### `brand_unknown` — 어휘집에 없는 브랜드를 위한 폴백 (2026-09-03)

```
brand_unknown(u, i) = 1   상품 i 의 brand_name 이
                          (a) 어휘집 brand 목록에 **없고**
                          (b) 사용자 u 가 전환한 상품의 브랜드 집합에 **있을 때**
                      0   그 밖에는 전부 0
```

`brand` 는 어휘집에 담긴 55개 고정 원핫입니다. 브랜드가 상품을 직접 등록하는
구조가 되면서 **목록에 없는 브랜드는 그 55차원이 전부 0** 이 되는 문제가 생겼습니다.
정확도에 가장 크게 기여하는 신호를 신규 브랜드만 못 받게 됩니다
(브랜드 블록이 없을 때 Recall@10 23.6% → 11.4%).

브랜드가 등록될 때마다 차원을 늘리고 기존 상품 200개를 다시 인코딩하는 것은 서비스
운영 중에 할 수 없으므로, **어휘집 밖 브랜드에만** 점수 항을 하나 더합니다.
문자열 비교라 어휘집이 필요 없습니다.

**어휘집에 있는 브랜드는 지금처럼 원핫으로 계산합니다.** 그래서 기존 카탈로그의
벡터와 점수는 한 자리도 바뀌지 않습니다 — 당시 대표 지표 Recall@10 **23.39%**
(CBF 단독) 가 그대로였습니다.

> 관계 항으로 **전면 교체**하는 안(brand 블록을 지우고 148 → 93차원)도 측정했습니다.
> valid 에서는 구분되지 않았지만(24.20% vs 24.30%) **test 에서 −0.81%p** 였습니다.
> 신규 브랜드 지원만 필요하다면 폴백으로 충분합니다.
> 재현: `Research/eval/eval_brand_relation_feature_20260903.py`

구현은 `batch/jobs/recommender.py` 의 `BRAND_W` · `brand_match(brands, rows, known)` 입니다.

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
2. ingredient 는 태그 + 전성분 문자열 파싱으로 값 생성 (위치 가중).
   **전성분은 한글·영문 모두 받습니다** — 성분 29종에 한국어 표기가 동의어로
   들어 있어 같은 성분표를 한글로 넣어도 매칭과 위치가중값이 같습니다
3. 블록별 인코딩 (원핫 또는 멀티핫 + IDF)
4. 블록별 L2 정규화 -> 블록 가중치 곱
5. 전체 이어붙인 후 L2 정규화
```

블록 구성과 가중치는 [`product-feature-spec.md`](product-feature-spec.md) 3장 참조.

**등록 상품에 없는 값 (2026-09-03)**

| 필드 | 신규 상품 | 처리 |
|---|---|---|
| `rating` | 리뷰가 0건이라 없다 | **같은 `tertiary_category` 의 중앙값**을 채운다. 단 그 카테고리 표본이 **3개 미만이면 전체 중앙값** — 상품 1~2개짜리 카테고리의 "중앙값" 은 그 상품 한둘의 평점일 뿐이다 (카탈로그 19개 중 7개가 해당, 전체 중앙값과 최대 0.489 차이). 카테고리가 처음이어도 전체 중앙값. 범위 밖 값은 0~1 로 자른다 |
| `loves_count` | 없다 | **0**. 인기도 항이 자연히 바닥값이 된다 |

`rating` 을 브랜드에게 직접 입력받으면 안 됩니다 — 자기 평점을 적으면 그대로 추천
점수가 됩니다. 등록 폼에서 받지 않고 파이프라인이 채웁니다.
구현은 `batch/jobs/product_encoder.py` 의 `rating_value()` 입니다.

### 인기도는 **사이트 안에서** 다시 편다 (2026-09-03)

`prior(i)` 는 카탈로그 200개 전체의 `loves_count` 를 log1p → minmax 한 값입니다.
그런데 사이트마다 파는 상품이 다릅니다. 자기 상품 20개만 파는 신규 브랜드라면 그
20개가 전역 순위 아래쪽에 몰려 **인기도 항이 전 후보에 비슷한 값을 줘 아무것도
구분하지 못합니다.**

그래서 서빙에서는 **그 사이트의 후보 집합 안에서 다시 0~1 로 폅니다.**
minmax 는 아핀 변환이라 이미 정규화된 값에 다시 걸어도 원본 log1p 에 건 것과
같습니다. 상품이 하나뿐이면 펼 수 없으므로 0 을 줍니다 — 후보가 하나면 인기도 항이
순위에 영향을 주지 않는 것이 맞습니다.

```python
Recommender(matrix, index, prior, catalog=[이 사이트가 파는 product_id])
```

`catalog` 를 주면 후보를 그 상품으로 제한하고 인기도를 그 안에서 다시 폅니다.
주지 않으면 지금까지와 완전히 동일하게 동작합니다 (평가·기존 배치 경로).
구현은 `batch/jobs/recommender.py` 의 `prior_in_catalog()` 입니다.

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

- ~~`backend/recommend/RankingService`~~ → `batch/serving/recommend_server.py` (파이썬 참조 구현, Jira 206). 백엔드는 프록시 예정 — 코사인·LTR 계산은 여기서
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
v_u⁺ = sum(w_k x decay(t_k) x v_i_k) / sum(w_k x decay(t_k))    전환한 상품 + 정독한 미전환
v_u⁻ = sum(w_k x decay(t_k) x v_i_k) / sum(w_k x decay(t_k))    얕게 본 미전환 + UI 좌절
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
| 5 | **전환한 상품은 `v_u⁺`. 미전환 상품은 관여도로 가른다** — `engagement >= 3.0` 이면 **약한 긍정**(전환 대비 0.6배), 미만이면 `v_u⁻` | 아래 5-1 참조 (2026-09-03 개정) |
| 6 | **UI 좌절**(`intent=friction`)은 전환 여부와 무관하게 항상 `v_u⁻` | `rage_click`, `dead_click` |
| 7 | **감점 대상 미전환 상품의 부정 강도는 관여도에 반비례한다** | 아래 참조 |

### 규칙 5-1 — 정독한 미전환 상품은 약한 긍정이다 (2026-09-03 개정)

> ⚠️ **확인 요청 — 백엔드 · 데이터 파트.** AI 파트가 측정 근거를 가지고 개정한
> 조항입니다. `batch/jobs/user_vector.py` 는 이미 이 규칙으로 돌고 있고 테스트
> 8건이 고정합니다. **출력 스키마와 필드는 바뀌지 않고 값만 바뀝니다** — Redis
> 스키마 변경도 백엔드 수정도 없으며, 배치를 다시 돌리면 반영됩니다.
> 이견이 있으면 알려주십시오.

```
engagement(i) >= ENGAGED_MIN  ->  v_u⁺ 에 w_i x ENGAGED_POS_W 로 넣는다
engagement(i) <  ENGAGED_MIN  ->  v_u⁻ (규칙 7 의 강도로 감점)

ENGAGED_MIN = 3.0 · ENGAGED_POS_W = 0.6
```

**왜 고쳤나.** 규칙 7 은 "오래 본 상품을 강하게 감점하면 자기 취향을 스스로
깎아내린다" 고 적어 놓고 **감점의 세기만 줄였지 부호는 그대로** 뒀습니다. 그
미완성이 동적 평가에서 드러났습니다 — 탐색이 쌓일수록 정확도가 내려갔습니다.

원인은 미전환 상품이 모이면 `v_u⁻` 가 **카탈로그 평균 방향**이 되는 것입니다.
정답도 대개 그 방향에 있어서 감점이 정답을 같이 밀어냅니다. 기획 원칙과도
어긋나 있었습니다 — 후보에서 뺄 때는 "안 산 것 ≠ 싫어한 것" 을 전제로 삼아 놓고
벡터에서는 통째로 감점하고 있었습니다.

**측정** — test 1,971명 · 최대 6 step · 강건성 6조건 (`batch/jobs/eval_dynamic.py`).
**아래 수치는 CBF 단독 기준입니다** (2026-09-03). CF 채택 후 값은 부록 S.

| 가정 | Final HR@10 (전 → 후) | 순위 개선 / 악화 (전 → 후) |
|---|---|---|
| default | 19.84% → **21.66%** | 38.3 / 53.8 → **48.1 / 45.8** |
| text_heavy | 21.21% → 21.61% | 43.0 / 51.4 → 48.6 / 45.3 |
| attr_heavy | 19.58% → 21.66% | 37.7 / 54.0 → 46.2 / 46.8 |
| flat | 20.29% → 22.58% | 37.4 / 54.3 → 47.3 / 45.6 |
| default · noise 1 | 20.09% → 22.78% | 38.4 / 54.2 → 49.3 / 44.2 |
| default · noise 2 | 20.14% → **23.49%** | 40.6 / 52.3 → 49.5 / 43.7 |

여섯 조건 중 다섯에서 **개선이 악화를 앞섭니다**. `noise 2` 에서는
Final 23.49% > Start 23.39% 로 부호가 넘어갑니다. target 의 중앙 순위도 전 조건에서
내려갑니다(57위 → 53~57위) — 고치기 전에는 57위 → 62~66위로 밀려났습니다.

**다른 축은 깎이지 않습니다.** 리뷰 순차 재생 test 22.53% → 22.68%,
valid 23.59% → 23.95%. 오프라인 대표 지표(23.39%)는 시드 벡터의 평균을 쓰므로
이 규칙을 타지 않습니다.

**임계값이 전부입니다.** 5.0 으로 올리면 걸리는 상품이 거의 없어 개정 전으로
돌아갑니다(−3.14%p). 배수는 0.3 / 0.6 / 1.0 이 −1.37 / −1.22 / −1.47%p 로 붙어 있어,
세기보다 **부호를 무엇으로 두느냐**가 전부입니다.

**규칙 5 자체를 되돌린 것이 아닙니다.** "미전환을 전부 `v_u⁺` 로" 는 여전히 나쁩니다
(아래 근거 표 5.9%). 관여도로 가르는 예외를 하나 판 것입니다.

**남은 한계.** 평균으로는 아직 Final < Start 입니다. 감점을 완전히 없앤 조건에서도
−1.37%p 가 남아, 남은 하락은 감점이 아니라 **긍정 축이 여러 상품의 평균이 되며
무뎌지는 구조** 때문으로 봅니다. 점수 식 수준의 다음 과제입니다.

> 재현: `Research/eval/eval_dynamic_why_declines_20260903.py` (원인 분해 · 임계·배수 스윕)

### 규칙 7 — 부정 강도는 관여도에 반비례한다

```
neg(i) = NEG_W0 / (1 + engagement(i) / NEG_TAU)      NEG_W0 = 1.0, NEG_TAU = 4.0
```

`engagement(i)` 는 그 상품에 쌓인 관여 점수입니다 — 양의 가중치 합에 **망설임·비교 이벤트의 절대값**을 더한 값입니다.

| 상황 | 관여도 | 부정 강도 |
|---|---:|---:|
| 즉시 이탈 (클릭만 하고 나감) | 1.0 | **0.80** |
| 얕게 보고 이탈 | 2.9 | 0.58 |
| ~~정독 후 이탈~~ | 5.0 | 규칙 5-1 로 **약한 긍정**이 됨 |
| ~~담았다 뺌~~ | 13.0 | 규칙 5-1 로 **약한 긍정**이 됨 |

> 2026-09-03 개정으로 이 표는 **관여도 3.0 미만 구간에만** 적용됩니다.
> 그 위는 규칙 5-1 이 약한 긍정으로 가져갑니다. `remove_from_cart` 로 전환이
> 취소된 상품도 관여도가 높아 대부분 긍정 쪽에 남습니다 — "구매 직전까지 갔다"
> 를 감점으로 읽지 않는다는 뜻입니다. 이 해석에 이견이 있으면 알려주십시오.

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

> **2026-09-03 개정(규칙 5-1)은 이 표를 뒤집지 않습니다.** "미전환을 전부 `v_u⁺` 로" 는 여전히 5.9% 로 나쁩니다. 개정은 미전환 **전체**가 아니라 관여도 3.0 이상 구간만 긍정으로 가져가는 예외입니다. 이 표를 개정 후 기준으로 다시 채우는 것은 남은 작업입니다.

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
      positive       : Set         긍정 가중이 붙은 product_id (2026-09-07 신설)
      viewed         : Set         접촉한 모든 product_id (converted 포함)
      n_products     : int         |viewed| (가중치 스케줄 판정용)
      updated_at     : timestamp
TTL   없음 (시뮬레이션 종료까지 유지)
```

**`seen` 을 두 집합으로 나눕니다.** 하드 제외와 소프트 강등은 다른 처리라 단일 집합으로 표현되지 않습니다. 기존 문서의 `seen` 은 `viewed` 에 해당하고, **추천 후보에서 실제로 빼는 것은 `converted` 뿐**입니다.

> ### ⚠ `positive` 를 `converted` 로 대신하면 안 됩니다 (2026-09-07)
>
> 학습 결합의 시드가 이 집합입니다. **전환한 상품만 쓰면 점수가 전환과 전환
> 사이에 한 발짝도 움직이지 않습니다** — 사용자가 아무리 둘러봐도 담기 전까지
> 추천이 그대로입니다.
>
> 동적 축에서 실제로 확인했습니다. **시작부터 못 맞힌 사람을 나중에 건지는
> 비율이 4.5% → 0.4%** 로 주저앉았습니다. `positive` 로 바꾸니 **9.7%** 로
> 선형(4.5%)을 두 배 넘겼습니다. "행동이 쌓일수록 좋아진다" 가 여기에 걸려
> 있습니다 (`evaluation-framework.md` 부록 T).
>
> `converted ⊆ positive ⊆ viewed` 입니다.

`converted ⊆ viewed` 입니다. `cart.add` 는 가중치 4.0 이라 `viewed` 에도 들어갑니다. 두 집합은 배타적이지 않습니다.

| 집합 | 등록 조건 | 추천에서의 처리 |
|---|---|---|
| `converted` | 위 "전환의 정의" 표에 해당하는 이벤트 발생 | **후보에서 완전히 제외** |
| **`positive`** | 집계 규칙을 통과해 **긍정 축 가중치가 양수**로 남은 상품 (전환 + 규칙 5-1 의 정독한 미전환) | **학습 결합의 시드** (§5) |
| `viewed` | `event_weight != 0` 인 이벤트가 1건이라도 발생 (감점 이벤트·`scroll_depth` 포함) | 후보에 남기되 **상한 2개** (§5) |
| (미등록) | `product.impression` 등 `event_weight = 0` 노출 | 두 집합 어디에도 넣지 않는다 |

소프트 강등이 실제로 적용되는 대상은 `converted` 를 먼저 제외한 뒤 남는 **`viewed \ converted`** 입니다. 상한 계산은 이 차집합에 대해 셉니다.

감점 이벤트만 발생한 상품도 `viewed` 에 들어갑니다. `rage_click` 이 찍혔다는 것은 그 상품을 봤다는 뜻이므로 노출 이력으로는 유효합니다.

### ⚠️ 구매 Event 도입 시의 개정안 (2026-09-04, 확인 요청 · Jira 112)

> **2026-09-07 진행 상황.** 프론트가 배너 이벤트와 **묶어서 한 번에 반영**하기로
> 했습니다. 가중치 제안을 프론트에 전달했습니다 (배너 2종 + 구매 3종, 2026-09-07).
>
> | 이벤트 | 제안 가중치 | 전환 |
> |---|---:|---|
> | `purchase` | **8.0** | ✅ `CONVERT` 에 넣음 |
> | `begin_checkout` | 5.0 | ❌ 시작만 하고 이탈이 있어 매출과 어긋남 |
> | `add_to_cart` | **4.0 → 3.0** | ✅ 그대로 (최강 자리를 `purchase` 에 내줌) |
> | `purchase_reason_select` | 0 | ❌ 선호가 아니라 이유 선언 |
> | `banner_click` | 1.5 | ❌ `recommendation_click` 과 같은 값 |
> | `banner_impression` | 0 | ❌ 클릭률 **분모** |
>
> **AI 쪽 `CONVERT` 는 이미 반영했습니다** (`user_vector.py`). `log.ts` 에 이벤트가
> 없어도 매칭이 안 될 뿐 안전하고, 반대로 로그가 먼저 오는데 비어 있으면 구매가
> 조용히 전환에서 빠집니다. **값은 측정이 아니라 제안이고, 첫 구매 로그 1,000건이
> 쌓이면 담기→구매 실제 전환율로 재조정합니다.**

계약이 `begin_checkout` · `purchase` · `purchase_reason_select` 를 활성 Event 로
올렸습니다(이벤트 39종). 결제 화면이 생기면 **위 표를 두 군데 고쳐야 합니다.**
AI 파트 제안이며 **백엔드·데이터·프론트 확인을 기다립니다.**

**① 깔때기는 최고 단계만 센다.** 구매 하나가 같은 상품에 이벤트 3건을 냅니다
(`add_to_cart` → `begin_checkout` → `purchase`). 누적하면 구매 상품이 담기만 한
상품의 **3.75배**(15 대 4)가 되는데, 그건 결제 단계를 몇 번 오갔는지가 선호도로
새어 드는 것입니다. **한 상품에 대해 도달한 최고 단계의 가중치만** 선호도 벡터에
넣습니다 — `section_dwell` 의 집계 규칙 A 와 같은 성격입니다.
**이벤트는 전부 전송합니다.** 1건만 세는 것은 벡터를 만들 때입니다.

**② `converted` 를 구매로 좁힌다.**

| | 지금 | 개정안 |
|---|---|---|
| `converted` (후보에서 완전 제외) | `add_to_cart` · `quantity_change` | **`purchase`** |
| `viewed` 상한 2개 (소프트 강등) | 나머지 | `add_to_cart` · `begin_checkout` · `quantity_change` 포함 |

담기를 후보에서 빼면 **담아 놓고 아직 안 산 사람에게 그 상품을 다시 못 보여줍니다.**
재고려 리마인드는 유효한 추천이고 상한 2개에서 포화한다는 실측이 이미 있습니다(§5).

> **재구매는 이 개정안에 포함되지 않습니다.** 구매한 상품을 영구 제외하면 `restock`
> 추천을 못 하는데, 카테고리별 소진 주기 데이터가 없습니다. 하드 제외로 두고
> **재구매 복귀는 별도 과제**로 남깁니다.

제안 가중치는 `purchase` 6.0 · `begin_checkout` 5.0 · `purchase_reason_select` 0
입니다. **구매 데이터가 0건이라 실측으로 정할 수 없는 잠정값**이고, `λ = 0.15` 와
같은 지위입니다 — 로그가 쌓이면 재측정합니다. 단일 출처는
`frontend/src/types/log.ts` 이므로 값 자체는 프론트가 넣습니다.

**출력 스키마와 Redis 필드는 바뀌지 않습니다.** 값만 바뀝니다.
전달 문서는 프론트에 직접 넘겼습니다 (개인 폴더 경로라 여기 적지 않습니다).

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

## 2-1. 언제 갱신하는가 — **실시간이어야 한다** (2026-09-07 신설)

지금까지 이 문서는 **누가 언제 Redis 를 갱신하는지**를 적지 않았다. 그래서
"Spark 가 마트를 만들 때 같이 넣겠지" 로 읽힐 수 있었는데, **그러면 실시간이
아니다.** 마이크로배치 주기만큼 늦는다.

### 갈래를 둘로 나눈다

```
행동  →  프론트 로거  →  POST /api/events  ─┬─→ Kafka → Spark → Mart   (분석·대시보드)
                                            │
                                            └─→ **Redis 사용자 벡터 즉시 갱신** (서빙)
```

**Kafka·Spark 파이프라인은 하나도 바뀌지 않는다.** 수집 API 가 Kafka 로 보내면서
Redis 도 같이 때리는 것뿐이다. 분석 축과 서빙 축은 목적이 달라 지연 요구도 다르다.

### 증분 갱신은 O(148) 한 줄이다

Redis 는 사용자당 누적합 두 개만 든다. 그래서 이벤트 하나가 오면 이렇게 끝난다.

```
u_sum += w x v_상품        # 148개 덧셈 (w = EVENT_WEIGHT)
w_sum += w                 # 1개 덧셈

v_u⁺ = u_sum / w_sum       # 읽을 때 나눈다
```

> **이것이 사용자 표현을 평균으로 유지한 이유다.** `max`/`top-k` 안을 기각할 때
> (`evaluation-framework.md` 부록 K) 정확도만 본 것이 아니다. 그 안을 쓰면
> **"그 사람이 반응한 상품 목록" 을 통째로 들고 있어야 하고 증분 갱신이 한 줄로
> 끝나지 않는다.** 평균은 실시간을 위한 선택이기도 했다.

집계 규칙(§2 규칙 1~7 · 5-1)은 그대로 적용한다 — 상품×섹션 1건, 정독한 미전환은
약한 긍정 등. **규칙을 서빙에서 다르게 적용하면 평가 수치와 어긋난다.**

### 프론트가 즉시 보내야 하는 이벤트

프론트 로거는 이벤트를 모아 배치로 보낸다. **전환 이벤트는 그러면 안 된다** —
담자마자 다음 추천에 반영되지 않는다.

| 이벤트 | 전송 |
|---|---|
| `add_to_cart` · `quantity_change` · `purchase` · `wishlist_toggle` | **즉시** |
| `remove_from_cart` | **즉시** (부정 축이 늦게 반영되면 뺀 상품이 계속 뜬다) |
| 나머지 (스크롤·체류·노출) | 지금처럼 배치 |

전환은 세션당 몇 건이라 즉시 보내도 트래픽에 영향이 없다.

### 남은 지연

| 구간 | 지금 | 실시간에서 |
|---|---|---|
| 행동 → 수집 API | 배치 버퍼 (수 초) | **전환만 즉시** |
| 수집 API → Redis | **없음** (Spark 경유였다) | **동기 갱신** |
| Redis → 추천 점수 | 요청 시 계산 | 그대로 |

### ⚠️ 아직 아무도 안 하고 있다

백엔드에 `RankingService` 가 없고, **Redis 사용자 벡터를 쓰는 주체도 없다.**
지금 사용자 벡터는 `batch/jobs/build_user_vectors.py` 가 배치로 만들어 파일로
낼 뿐이다. 이 절은 **만들 때 이렇게 만들라는 계약**이고 현재 구현 상태가 아니다.

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

## 4-1. Item Co-occurrence (CF 가점) — 2026-09-07 신설

### 입력

| | |
|---|---|
| 원본 | Sephora 리뷰 CSV (계약 §7.1.1 과 **같은 긍정 정의** — `rating >= 4` 또는 `is_recommended` 이고 `rating >= 3`) |
| 산출 | `batch/ingest/data/serving/item_cooc.npz` (200x200 float32 · 121KB) |
| 생성 | `batch/jobs/build_cooc.py` (`regenerate_all` 12단계) |

    S[i][j] = 동시발생(i, j) / sqrt(n_i x n_j)

**잠재 요인이 아니라 아이템-아이템**입니다. "이 상품을 산 사람이 저것도 샀다" 로
설명되므로 `breakdown` 에 항을 하나 더할 수 있습니다.

### ⚠️ 누출 차단이 이 산출물의 전제입니다

CF 는 "이 상품을 산 사람이 다음에 뭘 샀나" 를 씁니다. **평가 대상이 그 통계에
들어가면 정답을 보고 정답을 맞히는 것**이 됩니다.

`simulator/personas/data/personas_*.json` 의 `author_id` 를 **전부** 뺍니다 —
PC 9,900 · PA 100 · 홀드아웃까지 **14,000명**. 파일이 늘 때마다 손대지 않도록
디렉터리를 훑습니다.

> **페르소나 파일이 늘면 이 산출물을 반드시 다시 만들어야 합니다.** 새 홀드아웃이
> 동시발생에 남아 있으면 그것으로 잰 수치가 전부 거짓이 됩니다.

현재: 리뷰 1,094,411행 · 긍정 리뷰어 245,218명 · **동시발생 기여 51,269명** ·
0 이 아닌 쌍 16,789개 · 상품당 지지자 중앙 **1,225명**.

### 처리 — **가점 전용이어야 합니다**

    score += β x (cf / cf 최대)       이력이 없으면 **중앙값**을 준다

두 점수를 minmax 로 정규화해 섞으면 CF 이력이 없는 상품이 **0점(최하위)** 을 받아
신규 등록 상품을 밑바닥으로 밉니다.

| 정답이 신규 등록 상품일 때 | Recall@10 |
|---|---:|
| CBF 단독 (CF 안 씀) | 24.15% |
| **가점 전용 + 중립 가점** | **18.20%** |
| minmax 혼합 (α=0.7) | **1.55%** |

**중립 가점** — 이력이 없는 상품에 0 대신 중앙값을 줍니다. 0 은 "아무도 안 샀다"
가 아니라 "모른다" 인데, 0 을 주면 모르는 것을 나쁜 것으로 취급합니다.

> **중앙값은 이력이 있는 상품끼리 잽니다.** 후보 전체에서 재면 이력 없는 상품이
> 많을 때 중앙값이 0 이 되어 중립 가점이 무력화됩니다 — **신규 브랜드가 대부분인
> 플랫폼 초기가 정확히 그 상태**라 필요한 순간에 안 듣습니다.

### 임계점 — 지지자 3명

지지자(그 상품을 긍정 평가한 사람 중 **다른 상품도 산** 사람)가 3명 미만이면
가점을 막습니다. 0명 구간에서 CF 를 얹으면 **−0.46%p 손해**입니다 — 데이터가
거의 없을 때의 CF 값은 노이즈이고 가점 전용이어도 순위를 흔듭니다.

| 지지자 | 무엇을 쓰나 |
|---|---|
| 0~2명 | **CBF 단독.** 전용 칸으로 노출만 준다 |
| 3~30명 | **CBF + CF 가점** — 혼합이 CF 단독보다 3~5%p 앞선다 |
| 60명~ | CF 비중 상향 |

### 파라미터

| 이름 | 값 | 위치 |
|---|---:|---|
| `CF_BETA` | 1.0 | `batch/jobs/recommender.py` |
| `CF_MIN_SUPPORT` | 3 | 〃 |

**`cooc` 를 안 주면 항이 통째로 꺼져 기존과 한 자리도 다르지 않습니다.**
기본 동작은 변하지 않습니다.

### 소비처

`Recommender(cooc=..., supporters=...)`. 백엔드 `RankingService` 가 생기면
`item_cooc.npz` 를 메모리에 올려 같은 식을 씁니다 (200x200 이라 121KB).

> 근거: `docs/ai/evaluation-framework.md` 부록 N·O·P. 검증:
> `batch/jobs/test_cf_bonus.py` 6건.

## 4-2. Learning to Rank 모델 — 2026-09-07 채택

점수 결합을 사람이 정한 선형 합에서 **학습**으로 바꿉니다. §5 처리의 **4단계
하나만** 대체하고 나머지는 건드리지 않습니다.

### 왜 바꿨나

선형 합은 **조건부 규칙을 표현할 수 없습니다.** "브랜드 안에서만 보면 가격이
보인다" 를 찾아 놓고도(부록 M) `+ w_p x 가격근접` 으로 더하니 브랜드와 무관하게
항상 더해져 train 에서조차 CI 가 0 을 못 넘었습니다. 트리는 "같은 브랜드인가" 로
먼저 가르고 그 안에서 가격을 봅니다.

### 산출물

| 파일 | 크기 | 내용 |
|---|---:|---|
| `batch/ingest/data/serving/ltr_model.pkl` | 약 1.0MB | sklearn `HistGradientBoostingClassifier`, 트리 278개 |
| `batch/ingest/data/serving/ltr_model_meta.json` | — | 피처 이름 19개 · 학습 조건 · 순열 중요도 |

**학습은 `eval_metadata` 의 `train` 분할 5,954명에서만** 합니다. valid·test·홀드아웃은
한 명도 들어가지 않습니다. 재현: `python batch/jobs/train_ltr.py`

### 피처 19개

구현은 `batch/jobs/ltr_features.py` 하나입니다 — **학습과 서빙이 같은 코드를
씁니다.** 따로 구현하면 에러 없이 순위만 조금씩 틀립니다.

| # | 피처 | 설명 |
|---|---|---|
| 0 | `cos_all` | 전체 코사인 (시드 평균 벡터 대비) |
| 1 | `affinity` | 속성 친화도 (§3) |
| 2 | `prior` | 인기도 (§4) |
| 3 | `cf` | CF 점수 — **후보 안에서** 정규화 (§4-1) |
| 4 | `supporters` | 그 상품 지지자 수 `log1p/10` |
| 5 | `same_brand` | 시드 브랜드와 같은가 |
| 6 | `price_prox` | 시드 가격 중앙값과 가까운가 (log2 거리) |
| 7 | `n_seed` | 시드 개수 `/10` |
| 8 | `pop_rank` | 인기 순위 0~1 |
| **9** | **`cf_rank`** | **후보 안에서 CF 를 정렬한 등수 0~1** |
| 10~18 | `cos_{블록}` | 블록별 코사인 9개 (어휘집 `ORDER` 순서 그대로) |

**9번이 가장 중요한 피처입니다.**

| 피처 | 순열 중요도 |
|---|---:|
| **`cf_rank`** | **0.2394** |
| `pop_rank` | 0.1124 |
| `prior` | 0.1050 |
| `cos_all` | 0.0807 |
| `supporters` | 0.0783 |
| … | |
| `cos_brand` | 0.0104 |
| `same_brand` | 0.0034 |

CF 점수의 **절대값이 아니라 후보 중 몇 등인가**입니다. 사람마다 CF 점수 분포가
달라 원값은 서로 비교가 안 되고 순위는 같은 척도가 됩니다.

**브랜드 계열이 최하위입니다.** CBF 에서 브랜드 블록이 정확도에 가장 크게
기여하던 것(빼면 23.6% → 11.4%)과 정반대이고, LTR 이 브랜드 쏠림을 푸는 것과
맞아떨어집니다 (최다 브랜드 4.43 → 2.62칸).

### ⚠ 증강이 없으면 신규 상품이 영영 안 뜹니다

학습 카탈로그에는 **CF 이력이 없는 상품이 하나도 없습니다.** 모델이 "이력 없음" 을
본 적이 없으니 그런 상품이 오면 분포 밖이라 일괄 바닥을 줍니다.

그래서 학습 행의 **25%** 를 "오늘 등록된 상품" 모양으로 지워 덧붙입니다
(`cf = 0` · `cf_rank = 꼴찌` · `supporters = 0` · `cos_brand = 0`).

카탈로그의 10% 를 신규로 만들고 재면 이렇습니다 (holdout_a 2,000명).

| 구성 | 전체 Recall@10 | 신규 상품이 차지한 칸 비율 |
|---|---:|---:|
| 선형 (CBF + CF) | 32.45% | **0.46%** |
| **학습 결합 (LTR)** | **38.55%** | **5.73%** |

카탈로그 비중이 10% 이므로 5.73% 는 여전히 과소 노출이지만, 선형의 0.46% 와는
자릿수가 다릅니다. **정확도와 신규 노출이 같이 오릅니다.**

### ⚠ 후보 집합에 의존하는 피처가 둘입니다

`cf` 와 `cf_rank` 는 **후보 안에서** 계산해야 합니다. 사이트가 자기 상품만 판다면
그 안에서 다시 매깁니다. 후보 밖까지 넣어 등수를 매기면 **에러가 안 나고 순위만
틀립니다.**

### 검증

`batch/ingest/data/serving/ranking_golden.json` 이 **LTR 기준으로** 만들어집니다. 파일이 `scorer`
필드로 무엇으로 만들어졌는지 말합니다.

> **골든은 내보낸 정밀도로 계산합니다.** `product_feature.jsonl` 은 벡터를 소수
> 6자리로 반올림해 내보내고 자바가 읽는 것은 그 값입니다. 선형에서는 차이가
> 묻혔지만 **트리는 피처가 분기점 근처에 놓이면 잎이 통째로 갈립니다** — 실제로
> 한 페르소나에서 두 상품의 순서가 뒤집혔습니다. 정본 정밀도로 골든을 만들면
> 자바는 그것을 **영원히 재현할 수 없습니다.**

### 성능

| 결합 | 1건당 | 한 코어 처리량 | 조건 |
|---|---:|---:|---|
| 선형 (CBF + CF) | **0.29 ms** | 약 3,500건/s | 시드 3~4개 · 1,000명 |
| 학습 결합 (LTR) | **4.10 ms** | 약 244건/s | 같은 조건 |
| 학습 결합 (LTR) | **7.24 ms** | 약 138건/s | **실제 이벤트 이력** 400명 |

후보 200개 전부 채점 + MMR 포함, 파이썬 단일 코어. **14~25배 느리지만 절대값이
작습니다.** Top 10 만 뽑든 200개를 다 정렬하든 어차피 200개를 전부 채점하므로
목록 정렬용으로 200개를 달라고 해도 추가 비용이 없습니다.

> ⚠ **작은 표본으로 재면 안 됩니다.** sklearn 부스팅 트리는 첫 호출이 비쌉니다 —
> 30명으로 재면 1건당 48ms 가 나오는데 400명이면 7.2ms 입니다. 워밍업을 분모에서
> 빼거나 표본을 충분히 잡으십시오.
>
> 두 번째와 세 번째 줄의 차이는 **시드 개수**입니다. 실제 이벤트 이력이 쌓인
> 사용자는 `positive` 집합이 커서 피처 계산이 무거워집니다.

### 잃는 것 — `breakdown` 항별 분해

응답의 `breakdown`(코사인이 얼마, 친화도가 얼마 기여했나)이 사라집니다. 그 자리는
**피처 중요도**로 대신합니다. **블록 가중치(브랜드 0.60 등)는 그대로 남습니다** —
상품 인코딩도 배너 축 문구도 안 바뀝니다.

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
                  &banner_slots=6&reserved=2&axes=concern,segment
```

| 파라미터 | 기본 | 뜻 |
|---|---:|---|
| `persona_id` | — | **선택** (2026-09-09, Jira 214). **운영 합의 (2026-09-10, 백엔드·AI): 추천은 로그인 회원에게만 낸다. 비로그인 사용자는 추천을 받지 않고(백엔드 프록시가 이 API 를 부르지 않음), 행동 로그 `POST /api/events`·수집기 이벤트는 비로그인도 보낸다. 비로그인은 상세 페이지 열람까지만 가능하고 좋아요·장바구니·주문은 로그인 필요(기획 §15-11).** 아래 익명 cold_start 는 서버 능력으로 남겨 두는 것이고 화면 정책이 아니다. 없으면 **익명 cold_start** — 상태·속성 친화도 없이 인기 prior + MMR. 페르소나 표에 **없는 값**(실회원 `accountId`)도 받는다: 속성 친화도만 빠지고, `POST /api/events` 로 쌓인 행동으로 개인화된다. **404 는 내지 않는다** — 백엔드 프록시가 회원↔페르소나 매핑 없이 호출할 수 있게 |
| `size` | 10 | 메인 목록 칸 수 |
| `banner_slots` | 0 | 배너 칸 수 (최대 12). 0 이면 `hero`·`banners` 를 안 내린다. **> 0 이면 `reserved` 전용 칸이 배너 뒤 칸으로 가고 `items` 는 순수 순위** (프론트 확정 2026-09-09, Jira 218) |
| `reserved` | 2 | **신규·저노출 브랜드 전용** 칸 수 (§5-1). **자리 확정 (2026-09-09): `banner_slots > 0` 이면 배너 뒤 칸, 아니면 메인 안.** 이전 메모 — 구현·측정은 메인 `size` 칸 **안**에 두는 형태(`Recommender.rank(reserved=)`, 부록 U)이고, 배너 칸에 두는 형태는 재지 않았다. 확정 전까지 메인 안으로 읽는다. 신규 상품(지지자 <3 또는 어휘집 밖 브랜드)이 카탈로그에 **없으면 칸은 일반 순위로 채워지고** 응답 `reserved_filled` 가 0 이다 — 원천 200개는 그 상태. **등록 상품**(§5-2, Jira 216)이 들어오면 채워진다. 시연용 자사 브랜드 **SSAFY Beauty 8개**는 시작 시 이미 편입돼 있어 `reserved=2` 면 칸 9·10 이 SSAFY 상품이다 |
| `axes` | `concern,segment` | 축 배너 순환 순서. `concern · ingredient · clean · price_bin · category · segment` 중 쉼표 구분, 그 외 값은 **422** `INVALID_AXES`. 축 칸(`banner_slots − reserved`)을 이 순서로 돌며 채운다 |
| `hero` | `top` | **히어로 정책 (2026-09-10, Jira 237).** `top` = `items[0]` 에 축 문구(원안). `new_brand` = 신규 상품(지지자 <3 또는 어휘집 밖 브랜드) 중 이 사용자 점수가 가장 높은 것을 히어로로 — 배너 행이 화면에서 빠져(09-10 기획 검토) 전용 칸이 사라진 상태에서 신규 브랜드가 배너에 나올 자리가 히어로뿐이라서. 기획 §15-10 "배너에 신규 포함" 은 **포함으로 결정(09-10)**. 전환·비활성 제외, 신규가 없으면 `top` 으로 돌아가며 응답 `hero_policy` 가 실제 적용값이다. 히어로 상품은 `banners` 와 겹치지 않는다. `items` 는 정책과 무관(순위 불변). 그 외 값은 **422** `INVALID_HERO`. 배너 행이 살아나면 `top` 으로 돌린다 |

> **한 응답에 같이 싣는 이유** — 메인·히어로·배너가 **같은 점수에서 나오고 서로
> 중복을 배제해야** 합니다. 엔드포인트를 나누면 같은 상품이 두 자리에 뜨거나
> 중복 제거를 소비자가 하게 됩니다. 히어로 1 + 배너 6 + 메인 10 = 한 화면에
> **17개**라 이게 특히 중요합니다.

### 처리

```
1. Redis에서 (positive_*, negative_*, n_products, converted, positive, viewed) 조회
2. (선형일 때만) n_products로 가중치 스케줄 결정
3. (선형일 때만) v_u⁺ = positive_u_sum / positive_w_sum   (positive_w_sum = 0이면 생략)
                 v_u⁻ = negative_u_sum / negative_w_sum   (negative_w_sum = 0이면 생략)
4. scores = **학습 결합 모델 추론**                        ← 2026-09-07 채택 (§4-2)
             X = 피처 19개 x 후보 200개  (positive 집합이 시드)
             scores = model.predict_proba(X)[:, 1]
5. 노출 정책 적용 (아래)
6. MMR 다양성 보정 (λ_mmr = 0.8, 후보 풀 상위 30개 — λ_mmr 은 점수 쪽 계수라 클수록 약하게 걸리고 1.0 이면 끈 것과 같음)
   → **(size − reserved) 개**를 고른다
6-1. **신규 상품 전용 칸** (§5-1, 2026-09-08 구현) — 신규 상품 중 점수순으로 `reserved` 개를
   뒤에 붙인다. 신규 = 지지자 < 3명 **또는** 어휘집 밖 브랜드. 신규가 모자라면 남은 자리를
   일반 후보 점수순으로 채운다 (칸이 비지 않는다). `Recommender.pick()`
7. 상위 size개 반환 — 전용 칸으로 들어온 항목은 `reserved: true`
```

> **참조 구현 (2026-09-08, Jira 206) — `batch/serving/recommend_server.py`** (FastAPI).
> 위 1~7 을 파이썬으로 그대로 돈다. 백엔드 `RankingService` 는 아직 없으므로 **백엔드가
> 이 서버를 프록시하는 형태**를 권한다 — 모델이 sklearn pickle 이고 피처 19개를 자바로 다시
> 짜면 순위가 조용히 어긋난다. ONNX 로 가더라도 이 서버가 대조 기준이다.
>
> | | |
> |---|---|
> | 실행 | `python batch/serving/recommend_server.py` (포트 8300) · `GET /health` |
> | 요청 | `GET /api/recommend?persona_id=&size=10&reserved=0` (+ `seed=review` — 리뷰 시드를 상태로 쓰는 **시연용**, 응답 `state_source: review_seed`) |
> | 상태 | 메모리 (Redis 자리). `POST /api/events {persona_id, events[]}` 로 쌓는다. 이력 없으면 `state_source: cold_start` |
> | 응답 추가 필드 | `state_source` · `scorer` (`ltr`/`linear`) · `latency_ms` · `items[].brand_name` · `items[].position` · `items[].reason` (아래) · 선형 폴백일 때만 `weights` |
> | **유입 추적 식별자** (2026-09-08, Jira 209) | 응답마다 `recommendation_id`(uuid) · `list_id`(`"main"`) · `algorithm`(예 `ltr-278t-2026-09-07`, 모델이 바뀌면 문자열이 바뀐다). **FE 는 이 값을 `recommendation_impression` · `recommendation_click` · `product_view` 에 그대로 싣는다** (`event-properties-schema.md` 의 `recommendation_id` · `list_id` · `position` · `algorithm`). 이게 있어야 추천 CTR(`recommendation_daily_kpi`)과 **교차 브랜드 유입의 "추천 경유"** 를 닫을 수 있다 (마트는 데이터 파트, 요청서 별도 전달) |
> | **`reason`** | `breakdown` 대체. 항별 기여가 아니라 **그 상품에 실제로 있던 신호**만 문장으로: `cf` "회원님이 담은 상품을 고른 사람들이 함께 고른 상품" · `content` "본 상품과 성분·고민 구성이 비슷" (cos ≥ 0.5) · `attribute` "{skin_type} 피부 사용자 사이에서 반응이 좋은" (친화도 상위 20%) · `new_brand` (전용 칸) · 아무것도 없으면 `popular`. **프론트 확정 대기** — §7 |
> | **응답 시간 (실측)** | holdout_a 300명 · seed=review · reserved=2 · LTR: **점수 계산 p50 7.0ms / p95 8.9ms**, **HTTP 왕복+reason p50 12.3ms / p95 15.2ms** (파이썬 단일 프로세스, 워밍업 후). `batch/serving/bench_recommend.py` |
> | 안 한 것 | `banner_slots` / `axes` (배너, §5-1) — 전용 칸 자리 확정 뒤. Redis 연결. 인증 |
> | 테스트 | `python -m unittest batch/serving/test_recommend_server.py` — 계약 필드·전환 제외·콜드 스타트·404·reserved 상한 |

> **4단계만 바뀌었습니다.** 1·2·3·5·6·7 단계와 Redis 스키마·실시간 증분 갱신
> (§2-1)·노출 정책·MMR·배너(§5-1)는 그대로입니다.
>
> **선형 결합은 폴백으로 남깁니다.** 모델 산출물(`ltr_model.pkl`)이 없으면 아래
> 식으로 돕니다. 구현할 때 4단계만 갈아 끼울 수 있는 모양으로 두십시오.
>
> ```
> 4'. scores = w1 x (V @ v_u⁺) − λ x (V @ v_u⁻) + w2 x attr_affinity + w3 x prior
>              + w_b x brand_unknown(전환 상품의 브랜드, 어휘집)
>              + β x cf_bonus(positive 집합, 동시발생)          ← §4-1
> ```

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
| **이 표 기준 (test 1,971명 · CBF 단독)** | **23.39%** | 31.29% | 기준 |
| 이전 스케줄 | 22.43% | 30.91% | −0.96%p CI [−1.50, −0.36] |
| 속성 항 제거(w2=0) | 22.58% | 30.91% | −0.81%p CI [−1.52, −0.02] |

**고친 것은 6개 이상 구간 하나입니다.** 1~5개 구간(0.70 / 0.25 / 0.05)은 측정으로 뒷받침된 값이라 그대로 둡니다 — 함께 손대면 시드 1~2개 구간이 26.24% → 25.38% 로 손해를 봅니다.

속성 항은 정확도를 올리는 장치가 아니라 **롱테일 보험**입니다 — 빼면 전체보다 롱테일이 더 크게 떨어집니다(30.86% → 29.48%). 속성 항의 몫을 인기도로 옮기는 안은 −2.24%p 로 명확히 나빠 채택하지 않았습니다. 측정 스크립트는 `batch/jobs/eval_persona_feature.py`, 배경은 `docs/ai/persona-feature-port.md` §7.

### 응답

```json
{
  "persona_id": "PC00001",
  "persona_known": true,
  "n_products": 3,
  "recommendation_id": "3f9c1e2a7b4d4c0e9a1b2c3d4e5f6071",
  "list_id": "main",
  "algorithm": "ltr-278t-2026-09-07",
  "state_source": "events",
  "reserved_filled": 0,
  "weights": { "cosine": 0.60, "attr": 0.35, "prior": 0.05 },
  "items": [
    {
      "product_id": "P420652",
      "product_name": "Lip Sleeping Mask Intense Hydration with Vitamin C",
      "score": 0.7231,
      "position": 1,
      "reserved": false,
      "product_source": "seed_catalog",
      "breakdown": {
        "_note": "선형 폴백일 때만. 현행(LTR, §4-2)에서는 이 객체가 없다 — 대체 형태는 §7 미확정",
        "cosine": 0.6120,
        "attr_affinity": 0.4710,
        "prior": 1.0000,
        "cf": 0.8320
      },
      "reason": {
        "attribute": "지성 피부 사용자가 평균보다 2.6배 많이 선택",
        "content": "회원님이 본 클렌저와 성분 구성이 유사",
        "cf": "회원님이 담은 상품을 고른 사람들이 같이 고른 상품"
      }
    }
  ],

  "banner_slots": 6, "axes": ["concern", "segment"], "banner_list_id": "banner_row",
  "hero_policy": "top",
  "hero": {
    "product_id": "P420652",
    "banner_type": "concern",
    "banner_value": "Pores",
    "trait_source": "session",
    "hero_policy": "top"
  },
  // hero=new_brand 이면 hero 에 reserved:true · product_name · brand_name · score · reason · product_source 가 더 실린다
  // (items 밖 상품이라 프론트가 이름·가격을 items 에서 못 찾는다)
  "banners": [
    { "banner_slot": 1, "banner_type": "concern",   "banner_value": "Pores",
      "product_id": "P310022", "product_name": "…", "brand_name": "…", "score": 0.7112,
      "reserved": false, "trait_source": "session", "reason": { "cf": "…" }, "product_source": "seed_catalog" },
    { "banner_slot": 2, "banner_type": "segment",   "banner_value": "oily",
      "product_id": "P448821", "product_name": "…", "brand_name": "…", "score": 0.6640,
      "reserved": false, "trait_source": "profile", "reason": { "attribute": "…" }, "product_source": "seed_catalog" },
    { "banner_slot": 5, "banner_type": "new_brand", "banner_value": null,
      "product_id": "SB000001", "product_name": "…", "brand_name": "SSAFY Beauty", "score": 0.3104,
      "reserved": true, "trait_source": "session", "reason": { "attribute": "…" }, "product_source": "brand_registered" },
    { "banner_slot": 6, "banner_type": "new_brand", "banner_value": null,
      "product_id": "SB000002", "product_name": "…", "brand_name": "SSAFY Beauty", "score": 0.2988,
      "reserved": true, "trait_source": "session", "reason": { "new_brand": "…" }, "product_source": "brand_registered" }
  ]
}
```

## 5-2. 상품 등록 → 즉시 편입 (2026-09-09 신설 · Jira 216)

실서비스 흐름: **판매자 등록 → 쇼핑몰 백엔드 승인 → `POST /api/products` → 다음 추천 요청부터 후보.**
추천 서버가 상품을 자기 카탈로그에 갖고 있어야 점수를 낼 수 있으므로, 백엔드는 상품 승인 시
이 호출을 한 번 한다. 배치 재생성이 아니라 **요청 하나로 즉시** 들어간다 (208개 기준 재조립 수 ms).

### 요청

```
POST /api/products            body = 등록 입력 1건 또는 배열 (product-registration-spec §3 필드)
{
  "product_id": "SB000001",             // 없으면 서버가 발급 (R…)
  "product_name": "…", "brand_name": "SSAFY Beauty", "brand_id": "…",
  "secondary_category": "Treatments", "tertiary_category": "Exfoliators",
  "highlights": ["Pores", "Without Parabens"],
  "ingredients": "Water, Lactic Acid, …",       // 문자열 또는 문자열 배열
  "price_krw": 30800                            // 또는 price_usd
}
```

| 단계 | 규칙 | 근거 |
|---|---|---|
| 파생 | `price_krw` → `price_usd` **고정 환율 1,400** · `rating` 카테고리 중앙값 주입(`rating_source=injected`) · `loves_count=0` | product-registration-spec §4 |
| 검사 | `contracts/validate_product_registration.py` 의 `check()` 그대로. 위반이면 **422** `REGISTRATION_CONTRACT_VIOLATION` + 위반 목록, **한 건이라도 위반이면 배열 전체 거절** | 등록 폼과 같은 기준 |
| 인코딩 | 어휘집(`product-feature-vocab.json`)으로 148차원. 어휘집 밖 브랜드는 brand 블록 0 벡터 | product-feature-spec |
| 편입 | 콘텐츠 벡터·prior(0)·속성 친화도(중립 0.5)·CF 동시발생(0 행·열)·지지자(0) 를 한 행씩 늘리고 Recommender·LTR 피처를 재조립 | — |
| 영속 | `batch/ingest/data/serving/registered_products.jsonl` 에 파생값까지 append. 재시작 시 다시 읽음. 같은 `product_id` 재등록은 **그 행을 갈아 끼움**(`action: replaced`) | Redis/DB 자리 |

### 응답 (201)

```json
{ "registered": [ { "product_id": "SB000001", "brand_name": "SSAFY Beauty", "position_in_catalog": 200,
                    "price_usd": 22.0, "rating": 4.461, "rating_source": "injected",
                    "brand_in_vocab": false, "reserved_candidate": true, "action": "added", "warnings": [] } ],
  "products": 208, "registered_products": 8 }
```

`GET /api/products/{product_id}` 는 `product_source · supporters · reserved_candidate · active` 를 돌려준다.
`/health` 에 `seed_products · registered_products · inactive_products` 가 추가됐다.

### 판매 중단 · 삭제 (Jira 219)

`DELETE /api/products/{product_id}` — 추천 후보에서 **즉시** 빠진다 (메인·배너·hero 모두). 백엔드가 상품을
INACTIVE 로 바꾸거나 삭제할 때 한 번 부른다. 벡터·행은 지우지 않고 점수만 막으므로 **나머지 상품 순위는 그대로**다.
기록은 `registered_products.jsonl` 에 `{"product_id", "_op": "deactivate", "at"}` 행으로 남아 재시작 후에도 유지되고,
같은 id 를 다시 `POST /api/products` 하면 재활성된다. 원천 200개도 중단할 수 있다. 없는 id 는 404.

### 쇼핑몰 백엔드 카탈로그 동기화 (Jira 222)

승인 훅(요청서 4-1)이 없어도 카탈로그가 어긋나지 않게, 추천 서버가 **백엔드 공개 API** 를 읽어 맞춘다.
`POST /api/catalog/sync?source=http://shop-backend:8090` (수동) 또는 `SHOP_BACKEND_URL` + `CATALOG_SYNC_INTERVAL_SEC`(기본 300) 로 주기 실행.

| 단계 | 규칙 |
|---|---|
| 읽기 | `GET /api/products` (ACTIVE 요약) → 새 상품·요약이 바뀐 상품만 `GET /api/products/{id}` 로 전성분을 받는다 |
| 매핑 | `productId·productName·brandName(없으면 brandId)·secondaryCategory·tertiaryCategory·highlights·ingredients·priceKrw` → 등록 입력. **rating 은 넘기지 않는다** — 백엔드 값도 중앙값 주입이라 우리 §4.2 로 다시 주입해 기준을 하나로 |
| 편입 | `POST /api/products` 와 같은 경로(§4 파생·검사·인코딩). 기록에 `sync_source=shop_backend`·`sync_hash` 를 남겨 바뀐 것만 다시 인코딩 |
| 중단 | 이전 동기화로 들어온 상품이 ACTIVE 목록에서 빠지면 `deactivate`. 시연 시드(SSAFY Beauty, sync_source 없음)는 건드리지 않는다 |
| 실패 | 백엔드에 못 붙으면 `error` 를 채워 200 — 추천은 영향 없음. 상품 하나가 계약 위반이면 `rejected[id]` 에만 남고 나머지는 진행 |

응답·`/health.catalog_sync.last`: `listed · added · replaced · unchanged · deactivated · rejected · ms`. 훅과 동기화가 같이 돌아도 같은 id 는 갈아 끼우기라 충돌이 없다.

### 실시간 행동 유입 — Kafka 구독 (Jira 226)

실서비스에서 `POST /api/events` 를 부르는 주체가 없었다 — 실제 소비자 상태가 쌓이지 않아 모두 cold_start 에 머물렀다.
추천 서버가 **Kafka `activity-events` 를 Spark 와 다른 consumer group(`recommend-state-v1`)으로 구독**해 같은 `observe` 로 넘긴다.
Spark 정본을 우회하는 것이 아니라 Spark 가 맡지 않는 시간 단위(초)를 맡는다. 지연은 보통 1초 안.

| 항목 | 값 | 이유 |
|---|---|---|
| 켜는 조건 | `KAFKA_BOOTSTRAP_SERVERS` 있을 때만 | 없으면 지금과 같다 (로컬 개발 영향 없음). Spark 스트리밍→Delta 경로로 바꿀 때 이 어댑터만 교체 |
| commit | `enable.auto.commit=false`, **상태 반영 + 세션 로그 기록 뒤** commit | 처리 전에 commit 되면 재기동 때 이벤트를 잃는다 |
| 재기동 | committed offset 부터 이어 읽음. `auto.offset.reset=latest` 는 group 에 offset 이 없는 첫 기동에만 | "최신부터" 는 첫 기동의 선택일 뿐이다 |
| 중복 | `event_id` LRU 20만 건 | 계약상 같은 event_id 가 Kafka 에 여러 번 올 수 있다(Processed 에서 제거). 우리는 그 전 단계를 읽는다 |
| 검사 | `schema_version` 앞자리 · `persona_id·event_name·event_id` 필수 · 상태 이벤트만 | 수집 서버가 계약 검증을 이미 했다. 여기서는 최소만 |
| 관측 | `/health.kafka_state`: `alive · connected · lag · last_processed_at · processed · duplicates · filtered · invalid · last_error` | 스레드는 장애 경계가 아니다 — consumer 가 죽어도 API 는 산다. 그래서 상태를 드러낸다 |
| 제한 | **단일 replica.** Kafka key 가 `session_id` 라 같은 persona 가 여러 파티션에 흩어진다 | 소비자를 여러 대 두면 상태가 갈린다. 확장은 별도 `recommend-state-updater` → Redis (운영 단계) |

**배포 전 검증(데이터 팀 요구):** 2,000 TPS 에서 lag 증가율 · API p95/p99 · 재시작·중복·rebalance·Kafka 단절. 로컬에 Kafka 가 없어 가짜 consumer 로 로직만 검증했고, 실측은 EC2 또는 데이터 로컬 Kafka 에서 한다.

### 세션 상태 영속화 (Jira 224)

`POST /api/events` 로 받은 이벤트 중 **상태를 바꾸는 것**(behavior_weights 에 가중치가 있는 이름·section_dwell·scroll_depth·전환·되돌림)만
`session_events.jsonl` 에 append 하고, 기동 때 순서대로 다시 `observe` 한다 — 스냅샷이 아니라 **이벤트 로그 + 재생**이라
UserVector 규칙이 바뀌어도 재생하면 새 규칙으로 상태가 만들어진다. 재시작 뒤 `state_source=events` 가 그대로 남는다.
`/health.sessions` 에 재생 페르소나·이벤트 수·ms. 파일이 자라면 `POST /api/sessions/compact?keep_last=500` 으로 페르소나별 마지막 N건만 남긴다.
**워커 1개 전제는 그대로**다 — 프로세스가 여럿이면 서로의 append 를 못 본다. 확장은 Redis Streams 로 같은 모양(append → replay)으로 옮긴다.

### 배포 (Jira 219)

`deploy/recommend.Dockerfile` + `deploy/ec2-1/docker-compose.yml` 의 `recommend` 서비스 (8300, 내부 전용, `/data` 볼륨에 등록 상품).
백엔드는 `RECOMMEND_URL=http://recommend:8300` 으로 프록시한다. `WORKERS=1` — 사용자 상태·등록 상품이 프로세스 메모리라
워커를 늘리면 답이 갈린다 (확장은 Redis 뒤). 자세한 절차는 `deploy/ec2-1/README.md`.

### 기존 순위는 보존된다 — 순위 피처 분모 고정

LTR 피처 `pop_rank`·`cf_rank` 는 순위/카탈로그 크기다. 카탈로그가 200→208 이 되면 기존 상품 값이
r/200 → r/208 로 흔들리고, **그것만으로 트리 모델이 순위를 뒤집었다** (PC00001 2위 상품 0.257 → 0.142).
그래서 서빙은 분모를 **원천 카탈로그 크기(200)로 고정**한다 (`LtrFeatures(n_ref=)`). 등록 상품은 리뷰 0·CF 0 이라
맨 뒤에 서고 1.0 에서 잘린다. 검증: 등록 전후 원천 200개 피처가 bit 단위로 같고(`test_catalog_registry`),
`reserved=0` 응답이 214 서버와 동일.

### 등록 상품이 일반 칸에 오는 조건

신호가 없으면(행동 0·CF 0·prior 0) 일반 칸에는 **오지 않는다** — 전용 칸이 유일한 노출이다. 이것이 §5-1 의
설계다. 사용자가 등록 상품을 한 번 담으면 그 사용자에게는 같은 브랜드 상품이 일반 칸으로 올라온다.

> **측정 결과 (2026-09-09, Jira 217 · `batch/jobs/eval_registered_brand_share.py`, holdout_a 300명):**
> "10칸 중 7칸" 은 **페르소나 없는 사용자 + 전용 칸 2개**가 겹친 관찰이었고, 등록 상품 특유의 편향은 아니다.
>
> | 시드 상품 1개 담음 → top-10 중 같은 브랜드 | 페르소나 있음 | 페르소나 없음 |
> |---|---:|---:|
> | 등록 상품 (SSAFY Beauty 8개) | **24.0%** | 35.0% |
> | 원천 · 브랜드 상품수 ≥7 (크기 맞춘 대조군) | 37.1% | 25.5% |
> | 원천 · 임의 | 27.9% | 19.9% |
>
> 속성 친화도가 있으면 등록 상품은 같은 크기의 원천 브랜드보다 **덜** 끌어온다. 초과는 페르소나도 CF 도 없는
> 경로에서 **약 1칸**이고, 이는 CF 가 0 이라 코사인만 남은 콜드 상태의 성질이다 (행동이 쌓이면 사라진다).
>
> **기각한 고침 둘.** ① brand 블록 가중치 0 + LTR 재학습: 등록 57% / 70% 로 **악화** (same_brand 피처 중요도
> 0.003→0.038, holdout_a 43.95→43.40%). ② 등록 브랜드에 원핫 차원 추가: 57% / 70% 로 악화 (등록↔등록 코사인
> 0.34→0.88). 브랜드를 "더 잘" 표현하면 브랜드 재구매 설계가 그대로 작동해 같은 브랜드가 더 나온다.
> 남은 손잡이는 브랜드 상한·MMR λ 인데 그건 전역 노출 정책이다 (부록 · brand-exposure 프론티어: 상한은 비시드
> 1칸당 −1.8%p). **결론: 등록 상품 쪽에서 고칠 것은 없다.** §8.1 관계 피처 전환은 "어휘 없이 브랜드를 받는" 목적으로만 남는다.

## 5-1. 배너 (2026-09-07 신설 · 제안)

> **이름 확정 (2026-09-08, Jira 212):** 칸 번호는 응답도 이벤트도 **`banner_slot`** 이다.
> DATA 계약(`event-properties-schema.md` 배너 property)이 `banner_slot` 고정이고 `slot` 키는
> 스키마·클렌징 양쪽에서 거부되므로, 프론트가 응답 값을 변환 없이 `banner_impression` /
> `banner_click` 에 그대로 싣도록 응답 필드도 같은 이름으로 맞췄다. 합성 로그 생성기
> (`gen_behavior_logs.py`, `--no-banner-events` 로 끔)도 같은 이름으로 배너 2종을 낸다.

> **상태: 구현 (2026-09-09, Jira 218).** `batch/serving/banners.py` — `banner_slots > 0` 이면 응답에
> `hero`·`banners[]` 가 실린다. 프론트 확정(09-09) 네 가지를 그대로 따른다:
>
> | 확정 | 구현 |
> |---|---|
> | 전용 칸은 **배너 칸** | `banner_slots=6&reserved=2` → 칸 5·6 `new_brand`(`banner_value: null`, 키 유지). `items` 는 순수 순위(reserved=0 과 동일). `list_id=banner_row` 로 CTR 을 따로 본다 |
> | `hero.banner_type` **항상** 있음 | `items[0]` 에 사용자 축과 맞는 값, 없으면 상품 자신의 값(concern → ingredient → clean → category → price_bin). 이미지 변형 5종 선택용. **`hero=new_brand`(Jira 237) 면 대상이 items[0] 대신 점수 최고 신규 상품**이고 축 문구 규칙은 같다 |
> | 성분 축은 **위치가중 ≥ 0.3** | `ingredient` 소속은 전성분 앞 30% 성분만 (`INGREDIENT_MIN_POSITION`), **첫 값은 위치가중 내림차순**(09-10 수정 — 전에는 어휘집 등재 순서라 앞 30% 에 히알루론산이 있으면 그것이 문구가 됐다. 원천 74개 값이 바뀜, 프론트와 동일 규칙). 대시보드 미량 경고와 충돌 안 함 |
> | `reason` 은 **key 하나** | 아이템·배너 모두 `attribute → content → cf → new_brand → popular` 우선순위로 하나. 문장은 프론트가 다시 쓴다 |
>
> **축 값은 어디서 오나 (`trait_source`)** — `session`: 시드 상품(긍정 가중)에서 가장 많은 값(concern·ingredient·clean·category·price_bin) ·
> `profile`: 페르소나 속성(segment, skin_type → skin_tone → eye_color → hair_color 순) · `coldstart`: 시드도 속성도 없으면 축에서 상품이 가장 많은 값 ·
> `explore`: 서버는 안 쓴다(화면 몫). 축 안 순위는 추천 점수 그대로, 축은 필터다. 축이 마르면 점수순 일반 상품으로 채우고 문구는 그 상품의 축.
> 신규가 `reserved` 보다 적으면 남은 칸은 일반 상품(`reserved: false`)으로 채운다 — **칸은 비지 않는다.**
> 성능: 점수 계산 1회를 메인·배너가 같이 쓴다. 6칸 포함 200명 실측 — 서버 내부 p50 8.5 / p95 15.3ms, 인프로세스 왕복 p95 23ms (SLA 기준 **p95 200ms**, 프론트 확정).

### 배너는 정확도 장치가 아닙니다

축 기준으로 배너 칸을 뽑아도 **그냥 11등을 보여주는 것보다 못합니다.**

| 배너 칸 뽑는 규칙 | Recall@11 | 메인 10칸 대비 |
|---|---:|---:|
| 메인 10칸만 | 38.55% | 기준 |
| 그냥 11등 | 39.90% | +1.35%p |
| **축 기준** | 39.05% | **+0.50%p** |
| 무작위 | 38.85% | +0.30%p |

사용자의 시드 상품이 특정 축에서 일관되지 않기 때문입니다 (`concern` 0.336 ·
`ingredient` 0.155 · `texture` 0.052). **배너의 값은 ① 추천 이유를 말해 주는 것과
② 신규 브랜드에 자리를 주는 것**이고, 성과는 Recall 이 아니라 **배너 클릭률과
교차 브랜드 유입**으로 잽니다. 근거는 `evaluation-framework.md` 부록 Q ②.

### `banner_type` 과 `banner_value`

| `banner_type` | `banner_value` | 값 출처 |
|---|---|---|
| `concern` | 9종 | `product-feature-vocab.json` `concern` 블록 |
| `ingredient` | 30종 | 〃 `ingredient` |
| `clean` | 16종 | 〃 `clean` |
| `price_bin` | 5구간 | 〃 `price_bin_edges` |
| `category` | 8 / 19종 | 〃 `secondary` / `tertiary_category` |
| `segment` | 20종 | `affinity_lift.csv` 의 세그먼트 (skin_type 4 · tone 5 · hair 5 · eye 5) |
| `new_brand` | `null` | 전용 칸. 축이 아니라 자리 |

**`banner_value` 는 어휘집 문자열 그대로** 내려갑니다. 한국어 표시는 소비자가
`product-form-labels-ko.json` 으로 변환합니다 — **화면 라벨을 그대로 보내면
한 글자 차이로 그 축이 통째로 매칭 실패하고 화면에는 아무 표시도 안 납니다.**

### 중복 배제

`items` 와 `banners` 의 `product_id` 는 **서로 겹치지 않습니다.** `hero` 만
예외입니다 — `items[0]` 에 축 문구를 얹은 것이므로 같은 상품일 수 있습니다.
`hero=new_brand` 인 히어로는 `banners` 와 겹치지 않게 뺍니다(`items` 와는 겹칠 수 있음).

> **배너 행 상태 (2026-09-10):** 프론트 공유로 배너 행 6칸(전용 칸 5·6)이 09-10 기획 검토에서 화면에서
> 빠졌다. `banner_slots=6&reserved=2` 규격은 계약·서버에 그대로 남고(살아나면 즉시 쓸 수 있음), 화면은
> 히어로 하나 + `hero=new_brand` 로 신규 브랜드 노출을 대신한다. 기획 문서 반영은 확인 필요.

### 전용 칸 (`reserved`) — 신규 브랜드 비율에 따라 바꿉니다

CF 를 켜면 이력이 없는 신규 브랜드 상품이 밀려납니다. 점수로 싸우게 하는 것보다
**자리를 떼어 주는 것이 훨씬 쌉니다.**

| 신규 브랜드 비율 | 권장 `reserved` | 전용 칸의 비용 |
|---|---:|---|
| ~10% | **2칸** | −1.23%p (3칸은 1.3%p 더 깎임) |
| 10~30% | 2~3칸 | 이 구간부터 **공짜를 넘어 이득** |
| 30%+ | **3칸** | +0.81%p — 전체도 3칸이 최고 |

신규 브랜드 10% 조건에서 **전용 2칸이 그 사장님 상품의 적중률을 4.03% → 43.59%**
로 올립니다. 근거는 `evaluation-framework.md` 부록 P·R-3·R-4.

> **`reserved` 는 설정값으로 두십시오.** 브랜드가 늘면 칸 수를 바꿔야 하는데
> 코드에 박아 두면 그때 고쳐야 합니다.

**구현 (2026-09-08, Jira 129)** — `batch/jobs/recommender.py` `Recommender.rank(reserved=N)`.
측정한 형태 그대로다: **메인 `size` 칸 안에서** MMR 이 `size − N` 개를 고르고, 신규 상품
중 점수순 `N` 개를 뒤에 붙인다.

| | |
|---|---|
| 신규 상품 | 지지자 < `CF_MIN_SUPPORT`(3명) **또는** 브랜드가 어휘집 밖. 둘 다 이미 있는 값이라 새 산출물이 없다 |
| 신규가 모자라면 | 남은 자리를 일반 후보 점수순으로 채운다. **칸이 비지 않는다** |
| 지금 카탈로그 | 200개 전부 지지자 520명 이상·어휘집 안 → 신규 0개 → **`reserved=2` 와 `0` 이 같은 결과**. 골든·대표 지표(당시 43.95%)가 한 자리도 안 바뀐다 |
| 기본값 | 코드 `RESERVED = 0`. API 기본 2 는 서빙 설정에서 준다 |
| 응답 | 전용 칸 항목에 `reserved: true` (`rank(flags=True)`) |
| 검증 | `python batch/jobs/eval_persona_feature.py --split holdout_a --reserved 2` — "LTR" 행과 "LTR · 전용 칸" 행이 같아야 한다. 부하 조건(신규 10/30/50%)은 `Research/eval/eval_ltr_new_brand_20260907.py` |

> ⚠ **위 표의 `reserved` 파라미터 설명("그중 … 배너 칸")과 다릅니다.** 측정(부록 R-3·R-4)은
> 전용 칸을 **메인 목록 안**에 두고 잰 것이고, 배너 자리에 두는 형태는 재지 않았습니다.
> 메인 안에 두면 정확도 비용·이득이 위 표 그대로고, 배너에 두면 메인 정확도는 그대로인
> 대신 신규 브랜드 적중률 43.6% 는 보장되지 않습니다. **어느 자리로 갈지는 프론트와 확정할
> 것** — 구현은 메인 안 형태이고, 배너 형태가 필요하면 같은 `new_mask()` 로 뽑아 배너에
> 넣으면 됩니다.

`breakdown`을 응답에 포함하는 이유는 **추천 근거를 항별로 분해해 설명**할 수 있기 때문입니다.

> **2026-09-07 단서.** 원래 이 자리에 "잠재 요인 CF 로는 불가능하며 CBF 를 선택한
> 이유" 라고 적혀 있었는데, 그 근거가 약해졌습니다.
>
> - 우리가 쓰려는 CF 는 **잠재 요인이 아니라 아이템-아이템 동시발생**이라
>   "이 상품을 산 사람이 저것도 샀다" 로 설명이 됩니다. `breakdown` 에 항을
>   하나 더하면 됩니다
> - 다만 **학습 결합(LTR)까지 가면 항별 분해가 실제로 어려워집니다.** 그때는
>   피처 중요도로 대신 말해야 합니다 (부록 R). **설명 가능성은 LTR 채택의
>   비용으로 계산해야 하는 항목**이지, CBF 를 고른 이유로 남겨 둘 것이 아닙니다

### 성능 실측

상품 200개 × 148차원 기준, numpy 싱글 코어:

| 항목 | 값 |
|---|---:|
| 추천 1건 (점수 계산 + 상위 10개 추출) | **6.8 μs** |
| 싱글 코어 처리량 | 146,000 RPS |
| 사용자 10,000명 전원 일괄 재계산 | 3.8 ms |

> **2026-09-07 재측정 — 위는 점수 계산만입니다.** 사용자별 친화도·CF·MMR 까지
> 포함한 실제 경로는 이렇습니다 (후보 200개 · 파이썬).
>
> | 구성 | 1건당 |
> |---|---:|
> | 현행 선형 (CBF + CF 가점) | **0.26 ms** |
> | 학습 결합 (LTR, 트리 278개) | **4.0 ms** |
>
> **200개 전체를 정렬해 달라고 해도 추가 비용이 0 입니다** — Top 10 만 뽑든
> 전체를 정렬하든 어차피 200개를 전부 채점하기 때문입니다 (LTR 4.03 vs 3.80ms,
> 측정 노이즈 수준). 다만 LTR 은 선형보다 15배 느려 **사용자별 결과 캐싱이
> 필요합니다.**

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
| MMR λ_mmr | **0.8 확정** (2026-09-01). valid 에서 정확도는 어느 λ 에서도 유의차 없음 → **다양성 기준으로 채택**. 목록당 고유 브랜드 3.7 → 4.2개, 한 브랜드 최대 점유 61.3% → 59.0%. 근거는 `docs/ai/recommendation-design.md` 8절. **CF 채택 후 재스윕하지 않았다** — 근거가 다양성 쪽이고 CF 가 브랜드 쏠림을 오히려 풀어 주기 때문 (부록 S) |
| 시간 감쇠 τ | 30일. 생성 로그의 시간 범위에 따라 조정 |
| `w1` 항 검증 | 행동 로그 생성 후 가능 |
| CF 가점 (§4-1) | **채택** (2026-09-07). β = 1.0 · 가점 전용 · 지지자 3명 미만 차단 |
| 학습 결합 (§4-2) | **채택** (2026-09-07). §5 처리 4단계가 모델 추론으로 바뀌고 `breakdown` 항별 분해가 사라진다. 선형은 폴백으로 남는다 |
| 모델을 자바에서 어떻게 읽나 | **파이썬 추론 서버 참조 구현 있음** (2026-09-08, `batch/serving/recommend_server.py`, §5). 백엔드가 프록시하는 형태를 권함. ONNX 는 백엔드 결정 시 — 그때도 이 서버가 대조 기준 |
| `breakdown` 대체 형태 | **확정 (2026-09-09, Jira 218).** 아이템당 **key 하나**, 우선순위 attribute → content → cf → new_brand → popular. 문장은 프론트가 종류별로 다시 쓴다. (이전: `items[].reason` 에 실제로 있던 신호만 문장으로 (`cf`·`content`·`attribute`·`new_brand`·`popular`, §5 참조 구현 표). 문구·개수는 프론트와 협의 |
| 응답 시간 기준 | **p95 200ms 확정** (프론트, 2026-09-09) — 넘기면 프론트가 배너를 접고 인기순으로 그린다. 실측 p95 15.2ms(메인만)·15.3ms(배너 6칸 포함, 서버 내부). 이전 문구: 기준값(SLA)은 미정 — 백엔드 프록시·네트워크 포함해 다시 잰 뒤 정한다 |
| 신규 브랜드 전용 칸 (§5-1) | **구현** (2026-09-08, Jira 129). `Recommender.rank(reserved=N, flags=True)`. 지금 카탈로그는 신규 0개라 결과 불변 (부록 U) |
| 전용 칸의 자리 | **배너 칸으로 확정 (2026-09-09, 프론트).** `banner_slots > 0` 이면 배너 뒤 `reserved` 칸, `= 0` 이면 예전처럼 메인 안(측정 형태 보존). 이전: 측정·구현은 메인 `size` 칸 안. `reserved` 파라미터 설명은 배너 칸으로 적혀 있어 어긋남 — 확정 후 한쪽으로 정리 |
| 사용자 식별 (`persona_id`) | **선택 파라미터로 열었다** (2026-09-09, Jira 214). 없으면 익명 cold_start, 표에 없는 값은 실회원 id 로 받아 행동으로만 개인화. 404 없음. 회원 `accountId` ↔ 페르소나 매핑은 **백엔드 결정 대기** (요청서 A 매핑표 / B 프론트 전달 / C 익명 — C 는 서버 준비 완료) |
| 프론트·백엔드 연결 | **2026-09-09 요청서 전달.** 프론트: 이름 5개(`user_id→persona_id`·`k→size`·`rank→position`·`slot→banner_slot`·`model_version→algorithm`) + `recommendation_id`·`list_id` 추가 + Vite 프록시. 백엔드: `/api/recommend` 패스스루 컨트롤러·폴백·타임아웃 300ms 제안. 로컬 실측: Vite 프록시 한 줄로 5173→8300 200 |
| 시연용 자사 브랜드 (SSAFY Beauty) | **편입 완료** (2026-09-09, Jira 216, §5-2). `POST /api/products` 로 등록 즉시 카탈로그에 들어가고, 8개는 `registered_products.jsonl` 에 미리 들어 있다. `reserved=2` 면 칸 9·10 이 SSAFY. 기존 200개 순위는 분모 고정으로 보존. 편향 의혹은 Jira 217 에서 측정으로 닫힘 — 등록 상품 특유 편향 아님, 고침 둘 기각 (§5-2 표) |
