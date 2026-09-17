# -*- coding: utf-8 -*-
"""
시연용 한 방 스크립트 — PC 페르소나 9,900명의 행동 로그를 Kafka 로 쏟아 넣고 추천 서버 `/live` 에서 본다 (Jira 295)
================================================================================

    python simulator/generator/demo_live.py                 # 9,900명 · 3,000건/초 · Kafka(127.0.0.1:9092)
    python simulator/generator/demo_live.py --rate 5000     # 더 세게
    python simulator/generator/demo_live.py --http          # Kafka 없이 추천 서버 POST /api/events 로 직접 (파티션 칸은 비어 있다)
    python simulator/generator/demo_live.py --max-events 1000000   # 100만 건만

무엇을 하는가
    1. 추천 서버(`--recommend`, 기본 http://127.0.0.1:8300)가 떠 있는지 `/health` 로 확인한다.
    2. Kafka(`--bootstrap`, 기본 127.0.0.1:9092)에 붙을 수 있는지 본다. 못 붙으면 `--http` 로 물러난다(경고 출력).
    3. 로그가 캐시(`<DEMO_CACHE_DIR>/demo_behavior_<limit>_<currency>.jsonl`, 기본 `simulator/generator/.cache/`)에 없으면
       `gen_behavior_logs.py --limit <limit> --currency <currency>` 으로 만든다 (9,900명: 약 1,030만 건 · 6.9GB · 1분 · RSS 12GB).
       있으면 그대로 쓴다. 통화는 env `DEMO_CURRENCY`(기본 KRW) — 사이트가 원화(Jira 302)이고 계약이 purchase·view_cart 의
       currency 를 KRW 로 고정(Jira 303)해서, 달러 로그를 섞으면 Q5 `purchase_fact_currency_is_unambiguous` 가 깨진다(Jira 341).
       파일명에 통화가 들어가서 옛 `demo_behavior_<limit>.jsonl`(USD) 캐시는 다시 쓰지 않는다.
       컨테이너 안 생성은 1,000명(71만 건 · 714MB · 20초 · RSS 1.2GB)까지 — 9,900명(RSS 12GB)은 OOM. 배포본은 DEMO_LIMIT=9900 이고
       캐시를 노트북에서 만들어 볼륨 /data/demo_cache 에 올려 둔다(런북 §3, 09-17).
    4. 로그를 **key = session_id** 로 Kafka `activity-events` 에 초당 `--rate` 건씩 넣는다 — 수집기(backend/)와 같은 규칙이라
       파티션 3개로 갈라지고, 추천 서버 소비자가 읽어 상태에 반영한다. 그 사이 `/api/recommend` 도 초당 2~3번 불러
       응답 시간 칸을 살린다.
    5. 10초마다 진행을 찍고, 끝나면 `/live/stats` 요약을 출력한다.

무엇을 보는가
    브라우저에서 `<추천 서버>/live`. 초당 반영 이벤트 · Kafka 파티션 3개별 소비 · 상태 바뀐 사용자(→ 9,900) · 추천 p50/p95.

주의
    - 추천 서버는 `KAFKA_BOOTSTRAP_SERVERS` 를 주고 띄워야 Kafka 를 읽는다. 로컬은 `start-local.bat`(Kafka 4.2.1) 뒤
      `KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9092 python -m uvicorn batch.serving.recommend_server:app --port 8300`.
    - 시연 중 추천 서버 세션 로그(`SESSION_EVENTS_PATH`)가 커진다. 시연 전용 경로를 주는 것이 깔끔하다.
    - Windows 는 `localhost` 가 IPv6 폴백으로 2초 걸린다 — 주소는 전부 `127.0.0.1`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# 페르소나 수·캐시 위치는 환경변수로도 준다 (Jira 335). 생성기는 페르소나 1명당 RSS 약 1.2MB · 파일 0.7MB 를 쓰므로
# 9,900명은 RSS 약 12GB · 6.9GB 파일 — 노트북에선 되지만 배포 컨테이너(mem_limit)에서는 OOM 으로 죽는다(09-16 실측).
# 배포 compose 기본값은 DEMO_LIMIT=1000 이지만 EC2-1 .env 는 9900(노트북 생성 캐시 업로드, 09-17). DEMO_CACHE_DIR=/data/demo_cache(볼륨, 재배포에도 남는다).
DEFAULT_LIMIT = int(os.environ.get("DEMO_LIMIT", "9900"))
CACHE_DIR = os.environ.get("DEMO_CACHE_DIR") or os.path.join(HERE, ".cache")
# 생성기 통화(Jira 341). 생성기 기본은 USD(평가용 로그 호환, Jira 334)지만 시연 로그는 사이트·계약과 같은 KRW 여야 한다.
CURRENCIES = ("USD", "KRW")
DEFAULT_CURRENCY = os.environ.get("DEMO_CURRENCY", "KRW").upper()


def cache_path(limit, currency=DEFAULT_CURRENCY):
    return os.path.join(CACHE_DIR, f"demo_behavior_{limit}_{currency}.jsonl")


def pos_path(log_path):
    return log_path + ".pos"


def load_pos(log_path):
    """지난 실행이 보낸 줄 수. 정지 뒤 다시 시작하면 여기서 이어 간다 (Jira 335).

    같은 파일을 처음부터 다시 보내면 event_id 가 같아 소비자(kafka_state.Dedupe, 최근 20만 건)가 전부 중복으로 버리고
    화면은 안 움직인다 — 09-16 배포본에서 정지·재시작 뒤 duplicates 74,068 로 실측. 파일 끝까지 가면 0 으로 돌아간다."""
    try:
        with open(pos_path(log_path), encoding="utf-8") as f:
            return max(0, int(f.read().strip() or 0))
    except Exception:
        return 0


def save_pos(log_path, n):
    try:
        with open(pos_path(log_path), "w", encoding="utf-8") as f:
            f.write(str(n))
    except Exception:
        pass


def skip_lines(f, n):
    for _ in range(n):
        if not f.readline():
            return False
    return True


def http_json(url, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def port_open(hostport, timeout=2.0):
    host, port = hostport.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def generator_cmd(limit, path, currency=DEFAULT_CURRENCY):
    if currency not in CURRENCIES:
        raise SystemExit(f"DEMO_CURRENCY 는 {'/'.join(CURRENCIES)} 중 하나: {currency!r}")
    return [sys.executable, os.path.join(HERE, "gen_behavior_logs.py"),
            "--limit", str(limit), "--currency", currency, "--out", path]


def ensure_log(limit, path, currency=DEFAULT_CURRENCY):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[demo] 로그 캐시 사용: {path} ({os.path.getsize(path)/1e9:.1f}GB)")
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"[demo] 로그 생성 중: {limit:,}명 · {currency} → {path}  (1,000명 약 20초 · 9,900명 약 1분, RSS 약 {limit*1.2/1000:.1f}GB)", flush=True)
    cmd = generator_cmd(limit, path, currency)
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0 or not os.path.exists(path):
        oom = r.returncode in (-9, 137)          # 컨테이너 mem_limit 에 걸려 죽은 것
        hint = " — 메모리 부족: DEMO_LIMIT 을 줄이거나 mem_limit 을 올리십시오" if oom else ""
        raise SystemExit(f"로그 생성 실패 (exit {r.returncode}){hint}")
    return path


class Ticker(threading.Thread):
    """시연 동안 /api/recommend 를 초당 2~3번 — /live 의 응답 시간 칸을 살린다"""
    def __init__(self, base, limit):
        super().__init__(daemon=True)
        self.base, self.limit, self.stop = base, limit, threading.Event()

    def run(self):
        while not self.stop.is_set():
            pid = f"PC{random.randint(1, self.limit):05d}"
            try:
                http_json(f"{self.base}/api/recommend?persona_id={pid}&size=10&hero=new_brand&banner_slots=1")
            except Exception:
                pass
            self.stop.wait(0.4)


# 수집 API 한 요청에 담기는 이벤트 수. request_id 와 event_index 가 이 단위로 묶인다.
ENVELOPE_BATCH = 20


def now_iso_ms():
    """수집기 receivedAt 과 같은 모양 — 밀리초 3자리 + Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def put_envelope(event, received_at, request_id, event_index):
    """수집기가 채우는 봉투 다섯 필드를 여기서 채운다 (Jira 없음 — 09-17 규명).

    되감기는 수집 API(`POST /api/events`)를 건너뛰고 Kafka 에 직접 넣는다. 그런데 계약의 필수 19개 중
    `received_at`·`source`·`request_id`·`event_index`·`account_id` 다섯은 **생성기가 아니라 수집기가 채우는**
    봉투다(`backend/.../KafkaEventMessage.from`). 그대로 넣으면 정제가 `missing_required_field` 로 전부 버린다 —
    09-17 실측에서 원천 256,554건 중 253,596건(98.8%)이 이것 하나로 탈락했고 전부 `source=simulator` 였다.
    그래서 마트가 실사용자 트래픽만으로 만들어졌다.

    `source` 규칙은 수집기와 같다 — `actor_type=='synthetic'` 이면 `simulator`, 아니면 `web`.
    `account_id` 는 수집기도 비로그인이면 null 로 넣는다. **키가 없는 것과 null 은 다르다** — 없으면 탈락한다.
    """
    event["received_at"] = received_at
    event["source"] = "simulator" if event.get("actor_type") == "synthetic" else "web"
    event["request_id"] = request_id
    event["event_index"] = event_index
    if "account_id" not in event:
        event["account_id"] = None
    return event


