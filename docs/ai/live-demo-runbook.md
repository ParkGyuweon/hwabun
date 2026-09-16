# 실시간 시연 런북 — 페르소나 9,900명 트래픽 → Kafka 파티션 → 추천 상태 (Jira 295 · 311 · 320, 2026-09-16 갱신)

시연에서 보이려는 것 두 가지. ① 트래픽이 쏟아져도 **분산 처리**된다 — Kafka 파티션 3개가 이벤트를 나눠 받고 추천 서버가
초 단위로 상태에 반영한다. ② **개인화가 즉시 움직인다** — 신규 회원이 SSAFY Beauty 상품 하나에 좋아요를 누르면 목록이 바뀌고,
가격대만 훑으면 히어로 배너가 가격 문구로 바뀐다.

> **2026-09-15 배포 서버 상태 (먼저 읽을 것).** EC2-1 추천 컨테이너는 dev bd54d4e(302~308)로 올라가 있고 카탈로그는 깨끗하다.
> 그런데 **행동 이벤트가 0건 들어온다** — `.env` 의 Kafka 호스트가 EC2-1 자기 주소인데 브로커는 EC2-2 에 있어야 하고 아직 안 떴다.
> 수집기도 같은 이유로 이벤트를 버린다. 이게 풀려야 §5 시나리오의 2~4번이 배포본에서 움직인다 (인프라 몫, 09-15 회의 안건).
> `GMS_KEY` 도 비어 있어 대시보드 AI 처방 문장은 503 → 규칙표 문장만 나온다 (백엔드에 .env 채움 요청).

## 0. 시연 전 점검표 — 배포 서버 (EC2-1)

전부 읽기 전용이다. 하나라도 어긋나면 §6 함정에서 찾는다.

```bash
ssh -i ~/Downloads/J15A306T.pem ubuntu@j15a306.p.ssafy.io \
  'sudo docker exec ec2-1-recommend-1 python -c "import json,urllib.request;h=json.load(urllib.request.urlopen(\"http://127.0.0.1:8300/health\"));print(json.dumps({k:h.get(k) for k in (\"ok\",\"products\",\"registered_products\",\"new_brand_rule\",\"sessions\",\"kafka_state\",\"catalog_sync\",\"user_trait\")},ensure_ascii=False,default=str)[:1500])"'
```

| 값 | 기대 | 어긋나면 |
|---|---|---|
| `products` / `registered_products` / `new_brand_rule.new_now` | 208 / 8 / 8 | 원천 200개가 등록 상품으로 바뀐 것(308 이전 이미지) → 재배포 + `reset-registered-local.sh` |
| `kafka_state.connected` | true, `broker_errors` 안 늘어남 (09-15 17:40 부터 EC2-2 브로커 `j15a306a.p.ssafy.io:9092` 에 연결됨) | 브로커 미기동 또는 `.env` 호스트 오류(EC2-1 자기 주소면 틀림). 인프라 |
| `sessions.personas_in_memory` | 시연 트래픽 뒤 > 0 | 이벤트가 안 들어옴 = Kafka. `--http` 보험(§2-B) |
| `catalog_sync.last` | `replaced 0 · seed_kept 200 · added/unchanged 8` | `replaced` 가 크면 옛 이미지 |
| `user_trait.source` | dw 연결 전엔 null (정상 — 적재 Job 이 아직 없어 세 경로 전부 없음, 09-16) | dw 붙으면 `dw_mysql:…`, `age_days` ≤ 2 (319) |
| 컨테이너 어휘집 | `vocab 0.7 [0, 26000, 46000, 66000, 105000]` | 백엔드 재배포가 옛 브랜치로 되돌린 것(§6) |
| 응답 `hero.hero_policy_version` | `hero-2026-09-15` | 307 이전 이미지 |
| `prescription.enabled` / `key_present` / `llm_calls` | 시연 직전 true / true, 끝나면 false 로 | GMS 과금은 처방 요청에서만 난다(배치·Kafka 아님). 켜기·끄기(컨테이너에 curl 없음, python 으로): `sudo docker exec ec2-1-recommend-1 python -c "import urllib.request as u;r=u.Request('http://127.0.0.1:8300/api/prescription/llm',data=b'{\"enabled\":false}',headers={'content-type':'application/json'});print(u.urlopen(r).read().decode())"` — 메모리 상태라 재배포하면 `.env` 의 `PRESCRIPTION_LLM`(기본 on)으로 돌아간다 (Jira 325). GMS_KEY 는 EC2-1 `deploy/ec2-1/.env` 에만 있다(레포 아님, 09-16 투입) |

컨테이너 버전과 코드 존재는 재배포 스크립트 끝 줄이 찍어 준다: `image latest==running OK` · `code: user_trait.py`.

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

