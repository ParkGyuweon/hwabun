# 서빙용 피처 산출물

`python batch/jobs/export_features.py` 가 만든다. 백엔드 `RankingService` 가 읽는 입력이다.
계약은 `contracts/recommendation-io-spec.md`, 점수 식은 같은 문서 §API 를 따른다.

```
score(u, i) = model.predict_proba(피처 19개)      <- 학습 결합 (계약 §4-2)
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
| `ltr_model.pkl` | 학습 결합 모델 (부스팅 트리 278개, 약 1.0MB) | (서빙 전용) |
| `ltr_model_meta.json` | 피처 이름 19개 · 학습 조건 · 순열 중요도 · sklearn 버전 | (서빙 전용) |
| `ranking_golden.json` | 페르소나 20명의 기대 상위 10개와 점수 | (대조용, 적재 대상 아님) |

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
- **`ltr_model.pkl` 은 파이썬 pickle 이라 자바가 못 읽는다.** ONNX 로 내보내거나
  파이썬 추론 서버를 띄워야 한다. AI 파트 권고는 후자다 — 피처 19개를 자바로 다시
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
