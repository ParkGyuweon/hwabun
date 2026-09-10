# -*- coding: utf-8 -*-
"""추천 서버 연동(Jira 221)을 고정한다 — 네트워크 없이 가짜 opener 로 돈다.

여기서 막고 싶은 것
  * 서버 응답의 recommendation_id·algorithm·banner_slot·trait_source 가 이벤트에 그대로 실리지 않는 것
  * 배너 클릭이 서버가 노출하지 않은 상품에서 나오는 것
  * 서버가 죽었을 때 생성기가 멈추는 것 (한 번 경고하고 폴백해야 한다)
  * localhost 가 ::1 로 가서 호출마다 2초를 잃는 것
  * 상태 전송에 상태와 무관한 이벤트(section_view 등)까지 실어 보내는 것
"""
import io
import json
import os
import sys
import unittest
import urllib.error
from datetime import datetime

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

from recommend_client import STATE_EVENTS, RecommendClient, banners_from_response, hero_from_response  # noqa: E402

RESP = {
    "persona_id": "PC00001", "recommendation_id": "abc123", "list_id": "main",
    "algorithm": "ltr-278t-2026-09-07", "banner_slots": 6, "banner_list_id": "banner_row",
    "items": [{"product_id": f"P{i}", "position": i, "score": 1.0 / i} for i in range(1, 11)],
    "hero_policy": "new_brand",
    "hero": {"product_id": "SB000003", "banner_type": "concern", "banner_value": "Loss of firmness",
             "trait_source": "session", "hero_policy": "new_brand", "reserved": True,
             "product_name": "PDRN 핑크 펩타이드 세럼", "brand_name": "SSAFY Beauty", "score": 0.41,
             "reason": {"new_brand": "새로 입점한 브랜드의 상품"}, "product_source": "brand_registered"},
    "banners": [
        {"banner_slot": 1, "banner_type": "concern", "banner_value": "Pores", "product_id": "P21", "reserved": False, "trait_source": "session"},
        {"banner_slot": 2, "banner_type": "segment", "banner_value": "oily", "product_id": "P22", "reserved": False, "trait_source": "profile"},
        {"banner_slot": 3, "banner_type": "concern", "banner_value": "Pores", "product_id": "P23", "reserved": False, "trait_source": "session"},
        {"banner_slot": 4, "banner_type": "segment", "banner_value": "oily", "product_id": "P24", "reserved": False, "trait_source": "profile"},
        {"banner_slot": 5, "banner_type": "new_brand", "banner_value": None, "product_id": "SB000001", "reserved": True, "trait_source": "session"},
        {"banner_slot": 6, "banner_type": "new_brand", "banner_value": None, "product_id": "SB000002", "reserved": True, "trait_source": "session"},
    ],
}


class FakeOpener:
    """urllib.request.urlopen 흉내. 요청을 기록하고 정해진 응답을 준다"""

    def __init__(self, responses=None, fail=None):
        self.calls = []
        self.responses = responses or {}
        self.fail = fail

    def __call__(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url, req.data))
        if self.fail:
            raise self.fail
        path = req.full_url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        body = self.responses.get(path, {"ok": True})

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return json.dumps(body).encode("utf-8")
        return R()


