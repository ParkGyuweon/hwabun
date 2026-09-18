# 화분 (HWABUN)

> 여러 소규모 뷰티 브랜드를 한 쇼핑몰에 모아 소비자에게 맞춤 추천하고, 브랜드에는 고객 피드백과 교차 브랜드 인사이트를 제공하는 참여형 뷰티 커머스 플랫폼

소규모 뷰티 브랜드는 고객 의견을 제품에 반영하고 팬덤을 만들 시간도 도구도 없습니다. 화분은 그 일을 플랫폼 기능으로 만듭니다.

소비자는 쇼핑몰 BLOOM 하나에서 회원가입 한 번으로 여러 브랜드를 둘러보고, 자기 피부 고민에 맞는 상품을 추천받고, 써 본 뒤 피드백으로 제품 개선에 참여합니다. 브랜드 사장님은 대시보드에서 자기 상품 성과와 고객 반응을 봅니다. 혼자서는 알 수 없는 교차 브랜드 유입, 유사 브랜드 대비 전환율, 구매 이유 분포까지 볼 수 있습니다.

여러 브랜드를 모으는 이유는 둘입니다. 한 브랜드만으로는 추천 후보가 부족해 알고리즘이 의미를 갖기 어렵고, 모여 있어야 "다른 브랜드를 보던 고객이 우리에게 왔다"는 인사이트가 나옵니다.

### 우리가 만든 것

| | 산출물 |
| --- | --- |
| 서비스 | 통합 쇼핑몰 BLOOM, 브랜드 대시보드 11화면, 플랫폼 운영 화면 |
| 데이터 | 직접 설계한 행동 로그 43종 → Kafka → Spark 5단계(Q1~Q5) → 마트 25종 → DW MySQL(그중 22종 발행) |
| AI | 상품 벡터 148차원(멀티핫 블록 8종 + 스칼라), 학습 결합 추천(LTR 239트리·피처 20개), Kafka 구독 실시간 상태 반영, 대시보드 처방 문장 |
| 검증 | 페르소나 9,900명 합성 로그 약 1,049만 건, LLM 에이전트 100명이 실제 브라우저 조작, 파이프라인 품질 검증 159개 |

기준일 2026-09-18. 아래 수치는 이 날짜에 레포와 배포 서버에서 직접 확인한 값입니다.

## 1. 아키텍처

```
 ① 행동                ② 수집                ③ 분산 처리                 ④ 서빙·분석              ⑤ 소비
 ──────────            ──────────            ─────────────               ─────────────            ─────────
 실제 소비자                                                              추천 서버 8300           쇼핑몰 BLOOM
   │                   수집 서버 8080         Kafka activity-events       · items 10 + hero       · 추천 카드
 페르소나 PC 9,900명 ──▶ POST /api/events ──▶  파티션 3 · key=session_id ──▶ · 실시간 상태 반영  ──▶ · 신규 브랜드 히어로
   │  (생성기)           검증 → Kafka           │                          · 처방 문장(LLM)
 에이전트 PA 100명       백프레셔 429/503       ▼                          · 상품 등록 즉시 편입    브랜드 대시보드
   (Playwright+LLM)                          Spark Q1~Q5                        ▲                 · 11개 화면
                                              Q1 raw_sink   (상시)              │                 · 마트 API 7개
 세 갈래가 같은 스키마                          Q2 clean_events                   │
 frontend/src/types/log.ts (43종)              Q3 derive_facts                 DW MySQL
 contracts/event-properties-schema.md          Q4 build_marts  → 마트 25종      22 테이블
                                               Q5 validate     (검사 159개)      ▲
                                                     │                          │
                                                     └── dw projection ─────────┘
                                                         staging→검증→원자적 스왑

 쇼핑몰 백엔드 8090 (MySQL)  로그인 JWT · 브랜드 · 상품 등록 · 주문 · 결제 · 리뷰 · 피드백 · 정산 · 판매자 대시보드
                            /api/recommend 프록시 · 5분 주기 카탈로그 동기화
 운영  EC2-1  nginx(443) · shop-backend · mysql · backend · recommend · Prometheus · Grafana
       EC2-2  Kafka(KRaft) · Spark master/worker/history · Q1 상시 · 일일 배치 타이머(03:00 KST)
```

행동 로그를 직접 설계해 모으고, 분산 처리해 마트로 쌓고, 그 마트로 추천과 인사이트를 만들어, 브랜드가 대시보드에서 읽는 구조입니다.

실제 소비자와 LLM 에이전트는 진짜 브라우저에서 프론트 로거를 타고, 페르소나는 생성기가 수집기와 같은 봉투를 채워 보냅니다. 세 갈래가 같은 이벤트 스키마를 쓰기 때문에 Q2 아래로는 구분 없이 흐르고, 필요할 때만 `actor_type` 과 `generator_type` 으로 갈라 봅니다.

## 2. 팀 구성과 담당

6명입니다. 괄호 안 숫자는 `git log --no-merges` 로 센 해당 디렉터리 커밋 수입니다.

