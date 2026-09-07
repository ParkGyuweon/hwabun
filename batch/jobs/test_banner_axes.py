# -*- coding: utf-8 -*-
"""배너 축 산출물이 계약과 어긋나지 않았는지 (Jira 172).

여기서 막으려는 사고는 하나다 — **`banner_value` 가 어휘집 문자열이 아닌 것.**
한 글자만 달라도 그 축이 통째로 매칭 실패하는데 화면에는 아무 표시도 안 난다.
"""
import json
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)

OUT = os.path.join(ROOT, "batch", "ingest", "data", "serving", "banner_axes.json")
VOCAB = os.path.join(ROOT, "contracts", "product-feature-vocab.json")
LABELS = os.path.join(ROOT, "contracts", "product-form-labels-ko.json")
AXES = ("concern", "ingredient", "clean", "price_bin", "category", "segment")


class TestBannerAxes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(OUT):
            raise unittest.SkipTest("banner_axes.json 없음 — 먼저 생성하십시오")
        cls.doc = json.load(open(OUT, encoding="utf-8"))
        cls.vocab = json.load(open(VOCAB, encoding="utf-8"))
        cls.blocks = {b["name"]: set(b["vocab"]) for b in cls.vocab["blocks"]}

    def test_축이_여섯_개다(self):
        self.assertEqual(set(self.doc["axes"]), set(AXES))

    def test_어휘집_버전이_같다(self):
        self.assertEqual(self.doc["vocab_version"], self.vocab["version"])

    def test_banner_value_가_어휘집_문자열이다(self):
        cat = self.blocks["secondary_category"] | self.blocks["tertiary_category"]
        for axis, rows in self.doc["axes"].items():
            if axis == "segment":
                continue                     # 세그먼트는 어휘집이 아니라 친화도에서 온다
            allowed = cat if axis == "category" else self.blocks[axis]
            for r in rows:
                self.assertIn(r["banner_value"], allowed,
                              f"{axis}: {r['banner_value']} 가 어휘집에 없다")

    def test_상품_목록이_비어_있지_않다(self):
        for axis, rows in self.doc["axes"].items():
            for r in rows:
                self.assertTrue(r["product_ids"], f"{axis}/{r['banner_value']} 비었다")
                self.assertLessEqual(len(r["product_ids"]), self.doc["top"])

    def test_한국어_라벨이_전부_붙었다(self):
        """라벨이 빠지면 화면 문구가 영어로 나간다. 조용히 나가므로 여기서 막는다"""
        miss = [(a, r["banner_value"]) for a, rows in self.doc["axes"].items()
                for r in rows if not r.get("label_ko")]
        self.assertEqual(miss, [], f"한국어 라벨 없는 값: {miss[:8]}")

    def test_얇은_축이_표시돼_있다(self):
        for axis, rows in self.doc["axes"].items():
            for r in rows:
                self.assertEqual(r["too_thin"], r["n_products"] < 5,
                                 f"{axis}/{r['banner_value']} too_thin 이 안 맞는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
