"""
실제 리뷰 이력 순차 재생 — synthetic 행동을 최소화한 평가.

    과거 리뷰를 **시간순 이벤트로 재생**해서 사용자 벡터를 만들고,
    `eval_metadata.jsonl` 의 target(계약 §7.1 — 마지막 리뷰가 긍정일 때)이
    추천 Top 10 에 들어오는지 본다.

동적 시뮬레이션과 다른 점: 탐색 상품을 우리가 뽑지 않는다. 사용자가 **실제로 남긴
리뷰 순서** 그대로 간다. 그래서 "우리가 지어낸 행동" 이 개입할 여지가 가장 적다.
가능한 경우 이 축을 우선한다 (docs/ai/evaluation-framework.md 3절).

리뷰 -> 이벤트 변환
    평점 4~5   상세를 보고 섹션을 읽고 **담는다** (긍정. v_u+ 로 간다)
    평점 3      상세는 보되 담지 않는다 (중립)
    평점 1~2    얕게 보고 빠르게 나간다. 소량의 부정 신호 (v_u- 로 간다)
    is_recommended=False 는 한 단계 낮춰 본다

누출 방지
    - target 상품에 대한 **그 사용자의 모든 리뷰**는 재생하지 않는다.
      (같은 상품을 앞서 리뷰한 적이 있으면 그것까지 뺀다)
    - target 이후 시점의 리뷰도 재생하지 않는다.
    - target 은 정답이므로 추천 후보에서 빼지 않는다. seed 상품만 뺀다.

실행
    python batch/jobs/eval_review_replay.py --split valid
    python batch/jobs/eval_review_replay.py --split test
"""
import argparse
import json
import os
import sys

import numpy as np

# 콘솔이 cp949 면 "—" 나 "⚠️" 에서 UnicodeEncodeError 로 죽는다.
# 하필 CF 경고문이 그 문자를 쓰므로, 경고를 못 보고 죽는 일이 생긴다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from eval_metadata import load as load_metadata              # noqa: E402
from persona_feature import load as load_affinity            # noqa: E402
from persona_split import select as select_split             # noqa: E402
from product_encoder import Encoder, brand_key               # noqa: E402
from ltr_features import LtrFeatures, load_ltr, weighted_from_meta  # noqa: E402
from recommender import (load_cooc, cf_bonus,
                        BRAND_W, LAMBDA, LAMBDA_MMR,        # noqa: E402
                         Recommender, brand_match, schedule_for)
from user_vector import UserVector                           # noqa: E402

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
K = 10
POSITIVE = 4        # 이 점수 이상이면 긍정
NEGATIVE = 2        # 이 점수 이하면 부정
SECTIONS = ("about_product", "ingredients", "reviews", "how_to_use")


def ordered_reviews(persona, index):
    """시간순. 상품 목록에 없는 리뷰는 버린다"""
    rows = [r for r in persona.get("reviews", []) if r.get("group_id") in index]
    return sorted(rows, key=lambda r: str(r.get("submission_time") or ""))


def split_history(persona, index):
    """(재생할 리뷰, target). **정의는 eval_metadata.py 한 곳에만 둔다.**

    metadata 가 정한 seed 상품에 해당하는 리뷰만 시간순으로 재생한다. 예전에는
    이 파일이 자체 기준으로 target 을 골랐고, 다른 축과 8.0% 가 어긋났다.
    """
    row = persona.get("_meta") or {}
    seeds = set(row.get("seed_product_ids", []))
    target = row.get("target_product_id")
    if not seeds or target not in index:
        return None, None
    history = [r for r in ordered_reviews(persona, index)
               if r["group_id"] in seeds]
    return history, target


# 긍정 리뷰를 어떤 전환 이벤트로 재생하나 (Jira 320 실험). 리뷰 이력은 구매 이력이라
# `purchase`(8.0) 가 뜻에 맞지만, 지금까지의 수치는 전부 `add_to_cart`(3.0) 로 재생한 값이다.
POSITIVE_EVENT = "add_to_cart"


def events_for(review):
    """리뷰 한 건 -> 이벤트. 부족한 UI 이벤트만 보강한다"""
    gid = review["group_id"]
    rating = review.get("rating") or 0
    recommended = review.get("is_recommended")
    if recommended is False and rating >= POSITIVE:
        rating -= 1                      # 별점은 높은데 추천은 안 한 경우

    def ev(name, **props):
        return {"event_name": name, "product_id": gid, "properties": props}

    out = [ev("product_view")]
    if rating >= POSITIVE:
        out += [ev("section_dwell", section_id=s, dwell_ms=8000) for s in SECTIONS]
        out.append(ev("scroll_depth", depth_percent=100))
        out.append(ev("wishlist_toggle", action="add"))
        out.append(ev(POSITIVE_EVENT))   # 리뷰를 썼다는 것은 샀다는 뜻이다
    elif rating > NEGATIVE:
        out += [ev("section_dwell", section_id=s, dwell_ms=4000)
                for s in SECTIONS[:2]]
        out.append(ev("scroll_depth", depth_percent=50))
    else:
        out.append(ev("section_dwell", section_id=SECTIONS[0], dwell_ms=1200))
        out.append(ev("scroll_depth", depth_percent=25))
        out.append(ev("scroll_backtrack"))
    return out


