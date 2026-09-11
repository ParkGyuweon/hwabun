# batch/serving — 추천 추론 서버 (FastAPI, 8300)

계약 `contracts/recommendation-io-spec.md` §5 의 **참조 구현이자 정본**. 모델이 sklearn pickle 이고 피처 19개를 다른 언어로
다시 짜면 순위가 조용히 어긋나므로 점수는 파이썬이 내고, 쇼핑몰 백엔드는 프록시한다 (프록시는 2026-09-11 기준 브랜치
`feat/recommendation-proxy-mvp`, dev 미머지). 2026-09-11 EC2-1 에 컨테이너로 배포됨 (`deploy/ec2-1`).

## 기동

```bash
cd <레포 루트>
pip install -r batch/serving/requirements.txt          # scikit-learn 은 ltr_model_meta.json 의 버전과 정확히 같아야 한다
python -m uvicorn batch.serving.recommend_server:app --host 127.0.0.1 --port 8300
curl "http://127.0.0.1:8300/health"
curl "http://127.0.0.1:8300/api/recommend?persona_id=PA00001&size=10&banner_slots=1&reserved=0&hero=new_brand&seed=review"
```
- Windows 에서는 `localhost` 대신 **`127.0.0.1`** (IPv6 폴백으로 요청마다 2초).
- `GMS_KEY` 는 `POST /api/prescription` 만 쓴다. 없으면 그 엔드포인트만 503, 추천은 전부 정상.
- `KAFKA_BOOTSTRAP_SERVERS` 를 주면 `activity-events` 를 구독해 상태를 갱신한다 (없으면 `POST /api/events` 만).
- `seed=review` 는 리뷰 시드를 상태로 쓰는 **시연용** (`state_source: review_seed`).

## 파일

| 파일 | 역할 |
|---|---|
| `recommend_server.py` | 엔진(Engine)·엔드포인트. `/api/recommend` `/api/events` `/api/products` `/api/prescription` `/api/catalog/sync` `/api/sessions/compact` `/health` |
| `banners.py` | hero·배너 조립, 축 값(concern·ingredient·clean·price_bin·category·segment), `reason` 단일 key. 현행 화면은 히어로 1칸 `hero=new_brand` (Jira 237) |
| `catalog_registry.py` | 등록 상품(`POST /api/products`) 검증·인코딩·영속 (Jira 216/219) |
| `catalog_sync.py` | 쇼핑몰 `GET /api/products` 를 읽어 편입·갱신·중단 (Jira 222, `SHOP_BACKEND_URL`) |
| `kafka_state.py` | `activity-events` 소비자 — 수동 commit·event_id dedupe·health (Jira 226/232, 로컬 실측 ~35,000건/초) |
| `session_store.py` | 상태 이벤트 로그 append·재기동 시 재생 (Jira 224) |
| `prescription.py` | 대시보드 처방 문장 v0.3 (Jira 220/225, GMS) |
| `bench_recommend.py` | 응답 시간 측정 (p95 15ms 급) |

## 요청 파라미터 요약 (§5)

`persona_id`(없으면 익명 cold_start — 능력만, 화면 정책은 로그인 회원만) · `size` · `reserved` · `banner_slots` · `axes` ·
`hero=top|new_brand` · `skin_type|skin_tone|hair_color|eye_color` (실회원 가입 속성, Jira 245 — 페르소나 표에 있는 id 면 무시) · `seed=review`.
응답에 `recommendation_id`·`algorithm`·`attribute_source`·`hero_policy` 가 실린다.

## 테스트

```bash
cd batch/serving
python -m unittest test_recommend_server      # 28
python -m unittest test_banners               # 18   ← test_recommend_server 와 같은 프로세스로 돌리지 않는다 (등록 테스트 상품이 샌다)
python -m unittest test_catalog_registry test_catalog_sync test_kafka_state test_session_store test_prescription
```
테스트는 등록 상품 파일 복사본과 임시 세션 로그를 쓰므로 레포 파일을 건드리지 않는다. `test_prescription.test_live_once` 는 `RUN_LIVE`+`GMS_KEY` 가 있을 때만.

## 배포

`deploy/recommend.Dockerfile` (BuildKit 필수, 옆의 `.dockerignore` 사용) · `deploy/ec2-1/docker-compose.yml` `recommend` 서비스 (8300 내부 전용, `WORKERS=1`).
모델이 바뀌면 이미지 재빌드 후 `docker compose up -d recommend`. 절차는 `deploy/ec2-1/README.md`.
