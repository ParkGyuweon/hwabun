"""MMR 다양성 보정의 계약을 고정한다.

여기서 막고 싶은 것
  * lam=1.0 인데 순서가 바뀌는 것 (끈 상태가 끈 상태가 아니게 된다)
  * 다양성을 준다면서 점수가 낮은 것을 먼저 올리는 것 (1등은 항상 1등이어야 한다)
  * 후보가 k 개 미만일 때 죽는 것
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
    from batch.jobs.recommender import LAMBDA_MMR, Recommender


@unittest.skipIf(np is None, "numpy is required")
class MmrTest(unittest.TestCase):
    def setUp(self):
        # 0·1·2 는 서로 거의 같고, 3·4 는 다른 방향이다
        m = np.array([[1.0, 0.0], [0.99, 0.14], [0.98, 0.2],
                      [0.0, 1.0], [0.2, 0.98]], dtype=np.float32)
        m /= np.linalg.norm(m, axis=1, keepdims=True)
        ids = {f"P{i}": i for i in range(len(m))}
        self.rec = Recommender(m, ids, np.zeros(len(m), np.float32))
        self.scores = np.array([1.0, 0.95, 0.9, 0.85, 0.8], dtype=np.float32)
        self.order = [0, 1, 2, 3, 4]

    def test_lambda_one_keeps_score_order(self):
        self.assertEqual([0, 1, 2], self.rec.mmr(self.scores, self.order, 3, 1.0))

    def test_top1_is_always_the_best_score(self):
        for lam in (1.0, 0.8, 0.5, 0.1):
            self.assertEqual(0, self.rec.mmr(self.scores, self.order, 3, lam)[0], lam)

    def test_diversity_pulls_up_the_different_one(self):
        """비슷한 것끼리 몰려 있으면 다른 방향의 후보가 앞으로 온다"""
        picked = self.rec.mmr(self.scores, self.order, 3, 0.5)
        self.assertEqual(0, picked[0])
        self.assertIn(3, picked[:3])          # 점수는 4등이지만 방향이 다르다
        self.assertNotEqual([0, 1, 2], picked)

    def test_fewer_candidates_than_k(self):
        self.assertEqual([0, 1], self.rec.mmr(self.scores, [0, 1], 5, 0.8))
        self.assertEqual([2], self.rec.mmr(self.scores, [2], 5, 0.8))
        self.assertEqual([], self.rec.mmr(self.scores, [], 5, 0.8))

    def test_default_is_enabled(self):
        """계약이 정한 단계라 기본값이 켜져 있어야 한다"""
        self.assertLess(LAMBDA_MMR, 1.0)


if __name__ == "__main__":
    unittest.main()
