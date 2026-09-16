# -*- coding: utf-8 -*-
"""Jira 337 — /pipeline 파이프라인 화면. 감시자는 가짜 소스로, 라우트는 TestClient 로."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "jobs"))

import pipeline_stats as ps  # noqa: E402
import kafka_state  # noqa: E402


class ActorStatsUnit(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(ps.classify("PC00001"), "persona")
        self.assertEqual(ps.classify("PA00042"), "agent")
        self.assertEqual(ps.classify("3bd65921-4b45"), "real")
        self.assertEqual(ps.classify(None), "real")

    def test_counts_users_conversions(self):
        a = ps.ActorStats()
        a.record("PC00001", "section_dwell"); a.record("PC00001", "add_to_cart"); a.record("PC00002", "purchase")
        a.record("PA00001", "product_view"); a.record("m-1", "begin_checkout")
        s = a.snapshot()
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["users"], 4)
        self.assertEqual(s["actors"]["persona"], {"total": 3, "users": 2, "per_sec_10s_avg": 0.3,
                                                  "add_to_cart": 1, "begin_checkout": 0, "purchase": 1})
        self.assertEqual(s["actors"]["agent"]["users"], 1)
        self.assertEqual(s["actors"]["real"]["begin_checkout"], 1)
        self.assertEqual(len(s["series_60s"]), 60)
        self.assertEqual(s["series_60s"][-1], 5)


class ConsumerObserverHook(unittest.TestCase):
    """상태 필터에 걸리는 dwell 도, 중복도 관찰자에게는 간다 — '사이트 활동' 은 필터 전 전부"""
    def test_observer_sees_filtered_and_duplicate(self):
        seen = []

        class Log:
            state_names = {"add_to_cart"}
            def append_many(self, items): pass

        class Eng:
            session_log = Log()
            def observe(self, pid, evs, **kw): return len(evs)

        c = kafka_state.StateConsumer(Eng(), "x:1", observer=lambda pid, name: seen.append((pid, name)))
        import json
        mk = lambda eid, name: json.dumps({"schema_version": "0.2.0", "event_id": eid, "persona_id": "PC1", "event_name": name})
        n = c.process_batch([mk("e1", "section_dwell"), mk("e2", "add_to_cart"), mk("e2", "add_to_cart"), b"not json"])
        self.assertEqual(n, 1)
        self.assertEqual(seen, [("PC1", "section_dwell"), ("PC1", "add_to_cart"), ("PC1", "add_to_cart")])
        self.assertEqual(c.stats["filtered"], 1); self.assertEqual(c.stats["duplicates"], 1); self.assertEqual(c.stats["invalid"], 1)


class WatchersWithFakes(unittest.TestCase):
    def test_spark_poll_parses_master_json(self):
        w = ps.SparkWatch("http://spark:18080", fetch=lambda url: {
            "aliveworkers": 1, "cores": 2, "coresused": 1, "status": "ALIVE",
            "activeapps": [{"name": "raw_sink", "state": "RUNNING", "cores": 1, "duration": 125000}], "completedapps": [{}, {}]})
        got = w.poll()
        self.assertEqual(got["workers_alive"], 1)
        self.assertEqual(got["apps"][0]["duration_sec"], 125)
        self.assertEqual(got["completed"], 2)

    def test_spark_unconfigured_is_wait_not_crash(self):
        w = ps.SparkWatch("")
        self.assertFalse(w.state["configured"])
        with self.assertRaises(RuntimeError):
            w.poll()

    def test_dw_poll_counts_marts(self):
        import datetime as dt
        calls = []

        def q(sqls):
            calls.append(sqls)
            if "information_schema" in sqls[0][0]:
                return [(("brand_daily_kpi", 5, dt.datetime(2026, 9, 16, 15, 0)), ("other", 1, None))]
            return [((7,),) for _ in sqls]
        w = ps.DwWatch({"host": "h", "user": "u", "db": "dw"}, marts=("brand_daily_kpi", "product_daily_kpi"), query=q)
        got = w.poll()
        self.assertTrue(got["schema_exists"]); self.assertEqual(got["tables"], 2)
        self.assertEqual(got["marts"]["brand_daily_kpi"], {"rows": 7, "updated": "2026-09-16T15:00:00"})
        self.assertIsNone(got["marts"]["product_daily_kpi"])
        self.assertIn("`dw`.`brand_daily_kpi`", calls[1][0][0])

    def test_broker_poll_with_fake_consumer(self):
        class TP:
            def __init__(self, topic, p, offset=0): self.topic, self.partition, self.offset = topic, p, offset

        class Meta:
            class T:
                partitions = {0: None, 1: None, 2: None}
            topics = {"activity-events": T()}

        class Fake:
            def list_topics(self, t, timeout): return Meta()
            def committed(self, tps, timeout): return [TP(tp.topic, tp.partition, {0: 10, 1: -1001, 2: 40}[tp.partition]) for tp in tps]
            def get_watermark_offsets(self, tp, timeout): return (0, {0: 12, 1: 5, 2: 40}[tp.partition])
            def close(self): pass
        import types
        fake_mod = types.SimpleNamespace(TopicPartition=TP)
        sys.modules.setdefault("confluent_kafka", fake_mod)
        try:
            w = ps.BrokerWatch("b:9092", "activity-events", "g", consumer_factory=Fake)
            got = w.poll()
        finally:
            if sys.modules.get("confluent_kafka") is fake_mod:
                del sys.modules["confluent_kafka"]
        self.assertEqual(got["end_total"], 57)
        self.assertEqual(got["partitions"]["0"], {"begin": 0, "end": 12, "committed": 10, "lag": 2})
        self.assertIsNone(got["partitions"]["1"]["committed"])      # commit 없음
        self.assertEqual(got["lag_total"], 2)


class PipelineEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import recommend_server as rs
        cls.client = TestClient(rs.app)

    def test_page_and_stats(self):
        r = self.client.get("/pipeline")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/pipeline/stats", r.text)
        self.assertIn("/live/demo/start", r.text)
        d = self.client.get("/pipeline/stats").json()
        for k in ("activity", "live", "kafka", "broker", "spark", "dw", "dashboard_url", "demo"):
            self.assertIn(k, d)
        self.assertEqual(set(d["activity"]["actors"]), {"persona", "agent", "real"})
        r2 = self.client.get("/live")                       # 기존 화면은 그대로
        self.assertEqual(r2.status_code, 200)


if __name__ == "__main__":
    unittest.main()
