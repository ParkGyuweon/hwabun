"""
페르소나 자아 도출 — 리뷰 텍스트에서 "무엇을 신경 쓰는가"를 뽑는다

배경 (BEHAVIOR_SCENARIO.md 10-7절)
    페르소나마다 행동이 달라야 로그가 현실적인데, 그 차이의 근거를 지어내면 안 된다.
    미사용 자원이 하나 있다 — 리뷰 텍스트. 그 사람이 실제로 쓴 말이다.

방법
    관심 축을 zero-shot 으로 정의하고(SBERT), 각 페르소나의 리뷰를 그 축에 투영한다.
    concern_discovery_poc.py 에서 실제로 나온 군집을 축으로 삼았다.

⚠️ 순환 주의 — 자아는 "어떻게 보는가"만 결정한다
    ❌ "성분 민감하니 성분 좋은 상품을 고르게 하자"
         -> 추천도 ingredient 블록으로 맞힘. 자기가 심은 답을 채점
    ✅ "성분 민감하니 ingredients 섹션을 오래 보고 텍스트를 긁게 하자"
         -> 무엇을 고를지는 데이터(시드·목표)가 정함. 추천은 섹션 체류를 안 씀

    따라서 아래 축들은 전부 **행동 스타일**로만 매핑되고,
    어떤 상품을 보고 담을지에는 관여하지 않는다.

출력
    simulator/personas/data/persona_style.json   { persona_id: {축: 0~1 점수, ...} }

⚠️ 페르소나 파일(personas_9900.json / personas_100_agent.json)에서 파생된다.
   build_personas.py 를 다시 돌렸으면 이 스크립트도 반드시 다시 돌려야 한다.

실행
    python build_persona_style.py
    python build_persona_style.py --limit 200 --show 12
"""
import argparse, json, os, sys, time
import numpy as np

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
# 페르소나 파일과 성향 파일은 같은 폴더에 둔다 (simulator/personas/data)
ART = os.path.join(ROOT, "simulator", "personas", "data")
OUT = os.path.join(ART, "persona_style.json")

# concern_discovery_poc.py 의 k=35 군집에서 실제로 나온 축을 골랐다.
# 값은 그 축을 대표하는 표현이고, 리뷰를 이 문장들과의 코사인으로 채점한다.
AXES = {
    "ingredient":  "the ingredient list, niacinamide hyaluronic acid retinol, actives and formulation, fragrance free non comedogenic",
    "price":       "worth the price, expensive but worth every penny, overpriced for what it is, affordable dupe, repurchase again",
    "texture":     "the texture is creamy lightweight silky, absorbs quickly, sticky greasy residue, thick and heavy on skin",
    "scent":       "the scent is strong overpowering perfume, light fresh smell, fragrance bothers me",
    "sensitivity": "my sensitive skin did not react, no irritation or burning, gentle and calming, broke me out",
    "review_lean": "read the reviews before buying, reviews were right, hype and recommendations, tried it because of ratings",
}

# 축 -> 행동 스타일 보정 (곱셈 계수). "무엇을 고르는가"에는 절대 관여하지 않는다.
STYLE_EFFECT = {
    "ingredient":  {"p_accordion": 1.6, "p_text_selection": 2.0, "dwell_boost_ingredients": 2.0},
    "price":       {"p_variant_select": 1.8, "dwell_boost_product_hero": 1.5},
    "texture":     {"p_scroll_pause": 1.3, "dwell_boost_about_product": 1.4},
    "scent":       {"dwell_boost_about_product": 1.3, "p_text_selection": 1.3},
    "sensitivity": {"p_accordion": 1.5, "dwell_boost_ingredients": 1.8, "p_scroll_backtrack": 1.4},
    "review_lean": {"p_review_filter": 1.8, "dwell_boost_reviews": 2.0},
}


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main(limit, show):
    from sentence_transformers import SentenceTransformer
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"SBERT 로드 (device={dev})")
    model = SentenceTransformer("all-MiniLM-L6-v2", device=dev)

    names = list(AXES)
    Q = model.encode([AXES[k] for k in names], convert_to_numpy=True,
                     normalize_embeddings=True)

    P = json.load(open(os.path.join(ART, "personas_9900.json"), encoding="utf-8"))
    A = json.load(open(os.path.join(ART, "personas_100_agent.json"), encoding="utf-8"))
    people = (P + A) if not limit else (P[:limit] + A[:5])
    log(f"페르소나 {len(people):,}명")

    # 페르소나별 리뷰 텍스트를 하나로 합쳐 임베딩
    texts, ids = [], []
    for p in people:
        t = " ".join((r.get("review_text") or "")[:600] for r in p["reviews"])
        texts.append(t.strip() or "no review text")
        ids.append(p["persona_id"])

    t0 = time.time()
    E = model.encode(texts, batch_size=256, convert_to_numpy=True,
                     normalize_embeddings=True, show_progress_bar=True)
    log(f"임베딩 {E.shape} — {time.time()-t0:.1f}초")

    S = E @ Q.T                                   # (N, 축수) 코사인
    # 축별로 표준화 후 0~1 로 눌러 담는다. 축 간 스케일 차이를 없애기 위함
    S = (S - S.mean(0)) / (S.std(0) + 1e-9)
    S = 1 / (1 + np.exp(-S))                      # 시그모이드

    style = {pid: {k: round(float(v), 3) for k, v in zip(names, row)}
             for pid, row in zip(ids, S)}
    json.dump(style, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"저장 {OUT}  ({os.path.getsize(OUT)/1024:.0f}KB)")

    print("\n" + "=" * 66)
    print("축별 분포 (0~1)")
    print("=" * 66)
    for i, k in enumerate(names):
        c = S[:, i]
        print(f"  {k:<14} 평균 {c.mean():.3f}  p10 {np.percentile(c,10):.3f}  "
              f"p90 {np.percentile(c,90):.3f}")

    if show:
        print("\n" + "=" * 66)
        print(f"페르소나 샘플 — 가장 두드러진 축 표시")
        print("=" * 66)
        for pid, row in list(style.items())[:show]:
            top = sorted(row.items(), key=lambda x: -x[1])[:2]
            tags = " · ".join(f"{k} {v:.2f}" for k, v in top)
            print(f"  {pid}  {tags}")

    # 축 간 상관 — 하나로 뭉치면 축을 나눈 의미가 없다
    print("\n축 간 상관 (0.8 넘으면 사실상 같은 축)")
    C = np.corrcoef(S.T)
    hi = [(names[i], names[j], C[i, j]) for i in range(len(names))
          for j in range(i + 1, len(names)) if abs(C[i, j]) > 0.5]
    if hi:
        for a, b, v in sorted(hi, key=lambda x: -abs(x[2])):
            print(f"  {a} ~ {b}  {v:+.2f}")
    else:
        print("  0.5 넘는 쌍 없음")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()
    main(a.limit, a.show)
