"""성분 규제 보정 규칙 (2026-09-29) — 기본 끔, 켜면 고시 원료 1.0 · 산화아연은 SPF 로만.

전성분은 함량순이지만 **1% 이하 성분은 순서에 상관없이 적을 수 있다** (화장품법 시행규칙 별표 4).
그래서 고시 함량이 0.04% 인 아데노신은 효능 함량이어도 뒤쪽에 온다. 서빙 LTR 모델은 이 규칙 없이
학습됐으므로 **기본은 꺼져 있어야 하고, 꺼져 있을 때 벡터가 예전과 비트 단위로 같아야 한다.**
"""
import os
import sys
import unittest
from unittest import mock

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
from batch.jobs.product_encoder import Encoder, REGULATORY_RULE_ENV   # noqa: E402

# 아데노신이 맨 뒤, 산화아연(무기자차)만 있고 zinc pca 는 없는 가상 선크림
LATE = {"product_id": "T1", "product_name": "Test Cream", "highlights": [],
        "ingredients": ["Water, Glycerin, Butylene Glycol, Dimethicone, Zinc Oxide, "
                        "Squalane, Panthenol, Allantoin, Niacinamide, Adenosine"]}


class RegulatoryRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.dict(os.environ, {REGULATORY_RULE_ENV: ""}):
            cls.off = Encoder()
        cls.on = Encoder(regulatory_rule=True)

    def test_default_off(self):
        self.assertFalse(self.off.regulatory_rule)
        v = self.off.ingredient_values(LATE)
        self.assertLess(v["Adenosine"], 1.0)
        self.assertIn("Zinc", v)                 # 예전 동작: 산화아연이 Zinc 도 켠다

    def test_env_turns_on(self):
        with mock.patch.dict(os.environ, {REGULATORY_RULE_ENV: "1"}):
            self.assertTrue(Encoder().regulatory_rule)

    def test_functional_full_weight(self):
        v = self.on.ingredient_values(LATE)
        self.assertEqual(v["Adenosine"], 1.0)
        self.assertEqual(v["Niacinamide"], 1.0)
        # 고시 원료가 아닌 성분은 위치가중 그대로
        self.assertEqual(v["Squalane"], self.off.ingredient_values(LATE)["Squalane"])

    def test_zinc_oxide_only_spf(self):
        v = self.on.ingredient_values(LATE)
        self.assertNotIn("Zinc", v)
        self.assertIn("SPF", v)
        pca = dict(LATE, ingredients=["Water, Zinc PCA, Zinc Oxide"])
        self.assertIn("Zinc", self.on.ingredient_values(pca))

    def test_off_matrix_unchanged_by_rule_key(self):
        """규칙 키가 어휘집에 있어도 꺼져 있으면 벡터는 규칙 키가 없을 때와 같다"""
        import copy
        import json
        import tempfile
        V = copy.deepcopy(self.off.V)
        V["ingredient_source"].pop("regulatory_rule", None)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(V, f, ensure_ascii=False)
        try:
            bare = Encoder(vocab_path=f.name, regulatory_rule=False)
            np.testing.assert_array_equal(np.asarray(bare.matrix()), np.asarray(self.off.matrix()))
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
