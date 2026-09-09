# -*- coding: utf-8 -*-
"""등록 상품(어휘집 밖 브랜드)이 추천 목록에서 같은 브랜드를 얼마나 끌어오나 (Jira 217).

왜 재나
    Jira 216 뒤 "등록 상품 하나를 담은 사용자 목록에서 SSAFY Beauty 가 10칸 중 7칸" 이
    관찰됐다. 그것이 **등록 상품 특유의 편향**인지, 상품이 8개인 브랜드라면 원천
    브랜드도 그만큼 나오는 **브랜드 재구매 설계**인지 갈라야 고칠지 말지가 정해진다.

무엇을 재나
    사용자 N명이 상품 하나를 담았다고 놓고 top-10(reserved=0) 중 **그 상품과 같은
    브랜드의 비율**을 잰다. 세 가지 시드를 나란히 둔다.
        등록 상품            SSAFY Beauty 8개를 돌려 쓴다
        원천 · 큰 브랜드     카탈로그에 상품이 7개 이상인 브랜드 (크기를 맞춘 대조군)
        원천 · 임의          200개에서 무작위
    페르소나가 있는 경우(속성 친화도 켜짐)와 없는 경우(미등록 회원·익명)를 따로 본다.

2026-09-09 결과 (holdout_a 300명, LTR 278 트리)
    페르소나 있음   등록 24.0%  < 원천 큰 브랜드 37.1%  > 원천 임의 27.9%
    페르소나 없음   등록 35.0%  > 원천 큰 브랜드 25.5%  > 원천 임의 19.9%
    → 속성이 있으면 등록 상품은 원천 큰 브랜드보다 **덜** 끌어온다. 초과는 페르소나가
      없고 CF 도 0 인 경로에서 약 1칸. "7/10" 은 그 경로 + 전용 칸 2개가 겹친 관찰이었다.

기각한 고침 둘 (같은 지표)
    brand 블록 가중치 0 + LTR 재학습     등록 57.0% / 70.0% — same_brand 피처 중요도가
                                           0.003→0.038 로 올라 브랜드 끌림이 더 세진다. holdout_a −0.55%p
    등록 브랜드에 원핫 차원 추가          등록 57.0% / 70.0% — 등록↔등록 코사인 0.34→0.88
    둘 다 "브랜드를 더 잘 표현" 하면 재구매 설계가 그대로 작동해 같은 브랜드가 더 나온다.
    남은 손잡이는 브랜드 상한·MMR λ 인데 그건 등록 상품 문제가 아니라 전역 정책이다
    (brand-exposure 프론티어: 상한은 비시드 1칸당 −1.8%p).

실행: python batch/jobs/eval_registered_brand_share.py [--n 300] [--split holdout_a] [--min-brand-size 7]
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.path.insert(0, os.path.join(ROOT, "batch", "serving"))

from user_vector import UserVector      # noqa: E402


def share_same_brand(engine, personas, seeds, brand_of, use_persona=True, k=10):
    out = []
    for p, g in zip(personas, seeds):
        st = UserVector()
        st.observe({"event_name": "add_to_cart", "product_id": g, "properties": {}})
        ranked = engine.rec.rank(st, persona=(p if use_persona else None), k=k, reserved=0, flags=True)
        ids = [x[0] for x in ranked]
        out.append(sum(1 for x in ids if brand_of[x] == brand_of[g]) / k)
    a = np.asarray(out)
    return a.mean(), (a >= 0.5).mean()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--split", default="holdout_a", choices=("holdout_a", "holdout_b"))
    ap.add_argument("--min-brand-size", type=int, default=7)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    import recommend_server as rs
    e = rs.Engine()
    registered = [p["product_id"] for p in e.products if p.get("product_source") == "brand_registered"]
    if not registered:
        raise SystemExit("등록 상품이 없다 — registered_products.jsonl 을 확인하십시오 (Jira 216)")
    brand_of = {p["product_id"]: p.get("brand_name") for p in e.products}
    size_of = collections.Counter(brand_of[g] for g in brand_of if g not in registered)
    seed_ids = [p["product_id"] for p in e.products[:e.n_seed]]
    big = [g for g in seed_ids if size_of[brand_of[g]] >= a.min_brand_size]

    path = os.path.join(ROOT, "simulator", "personas", "data", f"personas_{a.split}.json")
    P = json.load(open(path, encoding="utf-8"))[:a.n]
    rng = np.random.default_rng(a.seed)
    groups = {
        f"등록 상품 ({len(registered)}개 돌려 씀)": [registered[i % len(registered)] for i in range(len(P))],
        f"원천 · 브랜드 상품수 ≥{a.min_brand_size} ({len(big)}개 중)": list(rng.choice(big, size=len(P))),
        "원천 · 임의": list(rng.choice(seed_ids, size=len(P))),
    }
    print(f"{a.split} {len(P)}명 · scorer {e.scorer} · {e.algorithm} · 카탈로그 {len(e.products)} (등록 {len(registered)})")
    print(f"\n{'시드':<34} {'페르소나 있음':>22} {'페르소나 없음':>22}")
    print(f"{'':<34} {'같은브랜드  ≥절반':>22} {'같은브랜드  ≥절반':>22}")
    for name, seeds in groups.items():
        m1, h1 = share_same_brand(e, P, seeds, brand_of, True)
        m0, h0 = share_same_brand(e, P, seeds, brand_of, False)
        print(f"{name:<34} {m1:>10.1%} {h1:>10.1%} {m0:>11.1%} {h0:>10.1%}")

    V = e.V
    ri = [e.index[g] for g in registered]
    Vs, Vo = V[ri], V[:e.n_seed]
    cs = Vs @ Vs.T
    np.fill_diagonal(cs, np.nan)
    same = [(i, j) for i in range(e.n_seed) for j in range(i + 1, e.n_seed)
            if brand_of[seed_ids[i]] == brand_of[seed_ids[j]]]
    print(f"\n코사인  등록↔등록 {np.nanmean(cs):.3f} · 원천 같은 브랜드 쌍 {np.mean([Vo[i] @ Vo[j] for i, j in same]):.3f}"
          f" · 등록↔원천 {(Vs @ Vo.T).mean():.3f} · 원천 전체 쌍 {(Vo @ Vo.T)[np.triu_indices(e.n_seed, 1)].mean():.3f}")


if __name__ == "__main__":
    main()