## 2. 기동 순서

### 2-A. 로컬 (노트북 1대) — 리허설용

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

### 2-B. 배포 서버 (EC2-1) — 본 시연

```bash
# ① 추천 컨테이너를 dev 최신으로 (1~2분, --no-cache). 성공 = 끝 줄 "image latest==running OK" + "code: user_trait.py" + vocab 0.7
bash deploy/ec2-1/redeploy-local.sh
# ②(필요할 때만) 볼륨의 등록 상품 파일을 SB 8개로 되돌린다 — health 의 registered 가 8 이 아니거나 new_now 가 8 을 넘을 때
bash deploy/ec2-1/reset-registered-local.sh
# ③ 점검표 §0
```

- 백엔드가 `ec2-1-deploy` 브랜치로 전체 재배포하면 추천 컨테이너가 **그 브랜치 코드로 되돌아간다**(09-15 10:40 실측, vocab 0.7 → 0.6).
  백엔드 재배포 뒤엔 §0 의 어휘집 줄을 꼭 본다. 백엔드와 합의: 배포 전 `git merge origin/dev`, compose·nginx 는 그 브랜치에서만 수정.
- `/live` 를 밖에서 보려면 nginx 에 `location = /live` · `location /live/` → `http://recommend:8300` 한 블록 (백엔드 몫). 없으면
  `ssh -L 8300:127.0.0.1:8300 …` 터널로 발표 노트북에서 `http://127.0.0.1:8300/live`. 단 컨테이너 8300 은 호스트에 안 열려 있으니
  터널 대상은 `docker exec` 로 컨테이너 IP 를 확인해 잡는다(`sudo docker inspect ec2-1-recommend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`).
- 배포 이미지엔 `simulator/` 가 없어 `/live` 의 시작 버튼은 비활성이다. 트래픽은 **EC2 호스트의 dev 워크트리**에서 돌린다:

```bash
# EC2-1 안. dev 워크트리는 redeploy 가 /home/ubuntu/dev-build 에 만들어 둔다. 디스크 292GB 여유, 파이썬 3.12
cd /home/ubuntu/dev-build
python3 -c "import numpy" || pip3 install --user numpy            # 로그 생성기(gen_behavior_logs)만 numpy 를 쓴다. demo_live 는 표준 라이브러리
PYTHONPATH=. python3 simulator/generator/demo_live.py --rate 3000 \
  --recommend http://<recommend 컨테이너 IP>:8300 --bootstrap <EC2-2 IP>:9092
# 캐시(simulator/generator/.cache/demo_behavior_9900.jsonl, 6.9GB)가 없으면 첫 실행이 1분쯤 생성한다
```

- **Kafka 가 없을 때의 보험**: `demo_live.py` 는 `--bootstrap` 포트가 닫혀 있으면 스스로 `--http` 로 물러나 추천 서버
  `POST /api/events` 에 직접 넣는다(`{persona_id, events[]}`). 개인화·`/live` 카운터·상태 사용자 목록은 그대로 움직이지만
  **파티션 칸은 비고 수집기·Spark·마트에는 아무것도 안 들어간다.** "분산"은 이 모드로는 못 보여준다. 시연 3일 전까지 Kafka 가
  안 붙으면 이 모드로 리허설하고, 발표에서는 분산 부분을 로컬 실측(§4)으로 대신한다.

## 3. 데이터

- 9,900명 로그 캐시 `simulator/generator/.cache/demo_behavior_9900.jsonl` — 1,030만 건 · 6.9GB · gitignore. 없으면 첫 시작에
  `gen_behavior_logs.py --limit 9900` 으로 1분 생성.
- 상태에 영향 없는 이벤트(dwell 류 약 30%)는 소비자가 걸러 `filtered` 로 세고, 화면 카운터엔 반영분만 잡힌다.
- 시연 전 `SESSION_EVENTS_PATH` 파일을 비우면 "상태가 바뀐 사용자" 가 0 에서 시작한다. 배포본은 볼륨 `/data/session_events.jsonl`.
- 원천 200개는 카탈로그 동기화·재등록으로 바뀌지 않는다(308, `seed_kept`). 등록 상품은 SB 8개만이고 가격은 원화 그대로 구간에
  들어간다(302, 경계 26,000 / 46,000 / 66,000 / 105,000).

## 4. 실측 (2026-09-14, 노트북)

| 투입 | 소비 lag | 파티션 분포 | 추천 p50 |
|---|---|---|---|
| 3,000건/초 | ≤ 3 | P0·P1·P2 각 33% ± 1 | 1.2ms |
| 5,000건/초 | 두 자리 | 균등 | 유지 |

