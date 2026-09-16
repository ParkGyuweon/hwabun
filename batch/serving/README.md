# batch/serving — 추천 추론 서버 (FastAPI, 8300)

계약 `contracts/recommendation-io-spec.md` §5 의 **참조 구현이자 정본**. 모델이 sklearn pickle 이고 피처 19개를 다른 언어로
다시 짜면 순위가 조용히 어긋나므로 점수는 파이썬이 내고, 쇼핑몰 백엔드는 프록시한다 (프록시 09-14 dev 머지, hero·가입 속성 4개 통과).
EC2-1 에 컨테이너로 배포됨 (`deploy/ec2-1`, 09-15 dev 최신 이미지 · 어휘집 0.7). 재배포는 `deploy/ec2-1/redeploy-local.sh` 한 줄.

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
- 처방 LLM(GMS 과금) 스위치(Jira 325): `PRESCRIPTION_LLM=off` 로 끄고, 재배포 없이 `POST /api/prescription/llm {"enabled": true|false}` 로 켜고 끈다. 꺼지면 503 → 프론트 규칙표 문장. 저장본(cached)은 꺼도 준다. `/health.prescription` 에 enabled·key_present·llm_calls·cache_hits.
- `DW_MYSQL_HOST/USER/PASSWORD/DB` 또는 `USER_TRAIT_SNAPSHOT_PATH` 를 주면 응답 `long_term_trait` 가 채워진다 (둘 다 없으면 null, health `user_trait` 에 출처). 신선도(Jira 319): health `age_days`·`stale`(`USER_TRAIT_STALE_DAYS` 2 초과), `USER_TRAIT_MAX_AGE_DAYS`(14) 넘으면 `long_term_trait` null.
- `seed=review` 는 리뷰 시드를 상태로 쓰는 **시연용** (`state_source: review_seed`).

## 파일

| 파일 | 역할 |
|---|---|
| `recommend_server.py` | 엔진(Engine)·엔드포인트. `/api/recommend` `/api/events` `/api/products` `/api/prescription` `/api/catalog/sync` `/api/sessions/compact` `/health` |
| `banners.py` | hero·배너 조립, 축 값(concern·ingredient·clean·price_bin·category·segment), `reason` 단일 key. 현행 화면은 히어로 1칸 `hero=new_brand` (Jira 237). 히어로 `banner_type` 은 요청 `axes` 순서, 1순위 축에 성향이 없으면 상품 자신 값 + `trait_source=coldstart`, `hero_policy_version=hero-2026-09-15` (Jira 304·307). price_bin 은 원화 경계(어휘집 0.7) |
| `catalog_registry.py` | 등록 상품(`POST /api/products`) 검증·인코딩·영속 (Jira 216/219) |
| `catalog_sync.py` | 쇼핑몰 `GET /api/products` 를 읽어 편입·갱신·중단 (Jira 222, `SHOP_BACKEND_URL`) |
| `kafka_state.py` | `activity-events` 소비자 — 수동 commit·event_id dedupe·health (Jira 226/232, 로컬 실측 ~35,000건/초) |
| `session_store.py` | 상태 이벤트 로그 append·재기동 시 재생 (Jira 224) |
| `user_trait.py` | 장기 성향 `user_trait_daily` 조회 → 응답 `long_term_trait` (Jira 306). dw MySQL(`DW_MYSQL_HOST`) → 스냅샷 → null. 시작 적재·5분 재적재. 신선도 `age_days`·`stale`(2일)·TTL 14일 → null (Jira 319) |
| `prescription.py` | 대시보드 처방 문장 v0.3 (Jira 220/225, GMS) |
| `bench_recommend.py` | 응답 시간 측정 (p95 15ms 급) |
| `e2e_smoke.py` | 로컬 E2E 스모크 24단계 (판매자→등록→동기화→추천→회원→주문→결제→마트 API). `BE`/`RS`/`FE` env 로 주소. 09-14 14/24, 실패는 전부 백엔드 요청 항목 (Jira 296) |
| `live_stats.py` | **실시간 처리 현황** `GET /live`(시연용 한 페이지) · `GET /live/stats`(JSON). 초당 반영 이벤트·Kafka 파티션별 소비·방금 상태가 바뀐 사용자·추천 p50/p95 (Jira 295) |

## 실시간 처리 현황 `/live` (Jira 295, 시연용)

브라우저에서 `http://<추천 서버>:8300/live` 를 열면 1초마다 갱신되는 한 페이지가 뜬다. Grafana 는 수집기(8080)까지,
Spark UI 는 마트까지만 보이고, "그 이벤트가 **추천 상태에 반영됐다**" 는 마지막 층은 이 프로세스만 알기 때문에 여기서 센다.

