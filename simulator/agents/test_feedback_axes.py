# -*- coding: utf-8 -*-
"""에이전트 피드백 축 라벨이 계약과 같은지 고정한다 (Jira 367).

09-19 까지 러너가 "효과·발림성·가격" 을 들고 있었고 계약·화면은 "효능·사용감·용량·가격" 이었다.
러너는 이 라벨로 `button[aria-label="…"]` 을 찾으므로 셋이 어긋난 채로 조용히 0건이 나갔다.
여기서 막고 싶은 것은 **다시 베껴 두는 것**이다.
"""
import json
import os
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)

import agent_runner as ar                     # noqa: E402

VOCAB = os.path.join(ROOT, "contracts", "feedback-category-vocab.json")


class FeedbackAxesTest(unittest.TestCase):
    def test_axes_come_from_the_contract_file(self):
        """화면 버튼의 aria-label 은 이 파일의 axes[].label 이다
        (frontend/src/types/feedback.ts 가 같은 파일을 import 한다)."""
        axes = json.load(open(VOCAB, encoding="utf-8"))["axes"]
        self.assertEqual({a["label"]: a["id"] for a in axes}, ar.FEEDBACK_AXES)

    def test_fallback_matches_the_contract_too(self):
        """대체값도 계약과 같아야 한다. 안 그러면 파일을 못 읽는 환경에서 같은 사고가 난다."""
        self.assertEqual(ar.FEEDBACK_AXES_FALLBACK, ar.FEEDBACK_AXES)

    def test_missing_file_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(ar.FEEDBACK_AXES_FALLBACK,
                             ar.load_feedback_axes(os.path.join(t, "nope.json")))

    def test_empty_axes_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "bad.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"axes": []}')
            self.assertEqual(ar.FEEDBACK_AXES_FALLBACK, ar.load_feedback_axes(p))

    def test_ids_are_what_the_server_stores(self):
        """DB shop_backend.feedback.axis_id 에 들어가는 값"""
        self.assertEqual({"efficacy", "texture", "scent", "packaging", "value"},
                         set(ar.FEEDBACK_AXES.values()))


class SummaryKeysTest(unittest.TestCase):
    def test_runner_summary_counts_feedback(self):
        """run_one 이 돌려주는 key 가 합산 dict 에 전부 있어야 한다.
        `feedbacks` 가 빠져 있어서 "의견 0건" 이 요약에 한 번도 안 찍혔다."""
        src = open(os.path.join(BD, "agent_runner.py"), encoding="utf-8").read()
        i = src.index("tot = dict(")
        tot_literal = src[i:src.index(")", src.index("reviewed=0", i))]
        for key in ("feedbacks", "feedback_failed", "reviewed", "banner_clicks"):
            self.assertIn(key, tot_literal, key)


if __name__ == "__main__":
    unittest.main()
