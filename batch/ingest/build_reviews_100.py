"""
상품당 리뷰 100건 층화 추출 (2026-09-10).

입력
    <SEPHORA_DATASET>/reviews_*.csv             원천 리뷰 (4속성 전부 채워진 행만 쓴다)
    batch/ingest/data/products_200.json         대표 product_id <- member_product_ids 조인
    frontend/src/mocks/products.sample.json     화면 별점 product.rating (소수 2자리) -- 맞출 목표
    frontend/src/mocks/reviews.sample.json      기존 10건. 칸(별점x피부타입)에 맞으면 우선 채택 (번역 재사용)
출력  --out 폴더
    reviews_en_100/{product_id}.json            상품별 100건, reviews.sample.json 과 같은 스키마
    reviews_en_100_all.json                     위를 합친 20,000건
    for_translation/{product_id}.json           review_id, review_title, review_text 만 (번역용)
    verify_report.csv / verify_report.md        상품별 원본 대비 검증

규칙
    1) 별점(1~5)별 개수: 원천 비율로 100건을 나눈 뒤, 평균이 product.rating 과 +-0.005 안에 들도록
       한 건씩 옆 별점으로 옮긴다. 옮긴 건수를 리포트에 적는다.
    2) 각 별점 안에서 리뷰어 skin_type(combination/dry/normal/oily) 을 원천 비율(최대잉여법)로 배분.
    3) 제약: 화면 파생 "어울리는 피부타입"(비율 >= 0.20) 집합이 원천과 같고, 추천율 편차 <= 0.05.
       만족할 때까지 시드를 바꿔 다시 뽑는다 (최대 80회).
    4) 본문 없는 리뷰는 뽑지 않는다.
"""
import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DS = os.environ.get("SEPHORA_DATASET", r"C:\Users\SSAFY\Desktop\Research\dataset\sephora")
UF = ["skin_type", "skin_tone", "eye_color", "hair_color"]
ST = ["combination", "dry", "normal", "oily"]
STARS = np.array([1, 2, 3, 4, 5])
N = 100
SHARE_MIN = 0.20          # frontend lib/format.ts SKIN_TYPE_MIN_SHARE
REC_TOL = 0.05
TONE_BUCKET = {"porcelain": "fair", "fair": "fair", "fairLight": "fair", "light": "light", "lightMedium": "light",
               "medium": "medium", "mediumTan": "medium", "olive": "medium", "tan": "tan", "deep": "deep",
               "rich": "deep", "dark": "deep", "ebony": "deep"}

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--seed", type=int, default=306)
A = ap.parse_args()
os.makedirs(os.path.join(A.out, "reviews_en_100"), exist_ok=True)
os.makedirs(os.path.join(A.out, "for_translation"), exist_ok=True)

prods = json.load(open(os.path.join(ROOT, "batch/ingest/data/products_200.json"), encoding="utf-8"))
pid2group = {}
for p in prods:
    pid2group[p["product_id"]] = p["product_id"]
    for m in (p.get("_merged") or {}).get("member_product_ids", []):
        pid2group[m] = p["product_id"]
site = {p["product_id"]: p for p in
        json.load(open(os.path.join(ROOT, "frontend/src/mocks/products.sample.json"), encoding="utf-8"))}
existing = pd.DataFrame(json.load(open(os.path.join(ROOT, "frontend/src/mocks/reviews.sample.json"), encoding="utf-8")))
existing_ids = set(existing.review_id)

parts = []
for path in sorted(glob.glob(os.path.join(DS, "reviews_*.csv"))):
    d = pd.read_csv(path, low_memory=False)
    d = d[d.product_id.isin(pid2group)]
    d = d[d[UF].notna().sum(axis=1) == 4].copy()
    tag = os.path.basename(path).replace("reviews_", "").replace(".csv", "")
    d["review_id"] = "RV-" + tag + "-" + d["Unnamed: 0"].astype(str).str.zfill(6)
    parts.append(d)
r = pd.concat(parts, ignore_index=True)
r["group_id"] = r.product_id.map(pid2group)
r["skin_tone_raw"] = r.skin_tone
r["skin_tone"] = r.skin_tone.map(TONE_BUCKET).fillna(r.skin_tone)
r["rec"] = r.is_recommended.fillna(0).astype(float)
print(f"원천 4속성 리뷰 {len(r):,}건 / 상품 {r.group_id.nunique()}")
pool = r[r.review_text.notna() & (r.review_text.astype(str).str.strip() != "") & r.skin_type.isin(ST)]
print(f"본문 있고 skin_type 4종인 풀 {len(pool):,}건 (제외 {len(r) - len(pool):,})")


