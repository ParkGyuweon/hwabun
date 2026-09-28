# 서빙용 피처 산출물

`python batch/jobs/export_features.py` 가 만든다. 추천 서버(`batch/serving`)가 읽는 입력이다. 백엔드는 프록시만 한다.
계약은 `contracts/recommendation-io-spec.md`, 점수 식은 같은 문서 §API 를 따른다.

```
score(u, i) = model.predict_proba(피처 20개)      <- 학습 결합 (계약 §4-2)
```

**2026-09-07 부터 점수 결합을 학습한다.** 아래 선형 식은 **폴백**이고, 그 항들은
없어지지 않고 모델의 피처로 들어간다.

```
score(u, i) = w1 x cos(v_u+, v_i) - λ x cos(v_u-, v_i) + w2 x attr_affinity(u, i)
            + w3 x prior(i) + w_b x brand_unknown(u, i) + β x cf_bonus(u, i)
```

| 파일 | 내용 | 대응 테이블 |
|---|---|---|
| `product_feature.jsonl` | 상품 200개 · 148차원 벡터 · prior · 카테고리/가격대/평점 | `product_feature` |
| `attribute_affinity.csv` | 4,000행 = 200상품 x 20세그먼트 | `attribute_affinity` |
| `item_cooc.npz` | 200x200 동시발생 + 상품별 지지자 수 | (서빙 전용) |
| `ltr_model.pkl` | 학습 결합 모델 (부스팅 트리 239개, 2026-09-16 · 약 0.9MB(901,360바이트) · 정본은 `ltr_model_meta.json`) | (서빙 전용) |
| `ltr_model_meta.json` | 피처 이름 20개 · 학습 조건 · 순열 중요도(현행 모델은 `null` — 09-26 실측값은 노션에만 있음) · sklearn 버전 | (서빙 전용) |
| `ranking_golden.json` | 페르소나 20명의 기대 상위 10개와 점수 | (대조용, 적재 대상 아님) |

## 백엔드 적재용 정규화 테이블

`python batch/jobs/export_backend_tables.py` 가 만든다. **DDL 이 같이 나온다** —
`backend_tables.sql` 을 그대로 실행하고 CSV 를 적재하면 된다.

| 파일 | 행 | 내용 |
|---|---:|---|
| `feature_block.csv` | 9 | 벡터 148차원을 블록으로 자르는 법 (`block_offset`·`dim`·가중치) |
| `ingredient_vocab.csv` | 30 | 성분 마스터 — `ingredient_id`·원문·한국어·보유 상품 수 |
| `concern_vocab.csv` | 9 | 피부 고민 마스터 |
| `product_ingredient.csv` | 842 | 상품 x 성분 (`position_weight`·`source`) |
| `product_concern.csv` | 363 | 상품 x 고민 상위 2축 |
| `ingredient_skin_affinity.csv` | 76 | 피부타입 x 성분 |
| `registered_products.jsonl` | 8 | **등록 상품** (Jira 216) — `POST /api/products` 가 §4 파생값까지 채워 append. 서버 재시작 시 원천 200개 뒤에 다시 붙는다. 지금은 시연 브랜드 SSAFY Beauty 8개. 오프라인 평가는 읽지 않는다 |

**위쪽 대시보드용 CSV(`product_ingredient_position.csv` 등)와 같은 값이다.**
대시보드용은 상품명·브랜드명을 행마다 붙여 바로 그릴 수 있게 한 것이고, 이쪽은
**키만 내고 상품 테이블에서 조인**하게 한 것이다. 적재는 이쪽을 쓸 것.

### 적재할 때 지킬 것

- **모든 행에 `vocab_version` 이 있다. 버전이 다른 행을 섞지 말 것.**
  `ingredient_id` 는 어휘집 배열의 인덱스이자 **블록 안에서의 차원 위치**라,
  버전이 다르면 그 대응이 조용히 깨진다. 전 테이블의 PK 첫 열이 `vocab_version` 이다
- **키는 `ingredient` 원문**이고 `label_ko` 는 화면 표시용이다. 한국어를 키로 쓰면
  한 글자 차이로 매칭이 통째로 실패하는데 **화면에는 아무 표시도 안 난다**
- `block_offset`·`concern_rank` 는 **MySQL 8 예약어(`offset`·`rank`)를 피한 이름**이다.
  CSV 헤더와 DDL 이 같으므로 그대로 적재된다
- **`position_weight` 는 함량이 아니다.** 전성분 맨 앞 성분이 1.0 (highlights 성분 태그는 2026-09-10 부터 쓰지 않음, 계약 §3.1), 전성분에서 찾은
  것은 배합 순서 기반 감쇠다. "앞쪽에 적혀 있다" 이지 "몇 % 들었다" 가 아니다
  (`source` 열은 호환을 위해 남겼고 지금은 전부 `parsed` 다)
- **`ingredient_skin_affinity` 는 곱이라 인과가 아니다.** "지성이 반응한 상품에
  이 성분이 많더라" 이지 "이 성분이 지성에 좋다" 가 아니다. `n_products` 가 작은
  행은 근거가 얇다

