#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실행 하나가 계약을 얼마나 밟았는지 보고한다.

`validate_events.py` 는 "이 Event 가 계약에 맞는가" 를 본다. 이 도구는 그 앞의
질문을 본다 — **이번 실행이 계약의 어디를 밟았고 어디를 안 밟았는가.**

둘 다 필요한 이유가 있다. 에이전트가 스크롤만 하다 떠나도 나온 Event 는 전부
계약에 맞으므로 검증기는 PASSED 를 준다. 그런데 전환 퍼널은 한 번도 안 돌았다.
"통과했다" 와 "확인했다" 가 다른 지점이고, 커버리지를 안 세면 구분이 안 된다.

보는 것 네 가지

    1. Event 커버리지    계약 Event 중 몇 종이 실제로 나왔나 (분류별)
    2. 계약 밖 Event      enum 에 없는 이름으로 나간 Event
    3. 봉투 검증          event-schema.json (validate_events.py 와 같은 기준)
    4. 필수 property      Event 별 required properties 위반

3번은 검증기와 겹치지만 4번은 겹치지 않는다. 검증기가 명시적으로 범위 밖에
두었고(properties 계약은 구현과 조율 전), Collector 도 properties 를 JsonNode 로
통과시킨다. 그래서 이 위반은 **bad_events 에도 안 남고 Processed 까지 그냥 흘러간다**
(event-taxonomy-trigger-schema.md §9.8). 세는 곳이 없으면 아무도 모른다.

필수 property 표는 문서에서 직접 읽는다. 여기에 복사해 두면 문서가 바뀔 때
조용히 어긋나고, 어긋난 줄 모른 채 "통과" 가 나온다.

입력
    .jsonl (한 줄 한 Event) · JSON 배열 · API 배치 본문({schema_version, events})

    agent_runner.py 가 남기는 파일은 Collector 이전 상태라 봉투 4필드
    (received_at·source·request_id·event_index)가 없다. 그대로 검증기에 넣으면
    Event 마다 그 4개가 오류로 뜬다. 없으면 Collector 규칙대로 채워서 검증하고
    보고서에 그 사실을 적는다.

실행
    python contracts/coverage_report.py simulator/agents/data/agent_events.jsonl
    python contracts/coverage_report.py <파일> --json report.json
    python contracts/coverage_report.py <파일> --group-by-persona

준비
    pip install -r contracts/requirements-validator.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SCHEMA_PATH = os.path.join(HERE, "event-schema.json")
TAXONOMY_PATH = os.path.join(ROOT, "docs", "analytics",
                             "event-taxonomy-trigger-schema.md")

BAR_W = 34


# ── 입력 ────────────────────────────────────────────────────────────────────

def load_events(path):
    """.jsonl · JSON 배열 · 배치 본문을 모두 받는다"""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []

    # 배열이나 배치 본문이면 통째로 파싱된다
    if text[0] in "[{":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, list):
            return doc
        if isinstance(doc, dict):
            return doc.get("events", [doc])

    out = []
    for i, line in enumerate(text.split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"  ! {i}번째 줄을 건너뛴다: {e}", file=sys.stderr)
    return out


SERVER_FIELDS = ("received_at", "source", "request_id", "event_index")


