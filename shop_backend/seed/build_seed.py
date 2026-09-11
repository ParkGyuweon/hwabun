"""프론트가 화면에 띄우는 데이터 전부를 shop_backend 테이블 모양으로 묶는다 (백엔드 시드 인계, 2026-09-11).

원천은 전부 저장소 안에 있고 이 스크립트는 그것을 **백엔드 컬럼 이름(camelCase)** 으로 바꿔 JSON 으로 쓴다.
백엔드는 이 JSON 을 읽어 INSERT 하면 된다. 어느 파일이 어느 테이블인지는 같은 폴더 README.md.

    python shop_backend/seed/build_seed.py          # → shop_backend/seed/out/*.json

원천
  frontend/src/mocks/products.sample.json          세포라 상품 200 (원문)
  frontend/src/mocks/products.collected.json       그 상품의 이미지·옵션·설명 수집본
  frontend/src/mocks/products.ssafy-beauty.json    시연 브랜드 8
  frontend/src/mocks/reviews.sample.json           세포라 리뷰 2,000 (리뷰어 피부 속성 포함)
  frontend/src/mocks/personas.sample.json          PA 페르소나 100 (회원 시드용)
  frontend/src/mocks/discounts.json                할인율 (표시용 → variant.sale_price_krw)
  contracts/localization/products-ko.json          상품 한국어 (이름·용량·가격·설명·성분)
  contracts/localization/reviews-ko.json           리뷰 한국어
  contracts/product-form-labels-ko.json            코드 테이블 한국어 라벨
  batch/ingest/data/products_200.json              세포라 brand_id (데이터 dim_brand 와 같은 값)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# 프론트 표시 환율 (frontend/src/lib/localize.ts). products-ko 의 price_krw 와 같은 식
KRW_PER_USD = 1340.86
KRW_ROUNDING = 100


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def to_krw(usd: float) -> int:
    return int(round(usd * KRW_PER_USD / KRW_ROUNDING) * KRW_ROUNDING)


def dump(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(data) if hasattr(data, "__len__") else "?"
    print(f"{name:28s} {n}")


# ---------- 원천 ----------
sample = load("frontend/src/mocks/products.sample.json")
collected = load("frontend/src/mocks/products.collected.json")
ssafy = load("frontend/src/mocks/products.ssafy-beauty.json")
reviews = load("frontend/src/mocks/reviews.sample.json")
personas = load("frontend/src/mocks/personas.sample.json")
discounts = {k: v for k, v in load("frontend/src/mocks/discounts.json").items() if not k.startswith("_")}
products_ko = {k: v for k, v in load("contracts/localization/products-ko.json").items() if not k.startswith("_")}
reviews_ko = {k: v for k, v in load("contracts/localization/reviews-ko.json").items() if not k.startswith("_")}
labels = load("contracts/product-form-labels-ko.json")
try:
    products_200 = load("batch/ingest/data/products_200.json")
    brand_id_by_name = {p["brand_name"]: str(p["brand_id"]) for p in products_200 if p.get("brand_id") is not None}
except FileNotFoundError:
    brand_id_by_name = {}

SECONDARY = {r["value"] for r in labels["secondary_category"]}
TERTIARY = {r["value"] for r in labels["tertiary_category"]}
PRICE_BIN_EDGES = [(20, "~20"), (35, "20-35"), (50, "35-50"), (80, "50-80")]


def price_bin(usd: float) -> str:
    for edge, code in PRICE_BIN_EDGES:
        if usd < edge:
            return code
    return "80+"


issues: list[dict] = []


def note(kind: str, pid: str, detail: str) -> None:
    issues.append({"kind": kind, "productId": pid, "detail": detail})


# ---------- 1. 브랜드 ----------
SSAFY_BRAND_ID = "ssafy-beauty"  # 제안값. 백엔드가 uuid 로 발급해도 되지만 그러면 AI 카탈로그·dw 에도 같은 값이 흘러가야 한다
brands: dict[str, dict] = {}
for p in sample:
    name = p["brand_name"]
    bid = brand_id_by_name.get(name)
    if bid is None:
        note("brand_id_missing", p["product_id"], f"products_200.json 에 {name} 의 brand_id 가 없다. slug 로 대체")
        bid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    brands.setdefault(bid, {"brandId": bid, "name": name, "source": "seed_catalog", "sephoraBrandId": bid.isdigit() and int(bid) or None})
brands[SSAFY_BRAND_ID] = {"brandId": SSAFY_BRAND_ID, "name": "SSAFY Beauty", "source": "brand_registered", "sephoraBrandId": None}
dump("brands.json", sorted(brands.values(), key=lambda b: b["name"]))


# ---------- 2. 상품 ----------
def build_product(p: dict, source: str) -> dict:
    pid = p["product_id"]
    ko = products_ko.get(pid, {})
    ext = collected.get(pid, {}) if isinstance(collected, dict) else {}
    cat = p.get("category") or []
    secondary = cat[1] if len(cat) > 1 else None
    tertiary = cat[2] if len(cat) > 2 else None
    if secondary not in SECONDARY:
        note("secondary_not_in_vocab", pid, f"{secondary!r}")
    if tertiary is None:
        # 원천이 2단계까지만 있는 상품. 같은 이름이 3단계 어휘에도 있으면 그것으로 채운다 (Moisturizers · Lip Balms & Treatments)
        if secondary in TERTIARY:
            tertiary = secondary
            note("tertiary_filled_from_secondary", pid, f"{secondary} → tertiary 도 같은 값으로")
        else:
            note("tertiary_missing", pid, f"secondary={secondary}. tertiary_category NOT NULL 이라 값을 정해야 한다")
    elif tertiary not in TERTIARY:
        note("tertiary_not_in_vocab", pid, f"{tertiary!r}")

    usd = float(p.get("price_usd") or 0)
    krw = int(ko["price_krw"]) if ko.get("price_krw") else to_krw(usd)
    disc = discounts.get(pid)
    sale_krw = int(round(krw * (1 - disc["rate"]) / KRW_ROUNDING) * KRW_ROUNDING) if disc else None

    brand_id = SSAFY_BRAND_ID if source == "brand_registered" else brand_id_by_name.get(p["brand_name"]) or re.sub(r"[^a-z0-9]+", "-", p["brand_name"].lower()).strip("-")

    variants_src = p.get("variants") or ext.get("variants") or []
    label_ko = (ko.get("variant_labels") or {}) if isinstance(ko.get("variant_labels"), dict) else {}
    variants = []
    for i, v in enumerate(variants_src):
        variants.append({
            "skuId": str(v.get("sku_id") or f"{pid}-{i+1}"),
            "label": v.get("label") or "기본",
            "labelKo": label_ko.get(v.get("label") or "", None),
            "size": p.get("size"),
            "priceKrw": krw,
            "salePriceKrw": sale_krw,
            "imageUrl": v.get("image_url"),
            "swatchUrl": v.get("swatch_url"),
            "sortOrder": i,
        })
    if not variants:
        variants.append({"skuId": str(p.get("sku_id") or pid), "label": "기본", "labelKo": "기본", "size": p.get("size"),
                         "priceKrw": krw, "salePriceKrw": sale_krw, "imageUrl": p.get("image_url"), "swatchUrl": None, "sortOrder": 0})

    ingredients = p.get("ingredients") or []
    ingredients_text = ", ".join(x.strip() for x in ingredients if x and x.strip())
    ing_ko = ko.get("ingredients")
    ingredients_text_ko = ", ".join(ing_ko) if isinstance(ing_ko, list) else (ing_ko or None)

    desc = p.get("description") or ext.get("description") or {}
    return {
        "productId": pid,
        "brandId": brand_id,
        "brandName": p["brand_name"],
        "productSource": source,
        "status": "ACTIVE",
        "categoryId": secondary,          # category 테이블은 secondary 코드로 시드 (요청 2·9-2)
        "secondaryCategory": secondary,
        "tertiaryCategory": tertiary,
        "priceBin": price_bin(usd),
        "productName": p["product_name"],            # 영문 원문. 추천 서버·데이터 dim_product 와 같은 값
        "productNameKo": ko.get("product_name"),     # 화면 표시명 (제안: description_json.name_ko 또는 product_name_ko 컬럼)
        "size": p.get("size"),
        "sizeKo": ko.get("size"),
        "priceKrw": krw,
        "salePriceKrw": sale_krw,
        "discountLabel": disc["label"] if disc else None,
        "sourcePriceUsd": usd,
        "sourceRating": p.get("rating"),
        "sourceReviewCount": p.get("review_count"),
        "sourceLovesCount": p.get("loves_count"),
        "sourceRank": p.get("rank"),
        "ratingSource": "observed" if p.get("rating") is not None else "injected",
        "primaryImageUrl": p.get("image_url") or ext.get("image_url"),
        "images": p.get("images") or ext.get("images") or [],
        "variants": variants,
        "highlights": p.get("highlights") or [],
        "suitableSkinTypes": p.get("suitable_skin_types") or [],
        "skincareConcerns": p.get("skincare_concerns") or [],
        "badges": p.get("badges") or [],
        "ingredientsText": ingredients_text,
        "ingredientsTextKo": ingredients_text_ko,
        "description": desc,
        "descriptionKo": ko.get("description"),
    }


products_out = [build_product(p, "seed_catalog") for p in sample] + [build_product(p, "brand_registered") for p in ssafy]
dump("products.json", products_out)


# ---------- 3. 리뷰 ----------
reviews_out = []
for r in reviews:
    ko = reviews_ko.get(r["review_id"], {})
    reviews_out.append({
        "reviewId": r["review_id"],
        "productId": r["product_id"],
        "authorId": r.get("author_id"),
        "rating": int(r["rating"]),
        "isRecommended": r.get("is_recommended"),
        "title": r.get("review_title"),
        "body": r.get("review_text"),
        "titleKo": ko.get("review_title"),
        "bodyKo": ko.get("review_text"),
        "submittedAt": r.get("submission_time"),
        "skinTypeSnapshot": r.get("skin_type"),
        "skinToneSnapshot": r.get("skin_tone"),
        "hairColorSnapshot": r.get("hair_color"),
        "eyeColorSnapshot": r.get("eye_color"),
        "source": "seed_catalog",
    })
dump("reviews.json", reviews_out)


# ---------- 4. 회원 (페르소나 100) ----------
members = [{
    "email": f"{p['persona_id'].lower()}@persona.hwabun.local",
    "password": "hwabun1234",
    "nickname": p["persona_id"],
    "skinTypeCode": p.get("skin_type"),
    "skinToneCode": p.get("skin_tone"),
    "hairColorCode": p.get("hair_color"),
    "eyeColorCode": p.get("eye_color"),
    "personaId": p["persona_id"],
} for p in personas]
dump("members-personas.json", members)


# ---------- 5. 코드 테이블 (한국어 라벨) ----------
codes = {}
for key in ["secondary_category", "tertiary_category", "price_bin", "concern", "clean", "texture", "ingredient"]:
    rows = labels.get(key) or []
    codes[key] = [{"code": r["value"], "labelKo": r["ko"]} for r in rows]
for field in ["skin_type", "skin_tone", "hair_color", "eye_color"]:
    codes[field] = [{"code": r["value"], "labelKo": r["ko"]} for r in labels["segment"] if r["field"] == field]
if not any(c["code"] == "gray" for c in codes["hair_color"]):
    codes["hair_color"].append({"code": "gray", "labelKo": "회색 모발"})
codes["category"] = [{"categoryId": c["code"], "code": c["code"], "name": c["labelKo"], "depth": 1, "sortOrder": i} for i, c in enumerate(codes["secondary_category"])]
dump("codes.json", codes)

# ---------- 6. 점검 결과 ----------
summary = Counter(i["kind"] for i in issues)
dump("issues.json", {"summary": dict(summary), "items": issues})
print("issues:", dict(summary))