## 백엔드가 알아야 할 것

- **벡터는 L2 정규화가 끝나 있다.** 다시 정규화하지 말고 내적만 하면 그것이 코사인이다.
- `vocab_version` 이 다른 행을 섞지 말 것. 차원 순서가 어휘집에 묶여 있다.
- 친화도 조회 가중치는 사용자 `skin_type` 에 따라 갈린다. 복합성(전체의 55.3%)은
  `skin_type` 항을 쓰지 않고 그 몫을 `skin_tone` 으로 넘긴다 (0.00 / 0.80 / 0.10 / 0.10).
  나머지는 0.40 / 0.40 / 0.10 / 0.10.
- 사용자 속성 표기를 세그먼트 이름으로 정규화해야 한다:
  `lightMedium -> light` 같은 톤 5버킷, `Grey -> gray`, `brunette -> brown`.
  기준 구현은 `batch/jobs/persona_feature.py` 의 `normalize()` 다.
- 셀이 없으면 **0.5(중립)** 을 쓴다. 0 을 쓰면 "표본 없음" 이 "안 맞음" 으로 둔갑한다.
- `w1/w2/w3` 는 상호작용 고유 상품 수에 따른 스케줄을 따른다 (`recommender.SCHEDULE`).
  **학습 결합을 쓰면 이 스케줄을 타지 않는다** — 시드 개수는 피처 `n_seed` 로 들어간다.
- **이 산출물을 읽어 점수를 내는 파이썬 서버가 있다** — `batch/serving/recommend_server.py`
  (계약 §5, Jira 206). 백엔드는 이것을 프록시하면 된다. 2026-09-11 EC2-1 에 컨테이너로 배포됨(`deploy/ec2-1`).
  실시간 행동은 Kafka `activity-events` 구독(Jira 226·232)으로 들어온다.
- 표에 없는 산출물: `banner_axes.json`(배너 축 값, Jira 218) · `product_concern_top2.csv` · `ingredient_skin_lift.csv`(대시보드).
  `session_events.jsonl`·`prescriptions.jsonl`·`registered_products.jsonl` 은 서버가 **런타임에 쓰는** 파일이라 산출물이 아니다
  (운영은 `/data` 볼륨, 로컬 실행 시 env 없이 돌리면 이 폴더에 생긴다 — `.gitignore` 의 `data/` 패턴에 걸려 커밋되지 않는다).
- **`ltr_model.pkl` 은 파이썬 pickle 이라 자바가 못 읽는다.** ONNX 로 내보내거나
  파이썬 추론 서버를 띄워야 한다. AI 파트 권고는 후자다 — 피처 20개를 자바로 다시
  구현하면 **에러 없이 순위만 틀린다.** 계약 §4-2 참조.
- pickle 은 sklearn 버전에 묶인다. `ltr_model_meta.json` 의 `sklearn_version` 이
  로컬과 다르면 다시 학습할 것 (`python batch/jobs/train_ltr.py`).

## 대조하는 법

`ranking_golden.json` 의 각 케이스는 **행동 로그 없이 리뷰 시드만으로** 만든 사용자
벡터 기준이고, 시드 상품은 후보에서 뺐다. 자바 구현이 같은 입력으로 같은 상위 10개와
점수(소수점 5자리)를 내면 벡터·가중치·정규화·시드 제외가 전부 맞다는 뜻이다.
파일이 `scorer` 필드로 무엇으로 만들어졌는지 말한다 (`"ltr"` / `"linear"`).

> ### ⚠ 파일에 적힌 값을 그대로 쓸 것
>
> `product_feature.jsonl` 은 벡터를 **소수 6자리로 반올림**해 내보낸다. 골든도
> **그 반올림된 값으로** 계산한다. 선형 합에서는 차이가 묻혔지만 **학습 결합은
> 트리라, 피처가 분기점 근처에 놓이면 잎이 통째로 갈린다** — 실제로 한 페르소나에서
> 두 상품의 순서가 뒤집혔다. 자체적으로 정밀도를 올리거나 다시 정규화하지 말 것.

식이 맞아도 블록 가중치·L2 정규화·시드 제외 중 하나만 어긋나면 순위가 **조용히**
달라진다. 그래서 눈으로 보지 말고 이 파일로 비교할 것.

파이썬 쪽 같은 검사: `python -m unittest batch.jobs.test_export_features`

## 서빙 정책과 다른 점

이 기준 결과는 점수 계산 대조용이라 **평가 모드**(시드 전부 제외)이고 **MMR 을
적용하지 않았다.** 실제 서빙은 여기에 두 가지가 더 붙는다.

1. 조회 상품을 상한 2개까지만 남긴다 (재고려 리마인드)
2. MMR 다양성 보정 `λ_mmr = 0.8`, 후보 풀은 상위 30개 (`recommender.mmr`)

그래서 서빙 목록과 이 파일의 순서는 다르다. **먼저 MMR 없이 이 파일로 점수를
맞춘 뒤**, MMR 을 켜는 순서로 붙이는 것이 디버깅하기 쉽다.
