# simulator/ — 페르소나 · 합성 로그 · 브라우저 에이전트 · 피드백

실사용자가 없는 프로젝트에서 행동 로그와 평가 표본을 만드는 쪽. 평가 체계는 `docs/ai/evaluation-framework.md`.

| 폴더 | 무엇 | README |
|---|---|---|
| `personas/` | 실제 Sephora 리뷰어에서 층화추출한 페르소나 10,000명(코드 9,900 + 에이전트 100) + 홀드아웃 2,000×2. `build_personas.py` | [`personas/data/README.md`](personas/data/README.md) |
| `generator/` | 코드 페르소나의 합성 행동 로그. `--recommend-url` 로 실제 추천 서버 응답을 쓴다(히어로 1칸 `hero=new_brand`, Jira 239). `--post` 로 수집기에 전송 | [`generator/README.md`](generator/README.md) |
| `agents/` | LLM 에이전트 100명이 실제 화면을 조작 (Playwright). 프롬프트로는 페르소나 차이가 안 난다(lift 1.0x) — 다음 손잡이는 러너 코드 필터(Jira 241) | [`agents/README.md`](agents/README.md) |
| `feedback/` | 고객 피드백 생성·분류(고정 목록 5축 20종, 계약 `contracts/feedback-classification.md`)·금지어 | 계약 문서 참조 |
| `collector_client.py` | 수집기 `POST /api/events` 클라이언트 (에이전트·생성기 공용) | — |

## 테스트

```bash
cd <레포 루트>
PYTHONPATH=. python -m unittest simulator.generator.test_gen_behavior_logs simulator.generator.test_recommend_client simulator.test_collector_client
```

## 주의

- PA(에이전트) 실행은 반드시 `--out` 을 준다 — 기본 경로를 덮어써 본실행 파일을 잃은 사고가 있었다(09-08).
- 에이전트 100명은 대표 정확도에 합치지 않는다. UI·로그 계약 검증용.
- `localhost` 대신 `127.0.0.1` (Windows IPv6 폴백 2초).
