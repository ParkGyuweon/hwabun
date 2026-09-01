"""
Product Feature 샘플 — 명세가 실제로 어떤 값을 만드는지 상품 6개로 보여준다.

    산출: batch/ingest/data/feature_sample.json
    문서: docs/ai/product-feature-sample.md (이 산출물을 읽고 쓴다)

왜 필요한가
    명세(contracts/product-feature-spec.md)만 읽으면 "그래서 이 상품은 몇이 되는가"
    를 알 수 없다. 블록별 원본값 -> L2 정규화 -> 블록 가중치까지 실제 숫자로 따라갈
    수 있어야 팀원이 인코딩을 검증할 수 있다.

고른 기준
    속성별 lift 극단 5개 + **같은 브랜드 형제 1개**.
    형제를 넣은 이유는 어휘집 0.4 에서 brand 블록(55차원, 가중치 0.60)이 들어왔기
    때문이다. 같은 브랜드끼리의 코사인과 다른 브랜드와의 코사인을 나란히 놓아야
    이 블록이 무엇을 하는지 보인다.

실행: python batch/ingest/build_feature_sample.py
"""
import csv
import json
import os
import sys

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
from persona_feature import AffinityTable, normalize, weights_for   # noqa: E402
from product_encoder import Encoder, ORDER                          # noqa: E402
from recommender import schedule_for                                # noqa: E402

OUT = os.path.join(ROOT, "batch", "ingest", "data", "feature_sample.json")
DOC = os.path.join(ROOT, "docs", "ai", "product-feature-sample.md")
AFFINITY_CSV = os.path.join(ROOT, "batch", "ingest", "data", "affinity_lift.csv")

# 속성별 lift 극단 사례. 이름은 카탈로그의 product_name 과 정확히 같아야 한다
PICK = [
    ("Balancing Force Oil Control Toner", "skin_type=oily lift 최고"),
    ("Cicapair Tiger Grass Cream", "skin_type=dry lift 최고"),
    ("Lip Sleeping Mask Intense Hydration with Vitamin C", "1위 상품 - loves_count 최고"),
    ("Greek Yoghurt Foaming Cream Cleanser", "skin_tone=deep lift 최고"),
    ("Smart Clinical Repair Wrinkle Correcting Serum", "hair_color=gray lift 최고"),
]

# 행동이 0건인 사용자 3명. 속성 항만으로 순위가 어떻게 갈리는지 보여준다
USERS = [
    {"label": "지성 / light 톤", "skin_type": "oily", "skin_tone": "light",
     "hair_color": "brown", "eye_color": "brown"},
    {"label": "건성 / fair 톤", "skin_type": "dry", "skin_tone": "fair",
     "hair_color": "blonde", "eye_color": "blue"},
    {"label": "복합성 / deep 톤", "skin_type": "combination", "skin_tone": "deep",
     "hair_color": "black", "eye_color": "brown"},
]


