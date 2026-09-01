# -*- coding: utf-8 -*-
"""수집 API 백프레셔 대응을 고정한다.

부하 테스트에서 "서버가 흘린 것" 과 "생성기가 버린 것" 이 섞이면 결과를 못 읽는다.
그래서 각 응답 코드에서 무엇을 하는지가 계약이다.
"""
import unittest

from simulator.collector_client import CollectorClient


class CollectorClientTest(unittest.TestCase):
    def build(self, statuses, **kw):
        """statuses 를 순서대로 돌려주는 클라이언트. 잠은 자지 않는다"""
        client = CollectorClient("http://x", log=lambda m: None, **kw)
        self.calls = []
        self.waits = []
        seq = list(statuses)

        def post(body, headers):
            code = seq.pop(0) if seq else "ok"
            self.calls.append((code, body.count(b'"event_id"')))
            if code == "ok":
                return "ok", None
            if isinstance(code, tuple):          # (코드, Retry-After)
                return code
            return code, None

        client._post = post
        return client

    def send(self, client, n=10):
        events = [{"event_id": f"e{i}"} for i in range(n)]
        import time
        real_sleep = time.sleep
        time.sleep = lambda s: self.waits.append(s)
        try:
            client.send(events)
        finally:
            time.sleep = real_sleep
        return client.stats

    def test_success(self):
        c = self.build(["ok"])
        st = self.send(c)
        self.assertEqual(10, st["sent"])
        self.assertEqual(0, st["dropped"] + st["gave_up"])

    def test_429_honors_retry_after(self):
        c = self.build([(429, 2.5), "ok"])
        st = self.send(c)
        self.assertEqual(10, st["sent"])
        self.assertEqual(1, st["retries"])
        self.assertIn(2.5, self.waits)          # 서버가 말한 만큼 기다린다

    def test_503_backs_off_and_retries(self):
        c = self.build([503, 503, "ok"])
        st = self.send(c)
        self.assertEqual(10, st["sent"])
        self.assertEqual(2, st["retries"])
        self.assertEqual([0.5, 1.0], self.waits)   # 지수 백오프

    def test_400_is_dropped_without_retry(self):
        c = self.build([400, "ok"])
        st = self.send(c)
        self.assertEqual(0, st["sent"])
        self.assertEqual(10, st["dropped"])
        self.assertEqual(0, st["retries"])       # 같은 요청은 몇 번을 보내도 거절된다

    def test_413_halves_the_batch(self):
        c = self.build([413, "ok", "ok"], max_batch=10)
        st = self.send(c)
        self.assertEqual(10, st["sent"])
        self.assertEqual([10, 5, 5], [n for _, n in self.calls])

    def test_gives_up_after_max_retries(self):
        c = self.build([503] * 10, max_retries=2)
        st = self.send(c)
        self.assertEqual(0, st["sent"])
        self.assertEqual(10, st["gave_up"])      # 조용히 사라지지 않는다
        self.assertEqual(2, st["retries"])

    def test_network_error_is_retried(self):
        c = self.build(["network", "ok"])
        st = self.send(c)
        self.assertEqual(10, st["sent"])
        self.assertEqual(1, st["retries"])


if __name__ == "__main__":
    unittest.main()