| 이름 | 역할 | 소유 영역 |
| --- | --- | --- |
| 강하린 | 기획 (PM) | 주차별 평가 보고서, 팀 문서, 일정 |
| 추유림 | 프론트엔드 | `frontend/` (195) · `docs/dashboard/` (60) |
| 최열음 | 백엔드 | `shop_backend/` (47) · `backend/` (30) · `monitoring/` (6) · `Jenkinsfile` |
| 이은솔 | 데이터 | `streaming/` (128) · `contracts/` (135) · `infra/` (16) |
| 송민우 | 인프라 | `deploy/ec2-2/` · dw projection · `streaming/` (23) · `infra/` (10) |
| 박규원 | AI | `batch/` (126) · `simulator/` (115) · `docs/ai/` |

### 강하린 · 기획 (PM)

- 서비스 방향 수립. "소규모 브랜드가 고객 의견을 제품에 반영하는 일을 쉽게 만든다"를 축으로 잡고, 여러 브랜드를 모아야 하는 이유(추천 후보 확보와 교차 발견)를 정리했습니다.
- MUST/SHOULD 기능을 분류하고 통합 인사이트 우선순위 8종을 골랐습니다.
- 매출·정산 원칙 확정. 정산은 주문 DB 기준으로 하고, 행동 로그의 `purchase` 는 전환 분석에만 씁니다.
- 주차별 평가 보고서를 씁니다 (`1차 평가/`).

### 추유림 · 프론트엔드

한 코드베이스에서 엔트리 3개를 빌드합니다. 로그가 여기서 출발합니다.

- 쇼핑몰 BLOOM (`index.html`). 상품 목록·상세·장바구니·주문·결제(PortOne)·리뷰·피드백에 추천 카드와 신규 브랜드 히어로 배너를 붙였습니다.
- 브랜드 대시보드 (`dashboard.html`). 개요, 행동, 콘텐츠, 고객군, 성분, 리뷰, 피드백, 상품, 상품등록, 주문, 내 상품까지 11개 화면입니다.
- 플랫폼 운영 화면 (`platform.html`).
- 행동 로거 (`src/lib/logger.ts`). 이벤트 43종을 조립해 버퍼에 담고 전송하며, 429/502/503 은 백오프로 재시도합니다. 이벤트 스키마 `src/types/log.ts` 는 AI·데이터가 직접 import 해서 가중치를 맞추는 단일 출처입니다.
- 수집 훅 (`src/hooks/`). 스크롤 깊이·정지·되돌아 읽기, 섹션 노출과 체류, 텍스트 선택·복사, 주목 신호(hover/rage/dead click), 이탈 요약을 잡습니다.
- 화면마다 그 자리에 그 이벤트를 둔 근거를 `docs/analytics/behavior-log-design.md` 에 남겼습니다.
- B2B 대시보드 시장 조사와 지표별 산출 근거를 정리했습니다 (`docs/dashboard/`).
- 상품 등록 폼을 추천이 요구하는 스키마에 맞춰 구현하고, 대시보드에서 목 데이터를 전부 걷어냈습니다(값이 없으면 0, "-", "없음").

### 최열음 · 백엔드

- 수집 서버 `backend/` 8080. `POST /api/events` 를 검증하고 Kafka `activity-events` 로 produce 합니다. 파티션 키는 `session_id`, 과부하 때는 429/503 으로 백프레셔를 겁니다. Actuator + Micrometer 로 Prometheus 메트릭을 냅니다.
- 쇼핑몰 백엔드 `shop_backend/` 8090. 도메인 12개(identity/JWT, brand, catalog, commerce, payment, feedback, dashboard, admin, settlement, recommendation 프록시, security, common)로 나뉘고, MySQL 테이블 36개와 ERD 문서가 있습니다.
- 상품 등록 계약을 구현했습니다. 어휘 검증과 unmapped 저장을 포함합니다.
- CI/CD `Jenkinsfile` 9 스테이지. GitLab 연결 확인 → Backend 테스트 → Shop Backend 테스트 → Frontend Docker 빌드 검증 → EC2 구성 변경 감지 → MySQL 마이그레이션 → EC2 배포 → DW 스키마 초기화 → MySQL seed
- 모니터링 `monitoring/`. Prometheus 설정과 Grafana 대시보드 3종(backend-overview, collector-validation, shop-backend-performance)을 프로비저닝합니다.
- nginx 라우팅 (`deploy/nginx/default.conf`). `/api/events` 는 수집 8080 으로, 나머지 `/api/` 는 쇼핑몰 8090 으로 보냅니다.

### 이은솔 · 데이터

Kafka 부터 마트까지 다섯 단계와, 파트 사이를 잇는 계약 문서를 맡습니다.

