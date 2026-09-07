"""
행동 로그 -> 사용자 벡터 상태 — 파이프라인이 만든 이벤트를 실제로 먹인다.

지금까지 `user_vector.py` 는 로컬 파일을 CLI 로 읽는 것이 전부였다. 수집 API 로
들어와 Kafka·Spark 를 통과한 이벤트가 추천으로 이어지는 경로가 없었다. 그 구간을
잇는 배치 잡이다.

입력 (둘 다 받는다)
    Spark 산출물   streaming clean_events_job 의 cleaned_events Parquet 디렉터리
                  (persona_id · event_name · product_id · properties_json · ...)
    JSONL         수집 API 로 보내기 전의 봉투. 생성기·에이전트 출력이 이 형태다

출력 (contracts/recommendation-io-spec.md §2 출력 스키마)
    user:vec:{persona_id} 해시에 그대로 넣을 수 있는 JSONL.
    **누적합과 누적가중치만** 담는다 — 전체 재계산 없이 O(148) 로 증분 갱신하려는
    설계라, 정규화된 벡터가 아니라 합을 보관해야 한다.

실행
    python batch/jobs/build_user_vectors.py data/processed/cleaned_events
    python batch/jobs/build_user_vectors.py events.jsonl --out user_vectors.jsonl
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from product_encoder import Encoder      # noqa: E402
from user_vector import UserVector       # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "batch", "ingest", "data", "serving",
                           "user_vectors.jsonl")
# 이벤트 순서. 세션 안에서는 sequence_no 가 진실이고, 세션 사이는 시각으로 잇는다
ORDER_KEYS = ("event_time", "occurred_at", "sequence_no")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_parquet_dir(path):
    """Spark 가 쓴 cleaned_events 를 읽는다. properties 는 JSON 문자열로 온다"""
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    cols = set(table.column_names)
    for row in table.to_pylist():
        props = row.get("properties_json") or row.get("properties") or "{}"
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except json.JSONDecodeError:
                props = {}
        yield {
            "persona_id": row.get("persona_id") or row.get("user_id"),
            "event_name": row.get("event_name"),
            "product_id": row.get("product_id"),
            "properties": props,
            "sequence_no": row.get("sequence_no") or 0,
            # Spark 는 event_time, 봉투는 occurred_at 을 쓴다
            "event_time": str(row.get("event_time") or ""),
            "actor_type": row.get("actor_type"),
        }
    if "persona_id" not in cols and "user_id" not in cols:
        raise SystemExit(f"{path} 에 persona_id 가 없습니다 — cleaned_events 인지 확인하세요")


def load_events(path):
    if os.path.isdir(path):
        return read_parquet_dir(path)
    return read_jsonl(path)


def sort_key(ev):
    return tuple(str(ev.get(k) or "") if k != "sequence_no" else int(ev.get(k) or 0)
                 for k in ORDER_KEYS)


def build(events, index, matrix, actor_type=None):
    """페르소나별로 이벤트를 순서대로 먹여 상태를 만든다"""
    by_persona = {}
    skipped = 0
    for ev in events:
        pid = ev.get("persona_id")
        if not pid:
            skipped += 1                      # 로그인 전 이벤트 등 — 귀속할 사람이 없다
            continue
        if actor_type and ev.get("actor_type") not in (None, actor_type):
            continue
        by_persona.setdefault(pid, []).append(ev)

    out = []
    for pid, evs in by_persona.items():
        evs.sort(key=sort_key)
        state = UserVector()
        for ev in evs:
            state.observe(ev)
        out.append(snapshot(pid, state, index, matrix, len(evs)))
    return out, skipped


def snapshot(persona_id, state, index, matrix, n_events):
    """Redis 해시에 그대로 들어갈 형태. 정규화 전 **누적합**을 보관한다"""
    pos, neg = state.weights()

    def accumulate(ws):
        u = np.zeros(matrix.shape[1], dtype=np.float64)
        total = 0.0
        for g, w in ws.items():
            i = index.get(g)
            if i is not None:
                u += w * matrix[i]
                total += w
        return u, total

    up, wp = accumulate(pos)
    un, wn = accumulate(neg)
    viewed = sorted(state.viewed)
    return {
        "persona_id": persona_id,
        "positive_u_sum": [round(float(x), 6) for x in up],
        "positive_w_sum": round(wp, 6),
        "negative_u_sum": [round(float(x), 6) for x in un],
        "negative_w_sum": round(wn, 6),
        "converted": sorted(state.converted),
        # 긍정 가중이 붙은 상품 집합 (전환 + 정독한 미전환, 규칙 5-1).
        # **학습 결합의 시드가 이것이다** — 전환만 쓰면 점수가 전환과 전환
        # 사이에 한 발짝도 안 움직여서 "행동이 쌓일수록 좋아진다" 가 깨진다.
        "positive": sorted(pos),
        "viewed": viewed,
        # 가중치 스케줄 판정용. 접촉한 고유 상품 수다 (converted 포함)
        "n_products": len(viewed),
        "n_events": n_events,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="cleaned_events Parquet 디렉터리 또는 이벤트 JSONL")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--actor-type", default=None,
                    help="synthetic / user 로 걸러낸다 (기본: 전부)")
    ap.add_argument("--show", type=int, default=3, help="맛보기 출력 인원")
    a = ap.parse_args()

    e = Encoder()
    matrix = np.asarray(e.matrix(), np.float64)
    index = {p["product_id"]: i for i, p in enumerate(e.products)}

    rows, skipped = build(load_events(a.input), index, matrix, a.actor_type)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    conv = sum(1 for r in rows if r["converted"])
    print(f"사용자 벡터 {len(rows):,}명 -> {a.out}")
    print(f"  전환 보유 {conv:,}명 ({conv / max(len(rows),1) * 100:.1f}%)"
          f" · 평균 접촉 상품 {np.mean([r['n_products'] for r in rows]):.1f}개"
          f" · persona_id 없어 건너뛴 이벤트 {skipped:,}건")
    for r in rows[:a.show]:
        print(f"  {r['persona_id']}  이벤트 {r['n_events']:>4}건 ·"
              f" 접촉 {r['n_products']:>3}개 · 전환 {len(r['converted']):>2}개 ·"
              f" 긍정 가중합 {r['positive_w_sum']:.1f} / 부정 {r['negative_w_sum']:.1f}")


if __name__ == "__main__":
    main()
