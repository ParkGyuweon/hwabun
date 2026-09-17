# -*- coding: utf-8 -*-
"""
에이전트 런처 — 발표 노트북에서 켜 두면 `/pipeline` 의 "▶ 에이전트 100명" 버튼이 여기로 와서 agent_runner 를 띄운다 (Jira 337)
================================================================================

    set GMS_KEY=...                                  (또는 .env)  — 없으면 시작을 거절한다
    python simulator/agents/agent_launcher.py                       # 127.0.0.1:8301
    python simulator/agents/agent_launcher.py --site https://j15a306.p.ssafy.io --workers 5

왜 노트북인가
    에이전트는 Playwright 브라우저 + GMS(LLM) 다. 추천 컨테이너에 브라우저 100개를 넣는 것은 메모리상 무리이고,
    GMS 지출을 서버 버튼에 걸어 두는 것도 위험하다. 그래서 **런처를 켜는 행위 자체가 허락**이다 — 켜져 있을 때만 버튼이 산다.
    에이전트는 배포 사이트를 진짜 브라우저로 쓰므로 그 로그는 프론트 로거 → 수집기 → Kafka 로 페르소나와 같은 길을 간다.

엔드포인트 (CORS 허용 — /pipeline 은 다른 origin 이다)
    GET  /status            {running, started_at, args, last_line, exit_code}
    POST /start {limit, checkout, workers, run_id}   agent_runner 를 자식 프로세스로. 이미 돌고 있으면 already=true
    POST /stop
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
RUNNER = os.path.join(HERE, "agent_runner.py")
DEFAULT_SITE = "https://j15a306.p.ssafy.io"

_state = {"proc": None, "started_at": None, "args": None, "log": None}
_cfg = {"site": DEFAULT_SITE, "workers": 5, "turns": 25, "post": None}


def _load_dotenv():
    """레포 루트 .env 의 GMS_KEY 만 (없으면 그대로). 값은 어디에도 찍지 않는다"""
    if os.environ.get("GMS_KEY"):
        return
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line.startswith("GMS_KEY=") and len(line) > 8:
            os.environ["GMS_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return


def status():
    p = _state["proc"]
    running = p is not None and p.poll() is None
    tail = ""
    try:
        if _state["log"] and os.path.exists(_state["log"]):
            with open(_state["log"], "rb") as f:
                f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 600))
                lines = f.read().decode("utf-8", "replace").strip().splitlines()
                tail = lines[-1] if lines else ""
    except Exception:
        tail = ""
    return {"running": running, "started_at": _state["started_at"], "args": _state["args"],
            "exit_code": (None if running or p is None else p.returncode), "last_line": tail,
            "key_present": bool(os.environ.get("GMS_KEY"))}


def start(body):
    if status()["running"]:
        return {"ok": True, "already": True, **status()}
    if not os.environ.get("GMS_KEY"):
        return {"ok": False, "error": "GMS_KEY 가 없다 — 런처를 켠 셸에 넣고 다시. 키는 화면·이력에 남기지 않는다"}
    limit = max(1, min(int(body.get("limit") or 100), 100))
    run_id = body.get("run_id") or f"demo-{time.strftime('%Y%m%d')}"          # 재구매는 같은 run_id 로 2회 (마트 grain)
    ts = time.strftime("%Y%m%dT%H%M%S")
    out = os.path.join(HERE, "data", f"launcher_{ts}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    args = [sys.executable, RUNNER, "--url", _cfg["site"], "--limit", str(limit), "--turns", str(_cfg["turns"]),
            "--workers", str(int(body.get("workers") or _cfg["workers"])), "--out", out,
            "--simulation-run-id", run_id, "--quiet"]
    # 수집 API 로도 보낸다 (09-17). 안 보내면 로그가 파일로만 쌓여 /pipeline 의 에이전트 축이
    # 실행 내내 0 이고 마트에도 안 들어간다. 브라우저가 프론트 로거로 보내는 것과는 다르다 —
    # 그쪽은 러너가 채우는 actor_type·실행 메타데이터가 없어 실사용자와 구분되지 않는다.
    post = body.get("post") or _cfg.get("post") or _cfg["site"]
    if post and str(post).lower() not in ("off", "none", "false"):
        args += ["--post", str(post)]
    if body.get("checkout", True):
        args.append("--checkout")
    log = os.path.join(HERE, "data", f"launcher_{ts}.log")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    _state["log"] = log
    _state["proc"] = subprocess.Popen(args, stdout=open(log, "ab"), stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    _state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _state["args"] = [a for a in args[2:]]
    print(f"[launcher] 시작 {limit}명 → {_cfg['site']} run_id={run_id} out={out}", flush=True)
    return {"ok": True, **status()}


def stop():
    p = _state["proc"]
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except Exception:
            p.kill()
    return {"ok": True, **status()}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path.split("?")[0] == "/status":
            return self._send(200, status())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except Exception:
            body = {}
        path = self.path.split("?")[0]
        if path == "/start":
            return self._send(200, start(body))
        if path == "/stop":
            return self._send(200, stop())
        self._send(404, {"error": "not found"})

    def log_message(self, *a):                         # 조용히
        pass


def main():
    ap = argparse.ArgumentParser(description="/pipeline 에이전트 버튼용 로컬 런처")
    ap.add_argument("--port", type=int, default=8301)
    ap.add_argument("--site", default=DEFAULT_SITE, help="에이전트가 쓸 사이트 (기본 배포본)")
    ap.add_argument("--post", default=None,
                    help="수집 API 베이스 URL. 안 주면 --site 와 같은 곳으로 보낸다. off 로 끈다")
    ap.add_argument("--workers", type=int, default=5, help="동시 브라우저 수")
    ap.add_argument("--turns", type=int, default=25)
    a = ap.parse_args()
    _cfg.update(site=a.site, workers=a.workers, turns=a.turns, post=a.post)
    _load_dotenv()
    print(f"[launcher] http://127.0.0.1:{a.port}  site={a.site} workers={a.workers} "
          f"GMS_KEY={'있음' if os.environ.get('GMS_KEY') else '없음 — 시작 거절'}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
