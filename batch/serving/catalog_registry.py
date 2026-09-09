"""등록 상품을 추천 카탈로그에 **즉시** 편입한다 (Jira 216).

실서비스 흐름
    판매자 등록 → 쇼핑몰 백엔드 승인 → POST /api/products (이 서버) → 다음 요청부터 추천 후보

계약 `contracts/product-registration-spec.md` 의 입력 필드를 받아 §4 파생값을 채우고
(price_krw→price_usd 고정 환율 · rating 카테고리 중앙값 주입 · loves_count 0),
`contracts/validate_product_registration.py` 의 검사를 그대로 통과시킨 뒤
어휘집으로 인코딩한다. 어휘집 밖 브랜드는 brand 블록이 0 벡터가 되고, 지지자 0 이라
`Recommender.new_mask()` 가 곧바로 전용 칸(reserved) 후보로 본다.

원천 카탈로그 200개는 `products_200.json` 그대로 두고, 등록 상품은
`batch/ingest/data/serving/registered_products.jsonl` 에 **파생값까지 채운 기록**으로 쌓아
서버가 재시작할 때 다시 읽는다. 오프라인 평가(`eval_*`)는 이 파일을 읽지 않으므로
holdout 수치는 흔들리지 않는다.

    python batch/serving/catalog_registry.py simulator/feedback/products.ssafy-beauty.json
        → 카탈로그 형식(category 배열·ingredients 리스트)을 등록 입력으로 바꿔 jsonl 에 쓴다
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from typing import Iterable

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "contracts"))
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))

import validate_product_registration as vpr          # noqa: E402

REGISTERED_PATH = os.path.join(ROOT, "batch", "ingest", "data", "serving",
                               "registered_products.jsonl")

# 계약 §4.1 — 등록 시점 고정 환율. 구간 경계가 넓어(0/20/35/50/80 USD) ±10% 오차로
# 구간이 바뀌는 상품은 드물다. 실시간 조회는 하지 않는다.
KRW_PER_USD = 1400.0

INPUT_FIELDS = ("product_id", "product_name", "brand_name", "brand_id",
                "secondary_category", "tertiary_category", "highlights",
                "ingredients", "price_krw", "price_usd", "image_url")


class RegistrationError(ValueError):
    """계약 위반 — 호출자가 4xx 로 바꾼다"""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _rating_reference():
    """§4.2 — tertiary_category 중앙값(표본 3개 이상), 아니면 전체 중앙값"""
    return vpr.rating_reference()


def derive(inp: dict, medians=None, overall=None) -> dict:
    """등록 입력 → 인코더가 읽을 수 있는 상품 기록. 계약 §4 파생값을 채운다."""
    if medians is None:
        medians, overall = _rating_reference()
    x = {k: inp.get(k) for k in INPUT_FIELDS if k in inp}
    x["product_name"] = inp.get("product_name")
    x["brand_name"] = inp.get("brand_name")
    x["secondary_category"] = inp.get("secondary_category")
    x["tertiary_category"] = inp.get("tertiary_category")
    x["highlights"] = list(inp.get("highlights") or [])
    ing = inp.get("ingredients") or []
    # 인코더는 `ingredients` 를 문자열 리스트로 읽고 join 한다. 문자열 하나로 와도 받는다
    x["ingredients"] = [ing] if isinstance(ing, str) else list(ing)

    # §4.1 가격
    if x.get("price_usd") is None and inp.get("price_krw") is not None:
        x["price_usd"] = round(float(inp["price_krw"]) / KRW_PER_USD, 2)
    if x.get("price_usd") is not None:
        x["price_usd"] = float(x["price_usd"])
        if x.get("price_krw") is None:          # pydantic 이 None 을 명시적으로 넘겨도 채운다
            x["price_krw"] = round(x["price_usd"] * KRW_PER_USD)

    # §4.2 rating 주입 — 실측이 있으면 observed 로 둔다
    if inp.get("rating") is not None:
        x["rating"], x["rating_source"] = float(inp["rating"]), "observed"
    else:
        x["rating"] = float(medians.get(x["tertiary_category"], overall))
        x["rating_source"] = "injected"

    # 인기 prior 입력 — 신규 등록은 0 (계약 §4 표)
    x["loves_count"] = int(inp.get("loves_count") or 0)
    x["product_id"] = inp.get("product_id") or f"R{int(time.time() * 1000) % 10**9:09d}"
    x["product_source"] = "brand_registered"
    x["registered_at"] = inp.get("registered_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
    # LtrFeatures.pop_rank_of 가 읽는 자리 — 리뷰 0 이면 인기 순위 최하위
    x["_review_stats"] = {"review_count": int(inp.get("review_count") or 0)}
    return x


def validate(x: dict, vocab=None, medians=None, overall=None):
    """계약 검사기 그대로. errors 가 있으면 RegistrationError, warnings 는 돌려준다"""
    vocab = vocab or vpr.load_vocab()
    if medians is None:
        medians, overall = _rating_reference()
    errors, warnings = vpr.check(x, vocab, medians, overall)
    if errors:
        raise RegistrationError(errors)
    return warnings


def from_catalog_form(p: dict) -> dict:
    """시연 카탈로그 형식(`products.ssafy-beauty.json`) → 등록 입력.

    `category: [대, 중, 소]` 를 secondary/tertiary 로 풀고, rating/loves 는 비워
    §4 규칙이 채우게 한다. 실서비스에서는 백엔드가 계약 필드로 바로 보낸다.
    """
    cat = p.get("category") or []
    out = {
        "product_id": p.get("product_id"),
        "product_name": p.get("product_name"),
        "brand_name": p.get("brand_name"),
        "brand_id": p.get("brand_id"),
        "secondary_category": p.get("secondary_category") or (cat[1] if len(cat) > 1 else None),
        "tertiary_category": p.get("tertiary_category") or (cat[2] if len(cat) > 2 else None),
        "highlights": p.get("highlights") or [],
        "ingredients": p.get("ingredients") or [],
        "image_url": p.get("image_url"),
        "review_count": p.get("review_count") or 0,
    }
    if p.get("price_usd") is not None:
        out["price_usd"] = p["price_usd"]
    if p.get("price_krw") is not None:
        out["price_krw"] = p["price_krw"]
    return out


class Registry:
    """등록 상품 기록의 영속 저장. 한 줄에 파생값까지 채운 상품 하나."""

    def __init__(self, path=REGISTERED_PATH):
        self.path = path

    def load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        seen, out = {}, []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    seen[r["product_id"]] = r          # 같은 id 는 마지막 기록이 이긴다
        for r in seen.values():
            out.append(r)
        return out

    def append(self, x: dict):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


def grow_square(S, k):
    """(N,N) 동시발생 행렬에 신규 k 행·열(0)을 붙인다. 신규는 아직 아무와도 같이 안 골라졌다"""
    if S is None:
        return None
    N = S.shape[0]
    out = np.zeros((N + k, N + k), S.dtype)
    out[:N, :N] = S
    return out


def grow_vector(v, k, fill=0.0):
    if v is None:
        return None
    return np.concatenate([np.asarray(v), np.full(k, fill, np.asarray(v).dtype)])


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="카탈로그 형식 파일을 등록 입력으로 바꿔 registered_products.jsonl 에 쓴다")
    ap.add_argument("path", help="카탈로그 형식 JSON (예: simulator/feedback/products.ssafy-beauty.json)")
    ap.add_argument("--out", default=REGISTERED_PATH)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    raw = vpr.load_products(a.path)
    vocab = vpr.load_vocab(); medians, overall = _rating_reference()
    reg = Registry(a.out)
    have = {r["product_id"] for r in reg.load()}
    n_new = 0
    for p in raw:
        x = derive(from_catalog_form(p), medians, overall)
        warns = validate(x, vocab, medians, overall)
        tag = "있음" if x["product_id"] in have else "신규"
        print(f"{x['product_id']}  {x['brand_name']}  {x['secondary_category']}/{x['tertiary_category']}"
              f"  ${x['price_usd']}  rating {x['rating']:.3f}({x['rating_source']})  [{tag}]")
        for w in warns:
            print("   ⚠", w)
        if tag == "신규" and not a.dry_run:
            reg.append(x); n_new += 1
    print(f"→ {n_new}건 추가 ({a.out})")


if __name__ == "__main__":
    _main(sys.argv[1:])
