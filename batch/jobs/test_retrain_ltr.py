# -*- coding: utf-8 -*-
"""retrain_ltr 의 판정·파싱·교체 — 학습을 돌리지 않는 부분만 (학습·평가는 --dry-run 실측으로)"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retrain_ltr as rl                                   # noqa: E402
from ltr_features import load_ltr, SERVING                 # noqa: E402


class TestDecide(unittest.TestCase):
    def test_better_or_equal_promotes(self):
        self.assertEqual(rl.decide(43.80, 44.10), (True, "not_worse"))
        self.assertEqual(rl.decide(43.80, 43.80), (True, "not_worse"))

    def test_within_tolerance_promotes(self):
        self.assertEqual(rl.decide(43.80, 43.40, tolerance=0.5), (True, "within_tolerance"))

    def test_worse_keeps(self):
        ok, why = rl.decide(43.80, 42.90, tolerance=0.5)
        self.assertFalse(ok)
        self.assertTrue(why.startswith("worse_by_0.90"))

    def test_no_current_promotes_candidate(self):
        self.assertEqual(rl.decide(None, 40.0), (True, "no_current"))

    def test_unmeasured_candidate_never_promotes(self):
        self.assertEqual(rl.decide(43.80, None), (False, "candidate_unmeasured"))
        self.assertEqual(rl.decide(None, None), (False, "candidate_unmeasured"))


class TestParse(unittest.TestCase):
    def test_reads_recall_line(self):
        out = "평가 1,988명\n  Recall@10    43.80%   CI [41.6, 46.0]\n  MRR 0.2"
        self.assertEqual(rl.parse_recall(out), 43.80)

    def test_missing_is_none(self):
        self.assertIsNone(rl.parse_recall("선형으로 돕니다"))
        self.assertIsNone(rl.parse_recall(""))


class TestPromoteAndLoad(unittest.TestCase):
    def test_promote_copies_both_files_atomically(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            for f in rl.FILES:
                open(os.path.join(src, f), "wb").write(b"x")
            rl.promote(src, dst)
            self.assertEqual(sorted(os.listdir(dst)), sorted(rl.FILES))   # .new 가 남지 않는다

    def test_load_ltr_falls_back_to_image_model_when_dir_empty(self):
        """LTR_MODEL_DIR 이 빈 볼륨이면 serving/ 모델로 내려간다 — 선형으로 떨어지면 안 된다"""
        with tempfile.TemporaryDirectory() as empty:
            old = os.environ.get("LTR_MODEL_DIR")
            os.environ["LTR_MODEL_DIR"] = empty
            try:
                got = load_ltr()
            finally:
                if old is None:
                    os.environ.pop("LTR_MODEL_DIR", None)
                else:
                    os.environ["LTR_MODEL_DIR"] = old
        self.assertIsNotNone(got)
        self.assertEqual(got[1]["_dir"], os.path.abspath(SERVING))

    def test_load_ltr_explicit_missing_path_is_none(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(load_ltr(empty))


if __name__ == "__main__":
    unittest.main()