- Q1 `raw_sink_job`. Kafka 를 읽어 Raw Parquet 으로 적재합니다. Structured Streaming 이라 체크포인트로 오프셋을 이어받고, 파싱에 실패한 레코드도 원문을 남깁니다.
- Q2 `clean_events_job`. 스키마와 의미를 검증하고 `event_id` 정본을 골라 cleaned / bad / duplicate 세 갈래로 나눕니다.
- Q3 `derive_facts_job`. 세션화와 Fact 6종(상품, 구매, 구매사유, 리뷰, 섹션 체류, 콘텐츠 관심), Dimension 2종(dim_product, dim_brand)을 만듭니다.
- Q4 `build_marts_job`. 퍼널 세션 Fact 를 만들고, 상품·퍼널·브랜드 일간 KPI, 재구매, 구매사유, 성분 주간 관심, 고객군, 가격대, 배너, 콘텐츠, 마찰, 이탈, 유입 경로, 교차 브랜드, Commons 코호트까지 마트 25종을 집계합니다. 이 가운데 22종이 DW 발행 대상이고, `banner_daily`·`category_price_reference`·`cross_brand_daily` 는 Parquet 으로만 둡니다.
- Q5 `validate_pipeline_job`. 품질 검증 159개로 grain 유일성, 비율 0~1, 재계산 결정성, 통화 일관성, 부분집합 관계, 상품 귀속을 확인합니다.
- 계약 문서를 소유합니다. `dw-schema.md`, `processed-schema.md`, `raw-event-schema.md`, `event-properties-schema.md`, `persona-schema.md`, `event-attribution-contract.md`, 그리고 대시보드 마트 조회 계약 `dashboard-mart-api-spec.md`
- Job 이 실제로 읽는 계약 파일도 같이 관리합니다. `event-schema.json`(Q2), `purchase-reason-trait-map.json`(Q4·Q5), `user-trait-weights.json`(Q4), `dw/build_ddl.py` 와 `dw/schema.sql`(DDL 생성, projection 이 역참조)
- 노출 정의 통일. 노출 이벤트 셋(product, recommendation, banner)을 CTR 분모에 합산하고, 뒤로가기 재조회는 상세 진입에서 뺍니다.
- 로컬 Kafka·Spark compose 를 만들었습니다 (`infra/`).

### 송민우 · 인프라

- EC2-2 를 구축했습니다. Kafka 브로커(KRaft), Spark 마스터/워커/히스토리, Q1 상시 가동 컨테이너가 떠 있습니다.
- 일일 배치 자동화. `run-daily-batch.sh` 가 flock 으로 중복 실행을 막고, systemd service·timer 가 매일 18:00 UTC(03:00 KST)에 Q2→Q3→Q4→Q5→발행을 한 번에 돌립니다.
- dw projection `publish_user_trait_job`. 마트 Parquet 을 MySQL 로 옮깁니다. staging 테이블에 적재하고 행 수·grain 유일성·NOT NULL 을 검증한 뒤 RENAME 으로 원자적으로 스왑하고 `__old` 를 백업으로 남깁니다. 대상 마트 22종
- DW 스키마 마이그레이션을 관리합니다 (`deploy/ec2-1/migrations/`).
- 퍼널 Fact 와 일간 KPI 마트를 초기 구현했습니다.

### 박규원 · AI

추천 모델과 추천 서버, 그리고 그 둘을 검증할 트래픽을 만드는 시뮬레이터를 맡습니다.

**오프라인 배치 `batch/jobs/`** (파일 37개, 테스트 13개)

- 상품 벡터 148차원 인코딩. 어휘집 `product-feature-vocab.json` 0.7 기준으로 멀티핫 블록 8종(`secondary_category`, `tertiary_category`, `concern`, `ingredient`, `clean`, `texture`, `price_bin`, `brand`)에 스칼라 `rating` 을 더합니다. 블록별 IDF 와 가중치는 문서 빈도에서 계산합니다.
- 페르소나 속성 친화도 4,000행. 상품 200개 × 세그먼트 20개를 lift 로 냅니다.
- CF 아이템 동시발생 `item_cooc.npz`(200×200 + 지지자 수). 학습·평가 누출을 막도록 seed 구간만 씁니다.
- LTR 학습 결합. HistGradientBoosting 트리 239개, 피처 20개, 학습 표본 5,954명 231,005행입니다(`ltr_model_meta.json`). 학습과 서빙이 `ltr_features.py` 한 파일을 같이 씁니다.
- 노출 정책, MMR 다양성, 신규 브랜드 전용 슬롯(`reserve_slots`), 콜드스타트 폴백
- `regenerate_all.py` 가 상품부터 서빙 산출물까지 16단계를 mtime 확인 후 필요한 것만 다시 만듭니다.

**평가**

- 축 3개를 분리합니다. 오프라인 leave-last-out(`eval_persona_feature.py`), 실제 리뷰 이력 순차 재생(`eval_review_replay.py`), 동적 시뮬레이션(`eval_dynamic.py`)
- 홀드아웃은 2세트(각 2,000명)로 두고 a 에서 고른 뒤 b 에서 확인합니다. 정답 정본은 `eval_metadata.py` 가 한 곳에서 만들어 세 축이 같은 문제를 풀게 합니다.
- 행동 생성이 추천 점수를 베끼지 않도록 `hidden_preference.py` 로 통제합니다.

**추천 서버 `batch/serving/` 8300** (테스트 11개 파일, 내부 전용)

