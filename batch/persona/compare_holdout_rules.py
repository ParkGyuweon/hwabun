# -*- coding: utf-8 -*-
"""계약 §7.1 과 eval_metadata.jsonl 이 서로 다른 정답을 고르는 규모를 잰다.

두 규칙은 목적이 다르다.

    계약 §7.1          가장 **최신** 리뷰를 숨기고 맞힐 수 있나 (recency holdout)
                       최신 리뷰가 부정이면 negative/diagnostic 으로 남긴다
    eval_metadata.py   마지막 **긍정** 리뷰를 맞힐 수 있나 (positive-target recall)
                       긍정이 아니면 더 앞으로 거슬러 올라간다

어느 쪽이 옳다고 이 스크립트가 정하지 않는다. 결정에 필요한 수치만 낸다.
`batch/jobs/eval_metadata.py` 는 읽기만 하고 고치지 않는다.

실행
    py batch/persona/compare_holdout_rules.py --out docs/analytics/persona-holdout-rule-conflict.md
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


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_eval_metadata():
    rows = {}
    with open(EVAL_METADATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows[row["persona_id"]] = row
    return rows


def compare(personas, product_ids, metadata):
    stats = Counter()
    labels = Counter()
    seed_delta = Counter()
    examples = []

    for persona in personas:
        pid = persona["persona_id"]
        reviews = persona.get("reviews", [])
        roles, decision = hr.classify(reviews, product_ids)
        stats["personas"] += 1

        if decision is None:
            stats["후보 없음"] += 1
            continue
        labels[decision["label"] or "excluded"] += 1
        if not decision["is_holdout_eligible"]:
            stats["계약 eligible=false"] += 1

        # 누출 방지가 없었다면 정답 상품이 seed 에 남았을 사람
        # (계약 §7.1-7 을 글자대로 읽은 경우)
        if any(role == hr.EXCLUDED and rid != decision["review"]["review_id"]
               for rid, role in roles.items()):
            stats["같은 상품 이전 리뷰"] += 1

        meta = metadata.get(pid)
        if meta is None:
            stats["eval_metadata 미포함"] += 1
            continue
        stats["대조 가능"] += 1

        contract_target = decision["canonical_product_id"]
        metadata_target = meta.get("target_product_id")
        if contract_target != metadata_target:
            stats["target 불일치"] += 1
            if len(examples) < 5:
                examples.append({
                    "persona_id": pid,
                    "contract_target": contract_target,
                    "contract_label": decision["label"],
                    "contract_rating": decision["review"].get("rating"),
                    "contract_submitted_at": decision["review"].get("submission_time"),
                    "metadata_target": metadata_target,
                    "metadata_submitted_at": meta.get("target_submitted_at"),
                })

        contract_seeds = {hr.canonical_product_id(r)
                          for r in reviews if roles.get(r["review_id"]) == hr.SEED}
        metadata_seeds = set(meta.get("seed_product_ids") or [])
        delta = len(contract_seeds) - len(metadata_seeds)
        seed_delta[delta] += 1
        if contract_seeds != metadata_seeds:
            stats["seed 집합 불일치"] += 1

    return stats, labels, seed_delta, examples


def _pct(part, whole):
    return f"{part / whole * 100:.1f}%" if whole else "-"


def render(full, sample, agent, examples):
    fs, fl, _, _ = full
    ss, _, _, _ = sample
    as_, al, _, _ = agent
    n = fs["personas"]

    lines = [
        "# Holdout 규칙 불일치 — 결정 요청",
        "",
        "> **임시 문서.** 박규원 님과 결정한 뒤 삭제한다. 커밋 대상이 아니다.",
        f"> 생성: `batch/persona/compare_holdout_rules.py` · 대상 PC {n:,}명 · PA {as_['personas']}명",
        "",
        "## 1. 무엇이 다른가",
        "",
        "| | `contracts/persona-schema.md` §7.1 | `batch/jobs/eval_metadata.py` |",
        "| --- | --- | --- |",
        "| 정답 선택 | 가장 **최신** 리뷰 1건 | 마지막 **긍정**(평점 4+) 리뷰 |",
        "| 최신이 부정일 때 | `negative`/`diagnostic` 으로 보존, `eligible=false` | 더 앞으로 거슬러 올라감 |",
        "| 묻는 질문 | \"이 사람의 다음 행동을 맞히나\" | \"이 사람이 좋아할 상품을 맞히나\" |",
        "| 쓰이는 곳 | `persona_holdout_target` (DW·Persona 계약) | AI 평가 3축 (오프라인·동적·리뷰재생) |",
        "",
        "## 2. 규모 (PC 9,900명)",
        "",
        "| 항목 | 인원 | 비율 |",
        "| --- | ---: | ---: |",
        f"| target 불일치 | {fs['target 불일치']:,} | {_pct(fs['target 불일치'], n)} |",
        f"| seed 상품 집합 불일치 | {fs['seed 집합 불일치']:,} | {_pct(fs['seed 집합 불일치'], n)} |",
        f"| 계약 규칙에서 `is_holdout_eligible=false` | {fs['계약 eligible=false']:,} | {_pct(fs['계약 eligible=false'], n)} |",
        "",
        f"계약 규칙의 label 분포 — "
        + " · ".join(f"`{k}` {v:,}" for k, v in sorted(fl.items(), key=lambda x: -x[1])),
        "",
        f"PC 100명 샘플(`pc100`) 기준 — target 불일치 {ss['target 불일치']}명, "
        f"eligible=false {ss['계약 eligible=false']}명. 100명 표본이라 방향만 읽을 것.",
        "",
        "**PA 100명은 `eval_metadata.jsonl` 에 없어 대조군이 없다.** 계약 규칙으로만 산출했고 "
        + " · ".join(f"`{k}` {v}" for k, v in sorted(al.items(), key=lambda x: -x[1]))
        + f" ({as_['계약 eligible=false']}명이 `eligible=false`).",
        "",
        "## 3. 불일치 사례",
        "",
        "| persona_id | 계약 target (평점·작성일) | eval_metadata target (작성일) |",
        "| --- | --- | --- |",
    ]
    for e in examples:
        lines.append(
            f"| `{e['persona_id']}` | `{e['contract_target']}` "
            f"({e['contract_rating']}점 · {e['contract_submitted_at']} · {e['contract_label']}) "
            f"| `{e['metadata_target']}` ({e['metadata_submitted_at']}) |")

    lines += [
        "",
        "## 4. 선택지",
        "",
        "**A. 계약을 `eval_metadata` 정의에 맞춘다** — §7.1 을 '마지막 긍정 리뷰' 로 개정.",
        "AI 평가 3축과 페르소나 테이블이 같은 문제를 풀게 된다. 대신 '최신 행동을 숨긴다' 는",
        f"recency holdout 의미가 사라지고, 최신 리뷰가 부정인 {fs['계약 eligible=false']:,}명의 신호를 잃는다.",
        "",
        "**B. 계약을 유지한다** — 페르소나 테이블과 AI 평가가 서로 다른 target 을 쓴다.",
        f"두 곳의 수치를 나란히 놓을 수 없고, {fs['target 불일치']:,}명에서 해석이 갈린다.",
        "",
        "**C. 둘 다 둔다** — `persona_holdout_target` 에 두 규칙의 결과를 각각 남기고",
        "소비처가 고른다. 계약에 규칙 식별 컬럼을 추가해야 하고 grain 이 늘어난다.",
        "",
        "## 5. 별건 — 이미 반영한 계약 수정 두 가지",
        "",
        "1. **`negative`/`diagnostic` 경계.** §7.1-5 가 경계를 정하지 않아",
        "   `recommendation-io-spec.md` 의 리뷰 극성(1~2 부정 / 3 중립)을 따랐다.",
        "2. **같은 상품의 이전 리뷰 누출.** §7.1-7 을 글자대로 적용하면 정답 상품이 seed 에도",
        f"   남는다. PC {fs['같은 상품 이전 리뷰']:,}명({_pct(fs['같은 상품 이전 리뷰'], n)}) · "
        f"PA {as_['같은 상품 이전 리뷰']}명({_pct(as_['같은 상품 이전 리뷰'], as_['personas'])}) 이 해당한다.",
        "   seed 상품은 `is_seen=true` 로 추천 후보에서 하드 제외되므로 그대로 두면 정답을 절대 맞힐 수 없다.",
        "   `eval_metadata.py` 도 같은 방어를 이미 하고 있어, 후보와 같은 상품의 이전 리뷰를",
        "   `excluded` 로 돌렸다. 이 조건을 §7.1-7 에 명시하는 계약 수정이 필요하다.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="계약 §7.1 vs eval_metadata 대조")
    ap.add_argument("--out", default=None, help="Markdown 리포트 경로. 없으면 표준 출력")
    args = ap.parse_args(argv)

    product_ids = {p["product_id"] for p in _load(PRODUCTS)}
    metadata = _load_eval_metadata()

    personas = sorted(_load(PERSONAS), key=lambda p: p["persona_id"])
    agents = sorted(_load(AGENT_PERSONAS), key=lambda p: p["persona_id"])

    full = compare(personas, product_ids, metadata)
    sample = compare(personas[:100], product_ids, metadata)
    agent = compare(agents, product_ids, metadata)

    report = render(full, sample, agent, full[3])
    if args.out:
        path = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
        print(f"리포트 -> {os.path.relpath(path, ROOT)}")
        print(f"  PC {full[0]['personas']:,}명 중 target 불일치 {full[0]['target 불일치']:,}명, "
              f"eligible=false {full[0]['계약 eligible=false']:,}명")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
