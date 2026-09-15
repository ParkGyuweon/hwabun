# 행동 로그 생성기

**PC 페르소나 9,900명**의 탐색 행동을 만들어 **파일로 저장**하거나
**수집 API 로 바로 전송**한다.

PA(LLM 에이전트) 100명은 기본으로 **생성하지 않는다** (`--include-agents` 필요).
PA 는 대표 정량 지표에 합치지 않는 **별도의 정성 검증 축**이다
(docs/ai/evaluation-framework.md 5절). 두 집단을 합쳐 하나의 성능처럼 보고하지 않는다.

## 행동을 무엇이 정하는가 — 평가용이면 모드를 바꿀 것

기본(`--behavior rule`)은 **평가 정답(target)을 알고 그 상품에 전환을 강제한다.**
트래픽·파이프라인·부하 검증에는 문제없지만, 그 로그로 추천을 평가하면 정답이 로그에
심겨 있어 자기실현 평가가 된다 (실측: target 을 담은 사람 30/30명).

```bash
python simulator/generator/gen_behavior_logs.py --behavior hidden_preference
```

이 모드는 추천·정답과 분리된 hidden preference 가 행동 강도를 정하고 target 에
전환을 강제하지 않는다 (실측: 30명 중 1명, 우연히 담긴 것). **평가에 쓸 로그는
반드시 이 모드로 만든다.** 계약: `docs/ai/evaluation-framework.md` 2절 · 부록 F

이벤트 형식은 프론트 `LogEnvelope` 와 같고, 백엔드 `ActivityEvent` 검증 규칙
(`event_name` 패턴 · `intent` 8종 · `page_type` 3종 · `sequence_no` 양수 등)을
전부 통과하는 것을 확인했다. `actor_type` 은 항상 `synthetic` 이라
실제 사용자 로그와 섞이지 않는다.

생성 직후에는 `contracts/event-properties-schema.md`를 읽어 Event별 required
property, 타입, enum도 검사한다. 위반이 하나라도 있으면 파일 저장이나 Collector
전송 전에 실행을 실패시킨다. 100명 생성 결과 99,672건에서 Properties 위반 0건을
확인했다. 생성하지 않은 `navigation_click`, `dead_click`을 제외한 34/36 Event가
해당 표본에 포함됐다.

## 무엇이 화면에 노출되는가 — `--exposure`

사람은 위에 있는 것을 본다. 그런데 기본값(`popular_v0`)은 **전원에게 같은 인기순
화면**을 보여준다 — 건성인 사람과 지성인 사람이 같은 상품을 본다.

| 정책 | 방문 후보를 어떻게 뽑나 |
|---|---|
| `popular_v0` (기본) | 같은 카테고리 → 인기순. 전원이 같은 화면 |
| `cbf_v1` | **추천 점수가 후보의 절반**을 정한다. 나머지는 카테고리 25% + 무작위 25% |

`cbf_v1` 은 실제 쇼핑몰처럼 추천이 진열에 영향을 주는 상황을 만든다. 후보 구성비는
`eval_dynamic.py` 와 같다 — 추천 Top 만 보면 추천이 자기가 고른 것만 채점하게 된다.

**노출만 추천이 정한다. 행동은 hidden preference 가 정한다.** 둘 다 추천이 정하면
추천이 자기가 띄운 것을 자기가 맞히는 로그가 되어 아무것도 측정할 수 없다.

> ⚠️ **이 로그로 추천 정확도를 재지 않는다.** 정책이 바뀌면 숫자가 같이 움직여서
> "추천이 좋아졌는가" 와 "노출을 많이 했는가" 가 섞인다. 대표 정확도는 리뷰 이력
> 기반 오프라인 평가가 담당한다. 이 로그는 **노출 대비 클릭·전환·커버리지를 정책끼리
> 비교**하는 데 쓴다. 정책이 다른 로그의 수치를 나란히 놓지 말 것.

정책 이름은 `impression_dwell` 의 `algorithm` 에 실린다 — 표시가 없으면 나중에
정책이 다른 로그가 섞여도 구분할 방법이 없다.

실측 (20명 · `--behavior hidden_preference`)

| | `popular_v0` | `cbf_v1` |
|---|---:|---:|
| 노출 → 클릭 | 8.8% | 9.6% |
| 장바구니 | 74건 | 100건 |
| 담긴 고유 상품 | 63개 | 81개 |
| 노출된 고유 상품 | 198개 | 178개 |

