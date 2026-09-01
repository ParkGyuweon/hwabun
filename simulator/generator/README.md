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

`--post` 와 `--out` 은 같이 쓸 수 있다. 전송하면서 파일로도 남는다.

## 규모 감각

| 대상 | 페르소나 | 이벤트 | 생성 시간 | 파일 |
|---|---:|---:|---:|---:|
| 맛보기 | 50 | 약 2만 | 1초 미만 | 10MB |
| 중간 | 1,000 | 약 59만 | 5초 | 300MB |
| 전원 | 10,000 | 약 590만 | 50초 | 3GB |

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
| `frontend/src/types/log.ts` | **이벤트 가중치·intent 의 단일 소스.** 생성기가 직접 읽는다 |

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
2. **탐색** — 목록 → 상세 → 복귀를 2~6회. 이탈 상품은 취향이 아니라
   노출(같은 카테고리 → 인기순)로 고른다
3. **목표 상품** — 끝까지 보고 `add_to_cart`. 45% 확률로 `wishlist_toggle`

리뷰 작성 이벤트는 만들지 않는다. 리뷰는 구매 후 행위라 `add_to_cart` 로 환산했다.

모든 synthetic Event의 `properties`에는 `scenario_id`, `simulation_run_id`,
`generator_type`이 포함된다. 기본 시나리오는 `normal_day`, 생성 방식은
`python_batch`이며, 실행 ID는 생략 시 UTC 시각을 기준으로 자동 생성한다.

```bash
python gen_behavior_logs.py --limit 50 \
  --scenario-id normal_day \
  --simulation-run-id run_20260831_001
```