| 라우트 | 하는 일 |
| --- | --- |
| `GET /api/recommend` | items 10개 + hero. `persona_id` 가 없으면 익명 콜드스타트 |
| `POST /api/products` · `DELETE /api/products/{id}` · `GET /api/products/{id}` | 등록 상품을 계약 검사·인코딩해 카탈로그에 바로 편입, 판매 중단 |
| `POST /api/events` | 행동 이벤트로 세션 상태 갱신 |
| `POST /api/catalog/sync` | 쇼핑몰 백엔드 ACTIVE 상품 동기화 (5분 주기) |
| `POST /api/prescription` · `GET`·`POST /api/prescription/llm` | 대시보드 처방 문장과 LLM 런타임 스위치 |
| `POST /api/sessions/compact` | 세션 이벤트 로그 압축 |
| `GET /health` | 모델·카탈로그·Kafka·DW 상태 |
| `GET /live` · `/live/stats` · `POST /live/demo/start`·`/stop` | 시연 화면과 재생 제어 |
| `GET /pipeline` · `/pipeline/stats` | 다섯 층(활동·Kafka·Spark·DW·대시보드)을 한 화면에서 읽기 전용으로 |

- 실시간 상태(`kafka_state.py`). `activity-events` 를 별도 컨슈머 그룹으로 구독하고 수동 커밋과 `event_id` dedupe 로 세션 상태를 초 단위로 갱신합니다.
- 세션 영속화(`session_store.py`). 이벤트 로그를 append 하고 기동할 때 재생하며, 주기적으로 compact 합니다.
- 장기 성향(`user_trait.py`). DW `user_trait_daily` 를 읽어 응답에 `long_term_trait` 을 싣습니다. DW MySQL → 스냅샷 → null 3단 폴백이고, `actor_type` 이 `user` 와 `synthetic` 인 행을 모두 읽어 `identity_scope` 로 가릅니다.
- 배너·히어로 조립(`banners.py`). 요청 `axes` 순서를 따르고 축 값의 출처(session·profile·coldstart)를 `reason` 으로 남깁니다.

**시뮬레이터 `simulator/`**

- 페르소나 생성기. 9,900명 분량 합성 로그를 만듭니다. 1인당 약 1,060건이고 9,900명이면 약 1,049만 건입니다(KRW 캐시 실측). 리뷰에서 뽑은 성향 6축(ingredient, price, texture, scent, sensitivity, review_lean)이 행동 확률과 체류를 바꿉니다. 성향은 "어떻게 보는가"만 정하고 "무엇을 고르는가"에는 관여하지 않습니다. 추천 점수가 쓰는 축과 겹치면 순환이 되기 때문입니다.
- 결제까지 이어지는 동선(`add_to_cart` → `begin_checkout` → `purchase` → `purchase_reason_select`), 재구매 쌍, `--limit` 층화 표본, `GEN_NOW` 기준 시각
- LLM 에이전트 100명(`agent_runner.py`). Playwright 로 실제 브라우저를 띄워 사이트를 조작하므로 프론트 로거를 그대로 타고 수집기로 들어갑니다. 둘러보기·정렬·배너 클릭·주문·구매 후 의견까지 합니다.
- `demo_live.py` 가 캐시를 Kafka 로 produce 하고, `shuffle_sessions.py` 가 페르소나 라운드로빈으로 세션을 섞어 초반에 전원이 나타나게 합니다.

**고객 피드백 분류**

- 계약 `feedback-classification.md` 0.2.0. 축 5종(efficacy, texture, scent, packaging, value)은 고객이 화면에서 고르고, 분류기는 그 축 안의 카테고리 20종과 `other` 중에서만 고릅니다. 건당 호출 1회, 라벨은 다중입니다.
- 채점(50건, 도달 가능 정답 49건 기준): 정밀도 93.7 · 재현율 94.9 · **F1 94.3** · 라벨 집합 완전 일치 88%
- 금지어 599개(`feedback-banned-terms.json`)를 대조해 `hidden_by_default` 를 정합니다. 이 단계에는 LLM 을 쓰지 않습니다.

**그 밖에**

- 상품 등록 계약(`product-registration-spec.md`)과 인코딩 어휘집, 등록 폼 한국어 라벨
- 배너 축 6종(`category`, `clean`, `concern`, `ingredient`, `price_bin`, `segment`)
- 상품·리뷰 한국어화 산출물(`build_ko_catalog.py`, `build_reviews_ko_files.py`, `merge_reviews_ko.py`)
- 백엔드 적재용 정규화 테이블 6종과 DDL(`export_backend_tables.py`)

LLM 을 쓰는 곳은 셋이고 경로가 다릅니다.

| 무엇 | 경로 | 실행 형태 |
| --- | --- | --- |
| 대시보드 처방 문장 | 추천 서버 `POST /api/prescription` → GMS | 서비스 안, 런타임 스위치로 on/off |
| 고객 피드백 분류 | `classify_feedback.py` → GMS 직접 | 오프라인 CLI |
| 에이전트 PA | `agent_runner.py` → GMS 직접 | 오프라인 CLI |

## 3. 기술 스택

버전은 `package.json`, `build.gradle`, `requirements*.txt`, Dockerfile, compose 에서 직접 읽은 값입니다.

