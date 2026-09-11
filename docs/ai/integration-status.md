# 파트 간 연결 현황 (2026-09-11, dev 5b5e465 기준)

레포 전체를 훑어 **누가 누구를 부르고, 양쪽이 다 있는지, 이름·파라미터가 맞는지**를 표로 적었다.
파트 이름은 프론트 · 쇼핑몰 백엔드(`shop_backend`) · 수집기(`backend`) · 데이터(`streaming`) · AI(`batch`·`simulator`) 로 쓴다.
근거는 파일:줄. 브랜치에만 있는 것은 그렇게 표기했다. 다음 점검 때 이 파일을 갱신한다.

## 1. 연결 표

| 연결 | 호출 쪽 | 받는 쪽 | 상태 | 비고 |
|---|---|---|---|---|
| 프론트 → 쇼핑몰 `POST /api/auth/login·members·sellers` | `frontend/src/lib/auth.ts:178,197` | `shop_backend/.../identity/IdentityController.java:65,88,111` | 연결됨 | 가입 속성 4개(`skinTypeCode` …)는 프론트가 보내지만 `RegisterMember` 가 아직 안 받음 → 프론트 요청 8번 |
| 프론트 → `GET/POST /api/brands` | `frontend/src/lib/brands.ts:50,65` | `.../brand/BrandController.java:40,56` | 연결됨 | |
| 프론트 → `GET /api/products`, `/api/products/{id}` | `frontend/src/lib/shopApi.ts:180,195` | `.../catalog/CatalogController.java:46,56` | 연결됨 | 비로그인 허용 |
| 프론트 → `POST /api/products` (상품 등록) | `shopApi.ts:248` | `CatalogController.java:111` | 연결됨 · **값 불일치** | 프론트가 `categoryId` 에 `secondary_category` 문자열을 넣고 category 시드가 없어 항상 400 (`shopApi.ts:17` 자체 주석) |
| 프론트 → `PATCH /api/products/{id}/status` | `shopApi.ts:263` | `CatalogController.java:163` | 연결됨 | |
| 프론트 → 장바구니·주문·결제 | `shopApi.ts:287,294,303` | `.../commerce/CommerceController.java:82,133,226` | 연결됨 | `GET /api/orders`(내 주문 목록) 없음 → 프론트 로컬 표시 |
| 프론트 → 피드백·리뷰 | `shopApi.ts:320,358,409` | `.../feedback/FeedbackController.java:84,134,73` | 연결됨 | |
| 프론트 → `GET /api/seller/dashboard` | `shopApi.ts:443` | `.../dashboard/DashboardController.java:20` | 연결됨 | 주문·매출·리뷰·피드백 4칸 |
| 프론트 → **마트 API 6개** `/api/seller/dashboard/{overview,products,content,segments,ingredients,friction}` | `frontend/src/dashboard/lib/martApi.ts:221~242` | **없음** | **한쪽만** | 계약 `contracts/dashboard-mart-api-spec.md` 는 쇼핑몰 백엔드를 서버로 지정. 구현 0. 대시보드는 모의값으로 동작 |
| 프론트 → 추천 `GET /api/recommend` | `frontend/src/lib/recommendApi.ts:136~163` (persona_id·size·banner_slots·reserved·hero·axes·skin_type·skin_tone·hair_color·eye_color) | `batch/serving/recommend_server.py:548~559` | 연결됨 (**로컬 Vite 프록시만**) | `vite.config.ts:41~46` 이 8300 으로 직결. 운영 경로는 아래 프록시 |
| 프론트 → 처방 `POST /api/prescription` | `frontend/src/dashboard/lib/prescriptionApi.ts:182` | `recommend_server.py:666` | 연결됨 (로컬만) | `GMS_KEY` 없으면 503 |
| 프론트 → 수집기 `POST /api/events` | `frontend/src/lib/logger.ts:79,581,605` | `backend/.../event/api/EventController.java:41` | 연결됨 | 스키마 `0.2.0-draft` 양쪽 일치. JWT 비밀키 `SHOP_BACKEND_JWT_SECRET` 를 쇼핑몰과 공유, 무효 토큰은 익명 |
| 수집기 → Kafka `activity-events` | `backend/.../KafkaEventPublisher.java:47` | 토픽 | 연결됨 | snake_case, `account_id` 포함 |
| Kafka → 데이터 Spark raw/clean/facts/marts | `streaming/jobs/raw_sink_job.py:23,266` → `build_marts_job.py` | Delta/Parquet 마트 12종 | 연결됨 (배치) | **마트 → MySQL `dw.*` 투영 잡 없음** (jdbc/mysql 0건) |
| Kafka → 추천 서버 상태 소비자 | `batch/serving/kafka_state.py:36~76` (group `recommend-state-v1`) | 수집기 메시지 | 연결됨 (스키마 일치) | `KAFKA_BOOTSTRAP_SERVERS` 없으면 비활성. 09-11 EC2-1 은 브로커 다운으로 connected=false |
| 추천 서버 → 쇼핑몰 카탈로그 동기화 `GET /api/products(/{id})` | `batch/serving/catalog_sync.py:72,100` | `CatalogController.java:46,56` | 연결됨 (필드 일치) | `SHOP_BACKEND_URL` 비면 안 함 — compose 기본값이 빈 문자열이라 **운영에서 꺼져 있음** |
| 쇼핑몰 승인 → 추천 `POST /api/products` (승인 훅) | **없음** (`shop_backend` 에 HTTP 클라이언트·recommend 참조 0건) | `recommend_server.py:593` | 한쪽만 | 5분 주기 동기화가 대체 (위 행). 계약상 선택 사항 |
| 쇼핑몰 → 추천 **프록시** `GET /api/recommend` | **dev 에 없음.** 브랜치 `feat/recommendation-proxy-mvp` 만: `RecommendationController.java:24~31` → `RecommendationClient.java:35~41` | `recommend_server.py:548` | **미머지 + 파라미터 불일치** | 브랜치는 `size·reserved·banner_slots·axes` 만 전달, **`hero`·속성 4개를 버림**. `persona_id=accountId` (맞음). 익명도 전달 (09-10 합의는 "안 부름") |
| 시뮬레이터 → 추천 `GET /api/recommend`, `POST /api/events` | `simulator/generator/recommend_client.py:73~90` | `recommend_server.py:548,686` | 연결됨 | 09-10 부터 `banner_slots=1·hero=new_brand` |
| 시뮬레이터 → 수집기 `POST /api/events` | `simulator/collector_client.py:36`, `agent_runner.py:1769` | `EventController.java:41` | 연결됨 | |
| 한국어화 JSON → 프론트 | `frontend/src/lib/localize.ts:18~20` (import) | `contracts/localization/*.json` | 연결됨 | `reviews-ko.json` 이 09-11 에 20,000건(9.1MB)이 되어 **번들에 그대로 실림** — 프론트가 상품별 파일 fetch 로 바꾸기 전까지 |
| nginx `/api/` → 컨테이너 | `deploy/nginx/default.conf:29~30` `proxy_pass http://backend:8080` | compose `backend` = **수집기** | **경로 불일치** | `/api/auth·products·recommend·prescription·seller/*` 가 전부 수집기로 가서 404. `recommend` 는 compose 에 있지만 nginx 라우트 없음(내부 전용) |

