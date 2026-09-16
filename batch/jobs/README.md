# batch/jobs — 인코딩 · 학습 · 추천기 (학습과 서빙이 같은 코드)

설계 문서: `docs/ai/recommendation-design.md` · 평가: `docs/ai/evaluation-framework.md` (대표 지표 부록 W: 42.15 / 43.15%).

| 파일 | 역할 |
|---|---|
| `product_encoder.py` | 상품 → 148차원 벡터 (어휘집 `contracts/product-feature-vocab.json` 0.5). 성분은 전성분 위치 가중만 쓴다 — highlights 성분 태그는 안 쓴다(계약 §3.1, 09-10). SPF 는 전성분에 자차가 없으면 제품명 `SPF nn` 으로 켠다 |
| `user_vector.py` · `behavior_weights.py` | 행동 이벤트 → 사용자 벡터. 가중치의 단일 소스는 `frontend/src/types/log.ts` |
| `persona_feature.py` | 속성 친화도 `AffinityTable` (`affinity_lift.csv`), 표기 정규화(`lightMedium→light`, `brunette→brown`, `Grey→gray`). 서버의 쿼리 속성 검증도 같은 표를 쓴다 |
| `build_cooc.py` · `cf_bonus` | CF 동시발생. 홀드아웃 페르소나는 `personas_*.json` glob 으로 자동 제외 |
| `ltr_features.py` | LTR 피처 20개 — 19개 + 가중 평균 코사인 `cos_seed_w`(강도 = 서빙은 이벤트 가중치, 학습은 시드 평점, Jira 322 09-16; `weighted_from_meta` 로 모델 메타를 따라감) (`n_ref=200` 분모 고정 — 등록 상품이 늘어도 원천 순위가 안 흔들린다) |
| `train_ltr.py` | HistGradientBoosting 학습 (`--seed`, `--max-iter 800`). 신규 상품 모양으로 학습 행 25% 증강 |
| `recommender.py` | 점수(LTR 또는 선형 폴백)·MMR λ=0.8·전용 칸 `reserved`·`new_mask()`. LTR 시드 0 = `prior×0.70 + 친화도×0.30` (Jira 245) |
| `hidden_preference.py` | 동적 평가용 — 추천 점수와 분리된 행동 생성 기준 |
| `eval_*.py` · `export_*.py` | 홀드아웃 평가, 대시보드·백엔드 테이블 내보내기 |

## 규칙

- **인코더·어휘집을 바꾸면** `batch/regenerate_all.py` 로 전부 다시 만들고 holdout_a 에서 고르고 holdout_b 에서 확인한다.
- **학습 난수 폭 ±0.8%p** — 1%p 안의 차이는 변경 효과로 읽지 않는다.
- 골든(`ranking_golden.json`)은 자바가 읽는 소수 6자리 반올림 기준으로 만든다.

## 테스트

```bash
cd <레포 루트>
PYTHONPATH=. python -m unittest discover -s batch/jobs -p "test_*.py"     # 98 (2026-09-11)
```