| 영역 | 기술 | 버전 | 비고 |
| --- | --- | --- | --- |
| 프론트엔드 | React · TypeScript · Vite | 19.2.8 · 6.0.2 · 8.2.2 | 엔트리 3개(`index.html`, `dashboard.html`, `platform.html`). dev 5173 |
| | @vitejs/plugin-react · oxlint | 6.1.0 · 1.79 | ESLint 대신 oxlint |
| | @portone/browser-sdk | 0.1.10 | 결제(카카오페이) |
| 쇼핑몰 백엔드 | Spring Boot · Java · JPA · MySQL | 4.1.1 · 21 · — · 8.4 | `shop_backend/` 8090, MySQL 13306 |
| | Spring Security · jjwt | — · 0.12.6 | 로그인·권한 |
| 수집 서버 | Spring Boot · Java | 4.1.1 · 21 | `backend/` 8080, `spring-boot-starter-kafka` |
| | Micrometer(Prometheus) · springdoc-openapi | — · 3.1.0 | 메트릭, Swagger UI |
| 메시징 | Apache Kafka (KRaft) | 4.2.0 | 토픽 `activity-events`, 파티션 3, 키 `session_id`. 운영은 EC2-2, 로컬은 `infra/kafka/` |
| 분산 처리 | Spark Structured Streaming / Batch | 3.5.6 | `streaming/` Q1~Q5, 출력은 Parquet. 로컬은 `infra/spark/` |
| | PyArrow · PyMySQL[rsa] | 19.0.1 · 1.1.1 | dw projection (`streaming/Dockerfile.dw`) |
| 추천 · AI | Python · NumPy · scikit-learn · joblib | 3.13 · 2.2.6 · 1.7.0 · 1.5.3 | HistGradientBoosting 239트리·피처 20개, 학습 5,954명 231,005행 (`ltr_model_meta.json`). sklearn 은 pkl 을 만든 버전과 정확히 같아야 로드됩니다. |
| | FastAPI · uvicorn · pydantic | 0.141.1 · 0.52.4 · 2.13.4 | 추천 추론 서버 `batch/serving/` 8300, 내부 전용 |
| | confluent-kafka | 2.15.0 | 추천 서버의 `activity-events` 구독 |
| | pymysql · cryptography | 1.1.1 · ≥42 | DW `user_trait_daily` 읽기. MySQL 8 의 `caching_sha2_password` 때문에 cryptography 가 필요합니다. |
| | OpenAI SDK → GMS | gpt-4.1-mini | 대시보드 처방 문장. temperature 0, JSON 스키마 강제, 자동 거부. 끄면 프론트가 규칙표 문장으로 폴백합니다. |
| | sentence-transformers | — | 리뷰·상품 텍스트 임베딩 384차원 (GPU, 배치 산출물용) |
| 시뮬레이터 | Python 생성기 | — | 페르소나 9,900명 합성 로그, 성향 6축, 결제·재구매, 층화 표본 |
| | Playwright(Chromium) + OpenAI SDK → GMS | gpt-4.1-nano | 에이전트 100명이 실제 브라우저 조작. `--local-model` 로 Qwen2.5 도 가능 |
| 운영 | Docker Compose · nginx · certbot | — | EC2-1 7서비스, EC2-2 7서비스 |
| | Jenkins | — | `Jenkinsfile` 9 스테이지 |
| | Prometheus · Grafana | 3.5.0 · 12.1.0 | 대시보드 3종 프로비저닝 |
| 데이터셋 | Sephora 리뷰 | — | 속성 4개가 모두 채워진 리뷰 844,865건(전체의 77.2%), 상품 200개(+ 등록 8 = 카탈로그 208), 페르소나 14,000명(9,900 + 홀드아웃 2,000×2 + 에이전트 100) |

Sephora 데이터를 쓴 이유는 여러 브랜드가 한 쇼핑몰에 섞여 있어 우리 추천 환경(통합몰)과 가장 가깝기 때문입니다. 단일 브랜드 자사몰 데이터로는 추천 후보가 부족합니다.

## 4. 실행

### 로컬 전 구간

```bash
# 1. 공용 네트워크 + Kafka + Spark
bash infra/create-network.sh
docker compose -f infra/kafka/docker-compose.yml -f infra/spark/docker-compose.yml \
  up -d --build --wait kafka spark-master spark-worker spark-history

# 2. Q1 상시 가동 (Kafka → Raw Parquet)
pwsh infra/spark/run-pipeline.ps1 -Action start-q1      # bash 판: infra/spark/run-pipeline.sh

# 3. 로그를 다 흘려보낸 뒤 Q1 을 세운다
#    Q1 이 append 하는 중에 Q2 가 스냅샷을 읽으면 결과가 흔들린다
pwsh infra/spark/run-pipeline.ps1 -Action stop-q1

# 4. Q2~Q5 배치
pwsh infra/spark/run-pipeline.ps1 -Action run-batch     # -From q3 로 중간부터

# 5. Q5 만 다시 (마트를 고친 뒤 검증만 볼 때)
pwsh infra/spark/run-pipeline.ps1 -Action validate

# 6. 추천 서버
python -m uvicorn batch.serving.recommend_server:app --host 127.0.0.1 --port 8300

# 7. 프론트
cd frontend && npm install && npm run dev               # 5173
```

