# S15P21A306 

## 1. 현재 폴더 구조

지금 레포에 실제로 들어있는 것입니다. (최종 확인 2026-09-01)

```
S15P21A306/
├── README.md                        이 문서
├── .gitignore
│
├── contracts/                       ★ 팀 계약. 여기가 바뀌면 여러 모듈이 동시에 영향받음
│   ├── event-schema.json                Raw Event JSON Schema (Collector 통과 후 계약)
│   ├── validate_events.py               이벤트 파일을 스키마로 검증하는 CLI
│   ├── requirements-validator.txt       검증기 의존성 (jsonschema[format])
│   ├── samples/ · tests/                유효/무효 이벤트 표본과 계약 테스트
│   ├── product-feature-spec.md          상품 벡터 148차원 명세 — 블록 구성·인코딩·가중치
│   ├── product-feature-vocab.json       인코딩 어휘집 `0.4` — 9개 블록 (brand 포함)
│   └── recommendation-io-spec.md        추천 입출력 계약 (백엔드↔AI) — 점수 식·가중치 스케줄
│
├── docs/
│   ├── ai/                          추천 알고리즘 설계·검증 (AI)
│   │   ├── recommendation-design.md     CBF 전체 설계안 — 점수 공식, 행동 가중치, 스케줄, MMR
│   │   ├── cbf-technical-review.md      코사인 계산 구조 실측 검증서
│   │   ├── product-feature-sample.md    상품 5개 인코딩 샘플  ⚠ 어휘집 0.3·93차원 기준 (갱신 필요)
│   │   └── persona-feature-port.md      페르소나 피처 이관 계획·검증 기준·결과
│   │
│   ├── analytics/                   행동 로그·DW 설계 (프론트·데이터)
│   │   ├── behavior-log-design.md       왜 그 자리에 그 이벤트를 두었는지
│   │   ├── event-taxonomy-trigger-schema.md · event-contract-summary.md   이벤트 계약
│   │   ├── log-transport-contract.md    전송 주기·재시도·actor_type 판정
│   │   ├── dw-schema.md · processed-schema.md   Mart·Processed 스키마
│   │   ├── persona-schema.md · persona-attribute-preprocessing.md
│   │   ├── marketing-signal-research.md · event-weight-rationale.html
│   │
│   ├── dashboard/                   B2B 대시보드 조사·설계 (프론트)
│   ├── data/                        데이터 수집 메모 (프론트)
│   ├── backend-ingestion-backpressure.md  수집 과부하 응답 정책 (백엔드)
│   └── git-convention.md            커밋 메시지·브랜치 전략 (팀 공통)
│
├── batch/                           ★ Spark Batch — 상품·페르소나 피처와 추천 계산
│   ├── ingest/
│   │   ├── build_feature_vocab.py       어휘집 생성 (문서빈도·블록 가중치)
│   │   ├── build_products_json.py       상품 200개 카탈로그 생성 (사이즈 변형 병합)
│   │   └── data/
│   │       ├── products_200.json            상품 200개 (원본 27컬럼 + 병합 이력 + 리뷰 통계)
│   │       ├── affinity_lift.csv            속성 친화도 4,000행 (200상품 × 20세그먼트)
│   │       ├── concern_from_reviews.npz     리뷰에서 뽑은 concern 점수
│   │       ├── excluded_products.json       제외 상품 목록과 사유
│   │       └── serving/                     ★ 백엔드 RankingService 입력
│   │           ├── product_feature.jsonl        상품 200개 × 148차원 + prior
│   │           ├── attribute_affinity.csv       친화도 4,000행 (계약 열)
│   │           └── ranking_golden.json          순위 대조용 기준 결과 (페르소나 20명)
│   └── jobs/
│       ├── product_encoder.py           상품 → 148차원 콘텐츠 벡터 인코더
│       ├── behavior_weights.py          `types/log.ts` 를 직접 읽는 행동 가중치 로더
│       ├── user_vector.py               이벤트 → v_u⁺ / v_u⁻ 집계
│       ├── build_user_vectors.py        Spark 산출물·JSONL → 사용자 벡터 상태 (Redis 형태)
│       ├── persona_feature.py           페르소나 속성 → 상품별 친화도 (200,)
│       ├── recommender.py               점수 계산·노출 정책·순위
│       ├── export_features.py           서빙용 산출물 + 순위 대조 기준 생성
│       ├── eval_persona_feature.py      9,900명 leave-last-out 검증
│       ├── concern_from_reviews.py · explore_choice.py
│       └── test_*.py                    단위 테스트 (피처·산출물·사용자 벡터)
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
│   ├── collector_client.py              수집 API 전송 (429/503 백프레셔 대응) — 공용
│   ├── test_collector_client.py
│   ├── generator/
│   │   ├── gen_behavior_logs.py         PC 9,900명 합성 로그 (1인당 약 600건)
│   │   ├── build_persona_style.py       리뷰에서 페르소나 6축 스타일 추출
│   │   └── test_gen_behavior_logs.py · README.md
│   ├── agents/agent_runner.py           PA 100명 — 실제 브라우저로 프론트를 조작
│   └── personas/
│       ├── build_personas.py            페르소나 추출
│       └── data/  personas_9900.json · personas_100_agent.json · persona_style.json
│
├── backend/                         Spring Boot 수집 서버 (백엔드)
│   └── src/main/java/com/cosmetic/collector/   POST /api/events → Kafka activity-events
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

## 2. 참고한 폴더 구조

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
