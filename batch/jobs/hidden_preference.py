"""
hidden preference — 시뮬레이션 사용자가 "이 상품을 실제로 좋아할 법한 정도" (0~1).

**추천 점수와 분리하기 위한 통제 장치다.** 추천 rank 는 어떤 상품이 노출될지에만
쓰고, 노출된 뒤의 행동(체류·찜·장바구니·이탈)은 이 점수가 정한다. 그래야 추천이
자기 순위로 긍정 행동을 만들고 그 행동으로 자기 성능을 재는 순환 평가가 줄어든다.
계약: docs/ai/evaluation-framework.md 2절

    hidden_pref(u, i) =
        0.30 * seed_review_text_match(u, i)
      + 0.20 * product_attribute_match(u, i)
      + 0.15 * category_match(u, i)
      + 0.10 * brand_affinity(u, i)
      + 0.10 * price_match(u, i)
      + 0.10 * product_quality(i)
      + 0.05 * noise

**현실의 정답이 아니다.** 이 점수가 맞다고 주장하지 않는다. 하나의 공식·하나의
seed 결과만 보고하지 않고 여러 가정에서 결과가 유지되는지 함께 본다(10단계).

누출 방지
    - seed(과거 긍정 리뷰)만 쓴다. target 상품에 대해 그 사용자가 쓴 리뷰와
      target 이후 행동은 입력에 넣지 않는다. 호출부가 seeds 를 넘긴다.
    - 상품 쪽 텍스트(설명·성분·하이라이트)는 사용자와 무관하므로 쓸 수 있다.

추천 모델과의 분리
    - 가장 큰 항(0.30)은 **리뷰 텍스트**다. 추천 모델은 리뷰 텍스트를 쓰지 않는다
      (정확도 목적 27개 구성이 전부 실패해 닫은 길이라 되돌리지 않는다).
    - `product_attribute_match` 는 추천의 속성 친화도와 신호가 겹친다. 완전한 분리는
      한 데이터셋 안에서 불가능하므로, 여기서는 축소·클리핑 없는 **원 구성비**를 쓰고
      가중치를 0.20 으로 제한한다. 이 겹침은 보고할 때 명시한다.
"""
import hashlib
import json
import math
import os
import re
from collections import Counter

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
# 프론트가 수집한 상세 설명. 있으면 텍스트가 풍부해지고, 없어도 동작한다
DESCRIPTIONS = os.path.join(ROOT, "frontend", "src", "mocks", "products.collected.json")

WEIGHTS = {
    "seed_review_text_match": 0.30,
    "product_attribute_match": 0.20,
    "category_match": 0.15,
    "brand_affinity": 0.10,
    "price_match": 0.10,
    "product_quality": 0.10,
    "noise": 0.05,
}

POSITIVE_RATING = 4          # 이 점수 이상을 긍정 seed 로 본다
_TOKEN = re.compile(r"[a-z]{3,}")
_STOP = frozenset("""
the and for with this that have has was were are but you your not all from out
its it's about into more some very just they them then than when what which who
will would can could should product products skin use used using really feel
felt love loved like liked buy bought try tried get got make makes made after
before while because also there their his her him she he too much many any one
two day days week weeks month months time times bit lot little
""".split())


def tokens(text):
    return [t for t in _TOKEN.findall(str(text).lower()) if t not in _STOP]


def _clip01(x):
    return float(min(1.0, max(0.0, x)))


