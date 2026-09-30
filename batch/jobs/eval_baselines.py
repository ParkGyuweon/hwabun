# -*- coding: utf-8 -*-
"""
기준선 비교 — "Recall@10 43.80% 가 인기순 추천보다 얼마나 좋은가".

    대표 지표(holdout_a 43.80%)를 낸 **같은 사람 · 같은 seed/target · 같은 후보 제외**
    위에서, 모델 대신 아래 기준선으로 줄을 세워 같은 지표를 낸다.

    인기순 (학습 기간 리뷰 수)      train 분할 페르소나(LTR 학습 집합 5,954명)의 리뷰를
                                    상품별로 센다. 평가 대상과 사람이 겹치지 않는다.
    인기순 (시점 절단)              위와 같되 **평가 대상의 target 리뷰 날짜보다 앞선 리뷰만**
                                    센다. 그 시점의 사이트가 알 수 있었던 인기다.
    인기순 (긍정 리뷰 수)           계약 §7.1.1 긍정 리뷰만 센다 (시점 절단).
    인기순 + 시드 브랜드 우선        시드와 같은 브랜드를 먼저, 그 안에서 인기순(시점 절단).
                                    "산 브랜드를 또 산다" 만 아는 손 규칙 — 더 센 기준선이다.
    인기순 (찜 수 loves_count)      모델의 prior 항이 쓰는 카탈로그 값. 수집 시점 스냅샷이라
                                    target 이후 찜까지 들어 있다 — **참고용**(약한 누출).
    무작위                          후보 n개 중 무작위 10개. 기댓값을 해석적으로 낸다.
    모델 (LTR 20피처)               eval_persona_feature 의 "학습 결합 (LTR)" 행과 같은 계산.
                                    Recall@10 이 43.80% 로 다시 나오는지로 하네스 동일성을 확인한다.

같은 규칙
    - seed/target 은 `eval_metadata_*.jsonl` (정의는 eval_metadata.py · holdout_rule.py 한 곳).
    - 사람 거르기는 `eval_persona_feature.seq_of` 그대로 (seed 가 카탈로그에 1개 이상).
    - 이미 본 상품(seed)은 후보에서 뺀다. target 은 빼지 않는다.
    - Recall@10 CI 는 부트스트랩 300회 · default_rng(42) (eval_review_replay 와 같다).
    - MRR = mean(1/rank), NDCG@10 = rank<=10 이면 1/log2(rank+1) (eval_review_replay 와 같다).
      모델은 적중을 MMR 을 거친 10칸으로, rank 는 원점수 등수로 잰다 (eval_review_replay 와 같다).
    - 기준선의 동점은 (리뷰 수 → 찜 수 → 카탈로그 순서) 로 고정한다. 매번 같은 값이 나온다.

실행
    python batch/jobs/eval_baselines.py --split holdout_a
    python batch/jobs/eval_baselines.py --split holdout_b
    python batch/jobs/eval_baselines.py --split holdout_a --no-model   # 기준선만 (모델 파일 없이)
"""
import argparse
import bisect
import json
import os
import sys
from collections import defaultdict

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.path.insert(0, ROOT)

K = 10
BOOT = 300
PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")


# ── 순수 함수 (테스트 대상) ────────────────────────────────────────────────
def canonical(review):
    """holdout_rule.canonical_product_id 와 같다 — group_id 가 대표 상품이다"""
    return review.get("group_id") or review.get("product_id")


def is_positive(review):
    """계약 §7.1.1 — holdout_rule.is_positive 를 그대로 쓴다"""
    from contracts.persona.holdout_rule import is_positive as _p
    return _p(review)


def review_dates(personas, index, positive_only=False):
    """상품 id -> 정렬된 리뷰 날짜 목록. 날짜가 없는 리뷰는 '아주 옛날' 로 둔다(항상 셈)"""
    out = defaultdict(list)
    for p in personas:
        for r in p.get("reviews", []):
            g = canonical(r)
            if g not in index:
                continue
            if positive_only and not is_positive(r):
                continue
            out[g].append(str(r.get("submission_time") or ""))
    return {g: sorted(v) for g, v in out.items()}


def popularity(dates, index, cutoff=None):
    """상품별 리뷰 수 벡터. cutoff(YYYY-MM-DD) 를 주면 그 날짜 **이전** 리뷰만 센다"""
    v = np.zeros(len(index), dtype=np.float64)
    for g, ds in dates.items():
        v[index[g]] = len(ds) if cutoff is None else bisect.bisect_left(ds, cutoff)
    return v


