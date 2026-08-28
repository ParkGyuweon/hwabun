"""
사람들은 다음 제품을 무엇을 기준으로 고르는가

리뷰에 author_id 와 submission_time 이 있어 같은 사람의 구매 순서를 복원할 수 있다.
연속한 두 상품(직전 -> 다음)이 무엇을 공유하는지 재고, 무작위 쌍과 비교한다.
lift = 실제 유지율 / 무작위 유지율.  1.0 이면 아무 상관 없다는 뜻이다.

이걸 알아야 추천 점수의 항과 가중치를 근거 있게 정할 수 있다.
"""
import os, sys, json
from collections import Counter, defaultdict
import numpy as np
import pandas as pd

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
# 리뷰 원본(54만건)은 용량 때문에 커밋하지 않는다. REVIEW_ART 로 경로를 준다
ART = os.environ.get("REVIEW_ART", os.path.join(ROOT, "batch", "ingest", "data"))
sys.path.insert(0, BD)
from product_encoder import Encoder


def main():
    e = Encoder()
    prods = {p["product_id"]: p for p in e.products}
    df = pd.read_parquet(os.path.join(ART, "poc_concern_reviews.parquet"))
    df = df[df["group_id"].isin(prods)].copy()
    df["t"] = pd.to_datetime(df["submission_time"], errors="coerce")
    df = df.dropna(subset=["t"]).sort_values(["author_id", "t"])

    # 같은 상품 재리뷰는 첫 건만
    df = df.drop_duplicates(["author_id", "group_id"], keep="first")
    g = df.groupby("author_id")["group_id"].apply(list)
    seqs = [s for s in g if len(s) >= 2]
    print(f"\n리뷰 {len(df):,}건 / 2개 이상 구매한 사람 {len(seqs):,}명 "
          f"/ 연속쌍 {sum(len(s)-1 for s in seqs):,}개")

    # ── 속성 추출 ─────────────────────────────────────────────────────────
    def feat(gid):
        p = prods[gid]
        t = e.split_tags(p)
        return {
            "brand": p["brand_name"],
            "secondary": p["secondary_category"],
            "tertiary": p["tertiary_category"],
            "price_bin": int(np.digitize(p["price_usd"], e.edges)),
            "concern": frozenset(t["concern"]),
            "clean": frozenset(t["clean"]),
            "ingredient": frozenset(e.ingredient_values(p)),
        }
    F = {gid: feat(gid) for gid in prods}
    ids = list(prods)

    def same(a, b, k):
        x, y = F[a][k], F[b][k]
        if isinstance(x, frozenset):
            return len(x & y) > 0
        return x == y

    KEYS = ["brand", "secondary", "tertiary", "price_bin", "concern", "clean", "ingredient"]

    pairs = [(s[i], s[i + 1]) for s in seqs for i in range(len(s) - 1)]
    rng = np.random.default_rng(0)
    rnd = [(ids[i], ids[j]) for i, j in
           rng.integers(0, len(ids), size=(len(pairs), 2))]

    print("\n" + "=" * 78)
    print("① 다음 제품을 고를 때 무엇이 유지되는가")
    print("=" * 78)
    print(f"{'속성':<14} {'실제 유지율':>11} {'무작위':>9} {'lift':>8}   해석")
    print("-" * 78)
    rows = []
    for k in KEYS:
        a = np.mean([same(x, y, k) for x, y in pairs]) * 100
        b = np.mean([same(x, y, k) for x, y in rnd]) * 100
        lift = a / b if b else 0
        rows.append((k, a, b, lift))
    for k, a, b, lift in sorted(rows, key=lambda r: -r[3]):
        bar = "█" * int(min(lift, 4) * 6)
        print(f"{k:<14} {a:10.1f}% {b:8.1f}% {lift:7.2f}x  {bar}")
    print("-" * 78)
    print("lift 1.0 = 무작위와 같음(그 속성은 선택에 관여 안 함)")

    # ── 최근 것 vs 전체 평균 ──────────────────────────────────────────────
    M = e.matrix(); idx = {p["product_id"]: i for i, p in enumerate(e.products)}
    print("\n" + "=" * 78)
    print("② 다음 상품은 '직전 것' 을 닮는가, '지금까지 전부' 를 닮는가")
    print("=" * 78)
    last, mean_all, first = [], [], []
    for s in seqs:
        if len(s) < 3: continue
        prev, nxt = s[:-1], s[-1]
        vn = M[idx[nxt]]
        last.append(float(M[idx[prev[-1]]] @ vn))
        v = M[[idx[x] for x in prev]].mean(0); v /= np.linalg.norm(v) + 1e-12
        mean_all.append(float(v @ vn))
        first.append(float(M[idx[prev[0]]] @ vn))
    print(f"  직전 1개와의 코사인      {np.mean(last):.4f}")
    print(f"  지금까지 전부의 평균     {np.mean(mean_all):.4f}   <- 현행 방식")
    print(f"  맨 처음 1개와의 코사인   {np.mean(first):.4f}")
    print(f"  (3개 이상 구매자 {len(last):,}명)")
    if np.mean(last) > np.mean(mean_all):
        print("  -> 최근 것이 더 강하다. 시간 감쇠를 넣을 근거가 된다")
    else:
        print("  -> 전체 평균이 낫다. 시간 감쇠는 근거가 약하다")

    # ── 카테고리 전이 ─────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("③ 카테고리 전이 — 무엇을 산 다음 무엇을 사는가")
    print("=" * 78)
    tr = defaultdict(Counter)
    for a, b in pairs:
        tr[F[a]["secondary"]][F[b]["secondary"]] += 1
    tot = Counter()
    for a, b in pairs: tot[F[a]["secondary"]] += 1
    print(f"{'직전 카테고리':<26} {'n':>6}  가장 흔한 다음 3개")
    print("-" * 78)
    for cat, c in tot.most_common(8):
        nxt = tr[cat].most_common(3)
        s = " · ".join(f"{k[:22]} {v/c*100:.0f}%" for k, v in nxt)
        print(f"{cat[:25]:<26} {c:6,}  {s}")
    print("-" * 78)
    rep = np.mean([F[a]["secondary"] == F[b]["secondary"] for a, b in pairs]) * 100
    print(f"같은 카테고리를 연속으로 사는 비율 {rep:.1f}%")


if __name__ == "__main__":
    main()