배포 서버 실측은 Kafka 가 붙은 뒤 같은 표로 한 번 더 채운다.

## 5. 개인화 시나리오 (프론트 화면) — 사람이 하는 3~4분

09-14 로컬 전 구간(프론트 → 수집기 8080 → Kafka → 추천 8300, 백엔드 8090) 헤드리스 확인 결과가 기준이다. 배포본에서는 §0 의
`kafka_state.connected=true` 가 전제다.

1. **새 회원 가입, 피부 프로필 입력** → 첫 화면은 콜드스타트 추천 + 프로필 세그먼트 히어로.
   - 프론트의 회원 귀속 수정(`fe-member-recommend-identity`)이 09-15 17:16 dev 에 머지돼 로그인 회원은 회원 id 로 추천을 받는다.
     피부 타입은 그래도 입력한다 — 콜드스타트 추천과 세그먼트 히어로가 그 값으로 나온다.
2. **히어로 `SB000001 제로 포어 토닝 패드` 클릭 → 좋아요 → 목록 복귀.**
   - 결과(09-14): 1·2위가 `딥 비타C 캡슐 세럼`·`콜라겐 젤리 크림`, 히어로는 `딥 비타C 세럼` 으로 바뀜 (SB 3개 top10). 새로고침 뒤에도 같음.
   - 더 극적: 상세에서 `PDRN 콜라겐 젤리 겔 마스크` 좋아요 → SB 6개 top10.
   - 좋아요한 상품 자체는 "이미 반응한 상품 제외" 정책으로 목록에서 빠진다 → 멘트는 **"이 브랜드의 다른 상품이 올라온다"**.
   - 상세만 보고 좋아요를 안 하면 변화 0. 미리 다른 좋아요를 누르면 상승폭이 줄어든다.
3. **가격대 상품만 몇 개 훑기(퀵룩·상세) → 히어로 배너가 가격 문구로.** 프론트 세션 성향이 `axes=price_bin,…` 을 보내고
   서버 `hero_for` 가 그 순서를 먼저 본다(304). 시드에 가격 트레잇이 아직 없으면 히어로 상품 자신의 가격대를 쓰고
   `trait_source=coldstart` 로 적는다(307) — 그래서 **이 단계는 항상 가격 문구가 나온다.** 응답 `hero.hero_policy_version=hero-2026-09-15`.
4. **담기 → 주문 → 결제 → 추천 갱신 확인 (Jira 320, 백엔드 결제 구현 뒤).** 로그인한 회원으로 SB 상품 하나를 담고 주문한다.
   - 결제 경로는 둘. **배포 프론트에는 09-16 12:19 부터 포트원 공개 키가 들어가 있어 사람 시연은 카카오페이 테스트 창**
     → 백엔드 `/api/orders/{id}/confirm`(백엔드 배포 브랜치에만 있음, dev 머지 확인 필요). 키가 없는 프론트(로컬)는
     `/api/orders/{id}/pay` 로 PAID 표시(테스트 주문). 어느 쪽이든 `purchase` 이벤트 모양은 같고 `payment_method` 만 다르다.
   - **에이전트(PA) 결제는 배포본에서 결제창을 넘지 못한다** — 카카오 로그인·QR 승인은 자동화 불가. 프론트에 `?pay=test`
     런타임 스위치를 요청했다(09-16, Downloads 요청서). 그 전까지 에이전트 `--checkout` 은 로컬 스택에서만. 배포본 에이전트 실행은 결제 없이.
   - 에이전트 재구매: 재생 로그를 `--include-agents` 로 만들어 PA 100명의 과거 구매·재구매 쌍을 마트에 깔고(Jira 328), 시연 전 에이전트를
     `--checkout` 으로 2회 돌리면 라이브 재구매가 잡힌다. 두 번째 실행은 첫 실행과 며칠 간격.
   - **로그인 없이 결제하면 화면에서 멈춘다** (서버 거절을 로컬 주문으로 덮지 않음, 백엔드 요청 09-15). 시나리오는 반드시 로그인 뒤.
   - 결제 뒤 목록: 산 상품은 "이미 반응한 상품 제외" 로 빠지고, `purchase` 8.0(담기 3.0 의 2.7배)이 그 상품 방향으로 벡터를 당겨
     같은 브랜드·유사 상품이 올라온다. 320 이전 이미지에서는 결제가 주문 단위(items[])라 추천에 **0 반영**이었다 — §0 에서 컨테이너가 320 이후인지 확인.
   - 결제 실패 연출은 하지 않는다 — `payment_failed` 가 수집기에 등록돼 있지 않아 프론트 스위치가 꺼져 있다.
   - 재구매율은 추천 화면이 아니라 대시보드 지표다(마트 `brand_repurchase_daily`, 일 배치). 라이브 결제 1건은 그날 배치 뒤에야 들어간다.
