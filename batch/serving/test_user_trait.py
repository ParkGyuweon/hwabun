"""user_trait.py — 장기 성향 조회 (Jira 306).

깨지면 안 되는 것
  * 5행 → trait 별 점수 + primary(is_primary_trait, 없으면 최고점) + window_end_date·policy
  * identity_scope: account 가 persona 보다 먼저
  * 스냅샷이 없으면 get() 은 None 이고 서버는 그대로 돈다
  * dw MySQL 이 죽어 있으면 스냅샷으로 폴백하고 health.error 에 남는다
  * 신선도 (Jira 319): age_days 가 stale_days 를 넘으면 health.stale, max_age_days 를 넘으면 get() 은 None
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

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

    def _store(self, **kw):
        kw.setdefault("today", lambda: date(2026, 9, 14))          # 스냅샷 window_end_date 는 2026-09-13
        return ut.UserTraitStore(snapshot_paths=(self.path,), mysql=None, reload_sec=0, log=lambda m: None, **kw)

    def test_get_and_scope_order(self):
        st = self._store()
        self.assertTrue(st.load().startswith("snapshot:"))
        self.assertEqual(st.get("PC00001")["primary"], "price")
        self.assertEqual(st.get("1001")["identity_scope"], "account")
        self.assertEqual(st.get("1001", scopes=("persona",))["primary"], "review")
        self.assertIsNone(st.get("nobody"))
        self.assertIsNone(st.get(None))
        h = st.health()
        self.assertEqual((h["rows"], h["users"]), (4, 3))
        self.assertEqual((h["window_end_date"], h["age_days"], h["stale"], h["expired"]), ("2026-09-13", 1, False, False))

    def test_stale_flag_but_still_served(self):
        st = self._store(today=lambda: date(2026, 9, 16))           # 3일 — 배치 두 번 빠짐
        st.load()
        h = st.health()
        self.assertEqual((h["age_days"], h["stale"], h["expired"]), (3, True, False))
        self.assertEqual(st.get("PC00001")["window_end_date"], "2026-09-13")   # 값은 그대로 나간다

    def test_ttl_expired_returns_none(self):
        st = self._store(today=lambda: date(2026, 9, 28))           # 15일 > 14
        st.load()
        self.assertTrue(st.health()["expired"])
        self.assertIsNone(st.get("PC00001"))
        self.assertEqual(st.health()["users"], 3)                    # 표는 남아 있다. 배치가 돌면 바로 살아난다
        off = self._store(today=lambda: date(2026, 9, 28), max_age_days=0)
        off.load()
        self.assertEqual(off.get("PC00001")["primary"], "price")     # 0 이면 TTL 끔

    def test_age_days_handles_missing_or_bad_dates(self):
        self.assertIsNone(ut.age_days(None))
        self.assertIsNone(ut.age_days("not-a-date"))
        self.assertEqual(ut.age_days("2026-09-13T00:00:00", date(2026, 9, 15)), 2)

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



class TestSyntheticRows(unittest.TestCase):
    """Jira 346 — 페르소나(actor_type=synthetic, identity_scope=persona) 행도 읽는다. 첫 적재 뒤 rows 0 방지."""

    def test_default_query_reads_both_actor_types(self):
        self.assertIn("actor_type IN ('user', 'synthetic')", ut.DEFAULT_QUERY)
        self.assertIn("contributing_event_count", ut.DEFAULT_QUERY)

    def test_synthetic_persona_rows_are_served_for_pc_ids(self):
        rows = [dict(r, actor_type="synthetic") for r in
                _rows("PC00001", "persona", {"price": 0.9, "review": 0.2}, "price")]
        rows += [dict(r, actor_type="user") for r in
                 _rows("1001", "account", {"review": 0.8}, "review")]
        stats = {}
        table = ut.aggregate(rows, stats)
        self.assertEqual(table[("persona", "PC00001")]["primary"], "price")
        self.assertEqual(table[("account", "1001")]["primary"], "review")
        self.assertEqual(stats["rows_by_actor_type"], {"synthetic": 2, "user": 1})
        self.assertEqual(stats["duplicate_grains"], 0)

    def test_account_lookup_never_falls_through_to_a_persona_row_of_same_id(self):
        # 같은 문자열 id 가 두 scope 에 있어도 account 가 먼저고, persona 만 요청하면 persona 가 나온다
        rows = _rows("42", "account", {"review": 0.8}, "review") + \
               [dict(r, actor_type="synthetic") for r in _rows("42", "persona", {"price": 0.9}, "price")]
        d = tempfile.mkdtemp(); path = os.path.join(d, "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r) for r in rows) + "\n")
        st = ut.UserTraitStore(snapshot_paths=(path,), mysql=None, today=lambda: date(2026, 9, 14))
        st.load()
        self.assertEqual(st.get("42")["identity_scope"], "account")
        self.assertEqual(st.get("42", scopes=("persona",))["primary"], "price")
        h = st.health()
        self.assertEqual(h["rows_by_actor_type"], {"user": 1, "synthetic": 1})

    def test_duplicate_grain_prefers_later_window_then_more_events(self):
        older = [dict(r, actor_type="synthetic", contributing_event_count=500, window_end_date="2026-09-10")
                 for r in _rows("PC00002", "persona", {"price": 0.1}, "price")]
        newer = [dict(r, actor_type="synthetic", contributing_event_count=5, window_end_date="2026-09-13")
                 for r in _rows("PC00002", "persona", {"price": 0.7}, "price")]
        stats = {}
        table = ut.aggregate(older + newer, stats)           # 순서와 무관해야 한다
        self.assertEqual(table[("persona", "PC00002")]["price"], 0.7)
        table2 = ut.aggregate(newer + older, stats)
        self.assertEqual(table2[("persona", "PC00002")]["price"], 0.7)
        self.assertEqual(stats["duplicate_grains"], 1)
        same_day = [dict(r, actor_type="synthetic", contributing_event_count=n, window_end_date="2026-09-13")
                    for n, sc in ((3, 0.2), (30, 0.6)) for r in _rows("PC00003", "persona", {"price": sc}, "price")]
        self.assertEqual(ut.aggregate(same_day)[("persona", "PC00003")]["price"], 0.6)


if __name__ == "__main__":
    unittest.main()