def served_top(scores, blocked, recommender, k=K, lam_mmr=LAMBDA_MMR):
    masked = scores.copy()
    for i in blocked:
        masked[i] = -np.inf
    order = [int(i) for i in np.argsort(-masked)[:k * 3] if np.isfinite(masked[i])]
    return recommender.mmr(masked, order, k, lam_mmr)


def run_persona(persona, history, target, ctx):
    M, index, prior, affinity, recommender = ctx
    state = UserVector()
    for review in history:
        for event in events_for(review):
            state.observe(event)

    vp, vn = state.vectors(index, M)
    w1, w2, w3 = schedule_for(len(state.viewed))
    scores = np.zeros(len(M), dtype=np.float32)
    if vp is not None:
        scores += w1 * (M @ vp.astype(np.float32))
    if vn is not None:
        scores -= LAMBDA * (M @ vn.astype(np.float32))
    if recommender.brands is not None:            # brand 관계 항
        rows = [index[g] for g in state.converted if g in index]
        bm = brand_match(recommender.brands, rows,
                         recommender.known_brands) if rows else None
        if bm is not None:
            scores = scores + BRAND_W * bm
    scores += w2 * affinity(persona) + w3 * prior

    # seed(재생한 상품)는 후보에서 뺀다. target 은 정답이라 빼지 않는다
    blocked = {index[r["group_id"]] for r in history}
    blocked.discard(index[target])

    # 학습 결합이 켜져 있으면 **위 선형 합을 통째로 대체**한다 (계약 §5 처리 4단계).
    # 시드는 서빙과 같게 전환한 상품을 쓴다.
    if recommender.ltr is not None and recommender.ltr_feat is not None:
        cand = np.ones(len(M), bool)
        cand[list(blocked)] = False
        pos, _neg = state.weights()
        gs = [g for g in pos if g in index] or [g for g in state.converted if g in index]
        rows = [index[g] for g in gs]
        if rows:
            sw = [pos.get(g, 1.0) for g in gs]                          # 실제 이벤트 가중치 (Jira 322)
            scores = recommender.ltr.predict_proba(
                recommender.ltr_feat.make(persona, rows, cand, seed_weights=sw))[:, 1].astype(np.float32)
        top = served_top(scores, blocked, recommender)
        masked = scores.copy()
        for i in blocked:
            masked[i] = -np.inf
        target_i = index[target]
        rank = int((masked > masked[target_i]).sum()) + 1
        return {"hit": target_i in top, "rank": rank,
                "n_seed": len(blocked), "n_converted": len(state.converted),
                "n_negative": len(state.viewed) - len(state.converted)}

    # CF 가점 — 서빙과 같게 **전환한 상품**을 쓴다.
    # 이 축은 이벤트를 실제로 재생하므로 state.converted 가 채워져 있다.
    if recommender.cooc is not None:
        cand = np.ones(len(M), bool)
        cand[list(blocked)] = False
        rows = [index[g] for g in state.converted if g in index]
        cfb = cf_bonus(recommender.cooc, rows, cand, recommender.supporters)
        if cfb is not None:
            scores = scores + recommender.cf_beta * cfb
    top = served_top(scores, blocked, recommender)
    masked = scores.copy()
    for i in blocked:
        masked[i] = -np.inf
    target_i = index[target]
    rank = int((masked > masked[target_i]).sum()) + 1
    return {"hit": target_i in top, "rank": rank,
            "n_seed": len(blocked), "n_converted": len(state.converted),
            "n_negative": len(state.viewed) - len(state.converted)}


