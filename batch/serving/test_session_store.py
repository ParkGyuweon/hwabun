# -*- coding: utf-8 -*-
"""세션 상태 영속화(Jira 224)를 고정한다.

여기서 막고 싶은 것
  * 재시작(새 Engine) 뒤 상태가 사라져 cold_start 로 돌아가는 것
  * 상태와 무관한 이벤트(노출·page_view)까지 파일에 쌓이는 것
  * 깨진 줄 하나 때문에 재생이 멎는 것
  * compact 가 마지막 N건을 잘라내지 않거나 순서를 바꾸는 것
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="sess224_")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "p.jsonl")
os.environ["SESSION_EVENTS_PATH"] = os.path.join(_TMP, "session_events.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)

from session_store import SessionLog       # noqa: E402


class TestSessionLog(unittest.TestCase):
    def test_filter_keeps_state_events_only(self):
        log = SessionLog(os.path.join(tempfile.mkdtemp(), "s.jsonl"))
        evs = [{"event_name": "product_impression", "product_id": "P1", "properties": {}},
               {"event_name": "page_view", "product_id": None, "properties": {}},
               {"event_name": "add_to_cart", "product_id": "P1", "properties": {}},
               {"event_name": "scroll_depth", "product_id": "P1", "properties": {"depth_percent": 75}},
               {"event_name": "rage_click", "product_id": "P1", "properties": {}}]
        kept = [e["event_name"] for e in log.filter(evs)]
        self.assertEqual(kept, ["add_to_cart", "scroll_depth", "rage_click"])
        self.assertEqual(log.append("PC1", evs), 3)
        rows = [json.loads(l) for l in open(log.path, encoding="utf-8")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["persona_id"], "PC1")
        self.assertEqual(log.append("PC1", evs[:2]), 0)          # 남길 게 없으면 쓰지 않는다

    def test_replay_skips_broken_line_and_compact_keeps_last(self):
        log = SessionLog(os.path.join(tempfile.mkdtemp(), "s.jsonl"))
        for i in range(12):
            log.append("PC1", [{"event_name": "add_to_cart", "product_id": f"P{i}", "properties": {}}])
        with open(log.path, "a", encoding="utf-8") as f:
            f.write('{"persona_id": "PC1", "events": [{"event_name": "add_to_c')   # 중간에 죽은 쓰기
        seen = []
        n_p, n_e, _ = log.replay(lambda pid, evs: seen.extend(e["product_id"] for e in evs))
        self.assertEqual((n_p, n_e), (1, 12))
        self.assertEqual(seen, [f"P{i}" for i in range(12)])
        before, after = log.compact(keep_last=5)
        self.assertEqual((before, after), (12, 5))
        seen2 = []
        log.replay(lambda pid, evs: seen2.extend(e["product_id"] for e in evs))
        self.assertEqual(seen2, ["P7", "P8", "P9", "P10", "P11"])


class TestEngineRestart(unittest.TestCase):
    """POST /api/events 로 쌓은 상태가 새 Engine(재시작)에서도 살아 있어야 한다"""

    def test_state_survives_restart(self):
        import recommend_server as rs
        e1 = rs.Engine()
        pid = "member-224"
        cold = e1.recommend(pid, size=10)
        self.assertEqual(cold["state_source"], "cold_start")
        g = cold["items"][0]["product_id"]
        e1.observe(pid, [{"event_name": "product_view", "product_id": g, "properties": {}},
                         {"event_name": "add_to_cart", "product_id": g, "properties": {}},
                         {"event_name": "product_impression", "product_id": "P1", "properties": {}}])
        warm = e1.recommend(pid, size=10)
        self.assertEqual(warm["state_source"], "events")
        self.assertNotIn(g, [i["product_id"] for i in warm["items"]])
        # 파일에는 상태 이벤트 2건만
        rows = [json.loads(l) for l in open(e1.session_log.path, encoding="utf-8")]
        self.assertEqual(sum(len(r["events"]) for r in rows), 2)
        # 재시작
        e2 = rs.Engine()
        self.assertEqual(e2.session_replayed["personas"], 1)
        self.assertEqual(e2.session_replayed["events"], 2)
        again = e2.recommend(pid, size=10)
        self.assertEqual(again["state_source"], "events")
        self.assertEqual([i["product_id"] for i in again["items"]], [i["product_id"] for i in warm["items"]])
        self.assertIn(g, e2.states[pid].converted)
        # 재생은 파일에 다시 쓰지 않는다
        rows2 = [json.loads(l) for l in open(e2.session_log.path, encoding="utf-8")]
        self.assertEqual(len(rows2), len(rows))


if __name__ == "__main__":
    unittest.main()
