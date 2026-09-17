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
| `user_trait.source` / `rows` / `rows_by_actor_type` | `dw_mysql:mysql/dw`(09-16 저녁부터). 첫 적재 전엔 `rows 0`·`{}` 가 정상. 적재 뒤 `rows_by_actor_type.synthetic` 이 잡혀야 페르소나 장기 성향이 산다(346 — 이전엔 `actor_type='user'` 만 읽어 영원히 0) | `rows 0` 이 계속이면 민우님 발행 Job 미실행. `max_age_days` 는 시연용 60(.env, 재생 로그 날짜 08-28), 시연 뒤 14 |
| `/pipeline/stats` `spark.reachable` / `dw.tables` / `dashboard_url` | true · 22 · `https://j15a306.p.ssafy.io/dashboard.html` (09-17 10:36) | Spark 는 EC2-2 18080(!297), dw 는 백엔드 CI 스키마, 대시보드는 .env |
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
- 배포본 `/live` 의 시작 버튼은 **9,900명**을 돌린다(EC2-1 `.env` `DEMO_LIMIT=9900`, 캐시 `/data/demo_cache/demo_behavior_9900_KRW.jsonl` 7GB 를 노트북에서 만들어 올림 — §3). 끝까지 가면 1,050만 건·약 57분,
  중간에 정지하면 `.pos` 에서 이어 간다. 컨테이너 안 생성은 1,000명까지(9,900명은 RSS 12GB 로 OOM, 09-16 실측). 캐시가 없을 때 9,900명을 EC2 에서 만들려면 **EC2 호스트의 dev 워크트리**에서 돌린다:

```bash
# EC2-1 안. dev 워크트리는 redeploy 가 /home/ubuntu/dev-build 에 만들어 둔다. 디스크 292GB 여유, 파이썬 3.12
cd /home/ubuntu/dev-build
python3 -c "import numpy" || pip3 install --user numpy            # 로그 생성기(gen_behavior_logs)만 numpy 를 쓴다. demo_live 는 표준 라이브러리
PYTHONPATH=. python3 simulator/generator/demo_live.py --rate 3000 \
  --recommend http://<recommend 컨테이너 IP>:8300 --bootstrap <EC2-2 IP>:9092
# 캐시(simulator/generator/.cache/demo_behavior_9900_KRW.jsonl, 6.9GB)가 없으면 첫 실행이 1분쯤 생성한다 (호스트 RAM 15.7GB 중 12GB 필요 — 다른 컨테이너 상태를 먼저 본다)
```

- **Kafka 가 없을 때의 보험**: `demo_live.py` 는 `--bootstrap` 포트가 닫혀 있으면 스스로 `--http` 로 물러나 추천 서버
  `POST /api/events` 에 직접 넣는다(`{persona_id, events[]}`). 개인화·`/live` 카운터·상태 사용자 목록은 그대로 움직이지만
  **파티션 칸은 비고 수집기·Spark·마트에는 아무것도 안 들어간다.** "분산"은 이 모드로는 못 보여준다. 시연 3일 전까지 Kafka 가
  안 붙으면 이 모드로 리허설하고, 발표에서는 분산 부분을 로컬 실측(§4)으로 대신한다.

## 2-1. 파이프라인 화면 `/pipeline` (Jira 337, 09-16)

`/live` 가 "추천 상태에 반영됐다" 는 마지막 층을 깊게 보는 화면이라면, `/pipeline` 은 다섯 층을 얕게 이어 본다 —
**① 사이트 활동(페르소나 PC / 에이전트 PA / 실사용자) → ② Kafka 파티션(브로커 끝 오프셋·소비 위치·lag) → ③ Spark(워커·실행 앱) → ④ dw 마트 7개(행 수·갱신) → ⑤ 대시보드(상태 반영·링크)**.
리허설(09-17)에서 로그가 어디까지 흘렀는지 짚는 용도. 다른 파트 자원은 전부 읽기만 한다. 접근은 `/live` 와 같다(컨테이너 8300, 터널).

