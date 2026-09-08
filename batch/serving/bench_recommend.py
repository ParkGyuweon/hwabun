# -*- coding: utf-8 -*-
"""추천 API 응답 시간 실측 — 계약 §5 "정해진 응답 시간" 의 근거 숫자 (Jira 206).

두 가지를 잰다
    (1) 점수 계산만        Recommender.rank 한 번 — 모델 추론 + MMR + 전용 칸
    (2) HTTP 왕복 포함     TestClient 로 /api/recommend — JSON 직렬화·reason 포함

⚠ 작은 표본으로 재면 안 된다. 부스팅 트리는 첫 호출이 비싸서 30명이면 48ms 가
   나온다 (부록 T). 워밍업 뒤 300명 이상.

실행
    python batch/serving/bench_recommend.py [--n 300] [--split holdout_a] [--url http://host:8300]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def pct(xs):
    a = np.asarray(xs)
    return f"p50 {np.percentile(a, 50):6.2f}ms · p95 {np.percentile(a, 95):6.2f}ms · max {a.max():6.2f}ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--split", default="holdout_a")
    ap.add_argument("--reserved", type=int, default=2)
    ap.add_argument("--url", default=None, help="띄워 둔 서버. 없으면 프로세스 안 TestClient")
    a = ap.parse_args()

    meta = os.path.join(ROOT, "batch", "ingest", "data", f"eval_metadata_{a.split}.jsonl")
    pids = [json.loads(l)["persona_id"] for l in open(meta, encoding="utf-8")][:a.n + 20]

    if a.url:
        import httpx
        get = lambda p: httpx.get(a.url + "/api/recommend", params=p, timeout=30).json()  # noqa: E731
        label = a.url
    else:
        from fastapi.testclient import TestClient
        import recommend_server as rs
        c = TestClient(rs.app)
        get = lambda p: c.get("/api/recommend", params=p).json()                          # noqa: E731
        label = "in-process TestClient"

    for p in pids[:20]:                                   # 워밍업 — 첫 호출은 비싸다
        get({"persona_id": p, "seed": "review", "reserved": a.reserved})

    inner, outer = [], []
    for p in pids[20:20 + a.n]:
        t0 = time.perf_counter()
        r = get({"persona_id": p, "seed": "review", "reserved": a.reserved})
        outer.append((time.perf_counter() - t0) * 1000)
        inner.append(r["latency_ms"])
    print(f"{label} · {a.split} {a.n}명 · seed=review · reserved={a.reserved} · scorer={r['scorer']}")
    print(f"  점수 계산만 (rank)     {pct(inner)}")
    print(f"  HTTP 왕복 + reason     {pct(outer)}")
    print("  ⚠ 파이썬 단일 프로세스·단일 요청 기준. 동시 요청은 워커 수로 푼다")


if __name__ == "__main__":
    main()
