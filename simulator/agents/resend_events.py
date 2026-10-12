"""러너가 파일로만 남긴 PA 행동 로그를 수집 API 로 다시 보낸다 (2026-10-01).

왜 필요한가: agent_runner 는 프론트의 /api/events 요청을 가로채(route.fulfill) 파일에 쓰고,
``--post`` 를 안 주면 수집 서버로는 **아무것도** 가지 않는다. 09-30 PA 100명·재구매 60건이
그렇게 돌아 쇼핑몰 DB 에 주문은 107건 있는데 운영 raw 에는 행동 로그가 0건이었다
(데이터 파트 10-01 지적). 이 스크립트는 그 파일을 생성기·러너와 **같은 CollectorClient** 로
같은 헤더(X-Actor-Type: synthetic, X-Simulation-Run-Id)를 붙여 보낸다.

    python simulator/agents/resend_events.py 파일.jsonl [...] --post https://j15a306.p.ssafy.io
    python simulator/agents/resend_events.py 파일.jsonl            # --post 없으면 세기만 한다

주의: raw 초기화(민우님 ②) **뒤에** 보낸다. 앞에 보내면 초기화 때 같이 지워진다.
      같은 파일을 두 번 보내면 수집기 dedupe 창(event_id 20만) 밖에서는 중복이 raw 에 남는다.
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "simulator"))
from collector_client import CollectorClient  # noqa: E402

POST_BATCH = 100     # 백엔드 EventBatchRequest @Size(max = 100) — agent_runner 와 같다


def load(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--post", default=None, metavar="URL", help="수집 API 베이스. 없으면 세기만")
    ap.add_argument("--post-timeout", type=int, default=40)
    ap.add_argument("--rps", type=int, default=0, help="초당 이벤트 상한 (0 = 없음)")
    a = ap.parse_args()

    total = 0
    for path in a.files:
        if path.endswith("_decisions.jsonl"):
            print(f"{os.path.basename(path)}: 판단 근거 파일 — 건너뜀 (이벤트가 아니다)")
            continue
        events = [e for e in load(path) if "event_name" in e]
        runs = Counter(e.get("properties", {}).get("simulation_run_id") for e in events)
        names = Counter(e["event_name"] for e in events)
        actors = Counter(e.get("actor_type") for e in events)
        print(f"{os.path.basename(path)}: {len(events):,}건 · run {dict(runs)} · actor {dict(actors)}"
              f" · purchase {names.get('purchase', 0)} · add_to_cart {names.get('add_to_cart', 0)}")
        total += len(events)
        if not a.post:
            continue
        client = CollectorClient(a.post, timeout=a.post_timeout, max_batch=POST_BATCH,
                                 rps=a.rps, log=lambda m: print(f"   {m}"))
        for run_id, _ in runs.items():
            chunk = [e for e in events if e.get("properties", {}).get("simulation_run_id") == run_id]
            st = client.send(chunk, schema_version=chunk[0].get("schema_version", "0.2.0-draft"),
                             headers={"X-Actor-Type": "synthetic", "X-Simulation-Run-Id": run_id or ""})
            print(f"   run {run_id}: 보냄 {st['sent']:,} · 버림 {st['dropped']} · 포기 {st['gave_up']} · 재시도 {st['retries']}")
    print(f"합계 {total:,}건" + ("" if a.post else " (전송 안 함 — --post 를 주면 보낸다)"))


if __name__ == "__main__":
    main()
