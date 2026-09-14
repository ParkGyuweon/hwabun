# -*- coding: utf-8 -*-
"""Jira 295 — /live 실시간 처리 현황. 다른 테스트 모듈과 같은 프로세스로 돌리지 않는다(등록 테스트 상품이 샌다)."""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "jobs"))

from live_stats import LiveStats  # noqa: E402


class LiveStatsUnit(unittest.TestCase):
    def test_counts_and_rates(self):
        ls = LiveStats()
        ls.record_events("PC00001", [{"event_name": "product_view", "product_id": "P1"},
                                     {"event_name": "add_to_cart", "product_id": "P1"}], source="kafka", partition=2)
        ls.record_events("M-1", [{"event_name": "wishlist_toggle", "product_id": "SB000001"}])
        ls.record_recommend("M-1", 12.5)
        ls.record_recommend("M-1", 30.0)
        s = ls.snapshot()
        self.assertEqual(s["events"]["total"], 3)
        self.assertEqual(s["events"]["per_sec"], 3)
        self.assertEqual(s["events"]["by_source"], {"kafka": 2, "http": 1})
        self.assertEqual(s["partitions"], {"2": 2})
        self.assertEqual(s["personas_touched"], 2)
        self.assertEqual(s["recommend"]["total"], 2)
        self.assertIn(s["recommend"]["p50_ms"], (12.5, 30.0))
        self.assertEqual(len(s["events"]["series_60s"]), 60)
        self.assertEqual(s["events"]["series_60s"][-1], 3)
        self.assertEqual(s["recent"][0]["persona_id"], "M-1")      # 최신이 먼저

    def test_window_trims_old(self):
        ls = LiveStats(window=1)
        ls._events.append((time.time() - 5, 7))
        ls.total_events += 7
        s = ls.snapshot()
        self.assertEqual(s["events"]["per_sec"], 0)
        self.assertEqual(s["events"]["total"], 7)            # 누적은 남는다


class LiveEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import recommend_server as rs
        cls.rs = rs
        cls.client = TestClient(rs.app)

    def test_page_and_stats(self):
        r = self.client.get("/live")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("/live/stats", r.text)
        before = self.client.get("/live/stats").json()
        self.client.post("/api/events", json={"persona_id": "LIVE-TEST-1", "events": [
            {"event_name": "product_view", "product_id": "P420652", "properties": {}}]})
        self.client.get("/api/recommend?persona_id=LIVE-TEST-1&size=3")
        after = self.client.get("/live/stats").json()
        self.assertGreaterEqual(after["events"]["total"], before["events"]["total"] + 1)
        self.assertGreaterEqual(after["recommend"]["total"], before["recommend"]["total"] + 1)
        self.assertEqual(after["recent"][0]["persona_id"], "LIVE-TEST-1")
        self.assertIn("sessions_in_memory", after)
        self.assertIn("kafka", after)

    def test_kafka_batch_records_partition(self):
        """(value, partition) 튜플로 들어오면 파티션이 /live 에 잡힌다 — 소비자 스레드 없이 process_batch 만"""
        import json
        from kafka_state import StateConsumer
        rs = self.rs
        e = rs.get_engine()
        c = StateConsumer.__new__(StateConsumer)
        c.engine = e
        c.state_names = None
        from kafka_state import Dedupe
        c.dedupe = Dedupe(1000)
        c.stats = {"invalid": 0, "filtered": 0, "duplicates": 0, "processed": 0, "last_processed_at": None}
        payload = json.dumps({"schema_version": "0.2.0-draft", "event_id": "live-ev-1", "event_name": "product_view", "persona_id": "LIVE-KAFKA-1",
                              "product_id": "P420652", "session_id": "s1", "properties": {}}, ensure_ascii=False).encode()
        n = c.process_batch([(payload, 1)])
        self.assertEqual(n, 1)
        s = self.client.get("/live/stats").json()
        self.assertGreaterEqual(int(s["partitions"].get("1", 0)), 1)
        self.assertEqual(s["events"]["by_source"].get("kafka", 0) >= 1, True)


if __name__ == "__main__":
    unittest.main()