| 칸 | 출처 | 지금(09-16) | 켜려면 |
| --- | --- | --- | --- |
| ① 활동 | Kafka 소비자가 받은 모든 메시지(상태 필터 전) | 됨 | — |
| ② Kafka | 같은 group 의 두 번째 Consumer(구독 안 함)로 워터마크·committed | 됨 | — |
| ③ Spark | `SPARK_MASTER_UI` 의 `/json` | **동작 (09-17 10:33)** — 민우님 !297 로 EC2-2 가 `SPARK_MASTER_UI_BIND_IP` 로 마스터 UI 를 열었고, EC2-1 `.env` `SPARK_MASTER_UI=http://j15a306a.p.ssafy.io:18080`(Kafka 와 같은 공개 호스트명 — 사설 IP 172.26.1.194 는 무응답) · 실측 워커 1 · 코어 2 · ALIVE | `/json` 은 `/json/` 로 302 하지만 urllib 이 따라간다. 컨테이너 재생성만(재빌드 없음) |
| ④ dw | `DW_MYSQL_*`(user_trait 와 같은 값), information_schema + 마트 COUNT(*) | **연결 (09-17)** — 스키마 22 테이블 인식, 행 0(첫 적재 전). 마트 목록은 `DW_PROJECTION_MARTS`(기본 7) | 민우님 발행 Job → 행 수. projection 이 22개면 EC2-1 .env 에도 같은 목록 |
| ⑤ 대시보드 | `DASHBOARD_URL` 링크 | **링크 (09-17)** — `https://j15a306.p.ssafy.io/dashboard.html`(프론트 별도 엔트리, SELLER 로그인) | 백엔드 마트 API 7개(!296, ec2-1-deploy) 배포 뒤 숫자 붙이기(AI 후속) |

버튼 둘. **▶ 페르소나 시작**은 `/live` 와 같은 `POST /live/demo/start`(9,900명·KRW·이어 보내기). 상태 줄 한글은 09-17(344)부터 안 깨진다. **▶ 에이전트 100명**은 발표 노트북의 런처
`python simulator/agents/agent_launcher.py`(127.0.0.1:8301, GMS_KEY 있는 셸에서)로 가서 `agent_runner --url <배포 사이트> --limit 100 --checkout --workers 5 --simulation-run-id demo-<날짜>` 를 띄운다.
런처를 켜는 것이 곧 GMS 허락이다(1명 약 9 크레딧, 100명 약 900). 런처 주소는 화면 오른쪽 위 칸(브라우저에 기억).
에이전트 로그는 진짜 브라우저 → 프론트 로거 → 수집기 → Kafka 로 페르소나와 같은 길을 가서 ① 의 PA 줄에 잡힌다.

## 3. 데이터

- 로그 캐시 `<DEMO_CACHE_DIR>/demo_behavior_<limit>_<currency>.jsonl` (로컬 기본 `simulator/generator/.cache/`, gitignore). 9,900명 = 1,030만 건 · 6.9GB · 1분 · RSS 12GB,
  1,000명 = 71만 건 · 714MB · 21초 · RSS 1.2GB (09-16 실측). 없으면 첫 시작에 `gen_behavior_logs.py --limit <limit> --currency <currency>` 으로 생성(컨테이너 안은 1,000명까지). 배포본은 9,900명 캐시를 올려 두며, 볼륨 `/data/demo_cache` 라 재배포에도 남는다.
- **통화는 KRW**(env `DEMO_CURRENCY`, 09-17 Jira 341). 사이트가 원화(302)이고 계약이 purchase·view_cart 의 currency 를 KRW 로 고정(303)해서, 달러 로그가 섞이면
  Q5 `purchase_fact_currency_is_unambiguous` 가 깨진다. 09-16 까지의 캐시 `demo_behavior_1000.jsonl`·`demo_behavior_9900.jsonl` 은 USD 라 이름이 달라 자동으로 안 쓰인다 — 볼륨에서 지운다(7.7GB).