class TestClient(unittest.TestCase):
    def test_localhost_rewritten_to_ipv4(self):
        c = RecommendClient("http://localhost:8300", opener=FakeOpener())
        self.assertEqual(c.base, "http://127.0.0.1:8300")
        c2 = RecommendClient("http://recommend:8300/", opener=FakeOpener())
        self.assertEqual(c2.base, "http://recommend:8300")

    def test_recommend_passes_slots_and_returns_response(self):
        op = FakeOpener({"api/recommend": RESP})
        c = RecommendClient("http://x:1", banner_slots=6, reserved=2, hero="top", opener=op)
        r = c.recommend("PC00001")
        self.assertEqual(r["recommendation_id"], "abc123")
        self.assertIn("banner_slots=6", op.calls[0][1])
        self.assertIn("reserved=2", op.calls[0][1])
        self.assertIn("hero=top", op.calls[0][1])
        self.assertIn("persona_id=PC00001", op.calls[0][1])
        self.assertEqual(c.stats["recommend"], 1)

    def test_defaults_match_hero_only_screen(self):
        """화면 = 히어로 하나 (Jira 239). 기본값은 banner_slots=1 · reserved=0 · hero=new_brand"""
        op = FakeOpener({"api/recommend": RESP})
        c = RecommendClient("http://x:1", opener=op)
        c.recommend("PC00001")
        q = op.calls[0][1]
        self.assertIn("banner_slots=1", q)
        self.assertIn("reserved=0", q)
        self.assertIn("hero=new_brand", q)

    def test_observe_filters_non_state_events(self):
        op = FakeOpener()
        c = RecommendClient("http://x:1", opener=op)
        evs = [{"event_name": "section_view", "product_id": None, "properties": {}},
               {"event_name": "add_to_cart", "product_id": "P1", "properties": {"quantity": 1}},
               {"event_name": "product_view", "product_id": "P2", "properties": {}}]
        n = c.observe("PC00001", evs)
        self.assertEqual(n, 2)
        sent = json.loads(op.calls[0][2].decode("utf-8"))
        self.assertEqual([e["event_name"] for e in sent["events"]], ["add_to_cart", "product_view"])
        self.assertEqual(c.observe("PC00001", [{"event_name": "section_view", "properties": {}}]), 0)
        self.assertEqual(len(op.calls), 1)

    def test_connection_failure_falls_back_once(self):
        logs = []
        c = RecommendClient("http://x:1", opener=FakeOpener(fail=ConnectionRefusedError()), log=logs.append)
        self.assertIsNone(c.recommend("PC00001"))
        self.assertIsNone(c.recommend("PC00002"))          # 두 번째는 부르지도 않는다
        self.assertFalse(c.available)
        self.assertEqual(len([l for l in logs if "붙지 못했다" in l]), 1)
        self.assertIn("폴백", c.summary())

    def test_http_error_keeps_server_available(self):
        err = urllib.error.HTTPError("http://x/api/recommend", 422, "bad", {}, io.BytesIO(b""))
        c = RecommendClient("http://x:1", opener=FakeOpener(fail=err), log=lambda m: None)
        self.assertIsNone(c.recommend("PC00001"))
        self.assertTrue(c.available)

    def test_hero_from_response_is_slot_1_with_contract_names(self):
        h = hero_from_response(RESP)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["slot"], 1)
        self.assertEqual(h[0]["product_id"], "SB000003")
        self.assertEqual(h[0]["type"], "concern")
        self.assertEqual(h[0]["value"], "Loss of firmness")
        self.assertEqual(h[0]["trait_source"], "session")
        self.assertTrue(h[0]["reserved"])
        self.assertEqual(hero_from_response({"items": []}), [])
        top = hero_from_response({"hero": {"product_id": "P1", "banner_type": "concern", "banner_value": "Pores",
                                           "trait_source": "session", "hero_policy": "top"}})
        self.assertFalse(top[0]["reserved"])

    def test_banners_from_response_keeps_contract_names(self):
        b = banners_from_response(RESP)
        self.assertEqual([x["slot"] for x in b], [1, 2, 3, 4, 5, 6])
        self.assertEqual(b[4]["type"], "new_brand")
        self.assertIsNone(b[4]["value"])
        self.assertTrue(b[4]["reserved"])
        self.assertEqual(b[1]["trait_source"], "profile")


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class TestGeneratorWithServer(unittest.TestCase):
    """browse_list 에 서버 응답을 주면 메인·배너 이벤트가 서버 식별자를 그대로 싣는다"""

    def test_browse_list_uses_server_ids(self):
        import gen_behavior_logs as gen
        ctx = gen.SimulationContext(scenario_id=gen.DEFAULT_SCENARIO_ID,
                                    simulation_run_id="run_test_221", generator_type=gen.DEFAULT_GENERATOR_TYPE)
        rng = np.random.default_rng(5)
        catalog = {f"P{i}": {"cat": "Moisturizers", "price": 10.0 * i, "concern": "Dryness",
                             "variants": [], "n": i} for i in range(1, 30)}
        events = []
        e = gen.Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), rng, ctx)
        banners = hero_from_response(RESP)                     # 화면 = 히어로 하나 (Jira 239)
        promo = [it["product_id"] for it in RESP["items"]]
        gen.browse_list(e, promo, ["P25", "P26", "P27"], catalog, rng, dwell_ms=3000, first=True,
                        banners=banners, reco=RESP)
        snap = [x for x in events if x["event_name"] == "recommendation_snapshot"]
        self.assertEqual(len(snap), 1)
        self.assertEqual(snap[0]["properties"]["recommendation_id"], "abc123")
        self.assertEqual(snap[0]["properties"]["list_id"], "main")
        self.assertEqual(snap[0]["properties"]["algorithm"], RESP["algorithm"])
        self.assertEqual(len(snap[0]["properties"]["ranking"]), 10)
        imps = [x for x in events if x["event_name"] == "recommendation_impression"]
        self.assertEqual([x["product_id"] for x in imps], promo)
        self.assertTrue(all(x["properties"]["recommendation_id"] == "abc123" and x["properties"]["list_id"] == "main"
                            for x in imps))
        bi = [x for x in events if x["event_name"] == "banner_impression"]
        self.assertEqual(len(bi), 1)
        pr = bi[0]["properties"]; h = RESP["hero"]
        self.assertEqual(bi[0]["product_id"], h["product_id"])
        self.assertEqual(pr["recommendation_id"], "abc123")
        self.assertEqual(pr["algorithm"], RESP["algorithm"])
        self.assertEqual(pr["banner_slot"], 1)
        self.assertEqual(pr["list_id"], "hero_banner")
        self.assertEqual(pr["banner_type"], h["banner_type"])
        self.assertEqual(pr["banner_value"], h["banner_value"])
        self.assertEqual(pr["trait_source"], h["trait_source"])
        self.assertEqual(pr["policy_version"], gen.BANNER_POLICY_VERSION)
        rid, algo, ids = e.last_main
        self.assertEqual((rid, algo, ids), ("abc123", RESP["algorithm"], promo))
        batch, shown, source, algo_b = e.last_banner
        self.assertEqual((batch, source, algo_b), ("abc123", None, RESP["algorithm"]))

    def test_browse_list_without_server_keeps_old_behaviour(self):
        import gen_behavior_logs as gen
        ctx = gen.SimulationContext(scenario_id=gen.DEFAULT_SCENARIO_ID,
                                    simulation_run_id="run_test_221b", generator_type=gen.DEFAULT_GENERATOR_TYPE)
        rng = np.random.default_rng(7)
        catalog = {f"P{i}": {"cat": "Moisturizers", "price": 10.0 * i, "concern": "Dryness",
                             "variants": [], "n": i} for i in range(1, 13)}
        popular = sorted(catalog, key=lambda g: -catalog[g]["n"])
        banners = gen.make_banners({"persona_id": "PC00001", "skin_type": "oily"}, catalog, popular[:8], popular, rng)
        events = []
        e = gen.Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), rng, ctx)
        gen.browse_list(e, popular[:2], popular[:5], catalog, rng, dwell_ms=3000, first=True, banners=banners)
        self.assertFalse([x for x in events if x["event_name"] == "recommendation_snapshot"])
        bi = [x for x in events if x["event_name"] == "banner_impression"]
        self.assertTrue(all(x["properties"]["algorithm"] == gen.BANNER_ALGO for x in bi))
        self.assertEqual(len({x["properties"]["trait_source"] for x in bi}), 1)


if __name__ == "__main__":
    unittest.main()
