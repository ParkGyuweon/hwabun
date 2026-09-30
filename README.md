# 화분 (HWABUN)

> 여러 소규모 뷰티 브랜드를 한 쇼핑몰에 모아 소비자에게 맞춤 추천하고, 브랜드에는 고객 피드백과 교차 브랜드 인사이트를 제공하는 참여형 뷰티 커머스 플랫폼

소규모 뷰티 브랜드는 고객 의견을 제품에 반영하고 팬덤을 만들 시간도 도구도 없습니다. 화분은 그 일을 플랫폼 기능으로 만듭니다.

소비자는 쇼핑몰 BLOOM 하나에서 회원가입 한 번으로 여러 브랜드를 둘러보고, 자기 피부 고민에 맞는 상품을 추천받고, 써 본 뒤 피드백으로 제품 개선에 참여합니다. 브랜드 사장님은 대시보드에서 자기 상품 성과와 고객 반응을 봅니다. 혼자서는 알 수 없는 교차 브랜드 유입, 유사 브랜드 대비 전환율, 구매 이유 분포까지 볼 수 있습니다.

여러 브랜드를 모으는 이유는 둘입니다. 한 브랜드만으로는 추천 후보가 부족해 알고리즘이 의미를 갖기 어렵고, 모여 있어야 "다른 브랜드를 보던 고객이 우리에게 왔다"는 인사이트가 나옵니다.

### 우리가 만든 것

| | 산출물 |
| --- | --- |
| 서비스 | 통합 쇼핑몰 BLOOM, 브랜드 대시보드(메뉴 8개 · 화면 13개), 플랫폼 운영 화면 |
| 데이터 | 직접 설계한 행동 로그 43종 → Kafka → Spark 5단계(Q1~Q5) → 마트 25종 → DW 계약 테이블 24개 = 대시보드용 22(`cross_brand_daily` 발행 대기 포함) + 추천 서버용 `user_trait_daily` 1 + 계약만 있고 쓰지 않는 `category_price_reference` 1, 운영 기본 발행 22 |
| AI | 상품 벡터 148차원(멀티핫 블록 8종 + 스칼라), 학습 결합 추천(LTR 382트리·피처 20개), Kafka 구독 실시간 상태 반영, 대시보드 처방 문장 |
| 검증 | 페르소나 9,900명 합성 로그 약 1,049만 건, LLM 에이전트 100명이 실제 브라우저 조작, 파이프라인 품질 검증 166개(2026-09-23 운영 배치 기준) |

기준일 2026-09-28(발표 종료일). 아래 수치는 이 날짜에 레포(`origin/dev`)와 배포 서버에서 직접 확인한 값입니다.

## 1. 아키텍처

