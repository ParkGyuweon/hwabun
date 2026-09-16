# -*- coding: utf-8 -*-
"""
시연 캐시를 세션 단위로 섞는다 — "만 명이 동시에 움직인다" 그림용 (Jira 337, 2026-09-16)
================================================================================

    python simulator/generator/shuffle_sessions.py in.jsonl out.jsonl [--seed 7]

왜
    gen_behavior_logs 는 페르소나별로 뭉쳐 쓴다 (PC00001 의 85일치 → PC00002 …). 그대로 초당 3,000건을 흘리면
    화면의 "활동 주체" 는 앞 사람부터 한 명씩 늘어, 2분 동안 9,900명 중 200명쯤만 움직인 것으로 보인다.
    세션 순서를 무작위로 섞으면 같은 2분에 거의 전원이 나타난다 (한 사람이 세션 수십 개라 9% 만 흘려도 다 걸린다).

무엇을 지키나
    * 세션 안 이벤트 순서·내용은 그대로 — 파일 안에서 한 세션은 연속 구간이므로 구간 단위로 옮긴다.
      sequence_no·occurred_at 의 세션 내 단조성은 깨지지 않는다. 마트 Job 은 occurred_at 으로 세션을 다시 세우니 영향 없다.
    * Kafka key 는 session_id 라 파티션 배분도 그대로.
    * 세션 사이의 시간 순서는 섞인다 — 시연에서는 "오늘 하루 몰린 트래픽" 으로 보이고, 정제 단계는 시각으로 정렬한다.

비용
    1차 통과로 세션 구간(시작 오프셋·길이)만 모은다 — 9,900명 6.9GB 면 구간 약 60만 개, RAM 수십 MB.
    2차 통과는 구간을 무작위 순서로 읽어 쓴다. SSD 에서 몇 분.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time


def session_ranges(path):
    """(시작 오프셋, 바이트 길이) — 파일 안에서 연속한 같은 session_id 구간"""
    ranges = []
    cur_sid, cur_start = None, 0
    pos = 0
    with open(path, "rb") as f:
        for line in f:
            n = len(line)
            try:
                sid = json.loads(line).get("session_id")
            except Exception:
                sid = None
            if sid != cur_sid:
                if cur_sid is not None or pos > cur_start:
                    ranges.append((cur_start, pos - cur_start))
                cur_sid, cur_start = sid, pos
            pos += n
        if pos > cur_start:
            ranges.append((cur_start, pos - cur_start))
    return ranges


def shuffle(src, dst, seed=7, log=print):
    t0 = time.time()
    ranges = session_ranges(src)
    log(f"[shuffle] 세션 구간 {len(ranges):,}개 ({time.time()-t0:.0f}초)")
    rng = random.Random(seed)
    rng.shuffle(ranges)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    written = 0
    with open(src, "rb") as f, open(dst, "wb") as out:
        for i, (start, n) in enumerate(ranges):
            f.seek(start)
            out.write(f.read(n))
            written += n
            if i % 100000 == 0 and i:
                log(f"[shuffle] {i:,}/{len(ranges):,} 구간 · {written/1e9:.1f}GB")
    log(f"[shuffle] 끝 — {written/1e9:.2f}GB → {dst} ({time.time()-t0:.0f}초)")
    return len(ranges), written


def main():
    ap = argparse.ArgumentParser(description="시연 캐시를 세션 단위로 섞는다")
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    if os.path.abspath(a.src) == os.path.abspath(a.dst):
        sys.exit("src 와 dst 가 같다")
    shuffle(a.src, a.dst, a.seed)


if __name__ == "__main__":
    main()
