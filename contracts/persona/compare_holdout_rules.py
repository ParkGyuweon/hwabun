# -*- coding: utf-8 -*-
"""계약 §7.1 과 평가 정본이 같은 정답을 고르는지 확인한다.

계약과 `batch/jobs/eval_metadata.py` 는 원래 서로 다른 정답을 골랐다 (PC 9,900명 중
752명). 계약을 정본 정의(마지막 긍정 리뷰)로 맞추면서 두 가지를 더 명시했고, 정본도
같은 기준을 반영했다.

    §7.1.1  긍정 조건에 is_recommended 를 포함한다 (평점 3 이상일 때만)
    §7.1.2  같은 날짜 리뷰의 tie-break 은 review_id DESC 다

2026-09-03 기준 PC 9,900명 · PA 100명 모두 target 불일치 0건이다. 규칙이나 원천이
바뀌면 여기서 다시 갈라지므로 회귀 확인용으로 남긴다. `--require-zero` 는 불일치가
1건이라도 있으면 종료 코드 2 로 실패한다.

`batch/jobs/eval_metadata.py` 는 읽기만 하고 고치지 않는다.

실행
    py contracts/persona/compare_holdout_rules.py
    py contracts/persona/compare_holdout_rules.py --require-zero
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import holdout_rule as hr                                    # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
AGENT_PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_100_agent.json")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
EVAL_METADATA = os.path.join(ROOT, "batch", "ingest", "data", "eval_metadata.jsonl")
EVAL_METADATA_AGENT = os.path.join(ROOT, "batch", "ingest", "data", "eval_metadata_agent.jsonl")

# PC 와 PA 는 파일이 분리돼 있다. PC 평가 표본에 PA 가 섞이면 안 되기 때문이다.

CAUSE_RECOMMENDED = "정본이 is_recommended 를 인정하지 않음 (계약 §7.1.1)"
CAUSE_TIE = "정본에 tie-break 기준이 없음 (계약 §7.1.2)"
CAUSE_OTHER = "설명되지 않는 차이"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_eval_metadata(path):
    """정본 파일 하나를 persona_id -> row 로 읽는다. 없으면 빈 dict."""
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows[row["persona_id"]] = row
    return rows


def _cause(reviews, target, product_ids):
    """이 사람의 target 이 정본과 갈린 이유를 하나로 고른다."""
    rating = target.get("rating")
    if rating is not None and rating < hr.POSITIVE_RATING_MIN and target.get("is_recommended") is True:
        return CAUSE_RECOMMENDED
    same_date = [r for r in reviews
                 if r.get("submission_time") == target.get("submission_time")
                 and hr.canonical_product_id(r) in product_ids]
    return CAUSE_TIE if len(same_date) > 1 else CAUSE_OTHER


def compare(personas, product_ids, metadata):
    stats = Counter()
    causes = Counter()
    examples = []

    for persona in personas:
        pid = persona["persona_id"]
        reviews = persona.get("reviews", [])
        roles, decision = hr.classify(reviews, product_ids)
        stats["personas"] += 1

        if decision is None or decision["review"] is None:
            stats["긍정 리뷰가 없어 target 없음"] += 1
            continue

        meta = metadata.get(pid)
        if meta is None:
            stats["정본에 없음"] += 1
            continue
        stats["대조 가능"] += 1

        contract_target = decision["canonical_product_id"]
        if contract_target == meta.get("target_product_id"):
            continue

        stats["target 불일치"] += 1
        cause = _cause(reviews, decision["review"], product_ids)
        causes[cause] += 1
        if cause == CAUSE_OTHER and len(examples) < 5:
            examples.append((pid, contract_target, meta.get("target_product_id"),
                             decision["review"].get("rating"),
                             decision["review"].get("submission_time")))

        contract_seeds = {hr.canonical_product_id(r)
                          for r in reviews if roles.get(r["review_id"]) == hr.SEED}
        if contract_seeds != set(meta.get("seed_product_ids") or []):
            stats["seed 집합 불일치"] += 1

    return stats, causes, examples


def report(title, stats, causes, examples):
    n = stats["personas"]
    print(f"[{title}] {n:,}명 · 대조 가능 {stats['대조 가능']:,}명")
    if stats["정본에 없음"]:
        print(f"  정본에 없어 대조 불가 {stats['정본에 없음']:,}명")
    if stats["긍정 리뷰가 없어 target 없음"]:
        print(f"  긍정 리뷰가 없어 target 없음 {stats['긍정 리뷰가 없어 target 없음']:,}명")

    mismatch = stats["target 불일치"]
    if not mismatch:
        print("  target 불일치 0건")
        return 0
    pct = mismatch / stats["대조 가능"] * 100 if stats["대조 가능"] else 0
    print(f"  target 불일치 {mismatch:,}명 ({pct:.1f}%) · seed 집합 불일치 {stats['seed 집합 불일치']:,}명")
    for cause, count in sorted(causes.items(), key=lambda x: -x[1]):
        print(f"    {count:>5,}명  {cause}")
    for pid, c, m, rating, date in examples:
        print(f"      {pid} 계약={c}({rating}점 {date}) 정본={m}")
    return causes[CAUSE_OTHER]


def main(argv=None):
    ap = argparse.ArgumentParser(description="계약 §7.1과 평가 정본의 정답 정렬 확인")
    ap.add_argument("--require-zero", action="store_true",
                    help="불일치가 1건이라도 있으면 종료 코드 2. 정본 재생성 후 인수 기준")
    args = ap.parse_args(argv)

    product_ids = {p["product_id"] for p in _load(PRODUCTS)}

    pc = sorted(_load(PERSONAS), key=lambda p: p["persona_id"])
    pa = sorted(_load(AGENT_PERSONAS), key=lambda p: p["persona_id"])

    unexplained = 0
    total_mismatch = 0
    for title, personas, meta_path in (("PC", pc, EVAL_METADATA),
                                       ("PA", pa, EVAL_METADATA_AGENT)):
        metadata = _load_eval_metadata(meta_path)
        stats, causes, examples = compare(personas, product_ids, metadata)
        unexplained += report(title, stats, causes, examples)
        total_mismatch += stats["target 불일치"]
        print()

    if unexplained:
        print(f"설명되지 않는 차이 {unexplained}건 — 어느 한쪽에 다른 문제가 있다")
        return 2
    if args.require_zero and total_mismatch:
        print(f"불일치 {total_mismatch}건 — 평가 정본이 계약 §7.1.1·§7.1.2를 아직 반영하지 않았다")
        return 2
    if total_mismatch:
        print("남은 차이는 모두 평가 정본이 계약 §7.1.1·§7.1.2를 반영하면 사라진다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
