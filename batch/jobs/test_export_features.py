"""서빙용 산출물이 계약대로 나왔는지, 기준 결과가 재현되는지 고정한다.

자바로 다시 구현한 RankingService 도 이 파일들만 읽으면 같은 검사를 할 수 있다.
"""
import csv
import json
import os
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
SERVING = os.path.join(ROOT, "batch", "ingest", "data", "serving")
PRODUCT_FEATURE = os.path.join(SERVING, "product_feature.jsonl")
AFFINITY = os.path.join(SERVING, "attribute_affinity.csv")
GOLDEN = os.path.join(SERVING, "ranking_golden.json")


@unittest.skipIf(np is None, "numpy is required")
@unittest.skipUnless(os.path.exists(GOLDEN), "먼저 export_features.py 를 실행하세요")
class ServingArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PRODUCT_FEATURE, encoding="utf-8") as f:
            cls.products = [json.loads(line) for line in f]
        with open(GOLDEN, encoding="utf-8") as f:
            cls.golden = json.load(f)

    def test_product_feature_contract(self):
        self.assertEqual(200, len(self.products))
        for p in self.products:
            self.assertEqual(148, len(p["vector"]), p["product_id"])
            # 백엔드는 정규화 없이 내적만 한다. 여기서 L2=1 이 아니면 점수가 어긋난다
            self.assertAlmostEqual(1.0, float(np.linalg.norm(p["vector"])), places=4)
            self.assertGreaterEqual(p["prior_score"], 0.0)
            self.assertLessEqual(p["prior_score"], 1.0)
            for key in ("secondary_category", "tertiary_category", "price_bin"):
                self.assertTrue(p[key], f"{p['product_id']} {key}")

    def test_affinity_contract(self):
        with open(AFFINITY, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(4000, len(rows))
        self.assertEqual(200, len({r["product_id"] for r in rows}))
        self.assertEqual(20, len({(r["attribute"], r["segment"]) for r in rows}))
        for r in rows:
            self.assertTrue(0.0 <= float(r["affinity"]) <= 1.0)

    def test_golden_is_reproducible(self):
        """기준 결과를 지금 코드로 다시 계산해도 같은 순위·점수가 나와야 한다

        **검사식이 골든과 다르면 "재현된다" 는 확인 자체가 거짓이 된다.**
        골든이 무엇으로 만들어졌는지는 파일이 `scorer` 로 말한다 — 그 값을 보고
        같은 경로로 다시 계산한다. 여기를 하드코딩하면 결합 방식을 바꿀 때마다
        테스트가 조용히 옛 식을 검사하게 된다.
        """
        import sys
        sys.path.insert(0, BD)
        from ltr_features import LtrFeatures, load_ltr
        from persona_feature import AffinityTable
        from product_encoder import Encoder
        from recommender import CF_BETA, cf_bonus, load_cooc, schedule_for

        index = {p["product_id"]: i for i, p in enumerate(self.products)}
        M = np.array([p["vector"] for p in self.products], np.float32)
        prior = np.array([p["prior_score"] for p in self.products], np.float32)
        affinity = AffinityTable(index)
        cooc, supporters = load_cooc()

        scorer = self.golden.get("scorer", "linear")
        feat = clf = None
        if scorer == "ltr":
            ltr = load_ltr()
            self.assertIsNotNone(ltr, "골든이 LTR 기준인데 ltr_model.pkl 이 없다")
            clf, meta = ltr
            self.assertEqual(meta["feature_names"],
                             self.golden["ltr_model"]["feature_names"],
                             "모델의 피처 구성이 골든을 만들 때와 다르다")
            # 블록 경계는 어휘집(계약)에서 온다 — 자바도 같은 파일을 읽는다
            feat = LtrFeatures(Encoder(), M, prior, affinity, cooc, supporters)

        for case in self.golden["cases"]:
            si = [index[g] for g in case["seed_product_ids"]]
            self.assertEqual(scorer, case.get("scorer", "linear"),
                             case["persona_id"])
            if scorer == "ltr":
                cand = np.ones(len(M), bool)
                cand[si] = False
                score = clf.predict_proba(
                    feat.make(case["attributes"], si, cand))[:, 1]
            else:
                u = M[si].mean(0)
                cos = M @ (u / np.linalg.norm(u))
                w1, w2, w3 = schedule_for(len(si))
                self.assertEqual(w1, case["weights"]["w1_cosine"], case["persona_id"])
                score = w1 * cos + w2 * affinity(case["attributes"]) + w3 * prior
                if cooc is not None:
                    cand = np.ones(len(M), bool)
                    cand[si] = False
                    cfb = cf_bonus(cooc, si, cand, supporters)
                    if cfb is not None:
                        score = score + CF_BETA * cfb
            score = np.asarray(score, np.float64)
            score[si] = -np.inf
            top = np.argsort(-score)[:len(case["expected_top10"])]
            got = [self.products[i]["product_id"] for i in top]
            self.assertEqual([x["product_id"] for x in case["expected_top10"]], got,
                             case["persona_id"])
            for i, want in zip(top, case["expected_top10"]):
                self.assertAlmostEqual(want["score"], float(score[i]), places=5)


if __name__ == "__main__":
    unittest.main()