5. **판매자로 전환 → 대시보드.** 방금 행동은 마트가 돌아야 지표에 들어간다(일 배치). 라이브 시연에서 대시보드는
   미리 채운 마트/스냅샷으로 보여주는 것이 기본(09-15 회의 안건). AI 처방 문장은 `GMS_KEY` 가 있어야 LLM 문장, 없으면 규칙표 문장.
- `long_term_trait`(지난 방문 성향)는 dw `user_trait_daily` 가 붙기 전까지 응답에 `null` 이다 — 새 세션은 콜드스타트로 시작하는 게 지금은 정상.
- 백엔드 프록시는 `hero`·`axes`·가입 속성 4개를 전부 통과시킨다(09-14 머지) — 09-14 판의 "hero 통과 요청" 은 끝났다.

## 6. 함정

- **백엔드 재배포가 추천을 되돌린다** — `ec2-1-deploy` 브랜치가 dev 보다 뒤면 그 코드로 이미지가 다시 빌드된다(09-16 12:21 재발: 배포 브랜치 push →
  Jenkins 가 `/home/ubuntu/S15P21A306/deploy-workspace` 에서 전 서비스 `up -d --build`, 추천이 09-15 이미지로). **판별법:**
  `sudo docker inspect ec2-1-recommend-1 --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'` 가 `deploy-workspace` 면
  백엔드 것, `dev-build` 면 우리 것. 복구는 `bash deploy/ec2-1/redeploy-local.sh` 한 줄. 근본 해결은 백엔드가 배포 브랜치에 dev 를 머지하는 것.
- **EC2-1 MySQL 컨테이너 이름은 `ec2-1-mysql-1`** — compose 가 가정한 `shop-backend-mysql` 이 아니다. dw 읽기(§0 `user_trait.source`) 전에
  `docker network connect shop-backend-db ec2-1-mysql-1` + `.env` 의 `DW_MYSQL_HOST` 조정, 또는 MySQL 재기동으로 이름을 맞춰야 한다.
- **추천 서버 health 는 nginx 밖으로 안 나온다** — `/recommend/health` 는 SPA 가 받는다. 확인은 컨테이너 안 `python -c "urllib.request…"` (curl 없음).
- **BuildKit 캐시** — 파일이 바뀌었는데도 전 레이어를 캐시로 재사용해 옛 이미지를 낸 적이 있다(09-15 11:00). 스크립트는 `--no-cache` 이고
  성공 판정은 vocab 이 아니라 `image latest==running OK` 다.
- **볼륨은 이미지 갱신으로 안 바뀐다** — `/data/registered_products.jsonl` 에 옛 값·오염 행이 남는다. `reset-registered-local.sh`.
- `Found orphan containers` 경고는 정상(백엔드 compose 의 shop-backend·mysql). `--remove-orphans` 금지.
- `.env` 의 `KAFKA_BOOTSTRAP_SERVERS` 가 EC2-1 자기 주소(`j15a306.p.ssafy.io:9092`)면 틀린 것 — 브로커는 EC2-2.
- 다른 브랜치를 체크아웃한 상태로 로컬 서버를 재기동하면 `/live` 가 없는 옛 코드가 뜬다 (404).
- Windows 는 `localhost` 가 IPv6 폴백으로 2초 — 주소는 전부 `127.0.0.1`.
- Kafka 없이도 `--http` 로 돌아가지만 파티션 칸이 비어 "분산" 은 안 보인다(§2-B).

## 7. 발표 구성 권고 (2026-09-15)

| 층 | 무엇 | 왜 |
|---|---|---|
| 배경 | 페르소나 9,900명 스트림을 `/live` + Grafana 로 켜 둔다 (30초) | 규모·실시간 증명. 조작이 없어 실패 위험이 낮다 |
| 전경 | §5 시나리오를 사람이 직접 (3~4분) | 개인화 증명. 청중이 따라온다 |
| 에이전트 100명 | 라이브 아님. 측정 수치 슬라이드("고른 브랜드 = 열린 브랜드 99%", "담기 lift 1.11x") + 20초 녹화 클립 | LLM 이라 느리고 예측이 안 된다. 멈추면 발표가 같이 멈춘다 |
| 마무리 | 대시보드 — 한 브랜드 인사이트 → 피드백 분류 → 여러 브랜드가 있어야 보이는 인사이트 | 통합몰이라 가능한 값으로 끝낸다 |

순서: 배경 켜기 → 전경 → 에이전트 클립·수치 → 대시보드.
