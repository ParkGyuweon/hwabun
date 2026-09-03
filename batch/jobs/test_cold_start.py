"""신규 상품·신규 사이트가 들어와도 점수가 나오는가 (Jira 105).

브랜드가 자기 상품을 직접 등록하면 두 가지가 없다.

    rating        리뷰가 0건이라 없다. 그대로 두면 정규화식이 터지고, 0 을 넣으면
                  음수가 나온다. 브랜드에게 직접 받을 수도 없다 — 자기 평점을
                  적으면 그게 곧 추천 점수가 된다
    loves_count   마찬가지로 없다. 인기도 항의 재료다

그리고 사이트마다 파는 상품이 다르다. 인기도를 카탈로그 200개 전체에서 재면
자기 상품 20개만 파는 사이트는 그 20개가 전역 순위 아래쪽에 몰려 **인기도 항이
아무것도 구분하지 못한다.**
"""
import os
import sys
import unittest

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from batch.jobs.product_encoder import Encoder                   # noqa: E402
from batch.jobs.recommender import Recommender, prior_in_catalog  # noqa: E402


class RatingDefaultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Encoder()
        cls.sample = dict(cls.e.products[0])

    def test_missing_rating_falls_back_to_category_median(self):
        """평점이 없으면 같은 카테고리의 중앙값. 유리하지도 불리하지도 않다"""
        x = {**self.sample, "rating": None, "tertiary_category": "Face Serums"}
        med = self.e._rating_median("Face Serums")
        expect = (med - self.e.rmin) / (self.e.rmax - self.e.rmin)
        self.assertAlmostEqual(expect, self.e.rating_value(x), places=6)

    def test_unknown_category_falls_back_to_global_median(self):
        x = {**self.sample, "rating": None, "tertiary_category": "처음 보는 카테고리"}
        self.assertAlmostEqual(
            (self.e._rating_median(None) - self.e.rmin)
            / (self.e.rmax - self.e.rmin),
            self.e.rating_value(x), places=6)

    def test_out_of_range_rating_is_clamped(self):
        """카탈로그에서 잰 min/max 라 실제 리뷰가 쌓이면 범위를 벗어날 수 있다"""
        self.assertEqual(1.0, self.e.rating_value({**self.sample, "rating": 5.0}))
        self.assertEqual(0.0, self.e.rating_value({**self.sample, "rating": 1.0}))

    def test_existing_catalog_is_unchanged(self):
        """기존 200개는 범위 안이라 자르기가 걸리지 않는다 — 벡터가 안 바뀐다"""
        vals = [self.e.rating_value(p) for p in self.e.products]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in vals))
        self.assertTrue(any(0.0 < v < 1.0 for v in vals))

    def test_missing_loves_count_is_zero(self):
        e = Encoder()
        e.products = [dict(p) for p in e.products[:3]]
        e.products[0].pop("loves_count", None)
        p = e.prior()
        self.assertEqual(3, len(p))
        self.assertTrue(np.isfinite(p).all())


class CatalogPriorTest(unittest.TestCase):
    def setUp(self):
        self.prior = np.array([0.0, 0.1, 0.2, 0.9, 1.0])

    def test_renormalized_inside_the_site(self):
        """사이트가 파는 3개 안에서 0~1 로 다시 편다"""
        out = prior_in_catalog(self.prior, [0, 1, 2])
        self.assertAlmostEqual(0.0, out[0])
        self.assertAlmostEqual(0.5, out[1])
        self.assertAlmostEqual(1.0, out[2])

    def test_products_outside_the_site_are_zero(self):
        out = prior_in_catalog(self.prior, [0, 1, 2])
        self.assertEqual(0.0, out[3])
        self.assertEqual(0.0, out[4])

    def test_single_product_site_gets_zero(self):
        """펼 수 없다. 후보가 하나면 인기도 항이 순위에 영향을 주지 않는 것이 맞다"""
        self.assertEqual(0.0, prior_in_catalog(self.prior, [3])[3])

    def test_empty_catalog(self):
        self.assertTrue((prior_in_catalog(self.prior, []) == 0).all())


class CatalogScopeTest(unittest.TestCase):
    def test_recommender_limits_candidates_to_the_site(self):
        e = Encoder()
        M = np.asarray(e.matrix(), np.float32)
        index = {p["product_id"]: i for i, p in enumerate(e.products)}
        prior = np.asarray(e.prior(), float)
        site = [p["product_id"] for p in e.products[:15]]
        rec = Recommender(M, index, prior, catalog=site)

        self.assertEqual(15, len(rec.catalog))
        # 사이트 밖 상품의 인기도는 0 이고, 안쪽은 0~1 로 다시 펴진다
        self.assertEqual(0.0, rec.prior[20])
        inside = rec.prior[rec.catalog]
        self.assertAlmostEqual(0.0, float(inside.min()))
        self.assertAlmostEqual(1.0, float(inside.max()))


if __name__ == "__main__":
    unittest.main()