`infra/spark/.env` 가 필요합니다. `.env.example` 을 복사해서 씁니다. `COMMONS_HASH_SALT` 가 비어 있으면 Q3 가 시작하자마자 실패합니다.

### 배치 재생성 (상품이 바뀌었을 때)

```bash
python batch/regenerate_all.py       # 16단계, mtime 확인 후 필요한 것만
```

### 행동 로그 생성

```bash
python simulator/generator/gen_behavior_logs.py --limit 1000 --currency KRW --out <경로>
python simulator/generator/demo_live.py --limit 9900      # Kafka 로 흘려보내기
```

### 테스트

```bash
python -m pytest batch/ contracts/ simulator/     # AI·계약·시뮬레이터
python -m pytest streaming/tests                  # Spark (pyspark 필요)
cd backend && ./gradlew test                      # 수집 서버
cd shop_backend && ./gradlew test                 # 쇼핑몰 백엔드
```

## 5. 폴더 구조

```
S15P21A306/
├── README.md                          이 문서
├── Jenkinsfile                        CI/CD 9 스테이지 (백엔드)
├── .env.example · .dockerignore · .gitattributes · .gitignore
│
├── contracts/                         ★ 팀 계약. 여기가 바뀌면 여러 모듈이 동시에 영향받는다 (데이터·AI)
│   ├── README.md                          단일 출처와 변경 규칙
│   ├── event-schema.json                  Raw Event JSON Schema
│   ├── event-properties-schema.md         Event별 properties·enum·필수값
│   ├── raw-event-schema.md                Raw Dataset grain·물리 key·컬럼
│   ├── processed-schema.md                Processed Dataset grain·key·컬럼
│   ├── dw-schema.md                       DW Dimension·Mart grain·컬럼
│   ├── persona-schema.md                  Persona·평가 split·Simulation Run
│   ├── event-attribution-contract.md      통합몰 Event 의 브랜드 귀속
│   ├── recommendation-io-spec.md          추천 입출력 (백엔드↔AI). 점수 식·LTR·§5 API·§5-1 배너
│   ├── dashboard-mart-api-spec.md         브랜드 대시보드 마트 조회 API (백엔드↔프론트↔데이터)
│   ├── prescription-api-spec.md           대시보드 처방 문장 API (AI↔프론트)
│   ├── product-feature-spec.md            상품 벡터 148차원 명세
│   ├── product-feature-vocab.json         인코딩 어휘집 0.7. 9블록, 원화 가격 경계
│   ├── product-registration-spec.md       상품 등록 입력 필드·어휘 제약·파생값
│   ├── product-form-labels-ko.json        등록 폼 한국어 라벨 (어휘집에서 생성)
│   ├── feedback-classification.md         고객 피드백 분류 계약 0.2.0
│   ├── feedback-category-vocab.json       피드백 어휘 5축 20종 + other
│   ├── feedback-banned-terms.json         금지어 599개
│   ├── cosmetic-claim-banned-terms.json   화장품 표시광고 금지 표현 (프론트 작성)
│   ├── user-trait-weights.json            사용자 성향 가중치 30일 창
│   ├── purchase-reason-trait-map.json     구매 사유 ↔ 성향 축 매핑
│   ├── validate_events.py · validate_product_registration.py · coverage_report.py
│   ├── requirements-validator.txt
│   ├── dw/                                DW DDL. build_ddl.py · schema.sql · test_build_ddl.py
│   ├── localization/                      한국어화 정본. labels·products·reviews-ko.json
│   ├── persona/                           중첩 Persona JSON → 계약 평탄 테이블 8종
│   │   └── build_persona_tables.py · holdout_rule.py · validate_persona_tables.py
│   │       compare_holdout_rules.py · test_persona_tables.py · data/(미커밋)
│   ├── samples/                           유효·무효 이벤트 표본 8종
│   └── tests/                             계약 테스트 3종
│
├── frontend/                          ★ React 19 + TypeScript 6 + Vite 8 (프론트)
│   ├── index.html · dashboard.html · platform.html      엔트리 3개
│   ├── package.json · tsconfig*.json · vite.config.ts · .oxlintrc.json
│   │                                      프록시 세 갈래:
│   │                                        /api/recommend · /api/prescription · /api/catalog        → 8300
│   │                                        /api/auth · brands · products · cart · orders · reviews
│   │                                        · feedback · seller · settlements · admin                 → 8090
│   │                                        그 외 /api (= /api/events)                                → 8080
│   ├── .env.development · .env.production · .env.example
│   ├── plugins/image-cache.ts · scripts/   (warm-images, 상품 이미지 수집)
│   ├── public/  brand/ · images/ · icons.svg
│   └── src/
│       ├── main.tsx · App.tsx · index.css
│       ├── types/     ★ log.ts (이벤트 43종·섹션·콘텐츠 종류·intent·LogEnvelope)
│       │              product · review · persona · cart · feedback · recommendation
│       ├── lib/       logger.ts(조립·버퍼·재시도) · section.ts · auth · checkout · discount · brands …
│       ├── hooks/     useImpression · useInteractionSignals · useExitSummary · useTextSelection
│       │              useAuth · useCatalog · useRecommendation · useFeedback …
│       ├── pages/     ProductListPage · ProductDetailPage · CartPage
│       ├── dashboard/ DashboardApp.tsx · screens/(11개) · lib/(martApi · martAdapter) · css 4종
│       ├── platform/  PlatformApp.tsx · lib
│       ├── components/ account · auth · banner · cart · common · devtools · feedback · layout · product · review
│       ├── mocks/     상품·리뷰·페르소나·피드백 샘플 JSON
│       └── styles/
│
├── backend/                           Spring Boot 수집 서버 8080 (백엔드)
│   ├── src/main/java/com/cosmetic/collector/   event/(api·application·infrastructure) · config · common
│   ├── BACKEND_INGESTION_POLICY.md · README.md
│   └── build.gradle · gradlew
│
├── shop_backend/                      Spring Boot 쇼핑몰 백엔드 8090 + MySQL (백엔드)
│   ├── src/main/java/com/cosmetic/shopbackend/
│   │       identity · brand · catalog · commerce · payment · feedback
│   │       dashboard · admin · settlement · recommendation · security · common
│   ├── mysql-erd.sql · mysql-erd.md · ERD-TABLES.md      테이블 36개
│   ├── migrations/ · docker-compose.mysql.yml · MYSQL-SETUP.md
│   └── PERFORMANCE-BASELINE-NPLUS1.md
│
├── streaming/                         ★ Spark Q1~Q5 + dw projection (데이터·인프라)
│   ├── jobs/
│   │   ├── raw_sink_job.py                Q1 Kafka → Raw Parquet
│   │   ├── clean_events_job.py            Q2 검증·중복 제거
│   │   ├── derive_facts_job.py            Q3 세션화·Fact 6종·Dimension 2종
│   │   ├── build_marts_job.py             Q4 퍼널 세션 Fact · Mart 25종 (발행 대상 22종)
│   │   ├── validate_pipeline_job.py       Q5 품질 검증 159개
│   │   ├── publish_user_trait_job.py      dw projection 진입점 (staging→검증→원자적 스왑)
│   │   ├── dw_projection_source.py        Parquet 읽기·DDL 대조
│   │   └── behavior_weights.py            frontend/src/types/log.ts 재사용 어댑터
│   ├── tools/replay_collector.py          gzip 행동 로그를 수집기로 재생 (SHA-256 회계)
│   ├── tests/                             Spark 테스트 26개 파일
│   └── Dockerfile.dw · requirements-dw.txt · DW_PROJECTION.md · README.md
│
├── batch/                             ★ 추천 배치 + 추천 추론 서버 (AI)
│   ├── regenerate_all.py                  상품이 바뀌면 여기서부터 (16단계·mtime 확인)
│   ├── ingest/                            원천 → 산출물
│   │   ├── build_products_json.py             상품 200개 카탈로그
│   │   ├── build_feature_vocab.py             어휘집 생성 (문서빈도·블록 가중치)
│   │   ├── build_affinity_lift.py             속성 친화도 4,000행
│   │   ├── build_form_labels.py               등록 폼 한국어 라벨
│   │   ├── build_feature_sample.py            샘플 6개 산출물·문서
│   │   ├── build_ko_catalog.py · merge_reviews_ko.py
│   │   │   build_reviews_100.py · build_reviews_ko_files.py    한국어화 산출물
│   │   └── data/                          products_200.json · affinity_lift.csv · eval_metadata*.jsonl
│   │       └── serving/                   ★ 서빙 산출물. product_feature.jsonl(148차원),
│   │                                      item_cooc.npz(CF), ltr_model.pkl + meta, banner_axes.json,
│   │                                      ingredient/concern vocab, product_ingredient.csv,
│   │                                      backend_tables.sql, registered_products.jsonl
│   ├── jobs/                              모델·평가 (37 파일, 테스트 13)
│   │   ├── product_encoder.py · persona_feature.py · user_vector.py · recommender.py
│   │   ├── ltr_features.py(피처 20개) · train_ltr.py · build_cooc.py
│   │   ├── export_features.py · export_backend_tables.py · export_dashboard.py · banner_axes.py
│   │   ├── eval_persona_feature.py · eval_dynamic.py · eval_review_replay.py · eval_cbf_flow.py
│   │   ├── eval_metadata.py · persona_split.py · hidden_preference.py
│   │   └── behavior_weights.py            frontend/src/types/log.ts 를 직접 읽는 가중치 로더
│   └── serving/                           ★ 추천 추론 서버 8300 (테스트 11 파일)
│       ├── recommend_server.py                FastAPI 진입점
│       ├── banners.py                         hero·배너 조립
│       ├── prescription.py                    대시보드 처방 문장 (LLM)
│       ├── catalog_sync.py                    쇼핑몰 백엔드 ACTIVE 상품 동기화
│       ├── catalog_registry.py                등록 입력 → 계약 검사 → 인코딩 → 카탈로그 편입
│       ├── session_store.py                   세션 상태 영속화·재생
│       ├── kafka_state.py                     activity-events 구독 → 상태 실시간 갱신
│       ├── user_trait.py                      DW user_trait_daily → long_term_trait
│       ├── live_stats.py · pipeline_stats.py  시연 화면 /live · /pipeline
│       ├── bench_recommend.py · e2e_smoke.py  응답 시간 실측, E2E 스모크
│       └── requirements.txt
│
├── simulator/                         ★ 행동 로그 생성기 · LLM 에이전트 (AI)
│   ├── collector_client.py                수집 API 전송 (429/503 백프레셔)
│   ├── generator/
│   │   ├── gen_behavior_logs.py               페르소나 9,900명 합성 로그 (성향 6축)
│   │   ├── demo_live.py                       캐시 → Kafka produce (/live 시연)
│   │   ├── shuffle_sessions.py                페르소나 라운드로빈으로 세션 섞기
│   │   ├── recommend_client.py                추천 서버 연동
│   │   └── build_persona_style.py             리뷰에서 페르소나 6축 추출
│   ├── agents/
│   │   ├── agent_runner.py                    에이전트 100명. Playwright 로 실제 브라우저 조작
│   │   ├── agent_launcher.py                  발표 노트북 런처 (8301)
│   │   ├── analyze_run_quality.py · model_server.py
│   │   └── data/                              실행 산출물 (미커밋)
│   ├── feedback/                          고객 피드백 시연 데이터
│   │   ├── gen_feedback.py · classify_feedback.py · banned_terms.py
│   │   └── products.ssafy-beauty.json         시연 브랜드 상품 8개 (SB000001~)
│   └── personas/
│       ├── build_personas.py · holdout_exclude_dupaccounts.txt
│       └── data/                              personas_9900 · _100_agent · _holdout_a/b · persona_style
│
├── deploy/                            EC2 배포 (인프라·백엔드·AI)
│   ├── backend.Dockerfile · shop_backend.Dockerfile · nginx.Dockerfile · nginx/default.conf
│   ├── recommend.Dockerfile · recommend.Dockerfile.dockerignore · recommend-entrypoint.sh
│   ├── ec2-1/                             서비스 7종. backend · shop-backend · mysql · recommend · nginx · prometheus · grafana
│   │   ├── docker-compose.yml · .env.example · prometheus.yml · README.md
│   │   ├── migrations/20260917_dw_mart_columns.sql
│   │   └── redeploy-local.sh · redeploy-recommend-from-dev.sh · reset-demo-local.sh
│   │       reset-registered-local.sh · build-verbose-local.sh
│   └── ec2-2/                             Kafka · Spark master/worker/history · Q1 상시 · dw-projection
│       ├── docker-compose.yml · .env.example · README.md
│       └── run-daily-batch.sh · hwabun-daily-batch.service · hwabun-daily-batch.timer
│
├── infra/                             로컬 개발 환경
│   ├── kafka/    docker-compose.yml · topics.sh/ps1 · README.md
│   ├── spark/    docker-compose.yml · Dockerfile · run-pipeline.sh/ps1 · verify-e2e.ps1
│   │             healthcheck.ps1 · assert_raw_event.py · conf/ · .env.example
│   └── create-network.sh/ps1              공용 docker 네트워크 a306-data
│
├── monitoring/                        Prometheus 설정, Grafana 대시보드 3종 (백엔드)
├── kafka/README.md                    Kafka 구조·이벤트 처리 명세
│
├── docs/
│   ├── planning/     ★ 확정 기획 정본. service-plan.md · feature-spec-status.md
│   ├── ai/           추천 설계·검증. recommendation-design · evaluation-framework ·
│   │                 cbf-technical-review · exposure-role · ingredient-domain-guide · live-demo-runbook
│   ├── analytics/    행동 로그·DW 설계. behavior-log-design · event-logging-design ·
│   │                 log-transport-contract · dw-design · spark-processing-design · persona-design
│   ├── dashboard/    B2B 대시보드 조사·설계. b2b-dashboard-research · insight-catalog · metric-basis
│   ├── localization/ 한국어화 검수본
│   ├── data/ · captures/ · system-architecture*.png
│   └── git-convention.md · backend-ingestion-backpressure.md
│
├── data/                              Spark 로컬 산출물 (gitignore). raw_events · processed · marts · checkpoints
└── 1차 평가/                          평가 제출물 (팀원 6명 폴더)
```

## 6. 문서 찾아가기

| 궁금한 것 | 문서 |
| --- | --- |
| 이 서비스가 무엇인가 | `docs/planning/service-plan.md` |
| 기획 대비 어디까지 구현됐나 | `docs/planning/feature-spec-status.md` |
| 어떤 이벤트를 왜 그 자리에 두었나 | `docs/analytics/behavior-log-design.md` |
| 이벤트 속성·enum 규칙 | `contracts/event-properties-schema.md` |
| 마트 grain·컬럼 | `contracts/dw-schema.md` |
| 추천 점수는 어떻게 나오나 | `docs/ai/recommendation-design.md` · `contracts/recommendation-io-spec.md` |
| 추천을 어떻게 평가했나 | `docs/ai/evaluation-framework.md` |
| 대시보드 지표 산출 근거 | `docs/dashboard/metric-basis.md` |
| 커밋·브랜치 규칙 | `docs/git-convention.md` |
