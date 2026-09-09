# -*- coding: utf-8 -*-
"""사용자 세션 상태 영속화 (Jira 224).

문제
    `POST /api/events` 로 쌓인 사용자 상태(UserVector)가 프로세스 메모리에만 있어
    서버를 재시작하면 전원이 cold_start 로 돌아간다. 시연 중 재배포 한 번에 개인화가 사라진다.

방식 — **이벤트 로그 + 재생** (스냅샷이 아니다)
    받은 이벤트를 그대로 한 줄씩 append 한다 (persona_id, events[], at). 기동 때 파일을 순서대로
    다시 `observe` 하면 같은 상태가 된다. UserVector 는 이벤트의 순수 함수라 스냅샷보다 안전하고,
    나중에 Redis Streams 로 옮길 때도 같은 모양이다 (append → replay).
    상태에 영향 없는 이벤트는 쓰지 않는다 — behavior_weights 에 가중치가 있는 이름만 남긴다.

한계 (그대로 둔 것)
    * 워커 1개 전제는 그대로다 — 프로세스마다 파일을 append 하면 서로의 이벤트를 못 본다.
      WORKERS>1 은 Redis 도입 뒤. compose 는 WORKERS=1 로 고정돼 있다
    * 파일은 계속 자란다. 기동 시 재생 시간이 문제가 되면 `compact()` 로 페르소나별 마지막
      N건만 남긴다 (기본 500건). 자동으로는 안 돈다 — 언제 줄일지는 운영 결정
"""
from __future__ import annotations

import json
import os
import time

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
DEFAULT_PATH = os.path.join(ROOT, "batch", "ingest", "data", "serving", "session_events.jsonl")


def _state_event_names():
    """behavior_weights 에 가중치가 있는 이벤트 이름 — 상태를 바꾸는 것들"""
    try:
        import sys
        sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
        import behavior_weights as BW
        import user_vector as UV
        w = BW.load()
        # 가중치 0 인 이벤트(노출·page_view 등)는 상태를 안 바꾼다 — 남기지 않는다
        names = {k for k, v in w.get("event", {}).items() if v} | set(w.get("negative", ()))
        names |= {"section_dwell", "section_view", "scroll_depth"}          # 규칙 3·4·깊이
        for k in ("UNDO", "CONVERT"):
            v = getattr(UV, k, None)
            if v:
                names |= set(v)
        return names or None
    except Exception:
        return None


class SessionLog:
    def __init__(self, path=None, keep_all=False):
        self.path = path or os.environ.get("SESSION_EVENTS_PATH") or DEFAULT_PATH
        self.state_names = None if keep_all else _state_event_names()
        self.appended = 0

    # ── 쓰기 ──────────────────────────────────────────────────────────────
    def filter(self, events):
        if self.state_names is None:
            return list(events)
        return [ev for ev in events if ev.get("event_name") in self.state_names]

    def append(self, persona_id, events):
        rows = self.filter(events)
        if not rows:
            return 0
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"persona_id": persona_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "events": rows}, ensure_ascii=False) + "\n")
        self.appended += len(rows)
        return len(rows)

    # ── 읽기 ──────────────────────────────────────────────────────────────
    def replay(self, observe):
        """파일을 순서대로 다시 observe 한다. (페르소나 수, 이벤트 수, ms)"""
        if not os.path.exists(self.path):
            return 0, 0, 0.0
        t0 = time.perf_counter()
        personas, n = set(), 0
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue                      # 깨진 줄(중간에 죽은 쓰기)은 건너뛴다
                observe(r["persona_id"], r["events"])
                personas.add(r["persona_id"]); n += len(r["events"])
        return len(personas), n, round((time.perf_counter() - t0) * 1000, 1)

    def compact(self, keep_last=500):
        """페르소나별 마지막 keep_last 건만 남겨 파일을 다시 쓴다. 돌려주는 값: (전, 후) 이벤트 수"""
        if not os.path.exists(self.path):
            return 0, 0
        per = {}
        before = 0
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue                      # 깨진 줄은 재생과 같이 버린다
                before += len(r["events"])
                per.setdefault(r["persona_id"], []).extend(r["events"])
        after = 0
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for pid, evs in per.items():
                keep = evs[-keep_last:]
                after += len(keep)
                f.write(json.dumps({"persona_id": pid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "events": keep}, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)
        return before, after
