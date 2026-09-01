"""
페르소나 속성 피처 검증 — 레포 데이터만으로 돌린다.

    페르소나 9,900명의 리뷰 상품을 시간순으로 늘어놓고 **마지막 1개를 정답**으로
    떼어낸 뒤, 앞의 것들(시드)로 추천했을 때 정답이 상위 10개에 들어오는지 본다.
    생성 로그가 아니라 실제 리뷰를 쓴다.

무엇을 확인하는가 (docs/ai/persona-feature-port.md §4)
    기준 2  현행 스케줄 정확도가 이관 전과 같은가
    기준 3  속성 항이 실제로 붙었는가 (w2=0 과 비교해 차이가 나야 한다)
    참고    스케줄 변경 효과 · 롱테일 · 계산 시간

⚠ 이 평가의 친화도 테이블은 리뷰 전체로 만든 것이라 정답이 포함돼 있다.
   낙관 편향은 전체 +0.23%p / 속성 항 단독 +0.59%p 로 측정됐다(같은 문서 §5).
   조건 간 **차이**를 보는 데는 영향이 없다.

실행: python batch/jobs/eval_persona_feature.py [--limit N]
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
from persona_feature import load as load_affinity          # noqa: E402
from persona_split import select as select_split           # noqa: E402
from product_encoder import Encoder                        # noqa: E402
from recommender import (LAMBDA_MMR, SCHEDULE,             # noqa: E402
                         Recommender, schedule_for)

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
K = 10
BOOT = 300
PREV_SCHEDULE = [(0, 0.00, 0.30, 0.70), (5, 0.70, 0.25, 0.05),
                 (10 ** 9, 0.40, 0.55, 0.05)]


def seq_of(persona, index):
    """리뷰 상품을 등장 순서대로. 마지막이 정답이다"""
    out = []
    for r in persona["reviews"]:
        g = r["group_id"]
        if g in index and g not in out:
            out.append(g)
    return out


def weights(schedule, n_seed):
    for hi, w1, w2, w3 in schedule:
        if n_seed <= hi:
            return w1, w2, w3
    return schedule[-1][1:]


def evaluate(personas, V, prior, pop_rank, affinity, index, recommender):
    """조건별 적중 여부를 사람 단위로 모은다. 같은 사람을 여러 조건에 쓰므로 짝비교가 된다

    조건은 **우리가 골랐던 것들**이다. valid 에서 같은 선택이 나오는지 확인하고,
    test 에서는 고른 것 하나만 최종 수치로 보고한다.
    """
    n = len(V)
    conds = {"현행 (스케줄+MMR)": (SCHEDULE, True, LAMBDA_MMR),
             "이전 스케줄": (PREV_SCHEDULE, True, LAMBDA_MMR),
             "속성 항 제거(w2=0)": (SCHEDULE, False, LAMBDA_MMR),
             "MMR 끔(λ=1.0)": (SCHEDULE, True, 1.0)}
    hits = {c: [] for c in conds}
    longtail, seeds, elapsed = [], [], 0.0
    for p in personas:
        s = seq_of(p, index)
        if len(s) < 2:
            continue
        si = [index[g] for g in s[:-1]]
        ti = index[s[-1]]
        cand = np.ones(n, bool)
        cand[si] = False                       # 시드는 후보에서 뺀다 (leakage 차단)

        u = V[si].mean(0)
        nu = np.linalg.norm(u)
        cos = V @ (u / nu) if nu > 1e-9 else np.zeros(n, np.float32)
        t0 = time.perf_counter()
        at = affinity(p)
        elapsed += time.perf_counter() - t0

        for name, (sch, use_attr, lam_mmr) in conds.items():
            w1, w2, w3 = weights(sch, len(si))
            if not use_attr:
                w1, w2, w3 = w1 + w2, 0.0, w3
            x = np.where(cand, w1 * cos + w2 * at + w3 * prior, -np.inf)
            if lam_mmr >= 1.0:
                top = np.argsort(-x)[:K]
            else:
                order = [int(i) for i in np.argsort(-x)[:K * 3] if np.isfinite(x[i])]
                top = recommender.mmr(x, order, K, lam_mmr)
            hits[name].append(1 if ti in list(top) else 0)
        longtail.append(pop_rank[ti] >= 101)
        seeds.append(len(si))
    return ({k: np.array(v) for k, v in hits.items()},
            np.array(longtail), np.array(seeds), elapsed)


def paired_ci(a, b, rng, boot=BOOT):
    d = a.astype(float) - b.astype(float)
    i = rng.integers(0, len(d), (boot, len(d)))
    m = d[i].mean(axis=1) * 100
    return d.mean() * 100, np.percentile(m, 2.5), np.percentile(m, 97.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="페르소나 수 (기본 전원)")
    ap.add_argument("--split", choices=("train", "valid", "test", "all"),
                    default="valid",
                    help="기본은 valid — 파라미터를 고르는 집합이다. "
                         "test 는 선택이 끝난 뒤 최종 보고에만 쓴다 (docs/ai/"
                         "evaluation-framework.md 1절)")
    a = ap.parse_args()

    e = Encoder()
    V = np.asarray(e.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(e.products)}
    lg = np.log1p(np.array([p["loves_count"] for p in e.products], float))
    prior = ((lg - lg.min()) / (lg.max() - lg.min())).astype(np.float32)
    nrev = np.array([p["_review_stats"]["review_count"] for p in e.products])
    pop_rank = np.empty(len(V), int)
    pop_rank[np.argsort(-nrev)] = np.arange(len(V))

    affinity = load_affinity(index)
    recommender = Recommender(V, index, prior, affinity=affinity)
    personas = select_split(json.load(open(PERSONAS, encoding="utf-8")), a.split)
    if a.limit:
        personas = personas[:a.limit]

    print(f"상품 {V.shape[0]}개 x {V.shape[1]}차원")
    print(f"**{a.split}** 집합 {len(personas):,}명 · 친화도 {affinity.n_rows:,}행")
    print(f"스케줄 {SCHEDULE} · λ_mmr {LAMBDA_MMR}")
    if a.split == "test":
        print("  ⚠ test 는 최종 보고용이다. 이 수치를 보고 파라미터를 고치면 "
              "분할이 무의미해진다")
    elif a.split == "all":
        print("  ⚠ 전원 집합이다. 파라미터 선택에도 최종 보고에도 쓰지 말 것")

    hits, lt, seeds, elapsed = evaluate(personas, V, prior, pop_rank, affinity,
                                        index, recommender)
    rng = np.random.default_rng(42)
    base = hits["현행 (스케줄+MMR)"]

    print(f"\n평가 {len(base):,}명 · 롱테일 {lt.sum():,}명 · Recall@10\n")
    print(f"{'조건':<22}{'전체':>8}{'롱테일':>9}   {'현행 대비 (CI)':>24}")
    print("-" * 66)
    for name, h in hits.items():
        d, lo, hi = paired_ci(h, base, rng)
        diff = ("기준" if name.startswith("현행")
                else f"{d:+6.2f}%p  [{lo:+.2f}, {hi:+.2f}]")
        print(f"{name:<22}{h.mean()*100:7.2f}%{h[lt].mean()*100:8.2f}%   {diff:>24}")

    print(f"\n시드 개수별 (전체 Recall@10)")
    bs = [(1, 2, "1~2개"), (3, 5, "3~5개"), (6, 99, "6개 이상")]
    print(f"{'조건':<22}" + "".join(f"{b[2]:>11}" for b in bs))
    print("-" * 66)
    for name, h in hits.items():
        row = ""
        for lo_, hi_, _ in bs:
            m = (seeds >= lo_) & (seeds <= hi_)
            row += f"{h[m].mean()*100:10.2f}%" if m.sum() else "          -"
        print(f"{name:<22}{row}")

    per = elapsed / max(len(base), 1) * 1000
    print(f"\n속성 피처 계산 {elapsed:.2f}초 / {len(base):,}명 = 1인당 {per:.3f}ms")


if __name__ == "__main__":
    main()