def star_quota(hist, target, n):
    q = np.round(hist * n).astype(int)
    while q.sum() > n:
        q[np.argmax(q)] -= 1
    while q.sum() < n:
        q[np.argmax(hist)] += 1
    moved = 0
    for _ in range(2000):
        m = (q * STARS).sum() / n
        if abs(m - target) < 0.005:
            return q, moved
        if m < target:
            i = [i for i in range(4) if q[i] > 0][0]
            q[i] -= 1
            q[i + 1] += 1
        else:
            i = [i for i in range(4, 0, -1) if q[i] > 0][0]
            q[i] -= 1
            q[i - 1] += 1
        moved += 1
    return q, moved


def largest_remainder(shares, n):
    raw = shares * n
    q = np.floor(raw).astype(int)
    rem = raw - q
    for i in np.argsort(-rem)[: n - q.sum()]:
        q[i] += 1
    return q


rng = np.random.default_rng(A.seed)
rows, all_out = [], []
for pid, sp in site.items():
    src = r[r.group_id == pid]                         # 원천 통계는 본문 없는 것까지 포함한 전체
    pl = pool[pool.group_id == pid]
    target = round(float(sp["rating"]), 2)
    hist = src.rating.value_counts(normalize=True).reindex(STARS, fill_value=0).values
    q, moved = star_quota(hist, target, N)
    skin_share = src.skin_type.value_counts(normalize=True).reindex(ST, fill_value=0).values
    src_set = set(np.array(ST)[skin_share >= SHARE_MIN])
    src_rec = src.rec.mean()
    # 칸 행렬 M[별점][피부타입]. 별점 개수 q 는 고정, 그 안에서 피부타입을 원천 비율로.
    M = np.array([largest_remainder(skin_share, qs) if qs > 0 else np.zeros(4, int) for qs in q])
    avail = np.array([[int(((pl.rating == s) & (pl.skin_type == st)).sum()) for st in ST] for s in STARS])
    # 파생 집합(비율 >= 0.20) 경계 보정: 총합이 원천과 다른 쪽에 떨어진 타입은 같은 별점 줄 안에서 한 건씩 옮긴다.
    skin_moved = 0
    for _ in range(20):
        T = M.sum(0)
        bad = [j for j in range(4) if (T[j] >= N * SHARE_MIN) != (skin_share[j] >= SHARE_MIN)]
        if not bad:
            break
        j = bad[0]
        need_up = skin_share[j] >= SHARE_MIN
        # 상대 타입: 자기 요구량 대비 여유가 가장 큰 쪽(올릴 때) / 원천 비율이 가장 큰 쪽(내릴 때)
        others = [u for u in range(4) if u != j]
        if need_up:
            slack = [(T[u] - (N * SHARE_MIN if skin_share[u] >= SHARE_MIN else 0), u) for u in others]
            u = max(slack)[1]
            cand = [s for s in range(5) if M[s][u] > 0 and avail[s][j] > M[s][j]]
            if not cand:
                break
            s = max(cand, key=lambda s: M[s][u])
            M[s][u] -= 1
            M[s][j] += 1
        else:
            u = max(others, key=lambda u: skin_share[u])
            cand = [s for s in range(5) if M[s][j] > 0 and avail[s][u] > M[s][u]]
            if not cand:
                break
            s = max(cand, key=lambda s: M[s][j])
            M[s][j] -= 1
            M[s][u] += 1
        skin_moved += 1
    best, best_score, best_attempt = None, 1e9, 0
    for attempt in range(80):
        picked = []
        for si, s in enumerate(STARS):
            cell = pl[pl.rating == s]
            for st, k in zip(ST, M[si]):
                if k <= 0:
                    continue
                c = cell[cell.skin_type == st]
                if len(c) < k:
                    raise SystemExit(f"{pid} 칸 부족 {s}점 {st}: 필요 {k} 있음 {len(c)}")
                take = c[c.review_id.isin(existing_ids)].head(k)
                rest = c[~c.review_id.isin(take.review_id)]
                if len(take) < k:
                    take = pd.concat([take, rest.sample(k - len(take), random_state=int(rng.integers(2 ** 31)))])
                picked.append(take)
        out = pd.concat(picked)
        out_share = out.skin_type.value_counts(normalize=True).reindex(ST, fill_value=0).values
        out_set = set(np.array(ST)[out_share >= SHARE_MIN])
        rec_diff = out.rec.mean() - src_rec
        score = (0 if out_set == src_set else 10) + abs(rec_diff)
        if score < best_score:
            best, best_score, best_attempt = out, score, attempt
        if out_set == src_set and abs(rec_diff) <= REC_TOL:
            break
    out = best.sort_values("submission_time", ascending=False)
    assert len(out) == N and abs(out.rating.mean() - target) < 0.005
    recs = []
    for x in out.itertuples():
        recs.append({
            "review_id": x.review_id, "product_id": pid, "author_id": str(x.author_id), "rating": int(x.rating),
            "is_recommended": (None if pd.isna(x.is_recommended) else bool(x.is_recommended)),
            "review_title": (None if pd.isna(x.review_title) else str(x.review_title)),
            "review_text": str(x.review_text), "submission_time": str(x.submission_time),
            "skin_type": x.skin_type, "skin_tone": x.skin_tone, "eye_color": x.eye_color, "hair_color": x.hair_color,
        })
    with open(os.path.join(A.out, "reviews_en_100", f"{pid}.json"), "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(A.out, "for_translation", f"{pid}.json"), "w", encoding="utf-8") as f:
        json.dump([{"review_id": x["review_id"], "review_title": x["review_title"], "review_text": x["review_text"]}
                   for x in recs], f, ensure_ascii=False, indent=1)
    all_out += recs
    out_share = out.skin_type.value_counts(normalize=True).reindex(ST, fill_value=0).values
    rows.append(dict(
        product_id=pid, product_name=sp["product_name"], site_rating=target, src_n=len(src),
        src_mean=round(src.rating.mean(), 3), out_mean=round(out.rating.mean(), 2), stars_moved=moved,
        star_tv=round(np.abs(q / N - hist).sum() / 2, 3), skin_tv=round(np.abs(out_share - skin_share).sum() / 2, 3),
        derived_skin_match=set(np.array(ST)[out_share >= SHARE_MIN]) == src_set,
        src_rec=round(src_rec, 3), out_rec=round(out.rec.mean(), 3),
        reused_existing=int(out.review_id.isin(existing_ids).sum()), attempts=best_attempt + 1, skin_moved=skin_moved,
        **{f"q{s}": int(k) for s, k in zip(STARS, q)}))

with open(os.path.join(A.out, "reviews_en_100_all.json"), "w", encoding="utf-8") as f:
    json.dump(all_out, f, ensure_ascii=False)
t = pd.DataFrame(rows)
t.to_csv(os.path.join(A.out, "verify_report.csv"), index=False, encoding="utf-8-sig")
dr = (t.out_rec - t.src_rec).abs()
md = [f"# 리뷰 100건 추출 검증 ({pd.Timestamp.today():%Y-%m-%d})", "",
      f"- 상품 200 · 리뷰 {len(all_out):,}건 · 원천 풀 {len(pool):,}건(본문 있음)",
      f"- 평균 = 화면 별점(소수 2자리) 일치: **{int((t.out_mean == t.site_rating).sum())}/200**",
      f"- 별점 축 조정(옆 별점으로 옮긴 건수): 평균 {t.stars_moved.mean():.2f}건, 최대 {t.stars_moved.max()}건, "
      f"0건인 상품 {int((t.stars_moved == 0).sum())}",
      f"- 별점 분포 어긋남(총변동): 평균 {t.star_tv.mean():.3f}, 최대 {t.star_tv.max():.3f}",
      f"- 피부타입 분포 어긋남(총변동): 평균 {t.skin_tv.mean():.3f}, 최대 {t.skin_tv.max():.3f}",
      f"- 화면 파생 '어울리는 피부타입' 집합 원천과 동일: **{int(t.derived_skin_match.sum())}/200** (경계 보정으로 옮긴 건수 합 {int(t.skin_moved.sum())}, 해당 상품 {int((t.skin_moved > 0).sum())})",
      f"- 추천율 편차 |out-src|: 평균 {dr.mean():.3f}, 최대 {dr.max():.3f}, 0.05 초과 {int((dr > 0.05).sum())}",
      f"- 기존 10건 재사용: {int(t.reused_existing.sum()):,}/2,000건", "", "상품별 표: verify_report.csv"]
with open(os.path.join(A.out, "verify_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")
print("\n".join(md))
