# -*- coding: utf-8 -*-
"""CF 동시발생 입력에서 홀드아웃 author_id 가 빠지는가 (Jira 203, 197 후속).

`build_cooc.excluded_authors()` 는 `simulator/personas/data/personas_*.json` 을
glob 으로 훑어 그 안의 author_id 전부를 CF 입력에서 뺀다. 홀드아웃 A/B 도 이름이
`personas_holdout_*.json` 이라 자동으로 잡힌다 — 데이터 파트가 14,000명·교집합 0 을
확인했다 (2026-09-08). 지금은 맞지만 지켜 주는 테스트가 없었다.

여기서 막으려는 사고는 둘이다.
  ① 홀드아웃 파일을 추가하거나 이름을 바꿨는데 glob 이 안 잡는 것 — 홀드아웃이
     동시발생에 남으면 **정답을 보고 정답을 맞힌다.** 수치가 조용히 올라간다
  ② 홀드아웃 A/B 가 겹치는 것 — 확인 세트가 선택 세트와 같은 사람을 갖게 된다

실행
    python -m unittest batch.jobs.test_build_cooc -v
"""
import glob
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import build_cooc  # noqa: E402

PDIR = build_cooc.PDIR


def _authors(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return {str(r["author_id"]) for r in rows if r.get("author_id")}


class TestExcludedAuthorsGlob(unittest.TestCase):
    """glob 규칙 자체 — 임시 디렉터리로 검사한다. 실데이터에 의존하지 않는다."""

    def _write(self, d, name, ids):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump([{"persona_id": f"X{i}", "author_id": a} for i, a in enumerate(ids)], f)

    def test_holdout_files_are_picked_up_by_glob(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "personas_9900.json", ["a1", "a2"])
            self._write(d, "personas_holdout_a.json", ["h1"])
            self._write(d, "personas_holdout_b.json", ["h2"])
            self._write(d, "personas_holdout_c.json", ["h3"])      # 앞으로 추가될 것
            self._write(d, "not_personas.json", ["zz"])            # 패턴 밖 — 안 잡혀야 한다
            with mock.patch.object(build_cooc, "PDIR", d):
                out, files = build_cooc.excluded_authors()
        self.assertEqual(out, {"a1", "a2", "h1", "h2", "h3"})
        self.assertNotIn("zz", out)
        self.assertEqual(len(files), 4)

    def test_author_id_is_string_and_empty_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "personas_x.json"), "w", encoding="utf-8") as f:
                json.dump([{"author_id": 123}, {"author_id": None}, {"author_id": ""}], f)
            with mock.patch.object(build_cooc, "PDIR", d):
                out, _ = build_cooc.excluded_authors()
        self.assertEqual(out, {"123"})


@unittest.skipUnless(glob.glob(os.path.join(PDIR, "personas_holdout_*.json")),
                     "홀드아웃 파일이 없는 환경")
class TestRealHoldoutsExcluded(unittest.TestCase):
    """실제 파일 — 지금 레포에 있는 홀드아웃 전부가 제외 집합에 들어가는가."""

    @classmethod
    def setUpClass(cls):
        cls.excluded, cls.files = build_cooc.excluded_authors()
        cls.holdouts = sorted(glob.glob(os.path.join(PDIR, "personas_holdout_*.json")))

    def test_every_holdout_author_is_excluded(self):
        for fp in self.holdouts:
            ids = _authors(fp)
            missing = ids - self.excluded
            self.assertFalse(missing, f"{os.path.basename(fp)} 의 author_id {len(missing)}명이 "
                                      f"CF 제외 집합에 없다 — 정답을 보고 정답을 맞히게 된다")
            self.assertIn(os.path.basename(fp), self.files)

    def test_holdouts_do_not_overlap(self):
        seen = {}
        for fp in self.holdouts:
            for a in _authors(fp):
                self.assertNotIn(a, seen, f"author {a} 가 {seen.get(a)} 와 "
                                          f"{os.path.basename(fp)} 양쪽에 있다")
                seen[a] = os.path.basename(fp)

    def test_holdout_size_matches_protocol(self):
        # 계약이 아니라 현재 체계(holdout-two-set-protocol) 의 값이다. 바뀌면 여기도 바꾼다.
        # a·b 2,000명(고르기·확인), c 6,400명(2026-09-30, 미사용 인원 전부 — 1%p 급을 보려고)
        expected = {"personas_holdout_a.json": 2000, "personas_holdout_b.json": 2000,
                    "personas_holdout_c.json": 6400}
        for fp in self.holdouts:
            name = os.path.basename(fp)
            self.assertIn(name, expected, f"{name} 은 체계에 없는 홀드아웃이다")
            self.assertEqual(len(_authors(fp)), expected[name], name)


if __name__ == "__main__":
    unittest.main()
