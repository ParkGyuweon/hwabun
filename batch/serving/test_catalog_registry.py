# -*- coding: utf-8 -*-
"""등록 상품 편입(Jira 216)을 고정한다.

여기서 막고 싶은 것
  * 등록 상품이 붙었을 때 **기존 200개의 LTR 피처가 한 자리라도 바뀌는 것** —
    순위 피처 분모가 카탈로그 크기를 따라가면 트리 모델이 기존 사용자의 순위를 뒤집는다
  * 계약 §4 파생값이 비는 것 (price_usd · rating 주입 · loves_count 0)
  * 어휘집 밖 브랜드·지지자 0 인 등록 상품이 전용 칸 후보에서 빠지는 것
  * 카탈로그 형식(category 배열) 변환이 어휘와 어긋나는 것
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))

import catalog_registry as cr                      # noqa: E402
from ltr_features import LtrFeatures, pop_rank_of  # noqa: E402
from persona_feature import NEUTRAL, load as load_affinity  # noqa: E402
from product_encoder import Encoder                # noqa: E402
from recommender import load_cooc, new_product_mask  # noqa: E402

SSAFY = os.path.join(ROOT, "simulator", "feedback", "products.ssafy-beauty.json")


def ssafy_inputs():
    raw = cr.vpr.load_products(SSAFY)
    return [cr.from_catalog_form(p) for p in raw]


class TestDerive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.medians, cls.overall = cr._rating_reference()
        cls.vocab = cr.vpr.load_vocab()

    def test_catalog_form_maps_category_array(self):
        x = cr.derive(ssafy_inputs()[0], self.medians, self.overall)
        self.assertEqual(x["secondary_category"], "Treatments")
        self.assertEqual(x["tertiary_category"], "Exfoliators")
        self.assertEqual(x["product_source"], "brand_registered")
        self.assertEqual(x["loves_count"], 0)
        self.assertEqual(x["rating_source"], "injected")
        self.assertEqual(x["rating"], self.medians["Exfoliators"])

    def test_price_krw_to_usd_fixed_rate(self):
        x = cr.derive({"product_name": "a", "brand_name": "B", "secondary_category": "Treatments",
                       "tertiary_category": "Face Serums", "ingredients": "Water",
                       "price_krw": 28000}, self.medians, self.overall)
        self.assertAlmostEqual(x["price_usd"], 28000 / cr.KRW_PER_USD, places=2)

    def test_price_usd_only_fills_krw_even_when_krw_key_is_none(self):
        # pydantic model_dump 는 price_krw=None 을 명시적으로 넘긴다
        x = cr.derive({"product_name": "a", "brand_name": "B", "secondary_category": "Treatments",
                       "tertiary_category": "Face Serums", "ingredients": "Water",
                       "price_usd": 22, "price_krw": None}, self.medians, self.overall)
        self.assertEqual(x["price_krw"], round(22 * cr.KRW_PER_USD))
        cr.validate(x, self.vocab, self.medians, self.overall)   # 계약 필수 price_krw 통과

    def test_all_ssafy_products_pass_contract(self):
        for inp in ssafy_inputs():
            x = cr.derive(inp, self.medians, self.overall)
            cr.validate(x, self.vocab, self.medians, self.overall)

    def test_contract_violation_raises(self):
        x = cr.derive({"product_name": "a", "brand_name": "B", "secondary_category": "Nope",
                       "tertiary_category": "Nope", "ingredients": "Water", "price_krw": 1000},
                      self.medians, self.overall)
        with self.assertRaises(cr.RegistrationError) as ctx:
            cr.validate(x, self.vocab, self.medians, self.overall)
        self.assertTrue(any("secondary_category" in e for e in ctx.exception.errors))


class TestCatalogGrowth(unittest.TestCase):
    """200 → 208 로 늘려도 기존 상품의 피처·후보 판정이 보존되는가"""

    @classmethod
    def setUpClass(cls):
        e = Encoder()
        cls.enc = e
        cls.V0 = np.asarray(e.matrix(), np.float32)
        lg = np.log1p(np.array([p["loves_count"] for p in e.products], float))
        cls.prior0 = ((lg - lg.min()) / (lg.max() - lg.min())).astype(np.float32)
        cls.index = {p["product_id"]: i for i, p in enumerate(e.products)}
        cls.aff = load_affinity(cls.index)
        cls.cooc0, cls.sup0 = load_cooc()
        medians, overall = cr._rating_reference()
        cls.recs = [cr.derive(i, medians, overall) for i in ssafy_inputs()]
        cls.n0 = len(e.products)

    def _grown(self):
        e = self.enc
        products = list(e.products)
        V = np.vstack([self.V0] + [np.asarray(e.encode(x), np.float32) for x in self.recs])
        k = len(self.recs)
        prior = cr.grow_vector(self.prior0, k, 0.0)
        cooc = cr.grow_square(self.cooc0, k)
        sup = cr.grow_vector(self.sup0, k, 0)
        index = dict(self.index)
        for x in self.recs:
            index[x["product_id"]] = len(products)
            products.append(x)
        aff = load_affinity(dict(self.index))
        grown = aff.grow([x["product_id"] for x in self.recs])
        self.assertEqual(grown, k)
        return products, V, prior, cooc, sup, index, aff

    def test_ltr_features_of_seed_products_unchanged(self):
        products, V, prior, cooc, sup, index, aff = self._grown()

        class E:  # LtrFeatures 가 읽는 것만
            blk = self.enc.blk
        E.products = self.enc.products
        f0 = LtrFeatures(E, self.V0, self.prior0, self.aff, self.cooc0, self.sup0)
        E1 = type("E1", (), {"blk": self.enc.blk, "products": products})
        f1 = LtrFeatures(E1, V, prior, aff, cooc, sup, n_ref=self.n0)
        persona = {"skin_type": "combination", "skin_tone": "light", "hair_color": "brown",
                   "eye_color": "brown"}
        seed = [self.index["P479839"], self.index["P454018"]]
        F0 = f0.make(persona, seed)
        F1 = f1.make(persona, seed)
        self.assertEqual(F1.shape, (self.n0 + len(self.recs), F0.shape[1]))
        np.testing.assert_allclose(F1[:self.n0], F0, atol=1e-6,
                                   err_msg="등록 상품을 붙였는데 기존 상품 피처가 변했다")

    def test_without_n_ref_rank_features_would_drift(self):
        # 분모를 고정하지 않으면 pop_rank 가 r/200 → r/208 로 흔들린다 — 그래서 n_ref 가 있다
        products, *_ = self._grown()
        a = pop_rank_of(self.enc.products)
        b = pop_rank_of(products)              # n_ref 없음
        c = pop_rank_of(products, self.n0)     # n_ref 고정
        self.assertFalse(np.allclose(a, b[:self.n0]))
        np.testing.assert_allclose(c[:self.n0], a)
        self.assertTrue(np.all(c[self.n0:] <= 1.0))

    def test_registered_products_are_reserved_candidates(self):
        products, V, prior, cooc, sup, index, aff = self._grown()
        known = set(self.enc.blk["brand"]["vocab"])
        brands = [p.get("brand_name") for p in products]
        m = new_product_mask(len(products), sup, brands, known)
        self.assertEqual(int(m[:self.n0].sum()), 0, "원천 200개엔 신규가 없어야 한다")
        self.assertTrue(np.all(m[self.n0:]), "등록 상품은 전부 전용 칸 후보")

    def test_affinity_neutral_for_registered(self):
        products, V, prior, cooc, sup, index, aff = self._grown()
        v = aff({"skin_type": "dry", "skin_tone": "light", "hair_color": "brown", "eye_color": "brown"})
        self.assertEqual(len(v), len(products))
        w_sum = sum(w for w in __import__("persona_feature").weights_for("dry").values())
        np.testing.assert_allclose(v[self.n0:], NEUTRAL * w_sum, atol=1e-6)


class TestRegistryFile(unittest.TestCase):
    def test_last_record_wins_and_append(self):
        with tempfile.TemporaryDirectory() as d:
            r = cr.Registry(os.path.join(d, "r.jsonl"))
            self.assertEqual(r.load(), [])
            r.append({"product_id": "A", "v": 1})
            r.append({"product_id": "B", "v": 1})
            r.append({"product_id": "A", "v": 2})
            rows = {x["product_id"]: x["v"] for x in r.load()}
            self.assertEqual(rows, {"A": 2, "B": 1})

    def test_committed_registry_has_ssafy_beauty(self):
        rows = cr.Registry().load()
        ids = {x["product_id"] for x in rows}
        self.assertTrue({f"SB00000{i}" for i in range(1, 9)} <= ids)
        for x in rows:
            self.assertEqual(x["brand_name"], "SSAFY Beauty")
            self.assertEqual(x["product_source"], "brand_registered")
            self.assertIsNotNone(x["rating"])


if __name__ == "__main__":
    unittest.main()
