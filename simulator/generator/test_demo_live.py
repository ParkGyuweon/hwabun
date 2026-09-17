# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from unittest import mock

from simulator.generator import demo_live


class DemoLiveCurrencyTest(unittest.TestCase):
    """Jira 341 — /live 생성 로그는 사이트·계약과 같은 KRW 로 만들고, 캐시 파일명에 통화를 넣어 옛 USD 캐시를 다시 쓰지 않는다."""

    def test_default_currency_is_krw(self):
        self.assertEqual("KRW", demo_live.DEFAULT_CURRENCY)

    def test_cache_path_carries_currency(self):
        self.assertEqual("demo_behavior_1000_KRW.jsonl", os.path.basename(demo_live.cache_path(1000)))
        self.assertEqual("demo_behavior_9900_USD.jsonl", os.path.basename(demo_live.cache_path(9900, "USD")))
        # 09-16 까지의 USD 캐시 이름과 겹치지 않는다
        self.assertNotEqual("demo_behavior_1000.jsonl", os.path.basename(demo_live.cache_path(1000)))

    def test_generator_cmd_passes_currency(self):
        cmd = demo_live.generator_cmd(1000, "x.jsonl", "KRW")
        self.assertEqual(["--limit", "1000", "--currency", "KRW", "--out", "x.jsonl"], cmd[-6:])
        self.assertTrue(cmd[1].endswith("gen_behavior_logs.py"))
        with self.assertRaises(SystemExit):
            demo_live.generator_cmd(1000, "x.jsonl", "EUR")

    def test_ensure_log_reuses_existing_file_without_running_generator(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "demo_behavior_10_KRW.jsonl")
            with open(p, "w") as f:
                f.write("{}\n")
            with mock.patch.object(demo_live.subprocess, "run") as run:
                self.assertEqual(p, demo_live.ensure_log(10, p))
                run.assert_not_called()


class EnvelopeTest(unittest.TestCase):
    """09-17 — Kafka 로 직접 넣는 되감기도 수집기가 채우는 봉투 다섯 필드를 채운다.

    안 채우면 정제가 `missing_required_field` 로 전부 버린다. 09-17 실측: 원천 256,554건 중
    253,596건(98.8%)이 이것 하나로 탈락, 전부 `source=simulator`."""

    # 계약(contracts/event-schema.json) 필수 19개 중 수집기가 채우는 다섯
    COLLECTOR_FIELDS = ("received_at", "source", "request_id", "event_index", "account_id")

    def test_envelope_fills_every_field_the_collector_would(self):
        e = demo_live.put_envelope({"actor_type": "synthetic"}, "2026-09-17T06:00:00.000Z", "req-1", 3)
        for k in self.COLLECTOR_FIELDS:
            self.assertIn(k, e, f"{k} 가 없으면 정제가 버린다")
        self.assertEqual("2026-09-17T06:00:00.000Z", e["received_at"])
        self.assertEqual("req-1", e["request_id"])
        self.assertEqual(3, e["event_index"])

    def test_source_follows_collector_rule(self):
        """KafkaEventMessage.sourceOf — synthetic 이면 simulator, 아니면 web"""
        self.assertEqual("simulator", demo_live.put_envelope({"actor_type": "synthetic"}, "t", "r", 0)["source"])
        self.assertEqual("web", demo_live.put_envelope({"actor_type": "user"}, "t", "r", 0)["source"])

    def test_account_id_is_null_not_absent(self):
        """수집기도 비로그인이면 null 로 넣는다. 키가 없는 것과 null 은 다르다 — 없으면 탈락한다"""
        e = demo_live.put_envelope({"actor_type": "synthetic"}, "t", "r", 0)
        self.assertIn("account_id", e)
        self.assertIsNone(e["account_id"])

    def test_existing_account_id_is_kept(self):
        e = demo_live.put_envelope({"actor_type": "user", "account_id": "PA00001"}, "t", "r", 0)
        self.assertEqual("PA00001", e["account_id"])

    def test_now_iso_ms_matches_occurred_at_shape(self):
        """생성기 occurred_at 과 같은 모양 — 밀리초 3자리 + Z"""
        import re
        self.assertRegex(demo_live.now_iso_ms(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


if __name__ == "__main__":
    unittest.main()
