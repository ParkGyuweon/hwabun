# -*- coding: utf-8 -*-
"""등록 상품이 계약을 지켰고 벡터를 만들 수 있는지 검사한다.

계약 원본은 `contracts/product-registration-spec.md` 다.

왜 필요한가
    등록이 성공하고 화면에도 보이는데 추천에만 안 뜨는 상황이 가장 나쁘다.
    어휘에 없는 값은 매칭되지 않고, 매칭되지 않으면 그 블록이 0 이 되어 코사인
    유사도가 낮아진다. 아무 에러도 나지 않으므로 Tenant 도 우리도 모른다.
    그래서 등록 시점에 두 가지를 본다 — 계약을 지켰는가, 그리고 **실제로 벡터가
    만들어지는가.**

보는 것

    A 필수 필드     계약 §3 의 필수 항목이 있는가
    B 어휘          카테고리·태그가 어휘집에 있는가. 성분 어휘는 태그로 거부한다
    C 파생값        rating · loves_count · price_usd 가 채워졌는가 (계약 §4)
    D 인코딩 가능    벡터를 실제로 만들 수 있는가. 빈 블록을 경고로 보고한다

D 는 계약 위반이 아니어도 경고한다. highlights 를 비우면 concern 블록(가중치 0.42)
이 0 이 되는데, 계약상 허용이지만 추천에는 크게 불리하기 때문이다.

**등록 입력에만 쓴다.** 기존 카탈로그 200개는 Sephora 원천이라 highlights 에 성분
태그가 남아 있고(110개·55.0%), 여기에 이 검증기를 돌리면 계약 §3.1 위반으로 잡힌다.
그건 결함이 아니다. 인코더는 그 태그를 성분 신호로 쓰지 않으므로 인코딩 규칙은 두
집합이 같고, 다른 것은 "앞으로 무엇을 받을 것인가" 하나다 (계약 §3.1 참조).

입력
    상품 1건의 JSON, 또는 상품 배열, 또는 .jsonl

실행
    py contracts/validate_product_registration.py <파일>
    py contracts/validate_product_registration.py <파일> --strict   경고도 실패로
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))

VOCAB = os.path.join(HERE, "product-feature-vocab.json")
FORM_LABELS = os.path.join(HERE, "product-form-labels-ko.json")
CATALOG = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 계약 §3 — Tenant 가 입력하는 필수 필드
REQUIRED_INPUT = ["product_name", "brand_name", "secondary_category",
                  "tertiary_category", "ingredients", "price_krw"]

# 계약 §4 — 등록 파이프라인이 채우는 필드
REQUIRED_DERIVED = ["product_id", "price_usd", "rating", "loves_count"]

# 계약 §3.1 — 폼 태그로 받는 블록. ingredient 는 제외한다
TAG_BLOCKS = ("concern", "clean", "texture")

MIN_CATEGORY_N = 3          # 계약 §4.2 — 이보다 적으면 전체 중앙값


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_products(path):
    if str(path).endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    data = _load_json(path)
    if isinstance(data, dict):
        return data.get("products", [data])
    return data


def load_vocab():
    v = _load_json(VOCAB)
    blocks = {b["name"]: b for b in v["blocks"]}
    scalar = v["scalars"][0]
    return {
        "tag": {n: set(blocks[n]["vocab"]) for n in TAG_BLOCKS},
        "ingredient": set(blocks["ingredient"]["vocab"]),
        "secondary_category": set(blocks["secondary_category"]["vocab"]),
        "tertiary_category": set(blocks["tertiary_category"]["vocab"]),
        "rating_min": scalar["min"],
        "rating_max": scalar["max"],
        "price_edges": v["price_bin_edges"],
        "synonyms": v["ingredient_source"]["synonyms"],
    }


def rating_reference():
    """계약 §4.2 — 카테고리 중앙값, 표본이 적으면 전체 중앙값."""
    products = _load_json(CATALOG)
    by = defaultdict(list)
    for p in products:
        if p.get("rating") is not None:
            by[p.get("tertiary_category")].append(p["rating"])
    overall = statistics.median([r for v in by.values() for r in v])
    return {k: (statistics.median(v) if len(v) >= MIN_CATEGORY_N else overall)
            for k, v in by.items()}, overall


def check(product, vocab, medians, overall):
    """상품 1건 -> (errors, warnings)"""
    errors, warnings = [], []
    pid = product.get("product_id") or product.get("product_name") or "?"

    for field in REQUIRED_INPUT:                                    # A
        if product.get(field) in (None, "", [], {}):
            errors.append(f"{pid}: 필수 입력 `{field}` 없음")
    for field in REQUIRED_DERIVED:
        if product.get(field) is None:
            errors.append(f"{pid}: 파생값 `{field}` 가 채워지지 않음 (계약 §4)")

    for field in ("secondary_category", "tertiary_category"):       # B
        value = product.get(field)
        if value is not None and value not in vocab[field]:
            errors.append(f"{pid}: `{field}` 값 {value!r} 이 어휘에 없음")

    allowed_tags = set().union(*vocab["tag"].values())
    for tag in product.get("highlights") or []:
        if tag in vocab["ingredient"]:
            errors.append(f"{pid}: 성분 {tag!r} 을 태그로 받을 수 없음 (계약 §3.1)")
        elif tag not in allowed_tags:
            warnings.append(f"{pid}: 태그 {tag!r} 이 어휘 밖 — unmapped 로 수집 (계약 §5)")

    rating = product.get("rating")                                  # C
    if rating is not None:
        if not (vocab["rating_min"] <= rating <= vocab["rating_max"]):
            errors.append(f"{pid}: rating {rating} 이 정규화 범위 "
                          f"[{vocab['rating_min']}, {vocab['rating_max']}] 밖")
        expected = medians.get(product.get("tertiary_category"), overall)
        if product.get("rating_source") == "injected" and abs(rating - expected) > 1e-6:
            warnings.append(f"{pid}: 주입 rating {rating} 이 §4.2 기준값 {expected:.4f} 와 다름")

    price_krw = product.get("price_krw")
    if isinstance(price_krw, (int, float)) and price_krw <= 0:
        errors.append(f"{pid}: price_krw 가 양수가 아님")

    if product.get("loves_count") not in (None, 0) and product.get("rating_source") == "injected":
        warnings.append(f"{pid}: 신규 등록인데 loves_count 가 0 이 아님")

    if not (product.get("highlights") or []):                       # D
        warnings.append(f"{pid}: highlights 가 비어 concern·clean·texture 블록이 0 이 된다 "
                        f"(가중치 합 0.50). 추천 노출에 불리 (계약 §3.3)")

    text = " ".join(product.get("ingredients") or [])
    if text and not any(any(s in text.lower() for s in syns)
                        for syns in vocab["synonyms"].values()):
        warnings.append(f"{pid}: 전성분에서 어휘 성분이 하나도 매칭되지 않음 "
                        f"(ingredient 블록 0, 가중치 0.27)")

    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="등록 상품 계약 검증")
    ap.add_argument("path", help="상품 JSON 또는 JSONL")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 처리")
    args = ap.parse_args(argv)

    vocab = load_vocab()
    medians, overall = rating_reference()
    products = load_products(args.path)

    all_errors, all_warnings = [], []
    for product in products:
        errors, warnings = check(product, vocab, medians, overall)
        all_errors += errors
        all_warnings += warnings

    print(f"상품 {len(products)}건 검사")
    for label, items in (("위반", all_errors), ("경고", all_warnings)):
        if not items:
            print(f"  {label} 없음")
            continue
        print(f"  {label} {len(items)}건")
        for line in items[:20]:
            print(f"    - {line}")
        if len(items) > 20:
            print(f"    ... 외 {len(items) - 20}건")

    if all_errors:
        return 2
    return 2 if (args.strict and all_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
