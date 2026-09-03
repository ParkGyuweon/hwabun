# -*- coding: utf-8 -*-
"""판정 규칙과 평탄화의 단위 테스트.

실제 페르소나 파일로 하는 검증은 `validate_persona_tables.py` 가 맡는다. 여기서는
원천 데이터에 아직 없거나 드문 경우 — 시각 없는 리뷰, NULL 속성, 같은 상품 재리뷰,
카탈로그에 없는 상품 — 를 손으로 만들어 규칙이 무너지지 않는지 본다.

실행
    py -m unittest batch/persona/test_persona_tables.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import holdout_rule as hr                                              # noqa: E402
import build_persona_tables as bp                                      # noqa: E402

CATALOG = {"P1", "P2", "P3"}


def review(review_id, product_id, rating=5, submitted="2020-01-01",
           is_recommended=None, **extra):
    row = {
        "review_id": review_id,
        "product_id": product_id,
        "group_id": product_id,
        "rating": rating,
        "is_recommended": is_recommended,
        "submission_time": submitted,
    }
    row.update(extra)
    return row


def persona(reviews, **extra):
    row = {
        "persona_id": "PA00001", "user_id": "PA00001", "author_id": "A1",
        "persona_source": "agent_sample", "profile_version": "persona-v1",
        "profile_scope": "full", "created_at": "2026-09-02T01:22:41Z",
        "updated_at": "2026-09-02T01:22:41Z",
        "skin_type": "dry", "skin_tone": "fair", "eye_color": "brown",
        "hair_color": "black", "stratum": "dry|fair|3", "review_bucket": "3",
        "n_reviews": len(reviews), "n_products": len(reviews), "n_positive": 3,
        "n_negative": 0, "n_neutral": 0, "avg_rating": 5.0,
        "reviews": reviews,
    }
    row.update(extra)
    return row


class OrderByRecency(unittest.TestCase):
    def test_최신_리뷰가_앞에_온다(self):
        rows = [review("r1", "P1", submitted="2019-01-01"),
                review("r2", "P2", submitted="2021-01-01")]
        self.assertEqual([r["review_id"] for r in hr.order_by_recency(rows)], ["r2", "r1"])

    def test_같은_날짜는_review_id_내림차순(self):
        rows = [review("r1", "P1"), review("r3", "P2"), review("r2", "P3")]
        self.assertEqual([r["review_id"] for r in hr.order_by_recency(rows)], ["r3", "r2", "r1"])

    def test_작성일_없는_리뷰는_뒤로_간다(self):
        """계약 §7.1-1 의 NULLS LAST. 시각이 없다고 최신으로 오해하면 안 된다."""
        rows = [review("r1", "P1", submitted=None),
                review("r2", "P2", submitted="2015-01-01")]
        self.assertEqual([r["review_id"] for r in hr.order_by_recency(rows)], ["r2", "r1"])


class Classify(unittest.TestCase):
    def test_최신_긍정은_positive_eligible(self):
        rows = [review("r1", "P1", submitted="2019-01-01"),
                review("r2", "P2", rating=5, submitted="2021-01-01")]
        roles, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["label"], hr.POSITIVE)
        self.assertTrue(decision["is_holdout_eligible"])
        self.assertEqual(roles["r1"], hr.SEED)
        self.assertEqual(roles["r2"], hr.HOLDOUT_TARGET)

    def test_평점이_낮아도_추천이면_positive(self):
        """계약 §7.1-3 은 rating>=4 '또는' is_recommended=true 다."""
        rows = [review("r1", "P1"), review("r2", "P2", rating=2,
                                           is_recommended=True, submitted="2021-01-01")]
        _, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["label"], hr.POSITIVE)

    def test_별점_1_2는_negative(self):
        rows = [review("r1", "P1"), review("r2", "P2", rating=2, submitted="2021-01-01")]
        _, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["label"], hr.NEGATIVE)
        self.assertFalse(decision["is_holdout_eligible"])

    def test_별점_3은_diagnostic(self):
        rows = [review("r1", "P1"), review("r2", "P2", rating=3, submitted="2021-01-01")]
        _, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["label"], hr.DIAGNOSTIC)

    def test_평점이_없으면_diagnostic(self):
        rows = [review("r1", "P1"), review("r2", "P2", rating=None, submitted="2021-01-01")]
        _, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["label"], hr.DIAGNOSTIC)

    def test_카탈로그에_없는_상품은_excluded(self):
        rows = [review("r1", "P1"), review("r2", "P999", submitted="2021-01-01")]
        roles, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["role"], hr.EXCLUDED)
        self.assertIsNone(decision["label"])
        self.assertEqual(roles["r2"], hr.EXCLUDED)

    def test_target과_같은_상품의_이전_리뷰는_seed가_아니다(self):
        """누출 방지. seed 로 남기면 is_seen=true 로 후보에서 빠져 정답을 못 맞힌다."""
        rows = [review("r1", "P2", submitted="2018-01-01"),
                review("r2", "P1", submitted="2019-01-01"),
                review("r3", "P2", submitted="2021-01-01")]
        roles, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["canonical_product_id"], "P2")
        self.assertEqual(roles["r3"], hr.HOLDOUT_TARGET)
        self.assertEqual(roles["r1"], hr.EXCLUDED)      # 같은 상품 P2
        self.assertEqual(roles["r2"], hr.SEED)

    def test_group_id가_대표_상품이다(self):
        rows = [review("r1", "P1"),
                review("r2", "P9", submitted="2021-01-01", group_id="P2")]
        _, decision = hr.classify(rows, CATALOG)
        self.assertEqual(decision["canonical_product_id"], "P2")

    def test_리뷰가_없으면_판정이_없다(self):
        roles, decision = hr.classify([], CATALOG)
        self.assertEqual(roles, {})
        self.assertIsNone(decision)


class SeedProduct(unittest.TestCase):
    def test_같은_상품의_여러_리뷰가_한_행으로_묶인다(self):
        rows = [review("r1", "P1", rating=4, submitted="2018-01-01"),
                review("r2", "P1", rating=2, submitted="2019-01-01"),
                review("r3", "P3", rating=5, submitted="2021-01-01")]
        roles, _ = hr.classify(rows, CATALOG)
        seeds = bp.build_seed_product(persona(rows), roles)
        self.assertEqual(len(seeds), 1)
        seed = seeds[0]
        self.assertEqual(seed["canonical_product_id"], "P1")
        self.assertEqual(seed["source_review_ids"], ["r1", "r2"])
        self.assertEqual(seed["last_reviewed_at"], "2019-01-01")
        self.assertEqual(seed["avg_seed_rating"], 3.0)
        self.assertFalse(seed["is_positive_seed"])
        self.assertTrue(seed["is_seen"])

    def test_initial_event_weight는_비워_둔다(self):
        """산식이 recommendation-io-spec.md 에 없다. 지어내지 않는다."""
        rows = [review("r1", "P1"), review("r2", "P3", submitted="2021-01-01")]
        roles, _ = hr.classify(rows, CATALOG)
        seeds = bp.build_seed_product(persona(rows), roles)
        self.assertIsNone(seeds[0]["initial_event_weight"])


class ProfileEval(unittest.TestCase):
    def test_속성은_최신_seed_리뷰에서_온다(self):
        """holdout 리뷰의 속성이 평가 Profile 에 새어들면 안 된다."""
        rows = [
            review("r1", "P1", submitted="2018-01-01", skin_tone="fair"),
            review("r2", "P2", submitted="2019-01-01", skin_tone="light"),
            review("r3", "P3", submitted="2021-01-01", skin_tone="deep"),   # holdout
        ]
        roles, _ = hr.classify(rows, CATALOG)
        row = bp.build_profile_eval(persona(rows), roles)
        self.assertEqual(row["skin_tone"], "light")
        self.assertEqual(row["profile_scope"], "eval")
        self.assertEqual(row["n_reviews_seed"], 2)
        self.assertEqual(row["n_products_seed"], 2)

    def test_seed에_속성이_없으면_None(self):
        rows = [review("r1", "P1", submitted="2018-01-01"),
                review("r2", "P3", submitted="2021-01-01", skin_tone="deep")]
        roles, _ = hr.classify(rows, CATALOG)
        row = bp.build_profile_eval(persona(rows), roles)
        self.assertIsNone(row["skin_tone"])


class AffinityInput(unittest.TestCase):
    def test_일반_피부타입_가중치(self):
        row = bp.build_affinity_input(persona([], skin_type="dry"))
        self.assertEqual(row["skin_type_weight"], 0.40)
        self.assertEqual(row["skin_tone_weight"], 0.40)
        self.assertAlmostEqual(sum(row[k] for k in
                                   ("skin_type_weight", "skin_tone_weight",
                                    "hair_color_weight", "eye_color_weight")), 1.0)

    def test_combination은_skin_type을_쓰지_않는다(self):
        row = bp.build_affinity_input(persona([], skin_type="combination"))
        self.assertEqual(row["skin_type_weight"], 0.00)
        self.assertEqual(row["skin_tone_weight"], 0.80)

    def test_NULL_속성은_가중치를_빼고_재정규화한다(self):
        row = bp.build_affinity_input(persona([], skin_type="dry", hair_color=None))
        self.assertEqual(row["hair_color_weight"], 0.0)
        total = sum(row[k] for k in ("skin_type_weight", "skin_tone_weight",
                                     "hair_color_weight", "eye_color_weight"))
        self.assertAlmostEqual(total, 1.0, places=5)


class Segments(unittest.TestCase):
    def test_허용된_6종만_나온다(self):
        rows = bp.build_segments(persona([]))
        self.assertEqual([r["segment_type"] for r in rows], list(bp.SEGMENT_TYPES))

    def test_NULL_속성은_행을_만들지_않는다(self):
        """segment_value 는 nullable=N 이다. 빈 값으로 채우지 않고 행을 뺀다."""
        rows = bp.build_segments(persona([], hair_color=None))
        self.assertNotIn("hair_color", [r["segment_type"] for r in rows])
        self.assertEqual(len(rows), len(bp.SEGMENT_TYPES) - 1)


class TableShape(unittest.TestCase):
    def test_모든_행이_계약_컬럼_순서를_지킨다(self):
        rows = [review("r1", "P1", submitted="2018-01-01"),
                review("r2", "P2", submitted="2019-01-01"),
                review("r3", "P3", submitted="2021-01-01")]
        tables = bp.build([persona(rows)], CATALOG)
        for name, spec in bp.TABLE_SPECS.items():
            expected = [c for c, _, _ in spec["columns"]]
            for row in tables[name]:
                self.assertEqual(list(row.keys()), expected, f"{name} 컬럼 순서")

    def test_사람_한_명이_holdout_한_행을_만든다(self):
        rows = [review("r1", "P1", submitted="2018-01-01"),
                review("r2", "P3", submitted="2021-01-01")]
        tables = bp.build([persona(rows)], CATALOG)
        self.assertEqual(len(tables["persona_holdout_target"]), 1)

    def test_excluded_후보는_holdout_행을_만들지_않는다(self):
        rows = [review("r1", "P1", submitted="2018-01-01"),
                review("r2", "P999", submitted="2021-01-01")]
        tables = bp.build([persona(rows)], CATALOG)
        self.assertEqual(tables["persona_holdout_target"], [])


if __name__ == "__main__":
    unittest.main()