def stream_kafka(path, bootstrap, topic, rate, max_events, skip=0):
    from confluent_kafka import Producer
    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": 20, "batch.num.messages": 2000,
                  "queue.buffering.max.messages": 500000, "compression.type": "lz4"})
    failed = [0]

    def on_delivery(err, _msg):
        if err is not None:
            failed[0] += 1
    t0 = time.time(); n = 0; last = t0; done = False
    with open(path, encoding="utf-8") as f:
        skip_lines(f, skip)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            key = event.get("session_id") or ""
            # 수집 API 를 건너뛰므로 봉투를 여기서 채운다 — 안 채우면 정제가 전부 버린다
            if n % ENVELOPE_BATCH == 0:
                request_id = str(uuid.uuid4())
                received_at = now_iso_ms()
            payload = json.dumps(
                put_envelope(event, received_at, request_id, n % ENVELOPE_BATCH),
                ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            while True:
                try:
                    p.produce(topic, value=payload, key=key.encode("utf-8"), on_delivery=on_delivery)
                    break
                except BufferError:
                    p.poll(0.05)
            n += 1
            if n % 500 == 0:
                p.poll(0)
            target = t0 + n / rate
            now = time.time()
            if now < target:
                time.sleep(min(0.05, target - now))
            if now - last >= 10:
                last = now
                save_pos(path, skip + n)
                print(f"[demo] Kafka 로 {n:,}건 (파일 위치 {skip + n:,}) · 실패 {failed[0]} · {n/(now-t0):,.0f}건/초", flush=True)
            if max_events and n >= max_events:
                break
        else:
            done = True
    p.flush(60)
    save_pos(path, 0 if done else skip + n)
    return n, failed[0]


def stream_http(path, base, rate, max_events, batch=50, skip=0):
    """Kafka 없이 추천 서버에 직접. 이벤트 모양은 /api/events 의 {persona_id, events[]}"""
    import queue
    q = queue.Queue(maxsize=200); ok = [0]; fail = [0]; lock = threading.Lock()

    def worker():
        while True:
            item = q.get()
            if item is None:
                return
            pid, evs = item
            try:
                http_json(f"{base}/api/events", {"persona_id": pid, "events": evs})
                with lock:
                    ok[0] += len(evs)
            except Exception:
                with lock:
                    fail[0] += len(evs)
    ths = [threading.Thread(target=worker, daemon=True) for _ in range(6)]
    for t in ths:
        t.start()
    t0 = time.time(); n = 0; last = t0; cur = None; buf = []; done = False
    with open(path, encoding="utf-8") as f:
        skip_lines(f, skip)
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            pid = d.get("persona_id")
            if pid != cur or len(buf) >= batch:
                if buf:
                    q.put((cur, buf))
                buf, cur = [], pid
            buf.append({"event_name": d.get("event_name"), "product_id": d.get("product_id"),
                        "properties": d.get("properties") or {}})
            n += 1
            target = t0 + n / rate
            now = time.time()
            if now < target:
                time.sleep(min(0.05, target - now))
            if now - last >= 10:
                last = now
                save_pos(path, skip + n)
                print(f"[demo] HTTP 로 {n:,}건 읽음 (파일 위치 {skip + n:,}) · 반영 {ok[0]:,} · 실패 {fail[0]:,} · {n/(now-t0):,.0f}건/초", flush=True)
            if max_events and n >= max_events:
                break
        else:
            done = True
    save_pos(path, 0 if done else skip + n)
    if buf:
        q.put((cur, buf))
    for _ in ths:
        q.put(None)
    for t in ths:
        t.join()
    return n, fail[0]


def main():
    ap = argparse.ArgumentParser(description="9,900명 로그를 쏟아 넣고 /live 로 본다")
    ap.add_argument("--recommend", default="http://127.0.0.1:8300")
    ap.add_argument("--bootstrap", default="127.0.0.1:9092")
    ap.add_argument("--topic", default="activity-events")
    ap.add_argument("--rate", type=int, default=3000, help="초당 이벤트 수 (기본 3,000)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"페르소나 수 (기본 {DEFAULT_LIMIT:,} = env DEMO_LIMIT)")
    ap.add_argument("--max-events", type=int, default=0, help="이만큼만 보내고 멈춘다 (0 = 전부, 9,900명은 약 1,030만 건)")
    ap.add_argument("--currency", choices=CURRENCIES, default=DEFAULT_CURRENCY,
                    help=f"생성 로그 통화 (기본 {DEFAULT_CURRENCY} = env DEMO_CURRENCY). 사이트·계약이 KRW 라 시연은 KRW (Jira 341)")
    ap.add_argument("--log", default=None, help="행동 로그 경로 (기본 <DEMO_CACHE_DIR>/demo_behavior_<limit>_<currency>.jsonl, 없으면 생성)")
    ap.add_argument("--http", action="store_true", help="Kafka 대신 추천 서버 POST /api/events 로 직접")
    ap.add_argument("--no-ticker", action="store_true", help="/api/recommend 를 같이 부르지 않는다")
    ap.add_argument("--restart", action="store_true",
                    help="지난 실행이 멈춘 자리(<log>.pos)를 무시하고 처음부터. 기본은 이어서 보낸다 — 처음부터 다시 보내면 "
                         "소비자가 event_id 중복으로 다 버린다")
    a = ap.parse_args()

    try:
        h = http_json(f"{a.recommend}/health")
    except Exception as ex:
        raise SystemExit(f"추천 서버가 응답하지 않는다: {a.recommend} ({ex}). 먼저 띄우십시오")
    kafka_state = h.get("kafka_state") or {}
    use_kafka = not a.http
    if use_kafka and not port_open(a.bootstrap):
        print(f"[demo] Kafka {a.bootstrap} 에 붙을 수 없다 → HTTP 직접 전송으로 물러난다 (파티션 칸은 비어 있다)")
        use_kafka = False
    if use_kafka and not kafka_state:
        print("[demo] 경고: 추천 서버가 KAFKA_BOOTSTRAP_SERVERS 없이 떠 있다 — Kafka 에 넣어도 서버가 읽지 않는다. "
              "서버를 KAFKA_BOOTSTRAP_SERVERS 로 다시 띄우거나 --http 를 쓰십시오")
    path = ensure_log(a.limit, a.log or cache_path(a.limit, a.currency), a.currency)
    skip = 0 if a.restart else load_pos(path)
    if skip:
        print(f"[demo] 지난 실행이 멈춘 {skip:,}번째 줄부터 이어 보낸다 (처음부터는 --restart)", flush=True)
    print(f"[demo] 보기: {a.recommend}/live   (경로: {'Kafka ' + a.bootstrap + ' → 파티션 3 → 소비자' if use_kafka else 'HTTP 직접'} · {a.rate:,}건/초)")

    ticker = None
    if not a.no_ticker:
        ticker = Ticker(a.recommend, a.limit); ticker.start()
    t0 = time.time()
    try:
        if use_kafka:
            n, failed = stream_kafka(path, a.bootstrap, a.topic, a.rate, a.max_events, skip=skip)
        else:
            n, failed = stream_http(path, a.recommend, a.rate, a.max_events, skip=skip)
    except KeyboardInterrupt:
        print("\n[demo] 중단"); n, failed = 0, 0
    finally:
        if ticker:
            ticker.stop.set()
    dt = time.time() - t0
    print(f"[demo] 끝 — {n:,}건 / {dt:,.0f}초 ({(n/dt if dt else 0):,.0f}건/초) · 실패 {failed}")
    try:
        s = http_json(f"{a.recommend}/live/stats")
        k = s.get("kafka") or {}
        print(f"[demo] /live: 반영 누적 {s['events']['total']:,} · 사용자 {s['personas_touched']:,} · "
              f"파티션 {s['partitions']} · 추천 p50 {s['recommend']['p50_ms']}ms p95 {s['recommend']['p95_ms']}ms"
              + (f" · Kafka processed {k.get('processed'):,} filtered {k.get('filtered'):,} lag {k.get('lag')}" if k else ""))
    except Exception:
        pass


if __name__ == "__main__":
    main()
