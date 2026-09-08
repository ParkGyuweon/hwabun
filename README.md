# S15P21A306

**HWABUN** — 1인·소상공인 뷰티 브랜드가 나눠 쓰는 쇼핑몰(**BLOOM**)과
인사이트 대시보드입니다. 행동 로그를 모아 브랜드에게 지표로 돌려주고,
그 위에서 상품 추천을 계산합니다.

## 1. 시스템 아키텍처

가상 사용자가 쇼핑몰을 쓰고, 그 행동 로그가 수집·처리되어 브랜드 대시보드로
나오는 한 줄기 파이프라인입니다. 추천은 그 옆에서 배치로 계산됩니다.

```
[ 행동 생성 ]                     [ 서비스 ]                  [ 수집 ]

 simulator/generator             frontend (React)           backend (Spring Boot)
 PC 9,900명 · 합성 로그   ────▶   상품 목록·상세·장바구니  ────▶  POST /api/events
                                 lib/logger.ts                  Collector
 simulator/agents        ────▶   이벤트 조립·버퍼링·재시도        백프레셔 429/503
 PA 100명 · Playwright                                              │
 + LLM (실제 브라우저 조작)                                          ▼
                                                        Kafka  activity-events
                                                         key = session_id
                                                                    │
                                                                    ▼
[ 처리 ]  streaming/  Spark Structured Streaming
   Q1 raw_sink       Kafka → raw_events (Parquet)
   Q2 clean_events   검증·중복 제거 → cleaned_events
   Q3 derive_facts   Fact 파생
   Q4 build_marts    Mart 집계
   Q5 validate       품질 검증 리포트
        │
        ▼
[ 소비 ]  frontend/src/dashboard — B2B 대시보드 (별도 엔트리)


[ 추천 ]  batch/ — 위 파이프라인과 분리된 오프라인 배치
   Sephora 리뷰 844,865건
     → 상품 벡터 148차원 · 페르소나 9,900명 · 속성 친화도 4,000행
     → train_ltr.py    학습 결합 모델 (트리 278개)
     → recommender.py  점수 + MMR
     → batch/ingest/data/serving/  서빙용 산출물
          ┈┈▶ (미연결) 백엔드 RankingService 가 없어 화면 노출에 반영되지 않습니다
   대표 지표 Recall@10 = 43.95% — CBF + CF 가점 + 학습 결합, holdout_a 2,000명
   ┈┈▶ 확인 집합 holdout_b 43.20% · 선형 대비 +5.80 / +3.95%p (둘 다 CI 가 0 제외)
   ┈┈▶ 23.39%(CBF 단독) → 38%대(CF 채택) → 43%대(학습 결합) 순으로 올랐다 (부록 S·T)
   ┈┈▶ 세 평가 축이 0.6%p 안에 모인다 — 오프라인 43.95 · 재생 43.95 · 동적 44.05%

[ 운영 ]  deploy/ec2-1  docker compose — backend · nginx · Prometheus · Grafana
```

**계약이 모듈을 잇습니다.** 이벤트는 `contracts/event-schema.json`, 추천 입출력은
`contracts/recommendation-io-spec.md` 가 단일 출처입니다. 기준은
[`contracts/README.md`](contracts/README.md) 를 따릅니다.

**아직 없는 것** — 백엔드 `RankingService`, 사용자 벡터 Redis 적재, 서빙 테이블 MySQL.
추천은 현재 배치 산출물까지만 나옵니다.

---

## 2. 기술 스택

