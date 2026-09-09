# S15P21A306

HWABUN — 1인·소상공인 뷰티 브랜드가 나눠 쓰는 쇼핑몰(BLOOM)과 인사이트 대시보드.

기준일 2026-09-09

## 1. 시스템 아키텍처

```
[ 사용자 ]                          [ 서비스 · frontend/ (React, Vite 5173) ]
 실제 소비자                          index.html      쇼핑몰 BLOOM — 목록·상세·장바구니·주문, 추천 카드·히어로·배너 행
 simulator/generator  PC 9,900명  ──▶  dashboard.html  브랜드 대시보드 — 개요·행동·상세 콘텐츠·고객군·성분·리뷰·피드백·상품 등록 (9화면)
 simulator/agents     PA 100명        platform.html   HWABUN 플랫폼 운영
 (Playwright + LLM)                   lib/logger.ts   이벤트 36종 조립·버퍼·재시도 (429/502/503 백오프)
                                          │                         │
              ┌───────────────────────────┘                         └──────────────────────┐
              ▼                                                                             ▼
[ 쇼핑몰 백엔드 · shop_backend/ (Spring, 8090, MySQL) ]          [ 수집 · backend/ (Spring, 8080) ]
 로그인(JWT)·브랜드·상품·주문·결제·리뷰·피드백·정산·판매자 대시보드     POST /api/events → 검증 → Kafka activity-events
 상품 등록 계약(어휘 검증·unmapped 저장) 구현, dev 머지              key=session_id · 파티션 3 · 백프레셔 429/503
              │  (예정) /api/recommend 프록시 · 승인 시 POST /api/products            │
              ▼                                                                       ▼
[ 추천 · batch/serving/ (FastAPI, 8300, 내부 전용) ]              [ 처리 · streaming/ (Spark 3.5.6) ]
 GET  /api/recommend    items 10 + hero + banners 6 (전용 칸 5·6 = 신규 브랜드)   Q1 raw_sink → raw_events (Parquet)
 POST /api/products     등록 즉시 카탈로그 편입 (SSAFY Beauty 8개 편입됨)         Q2 clean_events (스키마 검증·중복 제거)
 DELETE /api/products   판매 중단                                                 Q3 derive_facts → 상품·배너 Fact
 POST /api/events       세션 상태 갱신 (Redis 자리, 지금은 메모리)                 Q4 build_marts → content/banner/segment daily Mart
 POST /api/prescription 대시보드 처방 문장 (LLM gpt-4.1-mini, 자동 거부 포함)      Q5 validate → 품질 리포트
        ▲                                                                              │
        │ 모델·산출물 (오프라인 배치 batch/jobs/)                                        ▼
 Sephora 리뷰 844,865건 · 상품 200개                                       [ 소비 ]  브랜드 대시보드 (지금은 mocks/ 표본,
   → 상품 벡터 148차원 · 페르소나 12,000명 · 속성 친화도                              Mart 연결은 데이터·백엔드 협의 중)
   → CF 동시발생 · LTR 278 트리 → batch/ingest/data/serving/

[ 운영 · deploy/ec2-1 ]  docker compose — backend(8080) · recommend(8300) · nginx(443 → /api/ → backend) · Prometheus · Grafana
```

---

## 2. 기술 스택

