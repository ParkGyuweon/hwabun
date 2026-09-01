"""hidden preference 의 통제 조건을 고정한다.

여기서 막고 싶은 것
  * target 리뷰가 입력에 새어 들어가는 것 (정답을 보고 행동을 만드는 셈이 된다)
  * 실행마다 값이 달라져 재현이 안 되는 것
  * 추천 점수와 사실상 같아져 통제 장치 구실을 못 하는 것
"""
import os
import sys
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

BD = os.path.dirname(os.path.abspath(__file__))
if np is not None:
    sys.path.insert(0, BD)
    from batch.jobs.hidden_preference import WEIGHTS, HiddenPreference
    from batch.jobs.product_encoder import Encoder


def make_persona(pid, reviews, skin_type="dry", skin_tone="light"):
    return {"persona_id": pid, "skin_type": skin_type, "skin_tone": skin_tone,
            "hair_color": "brown", "eye_color": "brown", "reviews": reviews}


def review(gid, product, brand, text, rating=5):
    return {"group_id": gid, "product_name": product, "brand_name": brand,
            "review_title": "", "review_text": text, "rating": rating}


@unittest.skipIf(np is None, "numpy is required")
class HiddenPreferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = Encoder().products
        cls.hp = HiddenPreference(products=cls.products)
        cls.ids = [p["product_id"] for p in cls.products]

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(1.0, sum(WEIGHTS.values()), places=9)

    def test_score_range_and_shape(self):
        persona = make_persona("PT1", [review(self.ids[0], "a", "b", "hydrating")])
        scores = self.hp.score_all(persona, [self.ids[0]])
        self.assertEqual(len(self.products), len(scores))
        self.assertTrue(bool(np.all((scores >= 0) & (scores <= 1))))

    def test_target_review_is_not_used(self):
        """target 리뷰를 페르소나가 들고 있어도 seeds 에 없으면 점수가 같아야 한다"""
        seed_id, target_id = self.ids[0], self.ids[1]
        seed_only = make_persona("PT2", [review(seed_id, "a", "b", "hydrating gel")])
        with_target = make_persona("PT2", [
            review(seed_id, "a", "b", "hydrating gel"),
            review(target_id, "t", "tb", "this exact target product is amazing"),
        ])
        a = self.hp.score_all(seed_only, [seed_id])
        b = self.hp.score_all(with_target, [seed_id])   # seeds 에 target 없음
        np.testing.assert_allclose(a, b, atol=1e-6)

    def test_deterministic(self):
        persona = make_persona("PT3", [review(self.ids[2], "a", "b", "light cream")])
        a = self.hp.score_all(persona, [self.ids[2]])
        b = self.hp.score_all(persona, [self.ids[2]])
        np.testing.assert_allclose(a, b)

    def test_noise_seed_changes_scores(self):
        """강건성 평가를 하려면 seed 를 바꿔 다른 실행을 만들 수 있어야 한다"""
        persona = make_persona("PT4", [review(self.ids[3], "a", "b", "rich balm")])
        other = HiddenPreference(products=self.products, noise_seed=7)
        a = self.hp.score_all(persona, [self.ids[3]])
        b = other.score_all(persona, [self.ids[3]])
        self.assertFalse(bool(np.allclose(a, b)))

    def test_text_match_reacts_to_review_words(self):
        """리뷰에 쓴 말이 상품 텍스트와 겹치면 그 항목이 올라가야 한다"""
        product = self.products[0]
        words = " ".join((product.get("highlights") or ["hydrating"])[:3])
        persona = make_persona("PT5", [review(self.ids[5], "a", "b", words)])
        matched = self.hp.components(persona, [self.ids[5]],
                                     product["product_id"])["seed_review_text_match"]
        blank = make_persona("PT5", [review(self.ids[5], "a", "b", "zzz qqq")])
        unmatched = self.hp.components(blank, [self.ids[5]],
                                       product["product_id"])["seed_review_text_match"]
        self.assertGreater(matched, unmatched)

    def test_components_match_score(self):
        persona = make_persona("PT6", [review(self.ids[7], "a", "b", "gentle cleanser")])
        parts = self.hp.components(persona, [self.ids[7]], self.ids[9])
        expected = sum(WEIGHTS[k] * v for k, v in parts.items())
        got = float(self.hp.score_all(persona, [self.ids[7]])[9])
        self.assertAlmostEqual(expected, got, places=5)


if __name__ == "__main__":
    unittest.main()
