# -*- coding: utf-8 -*-
"""백엔드 적재용 정규화 테이블 (Jira 193).

왜 따로 뽑나
    `export_dashboard.py` 의 CSV 는 **대시보드가 바로 그리려고** 만든 것이라
    상품명·브랜드명이 행마다 반복된다(비정규화). 백엔드는 이미 상품 테이블을
    갖고 있으므로 그 열이 중복이고, 상품명이 바뀌면 두 곳을 고쳐야 한다.

    여기서는 **키와 값만** 낸다. 이름은 마스터 테이블에서 조인한다.

무엇을 내보내나
    feature_block.csv             벡터 148차원을 블록으로 자르는 법
    ingredient_vocab.csv          성분 30종 마스터
    concern_vocab.csv             피부 고민 9종 마스터
    product_ingredient.csv        상품 x 성분 (위치가중값)
    product_concern.csv           상품 x 고민 상위 2축
    ingredient_skin_affinity.csv  피부타입 x 성분

    DDL 은 `serving/backend_tables.sql` 에 같이 낸다.

⚠ 모든 행에 `vocab_version` 이 붙는다
    어휘가 늘면 차원 순서가 바뀌므로 **버전이 다른 행을 섞으면 안 된다.**
    `ingredient_id` 는 어휘집 배열의 인덱스이고 **블록 안에서의 차원 위치와
    같다** — 버전이 다르면 그 대응이 깨진다.

⚠ `position_weight` 는 함량이 아니다
    태그로 표시된 성분은 1.0, 전성분에서 찾은 것은 **배합 순서 기반 감쇠**다.
    "앞쪽에 적혀 있다" 이지 "몇 % 들었다" 가 아니다.

실행: python batch/jobs/export_backend_tables.py [--out DIR]
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from product_encoder import Encoder                     # noqa: E402

DATA = os.path.join(ROOT, "batch", "ingest", "data")
OUT_DIR = os.path.join(DATA, "serving")
CONTRACTS = os.path.join(ROOT, "contracts")
VOCAB = os.path.join(CONTRACTS, "product-feature-vocab.json")
LABELS = os.path.join(CONTRACTS, "product-form-labels-ko.json")
CONCERN_NPZ = os.path.join(DATA, "concern_from_reviews.npz")
AFFINITY = os.path.join(DATA, "affinity_lift.csv")

SKIN_TYPES = ("combination", "dry", "normal", "oily")
LIFT_MIN = 1.2          # 1.0 은 평균이라 그 근처를 섞으면 신호가 묽어진다
CONCERN_TOP = 2


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def load_labels():
    d = json.load(open(LABELS, encoding="utf-8"))
    # highlights_groups 는 `group`/`hint` 라 모양이 다르다 — 여기서는 안 쓴다
    return {k: {x["value"]: x["ko"] for x in v if "value" in x}
            for k, v in d.items() if isinstance(v, list)}


def block_of(vocab, name):
    return [x for x in vocab["blocks"] if x["name"] == name][0]


def export_feature_block(vocab, path):
    """벡터를 블록으로 자르는 법. 이게 없으면 벡터가 숫자 덩어리다"""
    rows, off = [], 0
    for b in vocab["blocks"]:
        rows.append([b["name"], off, b["dim"], b["block_weight"], b["encoding"],
                     vocab["version"]])
        off += b["dim"]
    for s in vocab.get("scalars", []):
        nm = s if isinstance(s, str) else s.get("name")
        rows.append([nm, off, 1, "", "scalar", vocab["version"]])
        off += 1
    # `offset` 은 MySQL 8 예약어라 `block_offset` 으로 낸다. DDL 과 헤더가
    # 어긋나면 CSV 를 그대로 적재할 수 없다
    n = write_csv(path, ["block_name", "block_offset", "dim", "block_weight",
                         "encoding", "vocab_version"], rows)
    return n, off


def export_vocab(vocab, labels, block, path):
    """어휘 마스터. id 는 배열 인덱스이자 블록 안에서의 차원 위치다"""
    b = block_of(vocab, block)
    df = b.get("doc_freq") or {}
    ko = labels.get(block, {})
    rows = [[i, v, ko.get(v, ""), int(df.get(v, 0)), vocab["version"]]
            for i, v in enumerate(b["vocab"])]
    return write_csv(path, [block + "_id", block, "label_ko", "doc_freq",
                            "vocab_version"], rows)


def export_product_ingredient(enc, vocab, path):
    """상품 x 성분. 상품명·브랜드명은 넣지 않는다 — 상품 테이블에서 조인한다"""
    idx = {v: i for i, v in enumerate(block_of(vocab, "ingredient")["vocab"])}
    rows = []
    for p in enc.products:
        vals = enc.ingredient_values(p)
        tagged = {h for h in p["highlights"] if h in enc.tag_ing}
        for name, v in sorted(vals.items(), key=lambda kv: -kv[1]):
            if name not in idx:
                continue          # 어휘집 밖 성분은 벡터에 안 들어간다
            rows.append([p["product_id"], idx[name], name, round(float(v), 4),
                         "tag" if name in tagged else "parsed", vocab["version"]])
    return write_csv(path, ["product_id", "ingredient_id", "ingredient",
                            "position_weight", "source", "vocab_version"], rows)


def export_product_concern(enc, vocab, path, top=CONCERN_TOP):
    if not os.path.exists(CONCERN_NPZ):
        print("  concern_from_reviews.npz 없음 — 건너뜁니다")
        return 0
    idx = {v: i for i, v in enumerate(block_of(vocab, "concern")["vocab"])}
    d = np.load(CONCERN_NPZ, allow_pickle=True)
    gid = [str(x) for x in d["group_id"]]
    axes = [str(x) for x in d["axes"]]
    score = np.asarray(d["score"], np.float64)
    known = {p["product_id"] for p in enc.products}
    rows = []
    for i, g in enumerate(gid):
        if g not in known:
            continue
        for rank, jj in enumerate(np.argsort(-score[i])[:top], 1):
            if score[i][jj] <= 0:
                continue          # 0 이면 "그 고민을 말한 리뷰가 없다"
            rows.append([g, rank, idx.get(axes[jj], -1), axes[jj],
                         round(float(score[i][jj]), 4), vocab["version"]])
    # `rank` 도 예약어다 (MySQL 8 윈도우 함수)
    return write_csv(path, ["product_id", "concern_rank", "concern_id", "concern",
                            "score", "vocab_version"], rows)


def export_ingredient_skin(enc, vocab, path):
    """피부타입 x 성분. 위치가중값과 세그먼트 lift 의 **곱이라 인과가 아니다**"""
    if not os.path.exists(AFFINITY):
        print("  affinity_lift.csv 없음 — 건너뜁니다")
        return 0
    idx = {v: i for i, v in enumerate(block_of(vocab, "ingredient")["vocab"])}
    by_seg = defaultdict(dict)
    with open(AFFINITY, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            seg, gid = r.get("segment"), r.get("group_id")
            if seg not in SKIN_TYPES or not gid:
                continue
            try:
                lift = float(r.get("lift") or 0)
            except ValueError:
                continue
            if lift >= LIFT_MIN:
                by_seg[seg][gid] = lift

    ing = {p["product_id"]: enc.ingredient_values(p) for p in enc.products}
    rows = []
    for seg in SKIN_TYPES:
        acc, support = defaultdict(float), defaultdict(set)
        for gid, lift in by_seg.get(seg, {}).items():
            for name, v in ing.get(gid, {}).items():
                if name not in idx:
                    continue
                acc[name] += v * lift
                support[name].add(gid)
        total = sum(acc.values()) or 1.0
        for name, v in sorted(acc.items(), key=lambda kv: -kv[1]):
            rows.append([seg, idx[name], name, round(v / total, 5),
                         len(support[name]), vocab["version"]])
    return write_csv(path, ["skin_type", "ingredient_id", "ingredient",
                            "share", "n_products", "vocab_version"], rows)


DDL = """-- 추천 파생 테이블 (batch/jobs/export_backend_tables.py 가 만든 CSV 적재용)
--
-- vocab_version 이 다른 행을 섞지 마십시오. 차원 순서가 어휘집에 묶여 있어
-- 버전이 다르면 ingredient_id 와 벡터 위치의 대응이 깨집니다.
--
-- product_id 는 상품 테이블의 키를 그대로 씁니다. FK 는 그쪽 스키마에 맞춰
-- 붙이십시오 (여기서는 걸지 않았습니다).

