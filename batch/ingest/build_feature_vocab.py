# -*- coding: utf-8 -*-
"""
상품 콘텐츠 벡터 어휘집 생성 — contracts/product-feature-vocab.json (v0.4, 148차원)

어휘집은 batch/jobs/product_encoder.py 가 읽는 유일한 진실 소스다.
블록 구성·가중치·IDF 문서빈도가 전부 여기서 나오므로, 카탈로그(products_200.json)가
바뀌면 반드시 이 스크립트를 다시 돌려 어휘집을 갱신해야 한다.

입력  batch/ingest/data/products_200.json
출력  contracts/product-feature-vocab.json

실행: python batch/ingest/build_feature_vocab.py
"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "batch", "jobs"))
from product_encoder import brand_key   # noqa: E402  브랜드 키 = brand_id (Jira 247)
import numpy as np

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
ART = os.path.join(BD, "data")
d = json.load(open(os.path.join(ART, "products_200.json"), encoding="utf-8"))
N = len(d)

ING = {"Hyaluronic Acid", "Vitamin C", "Niacinamide", "Retinol", "Salicylic Acid",
       "AHA/Glycolic Acid", "Lactic Acid", "Collagen", "SPF"}

# ingredient 어휘집: highlights 태그가 없어도 전성분 문자열에서 복원하기 위한 동의어.
# 값은 전성분 표기(소문자) 부분일치 패턴.
# 채택 기준: 상위 200개 중 5~120개 상품 보유 (너무 흔하거나 드문 성분 제외)
ING_SYNONYMS = {
    "Hyaluronic Acid": ["hyaluronic acid", "sodium hyaluronate", "hyaluronate"],
    "Vitamin C": ["ascorbic acid", "ascorbyl", "ascorbate"],
    "Niacinamide": ["niacinamide"],
    # retinoate = hydroxypinacolone retinoate(HPR, 레티노이드 에스터). 태그 제거(Jira 237) 뒤 Luna Retinoid Oil 등
    # 2개가 전성분에 HPR 이 있는데도 빠져서 추가 (2026-09-10, Jira 243). retinal = 레티날데하이드
    "Retinol": ["retinol", "retinyl", "retinoate", "retinal", "retinaldehyde"],
    # betaine salicylate = BHA 유도체(국내 각질 제품). butyloctyl/ethylhexyl salicylate 는 자차·에몰리언트라 넣지 않는다
    "Salicylic Acid": ["salicylic acid", "betaine salicylate"],
    "AHA/Glycolic Acid": ["glycolic acid"],
    "Lactic Acid": ["lactic acid"],
    "Collagen": ["collagen"],
    # 자외선차단 성분은 법정 표기라 전성분표에 반드시 들어간다. 태그가 없어도
    # 잡히게 동의어를 준다 (2026-09-03). 등록 폼은 성분 태그를 받지 않으므로,
    # 이게 없으면 등록된 선크림은 SPF 축이 영구히 0 이 된다
    "SPF": ["spf", "titanium dioxide", "zinc oxide", "octocrylene", "avobenzone",
            "homosalate", "octisalate",
            # 유기자차(INCI 영문). 국내 선크림 영문 전성분은 위 미국식 상용명이 아니라 이 이름으로
            # 적힌다 — 없으면 SSAFY 선 세럼(SB000006)처럼 SPF 축이 안 열린다 (2026-09-10)
            "ethylhexyl methoxycinnamate", "ethylhexyl salicylate", "ethylhexyl triazone",
            "butyl methoxydibenzoylmethane", "diethylamino hydroxybenzoyl hexyl benzoate",
            "bis-ethylhexyloxyphenol methoxyphenyl triazine", "methylene bis-benzotriazolyl",
            "phenylbenzimidazole sulfonic acid", "drometrizole trisiloxane",
            "terephthalylidene dicamphor sulfonic acid", "tris-biphenyl triazine",
            "polysilicone-15", "isoamyl p-methoxycinnamate", "diethylhexyl butamido triazone",
            # 국내 선크림은 한글 전성분표에 이 이름으로 적힌다
            "자외선차단", "티타늄디옥사이드", "티타늄옥사이드", "징크옥사이드",
            "산화아연", "옥토크릴렌", "아보벤존", "호모살레이트", "옥티살레이트",
            "에칠헥실메톡시신나메이트", "비스에칠헥실옥시페놀메톡시페닐트리아진",
            "에칠헥실살리실레이트", "에칠헥실트리아존", "부틸메톡시디벤조일메탄",
            "디에칠아미노하이드록시벤조일헥실벤조에이트", "메칠렌비스-벤조트리아졸릴테트라메칠부틸페놀",
            "페닐벤즈이미다졸설포닉애씨드", "드로메트리졸트리실록산", "테레프탈릴리덴디캠퍼설포닉애씨드",
            "트리스-비페닐트리아진", "폴리실리콘-15", "이소아밀p-메톡시신나메이트", "디에칠헥실부타미도트리아존"],
    "Silicone": ["dimethicone", "cyclopentasiloxane"],
    "Squalane": ["squalane", "squalene"],
    "Probiotic / Ferment": ["ferment filtrate", "lactobacillus", "bifida"],
    "Green Tea": ["camellia sinensis"],
    "Peptides": ["peptide", "palmitoyl tripeptide", "acetyl hexapeptide",
                 "copper tripeptide"],
    "Aloe": ["aloe barbadensis", "aloe vera"],
    "Licorice": ["glycyrrhiza", "licorice"],
    "Panthenol (B5)": ["panthenol", "pantothenic"],
    "Shea Butter": ["butyrospermum", "shea butter"],
    "Jojoba": ["jojoba"],
    "Ceramide": ["ceramide"],
    "Rosehip / Rose": ["rosa canina", "rosa damascena", "rose flower"],
    "Caffeine": ["caffeine"],
    "Urea": ["urea"],
    "Allantoin": ["allantoin"],
    "Adenosine": ["adenosine"],
    "Zinc": ["zinc pca", "zinc oxide", "zinc gluconate"],
    "Alcohol Denat": ["alcohol denat"],
    "Centella (Cica)": ["centella", "asiaticoside", "madecassoside", "asiatic acid"],
    "Willow Bark": ["salix", "willow bark"],
    "Mineral Oil / Petrolatum": ["petrolatum", "mineral oil"],
}

# 한국어 표기 (2026-09-03). 국내 브랜드가 상품을 등록할 때 한글 전성분표를
# 붙여넣는다. 파서가 한글을 남기게 고쳤고(product_encoder.parse_ingredients),
# 여기에 표기를 넣어야 매칭된다. 같은 성분표를 한글·영문으로 넣으면 매칭 결과와
# 위치가중값이 소수점까지 같은 것을 확인했다.
#
# **"알코올" 은 넣지 않는다** — 세틸알코올 같은 지방알코올이 걸린다. 변성알코올만.
ING_SYNONYMS_KO = {
    "Hyaluronic Acid": ["히알루론산", "하이알루로닉애씨드", "하이알루로네이트", "소듐하이알루로네이트"],
    "Vitamin C": ["아스코빅애씨드", "아스코빌", "아스코르브산"],
    "Niacinamide": ["나이아신아마이드", "니아신아마이드"],
    "Retinol": ["레티놀", "레티닐", "레티노에이트", "레티날"],
    "Salicylic Acid": ["살리실릭애씨드", "살리실산", "베타인살리실레이트"],
    "AHA/Glycolic Acid": ["글라이콜릭애씨드", "글리콜산"],
    "Lactic Acid": ["락틱애씨드", "젖산"],
    "Collagen": ["콜라겐"],
    "Silicone": ["다이메티콘", "디메치콘", "사이클로펜타실록세인", "사이클로메티콘"],
    "Squalane": ["스쿠알란", "스쿠알렌"],
    "Probiotic / Ferment": ["발효여과물", "락토바실러스", "비피다", "효모발효"],
    "Green Tea": ["녹차", "카멜리아시넨시스"],
    "Peptides": ["펩타이드", "펩티드"],
    "Aloe": ["알로에"],
    "Licorice": ["감초", "글리시리자"],
    "Shea Butter": ["시어버터", "부티로스퍼멈"],
    "Panthenol (B5)": ["판테놀", "판토텐"],
    "Jojoba": ["호호바"],
    "Ceramide": ["세라마이드"],
    "Rosehip / Rose": ["로즈힙", "로사카니나", "로사다마세나", "장미꽃"],
    "Caffeine": ["카페인"],
    "Urea": ["요소", "유레아"],
    "Adenosine": ["아데노신"],
    "Allantoin": ["알란토인"],
    "Zinc": ["징크피씨에이", "징크옥사이드", "산화아연"],
    "Alcohol Denat": ["변성알코올"],
    "Centella (Cica)": ["병풀", "센텔라", "아시아티코사이드", "마데카소사이드"],
    "Willow Bark": ["버드나무", "살릭스"],
    "Mineral Oil / Petrolatum": ["미네랄오일", "광물유", "페트롤라툼", "바셀린"],
}

for _name, _ko in ING_SYNONYMS_KO.items():
    ING_SYNONYMS[_name].extend(_ko)
POS_MIN = 0.10          # 전성분 뒤쪽 성분의 하한 (미량 성분 과대평가 방지)
PAREN_RE = re.compile(r"\([^)]*\)")
NOISE_RE = re.compile(r"^(water|aqua|eau)$|^\d|^and$|^or$|^may contain")
SPLIT_RE = re.compile("[,;" + chr(10) + "]")


def parse_ingredients(x):
    """전성분 문자열 -> 함량순 성분 리스트"""
    txt = PAREN_RE.sub(" ", " ".join(x["ingredients"]))
    out = []
    for tok in SPLIT_RE.split(txt):
        t = re.sub(r"[^A-Za-z0-9 \-/]", " ", tok).strip().lower()
        t = re.sub(r"\s+", " ", t)
        if not t or len(t) < 3 or len(t) > 45 or NOISE_RE.match(t):
            continue
        out.append(t)
    return out


def ingredient_values(x):
    """어휘별 값. 태그로 표시되면 1.0, 전성분에서만 찾으면 위치 기반 감쇠"""
    tagged = {h for h in x["highlights"] if h in ING}
    lst = parse_ingredients(x)
    n = max(len(lst), 1)
    vals = {}
    for name, syns in ING_SYNONYMS.items():
        if name in tagged:
            vals[name] = 1.0
            continue
        if not syns:
            continue
        for pos, t in enumerate(lst):
            if any(sy in t for sy in syns):
                vals[name] = max(1.0 - pos / n, POS_MIN)
                break
    return vals
CLEAN_EXTRA = {"Vegan", "Cruelty-Free", "Clean at Sephora", "Clean + Planet Positive",
               "Fragrance Free", "Gluten Free", "Oil Free", "Alcohol Free",
               "Hypoallergenic", "Reef Safe SPF", "Refill Available"}
POP_RE = re.compile(r"allure|Best of Beauty|Community Favorite|Award|Winner", re.I)
SKIN_MAP = {"dry": "dry", "combo": "combination", "combination": "combination",
            "normal": "normal", "oily": "oily"}
MIN_FREQ = 3          # 이 횟수 미만 태그는 어휘에서 제외

counts = collections.defaultdict(collections.Counter)
for x in d:
    for h in x["highlights"]:
        if h.startswith("Good for:"):
            counts["concern"][h.split(":", 1)[1].strip()] += 1
        elif h.startswith("Best for") and h.endswith("Skin"):
            for tok in re.split(r"[,/]| and ", h[len("Best for"):-len("Skin")]):
                k = tok.strip().lower()
                if k in SKIN_MAP:
                    counts["skin_fit"][SKIN_MAP[k]] += 1
        elif h in ING:
            pass  # ingredient 는 아래에서 전성분까지 포함해 별도 집계
        elif h in CLEAN_EXTRA or h.startswith("Without"):
            counts["clean"][h] += 1
        elif POP_RE.search(h):
            counts["popularity_excluded"][h] += 1
        else:
            counts["texture"][h] += 1

# skin_fit lift 기준선: 전체 리뷰의 skin_type 구성비
import collections as _c
_tot = _c.Counter()
for _x in d:
    for _k, _v in _x["_review_stats"]["segment_counts"]["skin_type"].items():
        _tot[_k] += _v
BASE_SHARE = {k: round(_tot[k] / sum(_tot.values()), 6) for k in
              ["combination", "dry", "normal", "oily"]}

ING_VALS = [ingredient_values(x) for x in d]
for v in ING_VALS:
    for k in v:
        counts["ingredient"][k] += 1

price = np.array([x["price_usd"] for x in d], dtype=float)
loves = np.array([x["loves_count"] for x in d], dtype=float)
rating = np.array([x["rating"] for x in d], dtype=float)

PRICE_EDGES = [0, 20, 35, 50, 80]
BLOCKS = [
    ("secondary_category", "one_hot", 0.06,
     sorted({x["secondary_category"] for x in d})),
    ("tertiary_category", "one_hot", 0.11,
     sorted({x["tertiary_category"] for x in d})),
    ("concern", "multi_hot_idf", 0.42,
     [k for k, v in counts["concern"].most_common() if v >= MIN_FREQ]),
    ("ingredient", "multi_hot_idf_position", 0.27,
     [k for k, v in counts["ingredient"].most_common() if 5 <= v <= 120]),
    ("clean", "multi_hot_idf", 0.06,
     [k for k, v in counts["clean"].most_common() if v >= MIN_FREQ]),
    ("texture", "multi_hot_idf", 0.02,
     [k for k, v in counts["texture"].most_common() if v >= MIN_FREQ]),
    ("price_bin", "one_hot", 0.04,
     ["~20", "20-35", "35-50", "50-80", "80+"]),
    # brand: 다음 구매에서 유지되는 속성 중 lift 가 압도적이다 (6.08x, 2위 price_bin 1.30x).
    # 어휘집에는 카탈로그에 실재하는 브랜드만 담는다 -> 신규 브랜드는 영벡터가 된다.
    ("brand", "one_hot", 0.60,
     # 키는 brand_id 문자열 (Jira 247). 칸 순서는 예전처럼 **이름순**으로 둔다 — id 순으로 바꾸면 벡터 값은
     # 같아도 코사인 합산 순서가 달라져 마지막 자리(1e-16)가 흔들리고 LTR 조기종료 시점이 바뀐다(369→276 트리).
     sorted({brand_key(x) for x in d}, key=lambda k: next(x["brand_name"] for x in d if brand_key(x) == k))),
]

for _x in d:
    counts["brand"][brand_key(_x)] += 1

# 블록별 각주 — 왜 이 블록이 있는지 계약서를 읽는 사람이 알 수 있어야 한다
BLOCK_NOTES = {
    "brand": "다음 구매에서 유지되는 속성 중 lift 가 압도적으로 높다 (6.08x). "
             "리뷰 15만 연속쌍에서 측정. 2위 price_bin 이 1.30x 이다.",
}

df = {}
for name, _, _, vocab in BLOCKS:
    if name in counts:
        df[name] = {t: int(counts[name][t]) for t in vocab}

spec = {
    "version": "0.6",
    "generated_from": "batch/ingest/data/products_200.json",
    "n_products": N,
    "min_tag_freq": MIN_FREQ,
    "idf_formula": "log(N / (1 + df))  -- 블록 내 L2 정규화 후 적용",
    "block_weight_sum": round(sum(w for _, _, w, _ in BLOCKS) + 0.02, 4),
    "blocks": [
        {"name": n, "encoding": e, "block_weight": w, "dim": len(v), "vocab": v,
         "doc_freq": df.get(n), **({"note": BLOCK_NOTES[n]} if n in BLOCK_NOTES else {})}
        for n, e, w, v in BLOCKS
    ],
    "scalars": [
        {"name": "rating", "transform": "minmax",
         "min": float(rating.min()), "max": float(rating.max()),
         "block_weight": 0.02,
         "note": "변동계수 0.057로 변별력 낮음. 가중치 최소로 유지하거나 제외 검토"},
    ],
    "prior_only": [
        {"name": "loves_count", "transform": "log1p_minmax",
         "log_min": float(np.log1p(loves).min()), "log_max": float(np.log1p(loves).max()),
         "note": "콘텐츠 벡터에 넣지 않음. 추천 점수의 인기도 항(prior)으로 사용"},
        {"name": "highlights_popularity_tags",
         "values": sorted(counts["popularity_excluded"]),
         "note": "Community Favorite / allure 수상. 콘텐츠가 아니라 인기 신호"},
    ],
    "ingredient_source": {
        "_note": "highlights 태그가 없어도 전성분 문자열에서 성분을 복원한다. "
                 "태그로 표시된 성분은 1.0, 전성분에서만 찾은 성분은 위치 기반 감쇠.",
        "synonyms": {k: v for k, v in ING_SYNONYMS.items() if v},
        "tag_value": 1.0,
        "position_formula": "max(1 - 등장위치/전체성분수, POS_MIN)",
        "position_min": POS_MIN,
        "vocab_criteria": "상위 200개 중 5~120개 상품 보유",
    },
    "attribute_affinity": {
        "_note": "콘텐츠 벡터가 아니라 추천 점수의 속성 항(attr_affinity)에서 소비된다. "
                 "사용자 속성으로 조회하는 테이블이므로 사용자별 가중치 분기가 가능하다.",
        "table": "batch/ingest/data/affinity_lift.csv",
        "attributes": ["skin_type", "skin_tone", "hair_color", "eye_color"],
        "source": "리뷰의 사용자 속성 구성비 (highlights 태그 아님)",
        "formula": "clip((share_in_product / share_overall - LO) / (HI - LO), 0, 1)",
        "LO": 0.60, "HI": 1.60,
        "shrinkage_k": 50,
        "skin_type_base_share": BASE_SHARE,
        "coverage": "200/200 (100%)",
        "user_weights": {
            "dry|oily|normal": {"skin_type": 0.40, "skin_tone": 0.40,
                                 "hair_color": 0.10, "eye_color": 0.10},
            "combination": {"skin_type": 0.00, "skin_tone": 0.80,
                            "hair_color": 0.10, "eye_color": 0.10}
        },
        "combination_note": "combination은 상품 200개 전부 lift 0.85~1.19(표준편차 0.053)로 "
                            "판별력이 없어 가중치 0. 해당 몫을 skin_tone으로 이관한다."
    },
    "brand_unknown_fallback": {
        "encoding": "match",
        "weight": 0.60,
        "note": "어휘집 brand 목록에 **없는** 브랜드에만 적용한다. 상품 벡터의 brand "
                "블록은 그 상품에서 전부 0 이 되므로, 대신 추천 점수에 "
                "'이 상품 브랜드가 사용자의 시드 브랜드에 있으면 1' 을 더한다. "
                "가중치는 원핫 블록과 같은 0.60 이다. 목록에 있는 브랜드는 지금처럼 "
                "원핫으로 계산하므로 기존 벡터와 점수가 한 자리도 바뀌지 않는다. "
                "값을 구매 횟수 비중으로 바꾸면 나빠진다 (valid -2.68 ~ -5.82%p) — "
                "원핫이 하던 것은 횟수가 아니라 이진 판정이다.",
        "why": "브랜드가 등록될 때마다 차원을 늘리고 기존 상품을 다시 인코딩하는 것은 "
               "서비스 운영 중에 할 수 없다. 폴백은 문자열 비교라 어휘집이 필요 없다.",
    },
    "price_bin_edges": PRICE_EDGES,
    "total_content_dim": sum(len(v) for _, _, _, v in BLOCKS) + 1,
    "changelog": [
        {"version": "0.6",
         "change": "brand 블록 vocab 의 키를 brand_name -> brand_id 문자열로 (labels 에 이름). 55개 1:1 이라 "
                   "원천 200개 벡터는 값이 한 자리도 안 바뀐다 (2026-09-11, Jira 247)",
         "evidence": "쇼핑몰 brand 테이블은 (판매자, 이름) 만 유일해 같은 이름의 브랜드가 여러 판매자에게 등록될 수 있다. "
                     "이름을 키로 쓰면 그 상품이 원천 브랜드의 원핫 벡터·재구매 효과(lift 6x)를 이름만으로 빌린다. "
                     "재생성 뒤 product_feature.jsonl 이 이전과 동일한지 대조해 확인"},
        {"version": "0.5",
         "change": "성분 동의어에 한국어 표기와 SPF 를 넣고, 어휘집에 없는 브랜드를 "
                   "위한 관계 폴백(brand_unknown_fallback)을 명시한다",
         "evidence": "한글·영문 전성분을 같이 넣으면 매칭과 위치가중값이 소수점까지 "
                     "같다. 신규 브랜드 폴백은 기존 200개 벡터를 바꾸지 않는다 "
                     "(카탈로그 브랜드는 전부 어휘집에 있어 폴백이 발동하지 않는다). "
                     "재현: Research/eval/eval_brand_relation_feature_20260903.py"},
        {"version": "0.4",
         "change": "brand 블록 추가 (55종, 가중치 0.60)",
         "evidence": "Recall@10 11.4% -> 23.6% (+12.28%p, 95% CI [+11.41, +13.10], "
                     "대응 부트스트랩 2000회). 롱테일 16.9% -> 31.4%"}
    ],
}

out = os.path.join(ROOT, "contracts", "product-feature-vocab.json")
for _b in spec["blocks"]:
    if _b["name"] == "brand":
        # vocab 은 brand_id 문자열이다. 사람이 읽을 이름은 labels 로 따로 둔다 (2026-09-11, Jira 247).
        _b["key"] = "brand_id 문자열 (원천은 세포라 brand_id, 등록 상품은 쇼핑몰 brand_id; 없으면 'name:'+brand_name)"
        _b["labels"] = {brand_key(x): x["brand_name"] for x in d}
        _b["why_id"] = ("쇼핑몰 brand 테이블은 (판매자, 이름) 만 유일해 같은 이름의 브랜드가 여러 개 등록될 수 있다. "
                        "이름을 키로 쓰면 원천 브랜드의 벡터·재구매 효과를 이름만으로 빌리게 된다.")
json.dump(spec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"저장: {out}")
print(f"\n블록별 차원 (min_freq={MIN_FREQ})")
tot = 0
for b in spec["blocks"]:
    print(f"  {b['name']:<20} {b['encoding']:<15} w={b['block_weight']:<5} {b['dim']:>3}차원")
    tot += b["dim"]
print(f"  {'rating (스칼라)':<20} {'minmax':<15} w=0.02  {1:>3}차원")
print(f"  {'합계':<20} {'':<15}       {tot+1:>3}차원")
print(f"\n제외: loves_count(prior), popularity 태그 {len(counts['popularity_excluded'])}종")
print(f"빈도 {MIN_FREQ} 미만으로 잘린 태그:")
for n, _, _, v in BLOCKS:
    if n in counts:
        cut = [k for k, c in counts[n].items() if c < MIN_FREQ]
        if cut:
            print(f"  {n}: {cut}")
