# -*- coding: utf-8 -*-
"""CF 가점이 **가점 전용**인지 (Jira 174).

여기서 막으려는 사고는 둘이다.
  ① CF 를 안 줬는데 점수가 달라지는 것 — 기존 수치가 조용히 흔들린다
  ② 이력이 없는 상품이 **바닥으로 밀리는 것** — minmax 혼합의 실패 모양이다
"""
import os
import sys
import unittest

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

from recommender import CF_MIN_SUPPORT, Recommender, cf_bonus  # noqa: E402
from user_vector import UserVector                             # noqa: E402


def make(n=6, dim=4):
    rng = np.random.default_rng(0)
    M = rng.random((n, dim)).astype(np.float32)
    M /= np.linalg.norm(M, axis=1, keepdims=True)
    index = {f"P{i}": i for i in range(n)}
    prior = np.linspace(0.1, 1.0, n).astype(np.float32)
    return M, index, prior


class TestCfBonus(unittest.TestCase):
    def setUp(self):
        self.M, self.index, self.prior = make()
        self.cooc = np.zeros((6, 6), np.float32)
        # P0 을 산 사람이 P1 도 샀다. P5 는 아무와도 안 묶인다(= 신규 상품)
        self.cooc[0, 1] = self.cooc[1, 0] = 0.9
        self.cooc[0, 2] = self.cooc[2, 0] = 0.3
        self.state = UserVector()
        self.state.observe({"event_name": "add_to_cart", "product_id": "P0",
                            "properties": {}})

    def test_CF_를_안_주면_점수가_한_자리도_안_바뀐다(self):
        a = Recommender(self.M, self.index, self.prior).score(self.state)
        b = Recommender(self.M, self.index, self.prior,
                        cooc=None).score(self.state)
        np.testing.assert_array_equal(a, b)

    def test_가점_전용이라_점수가_내려가지_않는다(self):
        base = Recommender(self.M, self.index, self.prior).score(self.state)
        got = Recommender(self.M, self.index, self.prior,
                          cooc=self.cooc).score(self.state)
        self.assertTrue(np.all(got >= base - 1e-6),
                        "CF 를 켰는데 내려간 상품이 있다 — 가점 전용이 아니다")

    def test_이력_없는_상품은_중앙값을_받는다(self):
        """0 을 주면 '모른다' 를 '나쁘다' 로 취급해 신규 상품을 바닥으로 민다"""
        b = cf_bonus(self.cooc, [0])
        self.assertGreater(b[5], 0.0, "이력 없는 상품이 0 을 받았다")
        # 이력이 있는 상품(P1·P2)의 중앙값을 받아야 한다
        seen = sorted(x for x in b if x > 0 and x != b[5])
        import statistics
        self.assertAlmostEqual(float(b[5]), statistics.median(seen), places=5)

    def test_이력_없는_상품이_많아도_중립값이_0_이_되지_않는다(self):
        """플랫폼 초기 — 상품 대부분이 신규다. 여기서 0 이 되면 아무 의미가 없다"""
        sparse = np.zeros((6, 6), np.float32)
        sparse[0, 1] = sparse[1, 0] = 0.9      # 이력이 있는 상품이 단 하나
        b = cf_bonus(sparse, [0])
        self.assertGreater(b[5], 0.0, "이력 없는 상품 다수일 때 중립값이 0 이 됐다")

    def test_지지자가_모자라면_가점이_막힌다(self):
        """이력이 여럿 있는 상태여야 중앙값이 '중간' 이 된다"""
        cooc = np.zeros((6, 6), np.float32)
        for j, w in ((1, 0.9), (2, 0.6), (3, 0.4), (4, 0.2)):
            cooc[0, j] = cooc[j, 0] = w
        sup = np.full(6, 9)
        sup[1] = CF_MIN_SUPPORT - 1           # 원래 1등이던 P1 만 임계 미만
        free = cf_bonus(cooc, [0])
        gated = cf_bonus(cooc, [0], supporters=sup)
        self.assertAlmostEqual(float(free[1]), 1.0, places=5)
        self.assertLess(float(gated[1]), 1.0,
                        "임계 미만인데 가점이 안 막혔다")

    def test_이력이_아예_없으면_항이_꺼진다(self):
        self.assertIsNone(cf_bonus(np.zeros((6, 6), np.float32), [0]))
        self.assertIsNone(cf_bonus(self.cooc, []))
        self.assertIsNone(cf_bonus(None, [0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
