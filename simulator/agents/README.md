# PA 에이전트 — LLM 이 실제 브라우저로 프론트를 조작한다

PC 9,900명이 코드로 합성 로그를 만든다면, PA 100명은 **LLM 이 화면을 읽고 다음
행동을 골라** 진짜 브라우저(Playwright + Chromium)를 움직입니다. 프론트도 수집
서버도 실물이라, 계약이 실제로 지켜지는지가 여기서 드러납니다.

> **정성 검증 축입니다.** 대표 정량 지표(PC 9,900명 오프라인 평가)에 합치지
> 마십시오 — `docs/ai/evaluation-framework.md` 5절.

## 파일

| 파일 | 역할 |
|---|---|
| `agent_runner.py` | 러너. 화면 → 텍스트 → LLM → 행동 → 로그 |
| `model_server.py` | GPU 서버에 모델만 올리는 최소 서버 (OpenAI 호환) |

## 모델을 고르는 세 가지 방법

| 방법 | 어디서 도는가 | 크레딧 | 언제 쓰는가 |
|---|---|---|---|
| 기본 (GMS) | 원격 API | 100명 × 15턴 ≈ **900** | 최종 보고용 1회 |
| `--local-model HF_ID` | 러너 프로세스 안 | **0** | 노트북에서 빠르게. 워커마다 모델이 한 벌씩 올라가 VRAM 이 곱해진다 (8GB 면 1개) |
| `--api-base URL` | 별도 모델 서버 | **0** | GPU 서버에 큰 모델을 올려 두고 브라우저만 노트북에서 |

```bash
# 배선만 확인 (LLM 호출 0회)
python simulator/agents/agent_runner.py --limit 3 --script click_product,add_to_cart

# 노트북 GPU 로
python simulator/agents/agent_runner.py --limit 10 --local-model Qwen/Qwen2.5-3B-Instruct

# GPU 서버에 모델을 올려 두고 (서버 쪽)
python simulator/agents/model_server.py --model Qwen/Qwen2.5-7B-Instruct --port 8501
# 노트북 쪽
python simulator/agents/agent_runner.py --limit 10 \
    --api-base http://<서버>:8501/v1 --model Qwen/Qwen2.5-7B-Instruct
```

프론트(`localhost:5173`)가 떠 있어야 합니다. `--post http://localhost:8080` 을 주면
파일 대신 수집 API 로 보냅니다.

## 판단 근거는 따로 남는다 — `--decisions`

`reason` 이 콘솔에만 찍히면 실행이 끝나는 순간 사라집니다. 실제로 8/31 GMS 100명
실행의 근거 문장이 그렇게 없어졌습니다. 그래서 턴마다 별도 파일로 남깁니다.
경로는 `--out` 옆에 `*_decisions.jsonl` 로 자동 생성되고, `--decisions off` 로 끕니다.

**이벤트에 넣지 않습니다.** 이벤트는 계약(36종)이고 property 도 계약이 정한 것만
씁니다 — `reason` 은 거기에 없습니다. 이벤트 로그와는
`persona_id` + `simulation_run_id` + 시각으로 붙습니다.

| 필드 | 뜻 |
|---|---|
| `screen` · `allowed` | 그 턴에 무슨 화면이었고 어떤 선택지를 줬는가 |
| `llm_action` · `llm_target` · `reason` | 모델이 뭐라고 했고 근거를 뭐라 댔는가 |
| `action` · `target` | **코드가 무엇으로 바꿨는가** |
| `corrected` | 둘이 다르면 교정된 턴 |
| `succeeded` | 그 조작이 실제로 먹혔는가 |

**`corrected` 가 특히 중요합니다.** 러너는 허용 밖 행동을 조용히 교정합니다.
그 비율을 모르면 "LLM 이 판단했다" 고 말할 근거가 얼마나 되는지 알 수 없습니다.

워커를 여러 개 쓰면 조각으로 쓰였다가 하나로 합쳐집니다.

## 왜 모델 서버를 따로 두는가

배정된 GPU 서버에는 주피터만 있고 `node` 도 `sudo` 도 없어 프론트와 Chromium 을
올릴 수 없습니다. 그래서 **모델만** 서버에 두고 브라우저는 노트북에 남깁니다.
노트북 VRAM 8GB 제약이 사라져 7B 이상을 쓸 수 있습니다.

`model_server.py` 는 러너의 `ask()` 가 보내는 것만 받고 `response_format` 같은
모르는 필드는 무시합니다. 작은 모델이 서두를 붙이는 버릇이 있어 `{"action": "` 를
프리필로 넣습니다. GPU 한 장이라 생성은 락으로 직렬화합니다.

