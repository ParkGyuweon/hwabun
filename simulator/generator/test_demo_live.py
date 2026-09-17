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


if __name__ == "__main__":
    unittest.main()
