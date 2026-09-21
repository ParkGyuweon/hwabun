# -*- coding: utf-8 -*-
"""평탄화 산출물이 계약을 지켰는지 검사한다.

`build_persona_tables.py` 가 냈다는 사실만으로는 계약을 지켰다는 뜻이 아니다.
같은 코드가 만들고 같은 코드가 확인하면 어긋난 줄 모른다. 그래서 검사는
TABLE_SPECS(컬럼·타입·nullable)와 원천 파일을 **다시 읽어** 대조한다.

보는 것

    A 컬럼 계약     컬럼 집합·순서, nullable=N 의 NULL, 타입
    B grain        계약이 정한 unique key 의 중복
    C enum         계약 §3 속성값과 role·label·segment_type·split
    D §11 조건     1~8 (9·10 은 Event 축이라 이 산출물의 범위 밖)
    E 누출         seed 와 holdout 이 겹치는가, 평가 Profile 에 정답이 새어들었는가
    F 참조 무결성   모든 테이블의 persona_id 가 Profile 에 있는가

위반이 하나라도 있으면 종료 코드 2 다.

실행
    py contracts/persona/validate_persona_tables.py contracts/persona/data
    py contracts/persona/validate_persona_tables.py contracts/persona/data/pa010
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import holdout_rule as hr                                                    # noqa: E402
from build_persona_tables import (SEGMENT_TYPES, SOURCE_CONFIGS, TABLE_SPECS,  # noqa: E402
                                  PRODUCTS, apply_source_contract)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 계약 §3.1 허용값
ATTR_ENUM = {
    "skin_type": {"combination", "dry", "normal", "oily"},
    "skin_tone": {"fair", "light", "medium", "tan", "deep"},
    "hair_color": {"auburn", "black", "blonde", "brown", "gray", "red"},
    "eye_color": {"blue", "brown", "gray", "green", "hazel"},
}
ROLE_ENUM = {hr.SEED, hr.HOLDOUT_TARGET, hr.EXCLUDED}
LABEL_ENUM = {hr.POSITIVE, hr.NEGATIVE, hr.DIAGNOSTIC}
SPLIT_ENUM = {"train", "valid", "test"}
PERSONA_SOURCE_ENUM = {"agent_sample", "batch_sample", "holdout_sample"}
EVALUATION_COHORT_ENUM = {"holdout_a", "holdout_b"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def _read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                rows.append((i, json.loads(line)))
    return rows


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _type_ok(value, declared):
    if value is None:
        return True
    if declared == "string":
        return isinstance(value, str)
    if declared in ("int", "long"):
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "double":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "date":
        return isinstance(value, str) and bool(DATE_RE.match(value))
    if declared == "timestamp":
        return isinstance(value, str) and bool(TS_RE.match(value))
    if declared == "array<string>":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return True


class Report:
    def __init__(self, sample_id):
        self.sample_id = sample_id
        self.violations = []
        self.notes = []
        self.checked = Counter()

    def fail(self, check, detail):
        self.violations.append((check, detail))

    def note(self, text):
        self.notes.append(text)

    def ok(self, check, count=1):
        self.checked[check] += count


def check_columns_and_types(tables, rep):
    for name, spec in TABLE_SPECS.items():
        expected = [c for c, _, _ in spec["columns"]]
        for lineno, row in tables[name]:
            if list(row.keys()) != expected:
                missing = set(expected) - set(row)
                extra = set(row) - set(expected)
                rep.fail("A.columns", f"{name}:{lineno} 컬럼 불일치 missing={sorted(missing)} extra={sorted(extra)}")
                continue
            for col, declared, nullable in spec["columns"]:
                value = row[col]
                if value is None and not nullable:
                    rep.fail("A.nullable", f"{name}:{lineno} {col} 이 NULL (계약 nullable=N)")
                elif not _type_ok(value, declared):
                    rep.fail("A.type", f"{name}:{lineno} {col} 타입 불일치 (계약 {declared}, 실제 {type(value).__name__})")
        rep.ok("A", len(tables[name]))


def check_grain(tables, rep):
    for name, spec in TABLE_SPECS.items():
        seen = Counter()
        for _, row in tables[name]:
            seen[tuple(row.get(k) for k in spec["grain"])] += 1
        dupes = [k for k, c in seen.items() if c > 1]
        if dupes:
            rep.fail("B.grain", f"{name} unique key 중복 {len(dupes)}건 예: {dupes[:3]}")
        rep.ok("B")


def check_enums(tables, rep):
    def scan(name, col, allowed, required):
        for lineno, row in tables[name]:
            value = row.get(col)
            if value is None:
                if required:
                    rep.fail("C.enum", f"{name}:{lineno} {col} 이 NULL")
                continue
            if value not in allowed:
                rep.fail("C.enum", f"{name}:{lineno} {col}={value!r} 은 계약 허용값이 아님")

    for col, allowed in ATTR_ENUM.items():
        scan("persona_profile", col, allowed, col in ("skin_type", "skin_tone"))
        scan("persona_profile_eval", col, allowed, col in ("skin_type", "skin_tone"))
        scan("persona_review_history", col, allowed, False)
        scan("persona_attribute_affinity_input", col, allowed, col in ("skin_type", "skin_tone"))

    scan("persona_review_history", "evaluation_role", ROLE_ENUM, True)
    scan("persona_profile", "latest_review_label", LABEL_ENUM, True)
    scan("persona_holdout_target", "target_label", {hr.POSITIVE}, True)   # §11-11
    scan("persona_evaluation_split", "evaluation_split", SPLIT_ENUM, True)
    scan("bridge_persona_segment", "segment_type", set(SEGMENT_TYPES), True)   # §11-8
    scan("persona_profile", "profile_scope", {"full"}, True)
    scan("persona_profile_eval", "profile_scope", {"eval"}, True)
    scan("persona_profile", "persona_source", PERSONA_SOURCE_ENUM, True)
    scan("persona_profile", "evaluation_cohort", EVALUATION_COHORT_ENUM, False)
    for lineno, row in tables["persona_profile"]:
        is_holdout = row.get("persona_source") == "holdout_sample"
        if is_holdout != (row.get("evaluation_cohort") is not None):
            rep.fail("C.cohort", f"persona_profile:{lineno} holdout_sample과 evaluation_cohort가 불일치")
    rep.ok("C")


def manifest_bands(manifest):
    """단일 대역은 `persona_band`, 합친 산출은 `persona_bands` 를 쓴다."""
    bands = manifest.get("persona_bands")
    return list(bands) if bands else [manifest["persona_band"]]


def check_cohort_consistency(tables, manifest, rep):
    # 대역을 합친 산출은 manifest 가 복수형 키를 쓴다. 행마다
    # persona_source 가 달라지므로 "manifest 값과 같다" 가 아니라 "manifest 가
    # 선언한 것 중 하나다" 를 본다. 단일 대역이면 목록 길이가 1 이라 같은 검사다.
    expected_sources = manifest.get("persona_sources") or [manifest.get("persona_source")]
    expected_cohorts = manifest.get("evaluation_cohorts") or [manifest.get("evaluation_cohort")]
    profile_cohorts = {}
    for lineno, row in tables["persona_profile"]:
        if row["persona_source"] not in expected_sources:
            rep.fail("C.source", f"persona_profile:{lineno} persona_source가 manifest와 불일치")
        if row.get("evaluation_cohort") not in expected_cohorts:
            rep.fail("C.cohort", f"persona_profile:{lineno} evaluation_cohort가 manifest와 불일치")
        profile_cohorts[row["persona_id"]] = row.get("evaluation_cohort")

    cohort_segments = defaultdict(list)
    for lineno, row in tables["bridge_persona_segment"]:
        if row["segment_type"] == "evaluation_cohort":
            cohort_segments[row["persona_id"]].append((lineno, row["segment_value"]))
    for persona_id, cohort in profile_cohorts.items():
        actual = [value for _, value in cohort_segments.get(persona_id, [])]
        expected = [] if cohort is None else [cohort]
        if actual != expected:
            rep.fail("C.cohort-segment",
                     f"{persona_id} evaluation_cohort segment={actual}, profile={cohort!r}")


def check_source_identity(tables, source_personas, rep):
    """원본 ID와 전역 ID가 양방향으로 손실 없이 매핑되는지 검사한다."""
    profiles = [row for _, row in tables["persona_profile"]]
    source_ids = [p.get("source_persona_id") for p in profiles]
    if len(set(source_ids)) != len(source_ids):
        rep.fail("D.source-id", "source_persona_id가 표본 안에서 중복됨")

    forward = {}
    reverse = {}
    for p in profiles:
        source_id = p.get("source_persona_id")
        persona_id = p.get("persona_id")
        cohort = p.get("evaluation_cohort")
        key = (cohort, source_id)

        if source_id not in source_personas:
            rep.fail("D.source-id", f"{source_id!r}를 원본 Persona 파일에서 찾을 수 없음")

        if cohort:
            try:
                source_number = int(source_id.removeprefix("PH"))
                cohort_index = ord(cohort.removeprefix("holdout_")) - ord("a")
                expected_id = f"PH{cohort_index * 2000 + source_number:05d}"
            except (AttributeError, TypeError, ValueError):
                expected_id = None
        else:
            expected_id = source_id
        if persona_id != expected_id:
            rep.fail("D.source-id",
                     f"{key} -> {persona_id}, 기대 전역 ID={expected_id}")

        if key in forward and forward[key] != persona_id:
            rep.fail("D.source-id", f"원본 키 {key}가 여러 전역 ID로 매핑됨")
        if persona_id in reverse and reverse[persona_id] != key:
            rep.fail("D.source-id", f"전역 ID {persona_id}가 여러 원본 키로 매핑됨")
        forward[key] = persona_id
        reverse[persona_id] = key
    rep.ok("D.source-id", len(profiles))


def _review_bucket(n_positive):
    if n_positive == 3:
        return "3"
    if n_positive == 4:
        return "4"
    return "5-6" if n_positive <= 6 else "7+"


def check_contract_11(tables, product_ids, rep):
    profiles = [r for _, r in tables["persona_profile"]]

    ids = [p["persona_id"] for p in profiles]                                  # §11-1
    if len(set(ids)) != len(ids):
        rep.fail("D.11-1", f"persona_id 중복 {len(ids) - len(set(ids))}건")

    for p in profiles:
        cohort = p.get("evaluation_cohort")
        if cohort:
            cohort_index = ord(cohort[-1]) - ord("a")
            lower = cohort_index * 2000 + 1
            upper = (cohort_index + 1) * 2000
            expected = f"PH{lower:05d}~PH{upper:05d}"
            try:
                number = int(p["persona_id"].removeprefix("PH"))
            except (TypeError, ValueError):
                number = -1
            if not p["persona_id"].startswith("PH") or not lower <= number <= upper:
                rep.fail("D.holdout-id",
                         f"{p['persona_id']} {cohort} ID 대역 불일치 (기대 {expected})")

        for col in ("skin_type", "skin_tone", "stratum", "review_bucket"):     # §11-2
            if not p.get(col):
                rep.fail("D.11-2", f"{p['persona_id']} {col} 없음")

        if not (p["n_reviews"] >= 3 and p["n_products"] >= 3 and p["n_positive"] >= 3):
            rep.fail("D.11-4",                                                 # §11-4
                     f"{p['persona_id']} 모집단 조건 미달 "
                     f"reviews={p['n_reviews']} products={p['n_products']} positive={p['n_positive']}")

        if p["review_bucket"] != _review_bucket(p["n_positive"]):              # §11-5
            rep.fail("D.11-5",
                     f"{p['persona_id']} review_bucket={p['review_bucket']} "
                     f"이지만 n_positive={p['n_positive']} 규칙은 {_review_bucket(p['n_positive'])}")

        expected_stratum = f"{p['skin_type']}|{p['skin_tone']}|{p['review_bucket']}"
        if p.get("stratum") != expected_stratum:
            rep.fail("D.stratum", f"{p['persona_id']} stratum={p.get('stratum')} 기대={expected_stratum}")

    for name, col in (("persona_review_history", "canonical_product_id"),      # §11-6
                      ("persona_seed_product", "canonical_product_id"),
                      ("persona_holdout_target", "target_canonical_product_id")):
        missing = {row[col] for _, row in tables[name] if row.get(col) not in product_ids}
        if missing:
            rep.fail("D.11-6", f"{name}.{col} 이 Product Feature 에 없음 {len(missing)}건 예: {sorted(missing)[:3]}")

    for _, row in tables["persona_holdout_target"]:                        # §11-11
        if not row.get("is_holdout_eligible"):
            rep.fail("D.11-11", f"{row['persona_id']} is_holdout_eligible 이 true 가 아님")

    rep.note("§11-9·10(Simulation Run 일관성, PA/PC generator_type)은 Event 축 검증이라 "
             "이 산출물의 범위 밖이다. Event 계약 검증기가 담당한다.")
    rep.ok("D")


def check_leakage(tables, product_ids, personas_by_id, rep):
    """§11-7 — 정답이 seed 쪽으로 새어들지 않았는가.

    평가 Profile 은 산출물끼리 비교하지 않고 **원천 페르소나 JSON 에서 규칙을
    다시 돌려** 대조한다. 산출물의 evaluation_role 을 믿고 검사하면 빌더가 role 을
    잘못 붙였을 때 그대로 통과한다.
    """
    seeds = defaultdict(set)
    for _, row in tables["persona_seed_product"]:
        seeds[row["persona_id"]].add(row["canonical_product_id"])

    seed_reviews = defaultdict(set)
    for _, row in tables["persona_review_history"]:
        if row["evaluation_role"] == hr.SEED:
            seed_reviews[row["persona_id"]].add(row["review_id"])

    seed_dates = defaultdict(list)
    for _, row in tables["persona_review_history"]:
        if row["evaluation_role"] == hr.SEED and row.get("submission_time"):
            seed_dates[row["persona_id"]].append(row["submission_time"])

    for _, row in tables["persona_holdout_target"]:
        pid = row["persona_id"]
        target = row["target_canonical_product_id"]
        if target in seeds.get(pid, ()):
            rep.fail("E.leak-product", f"{pid} target 상품 {target} 이 seed 에도 있음")
        if row["target_review_id"] in seed_reviews.get(pid, ()):
            rep.fail("E.leak-review", f"{pid} target 리뷰가 seed 에도 있음")

        # §11-12 시간 절단 — target 보다 나중에 쓴 리뷰는 seed 가 될 수 없다
        target_date = row.get("target_submission_time")
        if target_date:
            later = [d for d in seed_dates.get(pid, ()) if d > target_date]
            if later:
                rep.fail("E.time-cut",
                         f"{pid} target({target_date}) 이후 리뷰 {len(later)}건이 seed 에 있음")

    for _, row in tables["persona_profile_eval"]:
        persona = personas_by_id.get(row["persona_id"])
        if persona is None:
            rep.fail("E.source", f"{row['persona_id']} 를 원천 페르소나 파일에서 찾을 수 없음")
            continue
        reviews = persona.get("reviews", [])
        roles, _ = hr.classify(reviews, product_ids)
        expected_seeds = hr.seed_reviews(reviews, roles)

        for col in ("skin_type", "skin_tone", "eye_color", "hair_color"):
            expected = next((r.get(col) for r in expected_seeds if r.get(col) is not None), None)
            if row.get(col) != expected:
                rep.fail("E.eval-profile",
                         f"{row['persona_id']} eval {col}={row.get(col)!r} 이 최신 seed 리뷰 값 {expected!r} 과 다름")

        if row["n_reviews_seed"] != len(expected_seeds):
            rep.fail("E.eval-profile",
                     f"{row['persona_id']} n_reviews_seed={row['n_reviews_seed']} 실제 seed={len(expected_seeds)}")

        expected_products = len({hr.canonical_product_id(r) for r in expected_seeds})
        if row["n_products_seed"] != expected_products:
            rep.fail("E.eval-profile",
                     f"{row['persona_id']} n_products_seed={row['n_products_seed']} 기대={expected_products}")

        ratings = [r["rating"] for r in expected_seeds if r.get("rating") is not None]
        expected_avg = round(sum(ratings) / len(ratings), 4) if ratings else None
        if row["avg_rating_seed"] != expected_avg:
            rep.fail("E.eval-profile",
                     f"{row['persona_id']} avg_rating_seed={row['avg_rating_seed']} 기대={expected_avg}")

    for _, row in tables["persona_profile"]:                                # §11-13
        persona = personas_by_id.get(row["persona_id"])
        if persona is None:
            continue
        _, dec = hr.classify(persona.get("reviews", []), product_ids)
        expected = dec["latest_review_label"] if dec else None
        if row["latest_review_label"] != expected:
            rep.fail("E.latest-label",
                     f"{row['persona_id']} latest_review_label={row['latest_review_label']!r} "
                     f"기대={expected!r}")
    rep.ok("E")


def check_referential(tables, rep):
    known = {row["persona_id"] for _, row in tables["persona_profile"]}
    for name in TABLE_SPECS:
        if name == "persona_profile":
            continue
        unknown = {row["persona_id"] for _, row in tables[name]} - known
        if unknown:
            rep.fail("F.ref", f"{name} 에 Profile 에 없는 persona_id {len(unknown)}건 예: {sorted(unknown)[:3]}")
    rep.ok("F")


def validate_sample(sample_dir, product_ids, personas_by_id, source_personas):
    manifest = _load_json(os.path.join(sample_dir, "_manifest.json"))
    rep = Report(manifest["sample_id"])
    tables = {name: _read_jsonl(os.path.join(sample_dir, f"{name}.jsonl")) for name in TABLE_SPECS}

    for name, rows in tables.items():
        if len(rows) != manifest["row_counts"][name]:
            rep.fail("A.manifest", f"{name} 행 수 {len(rows)} 가 manifest {manifest['row_counts'][name]} 와 다름")

    check_columns_and_types(tables, rep)
    check_grain(tables, rep)
    check_enums(tables, rep)
    check_cohort_consistency(tables, manifest, rep)
    check_source_identity(tables, source_personas, rep)
    check_contract_11(tables, product_ids, rep)
    check_leakage(tables, product_ids, personas_by_id, rep)
    check_referential(tables, rep)
    return rep


def band_overlaps(bands):
    """모든 표본 쌍의 ID 교집합을 반환한다 (세 집합 전체 교집합이 아님)."""
    names = sorted(bands)
    return {(left, right): bands[left] & bands[right]
            for i, left in enumerate(names) for right in names[i + 1:]
            if bands[left] & bands[right]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Persona 평탄 테이블 계약 검증")
    ap.add_argument("path", nargs="?", default=os.path.join(HERE, "data"),
                    help="샘플 디렉터리 또는 그 상위 루트")
    args = ap.parse_args(argv)

    dirs = ([args.path] if os.path.exists(os.path.join(args.path, "_manifest.json"))
            else sorted(os.path.join(args.path, d) for d in os.listdir(args.path)
                        if os.path.exists(os.path.join(args.path, d, "_manifest.json"))))
    if not dirs:
        print(f"검증할 산출물이 없다: {args.path}")
        return 1

    product_ids = {p["product_id"] for p in _load_json(PRODUCTS)}
    personas_by_id = {}
    band_of_persona = {}
    for band, config in SOURCE_CONFIGS.items():
        for persona in _load_json(config["path"]):
            contracted = apply_source_contract(persona, config)
            personas_by_id[contracted["persona_id"]] = contracted
            band_of_persona[contracted["persona_id"]] = band

    source_personas_by_band = {
        band: {p["persona_id"]: p for p in _load_json(config["path"])}
        for band, config in SOURCE_CONFIGS.items()
    }
    reports = []
    for d in dirs:
        manifest = _load_json(os.path.join(d, "_manifest.json"))
        source_personas = {}
        for band in manifest_bands(manifest):
            source_personas.update(source_personas_by_band[band])
        reports.append(validate_sample(
            d, product_ids, personas_by_id, source_personas,
        ))

    # 샘플 간 persona_id 교집합 (계약 §11-1 은 모든 Dimension 표본에서 유일하다)
    # 대역별로 모은다. 표본 단위로 묶으면 합친 산출(pcall_paall)이 그 재료
    # (pcall·paall)와 겹쳐 보이는데, 같은 사람을 두 번 담은 것이라 교집합이
    # 아니다. 계약이 막으려는 것은 서로 다른 대역에 같은 persona_id 가 있는
    # 경우다.
    bands = defaultdict(set)
    for d, rep in zip(dirs, reports):
        manifest = _load_json(os.path.join(d, "_manifest.json"))
        fallback = manifest_bands(manifest)[0]
        for _, row in _read_jsonl(os.path.join(d, "persona_profile.jsonl")):
            persona_id = row["persona_id"]
            bands[band_of_persona.get(persona_id, fallback)].add(persona_id)
    overlaps = band_overlaps(bands)
    for (left, right), overlap in overlaps.items():
        reports[0].fail("D.11-1",
                        f"{left}·{right} persona_id 교집합 {len(overlap)}건")

    failed = 0
    for rep in reports:
        head = f"[{rep.sample_id}] 검사 {sum(rep.checked.values()):,}행"
        if rep.violations:
            failed += 1
            print(f"{head}  위반 {len(rep.violations)}건")
            for check, detail in rep.violations[:20]:
                print(f"  x {check:<14} {detail}")
            if len(rep.violations) > 20:
                print(f"  ... 외 {len(rep.violations) - 20}건")
        else:
            print(f"{head}  위반 0건")
        for note in rep.notes:
            print(f"  - {note}")

    if len(bands) > 1 and not overlaps:
        print(f"표본 간 persona_id 교집합 0건 확인 ({' / '.join(f'{b} {len(v)}명' for b, v in sorted(bands.items()))})")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