def main():
    ap = argparse.ArgumentParser()
    # CF 가점은 **채택됐다** (2026-09-07). 기본이 켬이고 끄려면 --no-cf 다.
    # 산출물이 없으면 조용히 꺼지지 않고 경고를 찍는다 — 조용히 꺼지면
    # "CF 를 켰다고 생각한 수치" 가 사실은 CBF 값이 된다.
    ap.add_argument("--no-cf", dest="cf", action="store_false", default=True,
                    help="CF 가점을 끈다 (CBF 단독 · 옛 수치 재현용)")
    ap.add_argument("--no-ltr", dest="ltr", action="store_false", default=True,
                    help="학습 결합을 끄고 선형 결합으로 돈다 (옛 수치 재현용)")
    ap.add_argument("--split", choices=("train", "valid", "test", "all",
                                        "holdout_a", "holdout_b", "holdout_c"),
                    default="valid")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--positive-event", choices=("add_to_cart", "purchase"), default="add_to_cart",
                    help="긍정 리뷰를 재생할 전환 이벤트. purchase 는 log.ts 가중치 8.0 (Jira 320 실험)")
    a = ap.parse_args()
    global POSITIVE_EVENT
    POSITIVE_EVENT = a.positive_event
    print(f"긍정 리뷰 재생 이벤트: {POSITIVE_EVENT}")

    encoder = Encoder()
    M = np.asarray(encoder.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(encoder.products)}
    prior = np.asarray(encoder.prior(), dtype=np.float32)
    affinity = load_affinity(index)
    cooc, supporters = load_cooc() if a.cf else (None, None)
    if a.cf and cooc is None:
        print("⚠️ CF 가점이 켜져 있는데 item_cooc.npz 가 없습니다 — "
              "CBF 단독으로 돕니다. `python batch/jobs/build_cooc.py` 를 먼저 도십시오")
    elif a.cf:
        print("CF 가점 켬 (β=1.0 · 가점 전용)")
    else:
        print("CF 가점 끔 — CBF 단독")
    ltr = load_ltr() if a.ltr else None
    if a.ltr and ltr is None:
        print("⚠️ 학습 결합이 켜져 있는데 ltr_model.pkl 이 없습니다 — "
              "선형으로 돕니다. `python batch/jobs/train_ltr.py` 를 먼저 도십시오")
    elif a.ltr:
        print(f"학습 결합 켬 (트리 {ltr[1]['n_trees']}개)")
    else:
        print("학습 결합 끔 — 선형 결합")
    recommender = Recommender(M, index, prior, affinity=affinity,
                              brands=[brand_key(p) for p in encoder.products],
                              known_brands=set(encoder.blk["brand"]["vocab"]),
                              cooc=cooc, supporters=supporters,
                              ltr=None if ltr is None else ltr[0],
                              ltr_feat=None if ltr is None else LtrFeatures(
                                  encoder, M, prior, affinity, cooc, supporters,
                                  weighted=weighted_from_meta(ltr[1])))
    ctx = (M, index, prior, affinity, recommender)

    # 홀드아웃은 페르소나 파일도 정본 파일도 따로다 (부록 Q)
    if a.split.startswith("holdout_"):
        tag = a.split.split("_")[1]
        ppath = os.path.join(ROOT, "simulator", "personas", "data",
                             f"personas_holdout_{tag}.json")
        mpath = os.path.join(ROOT, "batch", "ingest", "data",
                             f"eval_metadata_holdout_{tag}.jsonl")
        meta_rows = load_metadata(path=mpath, split=a.split)
    else:
        ppath, meta_rows = PERSONAS, load_metadata(split=a.split)
    profiles = {p["persona_id"]: p
                for p in json.load(open(ppath, encoding="utf-8"))}
    personas = [dict(profiles[r["persona_id"]], _meta=r)
                for r in meta_rows if r["persona_id"] in profiles]
    if a.limit:
        personas = personas[:a.limit]
    print(f"**{a.split}** 집합 {len(personas):,}명 ·"
          f" 리뷰를 시간순 이벤트로 재생")
    if a.split == "test":
        print("  ⚠ test 는 최종 보고용이다")

    results, skipped = [], 0
    for persona in personas:
        history, target = split_history(persona, index)
        if not target or not history:
            skipped += 1
            continue
        results.append(run_persona(persona, history, target, ctx))

    hits = np.array([r["hit"] for r in results])
    ranks = np.array([r["rank"] for r in results])
    ndcg = np.where(ranks <= K, 1.0 / np.log2(ranks + 1), 0.0)
    rng = np.random.default_rng(42)
    boot = rng.integers(0, len(hits), (300, len(hits)))
    ci = np.percentile(hits[boot].mean(axis=1) * 100, [2.5, 97.5])

    print(f"\n평가 {len(results):,}명 (재생할 리뷰가 없어 제외 {skipped:,}명)")
    print(f"  Recall@10   {hits.mean() * 100:6.2f}%   CI [{ci[0]:.2f}, {ci[1]:.2f}]")
    print(f"  MRR         {np.mean(1.0 / ranks):6.4f}")
    print(f"  NDCG@10     {ndcg.mean():6.4f}")
    print(f"  target 순위 중앙 {np.median(ranks):.0f}위 · 상위 25% {np.percentile(ranks, 25):.0f}위")
    print(f"  재생 리뷰   1인당 {np.mean([r['n_seed'] for r in results]):.1f}개"
          f" (전환 {np.mean([r['n_converted'] for r in results]):.1f}"
          f" / 비전환 {np.mean([r['n_negative'] for r in results]):.1f})")


if __name__ == "__main__":
    main()