개인화된 노출이 보는 상품 폭은 좁히면서 담기는 늘렸다. 20명 표본이라 방향만 읽을 것.

## 빠른 시작

```bash
# 1) 맛보기 — 50명, 파일로 저장
python simulator/generator/gen_behavior_logs.py --limit 50

# 2) 백엔드로 전송 (서버가 떠 있어야 한다)
python simulator/generator/gen_behavior_logs.py --limit 50 --post http://localhost:8080

# 3) 부하 조절 — 초당 200건
python simulator/generator/gen_behavior_logs.py --limit 500 --post http://localhost:8080 --rps 200

# 4) 전원 10,000명 (약 590만건 / 3GB)
python simulator/generator/gen_behavior_logs.py --post http://localhost:8080 --rps 2000
```

의존성은 `numpy` 하나다. 전송은 표준 라이브러리(`urllib`)를 쓴다.

## 옵션

| 옵션 | 뜻 | 기본값 |
|---|---|---|
| `--limit N` | 앞에서 N명만 생성 | 전원 |
| `--post URL` | 수집 API 베이스 URL. `/api/events` 는 자동으로 붙는다 | 없음 |
| `--rps N` | 초당 이벤트 수 제한. 0 이면 제한 없음 | 0 |
| `--out PATH` | jsonl 저장 경로 | `--post` 도 `--out` 도 없으면 `behavior_logs.jsonl` |
| `--show N` | 첫 페르소나의 이벤트 N건을 출력 | 0 |
| `--exposure {popular_v0,cbf_v1}` | **무엇이 화면에 노출되는가** (아래) | `popular_v0` |
| `--recommend-url URL` | **추천 서버 연동** (Jira 221, 아래 절). 목록마다 실제 추천을 받아 그 식별자로 이벤트를 만든다 | 없음 |
| `--banner-slots N` · `--reserved N` · `--hero top\|new_brand` | 추천 서버에 요청할 배너 칸 수 · 전용 배너 칸 수 · 히어로 정책 (Jira 237). 화면이 히어로 하나라 기본이 1 · 0 · new_brand (Jira 239) | 1 · 0 · new_brand |

`--post` 와 `--out` 은 같이 쓸 수 있다. 전송하면서 파일로도 남는다.

## 추천 서버 연동 — `--recommend-url` (Jira 221)

```bash
python -m uvicorn batch.serving.recommend_server:app --port 8300      # 추천 서버 먼저
python simulator/generator/gen_behavior_logs.py --recommend-url http://localhost:8300 --limit 200 --out logs.jsonl
```

없을 때는 생성기가 배너를 자기 규칙(`banner_axes_v0`)으로 뽑고 `recommendation_id` 도 가짜로 만든다. 주면 **프론트 184 와 같은 경로**로 바뀐다.

| 화면 | 없을 때 | 있을 때 |
|---|---|---|
| 목록의 맞춤 기획전 행 | 인기순 10개, 노출 이벤트 없음 | 서버 `items` 10개. `recommendation_snapshot`(list_id `main`) 1건 + 칸마다 `recommendation_impression`. 식별자·`algorithm`(`ltr-369t-…`)은 응답 그대로 |
| 히어로 배너 1칸 (2026-09-10, Jira 239 — 배너 행 6칸은 기획 검토로 화면에서 빠짐) | 리뷰가 가장 적은 상품을 new_brand 히어로로, `banner_axes_v0` | 서버 `hero` 그대로(`hero=new_brand`: 신규 상품 중 점수 최고) — `banner_slot` 1·`list_id` `hero_banner`·`banner_type`·`banner_value`(null 키 유지)·`trait_source`·`policy_version`(프론트 bannerConfig 와 같은 값). 응답 `banners[]` 는 화면에 없어 쓰지 않는다 |
| 클릭 | 이번 상품을 배너에 끼워 넣고 누른다 | **서버가 실제로 노출한 상품** 중에서 고른다 — 배너(`p_banner_click`) 또는 메인 카드(`p_rec_click`). 노출과 같은 `recommendation_id`·칸 번호 |
| 세션 상태 | — | 목록을 열기 전에 그동안의 행동을 `POST /api/events` 로 서버에 넘긴다 → 다음 추천이 그 행동을 반영(`state_source=events`) |

