# -*- coding: utf-8 -*-
"""추천 추론 서버의 계약을 고정한다 (Jira 206, 계약 §5).

여기서 막고 싶은 것
  * 응답에 계약 필드가 빠지는 것 (product_id · score · reserved · reason)
  * 전환한 상품이 추천에 다시 나오는 것 (노출 정책 §5 5단계)
  * 없는 persona 에 200 을 주는 것
  * 콜드 스타트가 죽는 것 — 이력 없는 사람도 size 개를 받아야 한다
  * reserved 가 size 를 넘거나 중복 상품이 나오는 것
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

# 등록 상품 파일은 **복사본**을 쓴다 — 테스트가 POST /api/products 로 레포 파일에 append 하면 안 된다
_TMP = tempfile.mkdtemp(prefix="reg216_")
_COPY = os.path.join(_TMP, "registered_products.jsonl")
shutil.copy(os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), _COPY)
os.environ["REGISTERED_PRODUCTS_PATH"] = _COPY

from fastapi.testclient import TestClient  # noqa: E402

import recommend_server as rs              # noqa: E402

client = TestClient(rs.app)
PID = "PC00001"
N_SEED = 200


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = client.get("/health").json()

    def test_health(self):
        self.assertTrue(self.h["ok"])
        self.assertEqual(self.h["seed_products"], N_SEED)
        self.assertGreaterEqual(self.h["registered_products"], 8)        # SSAFY Beauty (Jira 216)
        self.assertEqual(self.h["products"], N_SEED + self.h["registered_products"])
        self.assertIn(self.h["scorer"], ("ltr", "linear"))

    def test_cold_start_returns_full_list(self):
        r = client.get("/api/recommend", params={"persona_id": PID, "size": 10}).json()
        self.assertEqual(r["state_source"], "cold_start")
        self.assertEqual(len(r["items"]), 10)
        ids = [it["product_id"] for it in r["items"]]
        self.assertEqual(len(set(ids)), 10)
        for k in ("recommendation_id", "list_id", "algorithm"):
            self.assertTrue(r.get(k), k)          # 유입 추적 식별자 — 클릭 이벤트가 그대로 싣는다
        self.assertEqual([it["position"] for it in r["items"]], list(range(1, 11)))
        for it in r["items"]:
            for k in ("product_id", "product_name", "brand_name", "score", "position", "reserved", "reason"):
                self.assertIn(k, it)
            self.assertIsInstance(it["reserved"], bool)
            self.assertTrue(it["reason"])          # 근거 문구가 비어 있지 않다

    def test_review_seed_mode_marks_source(self):
        r = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "seed": "review"}).json()
        self.assertEqual(r["state_source"], "review_seed")
        self.assertGreater(r["n_products"], 0)

    # ── Jira 214: persona_id 없음 · 표에 없는 값 → 익명/미등록 cold_start, 404 없음 ──
    def test_anonymous_without_persona_id(self):
        r = client.get("/api/recommend", params={"size": 5})
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertIsNone(b["persona_id"])
        self.assertFalse(b["persona_known"])
        self.assertEqual(b["state_source"], "cold_start")
        self.assertEqual(len(b["items"]), 5)
        self.assertEqual(b["items"][0]["reason"], {"popular": "많은 사용자가 선택한 상품"})

    def test_empty_persona_id_is_anonymous(self):
        b = client.get("/api/recommend", params={"persona_id": "", "size": 5}).json()
        self.assertIsNone(b["persona_id"])
        self.assertFalse(b["persona_known"])

    def test_unknown_member_id_is_accepted_and_personalized_by_events(self):
        pid = "member-test-214"
        first = client.get("/api/recommend", params={"persona_id": pid, "size": 10})
        self.assertEqual(first.status_code, 200)
        f = first.json()
        self.assertEqual(f["persona_id"], pid)
        self.assertFalse(f["persona_known"])
        self.assertEqual(f["state_source"], "cold_start")
        # 익명과 같은 순위에서 시작한다 (속성 친화도 없음, 상태 없음)
        anon = client.get("/api/recommend", params={"size": 10}).json()
        self.assertEqual([i["product_id"] for i in f["items"]], [i["product_id"] for i in anon["items"]])
        g = f["items"][0]["product_id"]
        ev = client.post("/api/events", json={"persona_id": pid, "events": [
            {"event_name": "add_to_cart", "product_id": g, "properties": {}}]})
        self.assertEqual(ev.status_code, 200)
        second = client.get("/api/recommend", params={"persona_id": pid, "size": 10}).json()
        self.assertEqual(second["state_source"], "events")
        self.assertFalse(second["persona_known"])
        self.assertNotIn(g, [it["product_id"] for it in second["items"]])

    def test_known_persona_flag_and_reserved_filled(self):
        b = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 2}).json()
        self.assertTrue(b["persona_known"])
        self.assertEqual(b["reserved"], 2)
        self.assertEqual(b["reserved_filled"], sum(1 for it in b["items"] if it["reserved"]))
        self.assertLessEqual(b["reserved_filled"], 2)

    def test_converted_products_are_excluded(self):
        pid = "PC00002"
        first = client.get("/api/recommend", params={"persona_id": pid, "size": 10}).json()
        g = first["items"][0]["product_id"]
        ev = client.post("/api/events", json={"persona_id": pid, "events": [
            {"event_name": "add_to_cart", "product_id": g, "properties": {}}]}).json()
        self.assertIn(g, ev["converted"])
        second = client.get("/api/recommend", params={"persona_id": pid, "size": 10}).json()
        self.assertEqual(second["state_source"], "events")
        self.assertNotIn(g, [it["product_id"] for it in second["items"]])
        self.assertEqual(len(second["items"]), 10)

    def test_reserved_is_capped_and_unique(self):
        r = client.get("/api/recommend", params={"persona_id": PID, "size": 5, "reserved": 10,
                                                 "seed": "review"}).json()
        ids = [it["product_id"] for it in r["items"]]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        # reserved 는 size 로 잘린다. 등록 상품(SSAFY Beauty, Jira 216)이 있으니 전용 칸은
        # 최대 size 개까지만 찍히고 모두 등록 상품이어야 한다
        res = [it for it in r["items"] if it["reserved"]]
        self.assertEqual(len(res), r["reserved_filled"])
        self.assertLessEqual(len(res), 5)
        self.assertTrue(all(it["product_source"] == "brand_registered" for it in res))

    def test_recommendation_id_is_unique_per_call(self):
        a = client.get("/api/recommend", params={"persona_id": PID}).json()
        b = client.get("/api/recommend", params={"persona_id": PID}).json()
        self.assertNotEqual(a["recommendation_id"], b["recommendation_id"])
        self.assertEqual(a["algorithm"], b["algorithm"])

    def test_latency_is_reported(self):
        r = client.get("/api/recommend", params={"persona_id": PID, "seed": "review"}).json()
        self.assertGreater(r["latency_ms"], 0)


class TestRegistration(unittest.TestCase):
    """Jira 216 — 등록 즉시 카탈로그 편입. SSAFY Beauty 8개는 시작 시 이미 들어 있다"""

    def test_reserved_slots_filled_by_registered_products(self):
        b = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 2,
                                                 "seed": "review"}).json()
        self.assertEqual(b["reserved_filled"], 2)
        res = [it for it in b["items"] if it["reserved"]]
        self.assertEqual([it["position"] for it in res], [9, 10])
        for it in res:
            self.assertEqual(it["brand_name"], "SSAFY Beauty")
            self.assertEqual(it["product_source"], "brand_registered")
            self.assertIn("new_brand", it["reason"])

    def test_reserved_zero_ranking_equals_first_k_minus_r(self):
        # MMR 순차성 — 전용 칸을 붙여도 앞 (k-r) 칸은 reserved=0 과 같아야 한다
        a = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 0,
                                                 "seed": "review"}).json()
        b = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 2,
                                                 "seed": "review"}).json()
        self.assertEqual([i["product_id"] for i in a["items"]][:8],
                         [i["product_id"] for i in b["items"]][:8])
        self.assertFalse(any(i["product_id"].startswith("SB") for i in a["items"]),
                         "신호 없는 등록 상품이 일반 칸에 오면 안 된다")

    def test_get_product(self):
        r = client.get("/api/products/SB000001")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["product_source"], "brand_registered")
        self.assertEqual(b["supporters"], 0)
        self.assertTrue(b["reserved_candidate"])
        self.assertEqual(client.get("/api/products/NOPE").status_code, 404)

    def test_register_then_recommend_immediately(self):
        before = client.get("/health").json()["products"]
        payload = {"product_id": "SB0TEST1", "product_name": "테스트 세럼", "brand_name": "SSAFY Beauty",
                   "secondary_category": "Treatments", "tertiary_category": "Face Serums",
                   "highlights": ["Dryness", "Vegan"],
                   "ingredients": "Water, Glycerin, Niacinamide, Sodium Hyaluronate", "price_krw": 30800}
        r = client.post("/api/products", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        b = r.json()
        self.assertEqual(b["products"], before + 1)
        reg = b["registered"][0]
        self.assertEqual(reg["action"], "added")
        self.assertTrue(reg["reserved_candidate"])
        self.assertFalse(reg["brand_in_vocab"])
        self.assertEqual(reg["rating_source"], "injected")
        self.assertAlmostEqual(reg["price_usd"], 30800 / rs.KRW_PER_USD, places=2)
        # 바로 다음 요청부터 전용 칸 후보다 — 다른 테스트가 먼저 등록한 것이 있을 수 있어
        # 후보 수만큼(최대 10) 전용 칸을 열어 확인한다
        self.assertTrue(client.get("/api/products/SB0TEST1").json()["reserved_candidate"])
        n_reg = client.get("/health").json()["registered_products"]
        rec = client.get("/api/recommend", params={"size": 20, "reserved": min(10, n_reg)}).json()
        ids = [i["product_id"] for i in rec["items"] if i["reserved"]]
        self.assertIn("SB0TEST1", ids)
        # 영속: 파일에 남는다
        with open(_COPY, encoding="utf-8") as f:
            self.assertTrue(any(json.loads(l)["product_id"] == "SB0TEST1" for l in f if l.strip()))

    def test_register_same_id_replaces(self):
        p = {"product_id": "SB0TEST2", "product_name": "a", "brand_name": "SSAFY Beauty",
             "secondary_category": "Masks", "tertiary_category": "Face Masks",
             "highlights": ["Pores"], "ingredients": "Water, Kaolin", "price_usd": 6}
        n0 = client.post("/api/products", json=p).json()["products"]
        p["product_name"] = "b"
        r = client.post("/api/products", json=[p]).json()      # 배열도 받는다
        self.assertEqual(r["registered"][0]["action"], "replaced")
        self.assertEqual(r["products"], n0)

    def test_register_contract_violation_422(self):
        r = client.post("/api/products", json={
            "product_name": "x", "brand_name": "B", "secondary_category": "Nope",
            "tertiary_category": "Nope", "ingredients": "Water", "price_krw": 1000})
        self.assertEqual(r.status_code, 422)
        d = r.json()["detail"]
        self.assertEqual(d["code"], "REGISTRATION_CONTRACT_VIOLATION")
        self.assertTrue(any("secondary_category" in e for e in d["errors"]))
        # 하나라도 위반이면 아무것도 편입되지 않는다
        self.assertEqual(client.get("/api/products/x").status_code, 404)

    def test_member_converting_registered_product_gets_personalized(self):
        pid = "member-216"
        client.post("/api/events", json={"persona_id": pid, "events": [
            {"event_name": "add_to_cart", "product_id": "SB000003", "properties": {}}]})
        b = client.get("/api/recommend", params={"persona_id": pid, "size": 10, "reserved": 2}).json()
        self.assertEqual(b["state_source"], "events")
        self.assertNotIn("SB000003", [i["product_id"] for i in b["items"]])


if __name__ == "__main__":
    unittest.main()
