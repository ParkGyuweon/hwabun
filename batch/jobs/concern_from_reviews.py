"""
리뷰 텍스트로 concern 블록을 채운다.

문제
    concern 은 8개 블록 중 가중치가 가장 큰데(0.42) 200개 중 44개가 비어 있고,
    나머지도 9차원에 평균 1.45개만 켜져 있다. 출처가 highlights 태그라서 그렇다.
    highlights 는 마케팅 문구라 "이 제품이 실제로 뭘 해결해주는가" 를 다 담지 못한다.

    반면 상품당 리뷰가 평균 2,291건 있다. 사람들이 직접 쓴 말이다.

방법
    9개 concern 축을 리뷰에서 쓰는 표현으로 정의하고(zero-shot),
    상품의 모든 리뷰를 임베딩해 축과의 코사인을 상품 단위로 평균한다.

⚠️ 누설
    페르소나의 시드·정답 리뷰도 이 상품 벡터에 들어간다.
    9,900명 x 약 3건 = 3만건으로 전체 54만건의 5.5% 이고,
    특정 상품 하나로 보면 그 사람 리뷰 1건 / 2,291건 = 0.04% 다.
    영향은 무시할 수준이지만 수치를 해석할 때 기억해 둘 것.

출력
    artifacts/concern_from_reviews.npz   { group_id, axes, score(상품 x 9) }
"""
import os, sys, time
import numpy as np
import pandas as pd

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
DATA = os.path.join(ROOT, "batch", "ingest", "data")
ART = os.environ.get("REVIEW_ART", DATA)      # 리뷰 원본은 개인 작업 폴더에 있을 수 있다
CACHE_EMB = os.path.join(ART, "review_emb_all.npy")
OUT = os.path.join(DATA, "concern_from_reviews.npz")

# 어휘집의 concern 9종. 각 축을 "리뷰에 실제로 나오는 말" 로 풀어 쓴다.
# 마케팅 문구가 아니라 사용자가 쓰는 표현이어야 임베딩이 붙는다.
AXES = {
 "Dullness/Uneven Texture":
   "my skin looks dull and tired, uneven skin tone and texture, gave me a glow, "
   "brightened my complexion, skin looks radiant and awake",
 "Dryness":
   "my skin is so dry and flaky, this is so hydrating and moisturizing, "
   "relieved the tightness, my dry patches are gone, deeply nourishing",
 "Anti-Aging":
   "fine lines and wrinkles look softer, anti aging results, my crow's feet, "
   "smoother skin over time, mature skin",
 "Pores":
   "my pores look smaller and less visible, minimizes large pores, "
   "blackheads on my nose, clogged pores, refines skin texture",
 "Loss of firmness":
   "skin feels firmer and tighter, lifted and more sculpted, sagging skin, "
   "lost elasticity, plumper and bouncier",
 "Dark Circles":
   "dark circles under my eyes, under eye bags and puffiness, "
   "brightened my under eye area, tired looking eyes",
 "Acne/Blemishes":
   "cleared up my acne and breakouts, pimples and blemishes, "
   "did not break me out, cystic acne, blemish prone skin",
 "Redness":
   "calmed the redness and irritation, my rosacea, soothing for sensitive skin, "
   "reduced inflammation, no stinging or burning",
 "Dark spots":
   "faded my dark spots and hyperpigmentation, acne scars and marks, "
   "evened out discoloration, sun spots and melasma",
}


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main(sample_per_product=None):
    df = pd.read_parquet(os.path.join(ART, "poc_concern_reviews.parquet"))
    import json
    prods = json.load(open(os.path.join(DATA, "products_200.json"), encoding="utf-8"))
    keep = {p["product_id"] for p in prods}
    df = df[df["group_id"].isin(keep)].reset_index(drop=True)
    if sample_per_product:
        df = (df.groupby("group_id", group_keys=False)
                .apply(lambda g: g.sample(min(len(g), sample_per_product), random_state=0))
                .reset_index(drop=True))
    log(f"리뷰 {len(df):,}건 / 상품 {df.group_id.nunique()}개")

    from sentence_transformers import SentenceTransformer
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"SBERT 로드 (device={dev})")
    m = SentenceTransformer("all-MiniLM-L6-v2", device=dev)

    names = list(AXES)
    Q = m.encode([AXES[k] for k in names], convert_to_numpy=True, normalize_embeddings=True)

    tag = f"{len(df)}"
    cache = CACHE_EMB.replace(".npy", f"_{tag}.npy")
    if os.path.exists(cache):
        log(f"임베딩 캐시 사용 {os.path.basename(cache)}")
        E = np.load(cache)
    else:
        t0 = time.time()
        E = m.encode(df["review_text"].astype(str).str[:512].tolist(),
                     batch_size=512, convert_to_numpy=True,
                     normalize_embeddings=True, show_progress_bar=True)
        log(f"임베딩 {E.shape} — {time.time()-t0:.0f}초")
        np.save(cache, E.astype(np.float32))

    S = E @ Q.T                                   # (리뷰수, 9)
    df_idx = df.groupby("group_id").indices
    gids = sorted(df_idx)
    P = np.vstack([S[df_idx[g]].mean(0) for g in gids])
    log(f"상품별 집계 {P.shape}")

    # 축별 표준화 — 축마다 코사인 스케일이 달라 그대로 쓰면 한 축이 지배한다
    Z = (P - P.mean(0)) / (P.std(0) + 1e-9)
    np.savez(OUT, group_id=np.array(gids, dtype=object),
             axes=np.array(names, dtype=object), score=Z.astype(np.float32),
             raw=P.astype(np.float32))
    log(f"저장 {OUT}")

    print("\n" + "=" * 74)
    print("축별 상위 상품 — 리뷰가 실제로 그 고민을 말하는가")
    print("=" * 74)
    name_of = {p["product_id"]: p["product_name"] for p in prods}
    for i, k in enumerate(names):
        top = np.argsort(-Z[:, i])[:3]
        print(f"\n{k}")
        for t in top:
            print(f"   {Z[t,i]:+.2f}  {name_of[gids[t]][:56]}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(n)
