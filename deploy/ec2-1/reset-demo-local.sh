#!/usr/bin/env bash
# 리허설·시연 직전 초기화 ③ — EC2-1 추천 컨테이너 쪽 (Jira 347, 09-16 합의서 "시연_리허설_뒤_마트_초기화").
#
# 무엇을 비우나 (전부 볼륨 /data 안, 이미지·캐시 파일은 건드리지 않는다)
#   a. 실행 중인 demo_live 정지                (POST /live/demo/stop)
#   b. /data/session_events.jsonl 비우기       ("상태가 바뀐 사용자" 카운터가 0 에서 시작, 세션 로그 재생 이력 제거)
#   c. /data/demo_cache/*.pos 삭제              (다음 시작이 캐시 첫 줄부터. 캐시 .jsonl 자체는 남긴다 — 9,900명 7GB)
#   d. /data/demo_live.log 비우기              (상태 줄이 지난 실행 문구를 보이지 않게)
#   e. 추천 컨테이너 재기동                     (메모리 세션 상태 · 소비자 중복 창(최근 20만 event_id) · /live 카운터 초기화)
#
# 언제: 민우님 ① dw 마트 TRUNCATE · ② raw parquet/checkpoint 초기화와 **같은 시각**. 이것만 먼저 돌리고 /live 를 누르면
#       raw 에 옛 run 이 남은 채 새 run 이 겹친다. 순서는 ①②③ 뒤 → /live 시작.
#
# 실행 (Windows Git Bash):
#   bash deploy/ec2-1/reset-demo-local.sh            # dry-run: 지울 것과 현재 값만 보여준다. 아무것도 바꾸지 않는다
#   bash deploy/ec2-1/reset-demo-local.sh --apply    # 실제 실행
set -euo pipefail
KEY=${EC2_KEY:-$HOME/Downloads/J15A306T.pem}
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1
{ printf 'APPLY=%s\n' "$APPLY"; cat <<'REMOTE'; } | ssh -i "$KEY" ubuntu@j15a306.p.ssafy.io bash -s
set -euo pipefail
C=ec2-1-recommend-1
mode=$([ "$APPLY" = 1 ] && echo "APPLY" || echo "DRY-RUN (변경 없음, --apply 로 실행)")
echo "== 초기화 ③ [$mode] $(date '+%F %T %Z')"

snapshot() {   # 컨테이너 안 값. python 만 있다(curl 없음)
  sudo docker exec -i "$C" python - <<'PY'
import json, os, glob, urllib.request
def n_lines(p):
    try:
        with open(p, "rb") as f: return sum(1 for _ in f)
    except FileNotFoundError: return "(없음)"
def size(p):
    try: return f"{os.path.getsize(p)/1e6:.1f}MB"
    except FileNotFoundError: return "(없음)"
print(f"  session_events.jsonl : {n_lines('/data/session_events.jsonl')} 줄 · {size('/data/session_events.jsonl')}")
print(f"  demo_live.log        : {size('/data/demo_live.log')}")
for p in sorted(glob.glob("/data/demo_cache/*")):
    print(f"  demo_cache/{os.path.basename(p):<34} {os.path.getsize(p)/1e9:.2f}GB" if not p.endswith(".pos")
          else f"  demo_cache/{os.path.basename(p):<34} pos={open(p).read().strip()}  <- 삭제 대상")
try:
    s = json.load(urllib.request.urlopen("http://127.0.0.1:8300/live/stats", timeout=5))
    d = s.get("demo", {})
    print(f"  /live/stats          : events.total {s['events']['total']:,} · personas_touched {s['personas_touched']:,}"
          f" · sessions_in_memory {s.get('sessions_in_memory', '?')} · demo.running {d.get('running')}")
    h = json.load(urllib.request.urlopen("http://127.0.0.1:8300/health", timeout=5))
    u = h.get("user_trait", {})
    print(f"  /health              : ok {h.get('ok')} · kafka lag {h.get('kafka_state', {}).get('lag')} · user_trait rows {u.get('rows')}")
except Exception as ex:
    print(f"  서버 응답 없음: {ex}")
PY
}

echo "-- before"; snapshot
if [ "$APPLY" != 1 ]; then
  echo "-- dry-run 끝. 실제로 하려면: bash deploy/ec2-1/reset-demo-local.sh --apply"; exit 0
fi

echo "-- a. demo_live 정지"
sudo docker exec -i "$C" python - <<'PY'
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8300/live/demo/stop", data=b"{}", method="POST",
                             headers={"Content-Type": "application/json"})
try:
    r = json.load(urllib.request.urlopen(req, timeout=10)); print("  stop →", {k: r.get(k) for k in ("ok", "running", "exit_code")})
except Exception as ex:
    print("  stop 요청 실패(서버가 안 떠 있으면 정상):", ex)
PY
echo "-- b~d. 파일 비우기"
sudo docker exec "$C" sh -c ': > /data/session_events.jsonl; : > /data/demo_live.log; rm -fv /data/demo_cache/*.pos; ls -la /data/session_events.jsonl /data/demo_live.log'
echo "-- e. 컨테이너 재기동"
sudo docker restart "$C" >/dev/null
for i in $(seq 1 30); do
  sudo docker exec "$C" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8300/health', timeout=2)" 2>/dev/null && break
  sleep 2
done
echo "-- after"; snapshot
echo "== 끝. 이제 민우님 ①② 완료 확인 뒤 /live 시작 버튼."
REMOTE
