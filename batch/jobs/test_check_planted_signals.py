# -*- coding: utf-8 -*-
"""check_planted_signals — 작은 고정 이벤트로 집계와 기대 값 계산을 확인한다."""
import json
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import check_planted_signals as C  # noqa: E402


def ev(name, pv, pid, sid="run:1", persona="PC1", **props):
    return {"event_name": name, "persona_id": persona, "session_id": sid,
            "page_view_id": pv, "product_id": pid, "properties": props}


class DepthTest(unittest.TestCase):
    def test_observed_depth_matches_seven_section_grid(self):
        self.assertEqual(C.observed_depth(100), 100)
        self.assertEqual(C.observed_depth(90), 85)
        self.assertEqual([C.observed_depth(x) for x in (20, 30, 40, 50)], [14, 28, 40, 50])
        self.assertEqual(C.observed_depth(25), 25)

    def test_observed_depth_agrees_with_generator(self):
        """생성기의 visit_detail 이 실제로 남기는 최대 깊이와 같아야 한다"""
        G = C.load_generator()
        import numpy as np

        class Sink(list):
            pass

        for target in (20, 30, 40, 50, 90, 100):
            sink = Sink()
            ctx = G.SimulationContext("s", "run_test", "python_batch")
            e = G.Emitter(sink, "PC1", G.NOW, np.random.default_rng(0), ctx)
            product = {"name": "x", "brand": "b", "price": 1.0, "cat": "c"}
            G.visit_detail(e, "P1", product, [], np.random.default_rng(0), depth_target=target,
                           engaged=False, entry_source="in_app")
            got = max(x["properties"]["depth_percent"] for x in sink if x["event_name"] == "scroll_depth")
            self.assertEqual(got, C.observed_depth(target, len(G.DETAIL_LAYOUT)), target)

    def test_style_factor(self):
        self.assertAlmostEqual(C.style_factor(0.3, 2.2), 1.0)
        self.assertAlmostEqual(C.style_factor(0.5, 2.2), 1.0)
        self.assertAlmostEqual(C.style_factor(0.75, 2.2), 1.6)
        self.assertAlmostEqual(C.style_factor(1.0, 2.2), 2.2)


class NormalizeTest(unittest.TestCase):
    def test_generator_and_cleaned_rows_agree(self):
        a = C.normalize(ev("add_to_cart", "pv1", "P1", seeded=True, simulation_run_id="r1"))
        b = C.normalize({"event_name": "add_to_cart", "persona_id": "PC1", "session_id": "run:1",
                         "page_view_id": "pv1", "product_id": "P1", "is_seeded": True,
                         "simulation_run_id": "r1",
                         "properties_json": json.dumps({"seeded": True})})
        for k in ("event_name", "persona_id", "session_id", "page_view_id", "product_id", "seeded", "run_id"):
            self.assertEqual(a[k], b[k], k)


class CollectTest(unittest.TestCase):
    def test_visit_aggregation(self):
        rows = [
            ev("product_view", "pv1", "P1", navigation_source="in_app"),
            ev("scroll_depth", "pv1", "P1", depth_percent=14),
            ev("scroll_depth", "pv1", "P1", depth_percent=100),
            ev("add_to_cart", "pv1", "P1"),
            ev("wishlist_toggle", "pv1", "P1", action="add"),
            ev("product_view", "pv2", "SB1", navigation_source="in_app"),
            ev("scroll_depth", "pv2", "SB1", depth_percent=40),
            ev("add_to_cart", "pv2", "SB1"),
            ev("text_selection", "pv2", "SB1", section_id="ingredients"),
            ev("remove_from_cart", "cart1", "SB1"),
            {"event_name": "purchase", "persona_id": "PC1", "session_id": "run:1", "page_view_id": "cart1",
             "product_id": None, "properties": {"items": [{"product_id": "P1"}]}},
            # 시드 세션 — 본 탐색 세션 수에 넣지 않는다
            ev("product_view", "pv3", "P9", sid="seed:x", seeded=True),
            ev("rage_click", "pv3", "P9", sid="seed:x", seeded=True),
            # product_view 없는 담기(긍정 시드) — 방문으로 치지 않는다
            ev("add_to_cart", "pv4", "P8", sid="seed:y", seeded=True),
        ]
        visits, purchases, sessions, _ = C.collect(C.normalize(r) for r in rows)
        by = {v["pid"]: v for v in visits}
        self.assertEqual(set(by), {"P1", "SB1", "P9"})
        self.assertEqual((by["P1"]["depth"], by["P1"]["cart"], by["P1"]["wish"]), (100, True, True))
        self.assertTrue(by["SB1"]["removed"] and by["SB1"]["ing_sel"])
        self.assertTrue(by["P9"]["seeded"] and by["P9"]["rage"])
        self.assertEqual(purchases["run:1"], {"P1"})
        self.assertEqual(dict(sessions), {"PC1": {"run:1"}})

    def test_check_runs_on_fixture(self):
        G = C.load_generator()
        rows = [ev("product_view", "pv1", "P1"), ev("scroll_depth", "pv1", "P1", depth_percent=100),
                ev("add_to_cart", "pv1", "P1"),
                ev("product_view", "pv2", "P2"), ev("scroll_depth", "pv2", "P2", depth_percent=85)]
        visits, purchases, sessions, _ = C.collect(C.normalize(r) for r in rows)
        out = C.check(visits, purchases, sessions, G, {}, set())
        first = out[0]
        self.assertEqual((first[3], first[4], first[5]), (1.0, 1, True))
        deep = next(r for r in out if "p_deep_bounce" in r[0])
        self.assertEqual((deep[3], deep[4]), (1.0, 1))


if __name__ == "__main__":
    unittest.main()
