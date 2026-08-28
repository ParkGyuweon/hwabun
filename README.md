# S15P21A306 

## 1. 현재 폴더 구조

지금 레포에 실제로 들어있는 것입니다.

```
S15P21A306/
├── README.md                        이 문서
├── .gitignore
│
├── contracts/                       ★ 팀 계약. 여기가 바뀌면 여러 모듈이 동시에 영향받음
│   ├── product-feature-spec.md          상품 벡터 93차원 명세 — 블록 구성·인코딩·가중치·MySQL 스키마
│   ├── product-feature-vocab.json       인코딩 어휘집 `0.3` — 8개 블록의 어휘·문서빈도·가중치
│   └── recommendation-io-spec.md        추천 입출력 데이터 구조 (백엔드↔AI 계약)
│
├── docs/
│   ├── ai/                          추천 알고리즘 설계·검증 (AI 파트)
│   │   ├── recommendation-design.md     CBF 전체 설계안 — 점수 공식, 행동 가중치,
│   │   │                                속성 친화도, 가중치 스케줄, MMR, 서빙 구조
│   │   ├── cbf-technical-review.md      코사인 계산 구조 실측 검증서 — 값 범위, 증분 갱신,
│   │   │                                블록 가중치 튜닝, 성분 어휘 확장, 성능
│   │   └── product-feature-sample.md    상품 5개를 실제로 인코딩한 계산 샘플
│   │
│   ├── analytics/                   행동 로그 설계 (프론트 파트)
│   │   ├── behavior-log-design.md       왜 그 자리에 그 이벤트를 두었는지 — 설계 근거
│   │   └── marketing-signal-research.md 이벤트 목록·가중치의 외부 근거 조사
│   │
│   ├── data/                        데이터 수집 메모 (프론트 파트)
│   │   ├── README.md                    프론트 초기 UI용 샘플 데이터 설명 (상품 8개 / 리뷰 40건)
│   │   ├── field_stats.json             필드별 통계
│   │   └── product-images.md            원본에 없는 이미지·상세 설명을 채운 방법
│   │
│   └── git-convention.md            커밋 메시지·브랜치 전략 (팀 공통)
│
├── batch/                           ★ Spark Batch — 현재는 데이터와 인코더만 존재
│   ├── ingest/data/
│   │   ├── README.md                    배치 입력 데이터 설명
│   │   ├── products_200.json            상품 200개 (원본 27컬럼 + 병합 이력 + 리뷰 통계)
│   │   └── affinity_lift.csv            속성 친화도 테이블 4,000행 (200상품 × 20세그먼트)
│   └── jobs/
│       └── product_encoder.py           상품 → 93차원 콘텐츠 벡터 인코더
│
├── simulator/                       ★ 부하 발생기 — 현재는 페르소나 데이터만 존재
│   └── personas/data/
│       ├── README.md                    페르소나 데이터 설명
│       ├── personas_9900.json           코드 생성용 페르소나 9,900명 (36MB)
│       └── personas_100_agent.json      LLM 에이전트 구동용 100명 (0.4MB)
│
├── frontend/                        React 19 + TypeScript + Vite 8
│   ├── index.html
│   ├── package.json / tsconfig*.json / vite.config.ts
│   ├── .oxlintrc.json                   Oxlint 설정
│   ├── plugins/image-cache.ts           빌드 시 원격 이미지 로컬 캐시
│   ├── scripts/warm-images.ts           이미지 프리페치 스크립트
│   ├── public/                          favicon, 아이콘 스프라이트, 상품 플레이스홀더
│   └── src/
│       ├── main.tsx / App.tsx
│       ├── types/
│       │   ├── log.ts               ★ 행동 로그 이벤트 계약 — 이벤트 26종, 섹션,
│       │   │                          콘텐츠 종류, intent 분류, LogEnvelope
│       │   ├── product.ts / review.ts / persona.ts
│       ├── hooks/                   로그 수집 훅
│       │   ├── useScrollDepth.ts        25/50/75/100% 통과 시점 기록
│       │   ├── useSectionView.ts        IntersectionObserver 기반 섹션 노출·체류
│       │   ├── useTextSelection.ts      텍스트 선택·복사 (성분 검색 의도 신호)
│       │   ├── useInteractionSignals.ts 스크롤 정지·되돌아가기·호버 등 주목 신호
│       │   └── useExitSummary.ts        이탈 시 세션 요약 flush
│       ├── lib/
│       │   ├── logger.ts                이벤트 조립·버퍼링·전송
│       │   ├── section.ts               섹션 ↔ 콘텐츠 종류 매핑
│       │   ├── persona.ts               페르소나 전환 (개발용)
│       │   ├── image.ts / image-widths.ts  이미지 URL·반응형 폭
│       │   └── format.ts
│       ├── pages/ProductDetailPage.tsx  상품 상세 페이지 (로그 트리거의 무대)
│       ├── components/
│       │   ├── product/                 갤러리·요약·성분·하이라이트·옵션·유사상품
│       │   ├── review/                  리뷰 카드·목록·필터·요약
│       │   ├── layout/                  헤더, 페르소나 전환기
│       │   ├── devtools/                개발용 툴바·로그 패널 (찍히는 로그 실시간 확인)
│       │   └── common/                  Accordion, Chip, StarRating, EmptyState
│       ├── mocks/                       상품·리뷰 샘플 JSON
│       └── styles/ · index.css
│
└── 1차 평가/                        평가 제출물 (팀원별 폴더)

## 2. 참고폴더 구조 -

아래는 참고한 구조입니다. 

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
│   │   └── KafkaProducerService     partition_key=persona_id/user_id로 전송. 동기 처리 금지
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