def load_affinity_rows():
    """설명 문구용 원본값(lift/표본 수/z)까지 들고 있는다"""
    rows = {}
    with open(AFFINITY_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            bucket = rows.setdefault(r["group_id"], {}).setdefault(r["attribute"], {})
            bucket[r["segment"]] = {
                "affinity": float(r["affinity"]), "lift": float(r["lift"]),
                "n_reviews": int(r["n_reviews"]), "z_score": float(r["z_score"])}
    return rows


def pick_products(products):
    """극단 5개 + 그중 한 브랜드의 형제 1개"""
    by_name = {p["product_name"]: p for p in products}
    chosen, reasons = [], {}
    for name, why in PICK:
        if name not in by_name:
            raise SystemExit(f"카탈로그에 없는 상품: {name}")
        chosen.append(by_name[name])
        reasons[by_name[name]["product_id"]] = why

    picked = {p["product_id"] for p in chosen}
    for base in chosen:
        siblings = [p for p in products
                    if p["brand_name"] == base["brand_name"]
                    and p["product_id"] not in picked]
        if siblings:
            sib = min(siblings, key=lambda p: p["rank"])
            reasons[sib["product_id"]] = f"{base['brand_name']} 형제 - brand 블록 확인용"
            chosen.append(sib)
            break
    return chosen, reasons


def block_values(encoder, product):
    """블록별 비영값. 원본 -> L2 정규화 -> 블록 가중치를 곱한 뒤의 값이다"""
    raw = encoder.blocks(product)
    out = {}
    for name in ORDER:
        b = np.asarray(raw[name], dtype=float)
        norm = np.linalg.norm(b)
        weighted = (b / norm if norm > 0 else b) * encoder.w[name]
        vocab = encoder.blk[name]["vocab"] if name in encoder.blk else [name]
        out[name] = {"weight": encoder.w[name],
                     "values": {vocab[j]: round(float(v), 4)
                                for j, v in enumerate(weighted) if abs(v) > 1e-9}}
    return out


def build():
    encoder = Encoder()
    products = encoder.products
    index = {p["product_id"]: i for i, p in enumerate(products)}
    prior = np.asarray(encoder.prior(), dtype=float)
    affinity_rows = load_affinity_rows()
    table = AffinityTable(index)

    sample, reasons = pick_products(products)
    records, vectors = [], {}
    for p in sample:
        gid = p["product_id"]
        vec = np.asarray(encoder.encode(p), dtype=float)
        vectors[gid] = vec
        records.append({
            "rank": p["rank"], "product_id": gid,
            "product_name": p["product_name"], "brand_name": p["brand_name"],
            "선정_이유": reasons[gid],
            "원본": {"secondary_category": p["secondary_category"],
                     "tertiary_category": p["tertiary_category"],
                     "price_usd": p["price_usd"], "rating": p["rating"],
                     "loves_count": p["loves_count"],
                     "highlights": p.get("highlights")},
            "태그_분류": encoder.split_tags(p),
            "성분_값": {k: round(v, 4) for k, v in
                        sorted(encoder.ingredient_values(p).items(),
                               key=lambda kv: -kv[1])},
            "성분_수": len(encoder.parse_ingredients(p)),
            "prior_score": round(float(prior[index[gid]]), 4),
            "블록별_값": block_values(encoder, p),
            "벡터": [round(float(z), 5) for z in vec],
            "속성_친화도": affinity_rows.get(gid, {}),
        })

    ids = [p["product_id"] for p in sample]
    matrix = np.vstack([vectors[i] for i in ids])
    cosine = (matrix @ matrix.T).round(3)

    # 행동 0건 사용자의 순위. 이 구간의 가중치는 스케줄이 정한다
    w1, w2, w3 = schedule_for(0)
    examples = []
    for user in USERS:
        seg = normalize(user)
        weights = weights_for(user["skin_type"])
        rows = []
        for p in sample:
            gid = p["product_id"]
            detail = {}
            for attr, weight in weights.items():
                cell = affinity_rows.get(gid, {}).get(attr, {}).get(seg[attr])
                value = cell["affinity"] if cell else 0.5
                detail[attr] = {"segment": seg[attr], "affinity": round(value, 4),
                                "weight": weight, "contrib": round(value * weight, 4)}
            attr_score = float(table.vector(user)[index[gid]])
            prior_score = float(prior[index[gid]])
            rows.append({"product_name": p["product_name"],
                         "attr_affinity": round(attr_score, 4),
                         "prior": round(prior_score, 4),
                         "score": round(w2 * attr_score + w3 * prior_score, 4),
                         "detail": detail})
        rows.sort(key=lambda r: -r["score"])
        examples.append({"user": user,
                         "weights": {"w1_cosine": w1, "w2_attr": w2, "w3_prior": w3},
                         "ranking": rows})

    return {
        "vocab_version": encoder.V["version"],
        "n_dim": encoder.V["total_content_dim"],
        "blocks": [{"name": b["name"], "dim": len(b["vocab"]),
                    "weight": b["block_weight"]} for b in encoder.V["blocks"]],
        "products": records,
        "cosine_between_samples": {
            "order": [p["product_name"] for p in sample],
            "brand": [p["brand_name"] for p in sample],
            "matrix": cosine.tolist()},
        "recommendation_examples": examples,
    }


def write_markdown(out):
    """문서를 산출물에서 만든다.

    손으로 쓰면 어휘집이 바뀔 때마다 문서만 뒤처진다. 실제로 어휘집이 0.3 -> 0.4 로
    가면서 문서가 93차원에 멈춰 있었고, 그 사이 빠진 것이 정확도의 대부분을 설명하는
    brand 블록이었다. 그래서 서술만 여기에 두고 숫자는 전부 생성한다.
    """
    products = out["products"]
    lines = []
    a = lines.append
    a("# Product Feature 샘플 — 실제 상품 6개")
    a("")
    a(f"> 어휘집 `{out['vocab_version']}` · 콘텐츠 벡터 {out['n_dim']}차원")
    a("> 원본 데이터: [`batch/ingest/data/feature_sample.json`]"
      "(../../batch/ingest/data/feature_sample.json) (벡터 전체 값 포함)")
    a("> **이 문서는 생성물입니다.** 고칠 일이 있으면"
      " `batch/ingest/build_feature_sample.py` 를 고치고 다시 실행하세요.")
    a("")
    a("명세([`product-feature-spec.md`](../../contracts/product-feature-spec.md))가"
      " 실제로 어떤 값을 만들어내는지 확인하기 위한 샘플입니다."
      " 각 속성의 신호를 보여줄 극단 사례와, `brand` 블록을 확인하기 위한"
      " 같은 브랜드 형제 하나를 골랐습니다.")
    a("")
    a("| 상품 | 브랜드 | 순위 | 선정 이유 |")
    a("|---|---|---:|---|")
    for r in products:
        a(f"| {r['product_name']} | {r['brand_name']} | {r['rank']} |"
          f" {r['선정_이유']} |")
    a("")
    a("---")
    a("")
    a("## 1. 원본 필드")
    a("")
    a("| 상품 | secondary | tertiary | 가격 | 평점 | loves_count | prior |")
    a("|---|---|---|---:|---:|---:|---:|")
    for r in products:
        o = r["원본"]
        a(f"| {r['product_name'][:38]} | {o['secondary_category']} |"
          f" {o['tertiary_category']} | ${o['price_usd']:.0f} | {o['rating']:.2f} |"
          f" {o['loves_count']:,} | {r['prior_score']:.3f} |")
    a("")
    a("`prior` 는 `loves_count` 를 log1p 후 min-max 로 편 값입니다."
      " 개인화 정보가 없는 구간의 안전장치입니다.")
    a("")
    a("## 2. 블록 구성")
    a("")
    a("| 블록 | 차원 | 블록 가중치 |")
    a("|---|---:|---:|")
    for b in out["blocks"]:
        a(f"| `{b['name']}` | {b['dim']} | {b['weight']} |")
    a("| `rating` (스칼라) | 1 | 0.02 |")
    a("")
    a(f"합계 {out['n_dim']}차원. **`brand` 가 55차원 · 가중치 0.60 으로 가장 큽니다.**"
      " 다음 구매에서 유지되는 속성 중 lift 가 압도적이기 때문입니다(6.08배).")
    a("")
    a(f"## 3. 인코딩 따라가기 — {products[0]['product_name']}")
    a("")
    a("블록별로 L2 정규화한 뒤 블록 가중치를 곱한 값입니다."
      " 전체 L2 정규화 전 단계이며, 최종 벡터는 산출물의 `벡터` 에 있습니다.")
    a("")
    a("| 블록 | 가중치 | 비영값 |")
    a("|---|---:|---|")
    for name, blk in products[0]["블록별_값"].items():
        vals = ", ".join(f"`{k}` {v}" for k, v in blk["values"].items()) or "(없음)"
        a(f"| `{name}` | {blk['weight']} | {vals} |")
    a("")
    ing = products[0]["성분_값"]
    a("성분은 하이라이트 태그와 전성분 문자열에서 뽑아 위치 가중을 줍니다"
      f" (전성분 {products[0]['성분_수']}개 파싱): "
      + ", ".join(f"`{k}` {v}" for k, v in list(ing.items())[:5]) + ".")
    a("")
    a("## 4. 샘플 간 코사인 — `brand` 블록이 하는 일")
    a("")
    order = out["cosine_between_samples"]["order"]
    brands = out["cosine_between_samples"]["brand"]
    matrix = out["cosine_between_samples"]["matrix"]
    a("| | " + " | ".join(str(i) for i in range(len(order))) + " |")
    a("|---|" + "---:|" * len(order))
    for i, row in enumerate(matrix):
        a(f"| **{i}** {order[i][:30]} ({brands[i]}) | "
          + " | ".join(f"{v:.3f}" for v in row) + " |")
    a("")
    same = [(i, j) for i in range(len(order)) for j in range(i + 1, len(order))
            if brands[i] == brands[j]]
    if same:
        i, j = same[0]
        others = [matrix[i][k] for k in range(len(order)) if k not in (i, j)]
        a(f"**{brands[i]} 형제 두 개({i}·{j})가 {matrix[i][j]:.3f}** 입니다."
          f" 같은 상품 {i} 와 다른 브랜드들의 코사인은"
          f" {min(others):.3f}~{max(others):.3f} 입니다.")
        a("")
        a("브랜드가 같으면 55차원 원핫이 정확히 겹치고 그 축의 가중치가 0.60 이라,"
          " 카테고리나 성분이 달라도 코사인이 크게 올라갑니다. 브랜드 재구매를"
          " 잡아내는 힘이 여기서 나오고, 새 브랜드 추천이 어려운 이유도 같습니다"
          " — 원핫이라 시드와 직교하면 그 축의 기여가 0 입니다.")
    a("")
    a("## 5. 행동이 0건인 사용자의 순위")
    a("")
    w = out["recommendation_examples"][0]["weights"]
    a(f"상호작용 상품이 0개인 구간의 가중치입니다 (`w1={w['w1_cosine']}` ·"
      f" `w2={w['w2_attr']}` · `w3={w['w3_prior']}`,"
      " `batch/jobs/recommender.py` 의 `SCHEDULE`). 코사인 항이 없으므로"
      " **속성 친화도와 인기도만으로** 순위가 정해집니다.")
    a("")
    for ex in out["recommendation_examples"]:
        u = ex["user"]
        a(f"**{u['label']}** (`skin_type={u['skin_type']}`,"
          f" `skin_tone={u['skin_tone']}`, `hair_color={u['hair_color']}`,"
          f" `eye_color={u['eye_color']}`)")
        a("")
        a("| 순위 | 상품 | attr_affinity | prior | score |")
        a("|---:|---|---:|---:|---:|")
        for n, r in enumerate(ex["ranking"], 1):
            a(f"| {n} | {r['product_name'][:38]} | {r['attr_affinity']:.3f} |"
              f" {r['prior']:.3f} | **{r['score']:.4f}** |")
        a("")
    a("복합성 사용자는 `skin_type` 항을 쓰지 않고 그 몫을 `skin_tone` 으로 넘깁니다"
      " (0.00 / 0.80 / 0.10 / 0.10). 200개 상품 전부 lift 0.85~1.19 로 판별력이"
      " 없기 때문입니다. 나머지는 0.40 / 0.40 / 0.10 / 0.10 입니다.")
    a("")
    a("## 6. 재생성")
    a("")
    a("```bash")
    a("python batch/ingest/build_feature_sample.py")
    a("```")
    a("")
    a("산출물과 이 문서가 함께 갱신됩니다."
      " 어휘집이나 가중치 스케줄을 바꾸면 반드시 다시 실행하세요.")
    a("")
    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def main():
    out = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    write_markdown(out)

    print(f"저장: {os.path.relpath(OUT, ROOT)}  (어휘집 {out['vocab_version']}, "
          f"{out['n_dim']}차원, 상품 {len(out['products'])}개)")
    for r in out["products"]:
        print(f"  [{r['rank']:>3}위] {r['brand_name'][:14]:<14} "
              f"{r['product_name'][:36]:<36} prior={r['prior_score']:.3f}"
              f"  {r['선정_이유']}")

    names = out["cosine_between_samples"]["order"]
    print("\n샘플 간 코사인")
    print("              " + " ".join(f"{i:>6}" for i in range(len(names))))
    for i, row in enumerate(out["cosine_between_samples"]["matrix"]):
        print(f"  {i} {names[i][:11]:<11}" + " ".join(f"{v:6.3f}" for v in row))

    for ex in out["recommendation_examples"]:
        print(f"\n=== {ex['user']['label']} (행동 0건, "
              f"w2={ex['weights']['w2_attr']} w3={ex['weights']['w3_prior']}) ===")
        for r in ex["ranking"]:
            print(f"   {r['score']:.4f}  attr={r['attr_affinity']:.3f}"
                  f" prior={r['prior']:.3f}  {r['product_name'][:40]}")


if __name__ == "__main__":
    main()