| 영역 | 기술 | 버전 | 비고 |
| --- | --- | --- | --- |
| 프론트엔드 | React · TypeScript · Vite | 19.2 · 6.0 · 8.2 | 쇼핑몰과 대시보드가 별도 엔트리 (`index.html` / `dashboard.html`) |
| | oxlint | 1.79 | ESLint 대신 사용 |
| 백엔드 | Spring Boot · Java | 4.1.1 · 21 | 수집 서버. `POST /api/events` → Kafka |
| | springdoc-openapi | 3.1.0 | API 문서 |
| | Actuator + Micrometer | — | Prometheus 메트릭 노출 |
| 메시징 | Apache Kafka | 4.2.0 | 토픽 `activity-events`, 파티션 3, key = `session_id` |
| 스트리밍 | Spark Structured Streaming | 미고정 | Q1~Q5. 출력은 Parquet |
| 배치 · AI | Python · NumPy · pandas | — | 상품 벡터·페르소나·추천 점수 계산 |
| | sentence-transformers | — | 리뷰·상품 텍스트 임베딩 384차원 (GPU) |
| 시뮬레이터 | Playwright (Chromium) | — | PA 에이전트가 실제 브라우저를 조작 |
| | OpenAI SDK → GMS | — | `gpt-4.1-nano`. 100명 × 15턴 ≈ 900 크레딧 |
| | transformers (로컬) | — | `--local-model`. Qwen2.5-3B 기준 크레딧 0 |
| 운영 | Docker Compose · nginx | — | EC2-1 배포 (`deploy/ec2-1/`) |
| | Prometheus · Grafana | 3.5.0 · 12.1.0 | `monitoring/` 에 대시보드 프로비저닝 |
| 데이터 | Sephora 리뷰 데이터셋 | — | 리뷰 844,865건 · 상품 200개 |

---

## 3. 현재 폴더 구조

