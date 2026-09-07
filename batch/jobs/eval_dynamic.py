"""
동적 시뮬레이션 평가 — 행동이 쌓이는 동안 추천이 좋아지는가.

    seed 상태에서 시작해 5~6개 상품을 탐색한다.
    각 step 마다
        1. 지금 사용자 벡터로 추천 점수를 낸다
        2. **추천 점수는 노출 확률에만** 쓴다 — 후보 pool 에서 뽑을 때만
        3. 뽑힌 상품에 대한 행동은 **hidden preference** 가 정한다
        4. 그 행동을 이벤트로 만들어 사용자 벡터를 갱신한다
        5. target 이 Top 10 안에 들어왔는지 기록한다

**추천 순위로 행동을 만들고 그 행동으로 추천을 채점하는 순환 평가를 피하는 것이
이 구조의 목적이다.** 계약: docs/ai/evaluation-framework.md 2절

지표
    Start HR@10   탐색 전에 이미 Top 10 에 있었는가
    Final HR@10   마지막 step 후 Top 10 에 있는가
    Ever HR@10    탐색 중 한 번이라도 들어왔는가  (= Dynamic Recall@10)
    MRR / NDCG    target 이 얼마나 위에 있는가
    step별 HR@10  탐색이 진행될수록 좋아지는가
    rank 변화     시작 순위 대비 마지막 순위

**Ever HR@10 은 step 이 많아질수록 자연히 오른다.** 하나만 대표로 쓰지 않고
Start / Final / Ever 를 함께 본다.

실행
    python batch/jobs/eval_dynamic.py --split valid
    python batch/jobs/eval_dynamic.py --split test --noise-seed 1
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
from hidden_preference import (PROFILES, TEXT_EMBEDDING,      # noqa: E402
                               TEXT_LEXICAL, HiddenPreference)
from persona_feature import load as load_affinity            # noqa: E402
from persona_split import select as select_split             # noqa: E402
from product_encoder import Encoder                          # noqa: E402
from recommender import (BRAND_W, LAMBDA, LAMBDA_MMR,        # noqa: E402
                         Recommender, brand_match, schedule_for,
                         load_cooc, cf_bonus, CF_BETA)
from user_vector import UserVector                           # noqa: E402

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
K = 10
STEPS = 6
# 후보 pool 구성 — 추천 Top 만 보면 추천이 자기가 고른 것만 채점하게 된다
POOL_TOP = 50
POOL_MIX = {"top": 6, "category_popular": 3, "random": 3}


def seed_and_target(persona, index):
    """metadata 가 정한 seed / target 을 쓴다 (정의는 eval_metadata.py 한 곳)"""
    row = persona.get("_meta") or {}
    seeds = [g for g in row.get("seed_product_ids", []) if g in index]
    target = row.get("target_product_id")
    if not seeds or target not in index:
        return None, None
    return seeds, target


def events_for(product_id, pref, rng):
    """hidden preference -> 행동 이벤트. 계약 2절의 행동 변환 표를 그대로 옮긴다.

    이벤트를 만들어 UserVector 에 먹인다. 벡터를 직접 만지지 않는 이유는 서빙이
    쓰는 집계 규칙(상품x섹션 1건, 전환 상품만 v_u+, 관여 반비례 감점)을 그대로
    통과시켜야 평가가 실제 파이프라인과 같아지기 때문이다.
    """
    def ev(name, **props):
        return {"event_name": name, "product_id": product_id, "properties": props}

    out = [ev("product_view")]
    sections = ["about_product", "ingredients", "reviews", "how_to_use"]
    if pref >= 0.80:
        out += [ev("section_dwell", section_id=s, dwell_ms=9000) for s in sections]
        out.append(ev("scroll_depth", depth_percent=100))
        if rng.random() < 0.7:
            out.append(ev("wishlist_toggle", action="add"))
        if rng.random() < 0.75:
            out.append(ev("add_to_cart"))
    elif pref >= 0.60:
        out += [ev("section_dwell", section_id=s, dwell_ms=6000) for s in sections[:3]]
        out.append(ev("scroll_depth", depth_percent=75))
        if rng.random() < 0.3:
            out.append(ev("wishlist_toggle", action="add"))
        if rng.random() < 0.25:
            out.append(ev("add_to_cart"))
    elif pref >= 0.40:
        out += [ev("section_dwell", section_id=s, dwell_ms=4000) for s in sections[:2]]
        out.append(ev("scroll_depth", depth_percent=50))
    elif pref >= 0.20:
        out.append(ev("section_dwell", section_id=sections[0], dwell_ms=1500))
        out.append(ev("scroll_depth", depth_percent=25))
    else:
        out.append(ev("scroll_depth", depth_percent=25))
        if rng.random() < 0.2:
            out.append(ev("scroll_backtrack"))
        if rng.random() < 0.1:
            out.append(ev("rage_click"))
    return out


def candidate_pool(scores, visited, index_size, product_meta, target_category, rng):
    """추천 Top 일부 + 같은 카테고리/인기 일부 + 무작위 일부.

    target 을 후보로 강제하지 않는다. target 은 정답 holdout 으로만 둔다.
    """
    order = [int(i) for i in np.argsort(-scores) if i not in visited]
    pool = order[:POOL_TOP][:POOL_MIX["top"]]

    same_cat = [i for i in order
                if product_meta[i]["tertiary_category"] == target_category][:20]
    pool += list(rng.choice(same_cat, size=min(POOL_MIX["category_popular"],
                                               len(same_cat)), replace=False)) \
        if same_cat else []

    rest = [i for i in order if i not in pool]
    if rest:
        pool += list(rng.choice(rest, size=min(POOL_MIX["random"], len(rest)),
                                replace=False))
    return [int(i) for i in dict.fromkeys(pool)]


def rank_of_target(scores, target_i, blocked):
    masked = scores.copy()
    for i in blocked:
        masked[i] = -np.inf
    return int((masked > masked[target_i]).sum()) + 1


def served_top(scores, blocked, recommender, k=K, lam_mmr=LAMBDA_MMR):
    """실제로 화면에 나갈 목록. 노출 정책(seed 제외) + MMR 까지 통과시킨다.

    HR@10 은 "점수 상위 10" 이 아니라 **서빙 목록 상위 10** 으로 판정해야 한다.
    MMR 이 순서를 바꾸므로 둘이 다르다.
    """
    masked = scores.copy()
    for i in blocked:
        masked[i] = -np.inf
    order = [int(i) for i in np.argsort(-masked)[:k * 3] if np.isfinite(masked[i])]
    return set(recommender.mmr(masked, order, k, lam_mmr))


def run_persona(persona, seeds, target, ctx, rng):
    """한 사람의 탐색을 돌리고 step 별 target 순위를 돌려준다"""
    (M, index, prior, affinity, hp, recommender, meta, brands, known,
     cooc, supporters) = ctx
    state = UserVector()
    # seed 는 이미 좋아한 상품이다. 전환으로 넣고 후보에서 뺀다
    for gid in seeds:
        state.observe({"event_name": "add_to_cart", "product_id": gid,
                       "properties": {}})
    seed_idx = {index[g] for g in seeds}
    target_i = index[target]
    target_category = meta[target_i]["tertiary_category"]

    hidden = hp.score_all(persona, seeds)
    ranks, visited = [], set(seed_idx)
    stop_reason = "steps"

    def score_now():
        vp, vn = state.vectors(index, M)
        w1, w2, w3 = schedule_for(len(state.viewed))
        s = np.zeros(len(M), dtype=np.float32)
        if vp is not None:
            s += w1 * (M @ vp.astype(np.float32))
        if vn is not None:
            s -= LAMBDA * (M @ vn.astype(np.float32))
        # brand 관계 항 — 전환한 상품의 브랜드가 이 사람이 쓰던 브랜드다
        rows = [index[g] for g in state.converted if g in index]
        bm = brand_match(brands, rows, known) if rows else None
        if bm is not None:
            s = s + BRAND_W * bm
        s = s + w2 * affinity(persona) + w3 * prior
        # CF 가점 — 서빙과 같게 전환한 상품을 쓴다. 탐색이 쌓일수록 늘어난다
        if cooc is not None:
            cr = [index[g] for g in state.converted if g in index]
            cfb = cf_bonus(cooc, cr, None, supporters)
            if cfb is not None:
                s = s + CF_BETA * cfb
        return s

    scores = score_now()
    ranks.append(rank_of_target(scores, target_i, seed_idx))
    hits = [target_i in served_top(scores, seed_idx, recommender)]

    for _ in range(STEPS):
        pool = candidate_pool(scores, visited, len(M), meta, target_category, rng)
        if not pool:
            stop_reason = "no_candidate"
            break
        # 추천 점수는 여기서만 쓴다 — 무엇이 노출될지의 확률
        weights = np.exp(np.array([scores[i] for i in pool], dtype=np.float64) * 3.0)
        weights /= weights.sum()
        picked = int(rng.choice(pool, p=weights))
        visited.add(picked)

        pref = float(hidden[picked])
        for event in events_for(meta[picked]["product_id"], pref, rng):
            state.observe(event)

        scores = score_now()
        ranks.append(rank_of_target(scores, target_i, seed_idx))
        hits.append(target_i in served_top(scores, seed_idx, recommender))
        if picked == target_i:
            # target 을 직접 만난 뒤의 이벤트는 판정에 쓰지 않는다
            stop_reason = "target_visited"
            break

    return {"ranks": ranks, "hits": hits, "stop_reason": stop_reason,
            "n_converted": len(state.converted), "n_viewed": len(state.viewed)}


def summarize(results, label):
    ranks = [r["ranks"] for r in results]
    hitseq = [r["hits"] for r in results]
    start = np.array([r[0] for r in ranks])
    final = np.array([r[-1] for r in ranks])
    # HR 은 **서빙 목록**(노출 정책 + MMR 통과) 기준이고, 순위 지표는 점수 기준이다.
    # MMR 이 순서를 바꾸므로 "점수 상위 10" 과 "화면에 나가는 10" 은 다르다
    start_hit = np.array([h[0] for h in hitseq])
    final_hit = np.array([h[-1] for h in hitseq])
    ever_hit = np.array([any(h) for h in hitseq])

    print(f"\n[{label}] 페르소나 {len(results):,}명 · 최대 {STEPS} step")
    print(f"  Start HR@10   {start_hit.mean() * 100:6.2f}%   탐색 전")
    print(f"  Final HR@10   {final_hit.mean() * 100:6.2f}%   마지막 step 후")
    print(f"  Ever HR@10    {ever_hit.mean() * 100:6.2f}%   한 번이라도"
          f" (= Dynamic Recall@10)")
    print(f"  MRR           {np.mean(1.0 / final):6.4f}   마지막 순위 기준")
    ndcg = np.where(final <= K, 1.0 / np.log2(final + 1), 0.0)
    print(f"  NDCG@10       {ndcg.mean():6.4f}")
    print(f"  target 순위   시작 {np.median(start):.0f}위 -> 마지막 "
          f"{np.median(final):.0f}위 (중앙값)")
    improved = float((final < start).mean() * 100)
    worsened = float((final > start).mean() * 100)
    print(f"  순위 개선 {improved:.1f}% / 악화 {worsened:.1f}%"
          f" / 그대로 {100 - improved - worsened:.1f}%")

    depth = max(len(h) for h in hitseq)
    curve = []
    for step in range(depth):
        at = [h[step] if step < len(h) else h[-1] for h in hitseq]
        curve.append(float(np.mean(at) * 100))
    print("  step별 HR@10  " + " -> ".join(f"{v:.1f}" for v in curve))
    stops = {}
    for r in results:
        stops[r["stop_reason"]] = stops.get(r["stop_reason"], 0) + 1
    print(f"  종료 사유 {stops}")
    return {"start": float(start_hit.mean() * 100),
            "final": float(final_hit.mean() * 100),
            "ever": float(ever_hit.mean() * 100),
            "mrr": float(np.mean(1.0 / final)), "ndcg": float(ndcg.mean())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "valid", "test", "all"),
                    default="valid")
    # CF 가점은 **채택됐다** (2026-09-07). 기본이 켬이고 끄려면 --no-cf 다.
    ap.add_argument("--no-cf", dest="cf", action="store_false", default=True,
                    help="CF 가점을 끈다 (CBF 단독 · 옛 수치 재현용)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--noise-seed", type=int, default=0,
                    help="hidden preference 잡음 seed. 강건성 평가에서 바꿔 가며 돈다")
    ap.add_argument("--rng-seed", type=int, default=42, help="탐색 난수 seed")
    ap.add_argument("--embeddings", default=None,
                    help="임베딩 산출물 경로 (대안 산출물과 비교할 때)")
    ap.add_argument("--text-backend", choices=(TEXT_LEXICAL, TEXT_EMBEDDING),
                    default=None,
                    help="텍스트 매칭 방식. 기본은 임베딩 산출물이 있으면 embedding")
    ap.add_argument("--pref-profile", choices=tuple(PROFILES), default="default",
                    help="hidden preference 가중치 조합. 강건성 평가에서 바꿔 가며 돈다")
    a = ap.parse_args()

    encoder = Encoder()
    M = np.asarray(encoder.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(encoder.products)}
    prior = np.asarray(encoder.prior(), dtype=np.float32)
    affinity = load_affinity(index)
    recommender = Recommender(M, index, prior, affinity=affinity,
                              brands=[p["brand_name"] for p in encoder.products],
                              known_brands=set(encoder.blk["brand"]["vocab"]))
    hp = HiddenPreference(products=encoder.products, noise_seed=a.noise_seed,
                          weights=PROFILES[a.pref_profile],
                          text_backend=a.text_backend,
                          **({"embeddings_path": a.embeddings} if a.embeddings else {}))
    meta = [{"product_id": p["product_id"],
             "tertiary_category": p.get("tertiary_category")}
            for p in encoder.products]
    brands = [p["brand_name"] for p in encoder.products]
    known = set(encoder.blk["brand"]["vocab"])
    cooc, supporters = load_cooc() if a.cf else (None, None)
    if a.cf and cooc is None:
        print("⚠️ CF 가점이 켜져 있는데 item_cooc.npz 가 없습니다 — "
              "CBF 단독으로 돕니다")
    elif a.cf:
        print("CF 가점 켬 (β=1.0 · 가점 전용)")
    else:
        print("CF 가점 끔 — CBF 단독")
    ctx = (M, index, prior, affinity, hp, recommender, meta, brands, known,
           cooc, supporters)

    profiles = {p["persona_id"]: p
                for p in json.load(open(PERSONAS, encoding="utf-8"))}
    personas = [dict(profiles[r["persona_id"]], _meta=r)
                for r in load_metadata(split=a.split) if r["persona_id"] in profiles]
    if a.limit:
        personas = personas[:a.limit]

    print(f"**{a.split}** 집합 {len(personas):,}명 (PC 페르소나) ·"
          f" 상품 {len(M)}개")
    print(f"노출: 추천 점수 · 행동: hidden preference"
          f"({a.pref_profile}, {hp.text_backend}, seed {a.noise_seed})"
          f" · 탐색 seed {a.rng_seed}")
    if a.split == "test":
        print("  ⚠ test 는 최종 보고용이다")

    rng = np.random.default_rng(a.rng_seed)
    results = []
    for persona in personas:
        seeds, target = seed_and_target(persona, index)
        if not seeds:
            continue
        results.append(run_persona(persona, seeds, target, ctx, rng))
    summarize(results, f"{a.split} · {a.pref_profile} · noise {a.noise_seed}")


if __name__ == "__main__":
    main()
