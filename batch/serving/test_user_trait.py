"""user_trait.py — 장기 성향 조회 (Jira 306).

깨지면 안 되는 것
  * 5행 → trait 별 점수 + primary(is_primary_trait, 없으면 최고점) + window_end_date·policy
  * identity_scope: account 가 persona 보다 먼저
  * 스냅샷이 없으면 get() 은 None 이고 서버는 그대로 돈다
  * dw MySQL 이 죽어 있으면 스냅샷으로 폴백하고 health.error 에 남는다
"""
import json
import os
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import user_trait as ut  # noqa: E402


def _rows(uid, scope, scores, primary, wed="2026-09-13", ver="user-trait-v2"):
    return [{"user_id": uid, "identity_scope": scope, "trait": t, "trait_score": s,
             "is_primary_trait": (t == primary), "window_end_date": wed, "trait_policy_version": ver}
            for t, s in scores.items()]


class TestAggregate(unittest.TestCase):
    def test_five_rows_fold_into_one(self):
        rows = _rows("u1", "account", {"price": 4.5, "ingredient": 1.0, "review": 0.0, "concern": 2.5, "participate": 0.0}, "price")
        d = ut.aggregate(rows)[("account", "u1")]
        self.assertEqual(d["primary"], "price")
        self.assertEqual(d["price"], 4.5)
        self.assertEqual(d["review"], 0.0)
        self.assertEqual(d["window_end_date"], "2026-09-13")
        self.assertEqual(d["trait_policy_version"], "user-trait-v2")
        self.assertEqual(d["identity_scope"], "account")

    def test_primary_falls_back_to_max_score_and_missing_traits_are_zero(self):
        rows = _rows("u2", "persona", {"concern": 3.0, "price": 1.0}, primary=None)
        d = ut.aggregate(rows)[("persona", "u2")]
        self.assertEqual(d["primary"], "concern")
        self.assertEqual(d["ingredient"], 0.0)
        self.assertEqual(d["participate"], 0.0)

    def test_truthy_strings_from_csv(self):
        rows = _rows("u3", "account", {"review": 2.0, "price": 5.0}, primary=None)
        rows[0]["is_primary_trait"] = "true"          # csv 는 문자열로 온다
        rows[1]["trait_score"] = "5.0"
        d = ut.aggregate(rows)[("account", "u3")]
        self.assertEqual(d["primary"], "review")
        self.assertEqual(d["price"], 5.0)

    def test_unknown_trait_is_ignored(self):
        rows = _rows("u4", "account", {"price": 1.0, "smell": 9.0}, "price")
        d = ut.aggregate(rows)[("account", "u4")]
        self.assertNotIn("smell", d)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trait306_")
        self.path = os.path.join(self.tmp, "user_trait_snapshot.jsonl")
        rows = (_rows("PC00001", "persona", {"price": 4.5, "concern": 2.5}, "price")
                + _rows("1001", "account", {"ingredient": 3.0}, "ingredient")
                + _rows("1001", "persona", {"review": 9.0}, "review"))     # 같은 id 가 두 scope 에 → account 우선
        with open(self.path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_get_and_scope_order(self):
        st = ut.UserTraitStore(snapshot_paths=(self.path,), mysql=None, reload_sec=0, log=lambda m: None)
        self.assertTrue(st.load().startswith("snapshot:"))
        self.assertEqual(st.get("PC00001")["primary"], "price")
        self.assertEqual(st.get("1001")["identity_scope"], "account")
        self.assertEqual(st.get("1001", scopes=("persona",))["primary"], "review")
        self.assertIsNone(st.get("nobody"))
        self.assertIsNone(st.get(None))
        h = st.health()
        self.assertEqual((h["rows"], h["users"]), (4, 3))

    def test_no_snapshot_means_none_not_crash(self):
        st = ut.UserTraitStore(snapshot_paths=(os.path.join(self.tmp, "missing.jsonl"),), mysql=None,
                               reload_sec=0, log=lambda m: None)
        self.assertIsNone(st.load())
        self.assertIsNone(st.get("PC00001"))
        self.assertIsNone(st.health()["source"])

    def test_mysql_failure_falls_back_to_snapshot(self):
        bad = {"host": "127.0.0.1", "port": "1", "user": "x", "password": "x", "db": "dw", "timeout": "1"}
        st = ut.UserTraitStore(snapshot_paths=(self.path,), mysql=bad, reload_sec=0, log=lambda m: None)
        self.assertTrue(st.load().startswith("snapshot:"))
        self.assertIn("dw_mysql", st.health()["error"])
        self.assertEqual(st.get("PC00001")["primary"], "price")


if __name__ == "__main__":
    unittest.main()
