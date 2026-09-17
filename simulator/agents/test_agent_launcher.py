# -*- coding: utf-8 -*-
"""에이전트 실행기가 러너를 부를 때 붙이는 인자 (2026-09-17).

실행기는 얇은 껍데기다. 버튼이 여기를 부르고 여기가 에이전트 본체를 띄운다.
인자를 하나 빠뜨리면 실행은 되는데 결과가 어디에도 안 남는다 — 09-17 에 100명을
한 시간 돌리고도 /pipeline 의 에이전트 축이 0 이었고, 33,870건을 손으로 따로 보내야 했다.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent_launcher as L  # noqa: E402


class StartArgsTest(unittest.TestCase):
    def setUp(self):
        self._cfg = dict(L._cfg)
        self._state = dict(L._state)
        os.environ.setdefault("GMS_KEY", "test-only-not-a-real-key")
        self.addCleanup(self._restore)

    def _restore(self):
        L._cfg.clear(); L._cfg.update(self._cfg)
        L._state.clear(); L._state.update(self._state)

    def _args(self, body=None, **cfg):
        """start() 를 부르되 실제 프로세스는 띄우지 않고 인자만 받아 본다"""
        L._cfg.update(cfg)
        L._state.update({"proc": None, "log": None, "started_at": None, "args": None})
        captured = {}

        class FakeProc:
            def poll(self):
                return None

        def fake_popen(args, **kw):
            captured["args"] = args
            return FakeProc()

        with mock.patch.object(L.subprocess, "Popen", fake_popen), \
             mock.patch("builtins.open", mock.mock_open()):
            L.start(body or {})
        return captured["args"]

    def test_post_is_added_so_events_reach_the_collector(self):
        """안 붙이면 로그가 파일로만 쌓이고 화면·마트에 안 들어간다"""
        args = self._args(site="https://example.test")
        self.assertIn("--post", args)
        self.assertEqual("https://example.test", args[args.index("--post") + 1])

    def test_post_defaults_to_the_site(self):
        """수집기는 사이트와 같은 곳이다 — 따로 주지 않아도 된다"""
        args = self._args(site="https://j15a306.p.ssafy.io")
        self.assertEqual("https://j15a306.p.ssafy.io", args[args.index("--post") + 1])

    def test_post_can_be_turned_off(self):
        for off in ("off", "none", "false", "OFF"):
            with self.subTest(off=off):
                args = self._args(post=off)
                self.assertNotIn("--post", args)

    def test_body_overrides_config(self):
        args = self._args({"post": "http://127.0.0.1:8080"}, site="https://example.test")
        self.assertEqual("http://127.0.0.1:8080", args[args.index("--post") + 1])

    def test_out_and_run_id_are_always_given(self):
        """--out 없이 돌리면 로그가 어디에도 안 남는다. run_id 는 재구매 마트 grain 에 쓴다"""
        args = self._args()
        self.assertIn("--out", args)
        self.assertIn("--simulation-run-id", args)

    def test_limit_is_capped_at_100(self):
        args = self._args({"limit": 5000})
        self.assertEqual("100", args[args.index("--limit") + 1])


if __name__ == "__main__":
    unittest.main()