def order_by(primary, *tiebreaks):
    """점수 내림차순 순서. 동점은 tiebreaks 내림차순, 그래도 같으면 카탈로그 앞 순서"""
    n = len(primary)
    keys = [np.arange(n)] + [-np.asarray(t, float) for t in reversed(tiebreaks)] \
        + [-np.asarray(primary, float)]
    return np.lexsort(keys)


def rank_in(order, cand, target_i):
    """후보(cand=True) 안에서 target 의 1-기준 등수"""
    pos = 0
    for i in order:
        if cand[i]:
            pos += 1
            if i == target_i:
                return pos
    raise ValueError("target 이 후보에 없다")


def random_expectation(n_cand, k=K):
    """후보 n개를 무작위로 줄세울 때 (Recall@k, MRR, NDCG@k) 기댓값 — target 등수는 1..n 균등"""
    n = int(n_cand)
    r = np.arange(1, n + 1, dtype=float)
    top = r[:min(k, n)]
    return min(k, n) / n, float((1.0 / r).sum() / n), float((1.0 / np.log2(top + 1)).sum() / n)


def summarize(hits, ranks, k=K, boot=BOOT, seed=42):
    """eval_review_replay 와 같은 지표 · 같은 부트스트랩"""
    hits = np.asarray(hits, bool)
    ranks = np.asarray(ranks, float)
    ndcg = np.where(ranks <= k, 1.0 / np.log2(ranks + 1), 0.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(hits), (boot, len(hits)))
    lo, hi = np.percentile(hits[idx].mean(axis=1) * 100, [2.5, 97.5])
    return {"n": int(len(hits)), "recall": float(hits.mean() * 100),
            "ci": (float(lo), float(hi)), "mrr": float(np.mean(1.0 / ranks)),
            "ndcg": float(ndcg.mean()), "median_rank": float(np.median(ranks))}


def paired_diff(a, b, boot=BOOT, seed=42):
    """같은 사람 짝비교 a−b (%p) 와 95% CI"""
    d = np.asarray(a, float) - np.asarray(b, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (boot, len(d)))
    lo, hi = np.percentile(d[idx].mean(axis=1) * 100, [2.5, 97.5])
    return float(d.mean() * 100), float(lo), float(hi)


