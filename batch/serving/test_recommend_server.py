# -*- coding: utf-8 -*-
"""추천 추론 서버의 계약을 고정한다 (Jira 206, 계약 §5).

여기서 막고 싶은 것
  * 응답에 계약 필드가 빠지는 것 (product_id · score · reserved · reason)
  * 전환한 상품이 추천에 다시 나오는 것 (노출 정책 §5 5단계)
  * 없는 persona 에 200 을 주는 것
  * 콜드 스타트가 죽는 것 — 이력 없는 사람도 size 개를 받아야 한다
  * reserved 가 size 를 넘거나 중복 상품이 나오는 것
"""
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

from fastapi.testclient import TestClient  # noqa: E402

import recommend_server as rs              # noqa: E402

client = TestClient(rs.app)
PID = "PC00001"


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = client.get("/health").json()

    def test_health(self):
        self.assertTrue(self.h["ok"])
        self.assertEqual(self.h["products"], 200)
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
        # 지금 카탈로그는 신규 상품이 0개라 전용 칸이 하나도 안 찍혀야 한다
        self.assertFalse(any(it["reserved"] for it in r["items"]))

    def test_recommendation_id_is_unique_per_call(self):
        a = client.get("/api/recommend", params={"persona_id": PID}).json()
        b = client.get("/api/recommend", params={"persona_id": PID}).json()
        self.assertNotEqual(a["recommendation_id"], b["recommendation_id"])
        self.assertEqual(a["algorithm"], b["algorithm"])

    def test_latency_is_reported(self):
        r = client.get("/api/recommend", params={"persona_id": PID, "seed": "review"}).json()
        self.assertGreater(r["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