## 2. 끊어진 곳 (배포본 기준)

1. **운영 배포에 쇼핑몰 백엔드·MySQL 이 없다.** `deploy/ec2-1/docker-compose.yml` 서비스는 backend(수집기)·recommend·nginx·prometheus·grafana. nginx 가 `/api/` 전부를 수집기로 보내니 배포본에서 로그인·상품·주문·추천·처방이 전부 404. 2026-09-11 아침 기준 EC2-1 에 떠 있는 컨테이너는 `recommend` 하나.
2. **마트 API 서버가 없다.** 프론트가 6개 경로를 부르지만 쇼핑몰에는 `/api/seller/dashboard` 하나뿐. 데이터 쪽도 마트 → MySQL 투영 잡이 없어 계약의 두 단(데이터→dw.* / 백엔드→6 엔드포인트) 모두 미구현.
3. **추천 프록시 미머지.** dev 쇼핑몰에 `/api/recommend` 없음. 브랜치는 dev 대비 11파일 +249.
4. **승인 훅 없음 + 동기화 꺼짐.** 쇼핑몰이 추천 `POST /api/products` 를 부르는 코드 0건. 대체 경로인 5분 동기화는 `SHOP_BACKEND_URL` 기본값이 빈 문자열이라 운영에서 안 돈다.
5. **프론트 도커 빌드가 깨질 가능성.** `deploy/nginx.Dockerfile:7` 은 `contracts/product-feature-vocab.json` 하나만 복사하는데 프론트는 `product-form-labels-ko.json`·`feedback-category-vocab.json`·`localization/*.json` 도 import 한다. **확인 필요:** 실제 `npm run build` 로그.