- **배포본을 9,900명으로**: 컨테이너 안 생성은 OOM 이라 노트북에서 만든다 — `gen_behavior_logs.py --limit 9900 --currency KRW --out <grouped>` → `shuffle_sessions.py <grouped> <shuffled>`(페르소나별로 뭉친 파일을 세션 단위로 섞어 2분 안에 전원이 나타나게; 세션 안 순서는 그대로) → gzip → scp → 볼륨 `/data/demo_cache/demo_behavior_9900_KRW.jsonl` 에 gunzip → EC2 `.env` `DEMO_LIMIT=9900` → 컨테이너 재생성. 1,030만 건이라 초당 8,000 이면 21분, 3,000 이면 57분. 버튼 글자는 서버의 DEMO_LIMIT 을 읽어 바뀐다.
- 상태에 영향 없는 이벤트(dwell 류 약 30%)는 소비자가 걸러 `filtered` 로 세고, 화면 카운터엔 반영분만 잡힌다.
- 시연 전 `SESSION_EVENTS_PATH` 파일을 비우면 "상태가 바뀐 사용자" 가 0 에서 시작한다. 배포본은 볼륨 `/data/session_events.jsonl`.
- **리허설·시연 직전 초기화 ③ (09-17 Jira 347)**: `bash deploy/ec2-1/reset-demo-local.sh` 가 dry-run 으로 현재 값(session_events 줄 수, .pos, /live 카운터)을 보여주고,
  `--apply` 면 demo_live 정지 → `/data/session_events.jsonl`·`/data/demo_live.log` 비우기 → `/data/demo_cache/*.pos` 삭제 → 컨테이너 재기동(메모리 세션·중복 창·카운터 0) 순으로 돈다.
  캐시 .jsonl 은 남긴다. **민우님 ① dw 마트 ② raw 초기화와 같은 시각에** 돌리고, ①②③ 뒤에 /live 시작 버튼을 누른다(합의서 `시연_리허설_뒤_마트_초기화_합의요청_0916`).
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
     → 백엔드 `/api/orders/{id}/confirm`(2026-09-17 dev 병합 반영). 키가 없는 프론트(로컬)는
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
- **배포본 /live 시작 버튼이 404 `DEMO_UNAVAILABLE`** — 이미지에 `simulator/generator/demo_live.py` 가 없었다(09-16 발견, Jira 335 로 Dockerfile COPY + `recommend.Dockerfile.dockerignore` 예외 — 둘 다 있어야 빌드된다).
- **dw 접속이 `'cryptography' package is required for ... caching_sha2_password`** — MySQL 8 기본 인증에 pymysql 이 cryptography 를 요구한다(09-16, 백엔드 CI 가 dw·계정·.env 를 채운 직후 발견). 서버 requirements 에 추가(Jira 339). 확인은 `/health.user_trait.source = dw_mysql:…`, `/pipeline` dw 칸 schema_exists.
- **배포본 /live 시작이 `로그 생성 실패`** — 컨테이너 `mem_limit: 1g` 에서 9,900명 생성이 OOM(`OOMKilled=true`, 트레이스백 없이 죽는다). 335 후속으로 `mem_limit: 3g`·캐시 볼륨, 09-17 부터 9,900명 캐시는 노트북에서 만들어 올린다(§3). 캐시 파일이 없거나 이름이 `demo_behavior_<limit>_<currency>.jsonl` 과 다르면 컨테이너가 생성을 시도해 이 실패가 난다. 진단은 `/data/demo_live.log` 와 `docker inspect --format '{{.State.OOMKilled}}'`.
- **상태 줄이 `蹂닿린: …` 처럼 깨진다** — 로그 꼬리 400바이트가 한글 3바이트 중간에서 잘려 cp949 폴백으로 풀리던 것(09-17, Jira 344 로 `log_tail()` 수정). 옛 이미지면 재배포.
- **첫 적재 뒤에도 `user_trait.rows` 가 0** — (가) 옛 서버는 `actor_type='user'` 만 읽었고 페르소나 행은 synthetic 이다(346 으로 해결, `rows_by_actor_type` 확인). (나) `age_days > max_age_days` 면 값이 있어도 응답은 null — 재생 로그 날짜가 08-28 이라 EC2-1 은 60 으로 올려 둠(.env `USER_TRAIT_MAX_AGE_DAYS`). `expired=false` 인지 본다.
- **Kafka 보존 24시간·Q1 은 스트리밍** — EC2-2 토픽 보존 `KAFKA_TOPIC_RETENTION_MS=86400000`. Q1 raw sink(Structured Streaming)가 꺼져 있으면 그 사이 들어온 이벤트는 24시간 뒤 raw 에 못 간다. 버튼 전에 Spark 마스터 `/json/` 의 `activeapps` 에 raw sink 가 있는지 본다(09-17 요청: Q1 상시 가동·보존 7일).
- **시작 버튼은 배포 Kafka 로 진짜 이벤트를 보낸다** — EC2-2 `activity-events` → Spark raw sink → 마트까지 흐른다(generator_type=python_batch, 새 run_id). 데이터·인프라 파트와 시점을 맞추고 누른다.
- **정지 뒤 다시 시작하면 화면이 안 움직인다** — 같은 캐시를 처음부터 다시 보내면 event_id 가 같아 소비자(`Dedupe` 최근 20만 건)가 전부 버린다(09-16 duplicates 74,068 실측). 335 후속으로 demo_live 가 `<캐시>.pos` 에 보낸 줄 수를 10초마다 적고 다음 시작은 거기서 이어 간다. 끝까지 가면 0. 처음부터 다시 보내려면 `POST /live/demo/start {"restart": true}` 또는 `--restart` — 이때는 컨테이너를 재기동해 중복 창을 비우는 게 맞다.
- **배포본 /live 는 nginx 밖으로 안 열려 있다** — 추천 8300 은 컨테이너 안에서만. 보려면 `ssh -N -i ~/Downloads/J15A306T.pem -L 8300:<추천 컨테이너 IP>:8300 ubuntu@j15a306.p.ssafy.io` 뒤 `http://localhost:8300/live`. 컨테이너 IP 는 `sudo docker inspect ec2-1-recommend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`. 고정 주소는 백엔드 nginx `location /live` 요청.
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