실측 (40명 · 46,934건): 추천 호출 173 · 상태 전송 133회 18,685건 · 6초. 봉투 검증 47,112/47,112 통과. 배너 노출 1,038 → 클릭 18, 메인 노출 2,228 → 클릭 93.
서버가 죽으면 **한 번 경고하고 예전 방식으로 계속** 돈다 — 부하 테스트는 서버 없이도 돌아야 한다.
`localhost` 는 클라이언트가 `127.0.0.1` 로 바꿔 부른다 (Windows 에서 ::1 시도로 호출마다 2초를 잃는다).

## 규모 감각

| 대상 | 페르소나 | 이벤트 | 생성 시간 | 파일 |
|---|---:|---:|---:|---:|
| 맛보기 | 50 | 약 2만 | 1초 미만 | 10MB |
| 중간 | 1,000 | 약 59만 | 5초 | 300MB |
| 전원 (`--include-agents`) | 10,000 | 약 590만 | 50초 | 3GB |

전송은 100건씩 배치로 나간다(백엔드 `EventBatchRequest` 의 `@Size(max = 100)`).
**전원을 제한 없이 보내면 59,000회 요청**이 나가므로, 처음에는 `--limit` 과 `--rps` 로
작게 시작하는 것을 권한다.

## 전송 결과 읽는 법

```
[17:02:11] 수집 API 전송 시작 -> http://localhost:8080  (배치 100건, 200건/초 제한)
================================================================
전송 결과  성공 24,727건 / 실패 0건 / 123.6초  (200건/초)
================================================================
```

실패가 있으면 첫 HTTP 응답 본문을 함께 출력한다.

| 응답 | 뜻 | 할 일 |
|---|---|---|
| 202 | 정상. Kafka 발행까지 성공 | — |
| 400 | 계약 불일치 | 응답의 `details` 에 어느 필드인지 나온다 |
| 503 | `KAFKA_UNAVAILABLE`. **계약은 통과했고 Kafka 만 없다** | Kafka 를 띄운다 |

Kafka 가 안 떠 있으면 백엔드가 발행을 기다리다 **25초쯤 뒤에** 503 을 준다.
그래서 클라이언트 타임아웃을 40초로 잡아뒀다. 짧게 잡으면 클라이언트가 먼저 끊겨서
"타임아웃" 으로만 보이고 진짜 원인을 못 본다.

### 확인한 것 / 못 한 것

로컬에서 백엔드만 띄우고(Kafka 없이) 실제로 쏴본 결과 **503 KAFKA_UNAVAILABLE** 이 나왔다.
`ActivityEvent` 검증을 전부 통과하고 발행 단계에서만 막혔다는 뜻이다.
**Kafka 를 띄운 상태에서 202 가 나오는 것은 아직 확인하지 못했다.**

## 데이터 출처

| 파일 | 내용 |
|---|---|
| `simulator/personas/data/personas_9900.json` | 리뷰 3개 이상 상품에 남긴 실제 사용자에서 추출 |
| `simulator/personas/data/personas_100_agent.json` | 속성을 무작위로 부여한 검증용 에이전트 |
| `simulator/personas/data/persona_style.json` | 페르소나 성향 6축. 리뷰 텍스트에서 도출 |
| `batch/ingest/data/products_200.json` | 상품 카탈로그 |
| `frontend/src/mocks/products.sample.json` | 실제 SKU와 variant label |
| `frontend/src/types/log.ts` | **이벤트 가중치·intent 의 단일 소스.** 생성기가 직접 읽는다 |
| `contracts/event-properties-schema.md` | Event별 required property, 타입, enum 계약 |

마지막 항목이 중요하다. 가중치를 파이썬 쪽에 복사해두지 않고 `log.ts` 를 파싱하므로,
프론트가 이벤트를 추가하거나 이름을 바꾸면 생성기가 **자동으로 따라간다.**
형식이 크게 바뀌어 파싱에 실패하면 예외로 죽는다 — 낡은 값으로 도는 것보다 낫다.

## 페르소나 성향 다시 만들기 (선택)

`persona_style.json` 은 이미 커밋돼 있어 그냥 쓰면 된다.
다시 만들려면 SBERT 가 필요하다.

```bash
pip install sentence-transformers
python simulator/generator/build_persona_style.py
```