## 3. 불일치

1. **프록시 브랜치가 쿼리를 버린다** — 프론트가 보내는 `hero`·`skin_type`·`skin_tone`·`hair_color`·`eye_color` 를 `RecommendationQuery.java` 가 받지 않는다. 머지되면 히어로가 원천 상품으로 돌아가고 실회원 속성 친화도가 중립이 된다. 계약 §5 "프록시는 쿼리스트링 그대로 넘긴다"(09-11 합의) 와 어긋남. → 백엔드 전달 문서(09-11) 로 요청함.
2. **프록시 브랜치가 수집기를 교체한다** — `deploy/backend.Dockerfile` `COPY backend/` → `COPY shop_backend/`, compose `backend` 에 `SERVER_PORT: 8080`. 그대로면 compose 의 `backend` 컨테이너가 쇼핑몰이 되고 **수집기(`/api/events`) 컨테이너가 사라진다.** 의도(교체 vs 서비스 추가)는 브랜치 MR 설명에서 확인 필요.
3. **프록시 브랜치가 익명을 허용한다** — `SecurityConfig` 에 `GET /api/recommend` permitAll + 익명은 persona_id 없이 전달. 09-10 합의(비로그인은 프록시가 부르지 않음, 기획 §15-11)와 반대.
4. **상품 등록 categoryId** — 프론트가 `secondary_category` 문자열을 넣음. 백엔드 category 테이블 id·시드와 안 맞아 항상 실패.
5. **포트** — 쇼핑몰 8090, 수집기 8080. Vite 프록시는 맞게 나눴지만 nginx 는 8080 하나만 안다.

## 4. 파트별 다음 손

| 파트 | 할 일 |
|---|---|
| 쇼핑몰 백엔드 | 프록시: `hero`+속성 4개 통과(또는 Member 값 직접 부착), 익명 차단 · `RegisterMember` 속성 4개 · compose 에 쇼핑몰+MySQL 서비스 추가(수집기 교체 아님) · 마트 API 6개 · category 시드 |
| 수집기/인프라 | nginx 라우팅: `/api/events`→수집기, 나머지 `/api/`→쇼핑몰 8090 · nginx.Dockerfile 에 프론트가 import 하는 contracts JSON 추가 |
| 데이터 | 마트 → MySQL `dw.*` 투영 잡 · Kafka 브로커(j15a306:9092) 기동 |
| 프론트 | 상품별 리뷰 파일 fetch(§1-1~1-3) + `reviews-ko` import 제거 · `categoryId` 값 |
| AI | (완료) 245 속성 쿼리·EC2-1 배포. 남은 것: 프록시 머지 후 E2E 확인, `SHOP_BACKEND_URL` 운영값 |
