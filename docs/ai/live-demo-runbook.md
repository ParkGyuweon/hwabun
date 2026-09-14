# 실시간 시연 런북 — 페르소나 9,900명 트래픽 → Kafka 파티션 → 추천 상태 (Jira 295, 2026-09-14 확정)

시연에서 보이려는 것 두 가지. ① 트래픽이 쏟아져도 **분산 처리**된다 — Kafka 파티션 3개가 이벤트를 나눠 받고 추천 서버가
초 단위로 상태에 반영한다. ② **개인화가 즉시 움직인다** — 신규 회원이 SSAFY Beauty 상품 하나에 좋아요를 누르면 목록이 바뀐다.

## 1. 화면: 추천 서버 `/live`

`http://<추천 서버>:8300/live` — 1920×1080 한 화면, 스크롤 없음. HWABUN 팔레트(Warm Ivory 배경 · Fresh Green 막대 ·
Earthy Brown 제목) · Pretendard.

| 위치 | 내용 |
|---|---|
| 상단 4칸 | 초당 반영 이벤트 · 누적(Kafka/직접 구분) · 상태가 바뀐 사용자 수(→ 9,900) · 추천 응답 p50/p95 |
| 상단 오른쪽 | **초당 건수 선택(1,000~8,000) + ▶ 페르소나 9,900명 시작 / ■ 정지** — 서버가 `simulator/generator/demo_live.py` 를 자식 프로세스로 띄운다 |
| 왼쪽 열 | 방금 상태가 바뀐 사용자 40명 (persona_id · 파티션 배지 · 이벤트) |
| 오른쪽 위 | 최근 60초 초당 이벤트 막대 그래프 |
| 오른쪽 아래 | **Kafka 파티션 P0·P1·P2** — 막대 = 최근 10초 처리량(`+N/s`), 숫자 = 누적. key = session_id 라 한 사람은 한 파티션 |

## 2. 기동 순서 (로컬, 노트북 1대)

```bash
# ① Kafka 4.2.1 (KRaft). 토픽 activity-events 파티션 3 은 이미 만들어져 있다
C:\Users\SSAFY\kafka_2.13-4.2.1\start-local.bat          # 9092 뜨는 데 ~12초

# ② 추천 서버 — Kafka 구독 모드, 시연용 세션 로그 경로
cd S15P21A306
PYTHONPATH=. PYTHONUTF8=1 KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9092 RECOMMEND_STATE_GROUP=recommend-live-demo \
  SESSION_EVENTS_PATH=/tmp/demo_session_events.jsonl \
  python -m uvicorn batch.serving.recommend_server:app --host 127.0.0.1 --port 8300
# /live/stats 의 kafka.connected 가 true 되는 데 기동 후 ~30초

# ③ (선택) 프론트 5173 — 개인화 시나리오용
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

브라우저 `http://127.0.0.1:8300/live` → 초당 3,000 선택 → **시작**. 끝나면 버튼이 돌아오고 마지막 줄에 요약이 남는다.
명령줄로 하려면 `python simulator/generator/demo_live.py --rate 3000` (같은 것).

## 3. 데이터

- 9,900명 로그 캐시 `simulator/generator/.cache/demo_behavior_9900.jsonl` — 1,030만 건 · 6.9GB · gitignore. 없으면 첫 시작에
  `gen_behavior_logs.py --limit 9900` 으로 1분 생성.
- 상태에 영향 없는 이벤트(dwell 류 약 30%)는 소비자가 걸러 `filtered` 로 세고, 화면 카운터엔 반영분만 잡힌다.
- 시연 전 `SESSION_EVENTS_PATH` 파일을 비우면 "상태가 바뀐 사용자" 가 0 에서 시작한다.

## 4. 실측 (2026-09-14, 노트북)

| 투입 | 소비 lag | 파티션 분포 | 추천 p50 |
|---|---|---|---|
| 3,000건/초 | ≤ 3 | P0·P1·P2 각 33% ± 1 | 1.2ms |
| 5,000건/초 | 두 자리 | 균등 | 유지 |

## 5. 개인화 시나리오 (별도 화면, 프론트 5173)

가입 직후 회원(행동 0) → 메인 히어로 `SB000001 제로 포어 토닝 패드` → 클릭 → **좋아요** → 목록 복귀.
- 결과: 1·2위가 `딥 비타C 캡슐 세럼`·`콜라겐 젤리 크림`, 히어로는 `딥 비타C 세럼` 으로 바뀜 (SB 3개 top10 진입)
- 더 극적: 상세에서 `PDRN 콜라겐 젤리 겔 마스크` 좋아요 → SB 6개 top10
- 좋아요한 상품 자체는 "이미 반응한 상품 제외" 정책으로 목록에서 빠진다 → 멘트는 "이 브랜드의 다른 상품이 올라온다"
- 상세만 보고 좋아요를 안 하면 변화 0. 피부 속성은 영향 없음(콜드스타트). 미리 다른 좋아요를 누르면 상승폭이 줄어든다
- 배포본에서 돌리려면 백엔드 프록시가 `hero` 파라미터를 통과시켜야 한다(백엔드 요청 2번)

## 6. 함정

- 다른 브랜치를 체크아웃한 상태로 서버를 재기동하면 `/live` 가 없는 옛 코드가 뜬다 (404). 295 머지 전까지는 브랜치 확인.
- Windows 는 `localhost` 가 IPv6 폴백으로 2초 — 주소는 전부 `127.0.0.1`.
- 배포 Docker 이미지엔 `simulator/` 가 없어 시작 버튼이 비활성이다. 서버에서 보이려면 `demo_live.py` 를 밖에서 돌리고
  nginx 에 `/live` 라우트 한 블록.
- Kafka 없이도 `--http` 로 돌아가지만 파티션 칸이 비어 "분산" 은 안 보인다.