# ── 실행 ────────────────────────────────────────────────────────────────
def load_split(split):
    from eval_metadata import load as load_metadata
    if split.startswith("holdout_"):
        tag = split.split("_")[1]
        ppath = os.path.join(ROOT, "simulator", "personas", "data", f"personas_holdout_{tag}.json")
        mpath = os.path.join(ROOT, "batch", "ingest", "data", f"eval_metadata_holdout_{tag}.jsonl")
        rows = load_metadata(path=mpath, split=split)
    else:
        ppath, rows = PERSONAS, load_metadata(split=split)
    profiles = {p["persona_id"]: p for p in json.load(open(ppath, encoding="utf-8"))}
    return [dict(profiles[r["persona_id"]], _meta=r) for r in rows if r["persona_id"] in profiles]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="holdout_a",
                    choices=("valid", "test", "holdout_a", "holdout_b"))
    ap.add_argument("--no-model", dest="model", action="store_false", default=True,
                    help="모델(LTR) 행을 빼고 기준선만 낸다")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    from eval_persona_feature import seq_of
    from persona_split import select as select_split
    from product_encoder import Encoder, brand_key

    e = Encoder()
    V = np.asarray(e.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(e.products)}
    n = len(V)
    loves = np.array([p["loves_count"] for p in e.products], float)
    brands = np.array([brand_key(p) for p in e.products], dtype=object)

    # 인기의 출처 = train 분할 페르소나 (LTR 이 학습한 그 5,954명). 평가 대상과 사람이 겹치면 안 된다
    source = select_split(json.load(open(PERSONAS, encoding="utf-8")), "train")
    personas = load_split(a.split)
    if a.limit:
        personas = personas[:a.limit]
    overlap = ({p.get("author_id") for p in source} & {p.get("author_id") for p in personas}) - {None}
    if overlap:
        raise SystemExit(f"인기 출처와 평가 대상이 {len(overlap)}명 겹친다 — 누출")
    d_all = review_dates(source, index)
    d_pos = review_dates(source, index, positive_only=True)
    pop_all = popularity(d_all, index)
    order_all = order_by(pop_all, loves)
    order_loves = order_by(loves, pop_all)

    ltr = recommender = None
    if a.model:
        from ltr_features import LtrFeatures, load_ltr, rating_weights, weighted_from_meta
        from persona_feature import load as load_affinity
        from recommender import LAMBDA_MMR, Recommender, load_cooc
        lg = np.log1p(loves)
        prior = ((lg - lg.min()) / (lg.max() - lg.min())).astype(np.float32)
        affinity = load_affinity(index)
        cooc, supporters = load_cooc()
        loaded = load_ltr()
        if cooc is None or loaded is None:
            raise SystemExit("item_cooc.npz 또는 ltr_model.pkl 이 없다 — --no-model 로 기준선만 돌리거나 "
                             "build_cooc.py · train_ltr.py 를 먼저 돌린다")
        clf, meta = loaded
        F = LtrFeatures(e, V, prior, affinity, cooc, supporters, weighted=weighted_from_meta(meta))
        recommender = Recommender(V, index, prior, affinity=affinity,
                                  brands=list(brands),
                                  known_brands=set(e.blk["brand"]["vocab"]),
                                  cooc=cooc, supporters=supporters)
        ltr = (clf, F, rating_weights, LAMBDA_MMR, meta)

    names = ["인기순 · 리뷰 수 (train 분할)", "인기순 · 리뷰 수 (target 시점 절단)",
             "인기순 · 긍정 리뷰 수 (시점 절단)", "인기순 + 시드 브랜드 우선 (시점 절단)",
             "인기순 · 찜 수 loves_count (참고)"]
    res = {k: ([], []) for k in names}
    rnd = []
    model_h, model_r = [], []
    for p in personas:
        s = seq_of(p["_meta"], index)
        if len(s) < 2:
            continue
        si = [index[g] for g in s[:-1]]
        ti = index[s[-1]]
        cand = np.ones(n, bool)
        cand[si] = False
        cutoff = str(p["_meta"].get("target_submitted_at") or "") or None
        pop_cut = popularity(d_all, index, cutoff)
        pos_cut = popularity(d_pos, index, cutoff)
        same = np.isin(brands, list({brands[i] for i in si})).astype(float)
        orders = [order_all, order_by(pop_cut, loves), order_by(pos_cut, pop_cut, loves),
                  order_by(same, pop_cut, loves), order_loves]
        for nm, od in zip(names, orders):
            r = rank_in(od, cand, ti)
            res[nm][0].append(r <= K)
            res[nm][1].append(r)
        rnd.append(random_expectation(int(cand.sum())))
        if ltr is not None:
            clf, F, rw, lam, meta = ltr
            sw = rw(p, s[:-1]) if F.weighted else None
            sc = clf.predict_proba(F.make(p, si, cand, seed_weights=sw))[:, 1]
            x = np.where(cand, sc, -np.inf)
            order = [int(i) for i in np.argsort(-x)[:K * 3] if np.isfinite(x[i])]
            top = recommender.mmr(x, order, K, lam)
            model_h.append(ti in list(top))
            model_r.append(int((x > x[ti]).sum()) + 1)

    print(f"**{a.split}** · 평가 {len(rnd):,}명 · 후보 = 카탈로그 {n}개 − seed")
    print(f"인기 출처 train 분할 {len(source):,}명 · 리뷰 {int(pop_all.sum()):,}건 (평가 대상과 겹침 0명)\n")
    print(f"{'방법':<34}{'Recall@10':>10}  {'95% CI':>16}  {'MRR':>7}  {'NDCG@10':>8}  {'순위 중앙':>7}")
    print("-" * 92)
    rows = []
    if model_h:
        m = summarize(model_h, model_r)
        rows.append((f"모델 LTR ({meta['n_trees']}트리)", m))
    for nm in names:
        rows.append((nm, summarize(*res[nm])))
    for nm, m in rows:
        print(f"{nm:<34}{m['recall']:9.2f}%  [{m['ci'][0]:6.2f}, {m['ci'][1]:6.2f}]"
              f"  {m['mrr']:7.4f}  {m['ndcg']:8.4f}  {m['median_rank']:7.0f}")
    rr = np.array(rnd)
    print(f"{'무작위 (기댓값)':<34}{rr[:, 0].mean() * 100:9.2f}%  {'(해석적)':>16}"
          f"  {rr[:, 1].mean():7.4f}  {rr[:, 2].mean():8.4f}")

    if model_h:
        print("\n모델 − 기준선 (같은 사람 짝비교, 부트스트랩 300회)")
        for nm in names:
            d, lo, hi = paired_diff(model_h, res[nm][0])
            print(f"  − {nm:<34}{d:+7.2f}%p  [{lo:+.2f}, {hi:+.2f}]"
                  f"   ×{np.mean(model_h) / max(np.mean(res[nm][0]), 1e-9):.2f}")
        print(f"  − {'무작위 (기댓값)':<34}{(np.mean(model_h) - rr[:, 0].mean()) * 100:+7.2f}%p"
              f"   ×{np.mean(model_h) / rr[:, 0].mean():.2f}")


if __name__ == "__main__":
    main()