지금 레포에 실제로 들어있는 것입니다. (최종 확인 2026-09-07 오후)

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
│   ├── feedback-classification.md       ★ 고객 피드백 자동 분류 계약 — 입력 5필드·출력·금지어 플래그 (AI)
│   ├── feedback-category-vocab.json     피드백 어휘 — 5축 20종 + other (분류기는 여기서만 고른다)
│   ├── feedback-banned-terms.json       금지어 599개 (MIT) — 걸리면 hidden_by_default, 입력은 안 막음
│   ├── product-feature-spec.md          상품 벡터 148차원 명세 — 블록 구성·인코딩·가중치
│   ├── product-feature-vocab.json       인코딩 어휘집 `0.4` — 9개 블록 (brand 포함)
│   ├── product-registration-spec.md     브랜드가 상품을 등록할 때의 입력 필드·어휘 제약·파생값
│   ├── product-form-labels-ko.json      등록 폼 어휘의 한국어 표시 문구 57개 (어휘집에서 생성)
│   ├── validate_product_registration.py 등록 상품 JSON 을 계약으로 검증하는 CLI
│   └── recommendation-io-spec.md        추천 입출력 계약 (백엔드↔AI) — 점수 식·가중치 스케줄
│                                        규칙 5-1: 정독한 미전환 상품은 약한 긍정 (2026-09-03 개정)
│
├── docs/
│   ├── ai/                          추천 알고리즘 설계·검증 (AI)
│   │   ├── recommendation-design.md     CBF 전체 설계안 — 점수 공식, 행동 가중치, 스케줄, MMR
│   │   ├── cbf-technical-review.md      코사인 계산 구조 실측 검증서
│   │   ├── product-feature-sample.md    상품 6개 인코딩 샘플 (생성물 — build_feature_sample.py)
│   │   ├── persona-feature-port.md      페르소나 피처 이관 계획·검증 기준·결과
│   │   ├── exposure-role.md             노출이 어느 자리에서 무엇을 하는가 — 다섯 자리와 섞어 말하면 안 되는 것
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
│   └── jobs/
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
│       ├── concern_from_reviews.py · explore_choice.py
│       └── test_*.py                    단위 테스트 (피처·산출물·사용자 벡터·전용 칸·CF 홀드아웃 제외)
│
├── streaming/                       ★ Spark Structured Streaming (데이터)
│   ├── jobs/
│   │   ├── raw_sink_job.py              Kafka activity-events → Raw Parquet
│   │   ├── clean_events_job.py          검증·중복 제거 → cleaned_events
│   │   ├── derive_facts_job.py          Fact 파생
│   │   ├── build_marts_job.py           Mart 집계
│   │   └── validate_pipeline_job.py     품질 검증 리포트
│   ├── tests/ · README.md
│
├── simulator/                       ★ 부하·행동 로그 생성기 (AI)
│   ├── feedback/                    ★ 고객 피드백 시연 데이터 — 생성·자동 분류·금지어 (Jira 200~202)
│   │   ├── gen_feedback.py              페르소나 × 상품 × 축 → 개선 요청 99건 (nano)
│   │   ├── classify_feedback.py         계약 어휘 목록에서 고르기, 건당 호출 1회
│   │   ├── banned_terms.py              금지어 대조 — LLM 없음
│   │   └── data/  feedback_demo.jsonl · feedback_classified.sample30.jsonl
│   ├── collector_client.py              수집 API 전송 (429/503 백프레셔 대응) — 공용
│   ├── test_collector_client.py
│   ├── generator/
│   │   ├── gen_behavior_logs.py         PC 9,900명 합성 로그 (1인당 약 600건) — 노출 정책 --exposure
│   │   ├── build_persona_style.py       리뷰에서 페르소나 6축 스타일 추출
│   │   └── test_gen_behavior_logs.py · README.md
│   ├── agents/
│   │   ├── agent_runner.py               PA 100명 — 실제 브라우저로 프론트를 조작
│   │   ├── analyze_run_quality.py        실행 두 개를 대 보고 로그 품질을 재는 도구
│   │   ├── model_server.py               GPU 서버에 모델만 올리는 최소 서버 (--api-base 로 연결)
│   │   └── README.md                     모델 선택 세 가지·러너가 지키는 계약
│   └── personas/
│       ├── build_personas.py            페르소나 추출 (--holdout 로 미사용 인원에서 홀드아웃)
│       ├── holdout_exclude_dupaccounts.txt  같은 본문을 쓴 계정 12명 (홀드아웃 제외)
│       └── data/  personas_9900.json · personas_100_agent.json · persona_style.json
│                 personas_holdout_a.json · personas_holdout_b.json (각 2,000명)
│                 persona_sampling_report.json (표본 추출 근거) · README.md
│
├── backend/                         Spring Boot 수집 서버 (백엔드)
│   └── src/main/java/com/cosmetic/collector/   POST /api/events → Kafka activity-events
│
├── deploy/                          EC2 배포 (백엔드·인프라)
│   ├── backend.Dockerfile · nginx.Dockerfile · nginx/default.conf
│   └── ec2-1/                           docker-compose.yml · prometheus.yml
│
├── kafka/README.md                  Kafka 구조·이벤트 처리 명세 (백엔드·인프라)
├── infra/kafka/                     로컬 Kafka (docker-compose, topics.sh/ps1)
├── monitoring/                      Grafana 대시보드·프로비저닝
│
├── frontend/                        React 19 + TypeScript + Vite 8
│   ├── index.html · dashboard.html
│   ├── package.json / tsconfig*.json / vite.config.ts / .oxlintrc.json
│   ├── plugins/image-cache.ts · scripts/warm-images.ts
│   ├── public/
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
│       ├── dashboard/               B2B 대시보드 화면 (별도 엔트리)
│       ├── components/              product · review · layout · devtools · common
│       ├── mocks/                   상품·리뷰·페르소나 샘플 JSON
│       └── styles/ · index.css
│
└── 1차 평가/                        평가 제출물 (팀원별 폴더)
```

---

## 4. 참고한 폴더 구조

아래는 참고한 구조입니다. 현재 구조는 여기서 `contracts/` · `frontend/` · `batch/` · `simulator/` 일부만 채워진 상태입니다.

```
cosmetic-recsys/
├── docker-compose.yml
├── README.md
│
├── contracts/                       팀 전체의 계약. 여기가 바뀌면 4개 모듈이 동시에 영향받음
│   ├── event-schema.json            이벤트 봉투+페이로드 스키마 (JSON Schema)
│   ├── event-taxonomy.md            event_type 사전: product.click, section.view, scroll.depth ...
│   ├── user-feature-spec.md         Redis에 저장될 유저 Feature 자료구조 정의
│   └── api-spec.yaml                백엔드↔프론트 REST 명세 (OpenAPI)
│
├── frontend/                        Vue/React
│   ├── src/tracking/
│   │   ├── tracker.ts               이벤트 버퍼링 후 묶어서 POST. 개별 전송 금지
│   │   ├── scrollDepth.ts           25/50/75/100% 통과 시점만 기록
│   │   ├── dwellTime.ts             visibilitychange로 active/total duration 분리 측정
│   │   ├── sectionObserver.ts       IntersectionObserver로 섹션별 노출·체류 감지
│   │   └── sessionExit.ts           이탈 시 sendBeacon으로 잔여 버퍼 flush
│   ├── src/pages/                   상품목록·상세·검색·장바구니
│   └── src/components/
│
├── backend/                         Spring Boot
│   ├── collector/                   프론트 로그 수신 → Kafka 투입
│   │   ├── EventController          POST /api/events (배열 수신)
│   │   ├── EventValidator           contracts 스키마 검증, 불량 이벤트 격리
│   │   └── KafkaProducerService     partition_key=session_id로 전송. 동기 처리 금지
│   ├── product/                     상품 조회 API (MySQL)
│   ├── recommend/
│   │   ├── RankingService           Redis 유저Feature × MySQL 상품Feature → 정렬
│   │   └── AbTestService            A/B 그룹 배정, 노출 정책
│   └── config/                      Kafka·Redis·JPA 설정
│
├── simulator/                       부하 발생기. 실서비스 로직 아님
│   ├── personas/
│   │   ├── distribution.py          피부타입·연령 분포 (Sephora·논문 근거)
│   │   ├── rule_based.py            확률 상태머신: 검색→클릭→비교→장바구니→구매/이탈
│   │   └── llm_agent.py             LLM 페르소나 100명 (Claude API)
│   ├── scenarios/
│   │   ├── normal_day.py            평시 트래픽, 시간대 가중
│   │   └── sale_burst.py            세일 버스트: 배경 + 급증 + 지수감쇠
│   ├── event_builder.py             contracts 스키마대로 이벤트 조립·검증
│   ├── producer.py                  Kafka 직접 전송 (collector 우회)
│   └── main.py                      CLI: --scenario sale --personas 9900 --tps 2000
│
├── streaming/                       Spark Structured Streaming. 분산 트랙 핵심 증명 대상
│   ├── jobs/
│   │   ├── user_feature_job.py      Kafka 구독 → 세션 윈도우 집계 → Redis 갱신
│   │   ├── realtime_stats_job.py    실시간 인기상품·전환율 (대시보드용)
│   │   └── raw_sink_job.py          원본 이벤트를 Parquet로 적재. retention 만료 대비
│   ├── transforms/
│   │   ├── sessionize.py            session_id 기준 묶기, event_time 워터마크
│   │   └── feature_calc.py          관심 성분·가격대·카테고리 선호도 계산
│   └── sinks/
│       └── redis_sink.py            foreachBatch로 Redis write
│
├── batch/                           Spark Batch
│   ├── ingest/
│   │   ├── load_sephora.py          Kaggle 리뷰 109만건 적재
│   │   └── load_ingredients.py      성분 데이터 정규화
│   ├── jobs/
│   │   ├── product_feature_job.py   리뷰+성분 → 상품별 Feature 테이블 → MySQL
│   │   └── daily_rollup_job.py      전일 Parquet 집계 → 유저 Feature 갱신 (MVP 경로)
│   └── quality/validate.py          결측·이상치 체크
│
├── context/                         외부 환경 데이터
│   ├── weather_client.py            기상청 API (기온·습도)
│   ├── airquality_client.py         에어코리아 API (미세먼지)
│   └── scheduler.py                 주기 호출 → Redis 적재
│
└── infra/
    ├── kafka/topics.sh              토픽·파티션 수·replication factor 정의
    ├── spark/                       submit 스크립트, executor 메모리 설정
    ├── monitoring/                  Grafana: TPS·consumer lag·처리 지연 (발표 근거 자료)
    └── loadtest/                    노드 추가 시 처리량 변화 측정
```
