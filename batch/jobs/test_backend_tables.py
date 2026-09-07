# -*- coding: utf-8 -*-
"""백엔드 적재용 테이블이 DDL 과 맞는지 (Jira 194).

**CSV 헤더와 DDL 컬럼이 갈리면 적재할 때야 터진다.** 한쪽만 고치는 일이 잦고,
고친 사람은 다른 쪽을 안 본다. 그래서 두 파일을 서로 대조한다.

같이 보는 것:
    - PK 가 정말 유일한가 (중복 행이 있으면 적재가 통째로 실패한다)
    - 참조 무결성 — `product_ingredient.ingredient_id` 가 마스터에 있는가
    - `vocab_version` 이 파일마다 하나인가 (섞이면 차원 대응이 조용히 깨진다)

실행: python batch/jobs/test_backend_tables.py
"""
import csv
import io
import os
import re
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
SERVING = os.path.join(ROOT, "batch", "ingest", "data", "serving")
SQL = os.path.join(SERVING, "backend_tables.sql")

# 테이블 -> CSV. DDL 에 있는데 여기 없으면 그것도 잡는다
FILES = {
    "feature_block": "feature_block.csv",
    "ingredient_vocab": "ingredient_vocab.csv",
    "concern_vocab": "concern_vocab.csv",
    "product_ingredient": "product_ingredient.csv",
    "product_concern": "product_concern.csv",
    "ingredient_skin_affinity": "ingredient_skin_affinity.csv",
}

PRIMARY_KEYS = {
    "feature_block": ["vocab_version", "block_name"],
    "ingredient_vocab": ["vocab_version", "ingredient_id"],
    "concern_vocab": ["vocab_version", "concern_id"],
    "product_ingredient": ["vocab_version", "product_id", "ingredient_id"],
    "product_concern": ["vocab_version", "product_id", "concern_rank"],
    "ingredient_skin_affinity": ["vocab_version", "skin_type", "ingredient_id"],
}

# MySQL 8 예약어. 컬럼명으로 쓰면 백틱 없이는 적재가 안 된다
RESERVED = {"rank", "offset", "system", "groups", "lead", "lag", "row",
            "rows", "over", "window", "cume_dist", "dense_rank", "first_value"}


def parse_ddl(path):
    """CREATE TABLE 에서 컬럼 이름만 뽑는다. 제약 줄은 건너뛴다"""
    with io.open(path, encoding="utf-8") as f:
        sql = f.read()
    out = {}
    for m in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
        cols = []
        for line in m.group(2).splitlines():
            line = line.split("--")[0].strip().rstrip(",")
            if not line or line.upper().startswith(
                    ("PRIMARY KEY", "UNIQUE KEY", "KEY ", "FOREIGN KEY", "INDEX")):
                continue
            cols.append(line.split()[0])
        out[m.group(1)] = cols
    return out


def read_csv(name):
    with io.open(os.path.join(SERVING, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def header_of(name):
    with io.open(os.path.join(SERVING, name), encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


class BackendTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SQL):
            raise unittest.SkipTest(
                "backend_tables.sql 없음 — python batch/jobs/export_backend_tables.py")
        cls.ddl = parse_ddl(SQL)

    def test_ddl_covers_every_csv(self):
        self.assertEqual(set(FILES), set(self.ddl),
                         "DDL 의 테이블 목록과 내보내는 CSV 목록이 다르다")

    def test_header_matches_ddl(self):
        """열 이름과 **순서**까지 같아야 한다 — LOAD DATA 는 순서로 넣는다"""
        for table, name in FILES.items():
            with self.subTest(table):
                self.assertEqual(self.ddl[table], header_of(name))

    def test_no_reserved_words(self):
        for table, cols in self.ddl.items():
            for c in cols:
                with self.subTest(f"{table}.{c}"):
                    self.assertNotIn(c.lower(), RESERVED,
                                     f"{c} 는 MySQL 8 예약어다")

    def test_primary_key_is_unique(self):
        for table, keys in PRIMARY_KEYS.items():
            with self.subTest(table):
                seen = set()
                for r in read_csv(FILES[table]):
                    k = tuple(r[x] for x in keys)
                    self.assertNotIn(k, seen, f"{table} PK 중복: {k}")
                    seen.add(k)

    def test_one_vocab_version_per_file(self):
        """버전이 섞이면 ingredient_id 와 벡터 위치의 대응이 조용히 깨진다"""
        versions = set()
        for table, name in FILES.items():
            with self.subTest(table):
                v = {r["vocab_version"] for r in read_csv(name)}
                self.assertEqual(1, len(v), f"{table} 에 버전이 섞였다: {v}")
                versions |= v
        self.assertEqual(1, len(versions), f"파일끼리 버전이 다르다: {versions}")

    def test_ids_exist_in_master(self):
        """참조 무결성 — 마스터에 없는 id 를 쓰면 조인이 조용히 빈다"""
        ing = {r["ingredient_id"] for r in read_csv("ingredient_vocab.csv")}
        con = {r["concern_id"] for r in read_csv("concern_vocab.csv")}
        for name, col, master in (
                ("product_ingredient.csv", "ingredient_id", ing),
                ("ingredient_skin_affinity.csv", "ingredient_id", ing),
                ("product_concern.csv", "concern_id", con)):
            with self.subTest(name):
                bad = {r[col] for r in read_csv(name)} - master
                self.assertFalse(bad, f"{name} 의 {col} 가 마스터에 없다: {bad}")

    def test_ingredient_id_matches_vector_position(self):
        """id 는 배열 인덱스이자 **블록 안에서의 차원 위치**다. 0..n-1 로 빈틈없이"""
        for name, key in (("ingredient_vocab.csv", "ingredient_id"),
                          ("concern_vocab.csv", "concern_id")):
            with self.subTest(name):
                ids = sorted(int(r[key]) for r in read_csv(name))
                self.assertEqual(list(range(len(ids))), ids)

    def test_feature_block_offsets_are_contiguous(self):
        """블록 offset 이 앞 블록 끝과 붙어 있어야 벡터를 자를 수 있다"""
        rows = sorted(read_csv("feature_block.csv"),
                      key=lambda r: int(r["block_offset"]))
        off = 0
        for r in rows:
            self.assertEqual(off, int(r["block_offset"]), r["block_name"])
            off += int(r["dim"])
        self.assertEqual(148, off, "블록 폭 합이 벡터 차원과 다르다")

    def test_position_weight_range(self):
        for r in read_csv("product_ingredient.csv"):
            with self.subTest(r["product_id"], ing=r["ingredient"]):
                self.assertTrue(0.0 < float(r["position_weight"]) <= 1.0)
                self.assertIn(r["source"], ("tag", "parsed"))

    def test_skin_affinity_share_sums_to_one(self):
        """share 는 그 피부타입 안에서의 비중이다 — 합이 1 이 아니면 정규화가 틀렸다"""
        by_seg = {}
        for r in read_csv("ingredient_skin_affinity.csv"):
            by_seg.setdefault(r["skin_type"], []).append(float(r["share"]))
        self.assertTrue(by_seg, "행이 없다")
        for seg, vals in by_seg.items():
            with self.subTest(seg):
                self.assertAlmostEqual(1.0, sum(vals), places=2)


if __name__ == "__main__":
    unittest.main()