**인증이 없습니다.** 사내망에서만 띄우고 끝나면 내리십시오.
**V100 에는 bfloat16 이 없습니다** — `float16` 으로 고정돼 있습니다.

## 로그는 그 사람 것만 남는다 — 페르소나 게이트

`App.tsx` 가 페르소나를 `useState(personas[0])` 로 들고 있어 **페이지를 새로 열면
선택이 PA00001 로 돌아갑니다.** URL 파라미터도 저장소도 없습니다. 그래서 러너는
화면을 먼저 열고 드롭다운으로 페르소나를 고르는데, 그 사이 화면의 이벤트가 전부
PA00001 로 기록됐습니다.

| 2026-09-02 100명 실행 | |
|---|---:|
| 전체 | 49,749건 |
| **PA00001 에 쌓인 것** | **21,767건 (44%)** · 세션 146개 |
| 다른 사람 한 명당(중앙값) | 439건 |

세션이 섞이지는 않습니다 — 페르소나를 바꾸면 새 세션이 시작되므로 **앞 세션
통째로**가 PA00001 몫이 됩니다. `persona_id` 가 채워져 있어 전송 필터도 통과해서
수집 API 로 그대로 나갑니다.

**전환을 앞으로 옮기는 걸로는 못 고칩니다** — 그다음 `goto` 가 선택을 되돌려
그 사람 로그가 통째로 사라집니다 (실측 확인).

그래서 `LogSink` 가 컨텍스트마다 게이트를 하나 들고, **전환 전 이벤트는 파일에도
남기지 않습니다.** 전환 뒤에도 다른 사람 `persona_id` 로 오는 것이 있으면(프론트가
배치로 모아 보내기 때문) 같이 버리고, 실행 요약에 몇 건인지 찍습니다.

근본 수정은 프론트가 `?persona=` 를 읽는 것이고 제안 패치를 넘겨 뒀습니다
(`Research/handoff/frontend-persona-url-param.md`, **미적용**).

**2026-09-03 이전 로그는 이 오염을 안고 있습니다.** 사람 단위로 재려면
`--exclude=PA00001` 로 빼십시오.

## 실행이 좋아졌는지 재는 법

    python simulator/agents/analyze_run_quality.py <이전.jsonl> <나중.jsonl>

재진입률·왕복비·커버리지·교정률을 두 실행에 같은 잣대로 매깁니다. 사람 수가
달라도 되도록 1인당 값과 비율을 함께 냅니다. 프롬프트를 고칠 때마다 이걸로
전후를 비교합니다 — 고친 사람이 좋아졌다고 말하는 것과 수치가 좋아진 것은
다릅니다.

## 러너가 지키는 것

- **실행 메타데이터를 러너가 채웁니다** — `actor_type=synthetic`,
  `generator_type=agent_llm`, `scenario_id`, `simulation_run_id`.
  `clean_events_job` 이 `actor_type` 으로 `user_id`·`source`·`is_synthetic` 을
  파생하므로, 이게 틀리면 거절도 안 되고 조용히 잘못된 데이터가 됩니다
- **페르소나 선택 전 이벤트는 전송에서 제외합니다** — `persona_id` 가 없기 때문입니다
  (파일에는 남깁니다)
- **허용되지 않은 행동은 코드가 교정합니다.** LLM 이 지어낸 상품명으로 엉뚱한
  클릭이 남지 않도록 target 도 화면 기준으로 다시 잡습니다
- **워커는 프로세스로 나눕니다** — Playwright sync API 가 스레드 안전하지 않습니다.
  한 번의 실행이 여러 `simulation_run_id` 로 쪼개지지 않도록 부모가 ID 를 정해
  모든 샤드에 물려줍니다

## 알려진 것

- 작은 모델(3B)은 상태 추적을 자주 놓칩니다 — "이미 본 상품이므로" 라고 써놓고
  그 상품을 누릅니다. 행동 자체는 코드가 교정하므로 로그는 유효하지만,
  `reason` 문장을 근거로 읽으면 안 됩니다
- 화면이 비면 목록으로 되돌리는 방어가 있습니다. 원래는 프론트
  `AboutProduct.tsx` 크래시 때문이었고 **2026-09-02 고쳐졌습니다.** 방어는
  남겨 두었습니다 — 비었는데 계속 조작하면 로그가 조용히 망가집니다
