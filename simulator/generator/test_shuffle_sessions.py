# -*- coding: utf-8 -*-
"""Jira 337 — 세션 단위 섞기: 세션 안 순서·내용은 그대로, 세션 순서만 바뀐다"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shuffle_sessions as sh  # noqa: E402


class ShuffleSessions(unittest.TestCase):
    def test_sessions_stay_contiguous_and_ordered(self):
        d = tempfile.mkdtemp(); src = os.path.join(d, "a.jsonl"); dst = os.path.join(d, "b.jsonl")
        rows = []
        for p in range(5):
            for s in range(4):
                for i in range(3):
                    rows.append({"persona_id": f"PC{p}", "session_id": f"s{p}-{s}", "sequence_no": i, "x": "한글"})
        with open(src, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        n_ranges, written = sh.shuffle(src, dst, seed=1, log=lambda *a: None)
        self.assertEqual(n_ranges, 20)
        self.assertEqual(written, os.path.getsize(src))
        out = [json.loads(l) for l in open(dst, encoding="utf-8")]
        self.assertEqual(len(out), len(rows))
        self.assertEqual(sorted(json.dumps(r, sort_keys=True) for r in out), sorted(json.dumps(r, sort_keys=True) for r in rows))
        # 세션은 연속 구간이고 안에서는 sequence_no 0,1,2
        order = [r["session_id"] for r in out]
        seen = []
        for sid in order:
            if not seen or seen[-1] != sid:
                seen.append(sid)
        self.assertEqual(len(seen), 20)                       # 각 세션이 딱 한 구간
        for sid in set(order):
            self.assertEqual([r["sequence_no"] for r in out if r["session_id"] == sid], [0, 1, 2])
        self.assertNotEqual([r["session_id"] for r in rows], order)   # 실제로 섞였다


if __name__ == "__main__":
    unittest.main()
