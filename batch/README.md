# batch/ — AI 파트 (상품 인코딩 · 학습 · 추천 서버)

기준일 2026-09-16. 어휘집 0.7(price_bin 원화, 벡터 불변). 대표 지표는 `docs/ai/evaluation-framework.md` 상태 블록 (holdout_a 43.80 / holdout_b 42.45%, LTR 239 트리·20피처 — 09-16 가중 평균 코사인 채택, 09-10 19피처 모델은 42.15 / 43.15).

| 폴더 | 무엇 | 진입점 |
|---|---|---|
| `ingest/` | 원천(Sephora)·등록 상품에서 어휘집·상품 벡터·친화도·CF·LTR 산출물을 만든다 | `regenerate_all.py`(전체 재생성) · [`ingest/README.md`](ingest/README.md) |
| `ingest/data/` | 입력 데이터와 산출물. `serving/` 이 서버가 읽는 것 | [`ingest/data/README.md`](ingest/data/README.md) · [`serving/README.md`](ingest/data/serving/README.md) |
| `jobs/` | 인코더·사용자 벡터·친화도·CF·LTR 학습·추천기(순위·MMR·전용 칸) — 학습과 서빙이 같은 코드 | [`jobs/README.md`](jobs/README.md) |
| `serving/` | FastAPI 추천 서버 (계약 `contracts/recommendation-io-spec.md` §5). 백엔드가 프록시한다 | [`serving/README.md`](serving/README.md) |

## 흐름 한 장

```
products_200.json + registered_products.jsonl ─ product_encoder ─→ product_feature.jsonl (148차원)
reviews(844,865) ─ build_affinity_lift ─→ affinity_lift.csv        (속성 친화도)
personas(9,900)  ─ build_cooc ─────────→ item_cooc.npz             (CF 동시발생, 홀드아웃 제외)
                 ─ train_ltr ──────────→ ltr_model.pkl (239 트리)   (20 피처 = ltr_features.py)
                                          ↓
recommend_server.py (8300)  ←─ GET /api/recommend  ←─ 프론트(로컬 Vite) / 쇼핑몰 백엔드 프록시(운영, 09-14 머지)
        ↑ POST /api/events · Kafka activity-events (kafka_state.py)  ← 수집기 / 시뮬레이터
        ↑ POST /api/products · catalog_sync.py (5분, 원천 200개는 교체 안 함)  ← 상품 등록
        ↑ user_trait.py ← user_trait_daily (dw MySQL → 스냅샷 → null) → 응답 long_term_trait
```

## 재생성

```bash
python batch/regenerate_all.py          # 어휘집 → 인코딩 → 친화도 → CF → LTR → 골든 → 배너 축 → 대시보드 → 백엔드 테이블
```
인코더·어휘집을 바꾸면 전부 다시 만들고 홀드아웃 두 세트를 다시 잰다 (`docs/ai/evaluation-framework.md` 절차).
학습 난수 폭이 ±0.8%p 라 **1%p 안의 차이는 변경 효과로 읽지 않는다** (부록 W).

## 테스트

절대 import(`from batch...`) 라 **레포 루트에서** 돌린다. pytest 는 없다.

```bash
cd <레포 루트>
PYTHONPATH=. python -m unittest discover -s batch/jobs -p "test_*.py"     # 102
cd batch/serving && python -m unittest test_recommend_server               # 36  (test_banners 와 한 프로세스로 돌리지 않는다 — 등록 테스트 상품이 샌다)
python -m unittest test_banners                                            # 22
python -m unittest test_catalog_registry test_catalog_sync test_kafka_state test_session_store test_prescription test_user_trait   # 55
python -m unittest test_live                                               # 4
cd <레포 루트> && PYTHONPATH=. python -m unittest discover -s simulator/generator -p "test_*.py"   # 27 (생성기·추천 클라이언트, 절대 import 라 루트에서)
```

## 런타임에 쓰는 파일 (산출물 아님)

`session_events.jsonl` · `prescriptions.jsonl` · `registered_products.jsonl` 은 서버가 **쓰는** 파일이다. 운영은 `/data` 볼륨
(`SESSION_EVENTS_PATH`·`PRESCRIPTIONS_PATH`·`REGISTERED_PRODUCTS_PATH`), env 없이 로컬에서 돌리면 `ingest/data/serving/` 에 생긴다.
`.gitignore` 의 `data/` 패턴에 걸려 커밋되지 않는다 — 같은 이유로 **`ingest/data/` 에 새로 만든 산출물도 `git status` 에 안 뜬다.**
재생성 뒤에는 `git add -f` 또는 `git status --ignored` 로 확인한다.