성향은 **"어떻게 보는가"** 만 정한다. 성분에 민감한 페르소나는 `ingredients` 섹션을
오래 보고 아코디언을 자주 열지만, **무엇을 고를지에는 관여하지 않는다.**
후자를 건드리면 추천 점수가 쓰는 축과 겹쳐 순환이 된다.

## 생성되는 행동

페르소나 한 명당:

1. **시드** (`seed:{simulation_run_id}:{persona_id}:{product_id}`) — 시뮬레이션 시작 전 상태
   - 별점 4~5점 상품 → `add_to_cart`
   - 별점 1~2점 상품 → 상세에 들어갔다 얕게 보고 이탈 (`scroll_backtrack`, 35% 확률로 `rage_click`)
   - 3점 상품 → 아무 데도 넣지 않는다
   - 시드 세션은 NOW 기준 **최근 85일**에 흩어 놓고 재구매 간격은 14~30일이다 (Jira 313, 2026-09-15). 데이터 마트의
     재구매 창이 최근 90일이라 첫 구매와 재구매가 둘 다 창 안에 있어야 재구매율이 잡힌다. 120일이었을 때는 시드 결제가
     4~5월에 몰려 `repeat_buyer` 가 전부 0 이었다.
2. **탐색** — 목록 → 상세 → 복귀를 2~6회. 이탈 상품은 취향이 아니라
   노출(같은 카테고리 → 인기순)로 고른다
3. **목표 상품** — 끝까지 보고 `add_to_cart`. 45% 확률로 `wishlist_toggle`

리뷰 작성 이벤트는 만들지 않는다. 리뷰는 구매 후 행위라 `add_to_cart` 로 환산했다.

4. **결제** (Jira 312, 2026-09-15) — 시드(과거 구매)와 재구매(S2)는 담기 뒤 **전부** `begin_checkout → purchase →
   purchase_reason_select` 까지 간다(리뷰를 썼다 = 샀다). 목표 상품은 담은 세션의 45% `[추정]`가 결제까지 간다.
   결제 5% 는 `payment_failed`(user_cancel), 설문은 70% 응답(1~2개, 재구매면 `restock` 첫 번째)·30% `skipped`.
   금액은 이벤트 계약대로 USD, `order_channel=backend`, 결제수단은 kakaopay 60 / card 40 (`test` 는 시연 전용이라 안 씀).
   이게 없던 09-14 캐시로는 데이터 마트의 재구매·구매 사유 3종이 0 이었다.

모든 synthetic Event의 `properties`에는 `scenario_id`, `simulation_run_id`,
`generator_type`이 포함된다. 기본 시나리오는 `normal_day`, 생성 방식은
`python_batch`이며, 실행 ID는 생략 시 UTC 시각을 기준으로 자동 생성한다.

```bash
python gen_behavior_logs.py --limit 50 \
  --scenario-id normal_day \
  --simulation-run-id run_20260831_001
```

## 시연: 9,900명을 쏟아 넣고 실시간으로 본다 — `demo_live.py` (Jira 295)

```bash
# 1) Kafka (로컬: C:/Users/SSAFY/kafka_2.13-4.2.1/start-local.bat, 토픽 activity-events 파티션 3)
# 2) 추천 서버를 Kafka 구독으로
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9092 SESSION_EVENTS_PATH=/tmp/demo_session.jsonl python -m uvicorn batch.serving.recommend_server:app --port 8300
# 3) 한 방
python simulator/generator/demo_live.py                # 9,900명 · 3,000건/초 · 캐시 없으면 로그 생성(1분, 6.9GB)
python simulator/generator/demo_live.py --rate 5000 --max-events 3000000
python simulator/generator/demo_live.py --http         # Kafka 없이 (파티션 칸은 비어 있다)
```

브라우저 `http://127.0.0.1:8300/live`: 초당 반영 이벤트(60초 막대) · **Kafka 파티션 3개별 소비**(key = session_id 라 사람이
파티션에 갈린다) · 상태 바뀐 사용자(→ 9,900) · 방금 바뀐 사용자 40명 · 추천 p50/p95. 실측(2026-09-14, 노트북): 3,000건/초
투입에 소비 lag 3 이하, 추천 p50 1.2ms 유지. 5,000건/초도 lag 두 자리. 상태에 영향 없는 이벤트(dwell 류 약 30%)는
소비자가 걸러(`filtered`) 화면 카운터엔 반영분만 잡힌다. 로그는 `.cache/` 에 남고 gitignore 다.
