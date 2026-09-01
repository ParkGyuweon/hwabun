"""샘플 산출물과 문서가 지금 코드와 어긋나지 않았는지 확인한다.

어휘집이 0.3 -> 0.4 로 가는 동안 문서가 93차원에 멈춰 있었다. 그때 빠진 것이
정확도의 대부분을 설명하는 brand 블록이라, 문서만 읽은 사람은 실제와 다른 그림을
갖게 됐다. 같은 사고를 막기 위해 **커밋된 산출물을 지금 코드로 다시 만들어 비교한다.**

어휘집이나 가중치를 바꾼 뒤 이 테스트가 깨지면, 고칠 것은 테스트가 아니라 산출물이다:
    python batch/ingest/build_feature_sample.py
"""
import json
import os
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
SAMPLE = os.path.join(ROOT, "batch", "ingest", "data", "feature_sample.json")
DOC = os.path.join(ROOT, "docs", "ai", "product-feature-sample.md")

if np is not None:
    from batch.ingest.build_feature_sample import build


@unittest.skipIf(np is None, "numpy is required")
@unittest.skipUnless(os.path.exists(SAMPLE), "먼저 build_feature_sample.py 를 실행하세요")
class FeatureSampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SAMPLE, encoding="utf-8") as f:
            cls.saved = json.load(f)
        cls.fresh = build()
        with open(DOC, encoding="utf-8") as f:
            cls.doc = f.read()

    def test_saved_sample_matches_current_code(self):
        """커밋된 산출물이 지금 인코더가 만드는 값과 같아야 한다"""
        self.assertEqual(self.saved["vocab_version"], self.fresh["vocab_version"])
        self.assertEqual(self.saved["n_dim"], self.fresh["n_dim"])
        self.assertEqual([p["product_id"] for p in self.saved["products"]],
                         [p["product_id"] for p in self.fresh["products"]])
        for old, new in zip(self.saved["products"], self.fresh["products"]):
            np.testing.assert_allclose(old["벡터"], new["벡터"], atol=1e-5,
                                       err_msg=old["product_id"])
            self.assertAlmostEqual(old["prior_score"], new["prior_score"], places=4)

    def test_vector_dimension_matches_vocab(self):
        for p in self.saved["products"]:
            self.assertEqual(self.saved["n_dim"], len(p["벡터"]), p["product_id"])
            # 인코더는 전체 L2 정규화까지 끝낸 벡터를 낸다
            self.assertAlmostEqual(1.0, float(np.linalg.norm(p["벡터"])), places=4)

    def test_brand_sibling_is_included(self):
        """brand 블록을 보여주려면 같은 브랜드 쌍이 있어야 한다"""
        brands = [p["brand_name"] for p in self.saved["products"]]
        self.assertLess(len(set(brands)), len(brands))

    def test_doc_is_current(self):
        """문서가 산출물과 같은 어휘집·차원을 말하고 있어야 한다"""
        self.assertIn(f"`{self.saved['vocab_version']}`", self.doc)
        self.assertIn(f"{self.saved['n_dim']}차원", self.doc)
        self.assertNotIn("93차원", self.doc)
        for p in self.saved["products"]:
            self.assertIn(p["brand_name"], self.doc, p["product_id"])


if __name__ == "__main__":
    unittest.main()