def enrich(events):
    """Collector 가 붙이는 4필드를 채운다.

    source 규칙은 백엔드와 같다 (KafkaEventMessage.sourceOf).
    이미 있는 값은 건드리지 않는다.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rid = "coverage_" + uuid.uuid4().hex[:12]
    n = 0
    for i, ev in enumerate(events):
        if all(k in ev for k in SERVER_FIELDS):
            continue
        ev.setdefault("source",
                      "simulator" if ev.get("actor_type") == "synthetic" else "web")
        ev.setdefault("received_at", now)
        ev.setdefault("request_id", rid)
        ev.setdefault("event_index", i)
        n += 1
    return n


# ── 계약 읽기 ───────────────────────────────────────────────────────────────

def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


TOKEN = re.compile(r"`([a-z_][a-z0-9_]*)\s*:\s*[^`]+`")
ROW = re.compile(r"^\|\s*`([a-z_][a-z0-9_]*)`\s*\|(.*)\|(.*)\|\s*$")


def parse_required_properties(path):
    """문서 §9 의 표에서 Event 별 필수 property 를 읽는다.

    돌려주는 값
        {event_name: {"section": "9.2 ...", "all": [...], "any_of": [[...], ...]}}

    `A 또는 B` 는 둘 중 하나 이상이라는 뜻이라(§9 머리말) 따로 담는다.
    `A 또는 B, C` 처럼 섞여 나오므로 '또는' 양옆 토큰만 묶고 나머지는 개별 필수다.
    """
    if not os.path.exists(path):
        return {}, None

    with open(path, encoding="utf-8") as f:
        lines = f.read().replace("\r\n", "\n").split("\n")

    spec = {}
    section = None
    in_nine = False

    for line in lines:
        h2 = re.match(r"^##\s+(\d+)\.", line)
        if h2:
            in_nine = h2.group(1) == "9"
            section = None
            continue
        if not in_nine:
            continue
        h3 = re.match(r"^###\s+(9\.(\d+).*)$", line)
        if h3:
            # 9.1~9.5 만 Event별 필수 property 표다.
            # 9.6 배열/Object 구조, 9.7 표기 규칙, 9.8 구현과 명세의 차이는
            # 표 모양이 다르므로 읽지 않는다. 9.8 을 읽으면 그 표의
            # event_name 까지 규칙으로 잡혀 분류가 어긋난다.
            section = h3.group(1).strip() if h3.group(2) in "12345" else None
            continue

        m = ROW.match(line)
        if not m:
            continue
        name, req_cell, _opt = m.group(1), m.group(2), m.group(3)
        if name == "event_name" or section is None:
            # 9.6~9.8 구간의 표는 필수 property 명세가 아니다. 읽으면
            # 9.8 의 행이 9.1~9.5 에서 이미 잡은 분류를 덮어쓴다
            continue

        toks = TOKEN.findall(req_cell)
        if not toks or "없음" in req_cell.strip()[:6]:
            spec[name] = {"section": section, "all": [], "any_of": []}
            continue

        # '또는' 양옆 토큰을 묶는다. 위치로 가른다
        spans = [(m2.start(), m2.group(1)) for m2 in TOKEN.finditer(req_cell)]
        pairs = []
        for om in re.finditer(r"또는", req_cell):
            before = [t for p, t in spans if p < om.start()]
            after = [t for p, t in spans if p > om.start()]
            if before and after:
                pairs.append([before[-1], after[0]])
        grouped = {t for pair in pairs for t in pair}
        spec[name] = {
            "section": section,
            "all": [t for t in toks if t not in grouped],
            "any_of": pairs,
        }

    return spec, path


# ── 검사 ────────────────────────────────────────────────────────────────────

def validate_envelopes(events, schema):
    """event-schema.json 으로 봉투를 검증한다. validate_events.py 와 같은 기준"""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return None, "jsonschema 가 없다. pip install -r contracts/requirements-validator.txt"

    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        return None, ("date-time 형식 검사기가 없다. "
                      "pip install -r contracts/requirements-validator.txt")

    validator = Draft202012Validator(schema, format_checker=checker)
    failures = Counter()
    bad = 0
    for ev in events:
        errs = sorted(validator.iter_errors(ev), key=lambda e: list(e.path))
        if not errs:
            continue
        bad += 1
        for e in errs[:4]:
            where = "$" + "".join(f".{p}" for p in e.path)
            failures[f"{ev.get('event_name', '?')} {where}: {e.message[:90]}"] += 1
    return {"checked": len(events), "invalid": bad, "top": failures.most_common(12)}, None


def check_properties(events, spec):
    """Event 별 필수 property 위반을 센다. 검증기가 안 보는 자리다"""
    missing = Counter()
    offenders = defaultdict(int)
    checked = 0
    for ev in events:
        name = ev.get("event_name")
        rule = spec.get(name)
        if not rule:
            continue
        checked += 1
        props = ev.get("properties")
        if not isinstance(props, dict):
            props = {}
        gaps = [k for k in rule["all"] if k not in props]
        for group in rule["any_of"]:
            if not any(k in props for k in group):
                gaps.append(" 또는 ".join(group))
        if gaps:
            offenders[name] += 1
            for g in gaps:
                missing[(name, g)] += 1
    return {"checked": checked, "events_with_gaps": dict(offenders),
            "missing": missing.most_common(30)}


# ── 출력 ────────────────────────────────────────────────────────────────────

def bar(hit, total, width=BAR_W):
    if total <= 0:
        return ""
    filled = round(width * hit / total)
    return "█" * filled + "·" * (width - filled)


def rule(ch="─", n=74):
    return ch * n


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="실행 하나가 이벤트 계약을 얼마나 밟았는지 보고한다")
    ap.add_argument("path", help="Event 파일 (.jsonl · JSON 배열 · 배치 본문)")
    ap.add_argument("--json", metavar="OUT", default=None,
                    help="보고서를 JSON 으로도 저장한다")
    ap.add_argument("--group-by-persona", action="store_true",
                    help="페르소나별 커버리지를 함께 낸다")
    ap.add_argument("--no-validate", action="store_true",
                    help="봉투 검증을 건너뛴다 (jsonschema 없이 돌릴 때)")
    a = ap.parse_args(argv)

    events = load_events(a.path)
    if not events:
        print("Event 가 없다.", file=sys.stderr)
        return 1

    schema = load_schema()
    contract = list(schema["properties"]["event_name"]["enum"])
    spec, spec_path = parse_required_properties(TAXONOMY_PATH)

    filled = enrich(events)

    names = Counter(ev.get("event_name") for ev in events)
    in_contract = [n for n in contract if names.get(n)]
    missing_names = [n for n in contract if not names.get(n)]
    off_contract = {n: c for n, c in names.items() if n not in contract}

    sessions = {ev.get("session_id") for ev in events if ev.get("session_id")}
    personas = {ev.get("persona_id") for ev in events if ev.get("persona_id")}
    actors = Counter(ev.get("actor_type") for ev in events)
    gens = Counter((ev.get("properties") or {}).get("generator_type")
                   for ev in events if ev.get("actor_type") == "synthetic")
    runs = {(ev.get("properties") or {}).get("simulation_run_id")
            for ev in events if ev.get("actor_type") == "synthetic"}
    runs.discard(None)

    print()
    print(rule("═"))
    print(f"  이벤트 계약 커버리지  ·  {os.path.relpath(a.path, ROOT)}")
    print(rule("═"))
    print(f"  Event {len(events):,}건 · 세션 {len(sessions)} · 페르소나 {len(personas)}")
    print(f"  actor_type  " + " · ".join(f"{k or '(없음)'} {v:,}" for k, v in actors.most_common()))
    if gens:
        print(f"  generator   " + " · ".join(f"{k or '(없음)'} {v:,}" for k, v in gens.most_common()))
    if runs:
        print(f"  실행 ID     " + " · ".join(sorted(x for x in runs)[:3]))
    if filled:
        print(f"  * {filled:,}건에 Collector 필드를 채워서 검증했다 "
              f"({', '.join(SERVER_FIELDS)})")

    # 1. 커버리지
    pct = 100 * len(in_contract) / len(contract)
    print()
    print(rule())
    print(f"  1. Event 커버리지   {len(in_contract)} / {len(contract)} 종  ({pct:.0f}%)")
    print(rule())

    by_section = defaultdict(list)
    for n in contract:
        sec = (spec.get(n) or {}).get("section") or "분류 없음"
        by_section[sec].append(n)

    for sec in sorted(by_section):
        group = by_section[sec]
        hit = [n for n in group if names.get(n)]
        print()
        print(f"  {sec}   {len(hit)}/{len(group)}  {bar(len(hit), len(group))}")
        for n in group:
            c = names.get(n, 0)
            mark = "○" if not c else "●"
            cnt = f"{c:,}" if c else "—"
            print(f"      {mark} {n:<28} {cnt:>8}")

    if missing_names:
        print()
        print(f"  못 밟은 Event {len(missing_names)}종:")
        print("    " + ", ".join(missing_names))

    # 2. 계약 밖
    print()
    print(rule())
    print(f"  2. 계약 밖 event_name   {len(off_contract)}종")
    print(rule())
    if off_contract:
        for n, c in sorted(off_contract.items(), key=lambda x: -x[1]):
            print(f"      ! {n:<28} {c:>8,}   enum 에 없다 → 검증기가 거절한다")
    else:
        print("      없다.")

    # 3. 봉투 검증
    env = None
    print()
    print(rule())
    print("  3. 봉투 검증   event-schema.json")
    print(rule())
    if a.no_validate:
        print("      건너뜀 (--no-validate)")
    else:
        env, err = validate_envelopes(events, schema)
        if err:
            print(f"      돌리지 못했다: {err}")
        else:
            ok = env["checked"] - env["invalid"]
            print(f"      통과 {ok:,} / {env['checked']:,}"
                  + (f"   실패 {env['invalid']:,}" if env["invalid"] else "   전부 통과"))
            for msg, c in env["top"]:
                print(f"      · {c:>6,}  {msg}")

    # 4. 필수 property
    print()
    print(rule())
    print("  4. Event별 필수 property")
    print(rule())
    if not spec:
        props = None
        print(f"      명세를 못 읽었다: {TAXONOMY_PATH}")
    else:
        props = check_properties(events, spec)
        print(f"      명세 출처 {os.path.relpath(spec_path, ROOT)}  ·  Event {len(spec)}종 규칙")
        print(f"      검사 대상 {props['checked']:,}건 / 전체 {len(events):,}건 (규칙 있는 Event 만)")
        if not props["missing"]:
            print("      위반 없다.")
        else:
            total_bad = sum(props["events_with_gaps"].values())
            print(f"      위반 {total_bad:,}건")
            print()
            print(f"      {'event_name':<28} {'누락 property':<34} {'건수':>8}")
            for (n, k), c in props["missing"]:
                print(f"      {n:<28} {k:<34} {c:>8,}")
            print()
            print("      이 위반은 Collector 를 그냥 통과한다 (properties 를 JsonNode 로 넘김).")
            print("      bad_events 에도 안 남으므로 여기서 세지 않으면 아무도 모른다.")

    # 페르소나별
    if a.group_by_persona and personas:
        print()
        print(rule())
        print("  페르소나별 커버리지")
        print(rule())
        per = defaultdict(Counter)
        for ev in events:
            if ev.get("persona_id"):
                per[ev["persona_id"]][ev.get("event_name")] += 1
        for pid in sorted(per):
            hit = len([n for n in contract if per[pid].get(n)])
            print(f"      {pid:<12} {hit:>2}/{len(contract)} 종   "
                  f"{sum(per[pid].values()):>6,}건   {bar(hit, len(contract), 24)}")

    print()
    print(rule("═"))

    report = {
        "source": os.path.relpath(a.path, ROOT),
        "events": len(events),
        "sessions": len(sessions),
        "personas": sorted(x for x in personas),
        "actor_type": dict(actors),
        "generator_type": {k: v for k, v in gens.items()},
        "coverage": {"contract": len(contract), "hit": len(in_contract),
                     "percent": round(pct, 1),
                     "seen": {n: names[n] for n in in_contract},
                     "missing": missing_names},
        "off_contract": off_contract,
        "envelope": env,
        "required_properties": (
            None if not spec else
            {"checked": props["checked"],
             "events_with_gaps": props["events_with_gaps"],
             "missing": [{"event": n, "property": k, "count": c}
                         for (n, k), c in props["missing"]]}),
        "collector_fields_filled": filled,
    }
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  JSON 저장 → {a.json}")
        print()

    # 계약 밖 Event 나 봉투 실패가 있으면 실패로 끝낸다 (CI 에서 쓸 수 있게).
    # 커버리지가 낮은 것은 실패가 아니다 — 짧은 실행에서는 정상이다.
    if off_contract:
        return 2
    if env and env["invalid"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
