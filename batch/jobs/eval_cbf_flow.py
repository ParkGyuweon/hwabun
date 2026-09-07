"""
점수 계산 흐름 검증 — 로그 한 줄에서 추천 목록까지 전 구간을 실제로 돌린다.

    행동 로그 -> 사용자 벡터 상태 -> 점수(CBF + CF 가점) -> 노출 정책 -> MMR -> 상위 k

조각별 테스트는 이미 있지만, **조각을 이어 붙였을 때 실제로 목록이 나오는지**는
따로 확인해야 한다. 서빙은 Redis 에 저장된 상태(누적합)만 보고 계산하므로,
여기서도 `build_user_vectors` 가 낸 스냅샷만으로 점수를 낸다 — UserVector 객체를
다시 쓰지 않는다. 그래야 "저장한 것만으로 추천이 되는가" 가 검증된다.

계약: contracts/recommendation-io-spec.md §API 처리 1~7단계

실행
    python simulator/generator/gen_behavior_logs.py --limit 50 --out events.jsonl
    python batch/jobs/eval_cbf_flow.py events.jsonl      # CF 켬 (기본)
    python batch/jobs/eval_cbf_flow.py events.jsonl --no-cf
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

# 콘솔이 cp949 면 "—" 나 "⚠️" 에서 UnicodeEncodeError 로 죽는다.
# 하필 CF 경고문이 그 문자를 쓰므로, 경고를 못 보고 죽는 일이 생긴다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from build_user_vectors import build, load_events        # noqa: E402
from persona_feature import AffinityTable                # noqa: E402
from product_encoder import Encoder                      # noqa: E402
from recommender import (CF_BETA, LAMBDA, LAMBDA_MMR, VIEW_CAP,   # noqa: E402
                         Recommender, cf_bonus, load_cooc, schedule_for)

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
K = 10


def vectors_from_snapshot(snapshot):
    """저장된 누적합 -> 정규화 벡터. 서빙이 하는 것과 같은 계산 (계약 §API 3단계)"""
    out = []
    for axis in ("positive", "negative"):
        total = snapshot[f"{axis}_w_sum"]
        vec = np.asarray(snapshot[f"{axis}_u_sum"], dtype=np.float32)
        if total <= 0:
            out.append(None)
            continue
        vec = vec / total
        norm = np.linalg.norm(vec)
        out.append(None if norm < 1e-9 else vec / norm)
    return out


def score_from_snapshot(snapshot, persona, matrix, prior, affinity,
                        index=None, cooc=None, supporters=None):
    """계약 §API 4단계. 상태와 페르소나만으로 점수를 만든다

    CF 가점(§4-1)도 **스냅샷에 저장된 `converted` 만으로** 낸다. 서빙이 가진 것도
    그것뿐이므로, 여기서 UserVector 를 다시 들추면 "저장한 것만으로 되는가" 를
    검증하지 못한다.
    """
    positive, negative = vectors_from_snapshot(snapshot)
    w1, w2, w3 = schedule_for(snapshot["n_products"])
    score = np.zeros(len(matrix), dtype=np.float32)
    if positive is not None:
        score += w1 * (matrix @ positive)
    if negative is not None:
        score -= LAMBDA * (matrix @ negative)
    if persona is not None:
        score += w2 * affinity(persona)
    score = score + w3 * prior
    if cooc is not None and index is not None:
        rows = [index[g] for g in snapshot["converted"] if g in index]
        bonus = cf_bonus(cooc, rows, None, supporters)
        if bonus is not None:
            score = score + CF_BETA * bonus
    return score, (w1, w2, w3)


def serve(snapshot, persona, matrix, prior, affinity, recommender,
          k=K, lam_mmr=LAMBDA_MMR, view_cap=VIEW_CAP,
          cooc=None, supporters=None):
    """노출 정책(5) -> MMR(6) -> 상위 k(7)"""
    score, weights = score_from_snapshot(snapshot, persona, matrix, prior, affinity,
                                         recommender.idx, cooc, supporters)
    score = score.copy()

    # 전환한 상품은 후보에서 완전히 제외한다
    for gid in snapshot["converted"]:
        i = recommender.idx.get(gid)
        if i is not None:
            score[i] = -np.inf

    viewed = set(snapshot["viewed"])
    order, used = [], 0
    for i in np.argsort(-score):
        if not np.isfinite(score[i]):
            break
        if recommender.ids[i] in viewed:      # 조회 상품은 상한까지만 남긴다
            if used >= view_cap:
                continue
            used += 1
        order.append(int(i))
        if len(order) >= k * 3:               # MMR 이 고를 여지를 남긴다
            break
    picked = recommender.mmr(score, order, k, lam_mmr)
    return picked, weights, score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("events", help="이벤트 JSONL 또는 cleaned_events Parquet 디렉터리")
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--lam-mmr", type=float, default=LAMBDA_MMR)
    ap.add_argument("--show", type=int, default=2, help="목록을 펼쳐 볼 인원")
    # CF 가점은 채택됐다 (2026-09-07 · 계약 §4-1). 기본이 켬이고 끄려면 --no-cf 다.
    # 이 검증의 목적이 "계약 처리 1~7단계가 저장된 상태만으로 도는가" 이므로
    # 4단계에 CF 가 빠져 있으면 검증 자체가 낡은 계약을 보게 된다.
    ap.add_argument("--no-cf", dest="cf", action="store_false", default=True,
                    help="CF 가점을 끄고 CBF 단독으로 돈다 (옛 수치 재현용)")
    a = ap.parse_args()

    encoder = Encoder()
    matrix = np.asarray(encoder.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(encoder.products)}
    name = {p["product_id"]: f'{p["brand_name"]} {p["product_name"]}'
            for p in encoder.products}
    brand = [p["brand_name"] for p in encoder.products]
    prior = np.asarray(encoder.prior(), dtype=np.float32)
    affinity = AffinityTable(index)
    recommender = Recommender(matrix, index, prior, affinity=affinity)
    cooc, supporters = load_cooc() if a.cf else (None, None)
    if a.cf and cooc is None:
        print("⚠️ CF 가점이 켜져 있는데 item_cooc.npz 가 없습니다 — "
              "CBF 단독으로 돕니다. `python batch/jobs/build_cooc.py` 를 먼저 도십시오")
    elif a.cf:
        print("CF 가점 켬 (β=1.0 · 가점 전용 · 계약 §4-1)")
    else:
        print("CF 가점 끔 — CBF 단독")
    personas = {p["persona_id"]: p
                for p in json.load(open(PERSONAS, encoding="utf-8"))}

    print("1) 이벤트 읽기")
    events = list(load_events(a.events))
    print(f"   {len(events):,}건")

    print("2) 사용자 벡터 상태 만들기 (build_user_vectors)")
    t0 = time.perf_counter()
    snapshots, skipped = build(events, index, matrix.astype(np.float64))
    build_sec = time.perf_counter() - t0
    print(f"   {len(snapshots):,}명 · {build_sec:.2f}초"
          f" · persona_id 없어 건너뜀 {skipped:,}건")

    print("3~7) 스냅샷만으로 점수 -> 노출 정책 -> MMR -> 상위 k")
    unknown = [s for s in snapshots if s["persona_id"] not in personas]
    lists, buckets, elapsed = [], collections.Counter(), 0.0
    uniq_brand, blocked_ok, cap_ok = [], 0, 0
    for snap in snapshots:
        persona = personas.get(snap["persona_id"])
        t0 = time.perf_counter()
        picked, weights, _ = serve(snap, persona, matrix, prior, affinity,
                                   recommender, k=a.k, lam_mmr=a.lam_mmr,
                                   cooc=cooc, supporters=supporters)
        elapsed += time.perf_counter() - t0
        ids = [recommender.ids[i] for i in picked]
        lists.append((snap, ids))
        buckets[weights] += 1
        uniq_brand.append(len({brand[i] for i in picked}))
        if not (set(ids) & set(snap["converted"])):
            blocked_ok += 1
        if len([g for g in ids if g in set(snap["viewed"])]) <= VIEW_CAP:
            cap_ok += 1

    n = len(lists)
    print(f"   목록 {n:,}건 · 1건당 {elapsed / max(n,1) * 1e6:.0f}μs")
    if unknown:
        print(f"   ⚠ 페르소나 정보를 못 찾은 {len(unknown)}명은 속성 항 없이 계산했습니다")
    print()
    print("검증")
    print(f"  전환 상품이 목록에 없음        {blocked_ok:,}/{n:,}"
          f" ({blocked_ok / max(n,1) * 100:.1f}%)")
    print(f"  조회 상품 {VIEW_CAP}개 이하로 유지    {cap_ok:,}/{n:,}"
          f" ({cap_ok / max(n,1) * 100:.1f}%)")
    print(f"  목록당 고유 브랜드 평균        {np.mean(uniq_brand):.1f}개"
          f" (λ_mmr={a.lam_mmr})")
    print(f"  가중치 스케줄 분포")
    for (w1, w2, w3), count in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"      w1={w1} w2={w2} w3={w3}  {count:,}명")

    for snap, ids in lists[:a.show]:
        print(f"\n  [{snap['persona_id']}] 접촉 {snap['n_products']}개 ·"
              f" 전환 {len(snap['converted'])}개")
        for rank, gid in enumerate(ids, 1):
            mark = "  (조회함)" if gid in set(snap["viewed"]) else ""
            print(f"     {rank:>2}. {name[gid][:52]}{mark}")


if __name__ == "__main__":
    main()