CREATE TABLE feature_block (
  block_name    VARCHAR(32)  NOT NULL,
  block_offset  INT          NOT NULL,   -- 148차원 벡터 안에서의 시작 위치
  dim           INT          NOT NULL,
  block_weight  DECIMAL(4,2) NULL,
  encoding      VARCHAR(32)  NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, block_name)
);

CREATE TABLE ingredient_vocab (
  ingredient_id INT          NOT NULL,   -- ingredient 블록 안에서의 차원 위치
  ingredient    VARCHAR(64)  NOT NULL,   -- 계약 원문. API 키로 이것을 쓸 것
  label_ko      VARCHAR(64)  NULL,       -- 화면 표시용. 키로 쓰지 말 것
  doc_freq      INT          NOT NULL,   -- 이 성분을 가진 상품 수
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, ingredient_id),
  UNIQUE KEY uk_ingredient (vocab_version, ingredient)
);

CREATE TABLE concern_vocab (
  concern_id    INT          NOT NULL,
  concern       VARCHAR(64)  NOT NULL,
  label_ko      VARCHAR(64)  NULL,
  doc_freq      INT          NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, concern_id),
  UNIQUE KEY uk_concern (vocab_version, concern)
);

CREATE TABLE product_ingredient (
  product_id      VARCHAR(16)  NOT NULL,
  ingredient_id   INT          NOT NULL,
  ingredient      VARCHAR(64)  NOT NULL,
  position_weight DECIMAL(6,4) NOT NULL,  -- 0~1. 함량이 아니라 배합 순서 기반
  source          VARCHAR(8)   NOT NULL,  -- 'tag' = 원본 태그, 'parsed' = 전성분에서 복원
  vocab_version   VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, product_id, ingredient_id),
  KEY ix_ingredient (vocab_version, ingredient_id)
);