| 영역 | 기술 | 버전 | 비고 |
| --- | --- | --- | --- |
| 프론트엔드 | React · TypeScript · Vite | 19.2 · 6.0 · 8.2 | 엔트리 3개 — 쇼핑몰 `index.html` · 브랜드 대시보드 `dashboard.html` · 플랫폼 운영 `platform.html`. dev 5173. 프록시: 인증·브랜드·상품·주문·리뷰·피드백 → 8090, `/api/recommend` → 8300, 그 외 `/api` → 8080 |
| | oxlint | 1.79 | ESLint 대신 사용 |
| 쇼핑몰 백엔드 | Spring Boot · JPA · MySQL | 4.1.1 · 21 · 8.4 | `shop_backend/` (8090, MySQL 13306). 로그인(JWT)·브랜드·상품(등록 계약 검증)·주문·결제·리뷰·피드백·정산·판매자 대시보드 |
| 수집 서버 | Spring Boot · Java | 4.1.1 · 21 | `backend/` (8080). `POST /api/events` → Kafka. Actuator + Micrometer 로 Prometheus 메트릭 |
| | springdoc-openapi | 3.1.0 | Swagger UI |
| 메시징 | Apache Kafka (KRaft) | 4.2.0 | 토픽 `activity-events`, 파티션 3, key = `session_id` |
| 스트리밍 | Spark Structured Streaming | 3.5.6 | `streaming/` Q1~Q5. 출력 Parquet. 로컬은 `infra/spark/` compose |
| 추천 · AI | Python · NumPy · scikit-learn | 3.13 · 2.2.6 · 1.7.0 | 상품 벡터 148차원 · 페르소나 속성 친화도 · CF 동시발생 · 학습 결합(HistGradientBoosting 278 트리). sklearn 버전은 모델 pickle 과 고정 |
| | FastAPI · uvicorn · pydantic | 0.141 · 0.52 · 2.13 | **추천 추론 서버** `batch/serving/` (8300, 내부 전용). 추천·배너·상품 등록·처방 문장. `deploy/recommend.Dockerfile` |
| | OpenAI SDK → GMS | gpt-4.1-mini | 대시보드 처방 문장 (`POST /api/prescription`, 온도 0·JSON 스키마 강제). 키 없으면 이 엔드포인트만 503 |
| | sentence-transformers | — | 리뷰·상품 텍스트 임베딩 (GPU, 배치 산출물용). 정확도 목적 리뷰 임베딩은 기각 |
| 시뮬레이터 | Python 생성기 | — | PC 9,900명 합성 로그 · 배너 이벤트 · 피드백 시연 데이터 |
| | Playwright (Chromium) + OpenAI SDK → GMS | gpt-4.1-nano | PA 100명이 실제 브라우저를 조작. `--local-model` 로 Qwen2.5 도 가능 |
| 운영 | Docker Compose · nginx · certbot | — | EC2-1 (`deploy/ec2-1/`): backend · recommend · nginx(HTTPS) · Prometheus · Grafana |
| | Prometheus · Grafana | 3.5.0 · 12.1.0 | `monitoring/` 대시보드 2종(backend-overview · collector-validation) 프로비저닝 |
| 데이터 | Sephora 리뷰 데이터셋 | — | 리뷰 844,865건 · 상품 200개 · 페르소나 12,000명(9,900 + 홀드아웃 2,000×2 + 에이전트 100) |
| | 시연 브랜드 | — | SSAFY Beauty 8개 상품 (`simulator/feedback/products.ssafy-beauty.json`) — 등록 경로로 추천 카탈로그에 편입 |

---

## 3. 현재 폴더 구조

