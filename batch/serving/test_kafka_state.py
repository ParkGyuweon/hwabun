# -*- coding: utf-8 -*-
"""Kafka 행동 이벤트 구독(Jira 226)을 고정한다 — 가짜 consumer 로 돈다 (로컬에 Kafka 없음).

여기서 막고 싶은 것
  * 수집 서버 메시지(snake_case JSON)가 observe 입력으로 잘못 매핑되는 것
  * 같은 event_id 가 두 번 반영되는 것 / 상태 무관 이벤트(노출)가 반영되는 것 / 깨진 메시지가 스레드를 죽이는 것
  * commit 이 상태 반영 전에 나가는 것 (순서)
  * 브로커가 없을 때 예외로 죽는 것 (물러났다 재시도해야 한다)
  * /health 에 kafka_state 가 안 실리는 것
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="kafka226_")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "p.jsonl")
os.environ["SESSION_EVENTS_PATH"] = os.path.join(_TMP, "s.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)
os.environ.pop("KAFKA_BOOTSTRAP_SERVERS", None)

import kafka_state as ks                   # noqa: E402


def msg(pid, name, eid, product="P479839", props=None, schema="0.2.0-draft"):
    """수집 서버 KafkaEventMessage 와 같은 모양 (snake_case)"""
    return json.dumps({"schema_version": schema, "event_id": eid, "event_name": name, "intent": "interest",
                       "occurred_at": "2026-09-09T10:00:00Z", "persona_id": pid, "session_id": "s1",
                       "page_view_id": "pv1", "sequence_no": 1, "page_type": "product_detail", "product_id": product,
                       "actor_type": "user", "environment": "production", "received_at": "2026-09-09T10:00:00Z",
                       "source": "web", "request_id": "r1", "event_index": 0,
                       "properties": props or {}, "tenant_id": None}, ensure_ascii=False).encode("utf-8")


class FakeMsg:
    def __init__(self, value, error=None): self._v, self._e = value, error
    def value(self): return self._v
    def error(self): return self._e


class FakeConsumer:
    """consume() 가 배치를 하나씩 내주고, commit 시점을 기록한다"""

    def __init__(self, batches, log):
        self.batches = list(batches); self.log = log; self.closed = False

    def subscribe(self, topics): self.log.append(("subscribe", tuple(topics)))

    def consume(self, num_messages=500, timeout=1.0):
        if self.batches:
            b = self.batches.pop(0); self.log.append(("consume", len(b))); return [FakeMsg(v) for v in b]
        time.sleep(0.01); return []

    def commit(self, asynchronous=False): self.log.append(("commit", asynchronous))
    def assignment(self): return []
    def close(self): self.closed = True


class TestParse(unittest.TestCase):
    def test_parse_collector_message(self):
        ev = ks.parse(msg("PC00001", "add_to_cart", "e1", props={"quantity": 1}))
        self.assertEqual(ev, {"event_id": "e1", "persona_id": "PC00001", "event_name": "add_to_cart",
                              "product_id": "P479839", "properties": {"quantity": 1}})

    def test_parse_rejects_bad(self):
        self.assertIsNone(ks.parse(b"not json"))
        self.assertIsNone(ks.parse(msg("PC00001", "add_to_cart", "e1", schema="9.9.0")))
        self.assertIsNone(ks.parse(json.dumps({"schema_version": "0.2.0-draft", "event_name": "x"}).encode()))
        self.assertIsNone(ks.parse(b"[1,2]"))

    def test_dedupe_lru(self):
        d = ks.Dedupe(size=3)
        self.assertFalse(d.seen("a")); self.assertTrue(d.seen("a"))
        d.seen("b"); d.seen("c"); d.seen("d")            # a 가 밀려난다
        self.assertFalse(d.seen("a"))


class TestConsumer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import recommend_server as rs
        cls.rs = rs
        cls.e = rs.get_engine()

    def _run(self, batches):
        log = []
        c = ks.StateConsumer(self.e, "fake:9092", consumer_factory=lambda: FakeConsumer(batches, log),
                             log=lambda m: None, poll_timeout=0.01)
        c.start()
        for _ in range(200):
            if c.stats["batches"] >= len(batches):
                break
            time.sleep(0.02)
        c.stop()
        return c, log

    def test_events_update_state_then_commit(self):
        pid = "member-kafka-1"
        before = self.e.recommend(pid, size=5)
        self.assertEqual(before["state_source"], "cold_start")
        g = before["items"][0]["product_id"]
        c, log = self._run([[msg(pid, "product_view", "k1", product=g),
                             msg(pid, "add_to_cart", "k2", product=g),
                             msg(pid, "product_impression", "k3", product="P1"),        # 상태 무관 → 필터
                             msg(pid, "add_to_cart", "k2", product=g),                 # 중복
                             b"broken json"]])                                          # 깨짐
        s = c.stats
        self.assertEqual((s["processed"], s["filtered"], s["duplicates"], s["invalid"]), (2, 1, 1, 1))
        self.assertEqual(s["commits"], 1)
        # commit 은 consume 뒤, 그리고 상태 반영 뒤 (순서)
        kinds = [k for k, *_ in log]
        self.assertEqual(kinds[:3], ["subscribe", "consume", "commit"])
        after = self.e.recommend(pid, size=5)
        self.assertEqual(after["state_source"], "events")
        self.assertNotIn(g, [i["product_id"] for i in after["items"]])
        self.assertIn(g, self.e.states[pid].converted)
        # 세션 로그(JSONL)에도 남았다 → 재시작 재생 가능
        rows = [json.loads(l) for l in open(self.e.session_log.path, encoding="utf-8")]
        self.assertTrue(any(r["persona_id"] == pid for r in rows))
        self.assertIsNotNone(s["last_processed_at"])
        self.assertFalse(s["alive"])                       # stop 뒤

    def test_two_personas_in_one_batch(self):
        c, _ = self._run([[msg("member-kafka-2", "add_to_cart", "m1", product="P454018"),
                           msg("member-kafka-3", "add_to_cart", "m2", product="P426340")]])
        self.assertEqual(c.stats["processed"], 2)
        self.assertIn("P454018", self.e.states["member-kafka-2"].converted)
        self.assertIn("P426340", self.e.states["member-kafka-3"].converted)

    def test_factory_failure_retries_and_does_not_raise(self):
        calls = []

        def factory():
            calls.append(1)
            raise ConnectionError("no brokers")
        c = ks.StateConsumer(self.e, "down:9092", consumer_factory=factory, log=lambda m: None, poll_timeout=0.01)
        c.start(); time.sleep(1.3); c.stop()
        self.assertGreaterEqual(len(calls), 1)
        self.assertGreaterEqual(c.stats["errors"], 1)
        self.assertFalse(c.stats["connected"])
        self.assertIn("no brokers", c.stats["last_error"])

    def test_health_field_absent_without_bootstrap(self):
        from fastapi.testclient import TestClient
        h = TestClient(self.rs.app).get("/health").json()
        self.assertIn("kafka_state", h)
        self.assertIsNone(h["kafka_state"])                # KAFKA_BOOTSTRAP_SERVERS 없음 → 구독 안 함


if __name__ == "__main__":
    unittest.main()
