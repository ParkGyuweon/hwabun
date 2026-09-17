# -*- coding: utf-8 -*-
"""/pipeline · /live 페이지가 내보내는 JS 가 문법적으로 온전한지 (2026-09-17).

두 상수 모두 raw 가 아닌 일반 문자열이다. 그래서 소스에 `\\n` 을 한 번만 쓰면 파이썬이
**진짜 줄바꿈**으로 바꾸고, 그 줄바꿈이 JS 문자열 리터럴 안으로 들어가면

    Uncaught SyntaxError: Invalid or unexpected token

이 나면서 **스크립트 전체가 안 돈다.** 화면은 떠 있는데 숫자가 하나도 없고 불이 다 꺼진다.
서버는 멀쩡히 값을 주고 있어서 원인을 찾는 데 오래 걸린다 — 09-17 에 실제로 그랬다.
JS 안에서 줄바꿈을 쓰려면 소스에 백슬래시를 하나 더 써야 한다.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "jobs"))

from pipeline_stats import PIPELINE_HTML  # noqa: E402
from live_stats import LIVE_HTML  # noqa: E402


def script_of(html):
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    return m.group(1) if m else ""


class HtmlScriptTest(unittest.TestCase):
    PAGES = (("/pipeline", PIPELINE_HTML), ("/live", LIVE_HTML))

    def test_every_page_has_a_script(self):
        for name, html in self.PAGES:
            with self.subTest(page=name):
                self.assertGreater(len(script_of(html)), 500, "스크립트가 비었다")

    def test_no_string_literal_runs_past_the_end_of_its_line(self):
        """따옴표가 홀수인 줄 = 문자열이 줄을 넘어갔다는 뜻이다"""
        for name, html in self.PAGES:
            for n, line in enumerate(script_of(html).split("\n"), 1):
                with self.subTest(page=name, line=n):
                    self.assertEqual(0, line.count("'") % 2, line[:120])
                    self.assertEqual(0, line.count('"') % 2, line[:120])

    def test_page_declares_utf8_and_korean_survives(self):
        for name, html in self.PAGES:
            with self.subTest(page=name):
                self.assertIn('<meta charset="utf-8">', html)
                self.assertIn("페르소나", html)

    def test_pipeline_cost_notice_matches_measurement(self):
        """09-17 실측(3명 75회 45크레딧)에서 환산한 값. 900 은 옛 값이다"""
        self.assertIn("크레딧 약 1,500", PIPELINE_HTML)
        self.assertNotIn("약 900 크레딧", PIPELINE_HTML)


if __name__ == "__main__":
    unittest.main()