CREATE TABLE product_concern (
  product_id    VARCHAR(16)  NOT NULL,
  concern_rank  TINYINT      NOT NULL,   -- 1 = 리뷰가 가장 많이 말한 고민
  concern_id    INT          NOT NULL,
  concern       VARCHAR(64)  NOT NULL,
  score         DECIMAL(8,4) NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, product_id, concern_rank)
);

CREATE TABLE ingredient_skin_affinity (
  skin_type     VARCHAR(16)  NOT NULL,   -- combination | dry | normal | oily
  ingredient_id INT          NOT NULL,
  ingredient    VARCHAR(64)  NOT NULL,
  share         DECIMAL(8,5) NOT NULL,   -- 그 피부타입 안에서의 비중 (합 1.0)
  n_products    INT          NOT NULL,   -- 근거가 된 상품 수. 작으면 인용 주의
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, skin_type, ingredient_id)
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    enc = Encoder()
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    labels = load_labels()

    def out(name):
        return os.path.join(a.out, name)

    n_blk, total_dim = export_feature_block(vocab, out("feature_block.csv"))
    n_iv = export_vocab(vocab, labels, "ingredient", out("ingredient_vocab.csv"))
    n_cv = export_vocab(vocab, labels, "concern", out("concern_vocab.csv"))
    n_pi = export_product_ingredient(enc, vocab, out("product_ingredient.csv"))
    n_pc = export_product_concern(enc, vocab, out("product_concern.csv"))
    n_is = export_ingredient_skin(enc, vocab, out("ingredient_skin_affinity.csv"))

    with open(out("backend_tables.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(DDL)

    print("어휘집 %s · 벡터 %d차원\n" % (vocab["version"], total_dim))
    print("  feature_block.csv             %5d행   벡터를 자르는 법" % n_blk)
    print("  ingredient_vocab.csv          %5d행   성분 마스터" % n_iv)
    print("  concern_vocab.csv             %5d행   고민 마스터" % n_cv)
    print("  product_ingredient.csv        %5d행   상품 x 성분" % n_pi)
    print("  product_concern.csv           %5d행   상품 x 고민 (상위 2)" % n_pc)
    print("  ingredient_skin_affinity.csv  %5d행   피부타입 x 성분" % n_is)
    print("  backend_tables.sql                   DDL 6개")
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