```
S15P21A306/
├── README.md                        이 문서
├── .gitignore
│
├── contracts/                       ★ 팀 계약. 여기가 바뀌면 여러 모듈이 동시에 영향받음
│   ├── README.md                        계약 디렉터리 기준 — 단일 출처와 변경 규칙
│   ├── event-schema.json                Raw Event JSON Schema (Collector 통과 후 계약)
│   ├── event-properties-schema.md       Event별 properties·enum·필수값 계약
│   ├── raw-event-schema.md              Raw Dataset grain·물리 key·컬럼 계약
│   ├── processed-schema.md              Processed Dataset grain·key·컬럼 계약
│   ├── persona-schema.md                Persona·평가 split·Simulation Run 계약
│   ├── dw-schema.md                     DW Dimension·Mart grain·컬럼 계약
│   ├── validate_events.py               이벤트 파일을 스키마로 검증하는 CLI
│   ├── coverage_report.py               한 실행이 계약의 어디를 밟았는지 + properties 위반
│   ├── requirements-validator.txt       검증기 의존성 (jsonschema[format])
│   ├── samples/ · tests/                유효/무효 이벤트 표본과 계약 테스트
│   ├── persona/                     ★ 중첩 Persona JSON → 계약 평탄 테이블 8종 (데이터)
│   │   ├── build_persona_tables.py      평탄화. 계약 컬럼표(TABLE_SPECS)의 단일 출처
│   │   ├── holdout_rule.py              계약 §7.1 seed / holdout_target / excluded 판정
│   │   ├── validate_persona_tables.py   계약 §11·grain·nullable·enum·누출 검사
│   │   ├── compare_holdout_rules.py     계약 §7.1과 eval_metadata 정답 규칙 대조
│   │   ├── test_persona_tables.py       원천에 드문 경우의 단위 테스트
│   │   ├── README.md                    실행 방법·표본 검증 결과·미결 항목
│   │   └── data/                        JSONL 산출물 — 커밋하지 않는다 (결정론적 재생성)
│   ├── feedback-classification.md       ★ 고객 피드백 분류 계약 0.2.0 — 축은 고객 입력, 그 축 안 카테고리 다중, 언급 수 집계 (AI)
│   ├── feedback-category-vocab.json     피드백 어휘 — 5축 20종 + other (분류기는 여기서만 고른다)
│   ├── feedback-banned-terms.json       금지어 599개 (MIT) — 걸리면 hidden_by_default, 입력은 안 막음
│   ├── product-feature-spec.md          상품 벡터 148차원 명세 — 블록 구성·인코딩·가중치
│   ├── product-feature-vocab.json       인코딩 어휘집 `0.4` — 9개 블록 (brand 포함)
│   ├── product-registration-spec.md     브랜드가 상품을 등록할 때의 입력 필드·어휘 제약·파생값
│   ├── product-form-labels-ko.json      등록 폼 어휘의 한국어 표시 문구 57개 (어휘집에서 생성)
│   ├── validate_product_registration.py 등록 상품 JSON 을 계약으로 검증하는 CLI
│   ├── event-attribution-contract.md    통합몰 Event 의 브랜드 귀속 계약 (데이터)
│   ├── user-trait-weights.json          사용자 성향 가중치 30일 창 (`user-trait-v1-proposed`)
│   ├── prescription-api-spec.md         대시보드 처방 문장 API (AI↔프론트) — 요청·응답·거부 코드·v0.1 과의 차이 (Jira 220)
│   └── recommendation-io-spec.md        추천 입출력 계약 (백엔드↔AI) — 점수 식·LTR·§5 API·§5-1 배너
│                                        규칙 5-1: 정독한 미전환 상품은 약한 긍정 (2026-09-03 개정)
│                                        §5 persona_id 선택(익명 cold_start)·reserved_filled (2026-09-09, Jira 214)
│
├── docs/
│   ├── system-architecture*.png         시스템 구성도 3장
│   ├── dashboard/                   대시보드·기획 문서 — 재설계 명세 · AI 인사이트 규칙 · 성향 배너 플랜 · 포지셔닝 근거 · 한국 브랜드 시드 · Jira 재정렬
│   ├── ai/                          추천 알고리즘 설계·검증 (AI)
│   │   ├── recommendation-design.md     CBF 전체 설계안 — 점수 공식, 행동 가중치, 스케줄, MMR
│   │   ├── cbf-technical-review.md      코사인 계산 구조 실측 검증서
│   │   ├── product-feature-sample.md    상품 6개 인코딩 샘플 (생성물 — build_feature_sample.py)
│   │   ├── persona-feature-port.md      페르소나 피처 이관 계획·검증 기준·결과
│   │   ├── exposure-role.md             노출이 어느 자리에서 무엇을 하는가 — 다섯 자리와 섞어 말하면 안 되는 것
│   │   ├── ingredient-domain-guide.md   성분 도메인 가이드 — 성분↔피부·고민, 행동과 잇는 법
│   │   └── evaluation-framework.md     ★ 추천 평가 체계 (팀 합의) — 오프라인/동적/LLM 3축 분리
│   │                                     대표 지표·부록(기각된 안 포함)이 모두 여기 모입니다
│   │
│   ├── analytics/                   행동 로그·DW 설계 (프론트·데이터)
│   │   ├── behavior-log-design.md       왜 그 자리에 그 이벤트를 두었는지
│   │   ├── event-logging-design.md       화면 Trigger·KPI 연결·구현 현황
│   │   ├── log-transport-contract.md    전송 주기·재시도·actor_type 판정
│   │   ├── raw-event-storage-design.md  Raw 저장 구조·Delta 전환·검증 계획
│   │   ├── dw-design.md · spark-processing-design.md   Mart 적재·Spark 처리 설계
│   │   ├── persona-design.md             Persona 생성·표본·추천 연결 설계
│   │   ├── marketing-signal-research.md · event-weight-rationale.html
│   │   ├── event-guide.html              팀·기획용 행동 기록 안내서 (생성물)
│   │   └── tools/build-event-guide.mjs   안내서 생성 스크립트
│   │
│   ├── dashboard/                   B2B 대시보드 조사·설계 (프론트)
│   │   ├── b2b-dashboard-research.md    화면의 존재 이유 — 시장 조사와 설계 규칙
│   │   ├── frontend-dashboard-design.md · metric-basis.md   화면 설계 · 지표별 산출 근거
│   │   ├── collective-insight-data-boundary.md  합동 인사이트 — 공유 범위와 지켜야 할 경계
│   │   ├── insight-catalog.md           무엇을 어떻게 뽑아 누구에게 주나 (최종 그림)
│   │   ├── beauty-optimization-backlog.md  성분·피부·산업 특화 제안 목록
│   │   ├── data-event-backlog.md        AI·백엔드·데이터에 보낸 수집·수정 요청 (S1~S7)
│   │   └── deck-update-plan.md          중간발표 덱 반영 계획
│   ├── data/                        프론트 초기 UI용 샘플 데이터 (상품 8 · 리뷰 40)
│   │   └── README.md · field_stats.json · product-images.md
│   ├── planning/                    ★ 확정 기획 정본 (팀 공통)
│   │   ├── service-plan.md              최종 기획 — 통합 쇼핑몰 1개에 브랜드가 입점
│   │   └── feature-spec-status.md       기획 대비 구현 상태 표
│   ├── backend-ingestion-backpressure.md  수집 과부하 응답 정책 (백엔드)
│   └── git-convention.md            커밋 메시지·브랜치 전략 (팀 공통)
│
├── batch/                           ★ Spark Batch — 상품·페르소나 피처와 추천 계산
│   ├── regenerate_all.py            ★ 상품이 바뀌면 여기서부터 다시 만든다 (16단계·mtime 확인)
│   ├── ingest/
│   │   ├── build_feature_vocab.py       어휘집 생성 (문서빈도·블록 가중치)
│   │   ├── build_products_json.py       상품 200개 카탈로그 생성 (사이즈 변형 병합)
│   │   ├── build_affinity_lift.py       속성 친화도 4,000행 (lift 기반) — 개인 폴더에서 이관
│   │   ├── build_form_labels.py         등록 폼의 한국어 라벨 생성 (regenerate_all 2.5단계)
│   │   ├── build_feature_sample.py      샘플 6개 산출물 + 문서 생성
│   │   ├── test_feature_sample.py       산출물·문서가 코드와 어긋나지 않았는지
│   │   └── data/
│   │       ├── README.md                    산출물 목록과 재생성 방법
│   │       ├── products_200.json            상품 200개 (원본 27컬럼 + 병합 이력 + 리뷰 통계)
│   │       ├── affinity_lift.csv            속성 친화도 4,000행 (200상품 × 20세그먼트)
│   │       ├── affinity_power.csv           속성별 판별력 비교 (분석용)
│   │       ├── concern_from_reviews.npz     리뷰에서 뽑은 concern 점수
│   │       ├── excluded_products.json       제외 상품 목록과 사유
│   │       ├── eval_metadata.jsonl          평가 seed/target 정본 (9,900행)
│   │       ├── eval_metadata_agent.jsonl    같은 규칙의 PA 대조군 (100행)
│   │       ├── eval_metadata_holdout_a.jsonl · _holdout_b.jsonl
│   │       │                                 ★ 한 번도 안 쓴 리뷰어에서 뗀 홀드아웃
│   │       │                                 (고르기는 a · 확인은 b)
│   │       ├── text_embeddings.npz         seed 리뷰·상품 임베딩 384차원 (13.7MB)
│   │       ├── feature_sample.json          샘플 6개의 블록별 값·벡터·친화도
│   │       └── serving/                     ★ 백엔드 RankingService 입력
│   │           ├── README.md                    서빙 산출물의 열·갱신 시점·적재 주의
│   │           ├── product_feature.jsonl        상품 200개 × 148차원 + prior
│   │           ├── attribute_affinity.csv       친화도 4,000행 (계약 열)
│   │           ├── item_cooc.npz                200×200 동시발생 + 지지자 수 (CF)
│   │           ├── ltr_model.pkl · ltr_model_meta.json
│   │           │                                 ★ 학습 결합 모델 (트리 278개)
│   │           ├── ranking_golden.json          순위 대조용 기준 결과 (페르소나 20명)
│   │           ├── banner_axes.json             배너 축 6종의 상품 목록
│   │           ├── backend_tables.sql           ★ 아래 CSV 6종의 CREATE TABLE
│   │           ├── feature_block.csv            148차원을 블록으로 자르는 법
│   │           ├── ingredient_vocab.csv · concern_vocab.csv
│   │           │                                 어휘 마스터 (원문·한국어·빈도)
│   │           ├── product_ingredient.csv       상품 × 성분 (위치가중값 850행)
│   │           ├── product_concern.csv          상품 × 고민 상위 2축 (363행)
│   │           ├── ingredient_skin_affinity.csv 피부타입 × 성분 (76행)
│   │           └── product_ingredient_position.csv · product_concern_top2.csv
│   │                                             · ingredient_skin_lift.csv
│   │                                             대시보드용 (이름 붙은 비정규화 판)
│   ├── jobs/
│       ├── product_encoder.py           상품 → 148차원 콘텐츠 벡터 인코더
│       ├── behavior_weights.py          `frontend/src/types/log.ts` 를 직접 읽는 행동 가중치 로더
│       ├── user_vector.py               이벤트 → v_u⁺ / v_u⁻ 집계
│       ├── build_user_vectors.py        Spark 산출물·JSONL → 사용자 벡터 상태 (Redis 형태)
│       ├── persona_feature.py           페르소나 속성 → 상품별 친화도 (200,)
│       ├── recommender.py               점수 계산·노출 정책·MMR·신규 브랜드 전용 칸(reserved)
│       ├── ltr_features.py             ★ 학습 결합 피처 19개 — 학습과 서빙이 같은 코드
│       ├── train_ltr.py                 학습 결합 모델 학습 (train 5,954명)
│       ├── build_cooc.py                아이템-아이템 동시발생 (CF 입력, 누출 차단)
│       ├── export_features.py           서빙용 산출물 + 순위 대조 기준 생성
│       ├── export_backend_tables.py    ★ 백엔드 적재용 정규화 테이블 6종 + DDL
│       ├── export_dashboard.py          대시보드용 파생 산출물 (이름 붙은 판)
│       ├── banner_axes.py               배너 축 6종의 상품 목록
│       ├── eval_metadata.py            ★ seed/target 정본 — 세 축이 같은 문제를 풀게 한다
│       ├── hidden_preference.py        행동 생성을 추천 점수에서 떼어내는 통제 장치
│       ├── build_text_embeddings.py    seed 리뷰·상품 텍스트 임베딩 (GPU 21초)
│       ├── eval_persona_feature.py      9,900명 leave-last-out 검증 (오프라인 축)
│       ├── eval_dynamic.py             동적 시뮬레이션 (Dynamic Recall@10)
│       ├── eval_review_replay.py       실제 리뷰 이력 순차 재생
│       ├── persona_split.py            train/valid/test 분할 (split-v1)
│       ├── eval_cbf_flow.py            로그 -> 상태 -> 점수 -> 정책 -> MMR 전 구간 검증
│       ├── eval_registered_brand_share.py  등록 상품이 같은 브랜드를 얼마나 끌어오나 — 크기 맞춘 원천 브랜드와 대조 (Jira 217)
│       ├── concern_from_reviews.py · explore_choice.py
│       └── test_*.py                    단위 테스트 12개 (피처·산출물·사용자 벡터·MMR·전용 칸·배너 축·cold start·백엔드 테이블·eval_metadata)
│   └── serving/                     ★ 추천 추론 서버 — 계약 §5·§5-2 참조 구현 (Jira 206·214·216), 포트 8300
│       ├── recommend_server.py          FastAPI: GET /api/recommend(items · hero · banners) · POST/DELETE /api/products · POST /api/prescription · POST /api/events · /health
│       ├── banners.py                   §5-1 hero·배너 6칸 조립 — 축 값(session/profile/coldstart)·전용 칸 5·6·reason 단일 key (Jira 218)
│       ├── prescription.py              대시보드 처방 문장 POST /api/prescription — v0.3 프롬프트·JSON 스키마 강제·§6 자동 거부·저장 (Jira 220)
│       ├── catalog_registry.py          등록 입력 → §4 파생 → 계약 검사 → 인코딩 → 카탈로그 확장. CLI 로 카탈로그 파일 변환
│       ├── bench_recommend.py           응답 시간 실측 (p50/p95)
│       ├── requirements.txt             fastapi · uvicorn · httpx
│       └── test_recommend_server.py · test_catalog_registry.py · test_banners.py · test_prescription.py   (63개, 처방은 가짜 LLM)
│
├── streaming/                       ★ Spark Structured Streaming (데이터)
│   ├── jobs/
│   │   ├── raw_sink_job.py              Kafka activity-events → Raw Parquet
│   │   ├── clean_events_job.py          검증·중복 제거 → cleaned_events
│   │   ├── derive_facts_job.py          Fact 파생
│   │   ├── build_marts_job.py           Mart 집계
│   │   ├── validate_pipeline_job.py     품질 검증 리포트
│   │   └── behavior_weights.py          batch/jobs/behavior_weights.py 를 Spark 에서 재사용하는 어댑터
│   ├── tests/                           raw sink · data marts · brand attribution · banner/trait marts (Spark)
│   └── README.md
│
├── simulator/                       ★ 부하·행동 로그 생성기 (AI)
│   ├── feedback/                    ★ 고객 피드백 시연 데이터 — 생성·자동 분류·금지어 (Jira 200~202)
│   │   ├── gen_feedback.py              페르소나 × 상품 × 축 → 개선 요청 99건 (nano)
│   │   ├── classify_feedback.py         고른 축 안의 카테고리를 목록에서 전부 고르기, 건당 호출 1회 (사람 정답 50건 F1 94%)
│   │   ├── banned_terms.py              금지어 대조 — LLM 없음
│   │   ├── products.ssafy-beauty.json   ★ 시연용 자사 브랜드 SSAFY Beauty 상품 8개 (SB000001~) — 추천 카탈로그엔 아직 미포함
│   │   └── data/  feedback_demo.jsonl · feedback_classified.sample30.jsonl
│   ├── collector_client.py              수집 API 전송 (429/503 백프레셔 대응) — 공용
│   ├── test_collector_client.py
│   ├── generator/
│   │   ├── gen_behavior_logs.py         PC 9,900명 합성 로그 (1인당 약 600건) — 노출 정책 --exposure · 추천 서버 연동 --recommend-url (Jira 221)
│   │   ├── recommend_client.py          추천 서버 클라이언트 — items·hero·banners 식별자를 이벤트에 그대로, 행동은 /api/events 로 상태 전송. 없으면 폴백
│   │   ├── build_persona_style.py       리뷰에서 페르소나 6축 스타일 추출
│   │   └── test_gen_behavior_logs.py · test_recommend_client.py · README.md
│   ├── agents/
│   │   ├── agent_runner.py               PA 100명 — 실제 브라우저로 프론트를 조작
│   │   ├── analyze_run_quality.py        실행 두 개를 대 보고 로그 품질을 재는 도구
│   │   ├── model_server.py               GPU 서버에 모델만 올리는 최소 서버 (--api-base 로 연결)
│   │   ├── data/                         PA 실행 산출물 (agent_events*.jsonl · *_decisions.jsonl)
│   │   └── README.md                     모델 선택 세 가지·러너가 지키는 계약
│   └── personas/
│       ├── build_personas.py            페르소나 추출 (--holdout 로 미사용 인원에서 홀드아웃)
│       ├── holdout_exclude_dupaccounts.txt  같은 본문을 쓴 계정 12명 (홀드아웃 제외)
│       └── data/  personas_9900.json · personas_100_agent.json · persona_style.json
│                 personas_holdout_a.json · personas_holdout_b.json (각 2,000명)
│                 persona_sampling_report.json · holdout_a/b_sampling_report.json (표본 추출 근거) · README.md
│
├── backend/                         Spring Boot 수집 서버 (백엔드) — 8080
│   ├── src/main/java/com/cosmetic/collector/   POST /api/events → Kafka activity-events
│   ├── README.md · BACKEND_INGESTION_POLICY.md
│   └── build.gradle · gradlew
│
├── shop_backend/                    Spring Boot 쇼핑몰 백엔드 (백엔드) — 8090, MySQL 13306
│   ├── src/main/java/com/cosmetic/shopbackend/  컨트롤러 8종 — identity·brand·catalog·commerce·feedback·dashboard·admin·settlement
│   ├── mysql-erd.sql · mysql-erd.md · ERD-TABLES.md   테이블 29개 DDL·설명
│   └── MYSQL-SETUP.md · docker-compose.mysql.yml     로컬 MySQL 실행
│
├── deploy/                          EC2 배포 (백엔드·인프라·AI)
│   ├── backend.Dockerfile · nginx.Dockerfile · nginx/default.conf   nginx 는 /api/ → backend:8080 만
│   ├── recommend.Dockerfile · recommend.Dockerfile.dockerignore · recommend-entrypoint.sh   ★ 추천 서버 이미지 (AI, Jira 219) — BuildKit 필수
│   └── ec2-1/                           docker-compose.yml (backend · recommend · nginx · Prometheus · Grafana) · README.md
│
├── kafka/README.md                  Kafka 구조·이벤트 처리 명세 (백엔드·인프라)
├── infra/
│   ├── kafka/                           로컬 Kafka (docker-compose, topics.sh/ps1)
│   ├── spark/                           로컬 Spark 클러스터 (docker-compose · run-pipeline · verify-e2e)
│   └── create-network.sh/ps1            공용 docker 네트워크
├── monitoring/                      Prometheus 설정·Grafana 대시보드 프로비저닝
│
├── frontend/                        React 19 + TypeScript + Vite 8
│   ├── index.html · dashboard.html · platform.html   엔트리 3개
│   ├── package.json / tsconfig*.json / vite.config.ts / .oxlintrc.json
│   │                                    vite proxy: /api/auth·brands·products·orders·reviews·feedback·seller·admin → 8090, 그 외 /api → 8080
│   ├── plugins/image-cache.ts · scripts/  (warm-images · 상품 URL·이미지 수집 스크립트)
│   ├── public/  brand/ · images/ · icons.svg
│   └── src/
│       ├── main.tsx / App.tsx
│       ├── types/
│       │   ├── log.ts               ★ 행동 로그 이벤트 계약 (`frontend/src/types/log.ts`) — 이벤트 36종, 섹션,
│       │   │                          콘텐츠 종류, intent 분류, LogEnvelope
│       │   └── product.ts / review.ts / persona.ts / cart.ts
│       ├── hooks/                   로그 수집 훅 (스크롤·섹션·선택·주목 신호·이탈 요약)
│       ├── lib/
│       │   ├── logger.ts                이벤트 조립·버퍼링·전송 (재시도·백오프 포함)
│       │   ├── section.ts               섹션 ↔ 콘텐츠 종류 매핑
│       │   └── image.ts / image-widths.ts / format.ts
│       ├── pages/                   상품 목록·상세·장바구니
│       ├── dashboard/               브랜드 대시보드 화면 (별도 엔트리)
│       ├── platform/                HWABUN 플랫폼 운영 화면 (별도 엔트리)
│       ├── components/              product · review · layout · devtools · common
│       ├── mocks/                   상품·리뷰·페르소나 샘플 JSON
│       └── styles/ · index.css
│
└── 1차 평가/                        평가 제출물 (팀원별 폴더)
```