class HiddenPreference:
    """상품 쪽 표현은 한 번만 만들어 두고 페르소나마다 재사용한다"""

    def __init__(self, products=None, descriptions=None, weights=None, noise_seed=0):
        self.products = products if products is not None else _load(PRODUCTS)
        self.weights = dict(weights or WEIGHTS)
        self.noise_seed = noise_seed
        self.index = {p["product_id"]: i for i, p in enumerate(self.products)}
        self.n = len(self.products)

        desc = descriptions if descriptions is not None else _load(DESCRIPTIONS, {})
        self._docs = [self._product_tokens(p, desc.get(p["product_id"]))
                      for p in self.products]
        self._idf = self._build_idf(self._docs)
        self._doc_vecs = [self._vector(doc) for doc in self._docs]

        self._price = np.array([float(p.get("price_usd") or 0) for p in self.products])
        self._quality = self._build_quality()
        self._segment_share = [self._shares(p) for p in self.products]

    # ── 상품 쪽 준비 ────────────────────────────────────────────────────
    def _product_tokens(self, product, description):
        """상품 텍스트 — 이름·하이라이트·전성분·수집한 상세 설명"""
        parts = [product.get("product_name", ""), product.get("brand_name", "")]
        parts += list(product.get("highlights") or [])
        parts.append(str(product.get("ingredients") or "")[:2000])
        if isinstance(description, dict):
            for value in (description.get("description") or description).values():
                if isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, list):
                    parts.extend(str(v) for v in value)
        return tokens(" ".join(parts))

    def _build_idf(self, docs):
        df = Counter()
        for doc in docs:
            df.update(set(doc))
        total = max(len(docs), 1)
        return {term: math.log(total / (1 + count)) + 1.0 for term, count in df.items()}

    def _vector(self, doc):
        """IDF 가중 tf 벡터를 dict 로. 200개뿐이라 희소 dict 로 충분하다"""
        counts = Counter(doc)
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def _build_quality(self):
        rating = np.array([float(p.get("rating") or 0) for p in self.products])
        reviews = np.log1p([float((p.get("_review_stats") or {}).get("review_count", 0))
                            for p in self.products])
        def scale(x):
            lo, hi = x.min(), x.max()
            return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)
        return 0.6 * scale(rating) + 0.4 * scale(reviews)

    def _shares(self, product):
        """상품 리뷰어의 속성 구성비. 축소·클리핑 없는 원 값이다"""
        counts = (product.get("_review_stats") or {}).get("segment_counts") or {}
        out = {}
        for attr, buckets in counts.items():
            total = sum(buckets.values()) or 1
            out[attr] = {seg: n / total for seg, n in buckets.items()}
        return out

    # ── 페르소나 쪽 ─────────────────────────────────────────────────────
    def profile(self, persona, seeds):
        """seed 로부터 사용자 표현을 만든다. target 은 호출부가 이미 뺐다"""
        seed_set = set(seeds)
        reviews = [r for r in persona.get("reviews", [])
                   if r.get("group_id") in seed_set
                   and (r.get("rating") or 0) >= POSITIVE_RATING]
        text = " ".join(f"{r.get('review_title') or ''} {r.get('review_text') or ''}"
                        for r in reviews)
        brands = Counter(r.get("brand_name") for r in reviews if r.get("brand_name"))
        cats, prices = Counter(), []
        for gid in seeds:
            i = self.index.get(gid)
            if i is None:
                continue
            product = self.products[i]
            cats[product.get("tertiary_category")] += 1
            if product.get("price_usd"):
                prices.append(float(product["price_usd"]))
        return {
            "vector": self._vector(tokens(text)),
            "brands": brands,
            "categories": cats,
            "prices": prices,
            "skin_type": persona.get("skin_type"),
            "skin_tone": persona.get("skin_tone"),
        }

    # ── 항목별 점수 ─────────────────────────────────────────────────────
    def _text_match(self, profile, i):
        user, doc = profile["vector"], self._doc_vecs[i]
        if not user or not doc:
            return 0.0
        small, large = (user, doc) if len(user) < len(doc) else (doc, user)
        cos = sum(v * large.get(t, 0.0) for t, v in small.items())
        # 코사인은 실측 0~0.35 구간에 몰린다. 그 구간을 0~1 로 편다
        return _clip01(cos / 0.35)

    def _attribute_match(self, profile, i):
        shares = self._segment_share[i]
        out, used = 0.0, 0
        for attr in ("skin_type", "skin_tone"):
            seg = profile.get(attr)
            table = shares.get(attr) or {}
            if not seg or not table:
                continue
            base = 1.0 / max(len(table), 1)          # 균등 대비 몇 배인가
            out += _clip01((table.get(seg, 0.0) / base - 0.5) / 1.5)
            used += 1
        return out / used if used else 0.5

    def _category_match(self, profile, i):
        cats = profile["categories"]
        if not cats:
            return 0.5
        return _clip01(cats.get(self.products[i].get("tertiary_category"), 0)
                       / max(cats.values()))

    def _brand_affinity(self, profile, i):
        brands = profile["brands"]
        if not brands:
            return 0.5
        return _clip01(brands.get(self.products[i].get("brand_name"), 0)
                       / max(brands.values()))

    def _price_match(self, profile, i):
        prices = profile["prices"]
        price = self._price[i]
        if not prices or price <= 0:
            return 0.5
        center = float(np.median(prices))
        if center <= 0:
            return 0.5
        # 가격은 배수로 느낀다. 2배 차이면 0 에 가깝게 떨어뜨린다
        return _clip01(1.0 - abs(math.log(price / center)) / math.log(2.5))

    def _noise(self, persona_id, product_id):
        """페르소나·상품·seed 로 결정되는 재현 가능한 잡음"""
        key = f"{self.noise_seed}|{persona_id}|{product_id}".encode()
        return int(hashlib.md5(key).hexdigest()[:8], 16) / 0xFFFFFFFF

    # ── 공개 API ────────────────────────────────────────────────────────
    def components(self, persona, seeds, product_id):
        """항목별 값. 왜 그 점수인지 설명할 때 쓴다"""
        i = self.index[product_id]
        profile = self.profile(persona, seeds)
        return {
            "seed_review_text_match": self._text_match(profile, i),
            "product_attribute_match": self._attribute_match(profile, i),
            "category_match": self._category_match(profile, i),
            "brand_affinity": self._brand_affinity(profile, i),
            "price_match": self._price_match(profile, i),
            "product_quality": float(self._quality[i]),
            "noise": self._noise(persona["persona_id"], product_id),
        }

    def score_all(self, persona, seeds):
        """모든 상품에 대한 hidden preference (상품수,) 배열"""
        profile = self.profile(persona, seeds)
        w = self.weights
        out = np.zeros(self.n, dtype=np.float32)
        for i, product in enumerate(self.products):
            out[i] = (
                w["seed_review_text_match"] * self._text_match(profile, i)
                + w["product_attribute_match"] * self._attribute_match(profile, i)
                + w["category_match"] * self._category_match(profile, i)
                + w["brand_affinity"] * self._brand_affinity(profile, i)
                + w["price_match"] * self._price_match(profile, i)
                + w["product_quality"] * float(self._quality[i])
                + w["noise"] * self._noise(persona["persona_id"],
                                           product["product_id"])
            )
        return np.clip(out, 0.0, 1.0)