```
 ① 행동                ② 수집                ③ 분산 처리                 ④ 서빙·분석              ⑤ 소비
 ──────────            ──────────            ─────────────               ─────────────            ─────────
 실제 소비자                                                              추천 서버 8300           쇼핑몰 BLOOM
   │                   수집 서버 8080         Kafka activity-events       · items 10 + hero       · 추천 카드
 페르소나 PC 9,900명 ──▶ POST /api/events ──▶  파티션 3 · key=session_id ──▶ · 실시간 상태 반영  ──▶ · 신규 브랜드 히어로
   │  (생성기)           검증 → Kafka           │                          · 처방 문장(LLM)
 에이전트 PA 100명       백프레셔 429/503       ▼                          · 상품 등록 즉시 편입    브랜드 대시보드
   (Playwright+LLM)                          Spark Q1~Q5                        ▲                 · 13개 화면
                                              Q1 raw_sink   (상시)              │                 · 마트 API 10개
 세 갈래가 같은 스키마                          Q2 clean_events                   │
 frontend/src/types/log.ts (43종)              Q3 derive_facts                 DW MySQL
 contracts/event-properties-schema.md          Q4 build_marts  → 마트 25종      24 테이블
                                               Q5 validate     (검사 171개)      ▲
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

6명입니다. 괄호 안 숫자는 `git log --no-merges --author=<이름> -- <경로>` 로 센 해당 디렉터리 커밋 수입니다(2026-09-29 `origin/dev`. 추유림은 `추유림`·`youlim0314` 두 작성자 이름을 합산했고, 그 밖의 다른 계정 이름은 합산하지 않았습니다).

| 이름 | 역할 | 소유 영역 |
| --- | --- | --- |
| 강하린 | 기획 (PM) | 프로젝트 일정·업무 관리 · 서비스 기획 · 발표/영상 콘텐츠 제작 |
| 추유림 | 프론트엔드 | `frontend/` (203) · `docs/dashboard/` (30) |
| 최열음 | 백엔드 | `shop_backend/` (70) · `backend/` (31) · `monitoring/` (6) · `Jenkinsfile` |
| 이은솔 | 데이터 | `streaming/` (166) · `contracts/` (162) · `infra/` (18) |
| 송민우 | 인프라 | `deploy/ec2-2/` · dw projection · `streaming/` (23) · `infra/` (10) |
| 박규원 | AI | `batch/` (144) · `simulator/` (137) · `docs/ai/` (90) |

### 강하린 · 기획 (PM)

- 서비스 기획 및 방향성 구체화. 타깃 사용자를 정의하고 핵심 가치와 서비스 구조를 설계했습니다. 국내 소규모 뷰티 브랜드의 현황·문제점과 데이터 인프라 필요성을 조사했습니다.
- 프로젝트 브랜딩. HWABUN·BLOOM 서비스 콘셉트와 슬로건, 디자인 방향을 수립했습니다.
- 프로젝트 관리. 주차별 일정과 업무 우선순위를 관리하고, 파트별 진행 상황과 통합 일정을 조율합니다.
- 주요 기능 기획. 사용자 Flow 를 정리하고 핵심 기능을 정의해 MUST/SHOULD 우선순위를 정했습니다.
- 발표 자료 제작. 기획 발표 PPT 구성과 발표 스토리라인을 설계하고 디자인했습니다.
- 영상 포트폴리오 제작. HWABUN 홍보영상 시나리오·스토리보드를 기획하고 키컷과 영상을 제작했습니다.

### 추유림 · 프론트엔드

한 코드베이스에서 엔트리 3개를 빌드합니다. 로그가 여기서 출발합니다.

- 쇼핑몰 BLOOM (`index.html`). 상품 목록·상세·장바구니·주문·결제(PortOne)·리뷰(구매자만)·피드백에 추천 카드와 신규 브랜드 히어로 배너를 붙였습니다.
- 브랜드 대시보드 (`dashboard.html`). 사장님이 묻는 질문 순서로 메뉴 8개(요약 · 상세페이지 · 상품 · 주문 · 고객 · 고객의 말 · 시장 · 상품 등록)이고, 그 안에 화면 13개(콘텐츠·마찰, 주문·정산, 공개 리뷰·받은 피드백 등)가 있습니다. 상세페이지 처방 문장은 AI 서버(`/api/prescription`)가 답하면 그 문장을, 아니면 규칙 표 문장을 씁니다 — 화면이 비는 순간이 없게 한 구조입니다.
- 플랫폼 운영 화면 (`platform.html`).
- 행동 로거 (`src/lib/logger.ts`). 이벤트 43종을 조립해 버퍼에 담고 전송하며, 429/502/503 은 백오프로 재시도합니다. 이벤트 스키마 `src/types/log.ts` 는 AI·데이터가 직접 import 해서 가중치를 맞추는 단일 출처입니다.
- 수집 훅 (`src/hooks/`). 스크롤 깊이·정지·되돌아 읽기, 섹션 노출과 체류, 텍스트 선택·복사, 주목 신호(hover/rage/dead click), 이탈 요약을 잡습니다.
- 화면마다 그 자리에 그 이벤트를 둔 근거를 `docs/analytics/behavior-log-design.md` 에 남겼습니다.
- B2B 대시보드 시장 조사와 지표별 산출 근거를 정리했습니다 (`docs/dashboard/`).
- 상품 등록 폼을 추천이 요구하는 스키마에 맞춰 구현했습니다. 대시보드는 행동 지표(마트) · 주문·정산·공개 리뷰(쇼핑몰 원장)를 실측으로 읽고, 값이 없으면 0, "-", "없음"입니다. 받은 피드백 탭에만 시연용 시드 30건이 "시드" 배지를 달고 남아 있습니다.
- 고객 목소리 AI 요약 카드(매일 06:00 자동 + "즉시 반영" 버튼)와 정산 화면(월별 정산 · 수수료 0%)을 붙였습니다. AI 요약은 백엔드·추천 서비스 API 연결 대기 중이라 그때까지 "연결 전"으로 표시합니다 (`contracts/feedback-insight-spec.md`).

### 최열음 · 백엔드

- 수집 서버 `backend/` 8080. `POST /api/events` 를 검증하고 Kafka `activity-events` 로 produce 합니다. 파티션 키는 `session_id`, 과부하 때는 429/503 으로 백프레셔를 겁니다. Actuator + Micrometer 로 Prometheus 메트릭을 냅니다.
- 쇼핑몰 백엔드 `shop_backend/` 8090. 도메인 13개(identity/JWT, brand, catalog, commerce, payment, feedback, notification, dashboard, admin, settlement, recommendation 프록시, security, common)로 나뉘고, MySQL 테이블 38개와 ERD 문서가 있습니다.
- 상품 등록 계약을 구현했습니다. 어휘 검증과 unmapped 저장을 포함합니다.
- CI/CD `Jenkinsfile` 6 스테이지. GitLab 연결 확인 → Backend 테스트 → Shop Backend 테스트 → Frontend Docker 빌드 검증 → EC2 구성 변경 감지 → EC2 배포. MySQL 컨테이너와 스키마·seed는 배포에서 건드리지 않습니다.
- 모니터링 `monitoring/`. Prometheus 설정과 Grafana 대시보드 3종(backend-overview, collector-validation, shop-backend-performance)을 프로비저닝합니다.
- nginx 라우팅 (`deploy/nginx/default.conf`). `/api/events` 는 수집 8080 으로, `/api/prescription`·`/api/headline` 은 추천 서버 8300 으로, 나머지 `/api/` 는 쇼핑몰 8090 으로 보냅니다(추천은 쇼핑몰의 `/api/recommend` 프록시를 거칩니다).

### 이은솔 · 데이터

Kafka 부터 마트까지 다섯 단계와, 파트 사이를 잇는 계약 문서를 맡습니다.

- Q1 `raw_sink_job`. Kafka 를 읽어 Raw Parquet 으로 적재합니다. Structured Streaming 이라 체크포인트로 오프셋을 이어받고, 파싱에 실패한 레코드도 원문을 남깁니다.
- Q2 `clean_events_job`. 스키마와 의미를 검증하고 `event_id` 정본을 골라 cleaned / bad / duplicate 세 갈래로 나눕니다.
- Q3 `derive_facts_job`. 세션화와 Fact 6종(상품, 구매, 구매사유, 리뷰, 섹션 체류, 콘텐츠 관심), Dimension 2종(dim_product, dim_brand)을 만듭니다.
- Q4 `build_marts_job`. 퍼널 세션 Fact 를 만들고, 상품·퍼널·브랜드 일간 KPI, 재구매, 구매사유, 성분 주간 관심, 고객군, 가격대, 배너, 콘텐츠, 마찰, 이탈, 유입 경로, 교차 브랜드, Commons 코호트까지 마트 25종을 집계합니다. 이 가운데 24종이 DW 발행 대상이고(`cross_brand_daily`·`category_price_reference` 는 09-28 에 등록, DW 테이블을 만든 뒤 발행 — 운영 EC2-2 의 기본 실행 목록은 아직 22종), `banner_daily` 는 Parquet 으로만 둡니다. `analytics_baseline` (`dw-schema.md` §4.13) 은 기준선 기간을 인자로 준 실행에서만 만들어져 상시 25종에 넣지 않습니다 — 코드에는 출력 경로가 26개인데 평소 25개만 생기는 이유입니다.
- Q5 `validate_pipeline_job`. 품질 검증 171개로 grain 유일성, 비율 0~1(Event 날짜로 칸을 나누는 Mart 는 자정을 넘긴 세션 때문에 일자 칸이 아니라 날짜 합산으로 본다 — `dw-schema.md` §4 도입), 재계산 결정성, 통화 일관성, 부분집합 관계, 상품 귀속, 발행 대상 마트의 NOT NULL 계약, 세션 안에서 클릭에 대응하는 노출이 있는지를 확인합니다.
- 계약 문서를 소유합니다. `dw-schema.md`, `processed-schema.md`, `raw-event-schema.md`, `event-properties-schema.md`, `persona-schema.md`, `event-attribution-contract.md`, 그리고 대시보드 마트 조회 계약 `dashboard-mart-api-spec.md`
- Job 이 실제로 읽는 계약 파일도 같이 관리합니다. `purchase-reason-trait-map.json`(Q4·Q5), `user-trait-weights.json`(Q4), `dw/build_ddl.py`(DDL 생성 · projection 과 Q5 의 NOT NULL 정책 정본) 와 `dw/schema.sql`, `event-schema.json`(Q5 가 `impression_origin` 허용값을 여기서 읽습니다 — Q2 와 수집기는 같은 규칙을 각자 코드로 구현합니다)
- 노출 정의 통일. 노출 이벤트 셋(product, recommendation, banner)을 CTR 분모에 합산하고, 뒤로가기 재조회는 상세 진입에서 뺍니다. 선행 노출 없이 클릭·Quick Look 이 먼저 일어나면 프론트가 노출을 합성해 남기고, 그 사실을 `impression_origin`(`observed` · `implied_by_click` · `implied_by_quick_look`) 으로 구분합니다. 합성분도 분모에 넣습니다.
- 로컬 Kafka·Spark compose 를 만들었습니다 (`infra/`).

### 송민우 · 인프라

- EC2-2 를 구축했습니다. Kafka 브로커(KRaft), Spark 마스터/워커/히스토리, Q1 상시 가동 컨테이너가 떠 있습니다.
- 일일 배치 자동화. `run-daily-batch.sh` 가 flock 으로 중복 실행을 막고, systemd service·timer 가 매일 18:00 UTC(03:00 KST)에 Q2→Q3→Q4→Q5→발행을 한 번에 돌립니다.
- dw projection `publish_user_trait_job`. 마트 Parquet 을 MySQL 로 옮깁니다. staging 테이블에 적재하고 행 수·grain 유일성·NOT NULL 을 검증한 뒤 RENAME 으로 원자적으로 스왑합니다. 검증에 실패하면 기존 테이블이 그대로 남고, 발행에 성공하면 이전 테이블(`__old`)은 같은 실행에서 정리해 롤백용 백업은 남지 않습니다. 발행 대상 마트 24종(운영 기본 실행 22종)
- DW 스키마 마이그레이션을 관리합니다 (`deploy/ec2-1/migrations/`).
- 퍼널 Fact 와 일간 KPI 마트를 초기 구현했습니다.

### 박규원 · AI

추천 모델과 추천 서버, 그리고 그 둘을 검증할 트래픽을 만드는 시뮬레이터를 맡습니다.

- 상품 벡터 148차원. 어휘집 0.7 기준 멀티핫 블록 8종(카테고리 2·고민·성분·클린·제형·가격대·브랜드) + 스칼라 `rating`. 블록 가중치는 문서 빈도에서 계산합니다.
- 추천 점수. 콘텐츠 유사도에 페르소나 속성 친화도 4,000행과 CF 동시발생(200×200)을 얹고 LTR 로 결합합니다. 트리 239개·피처 20개, 학습 5,954명 231,005행. 학습과 서빙이 `ltr_features.py` 를 같이 씁니다.
- 노출 정책. MMR 다양성, 신규 브랜드 전용 슬롯, 콜드스타트 폴백. `regenerate_all.py` 가 16단계를 mtime 확인 후 필요한 것만 다시 만듭니다.
- 평가 축 3개 분리. 오프라인 leave-last-out, 리뷰 이력 순차 재생, 동적 시뮬레이션. 홀드아웃 2세트(각 2,000명)로 a 에서 고르고 b 에서 확인합니다.
- 추천 서버 `batch/serving/` 8300, 라우트 23개. 추천(items 10 + hero), 상품 등록·중단, 이벤트 수신, 대시보드 처방 문장·한 마디(`/api/headline`), 고객 피드백 분류, 카탈로그 동기화, 시연 화면 `/live`·`/live/users`·`/pipeline`
- 실시간 상태. `activity-events` 를 별도 컨슈머 그룹으로 구독해 세션 상태를 초 단위로 갱신하고, DW `user_trait_daily` 를 읽어 응답에 `long_term_trait` 을 싣습니다.
- 시뮬레이터. 페르소나 9,900명 합성 로그(약 1,049만 건)와 LLM 에이전트 100명. 에이전트는 Playwright 로 실제 브라우저를 띄워 프론트 로거를 그대로 탑니다. 성향 6축이 "어떻게 보는가"만 바꾸고 "무엇을 고르는가"에는 관여하지 않습니다.
- 고객 피드백 분류. 축 5종은 고객이 고르고 분류기는 그 축 안 카테고리 20종에서만 고릅니다. 사람 정답 50건 대비 F1 94.3, 금지어 599개 대조
- 상품 등록 계약·어휘집·한국어 폼 라벨, 배너 축 6종, 상품·리뷰 한국어화, 백엔드 적재용 테이블 6종과 DDL

LLM 을 쓰는 곳은 넷이고 경로가 다릅니다.

| 무엇 | 경로 | 실행 형태 |
| --- | --- | --- |
| 대시보드 처방 문장 | 추천 서버 `POST /api/prescription` → GMS | 서비스 안, 런타임 스위치로 on/off |
| 대시보드 한 마디 | 추천 서버 `POST /api/headline` → GMS | 서비스 안, 처방 스위치를 같이 따르고 꺼지면 규칙 문장 |
| 고객 피드백 분류 | 추천 서버 `POST /api/feedback/classify` → GMS · 배치는 `classify_feedback.py` → GMS 직접 | 서비스 안(백엔드 배치가 호출) · 오프라인 CLI |
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
| 추천 · AI | Python · NumPy · scikit-learn · joblib | 3.13 · 2.2.6 · 1.7.0 · 1.5.3 | HistGradientBoosting 382트리·피처 20개, 학습 5,954명 231,005행 (`ltr_model_meta.json`). sklearn 은 pkl 을 만든 버전과 정확히 같아야 로드됩니다. |
| | FastAPI · uvicorn · pydantic | 0.141.1 · 0.52.4 · 2.13.4 | 추천 추론 서버 `batch/serving/` 8300, 내부 전용 |
| | confluent-kafka | 2.15.0 | 추천 서버의 `activity-events` 구독 |
| | pymysql · cryptography | 1.1.1 · ≥42 | DW `user_trait_daily` 읽기. MySQL 8 의 `caching_sha2_password` 때문에 cryptography 가 필요합니다. |
| | OpenAI SDK → GMS | gpt-4.1-mini | 대시보드 처방 문장. temperature 0, JSON 스키마 강제, 자동 거부. 끄면 프론트가 규칙표 문장으로 폴백합니다. |
| | sentence-transformers | — | 리뷰·상품 텍스트 임베딩 384차원 (GPU, 배치 산출물용) |
| 시뮬레이터 | Python 생성기 | — | 페르소나 9,900명 합성 로그, 성향 6축, 결제·재구매, 층화 표본 |
| | Playwright(Chromium) + OpenAI SDK → GMS | gpt-4.1-nano | 에이전트 100명이 실제 브라우저 조작. `--local-model` 로 Qwen2.5 도 가능 |
| 운영 | Docker Compose · nginx · certbot | — | EC2-1 7서비스, EC2-2 7서비스 |
| | Jenkins | — | `Jenkinsfile` 6 스테이지 |
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
├── Jenkinsfile                        CI/CD 6 스테이지 (백엔드)
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
│   ├── headline-api-spec.md               대시보드 화면·섹션별 한 마디 API (AI↔프론트)
│   ├── feedback-insight-spec.md           고객 목소리 AI 요약 API 초안 0.1 (프론트 제안, 서버 미구현)
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
│   │                                        /api/recommend · /api/prescription · /api/headline · /api/catalog → 8300
│   │                                        /api/auth · members · brands · products · cart · orders · reviews
│   │                                        · feedback · seller · settlements · admin · notifications → 8090
│   │                                        그 외 /api (= /api/events)                                → 8080
│   ├── .env.development · .env.production · .env.example
│   ├── plugins/   image-cache.ts · review-chunks.ts (Vite 플러그인)
│   ├── scripts/   build-personas · build-products · build-reviews · collect-product-content · warm-images (시드·이미지 수집)
│   ├── public/  brand/ · images/ · icons.svg
│   └── src/
│       ├── main.tsx · App.tsx · index.css
│       ├── types/     ★ log.ts (이벤트 43종·섹션·콘텐츠 종류·intent·LogEnvelope)
│       │              product · review · persona · cart · feedback · recommendation
│       ├── lib/       logger.ts(조립·버퍼·재시도) · section.ts · auth · checkout · discount · brands …
│       ├── hooks/     useImpression · useInteractionSignals · useExitSummary · useTextSelection
│       │              useAuth · useCatalog · useRecommendation · useFeedback …
│       ├── pages/     ProductListPage · ProductDetailPage · CartPage
│       ├── dashboard/ DashboardApp.tsx · screens/(15 파일 = 화면 13 + 공용 2) · lib/(martApi · martAdapter · insightApi · prescription) · css 4종
│       ├── platform/  PlatformApp.tsx · lib
│       ├── components/ account · auth · banner · cart · common · devtools · feedback · layout · product · review
│       ├── mocks/     SSAFY Beauty 카탈로그 · 시연용 시드(피드백 30건 등) · 스크립트 산출 샘플 JSON
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
│   ├── mysql-erd.sql · mysql-erd.md · ERD-TABLES.md      테이블 38개
│   ├── migrations/ · docker-compose.mysql.yml · MYSQL-SETUP.md
│   └── PERFORMANCE-BASELINE-NPLUS1.md
│
├── streaming/                         ★ Spark Q1~Q5 + dw projection (데이터·인프라)
│   ├── jobs/
│   │   ├── raw_sink_job.py                Q1 Kafka → Raw Parquet
│   │   ├── clean_events_job.py            Q2 검증·중복 제거
│   │   ├── derive_facts_job.py            Q3 세션화·Fact 6종·Dimension 2종
│   │   ├── build_marts_job.py             Q4 퍼널 세션 Fact · Mart 25종 (발행 대상 24종)
│   │   ├── validate_pipeline_job.py       Q5 품질 검증 171개
│   │   ├── publish_user_trait_job.py      dw projection 진입점 (staging→검증→원자적 스왑)
│   │   ├── dw_projection_source.py        Parquet 읽기·DDL 대조
│   │   └── behavior_weights.py            frontend/src/types/log.ts 재사용 어댑터
│   ├── tools/replay_collector.py          gzip 행동 로그를 수집기로 재생 (SHA-256 회계)
│   ├── tests/                             Spark 테스트 37개 파일
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
│   └── serving/                           ★ 추천 추론 서버 8300 (테스트 13 파일)
│       ├── recommend_server.py                FastAPI 진입점
│       ├── banners.py                         hero·배너 조립
│       ├── prescription.py                    대시보드 처방 문장 (LLM)
│       ├── headline.py                        대시보드 화면·섹션별 한 마디 (LLM)
│       ├── feedback_classify.py               고객 피드백 분류 서빙
│       ├── catalog_sync.py                    쇼핑몰 백엔드 ACTIVE 상품 동기화
│       ├── catalog_registry.py                등록 입력 → 계약 검사 → 인코딩 → 카탈로그 편입
│       ├── session_store.py                   세션 상태 영속화·재생
│       ├── kafka_state.py                     activity-events 구독 → 상태 실시간 갱신
│       ├── user_trait.py                      DW user_trait_daily → long_term_trait
│       ├── live_stats.py · pipeline_stats.py  시연 화면 /live · /live/users · /pipeline
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
│   ├── ai/           추천 설계·검증. README · recommendation-design · evaluation-framework ·
│   │                 cbf-technical-review · exposure-role · ingredient-domain-guide · live-demo-runbook ·
│   │                 persona-feature-port · product-feature-sample
│   ├── analytics/    행동 로그·DW 설계. behavior-log-design · event-logging-design ·
│   │                 log-transport-contract · dw-design · spark-processing-design · persona-design ·
│   │                 raw-event-storage-design · marketing-signal-research · event-weight-rationale.html
│   ├── dashboard/    B2B 대시보드 조사·설계. b2b-dashboard-research · insight-catalog · metric-basis
│   ├── localization/ 한국어화 검수본
│   ├── data/ · captures/ · system-architecture*.png
│   ├── api-spec.md                    쇼핑몰 백엔드 API 명세 (백엔드)
│   ├── shop-backend-requests.md · recommend-trait-requests.md   프론트 → 백엔드·AI 요청서
│   └── git-convention.md · backend-ingestion-backpressure.md
│
├── data/                              Spark 로컬 산출물 (gitignore). raw_events · processed · marts · checkpoints
├── exec/                              포팅 제출물 (인프라). 포팅 매뉴얼 · 외부 서비스 정보 · DB 덤프(dw·shop_backend 2026-09-23) · 시연 시나리오
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