| 칸 | 뜻 | 어디서 오나 |
|---|---|---|
| 초당 반영 이벤트 · 60초 막대 | `Engine.observe` 에 들어온 상태 변경 이벤트 수 | Kafka 소비자 + `POST /api/events` 둘 다 |
| Kafka 파티션별 소비 | 파티션 3개(key = session_id)가 이벤트를 나눠 받는 모양 | 소비자가 메시지 파티션 번호를 같이 넘긴다. Kafka 미연결이면 빈 칸 |
| 상태가 바뀐 사용자 | 기동 후 상태가 한 번이라도 바뀐 persona_id 수 · 메모리 세션 수 | |
| 추천 응답 p50/p95 · 요청/초 | 최근 60초 `/api/recommend` `latency_ms` | |
| 방금 상태가 바뀐 사용자 | 최근 40명, 어느 파티션(또는 직접)에서 어떤 이벤트로 | |

상단 오른쪽 **▶ 페르소나 시작** 버튼은 `POST /live/demo/start`(초당 건수) 로 `simulator/generator/demo_live.py` 를 자식 프로세스로 띄운다. 인원은 env `DEMO_LIMIT`(로컬 기본 9,900, 배포 compose 1,000 — 컨테이너 메모리 때문), 캐시는 `DEMO_CACHE_DIR`(배포 볼륨 `/data/demo_cache`). 09-16 부터 Docker 이미지에도 들어 있다(Jira 335). 절차 정본은 `docs/ai/live-demo-runbook.md`.

`GET /pipeline` · `/pipeline/stats` (Jira 337, `pipeline_stats.py`): 사이트 활동(PC/PA/실사용자) → Kafka 파티션(브로커 워터마크·committed·lag) → Spark(`SPARK_MASTER_UI`) → dw 마트 7개(`DW_MYSQL_*`) → 대시보드(`DASHBOARD_URL`) 를 한 화면에. 다른 파트 자원은 읽기만. 소비자에 `observer` 훅(필터 전 모든 메시지)이 붙는다. 에이전트 버튼은 노트북 런처 `simulator/agents/agent_launcher.py`(8301) 로 간다. 런북 §2-1.

`GET /live/stats` 가 같은 숫자를 JSON 으로 준다(`events.series_60s`·`partitions`·`recent`…). 인증은 없다 — 추천 서버는
내부 네트워크 전용이고, 시연에서 밖에 보이려면 nginx 에 `/live` 를 `recommend:8300` 으로 여는 한 줄이 필요하다(배포 README).
운영 지표의 정본은 수집기 Prometheus 메트릭이고, 이 페이지는 시연·디버그용이다.

## 요청 파라미터 요약 (§5)

`persona_id`(없으면 익명 cold_start — 능력만, 화면 정책은 로그인 회원만) · `size` · `reserved` · `banner_slots` · `axes` ·
`hero=top|new_brand` · `skin_type|skin_tone|hair_color|eye_color` (실회원 가입 속성, Jira 245 — 페르소나 표에 있는 id 면 무시) · `seed=review`.
응답에 `recommendation_id`·`algorithm`·`attribute_source`·`hero_policy` 가 실리고, 09-15 부터 `long_term_trait`(없으면 null)와 hero 의 `hero_policy_version`·`trait_source` 가 추가됐다.

## 테스트

```bash
cd batch/serving
python -m unittest test_recommend_server      # 36
python -m unittest test_banners               # 22   ← test_recommend_server 와 같은 프로세스로 돌리지 않는다 (등록 테스트 상품이 샌다)
python -m unittest test_catalog_registry test_catalog_sync test_kafka_state test_session_store test_prescription test_user_trait   # 13·5·7·3·17·10 = 55
python -m unittest test_live                  # 4    ← /live (Jira 295). TestClient 를 여니 따로 돌린다
```
테스트는 등록 상품 파일 복사본과 임시 세션 로그를 쓰므로 레포 파일을 건드리지 않는다. `test_prescription.test_live_once` 는 `RUN_LIVE`+`GMS_KEY` 가 있을 때만.

## 배포

`deploy/recommend.Dockerfile` (BuildKit 필수, 옆의 `.dockerignore` 사용) · `deploy/ec2-1/docker-compose.yml` `recommend` 서비스 (8300 내부 전용, `WORKERS=1`).
모델이 바뀌면 이미지 재빌드 후 `docker compose up -d recommend`. 절차는 `deploy/ec2-1/README.md`.