def _load(path, default=None):
    if not os.path.exists(path):
        if default is None:
            raise SystemExit(f"파일이 없습니다: {path}")
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    personas = _load(os.path.join(ROOT, "simulator", "personas", "data",
                                  "personas_9900.json"))
    hp = HiddenPreference()
    persona = personas[0]
    seeds = []
    for r in persona["reviews"]:
        if r["group_id"] in hp.index and r["group_id"] not in seeds:
            seeds.append(r["group_id"])
    target, seeds = seeds[-1], seeds[:-1]

    scores = hp.score_all(persona, seeds)
    order = np.argsort(-scores)
    print(f"{persona['persona_id']} · seed {len(seeds)}개 · target {target}")
    print(f"hidden preference  평균 {scores.mean():.3f} · "
          f"최소 {scores.min():.3f} · 최대 {scores.max():.3f}\n")
    print("상위 5")
    for i in order[:5]:
        p = hp.products[i]
        print(f"  {scores[i]:.3f}  {p['brand_name'][:12]:<12} {p['product_name'][:40]}")
    print("\n하위 3")
    for i in order[-3:]:
        p = hp.products[i]
        print(f"  {scores[i]:.3f}  {p['brand_name'][:12]:<12} {p['product_name'][:40]}")
    print(f"\ntarget 항목별: "
          + " · ".join(f"{k} {v:.2f}" for k, v in
                       hp.components(persona, seeds, target).items()))
